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
