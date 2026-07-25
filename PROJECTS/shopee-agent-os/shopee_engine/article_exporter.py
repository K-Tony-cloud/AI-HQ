"""Export SEO articles from DB to Astro-compatible Markdown files.

Rules:
- Product data, prices, images, and affiliate URLs are rebuilt from DB at export time.
- AI prose sections (บทนำ, คำแนะนำการเลือกซื้อ, บทสรุป) are preserved from content_md.
- Writes atomically via temp-file rename; prevents path traversal.
- Will not overwrite a file belonging to a different article_id.
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from shopee_engine.seo_engine import (
    SEO_ARTICLE_PRODUCTS_TABLE,
    SEO_ARTICLES_TABLE,
    _build_comparison_table,
    _build_product_blocks,
    _connect,
    format_price,
    get_related_articles,
)
from shopee_engine.decision_engine import (
    build_decision_faq,
    build_shopping_advisor,
    get_section_title,
)

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _git_root() -> Path:
    """Resolve the monorepo root from this file's location.

    shopee_engine/ → shopee-agent-os/ → PROJECTS/ → AI-HQ/
    """
    return Path(__file__).resolve().parent.parent.parent.parent


def get_site_path() -> Path:
    """Return the seo-website project directory."""
    env = os.getenv("SEO_SITE_PATH", "")
    if env:
        return Path(env).resolve()
    return _git_root() / "PROJECTS/seo-website"


def get_articles_dir() -> Path:
    return get_site_path() / "src/content/articles"


def get_dist_dir() -> Path:
    return get_site_path() / "dist"


def get_site_url() -> str:
    """Return SITE_URL from env. Raises ValueError if missing or invalid."""
    url = os.getenv("SITE_URL", "").strip()
    if not url:
        raise ValueError("SITE_URL environment variable is not set")
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"SITE_URL must start with http:// or https://, got: {url!r}")
    return url.rstrip("/")


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def _sanitize_slug(slug: str) -> str:
    """Verify slug is safe as a filename. Raises on traversal or bad chars."""
    slug = slug.strip()
    if not slug or ".." in slug or "/" in slug or "\\" in slug:
        raise ValueError(f"Unsafe slug: {slug!r}")
    if re.search(r'[<>:"|?*\x00-\x1f]', slug):
        raise ValueError(f"Slug contains illegal characters: {slug!r}")
    return slug


def _safe_article_path(article_id: str, articles_dir: Path) -> Path:
    """Return the target .md path and verify it stays inside articles_dir."""
    safe_id = _sanitize_slug(article_id)
    target = (articles_dir / f"{safe_id}.md").resolve()
    if not str(target).startswith(str(articles_dir.resolve())):
        raise ValueError(f"Path traversal detected for article_id: {article_id!r}")
    return target


# ---------------------------------------------------------------------------
# Placeholder / secret detection
# ---------------------------------------------------------------------------

_PLACEHOLDER_PATTERNS = [
    (re.compile(r'\btodo\b', re.IGNORECASE),                    "TODO placeholder"),
    (re.compile(r'\blorem ipsum\b', re.IGNORECASE),             "Lorem ipsum placeholder"),
    (re.compile(r'\bexample\.com\b', re.IGNORECASE),            "example.com placeholder"),
    (re.compile(r'\{ARTICLE_ID\}'),                              "Unresolved {ARTICLE_ID}"),
    (re.compile(r'\bsk-ant-[A-Za-z0-9_-]{10,}'),               "Anthropic API key"),
    (re.compile(r'\bsk-[A-Za-z0-9]{20,}'),                     "OpenAI-style API key"),
    (re.compile(r'/Users/[A-Za-z0-9_.-]+/'),                    "Local absolute path"),
    (re.compile(r'\{\.affiliate-btn\}'),                         "Pandoc {.affiliate-btn} literal"),
    (re.compile(r'href="/[^"]*affiliate[^"]*"'),                 "Internal/relative affiliate path in href"),
    (re.compile(r'href="/seo-'),                                 "Discord command path in href"),
    (re.compile(r'href="/affiliate-'),                           "Internal affiliate route in href"),
    (re.compile(r'href="(\d+)"'),                               "Numeric itemid used as href"),
]


def detect_placeholders(content: str) -> list[str]:
    """Return list of description strings for any placeholder/secret matches."""
    found = []
    for pat, label in _PLACEHOLDER_PATTERNS:
        m = pat.search(content)
        if m:
            found.append(f"{label}: {m.group()[:60]!r}")
    return found


# ---------------------------------------------------------------------------
# Prose extraction from content_md
# ---------------------------------------------------------------------------

_PROSE_SECTIONS = {"บทนำ", "บริบทการซื้อ", "คำแนะนำการเลือกซื้อ", "บทสรุป"}
_DATA_SECTIONS  = {"ตารางเปรียบเทียบ", "แนะนำสินค้า", "คำถามที่พบบ่อย (FAQ)"}

_DISCLOSURE_RE = re.compile(
    r"---\s*\n\s*\*บทความนี้มีลิงก์ Affiliate[^\n]*\n?",
    re.MULTILINE,
)


def _clean_disclosure(text: str) -> str:
    """Strip embedded affiliate disclosure text from prose sections."""
    return _DISCLOSURE_RE.sub("", text).strip()


_HIGHLIGHTS_RE = re.compile(
    r"<!--\s*editorial:product_highlights\s*\n(\{.*?\})\s*-->",
    re.DOTALL,
)


def _extract_product_highlights(content_md: str) -> dict[str, str]:
    """Parse per-product editorial highlights from HTML comment in content_md."""
    import json
    m = _HIGHLIGHTS_RE.search(content_md)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _extract_prose(content_md: str) -> dict[str, str]:
    """Pull AI prose sections from content_md, skip data-driven sections."""
    # Strip YAML frontmatter
    body = content_md
    if body.startswith("---"):
        end = body.find("---", 3)
        if end != -1:
            body = body[end + 3:].lstrip("\n")

    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []

    for line in body.split("\n"):
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current and current in _PROSE_SECTIONS:
                sections[current] = "\n".join(buf).strip()
            current = m.group(1).strip()
            buf = []
        else:
            buf.append(line)

    if current and current in _PROSE_SECTIONS:
        sections[current] = "\n".join(buf).strip()

    return {k: _clean_disclosure(_HIGHLIGHTS_RE.sub("", v)) for k, v in sections.items()}


# ---------------------------------------------------------------------------
# DB product loading (enriched via LEFT JOIN with products table)
# ---------------------------------------------------------------------------

def _load_enriched_products(article_id: str, con) -> list[dict]:
    """Load seo_article_products, enriched with fresh data from products table."""
    df = con.execute(f"""
        SELECT
            ap.rank_in_article,
            ap.product_title       AS title,
            ap.sale_price,
            ap.image_link,
            ap.affiliate_link,
            ap.affiliate_link_type,
            ap.opportunity_score,
            ap.itemid,
            ap.shopid,
            COALESCE(p.price, 0)                AS original_price,
            COALESCE(p.item_sold, 0)            AS item_sold,
            COALESCE(p.item_rating, 0.0)        AS item_rating,
            COALESCE(p.shop_rating, 0.0)        AS shop_rating,
            COALESCE(p.discount_percentage, 0)  AS discount_pct,
            COALESCE(p.product_link, '')        AS product_link
        FROM {SEO_ARTICLE_PRODUCTS_TABLE} ap
        LEFT JOIN products p ON (ap.itemid = p.itemid AND ap.shopid = p.shopid)
        WHERE ap.article_id = ?
          AND ap.product_status != 'not_found'
        ORDER BY ap.rank_in_article ASC
    """, [article_id]).fetchdf()

    results = []
    for _, row in df.iterrows():
        sale_price = int(row.get("sale_price") or 0)
        orig_price = int(row.get("original_price") or 0)
        results.append({
            "title":               str(row.get("title") or ""),
            "itemid":              int(row.get("itemid") or 0),
            "shopid":              int(row.get("shopid") or 0),
            "sale_price":          sale_price,
            "sale_price_fmt":      format_price(sale_price),
            "original_price":      orig_price,
            "original_price_fmt":  format_price(orig_price) if orig_price else "",
            "item_sold":           int(row.get("item_sold") or 0),
            "shop_rating":         float(row.get("shop_rating") or 0),
            "item_rating":         float(row.get("item_rating") or 0),
            "discount_pct":        int(row.get("discount_pct") or 0),
            "image_link":          str(row.get("image_link") or ""),
            "affiliate_link":      str(row.get("affiliate_link") or ""),
            "affiliate_link_type": str(row.get("affiliate_link_type") or "none"),
            "product_link":        str(row.get("product_link") or ""),
            "opportunity_score":   float(row.get("opportunity_score") or 0),
            "category": "",
            "brand":    "",
        })
    return results


# ---------------------------------------------------------------------------
# Frontmatter builder
# ---------------------------------------------------------------------------

def _build_frontmatter(
    article: dict,
    product_ids: list[int],
    as_status: str,
    published_at: str,
    site_url: str,
) -> str:
    def _esc(v: str) -> str:
        return v.replace("\\", "\\\\").replace('"', '\\"')

    article_id   = str(article.get("article_id", ""))
    keyword      = _esc(str(article.get("keyword", "")))
    category     = _esc(str(article.get("category", "") or ""))
    cat_label    = _esc(str(article.get("category_label", "") or ""))
    subcategory  = _esc(str(article.get("subcategory", "") or ""))
    sub_label    = _esc(str(article.get("subcategory_label", "") or ""))
    title        = _esc(str(article.get("title", "")))
    description  = _esc(str(article.get("meta_description", "") or ""))
    created_at   = str(article.get("created_at", ""))
    updated_at   = datetime.now(timezone.utc).isoformat()
    last_sync    = str(article.get("last_product_sync", "") or "")
    disclosure   = "true" if article.get("affiliate_disclosure", True) else "false"
    canonical    = f"{site_url}/{article_id}"
    ids_str      = "[" + ", ".join(str(i) for i in product_ids) + "]"

    lines = [
        "---",
        f'article_id: "{article_id}"',
        f'keyword: "{keyword}"',
        f'category: "{category}"',
        f'category_label: "{cat_label}"',
        f'subcategory: "{subcategory}"',
        f'subcategory_label: "{sub_label}"',
        f'title: "{title}"',
        f'description: "{description}"',
        f"product_ids: {ids_str}",
        f'created_at: "{created_at}"',
        f'updated_at: "{updated_at}"',
    ]
    if last_sync:
        lines.append(f'last_product_sync: "{last_sync}"')
    if published_at:
        lines.append(f'published_at: "{published_at}"')
    lines += [
        f'article_status: "{as_status}"',
        f"affiliate_disclosure: {disclosure}",
        f'canonical: "{canonical}"',
        "---",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Body builder (prose from content_md + data rebuilt from DB products)
# ---------------------------------------------------------------------------

def _build_template_summary(keyword: str, products: list[dict]) -> str:
    """Build a product-specific summary from actual article data. Never returns empty."""
    if not products:
        return f"สินค้าทุกรุ่นในบทความนี้คัดสรรจากข้อมูลจริงบน Shopee เพื่อช่วยผู้ซื้อตัดสินใจได้ง่ายขึ้น"

    count      = len(products)
    by_price   = sorted(products, key=lambda p: p["sale_price"] or 9_999_999)
    by_rating  = sorted(products, key=lambda p: p.get("item_rating") or 0, reverse=True)
    by_sold    = sorted(products, key=lambda p: p.get("item_sold") or 0, reverse=True)

    cheapest   = by_price[0]
    priciest   = by_price[-1]
    top_rated  = by_rating[0]
    top_sold   = by_sold[0]

    price_range = (
        cheapest["sale_price_fmt"]
        if cheapest["sale_price"] == priciest["sale_price"]
        else f"{cheapest['sale_price_fmt']}–{priciest['sale_price_fmt']}"
    )

    para1 = (
        f"ทั้ง {count} รุ่นที่แนะนำในบทความนี้คัดสรรจากยอดขายและรีวิวจริงบน Shopee "
        f"ราคาอยู่ในช่วง {price_range} เหมาะสำหรับ {keyword} หลากหลายงบประมาณ"
    )

    parts: list[str] = []
    if cheapest.get("sale_price") and cheapest is not top_rated:
        parts.append(
            f"สำหรับผู้ที่ต้องการประหยัดงบ **{cheapest['title'][:35]}** "
            f"ราคา {cheapest['sale_price_fmt']} ถือเป็นตัวเลือกที่คุ้มค่าที่สุดในกลุ่มนี้"
        )
    if top_rated.get("item_rating", 0) >= 4.0:
        sold_note = (
            f" และมียอดขายสูงสุด {top_sold['item_sold']:,} ชิ้น"
            if top_sold is top_rated and top_sold.get("item_sold")
            else ""
        )
        parts.append(
            f"**{top_rated['title'][:35]}** ได้คะแนนรีวิวสูงสุดที่ {top_rated['item_rating']:.1f}⭐"
            f"{sold_note} ราคา {top_rated['sale_price_fmt']} "
            f"เหมาะสำหรับผู้ที่เน้นคุณภาพและความน่าเชื่อถือจากผู้ใช้จริง"
        )
    elif top_sold is not cheapest and top_sold.get("item_sold"):
        parts.append(
            f"**{top_sold['title'][:35]}** มียอดขายสูงสุด {top_sold['item_sold']:,} ชิ้น "
            f"ราคา {top_sold['sale_price_fmt']} บ่งบอกว่าเป็นตัวเลือกยอดนิยมในหมู่ผู้ซื้อจริง"
        )

    para2 = (
        " ".join(parts) if parts
        else f"แนะนำให้เปรียบเทียบสเปกและรีวิวของแต่ละรุ่นผ่านลิงก์ดูสินค้าก่อนตัดสินใจ"
    )

    return f"{para1}\n\n{para2}"


def _build_export_body(
    article: dict,
    products: list[dict],
    prose: dict[str, str],
    related_articles: list[dict] | None = None,
) -> str:
    keyword = str(article.get("keyword", ""))

    intro        = prose.get("บทนำ") or f"บทความคัดสรร {keyword} จากข้อมูลจริงบน Shopee"
    buying_guide = prose.get("คำแนะนำการเลือกซื้อ", "")
    # Use stored prose summary only if non-empty; always fall back to product-specific template
    summary      = prose.get("บทสรุป", "") or _build_template_summary(keyword, products)

    # Editorial team sections (new — absent in legacy articles, gracefully empty)
    buying_context = prose.get("บริบทการซื้อ", "")

    # Product highlights from HTML comment in content_md
    product_highlights = _extract_product_highlights(str(article.get("content_md", "")))
    category     = str(article.get("category", ""))
    comp_table   = _build_comparison_table(products)
    prod_blocks  = _build_product_blocks(products, product_highlights=product_highlights)

    # Decision Engine sections
    section_title   = get_section_title(category)
    advisor_body    = build_shopping_advisor(keyword, category, products)
    decision_faq    = build_decision_faq(keyword, category, products)

    buying_context_section = (
        f"## บริบทการซื้อ\n\n{buying_context}\n\n"
        if buying_context else ""
    )
    buying_section = (
        f"\n## คำแนะนำการเลือกซื้อ\n\n{buying_guide}\n"
        if buying_guide else ""
    )
    advisor_section = (
        f"\n## {section_title}\n\n{advisor_body}\n"
        if advisor_body else ""
    )

    # Related articles section — rendered as a nav list before the page ends
    related_section = ""
    if related_articles:
        lines = ["## บทความที่เกี่ยวข้อง"]
        for ra in related_articles:
            ra_id    = ra.get("article_id", "")
            ra_title = ra.get("title") or ra.get("keyword") or ra_id
            lines.append(f"- [{ra_title}](/{ra_id}/)")
        related_section = "\n".join(lines) + "\n\n"

    return (
        f"## บทนำ\n\n{intro}\n\n"
        f"{buying_context_section}"
        f"## ตารางเปรียบเทียบ\n\n{comp_table}\n\n"
        f"## แนะนำสินค้า\n\n{prod_blocks}\n"
        f"{advisor_section}"
        f"{buying_section}"
        f"\n## บทสรุป\n\n{summary}\n\n"
        f"{decision_faq}\n"
        f"{related_section}"
    )


# ---------------------------------------------------------------------------
# File collision guard
# ---------------------------------------------------------------------------

def _check_collision(target: Path, article_id: str) -> str | None:
    """If target file exists, verify it belongs to the same article. Returns error or None."""
    if not target.exists():
        return None
    text = target.read_text(encoding="utf-8")
    m = re.search(r'^article_id:\s*"([^"]+)"', text, re.MULTILINE)
    if m and m.group(1) != article_id:
        return (
            f"File {target.name} already exists and belongs to article "
            f"'{m.group(1)}', not '{article_id}'"
        )
    return None


# ---------------------------------------------------------------------------
# Main export entry point
# ---------------------------------------------------------------------------

def export_article(
    article_id: str,
    as_status: str = "published",
    published_at: str | None = None,
) -> dict:
    """Export article from DB to Astro-compatible Markdown file.

    Returns:
        {success: bool, file_path: str | None, article_id: str, error: str | None}
    """
    articles_dir = get_articles_dir()

    # 0. Validate slug before any DB access (fail fast on path traversal)
    try:
        _safe_article_path(article_id, articles_dir)
    except ValueError as e:
        return _err(article_id, str(e))

    # 1. Load from DB
    con = _connect(read_only=True)
    try:
        art_df = con.execute(
            f"SELECT * FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
        ).fetchdf()
        if art_df.empty:
            con.close()
            return _err(article_id, f"Article '{article_id}' not found")
        article  = art_df.iloc[0].to_dict()
        products = _load_enriched_products(article_id, con)
        con.close()
    except Exception as exc:
        con.close()
        return _err(article_id, str(exc))

    if not products:
        return _err(article_id, "No active products found for this article")

    # 2. Get SITE_URL
    try:
        site_url = get_site_url()
    except ValueError as e:
        return _err(article_id, str(e))

    # 3. Build content
    prose           = _extract_prose(str(article.get("content_md", "")))
    pub_ts          = published_at or datetime.now(timezone.utc).isoformat()
    product_ids     = [p["itemid"] for p in products]
    frontmatter     = _build_frontmatter(article, product_ids, as_status, pub_ts, site_url)
    related_articles = get_related_articles(article_id, limit=4)
    body            = _build_export_body(article, products, prose, related_articles)
    full_content    = frontmatter + "\n" + body

    # 4. Placeholder / secret check
    issues = detect_placeholders(full_content)
    if issues:
        return _err(article_id, "Placeholder/secret detected: " + "; ".join(issues))

    # 5. Safe path resolution
    try:
        target = _safe_article_path(article_id, articles_dir)
    except ValueError as e:
        return _err(article_id, str(e))

    # 6. Collision check
    if err := _check_collision(target, article_id):
        return _err(article_id, err)

    # 7. Atomic write
    articles_dir.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=articles_dir, suffix=".md.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(full_content)
            os.replace(tmp_path, target)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        return _err(article_id, f"Write failed: {exc}")

    return {"success": True, "file_path": str(target), "article_id": article_id, "error": None}


def delete_article_file(article_id: str) -> bool:
    """Delete the exported Markdown file for an article. Returns True if deleted."""
    try:
        target = _safe_article_path(article_id, get_articles_dir())
    except ValueError:
        return False
    if target.exists():
        target.unlink()
        return True
    return False


def generate_preview_body(article_id: str) -> dict:
    """Generate the article body using the same pipeline as export_article, without writing a file.

    Returns {"success": True, "article_id": str, "body": str} or an error dict.
    Used by /seo-preview so it always reflects live DB data (products, affiliate links, prose).
    """
    con = _connect(read_only=True)
    try:
        art_df = con.execute(
            f"SELECT * FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
        ).fetchdf()
        if art_df.empty:
            con.close()
            return _err(article_id, f"Article '{article_id}' not found")
        article  = art_df.iloc[0].to_dict()
        products = _load_enriched_products(article_id, con)
        con.close()
    except Exception as exc:
        con.close()
        return _err(article_id, str(exc))

    if not products:
        return _err(article_id, "No active products found for this article")

    prose = _extract_prose(str(article.get("content_md", "")))
    body  = _build_export_body(article, products, prose)
    return {"success": True, "article_id": article_id, "body": body}


def _err(article_id: str, msg: str) -> dict:
    return {"success": False, "file_path": None, "article_id": article_id, "error": msg}
