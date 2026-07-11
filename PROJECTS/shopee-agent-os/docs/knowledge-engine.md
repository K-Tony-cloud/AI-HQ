# Knowledge Engine

Knowledge Platform ของ suenaidee.com — ระบบที่ให้ข้อมูลเชิงความรู้แก่ทุก feature ของเว็บไซต์

## ภาพรวม

Knowledge Engine ไม่ใช่แค่ระบบ Internal Linking แต่เป็น Knowledge Platform ส่วนกลาง ที่ทำหน้าที่เป็นฐานความรู้สำหรับ:

- **Internal Linking** — ลิงก์บทความตาม intent และ product relationship
- **Topic Cluster** (Phase 3D) — จัดกลุ่มบทความรอบ pillar topic
- **Homepage Recommendation** (อนาคต) — แนะนำบทความตาม context ผู้ใช้
- **Search** (อนาคต) — เสริม search ranking ด้วย semantic signals
- **Mission/Campaign** (Phase 2) — ลิงก์ตาม campaign context
- **Calendar/Seasonal** (Phase 2) — ลิงก์ตาม seasonal intent

## Architecture

```
shopee_engine/
  knowledge_engine/          ← Python package (public API)
    __init__.py              # stable public exports
    graph.py                 # KnowledgeGraph — YAML loader + validator + cache
    signals.py               # ArticleProfile, SignalVector, compute_signals()
    linker.py                # compute_links(), get_article_links(), LinkBundle
    cluster.py               # ClusterBundle stub (Phase 3D)
    _exceptions.py           # exception hierarchy

  knowledge/                 ← Data files (Knowledge Graph)
    product_graph.yaml       # nodes, edges, anchor templates
    link_config.yaml         # scoring weights, thresholds, limits
    pinned_links.yaml        # admin-pinned links
```

## Design Principles

1. **Library First** — import เพียง `from shopee_engine.knowledge_engine import ...` โดยไม่ต้องรู้ implementation ภายใน
2. **Data Driven** — knowledge, weights, thresholds, anchors อยู่ใน YAML ทั้งหมด ไม่ hardcode ใน Python
3. **Logic ≠ Rendering** — Engine คืน data structure (`LinkBundle`) เท่านั้น ไม่สร้าง markdown
4. **Validate at Startup** — YAML validation รวม error ทั้งหมดก่อน raise เพื่อให้แก้ได้ทีเดียว
5. **Extensible** — future signals, strategies, cluster types เพิ่มได้โดยไม่ rewrite
6. **Performance** — KnowledgeGraph โหลด YAML ครั้งเดียว, cache ไว้ใน singleton

## Knowledge Graph (`product_graph.yaml`)

### Nodes

แต่ละ node แทน subcategory ของสินค้า

```yaml
nodes:
  usb-mobile-fans:
    label: "พัดลม USB & มือถือ"
    category: mobile-gadgets
    intent_tags: [cooling, portable, office, daily-use, summer, wfh]
    personas: [งบน้อย, ใช้งานหนักทุกวัน, พกพาบ่อย, คะแนนดีที่สุด, ซื้อเป็นของขวัญ]
    price_typical: [100, 1000]
```

| Field | ความหมาย |
|-------|----------|
| `label` | ชื่อที่แสดงใน anchor text |
| `category` | category ระดับบน (ใช้ใน category_match signal) |
| `intent_tags` | use-case signals — ใช้คำนวณ use_case_proximity |
| `personas` | buyer persona — ใช้คำนวณ persona_overlap |
| `price_typical` | ช่วงราคาปกติ [min, max] — ใช้คำนวณ price_compat |

### Edges

Edge แสดง relationship ระหว่าง subcategories (directed)

```yaml
edges:
  - source: usb-mobile-fans
    target: power-bank
    type: complement
    score: 0.85
    rationale: "พัดลม USB พกพาต้องการแหล่งพลังงานสำรอง"
```

| `type` | ความหมาย | Placement |
|--------|----------|-----------|
| `complement` | ใช้ร่วมกัน | post_advisor |
| `type_alt` | ทางเลือกแทนกันได้ | post_summary |
| `related` | หมวดใกล้เคียง | post_summary |
| `budget_alt` | **computed** จาก same subcategory + non-overlapping price | post_advisor |

> `budget_alt` ไม่มีใน YAML — engine คำนวณ dynamically จาก price range ของบทความจริง

### Anchor Templates

```yaml
anchor_templates:
  complement:
    - "{target_label} ที่ใช้คู่กัน"
    - "ใช้ร่วมกับ {target_label}"

  subcategory_overrides:
    usb-mobile-fans:
      complement:
        - "Power Bank สำหรับชาร์จพัดลม USB"   # ชนะ generic pool
```

Template variables: `{source_label}`, `{target_label}`, `{target_price_range}`, `{target_category_label}`

## Config (`link_config.yaml`)

### Scoring Weights

ต้องรวมได้ 1.0 — validated ที่ startup

```yaml
scoring_weights:
  complement:         0.35
  persona_overlap:    0.20
  use_case_proximity: 0.15
  price_compat:       0.15
  category_match:     0.10
  keyword_diversity:  0.05
  seasonal_intent:    0.00   # Phase 2 slot
  content_performance: 0.00  # Phase 4 slot
  campaign_match:     0.00   # Phase 2 slot
```

### Limits

```yaml
limits:
  max_links_per_article:    4    # hard cap
  max_same_subcategory:     1    # ป้องกัน circular overload
  min_links_to_show:        2    # ซ่อน section ถ้าน้อยกว่า
  min_published_threshold:  5    # cold-start gate
```

### Anchor Rotation

```yaml
anchor_rotation: "hash"   # "hash" | "round_robin" | "performance"
```

- `hash` — deterministic per (source, target) pair — articles ต่างกันได้ anchor ต่างกัน
- `performance` — Phase 4, CTR-based (slot reserved)

## Pinned Links (`pinned_links.yaml`)

Admin-defined links ที่ bypass algorithm แต่ยัง subject to safety checks

```yaml
pinned:
  - source_article_id: "usb-mobile-fans-ไม่เกิน-500-บาท"
    target_article_id: "power-bank-for-travel"
    link_type: "complement"
    anchor_text: "Power Bank สำหรับพัดลม USB พกพา"
    placement: "post_advisor"
    priority: 1          # ยิ่งเลขน้อยยิ่งแสดงก่อน
    note: "Campaign หน้าร้อน 2026"
    expires_at: null     # null = permanent | "YYYY-MM-DD" = auto-expire
```

Safety checks ที่ยังใช้กับ pinned links:
- target ต้องมี status = 'published'
- ไม่ self-link
- expires_at ไม่ผ่าน

## Signals (`SignalVector`)

| Signal | สูตร | Weight |
|--------|------|--------|
| `complement` | edge.score จาก product_graph.yaml | 0.35 |
| `persona_overlap` | Jaccard(source.personas, target.personas) | 0.20 |
| `use_case_proximity` | Jaccard(source.intent_tags, target.intent_tags) | 0.15 |
| `price_compat` | overlap(price_ranges) / union(price_ranges) | 0.15 |
| `category_match` | 1.0 ถ้า category ตรงกัน | 0.10 |
| `keyword_diversity` | 1 − Jaccard(keyword tokens) | 0.05 |
| `seasonal_intent` | Phase 2 (= 0.0) | 0.00 |
| `content_performance` | Phase 4 (= 0.0) | 0.00 |
| `campaign_match` | Phase 2 (= 0.0) | 0.00 |

## Scoring Formula

```python
raw_score = sum(weight[signal] × signal_value for each signal)

final_score = raw_score
    × (budget_alt_bonus       if is_budget_alt else 1.0)
    × (same_subcategory_penalty if subcategory already used else 1.0)
```

ตัดทิ้ง candidates ที่ `final_score < min_score_threshold`

## Public API

```python
from shopee_engine.knowledge_engine import (
    get_article_links,   # DB convenience wrapper
    compute_links,       # pure function (no DB)
    LinkBundle,
    LinkRecord,
    ArticleProfile,
    SignalVector,
    compute_signals,
    KnowledgeGraph,
)
```

### `compute_links(source, candidates, graph) → LinkBundle`

Pure function — no DB, no rendering. Fully testable.

```python
source     = ArticleProfile(article_id="fans-500", ...)
candidates = [ArticleProfile(...), ...]
graph      = KnowledgeGraph.load()

bundle = compute_links(source, candidates, graph)

if bundle._show:
    for link in bundle.links:
        print(link.link_type, link.anchor_text, link.target_url)
```

### `get_article_links(article_id, con) → LinkBundle`

DB convenience wrapper — loads candidates from DuckDB and calls `compute_links`.

```python
import duckdb
con = duckdb.connect("data/shopee.duckdb", read_only=True)
bundle = get_article_links("usb-mobile-fans-ไม่เกิน-500-บาท", con)
```

### `LinkBundle`

```python
@dataclass
class LinkBundle:
    _show:            bool         # False = ซ่อน section ทั้งหมด
    _reason:          str          # เหตุผลถ้า _show=False
    _candidate_count: int
    _pinned_count:    int
    links:            list[LinkRecord]
```

### `LinkRecord`

```python
@dataclass
class LinkRecord:
    link_type:    str      # "complement" | "budget_alt" | "type_alt" | "related"
    target_id:    str
    target_url:   str
    target_label: str
    anchor_text:  str
    score:        float
    placement:    str      # "post_advisor" | "post_summary"
    pinned:       bool
    signals:      SignalVector
```

## Data Flow

```
link_config.yaml  ──┐
product_graph.yaml ─┤→ KnowledgeGraph.load() [cached singleton]
pinned_links.yaml  ─┘         ↓
                     get_article_links(article_id, con)
                         ↓              ↓
                   _load_profiles()   _resolve_pinned()
                   (from DuckDB)      (from graph.pinned)
                         ↓
                   compute_links(source, candidates, graph)
                         ↓
                   compute_signals() per candidate
                         ↓
                   _weighted_score() + multipliers
                         ↓
                   safety filters + dedup + subcategory cap
                         ↓
                   _select_anchor() per selected link
                         ↓
                   LinkBundle  ← คืนให้ caller
                         ↓
                   article_exporter.py renders to markdown (Phase 3B)
```

## Cold-Start Behavior

เมื่อจำนวน published articles < `min_published_threshold` (default: 5):

```python
bundle._show   = False
bundle._reason = "cold_start: 2 published articles < threshold 5"
bundle.links   = []
```

Caller ต้องตรวจ `bundle._show` ก่อน render เสมอ

## Backward Compatibility

- บทความเก่า: `republish()` → ได้รับ links ใหม่อัตโนมัติ
- URL/slug: ไม่เปลี่ยน (ใช้ `article_id` → canonical)
- Affiliate links: ไม่แตะ (อยู่คนละ section)
- DB schema: ไม่เปลี่ยน

## Extending the Engine

### เพิ่ม node ใหม่
แก้ `product_graph.yaml` → เพิ่ม entry ใน `nodes:` และ `edges:` ที่เกี่ยวข้อง

### เพิ่ม signal ใหม่ (Phase 2+)
1. เพิ่ม field ใน `SignalVector` dataclass (default=0.0)
2. เพิ่ม key ใน `scoring_weights` ใน `link_config.yaml` (ค่า 0.0 จนพร้อม)
3. Implement การคำนวณใน `compute_signals()` ใน `signals.py`
4. เมื่อพร้อมใช้: เพิ่ม weight ใน YAML (ลด weight อื่นให้รวมยังคงเป็น 1.0)

### เพิ่ม link_type ใหม่
1. เพิ่มใน `_VALID_EDGE_TYPES` ใน `graph.py`
2. เพิ่ม anchor pool ใน `anchor_templates:` ใน `product_graph.yaml`
3. กำหนด placement ใน `_POST_ADVISOR_TYPES` หรือ `_POST_SUMMARY_TYPES` ใน `linker.py`

### ClusterBundle (Phase 3D)
`cluster.py` มี stub พร้อม — implement โดยไม่แตะ public API ของ Phase 3A

## Phase Plan

| Phase | งาน | สถานะ |
|-------|-----|-------|
| 3A | Knowledge Engine core — graph, signals, linker, YAML, tests, docs | ✅ Done |
| 3B | Rendering: `build_link_section()` + `article_exporter` integration | Planned |
| 3C | Pinned links expiry logic + `product_graph.yaml` expansion | Planned |
| 3D | Production rollout (≥5 articles) + `ClusterBundle` full implementation | Planned |
