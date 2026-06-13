"""
Bulk-generate 50 content packs and store in queue.
Pulls top-50 products by opportunity score directly from DuckDB,
then calls queue_add for each via the content engine.
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import duckdb
from shopee_engine.config import config, build_column_map
from shopee_engine.content_engine import queue_add

def get_top_keywords(n: int = 50) -> list[str]:
    con = duckdb.connect(str(config.db_path), read_only=True)
    cols = [r[0] for r in con.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='products'"
    ).fetchall()]
    col_map = build_column_map(cols)
    lower_map = {c.lower(): c for c in cols}

    name_col  = col_map.get("product_name") or (cols[1] if len(cols) > 1 else cols[0])
    sold_col  = col_map.get("sales")
    likes_col = lower_map.get("like") or lower_map.get("likes")
    disc_col  = col_map.get("discount")
    shop_r    = col_map.get("shop_rating")
    item_r    = col_map.get("rating")

    def s(c): return f'COALESCE(TRY_CAST("{c}" AS DOUBLE), 0.0)'

    opp = (
        f'{s(sold_col) if sold_col else "0"}*0.40 + '
        f'{s(likes_col) if likes_col else "0"}*0.15 + '
        f'{s(disc_col) if disc_col else "0"}*0.15 + '
        f'{s(shop_r) if shop_r else "0"}*100*0.15 + '
        f'{s(item_r) if item_r else "0"}*100*0.15'
    )

    rows = con.execute(f"""
        SELECT "{name_col}" AS name
        FROM products
        WHERE "{name_col}" IS NOT NULL AND LENGTH("{name_col}") > 5
        ORDER BY {opp} DESC
        LIMIT {n}
    """).fetchall()
    con.close()
    return [str(r[0])[:60] for r in rows if r[0]]


if __name__ == "__main__":
    keywords = get_top_keywords(50)
    print(f"Queuing {len(keywords)} products …\n")

    ok = 0
    for i, kw in enumerate(keywords, 1):
        try:
            row_id = queue_add(kw, provider="template")
            print(f"  [{i:02d}/50] ID={row_id}  ✓  {kw[:55]}")
            ok += 1
        except Exception as e:
            print(f"  [{i:02d}/50] SKIP  {kw[:40]} — {e}")

    print(f"\nDone. {ok}/50 content packs queued.")
