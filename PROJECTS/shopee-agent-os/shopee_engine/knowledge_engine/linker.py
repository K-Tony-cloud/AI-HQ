"""
Knowledge Engine — Internal Linking core.

Public API:
    compute_links(source, candidates, graph) → LinkBundle
        Pure function — no DB, no rendering, fully testable.

    get_article_links(article_id, con) → LinkBundle
        DB convenience wrapper. Returns cold-start bundle if threshold not met.

Both functions return LinkBundle — a data structure, NOT markdown.
Rendering is the responsibility of the caller (article_exporter, API, etc.).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date

from .graph import KnowledgeGraph, LinkConfig, PinnedLink
from .signals import ArticleProfile, SignalVector, compute_signals

_SITE_URL = os.getenv("SHOPEE_SITE_URL", "https://suenaidee.com")
_VALID_PLACEMENTS = ("post_advisor", "post_summary")
_POST_ADVISOR_TYPES = {"complement", "budget_alt"}
_POST_SUMMARY_TYPES = {"related", "type_alt"}


# ---------------------------------------------------------------------------
# Output data structures
# ---------------------------------------------------------------------------

@dataclass
class LinkRecord:
    """A single resolved internal link — pure data, ready for any renderer."""
    link_type:    str      # "complement" | "budget_alt" | "type_alt" | "related"
    target_id:    str
    target_url:   str
    target_label: str
    anchor_text:  str
    score:        float
    placement:    str      # "post_advisor" | "post_summary"
    pinned:       bool
    signals:      SignalVector


@dataclass
class LinkBundle:
    """
    All resolved internal links for a single article.

    _show=False means the section must be hidden entirely.
    links is empty when _show=False.

    Callers must NOT render the section if _show is False.
    """
    _show:            bool
    _reason:          str
    _candidate_count: int
    _pinned_count:    int
    links:            list[LinkRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure computation API
# ---------------------------------------------------------------------------

def compute_links(
    source:     ArticleProfile,
    candidates: list[ArticleProfile],
    graph:      KnowledgeGraph,
) -> LinkBundle:
    """
    Compute internal links for a source article given a list of candidates.

    Pure function — no DB access, no rendering.
    Returns LinkBundle with _show=False when safety filters leave too few links.
    """
    cfg = graph.config

    # Safety: remove self and any with no meaningful data
    candidates = [c for c in candidates if c.article_id != source.article_id]

    all_candidates = list(candidates)

    # ── Score all candidates ─────────────────────────────────────────────────
    scored: list[tuple[float, str, str, SignalVector, ArticleProfile]] = []
    # (score, link_type, anchor, signals, profile)

    seen_subcategories: set[str] = set()

    for target in candidates:
        signals  = compute_signals(source, target, graph)
        raw      = _weighted_score(signals, cfg)
        lt, mult = _resolve_link_type(source, target, signals, graph)
        if lt is None:
            continue

        # Diversity penalty when same subcategory already queued
        if target.subcategory in seen_subcategories:
            mult *= cfg.same_subcategory_penalty

        final = raw * mult
        if final < cfg.min_score_threshold:
            continue

        anchor = _select_anchor(source, target, lt, graph)
        placement = _placement_for(lt)

        scored.append((final, lt, anchor, signals, target))

    # ── Deduplicate: keep best score per target ──────────────────────────────
    best_by_target: dict[str, tuple[float, str, str, SignalVector, ArticleProfile]] = {}
    for entry in scored:
        tid = entry[4].article_id
        if tid not in best_by_target or entry[0] > best_by_target[tid][0]:
            best_by_target[tid] = entry

    ranked = sorted(best_by_target.values(), key=lambda x: -x[0])

    # ── Apply per-subcategory cap ────────────────────────────────────────────
    subcategory_counts: dict[str, int] = {}
    selected: list[tuple[float, str, str, SignalVector, ArticleProfile]] = []

    for entry in ranked:
        score, lt, anchor, signals, target = entry
        subcat = target.subcategory
        if lt != "budget_alt":
            count = subcategory_counts.get(subcat, 0)
            if count >= cfg.max_same_subcategory:
                continue
            subcategory_counts[subcat] = count + 1
        if len(selected) >= cfg.max_links_per_article:
            break
        selected.append(entry)

    # ── Build LinkRecords ────────────────────────────────────────────────────
    records: list[LinkRecord] = [
        LinkRecord(
            link_type=lt,
            target_id=target.article_id,
            target_url=target.canonical_url,
            target_label=target.node_label or target.keyword,
            anchor_text=anchor,
            score=round(score, 4),
            placement=_placement_for(lt),
            pinned=False,
            signals=signals,
        )
        for score, lt, anchor, signals, target in selected
    ]

    if len(records) < cfg.min_links_to_show:
        return LinkBundle(
            _show=False,
            _reason=f"too_few_links: {len(records)} valid candidates < {cfg.min_links_to_show}",
            _candidate_count=len(all_candidates),
            _pinned_count=0,
            links=[],
        )

    return LinkBundle(
        _show=True,
        _reason="ok",
        _candidate_count=len(all_candidates),
        _pinned_count=0,
        links=records,
    )


# ---------------------------------------------------------------------------
# DB convenience wrapper
# ---------------------------------------------------------------------------

def get_article_links(article_id: str, con) -> LinkBundle:
    """
    Compute internal links for an article, loading candidates from the DB.

    Cold-start gate: returns _show=False if published article count is below
    the configured threshold. Threshold is read from link_config.yaml.

    con: a DuckDB connection (read access to seo_articles + seo_article_products + products).
    """
    graph = KnowledgeGraph.load()
    cfg   = graph.config

    # ── Cold-start gate ──────────────────────────────────────────────────────
    published_count = _count_published(con)
    if published_count < cfg.min_published_threshold:
        return LinkBundle(
            _show=False,
            _reason=(
                f"cold_start: {published_count} published articles "
                f"< threshold {cfg.min_published_threshold}"
            ),
            _candidate_count=0,
            _pinned_count=0,
            links=[],
        )

    # ── Load all published profiles ───────────────────────────────────────────
    all_profiles = _load_profiles(con, graph)

    source_profile = next(
        (p for p in all_profiles if p.article_id == article_id), None
    )
    if source_profile is None:
        return LinkBundle(
            _show=False,
            _reason=f"source_not_found: '{article_id}' not in published articles",
            _candidate_count=0,
            _pinned_count=0,
            links=[],
        )

    candidates = [p for p in all_profiles if p.article_id != article_id]

    # ── Pure scoring ─────────────────────────────────────────────────────────
    bundle = compute_links(source_profile, candidates, graph)

    # ── Inject pinned links (bypass scoring, front of list) ──────────────────
    pinned_records = _resolve_pinned(article_id, all_profiles, graph)
    if pinned_records:
        # Remove any algorithm-selected links that duplicate a pinned target
        pinned_ids = {r.target_id for r in pinned_records}
        algo_links = [r for r in bundle.links if r.target_id not in pinned_ids]
        combined   = (pinned_records + algo_links)[: cfg.max_links_per_article]
        total_show = len(combined) >= cfg.min_links_to_show
        bundle = LinkBundle(
            _show=total_show,
            _reason="ok" if total_show else f"too_few_links: {len(combined)} < {cfg.min_links_to_show}",
            _candidate_count=bundle._candidate_count,
            _pinned_count=len(pinned_records),
            links=combined if total_show else [],
        )

    return bundle


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _weighted_score(signals: SignalVector, cfg: LinkConfig) -> float:
    w = cfg.weights
    return (
        w.get("complement",          0) * signals.complement
      + w.get("persona_overlap",     0) * signals.persona_overlap
      + w.get("use_case_proximity",  0) * signals.use_case_proximity
      + w.get("price_compat",        0) * signals.price_compat
      + w.get("category_match",      0) * signals.category_match
      + w.get("keyword_diversity",   0) * signals.keyword_diversity
      + w.get("seasonal_intent",     0) * signals.seasonal_intent
      + w.get("content_performance", 0) * signals.content_performance
      + w.get("campaign_match",      0) * signals.campaign_match
    )


def _resolve_link_type(
    source:  ArticleProfile,
    target:  ArticleProfile,
    signals: SignalVector,
    graph:   KnowledgeGraph,
) -> tuple[str | None, float]:
    """
    Determine the most appropriate link_type for a source→target pair.
    Returns (link_type, score_multiplier) or (None, 0) if no valid type.

    Priority:
      1. budget_alt  — same subcategory, non-overlapping price
      2. complement  — explicit graph edge of type "complement"
      3. type_alt    — explicit graph edge of type "type_alt"
      4. related     — explicit graph edge of type "related" or same category
    """
    cfg = graph.config

    if signals.is_budget_alt:
        return "budget_alt", cfg.budget_alt_bonus

    edge = graph.get_edge(source.subcategory, target.subcategory)
    if edge:
        return edge.link_type, 1.0

    if signals.category_match > 0 and signals.use_case_proximity > 0.1:
        return "related", 1.0

    return None, 0.0


def _placement_for(link_type: str) -> str:
    return "post_advisor" if link_type in _POST_ADVISOR_TYPES else "post_summary"


def _select_anchor(
    source: ArticleProfile,
    target: ArticleProfile,
    link_type: str,
    graph: KnowledgeGraph,
) -> str:
    """
    Select anchor text using the configured rotation strategy.
    Fills template variables with profile data.
    """
    pool = graph.get_anchor_pool(source.subcategory, link_type)
    if not pool:
        return target.node_label or target.keyword

    strategy = graph.config.anchor_rotation
    if strategy == "hash":
        idx = hash(source.article_id + target.article_id) % len(pool)
    else:
        # round_robin / performance: fall back to hash until implemented
        idx = hash(source.article_id + target.article_id) % len(pool)

    template = pool[idx]

    # Price range label for budget_alt
    t_price = (
        f"฿{target.price_min:,}–฿{target.price_max:,}"
        if target.price_min and target.price_max
        else ""
    )
    source_label = source.node_label or source.keyword
    target_label = target.node_label or target.keyword

    return (
        template
        .replace("{source_label}",       source_label)
        .replace("{target_label}",       target_label)
        .replace("{target_price_range}", t_price)
        .replace("{target_category_label}", target.node_label or "")
    )


def _count_published(con) -> int:
    row = con.execute(
        "SELECT COUNT(*) FROM seo_articles WHERE status = 'published'"
    ).fetchone()
    return int(row[0]) if row else 0


def _load_profiles(con, graph: KnowledgeGraph) -> list[ArticleProfile]:
    """Load all published article profiles from DB and enrich from graph."""
    rows = con.execute("""
        SELECT
            a.article_id,
            a.keyword,
            a.category,
            COALESCE(a.subcategory, '') AS subcategory,
            COALESCE(MIN(p.sale_price), 0) AS price_min,
            COALESCE(MAX(p.sale_price), 0) AS price_max
        FROM seo_articles a
        LEFT JOIN seo_article_products ap ON a.article_id = ap.article_id
        LEFT JOIN products p
            ON ap.itemid = p.itemid AND ap.shopid = p.shopid
            AND p.sale_price IS NOT NULL AND p.sale_price > 0
        WHERE a.status = 'published'
        GROUP BY a.article_id, a.keyword, a.category, a.subcategory
    """).fetchall()

    profiles = []
    for row in rows:
        article_id, keyword, category, subcategory, price_min, price_max = row
        canonical_url = f"{_SITE_URL}/{article_id}/"
        profile = ArticleProfile(
            article_id=article_id,
            keyword=str(keyword or ""),
            category=str(category or ""),
            subcategory=str(subcategory or ""),
            price_min=int(price_min or 0),
            price_max=int(price_max or 0),
            canonical_url=canonical_url,
        ).enrich_from_graph(graph)
        profiles.append(profile)

    return profiles


def _resolve_pinned(
    source_id:    str,
    all_profiles: list[ArticleProfile],
    graph:        KnowledgeGraph,
) -> list[LinkRecord]:
    """Resolve pinned links for the source article. Safety-checked."""
    today = date.today().isoformat()
    published_ids = {p.article_id for p in all_profiles}
    profile_map   = {p.article_id: p for p in all_profiles}

    records: list[LinkRecord] = []
    for pin in graph.pinned:
        if pin.source_article_id != source_id:
            continue
        if pin.expires_at and pin.expires_at < today:
            continue
        if pin.target_article_id not in published_ids:
            continue   # safety: target must be published
        if pin.target_article_id == source_id:
            continue   # safety: no self-link

        target = profile_map[pin.target_article_id]
        records.append(LinkRecord(
            link_type=pin.link_type,
            target_id=pin.target_article_id,
            target_url=target.canonical_url,
            target_label=target.node_label or target.keyword,
            anchor_text=pin.anchor_text,
            score=1.0,
            placement=pin.placement,
            pinned=True,
            signals=SignalVector(),
        ))

    return records
