"""
Signal computation for the Knowledge Engine.

Defines ArticleProfile (normalized article data for scoring) and SignalVector
(computed signals between a source and target article).

Both are pure data structures — no DB access, no rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .graph import GraphEdge, KnowledgeGraph


# ---------------------------------------------------------------------------
# ArticleProfile — normalized article data (DB-agnostic)
# ---------------------------------------------------------------------------

@dataclass
class ArticleProfile:
    """
    Normalized representation of a published article for signal computation.

    Constructed from DB data by the linker. Can also be built programmatically
    (e.g., for testing, or future non-DB sources).
    """
    article_id:    str
    keyword:       str
    category:      str
    subcategory:   str
    price_min:     int
    price_max:     int
    canonical_url: str
    # Enriched from graph node (may be empty if subcategory not in graph)
    intent_tags:   tuple[str, ...] = field(default_factory=tuple)
    personas:      tuple[str, ...] = field(default_factory=tuple)
    node_label:    str = ""

    def enrich_from_graph(self, graph: KnowledgeGraph) -> "ArticleProfile":
        """Return a new profile enriched with graph node data."""
        node = graph.get_node(self.subcategory)
        if node is None:
            return self
        return ArticleProfile(
            article_id=self.article_id,
            keyword=self.keyword,
            category=self.category,
            subcategory=self.subcategory,
            price_min=self.price_min,
            price_max=self.price_max,
            canonical_url=self.canonical_url,
            intent_tags=node.intent_tags,
            personas=node.personas,
            node_label=node.label,
        )


# ---------------------------------------------------------------------------
# SignalVector — computed signals between a source and target
# ---------------------------------------------------------------------------

@dataclass
class SignalVector:
    """
    All signals computed between a source and target ArticleProfile.

    Active signals: used in Phase 3A scoring.
    Reserved slots: 0.0 until the corresponding engine phase is activated.
    """
    # ── Active (Phase 3A) ────────────────────────────────────────────────────
    complement:          float = 0.0   # edge score from product_graph.yaml
    persona_overlap:     float = 0.0   # Jaccard(source.personas, target.personas)
    use_case_proximity:  float = 0.0   # Jaccard(source.intent_tags, target.intent_tags)
    price_compat:        float = 0.0   # price range overlap ratio
    category_match:      float = 0.0   # 1.0 if same category
    keyword_diversity:   float = 0.0   # 1 - keyword overlap (rewards dissimilarity)
    is_budget_alt:       bool  = False # same subcategory + non-overlapping price

    # ── Reserved (Phase 2+) — always 0.0 until activated ────────────────────
    seasonal_intent:     float = 0.0   # Calendar Engine (Phase 2)
    content_performance: float = 0.0   # Search Console CTR (Phase 4)
    campaign_match:      float = 0.0   # Mission/Campaign Engine (Phase 2)


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def compute_signals(
    source: ArticleProfile,
    target: ArticleProfile,
    graph:  KnowledgeGraph,
) -> SignalVector:
    """
    Compute all signals between source and target profiles.

    Pure function — no DB access, no side effects.
    """
    edge: GraphEdge | None = graph.get_edge(source.subcategory, target.subcategory)

    return SignalVector(
        complement=         edge.score if edge else 0.0,
        persona_overlap=    _jaccard(set(source.personas), set(target.personas)),
        use_case_proximity= _jaccard(set(source.intent_tags), set(target.intent_tags)),
        price_compat=       _price_compat(source, target),
        category_match=     1.0 if source.category == target.category else 0.0,
        keyword_diversity=  _keyword_diversity(source.keyword, target.keyword),
        is_budget_alt=      _is_budget_alt(source, target),
        seasonal_intent=    0.0,
        content_performance=0.0,
        campaign_match=     0.0,
    )


# ---------------------------------------------------------------------------
# Helper computations
# ---------------------------------------------------------------------------

def _jaccard(a: set, b: set) -> float:
    """Jaccard similarity: |A∩B| / |A∪B|. Returns 0.0 if both empty."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _price_compat(source: ArticleProfile, target: ArticleProfile) -> float:
    """
    Price range compatibility: overlap ratio over union of price ranges.

    Returns 0.0 if either article has no price data.
    Returns 1.0 if ranges are identical.
    Returns lower values as ranges diverge.
    """
    s_min, s_max = source.price_min, source.price_max
    t_min, t_max = target.price_min, target.price_max

    if not (s_min or s_max) or not (t_min or t_max):
        return 0.0
    if s_max < s_min or t_max < t_min:
        return 0.0

    overlap_min = max(s_min, t_min)
    overlap_max = min(s_max, t_max)
    overlap = max(0, overlap_max - overlap_min)

    union_min = min(s_min, t_min)
    union_max = max(s_max, t_max)
    union = max(1, union_max - union_min)

    return overlap / union


def _keyword_diversity(kw_a: str, kw_b: str) -> float:
    """
    Token-level diversity: 1 - Jaccard(tokens_a, tokens_b).

    Rewards different keyword contexts. Returns 1.0 if completely different,
    0.0 if identical.
    """
    tokens_a = set(kw_a.lower().split())
    tokens_b = set(kw_b.lower().split())
    return 1.0 - _jaccard(tokens_a, tokens_b)


def _is_budget_alt(source: ArticleProfile, target: ArticleProfile) -> bool:
    """
    True when source and target are in the same subcategory but their price
    ranges do not overlap — i.e., they serve different budget tiers.
    """
    if source.subcategory != target.subcategory:
        return False
    if source.article_id == target.article_id:
        return False
    # Non-overlapping: target is either cheaper or more expensive with no overlap
    s_min, s_max = source.price_min, source.price_max
    t_min, t_max = target.price_min, target.price_max
    return t_max < s_min or t_min > s_max
