# shopee-agent-os

**Shopee Product Intelligence Engine** — วิเคราะห์ Shopee Affiliate Datafeed ขนาด 3–10 GB+  
โดยไม่โหลดข้อมูลทั้งหมดเข้า RAM ด้วย DuckDB

---

## Features

- **Zero RAM overflow** — ใช้ DuckDB streaming อ่าน CSV โดยตรง
- **Fast analytics** — DuckDB columnar engine รัน aggregate query บน 10 GB ใน วินาที
- **Auto column detection** — รับ schema ต่างกันจาก partner หลายเจ้าโดยอัตโนมัติ
- **Rich terminal UI** — ตาราง, progress bar, สี สวยงาม
- **Windows & Mac** — รองรับทั้งสองระบบ

---

## Project Structure

```
shopee-agent-os/
├── shopee_engine/
│   ├── cli.py          # Typer CLI entry point
│   ├── config.py       # Paths + column alias mapping
│   ├── importer.py     # CSV → DuckDB (streaming)
│   ├── search.py       # Full-text product search
│   ├── ranking.py      # Top products by metric
│   └── analytics.py    # Category & commission reports
├── data/               # DuckDB database stored here (gitignored)
├── tests/
└── pyproject.toml
```

---

## Installation

### Prerequisites

- Python 3.12+
- pip หรือ uv (แนะนำ uv — เร็วกว่า)

### Mac / Linux

```bash
# 1. clone หรือ copy โปรเจกต์
cd shopee-agent-os

# 2. สร้าง virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 3. ติดตั้ง dependencies
pip install -e .
```

### Windows (PowerShell)

```powershell
# 1. เปิด PowerShell ใน project directory
cd shopee-agent-os

# 2. สร้าง virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. ติดตั้ง dependencies
pip install -e .
```

### ใช้ uv (เร็วกว่า pip)

```bash
uv venv --python 3.12
source .venv/bin/activate   # Mac/Linux
# หรือ  .venv\Scripts\Activate.ps1  (Windows)
uv pip install -e .
```

---

## Usage

### 1. Import Datafeed

```bash
# ไฟล์ CSV ทั่วไป
shopee import-datafeed /path/to/shopee_affiliate_feed.csv

# ไฟล์ TSV (tab-separated)
shopee import-datafeed /path/to/feed.tsv --delimiter $'\t'

# กำหนด table name เอง
shopee import-datafeed /path/to/feed.csv --table products_th

# Strict mode (หยุดเมื่อ row มีปัญหา)
shopee import-datafeed /path/to/feed.csv --strict
```

### 2. ดู Schema

```bash
# ดู columns, types, และ sample data หลัง import
shopee show-schema

# ดู table อื่น
shopee show-schema --table products_th
```

### 3. Search Products

```bash
# ค้นหาสินค้า
shopee search-products "รองเท้าวิ่ง"

# ค้นหาพร้อม filter
shopee search-products "iphone case" --max-price 500
shopee search-products "เสื้อ" --category "แฟชั่น" --min-rating 4.5
shopee search-products "laptop" --limit 50 --min-price 10000
```

### 4. Top Products

```bash
# Top 20 ขายดีสุด (default)
shopee top-products

# Top 50 commission สูงสุด
shopee top-products --rank-by commission_rate --top 50

# Top rated ในหมวด Electronics
shopee top-products --rank-by rating --category Electronics

# เรียงตามราคา
shopee top-products --rank-by price --top 30
```

Rank-by options: `sales` | `commission_rate` | `rating` | `price`

### 5. Category Report

```bash
# รายงานทุก category
shopee category-report

# Top 30 categories + commission distribution chart
shopee category-report --top 30 --commission
```

### 6. Summary

```bash
# ดู stats รวมของ datafeed
shopee summary
```

---

## Phase 1.5 — Product Discovery Engine

### 7. Find Winning Products

ค้นหาสินค้าน่าทำคอนเทนต์/น่าทำ Affiliate ด้วย multi-filter + opportunity_score

```bash
# filter หลาย criteria พร้อมกัน
shopee find-winning-products --category Face --min-sold 500 --min-shop-rating 4.8 --price-min 50 --price-max 1500 --top 30

# ค้นด้วย keyword + discount
shopee find-winning-products --keyword ลิปสติก --min-discount 20 --top 20

# สินค้า Health ราคาไม่เกิน 1000 ยอดขายดี
shopee find-winning-products --category Health --max-price 1000 --min-sold 200
```

Options:
- `--keyword` — ค้นใน title
- `--category` — filter category (ทุก level)
- `--min-sold` — ขั้นต่ำ item_sold
- `--min-rating` — ขั้นต่ำ item_rating
- `--min-shop-rating` — ขั้นต่ำ shop_rating
- `--price-min` / `--price-max` — ช่วงราคา sale_price
- `--min-discount` — ส่วนลดขั้นต่ำ (%)
- `--top` — จำนวนผลลัพธ์

### 8. Top Opportunities

จัดอันดับสินค้าด้วย opportunity_score:
`item_sold×0.40 + likes×0.15 + discount%×0.15 + shop_rating×100×0.15 + item_rating×100×0.15`

```bash
shopee top-opportunities --top 30
shopee top-opportunities --category Beauty --top 50
```

### 9. Top Viral

หาสินค้าเหมาะทำ TikTok/Reels — ราคาต่ำ, ยอดขายดี, likes สูง, ส่วนลดดี

```bash
shopee top-viral --price-max 500 --top 30
shopee top-viral --category Beauty --price-max 300 --top 20
```

Viral score = `item_sold×0.35 + likes×0.35 + discount%×100×0.30`  
Filter: price ≤ price_max, item_sold ≥ 50

### 10. Top Niche

หา category เฉพาะที่มี avg_sales สูง แต่จำนวนสินค้าน้อย → market gap signal

```bash
shopee top-niche --top 20
shopee top-niche --max-products 1000 --top 30
```

### 11. Daily Picks

สินค้าแนะนำประจำวัน แยกตาม 7 content buckets:
Gadget, Home, Viral TikTok, Mobile Accessories, Mother & Baby, Health, Camping

```bash
shopee daily-picks --top 10
```

### 12. Export Opportunities

Export ผลลัพธ์ไปเป็น CSV โดยตรงจาก DuckDB (ไม่โหลดเข้า RAM)

```bash
shopee export-opportunities --category Face --top 100 --output exports/face_opportunities.csv
shopee export-opportunities --keyword ลิปสติก --top 200 --output exports/lip.csv
shopee export-opportunities --top 500 --output exports/all_top500.csv
```

---

## Phase 4 — Affiliate Performance Engine

### 13. Import Affiliate Report

นำเข้า Shopee Affiliate Report CSV (Orders / Click / Commission) พร้อม auto-detect schema
รองรับหลายไฟล์ — append เข้า DuckDB โดยอัตโนมัติ

```bash
shopee import-affiliate-report reports/orders_june.csv
shopee import-affiliate-report reports/commission_q2.csv
```

### 14. Daily Performance

ดู performance รายวัน: Clicks, Orders, Conv.%, EPC, Revenue, Commission

```bash
shopee daily-performance
shopee daily-performance --days 14
```

### 15. Product Performance

ตาราง ranked สินค้า: Clicks, Orders, Conv.%, EPC, Revenue, Commission

```bash
shopee product-performance --top 50
```

### 16. Top Profit Products

จัดอันดับสินค้าด้วย Commission → EPC → Conversion Rate

```bash
shopee top-profit-products
shopee top-profit-products --top 50
```

### 17. Merge Product Intelligence

Join ข้อมูล affiliate performance กับ 1M product discovery data  
สร้าง `profit_intelligence` view พร้อม `profit_score`

```bash
shopee merge-product-intelligence
```

`profit_score = commission×0.40 + epc×1000×0.30 + conversion_rate×0.30`

### 18. Profit Opportunities

ค้นหาสินค้า high commission + good conversion + low competition

```bash
shopee profit-opportunities --top 30
shopee profit-opportunities --min-commission 50 --min-conversion 2
```

---

## Phase 5 — Affiliate Operator Command Center

### 19. Morning Brief

สรุปภาพรวมประจำเช้า: Top Opportunities, Top Viral, Top Niches, Top Profit

```bash
shopee morning-brief
shopee morning-brief --top 10
```

### 20. Category Brief

วิเคราะห์ category เชิงลึก: Top 20 products + Opportunity Score + Profit Score + Content Angle

```bash
shopee category-brief --category Gadget
shopee category-brief --category Health --top 30
shopee category-brief --category Baby
shopee category-brief --category Camping
shopee category-brief --category Home
shopee category-brief --category Mobile
```

Categories: `Gadget` | `Health` | `Baby` | `Camping` | `Home` | `Mobile` | `Beauty` | `Fashion`

### 21. Trend Watch

หาสินค้าที่กำลัง trending ด้วย 3 สัญญาณ:

- **Social Momentum** — likes ÷ sold ratio สูงผิดปกติ
- **Promo Surge** — ส่วนลด ≥25% + ยอดขาย ≥500
- **New Viral Potential** — likes ≥1,000 แต่ยอดขายยังต่ำ

```bash
shopee trend-watch
```

### 22. Content Worklist

รายการงานคอนเทนต์ประจำวัน พร้อม Priority, Suggested Hook, Format, Platform

```bash
shopee content-worklist
shopee content-worklist --top 30
```

### 23. Executive Summary

สรุปภาพรวมทั้งหมด: Opportunities, Risks, Market Gaps, Viral Candidates, Profit Candidates

```bash
shopee executive-summary
```

### 24. Daily Report

Export รายงานประจำวันเป็น Markdown / HTML / CSV

```bash
shopee daily-report --format markdown
shopee daily-report --format html
shopee daily-report --format csv --output exports/reports
```

---

## Opportunity Score Formula

```
opportunity_score =
  (item_sold          × 0.40)
+ (likes              × 0.15)
+ (discount_%         × 0.15)
+ (shop_rating × 100  × 0.15)
+ (item_rating × 100  × 0.15)   ← falls back to shop_rating if item_rating absent
```

> **Note:** `likes` มีผลสูงมากในข้อมูลจริง (บางสินค้ามี likes 100K+)  
> ปรับ weight ได้ใน `discovery.py → _opportunity_score_expr()`

---

## Column Detection

โปรเจกต์นี้ detect column names อัตโนมัติจาก alias ใน `config.py`  
หาก datafeed ใช้ชื่อ column แปลกออกไป ให้เพิ่ม alias ใน `COLUMN_ALIASES`:

```python
# shopee_engine/config.py
COLUMN_ALIASES = {
    "sales": ["sales", "sold", "monthly_sold", "your_custom_col_name"],
    ...
}
```

ตรวจสอบ column จริงด้วย:

```bash
shopee show-schema
```

---

## Performance Tips

| File Size | RAM ที่ใช้จริง | Import Time (approx) |
|-----------|----------------|----------------------|
| 1 GB      | ~200 MB        | ~30 sec              |
| 5 GB      | ~300 MB        | ~2–3 min             |
| 10 GB     | ~400 MB        | ~5–7 min             |

- DuckDB เก็บข้อมูลใน `data/shopee.duckdb` (columnar format — เล็กกว่า CSV ต้นฉบับ ~2–5x)
- Import ครั้งเดียว query ได้ตลอด — ไม่ต้อง import ซ้ำ
- Query เร็วมากเพราะ DuckDB ทำ predicate pushdown และ parallel scan อัตโนมัติ

---

## Tech Stack

| Library   | Version   | Role                                 |
|-----------|-----------|--------------------------------------|
| Python    | 3.12+     | Runtime                              |
| DuckDB    | ≥ 1.1.0   | Analytical database engine           |
| Pandas    | ≥ 2.2.0   | DataFrame output layer               |
| PyArrow   | ≥ 16.0.0  | Arrow IPC / Parquet support          |
| Rich      | ≥ 13.7.0  | Terminal UI (tables, progress, color)|
| Typer     | ≥ 0.12.0  | CLI framework                        |
