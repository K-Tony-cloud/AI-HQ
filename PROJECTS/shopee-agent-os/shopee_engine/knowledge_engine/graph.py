"""
KnowledgeGraph — loads, validates, and caches the product knowledge graph.

Reads three YAML files from shopee_engine/knowledge/:
  - product_graph.yaml  → nodes, edges, anchor templates
  - link_config.yaml    → scoring weights, thresholds, limits
  - pinned_links.yaml   → admin-pinned links

Validation runs at first load (startup). All errors are collected before
raising so the operator can see every problem at once.

Public surface:
  KnowledgeGraph.load()            → singleton instance (cached after first call)
  KnowledgeGraph.from_paths(...)   → for testing with custom YAML paths
  graph.get_edge(src, tgt)         → GraphEdge | None
  graph.get_anchor_pool(src, type) → list[str]
  graph.config                     → LinkConfig (weights, limits, multipliers)
  graph.pinned                     → list[PinnedLink]
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ._exceptions import ConfigValidationError, GraphValidationError, PinsValidationError

# Default YAML paths (relative to this file's package location)
_KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
_GRAPH_PATH  = _KNOWLEDGE_DIR / "product_graph.yaml"
_CONFIG_PATH = _KNOWLEDGE_DIR / "link_config.yaml"
_PINS_PATH   = _KNOWLEDGE_DIR / "pinned_links.yaml"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GraphNode:
    id:            str
    label:         str
    category:      str
    intent_tags:   tuple[str, ...]
    personas:      tuple[str, ...]
    price_typical: tuple[int, int]   # (min, max) in THB


@dataclass(frozen=True)
class GraphEdge:
    source:    str
    target:    str
    link_type: str    # "complement" | "type_alt" | "related"
    score:     float  # 0.0–1.0
    rationale: str


@dataclass(frozen=True)
class PinnedLink:
    source_article_id: str
    target_article_id: str
    link_type:         str
    anchor_text:       str
    placement:         str     # "post_advisor" | "post_summary"
    priority:          int
    note:              str
    expires_at:        str | None   # "YYYY-MM-DD" or None


@dataclass
class LinkConfig:
    # Scoring weights (sum must ≈ 1.0)
    weights:     dict[str, float]
    # Multipliers
    budget_alt_bonus:         float
    same_subcategory_penalty: float
    min_score_threshold:      float
    # Limits
    max_links_per_article:    int
    max_same_subcategory:     int
    min_links_to_show:        int
    min_published_threshold:  int
    # Anchor rotation
    anchor_rotation: str


# ---------------------------------------------------------------------------
# KnowledgeGraph
# ---------------------------------------------------------------------------

class KnowledgeGraph:
    """
    Loaded-and-validated knowledge graph. Use KnowledgeGraph.load() for
    the singleton; use KnowledgeGraph.from_paths() in tests.
    """

    _instance: KnowledgeGraph | None = None

    def __init__(
        self,
        nodes:              dict[str, GraphNode],
        edges:              list[GraphEdge],
        anchor_generic:     dict[str, list[str]],
        anchor_overrides:   dict[str, dict[str, list[str]]],
        config:             LinkConfig,
        pinned:             list[PinnedLink],
    ) -> None:
        self._nodes            = nodes
        self._edges            = edges
        self._anchor_generic   = anchor_generic
        self._anchor_overrides = anchor_overrides
        self.config            = config
        self.pinned            = pinned

        # Build lookup index: (source_subcategory, target_subcategory) → edge
        self._edge_index: dict[tuple[str, str], GraphEdge] = {
            (e.source, e.target): e for e in edges
        }

    # ── Queries ──────────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)

    def get_edge(self, source: str, target: str) -> GraphEdge | None:
        return self._edge_index.get((source, target))

    def get_anchor_pool(self, source_subcategory: str, link_type: str) -> list[str]:
        """Return anchor template pool. Subcategory override takes priority."""
        override = (
            self._anchor_overrides
            .get(source_subcategory, {})
            .get(link_type)
        )
        if override:
            return override
        return self._anchor_generic.get(link_type, [])

    def all_node_ids(self) -> list[str]:
        return list(self._nodes.keys())

    # ── Singleton ────────────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> "KnowledgeGraph":
        """Return singleton instance, loading and validating YAML on first call."""
        if cls._instance is None:
            cls._instance = cls.from_paths(_GRAPH_PATH, _CONFIG_PATH, _PINS_PATH)
        return cls._instance

    @classmethod
    def _reset(cls) -> None:
        """Reset singleton — for use in tests only."""
        cls._instance = None

    # ── Factories ────────────────────────────────────────────────────────────

    @classmethod
    def from_paths(
        cls,
        graph_path:  Path,
        config_path: Path,
        pins_path:   Path,
    ) -> "KnowledgeGraph":
        """Load from YAML files. Validates everything before returning."""
        graph_data  = _load_yaml(graph_path)
        config_data = _load_yaml(config_path)
        pins_data   = _load_yaml(pins_path)
        return cls.from_dicts(graph_data, config_data, pins_data)

    @classmethod
    def from_dicts(
        cls,
        graph_data:  dict,
        config_data: dict,
        pins_data:   dict,
    ) -> "KnowledgeGraph":
        """Construct from raw dicts (for testing or programmatic use)."""
        nodes, edges, anchor_generic, anchor_overrides = _parse_and_validate_graph(graph_data)
        config  = _parse_and_validate_config(config_data)
        pinned  = _parse_and_validate_pins(pins_data)
        return cls(nodes, edges, anchor_generic, anchor_overrides, config, pinned)


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise KnowledgeGraphFileError(f"Knowledge file not found: {path}")
    except yaml.YAMLError as exc:
        raise GraphValidationError(f"YAML parse error in {path.name}: {exc}")


class KnowledgeGraphFileError(GraphValidationError):
    pass


# ---------------------------------------------------------------------------
# Graph parsing and validation
# ---------------------------------------------------------------------------

_VALID_EDGE_TYPES = {"complement", "type_alt", "related"}
_VALID_PLACEMENTS = {"post_advisor", "post_summary"}
_VALID_LINK_TYPES = _VALID_EDGE_TYPES | {"budget_alt"}


def _parse_and_validate_graph(
    data: dict,
) -> tuple[dict[str, GraphNode], list[GraphEdge], dict[str, list[str]], dict[str, dict[str, list[str]]]]:
    errors: list[str] = []

    # ── Nodes ────────────────────────────────────────────────────────────────
    raw_nodes: dict[str, Any] = data.get("nodes") or {}
    if not raw_nodes:
        errors.append("graph: 'nodes' is empty or missing")

    nodes: dict[str, GraphNode] = {}
    seen_ids: set[str] = set()

    for node_id, attrs in raw_nodes.items():
        if node_id in seen_ids:
            errors.append(f"graph: duplicate node id '{node_id}'")
            continue
        seen_ids.add(node_id)

        if not attrs:
            errors.append(f"graph: node '{node_id}' has no attributes")
            continue

        label    = attrs.get("label", "")
        category = attrs.get("category", "")
        tags     = attrs.get("intent_tags") or []
        personas = attrs.get("personas") or []
        price    = attrs.get("price_typical") or []

        if not label:
            errors.append(f"graph: node '{node_id}' missing 'label'")
        if not category:
            errors.append(f"graph: node '{node_id}' missing 'category'")
        if len(price) != 2 or not all(isinstance(x, (int, float)) for x in price):
            errors.append(f"graph: node '{node_id}' 'price_typical' must be [min, max]")
        if not isinstance(tags, list):
            errors.append(f"graph: node '{node_id}' 'intent_tags' must be a list")
        if not isinstance(personas, list):
            errors.append(f"graph: node '{node_id}' 'personas' must be a list")

        nodes[node_id] = GraphNode(
            id=node_id,
            label=label,
            category=category,
            intent_tags=tuple(str(t) for t in tags),
            personas=tuple(str(p) for p in personas),
            price_typical=(int(price[0]), int(price[1])) if len(price) == 2 else (0, 0),
        )

    # ── Edges ────────────────────────────────────────────────────────────────
    raw_edges: list[dict] = data.get("edges") or []
    edges: list[GraphEdge] = []

    for i, e in enumerate(raw_edges):
        src  = e.get("source", "")
        tgt  = e.get("target", "")
        etype = e.get("type", "")
        score = e.get("score")

        prefix = f"graph: edge[{i}] ({src}→{tgt})"

        if not src:
            errors.append(f"{prefix}: missing 'source'")
        elif src not in nodes:
            errors.append(f"{prefix}: source '{src}' not in nodes")

        if not tgt:
            errors.append(f"{prefix}: missing 'target'")
        elif tgt not in nodes:
            errors.append(f"{prefix}: target '{tgt}' not in nodes")

        if src and tgt and src == tgt:
            errors.append(f"{prefix}: self-edge not allowed")

        if etype not in _VALID_EDGE_TYPES:
            errors.append(f"{prefix}: invalid type '{etype}'. Must be one of {sorted(_VALID_EDGE_TYPES)}")

        if score is None or not isinstance(score, (int, float)):
            errors.append(f"{prefix}: 'score' must be a number")
        elif not (0.0 <= float(score) <= 1.0):
            errors.append(f"{prefix}: score {score} out of range [0.0, 1.0]")

        if not errors or all(prefix not in err for err in errors[-6:]):
            edges.append(GraphEdge(
                source=src, target=tgt, link_type=etype,
                score=float(score) if score is not None else 0.0,
                rationale=str(e.get("rationale", "")),
            ))

    # ── Anchor templates ─────────────────────────────────────────────────────
    raw_templates: dict = data.get("anchor_templates") or {}
    anchor_generic:   dict[str, list[str]] = {}
    anchor_overrides: dict[str, dict[str, list[str]]] = {}

    for link_type, pool in raw_templates.items():
        if link_type == "subcategory_overrides":
            if not isinstance(pool, dict):
                errors.append("graph: 'anchor_templates.subcategory_overrides' must be a mapping")
                continue
            for sub_id, sub_map in pool.items():
                if not isinstance(sub_map, dict):
                    errors.append(f"graph: anchor_templates.subcategory_overrides.{sub_id} must be a mapping")
                    continue
                anchor_overrides[sub_id] = {}
                for lt, tmpl_list in sub_map.items():
                    if not isinstance(tmpl_list, list) or not tmpl_list:
                        errors.append(f"graph: anchor override {sub_id}.{lt} must be a non-empty list")
                    else:
                        anchor_overrides[sub_id][lt] = [str(t) for t in tmpl_list]
            continue

        if link_type not in _VALID_LINK_TYPES:
            errors.append(f"graph: unknown anchor link_type '{link_type}'. Valid: {sorted(_VALID_LINK_TYPES)}")
            continue
        if not isinstance(pool, list) or not pool:
            errors.append(f"graph: anchor_templates.{link_type} must be a non-empty list")
        else:
            for j, tmpl in enumerate(pool):
                if not isinstance(tmpl, str) or not tmpl.strip():
                    errors.append(f"graph: anchor_templates.{link_type}[{j}] must be a non-empty string")
            anchor_generic[link_type] = [str(t) for t in pool]

    if errors:
        raise GraphValidationError(
            f"product_graph.yaml has {len(errors)} error(s):\n" +
            "\n".join(f"  • {e}" for e in errors)
        )

    return nodes, edges, anchor_generic, anchor_overrides


# ---------------------------------------------------------------------------
# Config parsing and validation
# ---------------------------------------------------------------------------

_REQUIRED_WEIGHT_KEYS = {
    "complement", "persona_overlap", "use_case_proximity",
    "price_compat", "category_match", "keyword_diversity",
    "seasonal_intent", "content_performance", "campaign_match",
}
_VALID_ROTATION = {"hash", "round_robin", "performance"}


def _parse_and_validate_config(data: dict) -> LinkConfig:
    errors: list[str] = []

    weights_raw: dict = data.get("scoring_weights") or {}
    multipliers: dict = data.get("multipliers") or {}
    limits:      dict = data.get("limits") or {}

    # Weight keys
    missing_keys = _REQUIRED_WEIGHT_KEYS - set(weights_raw.keys())
    if missing_keys:
        errors.append(f"config: scoring_weights missing keys: {sorted(missing_keys)}")

    # Weight values
    for k, v in weights_raw.items():
        if not isinstance(v, (int, float)):
            errors.append(f"config: scoring_weights.{k} must be a number, got {type(v).__name__}")
        elif v < 0:
            errors.append(f"config: scoring_weights.{k} = {v} is negative")

    # Weight sum
    weight_sum = sum(float(v) for v in weights_raw.values() if isinstance(v, (int, float)))
    if abs(weight_sum - 1.0) > 0.001:
        errors.append(f"config: scoring_weights sum = {weight_sum:.4f}, must be 1.0")

    # Multipliers
    for key in ("budget_alt_bonus", "same_subcategory_penalty", "min_score_threshold"):
        v = multipliers.get(key)
        if v is None:
            errors.append(f"config: multipliers.{key} is missing")
        elif not isinstance(v, (int, float)) or float(v) < 0:
            errors.append(f"config: multipliers.{key} must be a non-negative number")

    # Limits
    for key in ("max_links_per_article", "max_same_subcategory", "min_links_to_show", "min_published_threshold"):
        v = limits.get(key)
        if v is None:
            errors.append(f"config: limits.{key} is missing")
        elif not isinstance(v, int) or v < 0:
            errors.append(f"config: limits.{key} must be a non-negative integer")

    # Rotation
    rotation = data.get("anchor_rotation", "hash")
    if rotation not in _VALID_ROTATION:
        errors.append(f"config: anchor_rotation '{rotation}' invalid. Must be one of {sorted(_VALID_ROTATION)}")

    if errors:
        raise ConfigValidationError(
            f"link_config.yaml has {len(errors)} error(s):\n" +
            "\n".join(f"  • {e}" for e in errors)
        )

    return LinkConfig(
        weights=   {k: float(v) for k, v in weights_raw.items()},
        budget_alt_bonus=        float(multipliers.get("budget_alt_bonus", 1.2)),
        same_subcategory_penalty=float(multipliers.get("same_subcategory_penalty", 0.5)),
        min_score_threshold=     float(multipliers.get("min_score_threshold", 0.25)),
        max_links_per_article=   int(limits.get("max_links_per_article", 4)),
        max_same_subcategory=    int(limits.get("max_same_subcategory", 1)),
        min_links_to_show=       int(limits.get("min_links_to_show", 2)),
        min_published_threshold= int(limits.get("min_published_threshold", 5)),
        anchor_rotation=rotation,
    )


# ---------------------------------------------------------------------------
# Pins parsing and validation
# ---------------------------------------------------------------------------

def _parse_and_validate_pins(data: dict) -> list[PinnedLink]:
    errors: list[str] = []
    raw_pins: list[dict] = data.get("pinned") or []

    if not isinstance(raw_pins, list):
        raise PinsValidationError("pinned_links.yaml: 'pinned' must be a list")

    pins: list[PinnedLink] = []

    for i, p in enumerate(raw_pins):
        prefix = f"pins[{i}]"

        src  = p.get("source_article_id", "")
        tgt  = p.get("target_article_id", "")
        lt   = p.get("link_type", "")
        anc  = p.get("anchor_text", "")
        plc  = p.get("placement", "post_advisor")
        pri  = p.get("priority", 99)
        note = p.get("note", "")
        exp  = p.get("expires_at")

        if not src:
            errors.append(f"{prefix}: missing 'source_article_id'")
        if not tgt:
            errors.append(f"{prefix}: missing 'target_article_id'")
        if src and tgt and src == tgt:
            errors.append(f"{prefix}: source and target are the same article")
        if lt not in _VALID_LINK_TYPES:
            errors.append(f"{prefix}: invalid link_type '{lt}'")
        if not anc or not anc.strip():
            errors.append(f"{prefix}: 'anchor_text' must be non-empty")
        if plc not in _VALID_PLACEMENTS:
            errors.append(f"{prefix}: invalid placement '{plc}'")
        if not isinstance(pri, int):
            errors.append(f"{prefix}: 'priority' must be an integer")

        if not errors:
            pins.append(PinnedLink(
                source_article_id=src, target_article_id=tgt,
                link_type=lt, anchor_text=anc,
                placement=plc, priority=pri,
                note=str(note), expires_at=str(exp) if exp else None,
            ))

    if errors:
        raise PinsValidationError(
            f"pinned_links.yaml has {len(errors)} error(s):\n" +
            "\n".join(f"  • {e}" for e in errors)
        )

    return sorted(pins, key=lambda x: x.priority)
