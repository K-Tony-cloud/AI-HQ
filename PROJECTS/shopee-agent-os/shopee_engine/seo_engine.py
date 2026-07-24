"""SEO Affiliate Website Engine — article generation and management.

Generates Thai SEO buying-guide articles from the existing Shopee product
database.  Data rules:
  - All product specs, prices, images, and affiliate links come from the DB.
  - AI (Claude/OpenAI) is used ONLY for: intro paragraph, buying guide prose,
    transition text, and summary.
  - AI must NEVER invent specs, prices, scores, or product info.
  - Template fallback is used when no API key is available.
"""

from __future__ import annotations

import hashlib
import re
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from shopee_engine.config import config
from shopee_engine.taxonomy import _RAW_TO_CANONICAL

# Canonical editorial slug → list of raw DB category strings (derived from taxonomy)
_SLUG_TO_DB_CATS: dict[str, list[str]] = {}
for _raw_cat, _slug in _RAW_TO_CANONICAL.items():
    _SLUG_TO_DB_CATS.setdefault(_slug, []).append(_raw_cat)

# ---------------------------------------------------------------------------
# In-memory idea cache (volatile — valid for 1 hour within same process)
# ---------------------------------------------------------------------------

_idea_cache: dict[str, dict] = {}
_IDEA_TTL = 3600  # seconds

def _evict_ideas() -> None:
    now = time.time()
    expired = [k for k, v in _idea_cache.items() if now - v["ts"] > _IDEA_TTL]
    for k in expired:
        del _idea_cache[k]

def _make_idea_id(cat: str, bucket: int) -> str:
    raw = f"{cat}_{bucket}"
    return "idea-" + hashlib.md5(raw.encode()).hexdigest()[:6]


# ---------------------------------------------------------------------------
# Keyword normalization
# ---------------------------------------------------------------------------

_PRICE_RE       = re.compile(r"ไม่เกิน\s*([\d,]+)\s*บาท", re.IGNORECASE)
_CONNECTOR_RE   = re.compile(r"[&,\-/|]+")
# Spec evidence patterns
_WATT_RE        = re.compile(r"(\d+(?:\.\d+)?)\s*w\b", re.IGNORECASE)
_WATT_KW_RE     = re.compile(r"\b(\d+(?:\.\d+)?)\s*w\b", re.IGNORECASE)
_IPHONE_SPEC_RE = re.compile(
    r"iphone|lightning|mfi|\bios\b|apple|magsafe|ไอโฟน|แอปเปิ้ล", re.IGNORECASE
)
_STOPWORDS_TH   = frozenset([
    "ไม่เกิน", "บาท", "ที่สุด", "ที่ดีที่สุด", "ราคา", "แนะนำ",
    "ยอดนิยม", "สำหรับ", "ผู้เริ่มต้น", "ดีที่สุด", "คุ้มค่า",
    # Grammatical connectors — not product attributes
    "ที่มี", "ที่ไม่มี", "ซึ่งมี", "มี",
    # Editorial-context phrases (question/year/context words)
    "รุ่นไหนดี", "รุ่นไหน", "ดีไหม", "ดีมั้ย", "คุ้มไหม", "น่าซื้อ",
    "อัปเดต", "update", "ล่าสุด", "สรุป", "เปรียบเทียบ", "เลือก",
    # Year prefix (digit year stripped by _YEAR_RE; Thai word guard)
    "ปี",
])
_STOPWORDS_EN   = frozenset(["and", "or", "the", "for", "best", "top"])

# Strip year tokens (e.g. "ปี 2026", "2026", "2569") from keyword before search
_YEAR_RE = re.compile(r"ปี\s*\d{4}|\b(25\d{2}|20\d{2})\b")

# Thai contextual prefixes — compound words starting with these are destination/purpose
# phrases, not product attributes (e.g. "สำหรับเดินทางไปจีน", "เพื่อการท่องเที่ยว")
_CONTEXT_PREFIX_TH = ("สำหรับ", "เพื่อ", "ใช้กับ", "ใช้สำหรับ")

# Synonym groups: lower-case trigger → list of extra search terms
_SYNONYM_MAP: dict[str, list[str]] = {
    "powerbank":          ["power bank", "พาวเวอร์แบงค์", "แบตสำรอง", "แบตเตอรี่สำรอง"],
    "powerbanks":         ["power bank", "powerbank", "พาวเวอร์แบงค์", "แบตสำรอง", "แบตเตอรี่สำรอง"],
    "power bank":         ["powerbank", "พาวเวอร์แบงค์", "แบตสำรอง"],
    "พาวเวอร์แบงค์":     ["powerbank", "power bank", "แบตสำรอง"],
    "แบตสำรอง":          ["powerbank", "power bank", "พาวเวอร์แบงค์"],
    "fan":                ["พัดลม"],
    "mobile fan":         ["พัดลมพกพา", "พัดลม usb", "usb fan"],
    "usb fan":            ["พัดลมพกพา", "พัดลม usb", "mobile fan"],
    "usb & mobile fan":   ["พัดลมพกพา", "พัดลม usb", "usb fan", "mobile fan", "พัดลม"],
    "portable fan":       ["พัดลมพกพา", "พัดลม usb", "usb fan"],
    "พัดลมพกพา":         ["usb fan", "mobile fan", "พัดลม usb"],
    "พัดลม usb":          ["usb fan", "mobile fan", "พัดลมพกพา"],
}

# Normalized synonym map: connector-stripped + de-pluralized keys for robust lookup
def _normalize_phrase(p: str) -> str:
    return re.sub(r" +", " ", _CONNECTOR_RE.sub(" ", p).lower()).strip()

_SYNONYM_MAP_NORM: dict[str, list[str]] = {}
for _k, _v in _SYNONYM_MAP.items():
    _kn = _normalize_phrase(_k)
    _SYNONYM_MAP_NORM[_kn] = _v
    if _kn.endswith("s") and not _kn.endswith("ss"):
        _SYNONYM_MAP_NORM[_kn[:-1]] = _v
del _k, _v, _kn

# Multi-word compound terms that must be preserved as a single token during
# keyword tokenization. Without this, "power bank" splits into ["power", "bank"]
# — two separate AND-groups — and products with "bank" in their description
# (cables, adapters) pass the filter falsely. Sorted longest-first for greedy match.
_COMPOUND_TERMS: list[str] = sorted(
    [k for k in _SYNONYM_MAP if " " in k],
    key=len, reverse=True,
)

# ---------------------------------------------------------------------------
# Product relevance gate
# ---------------------------------------------------------------------------

# Each rule applies when keyword contains a trigger term, then enforces:
#   require_title — at least one must appear in product title (positive gate)
#   block_title   — none may appear in product title (negative gate)
_PRODUCT_TYPE_RULES: list[dict] = [
    {
        "triggers": frozenset([
            "power bank", "powerbank", "พาวเวอร์แบงค์", "แบตสำรอง", "แบตเตอรี่สำรอง",
        ]),
        "require_title": [
            "power bank", "powerbank", "พาวเวอร์แบงค์", "แบตสำรอง", "แบตเตอรี่สำรอง",
        ],
        "block_title": [
            "cable", "สายชาร์จ", "lightning cable", "adapter", "อะแดปเตอร์",
            "หัวชาร์จ", "wall charger",
        ],
        "type_label": "Power Bank",
    },
    {
        "triggers": frozenset(["พัดลม", "fan", "mobile fan", "usb fan", "พัดลมพกพา"]),
        "require_title": ["พัดลม", "fan"],
        "block_title": [],
        "type_label": "พัดลม / Fan",
    },
]


def check_product_relevance(keyword: str, title: str) -> tuple[bool, str]:
    """Return (is_relevant, reason).

    Returns (True, 'ok') when no rule triggers or all gates pass.
    Returns (False, reason) when a product-type rule rejects this product.
    """
    kw_lo    = keyword.lower()
    title_lo = title.lower()

    for rule in _PRODUCT_TYPE_RULES:
        if not any(trigger in kw_lo for trigger in rule["triggers"]):
            continue

        required = rule.get("require_title", [])
        if required and not any(req in title_lo for req in required):
            sample = " หรือ ".join(f"'{r}'" for r in required[:3])
            return False, f"ไม่ใช่ {rule['type_label']} — title ต้องมี: {sample}"

        for bad in rule.get("block_title", []):
            if bad in title_lo:
                return False, (
                    f"title มี '{bad}' — สินค้านี้ไม่ใช่ {rule['type_label']}"
                )

    return True, "ok"


# ---------------------------------------------------------------------------
# Spec requirement extraction + evidence detection
# ---------------------------------------------------------------------------

def _extract_spec_requirements(keyword: str) -> dict:
    """Derive required specs from keyword text.

    Returns:
        min_watt        — minimum wattage required (None if keyword has none)
        iphone_required — True when keyword mentions iPhone/iOS/Lightning
    """
    watts = [float(m) for m in _WATT_KW_RE.findall(keyword)]
    return {
        "min_watt":       max(watts) if watts else None,
        "iphone_required": bool(_IPHONE_SPEC_RE.search(keyword)),
    }


def detect_product_spec_evidence(
    title: str,
    description: str = "",
    attrs: str = "",
) -> dict:
    """Scan title / description / attrs for wattage and iPhone-compatibility evidence.

    Returns:
        watt_max    — highest watt value found (0.0 if none)
        watt_source — "title" | "description" | "attrs" | "none"
        watt_values — all unique watt values found across all fields (sorted desc)
        iphone_compat  — True when any field mentions iPhone compatibility
        iphone_source  — "title" | "description" | "none"
    """
    w_title = [float(m) for m in _WATT_RE.findall(title)]
    w_desc  = [float(m) for m in _WATT_RE.findall(description)]
    w_attrs = [float(m) for m in _WATT_RE.findall(attrs)]
    all_watts = sorted(set(w_title + w_desc + w_attrs), reverse=True)

    if w_title:
        watt_max, watt_source = max(w_title), "title"
    elif w_attrs:
        watt_max, watt_source = max(w_attrs), "attrs"
    elif w_desc:
        watt_max, watt_source = max(w_desc), "description"
    else:
        watt_max, watt_source = 0.0, "none"

    iphone_in_title = bool(_IPHONE_SPEC_RE.search(title))
    iphone_in_desc  = bool(_IPHONE_SPEC_RE.search(description + " " + attrs))
    iphone_compat   = iphone_in_title or iphone_in_desc
    iphone_source   = "title" if iphone_in_title else ("description" if iphone_in_desc else "none")

    return {
        "watt_max":      watt_max,
        "watt_source":   watt_source,
        "watt_values":   all_watts[:8],
        "iphone_compat": iphone_compat,
        "iphone_source": iphone_source,
    }


def check_product_spec(
    keyword: str,
    title: str,
    description: str = "",
    attrs: str = "",
) -> tuple[bool, str, dict]:
    """Validate product against spec requirements derived from keyword.

    Returns (is_valid, reason, evidence_dict).
    is_valid=True when all requirements are met or keyword has no spec requirements.
    """
    reqs     = _extract_spec_requirements(keyword)
    evidence = detect_product_spec_evidence(title, description, attrs)

    if reqs["min_watt"] is not None and evidence["watt_max"] < reqs["min_watt"]:
        return False, (
            f"ไม่มีหลักฐาน ≥{reqs['min_watt']:.0f}W — "
            f"พบสูงสุด {evidence['watt_max']:.0f}W จาก {evidence['watt_source']}"
        ), evidence

    if reqs["iphone_required"] and not evidence["iphone_compat"]:
        return False, "ไม่มีหลักฐานว่าใช้กับ iPhone ได้ (ไม่พบ: iphone/lightning/mfi/ios ใน title หรือ description)", evidence

    return True, "ok", evidence


def _keyword_to_term_groups(keyword: str) -> list[list[str]]:
    """Return term groups for AND/OR SQL construction.

    Each inner list is OR'd (synonyms for one concept).
    The outer list is AND'd (all concept groups must match).

    - Phrase synonym found  → 1 group (synonym terms only, no broad raw tokens)
    - Multi-token, no match → N groups (one per token + its synonyms)

    Compound terms (e.g. "power bank") are preserved as a single token before
    whitespace splitting to prevent false AND-group fragmentation.
    """
    kw_clean = _YEAR_RE.sub(" ", _CONNECTOR_RE.sub(" ", keyword)).strip()

    # Protect known multi-word compounds before whitespace split.
    # "power bank" → "power\x00bank" so it stays one token; restored afterward.
    # Word-boundary guard: only replace when the char right after the match is not
    # alphabetic — prevents "mobile fan" from corrupting "mobile fans" (plural).
    kw_lo = kw_clean.lower()
    _ph_map: dict[str, str] = {}
    kw_protected = kw_lo
    for compound in _COMPOUND_TERMS:
        idx = kw_protected.find(compound)
        if idx < 0:
            continue
        end_idx = idx + len(compound)
        after = kw_protected[end_idx] if end_idx < len(kw_protected) else " "
        if after.isalpha():
            continue  # partial match (e.g. "mobile fans" ≠ "mobile fan")
        ph = compound.replace(" ", "\x00")
        _ph_map[ph] = compound
        kw_protected = kw_protected[:idx] + ph + kw_protected[end_idx:]

    raw_tokens = [t.strip() for t in kw_protected.split() if t.strip()]
    # Restore compound placeholders and apply stopword filter
    tokens = []
    for t in raw_tokens:
        restored = _ph_map.get(t, t)
        if (
            restored not in _STOPWORDS_TH
            and restored not in _STOPWORDS_EN
            and not any(restored.startswith(p) for p in _CONTEXT_PREFIX_TH)
        ):
            tokens.append(restored)
    if not tokens:
        return []

    full_phrase = " ".join(tokens)

    synonyms = _SYNONYM_MAP_NORM.get(full_phrase)
    if synonyms is None and full_phrase.endswith("s") and not full_phrase.endswith("ss"):
        synonyms = _SYNONYM_MAP_NORM.get(full_phrase[:-1])

    if synonyms is not None:
        return [list(dict.fromkeys(synonyms))]

    groups: list[list[str]] = []
    for tok in tokens:
        group = [tok]
        if tok in _SYNONYM_MAP:
            group.extend(_SYNONYM_MAP[tok])
        elif tok.endswith("s") and not tok.endswith("ss") and tok[:-1] in _SYNONYM_MAP:
            group.extend(_SYNONYM_MAP[tok[:-1]])
        groups.append(list(dict.fromkeys(group)))
    return groups


def _extract_price_max(keyword: str) -> tuple[str, int | None]:
    """Strip price constraint and year tokens from keyword; return (cleaned_kw, price_max|None)."""
    m = _PRICE_RE.search(keyword)
    price_max = None
    cleaned   = keyword
    if m:
        price_max = int(m.group(1).replace(",", ""))
        cleaned   = _PRICE_RE.sub("", cleaned)
    cleaned = _YEAR_RE.sub("", cleaned).strip()
    return cleaned, price_max


def _keyword_to_search_terms(keyword: str) -> list[str]:
    """Normalize a keyword string to a deduplicated list of search terms.

    Steps:
      1. Replace connectors (&, -, /) with spaces
      2. Split into tokens
      3. Drop stopwords
      4. Expand synonyms
    """
    kw_clean = _CONNECTOR_RE.sub(" ", keyword).strip()
    tokens = [t.strip().lower() for t in kw_clean.split() if t.strip()]
    tokens = [t for t in tokens if t not in _STOPWORDS_TH and t not in _STOPWORDS_EN]

    # Check full phrase synonyms first (e.g. "usb & mobile fan" as a whole)
    full_phrase = " ".join(tokens)
    all_terms = list(tokens)
    if full_phrase in _SYNONYM_MAP:
        all_terms.extend(_SYNONYM_MAP[full_phrase])
    else:
        for token in tokens:
            if token in _SYNONYM_MAP:
                all_terms.extend(_SYNONYM_MAP[token])

    # Deduplicate preserving order
    seen: set[str] = set()
    result = []
    for t in all_terms:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def normalize_search_terms(keyword: str) -> dict:
    """Public helper: normalize keyword and return display info.

    Returns:
        {
          "cleaned": str,
          "price_max": int | None,
          "terms": list[str],
          "display": str,
        }
    """
    cleaned, price_max = _extract_price_max(keyword)
    terms = _keyword_to_search_terms(cleaned)
    return {
        "cleaned":   cleaned,
        "price_max": price_max,
        "terms":     terms,
        "display":   ", ".join(terms) if terms else cleaned,
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEO_ARTICLES_TABLE          = "seo_articles"
SEO_ARTICLE_PRODUCTS_TABLE  = "seo_article_products"
SEO_ARTICLE_REVISIONS_TABLE = "seo_article_revisions"

ARTICLE_STATUSES = ("draft", "reviewed", "published", "archived")

# Fields that /seo-edit may change; 'intro' and 'summary' map to content_md sections
EDITABLE_FIELDS = frozenset({"title", "intro", "summary", "meta_description", "category", "category_label"})
_PROSE_FIELD_TO_SECTION: dict[str, str] = {"intro": "บทนำ", "summary": "บทสรุป"}

# Only these hostnames carry Shopee affiliate commission tracking
AFFILIATE_HOSTS = {"s.shopee.co.th", "shope.ee"}


def _validate_affiliate_url(url: str) -> str | None:
    """Return an error string if url is not a valid commission-tracked affiliate URL, else None."""
    from urllib.parse import urlparse
    if not url:
        return None  # missing link handled separately
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return f"URL ไม่ถูกต้อง (ไม่มี scheme/host): '{url[:60]}'"
    if parsed.netloc not in AFFILIATE_HOSTS:
        return (
            f"URL ไม่ใช่ affiliate host ที่รองรับ ('{parsed.netloc}' ≠ {sorted(AFFILIATE_HOSTS)}): "
            f"'{url[:60]}'"
        )
    return None

# Allowed status transitions — all others are forbidden
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft":     frozenset({"reviewed"}),
    "reviewed":  frozenset({"draft", "published"}),
    "published": frozenset({"reviewed", "archived"}),
    "archived":  frozenset(),
}


def validate_status_transition(from_status: str, to_status: str) -> dict:
    """Check whether a status transition is permitted.

    Returns {valid: bool, error: str | None}.
    """
    if from_status not in _ALLOWED_TRANSITIONS:
        return {"valid": False, "error": f"Unknown status: '{from_status}'"}
    if to_status not in ARTICLE_STATUSES:
        return {"valid": False, "error": f"Unknown target status: '{to_status}'"}
    if to_status not in _ALLOWED_TRANSITIONS[from_status]:
        allowed_str = ", ".join(sorted(_ALLOWED_TRANSITIONS[from_status])) or "ไม่มี"
        return {
            "valid": False,
            "error": f"ไม่สามารถเปลี่ยนจาก '{from_status}' → '{to_status}' (อนุญาต: {allowed_str})",
        }
    return {"valid": True, "error": None}

SITE_CATEGORIES = [
    "Home & Living",
    "Mobile & Gadgets",
    "Beauty",
    "Health",
    "Mom & Baby",
    "Sports & Outdoors",
    "Food & Beverages",
]

# Keyword templates for building article opportunity ideas
_SEARCH_INTENT_TEMPLATES = [
    "{category} ราคาไม่เกิน {price}",
    "{category} ตัวไหนดี",
    "{category} คุ้มค่าที่สุด",
    "{category} แนะนำ",
    "ซื้อ {category} อะไรดี",
    "{category} สำหรับผู้เริ่มต้น",
    "{category} ยอดนิยม",
]

_PRICE_BUCKETS = [500, 1000, 1500, 2000, 3000, 5000]


# ---------------------------------------------------------------------------
# Price formatting — ALL price display must go through this function
# ---------------------------------------------------------------------------

def format_price(value: int | float | None) -> str:
    """Format a DB price value (already in THB) for display."""
    if value is None:
        return "ไม่ระบุราคา"
    try:
        v = int(value)
        return f"฿{v:,}"
    except (TypeError, ValueError):
        return "ไม่ระบุราคา"


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

def _connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(config.db_path), read_only=read_only)


# ---------------------------------------------------------------------------
# Migration — idempotent, safe to run multiple times
# ---------------------------------------------------------------------------

def run_migration() -> dict[str, str]:
    """Create SEO tables if they do not exist. Returns {table: status}."""
    results: dict[str, str] = {}
    con = _connect(read_only=False)
    try:
        _init_seo_tables(con)
        for table in (SEO_ARTICLES_TABLE, SEO_ARTICLE_PRODUCTS_TABLE):
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            results[table] = f"ok ({count} rows)"
        con.close()
    except Exception as exc:
        con.close()
        raise RuntimeError(f"Migration failed: {exc}") from exc
    return results


def _init_seo_tables(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {SEO_ARTICLES_TABLE} (
            id                  INTEGER PRIMARY KEY,
            article_id          VARCHAR UNIQUE NOT NULL,
            keyword             VARCHAR NOT NULL,
            category            VARCHAR DEFAULT '',
            title               VARCHAR DEFAULT '',
            meta_description    VARCHAR DEFAULT '',
            content_md          TEXT DEFAULT '',
            status              VARCHAR DEFAULT 'draft',
            created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_product_sync   TIMESTAMP,
            affiliate_disclosure BOOLEAN DEFAULT true,
            published_path      VARCHAR DEFAULT '',
            git_commit_hash     VARCHAR DEFAULT ''
        )
    """)
    # Idempotent column additions for future schema evolution
    for col_def in [
        ("article_id",          "VARCHAR"),
        ("affiliate_disclosure","BOOLEAN DEFAULT true"),
        ("published_path",      "VARCHAR DEFAULT ''"),
        ("git_commit_hash",     "VARCHAR DEFAULT ''"),
        ("last_product_sync",   "TIMESTAMP"),
        ("reviewed_at",         "TIMESTAMP"),
        ("review_note",         "VARCHAR DEFAULT ''"),
        ("published_at",        "TIMESTAMP"),
        ("category_label",      "VARCHAR DEFAULT ''"),
        ("subcategory",         "VARCHAR DEFAULT ''"),
        ("subcategory_label",   "VARCHAR DEFAULT ''"),
    ]:
        try:
            con.execute(
                f"ALTER TABLE {SEO_ARTICLES_TABLE} "
                f"ADD COLUMN IF NOT EXISTS {col_def[0]} {col_def[1]}"
            )
        except Exception:
            pass

    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {SEO_ARTICLE_PRODUCTS_TABLE} (
            id                  INTEGER PRIMARY KEY,
            article_id          VARCHAR NOT NULL,
            itemid              BIGINT,
            shopid              BIGINT,
            product_title       VARCHAR DEFAULT '',
            sale_price          BIGINT DEFAULT 0,
            image_link          VARCHAR DEFAULT '',
            affiliate_link      VARCHAR DEFAULT '',
            affiliate_link_type VARCHAR DEFAULT 'none',
            opportunity_score   DOUBLE DEFAULT 0,
            rank_in_article     INTEGER DEFAULT 0,
            product_status      VARCHAR DEFAULT 'active',
            synced_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for col_def in [
        ("affiliate_link_type", "VARCHAR DEFAULT 'none'"),
        ("product_status",      "VARCHAR DEFAULT 'active'"),
        ("synced_at",           "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]:
        try:
            con.execute(
                f"ALTER TABLE {SEO_ARTICLE_PRODUCTS_TABLE} "
                f"ADD COLUMN IF NOT EXISTS {col_def[0]} {col_def[1]}"
            )
        except Exception:
            pass

    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {SEO_ARTICLE_REVISIONS_TABLE} (
            id               INTEGER PRIMARY KEY,
            article_id       VARCHAR NOT NULL,
            revision_number  INTEGER NOT NULL,
            title            VARCHAR DEFAULT '',
            meta_description VARCHAR DEFAULT '',
            content_md       TEXT    DEFAULT '',
            category         VARCHAR DEFAULT '',
            category_label   VARCHAR DEFAULT '',
            status           VARCHAR DEFAULT '',
            saved_by         VARCHAR DEFAULT 'system',
            change_summary   VARCHAR DEFAULT '',
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

def generate_slug(keyword: str) -> str:
    """Generate a URL-safe slug from a Thai/English keyword."""
    slug = keyword.strip().lower()
    slug = re.sub(r"[^฀-๿a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        slug = hashlib.md5(keyword.encode()).hexdigest()[:8]
    return slug


def _unique_article_id(keyword: str, con: duckdb.DuckDBPyConnection) -> str:
    """Return a unique article_id (slug), appending a suffix if needed."""
    base = generate_slug(keyword)
    candidate = base
    suffix = 2
    while True:
        exists = con.execute(
            f"SELECT COUNT(*) FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?",
            [candidate],
        ).fetchone()[0]
        if not exists:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def check_duplicate_draft(keyword: str) -> dict | None:
    """Return existing article dict if any article already exists for this keyword, else None.

    Checks both slug match (article_id) and exact keyword match (case-insensitive).
    """
    slug = generate_slug(keyword)
    con = _connect(read_only=True)
    try:
        row = con.execute(
            f"SELECT article_id, title, keyword, status, updated_at "
            f"FROM {SEO_ARTICLES_TABLE} "
            f"WHERE article_id = ? OR LOWER(keyword) = LOWER(?)",
            [slug, keyword],
        ).fetchdf()
        con.close()
        if row.empty:
            return None
        return row.iloc[0].to_dict()
    except Exception:
        con.close()
        raise


# ---------------------------------------------------------------------------
# Keyword / article opportunity ideas
# ---------------------------------------------------------------------------

def find_keyword_opportunities(
    category: str | None = None,
    top: int = 10,
    min_sales: int = 50,
) -> list[dict]:
    """Return ranked article opportunity ideas from product database.

    Uses opportunity_score calculated from actual product data.
    Does NOT claim to represent Google search volume.
    Label in UI: "article opportunity score".
    """
    con = _connect(read_only=True)
    try:
        cat_filter = ""
        params: list[Any] = []
        if category:
            cat_filter = "AND (global_category1 ILIKE ? OR global_category2 ILIKE ? OR global_category3 ILIKE ?)"
            params = [f"%{category}%", f"%{category}%", f"%{category}%"]

        rows = con.execute(f"""
            SELECT
                title,
                itemid,
                shopid,
                sale_price,
                item_sold,
                "like" AS likes,
                shop_rating,
                item_rating,
                discount_percentage,
                global_category1 AS cat1,
                global_category2 AS cat2,
                global_category3 AS cat3,
                image_link,
                product_link,
                "product_short link" AS datafeed_link,
                (
                    COALESCE(item_sold, 0) * 0.40
                    + COALESCE("like", 0) * 0.15
                    + COALESCE(discount_percentage, 0) * 0.15
                    + COALESCE(shop_rating, 0) * 100 * 0.15
                    + COALESCE(item_rating, 0) * 100 * 0.15
                ) AS opportunity_score
            FROM products
            WHERE item_sold >= ?
            {cat_filter}
            ORDER BY opportunity_score DESC
            LIMIT ?
        """, [min_sales] + params + [top * 5]).fetchdf()
        con.close()
    except Exception:
        con.close()
        raise

    if rows.empty:
        return []

    # Group into keyword ideas by category + price bucket
    ideas: list[dict] = []
    seen_cats: set[str] = set()

    for _, row in rows.iterrows():
        cat = str(row.get("cat3") or row.get("cat2") or row.get("cat1") or "")
        price = int(row.get("sale_price") or 0)

        # Build keyword ideas from category + price
        for bucket in _PRICE_BUCKETS:
            if price <= bucket:
                kw = f"{cat} ไม่เกิน {bucket:,} บาท"
                key = f"{cat}_{bucket}"
                if key not in seen_cats:
                    ideas.append({
                        "keyword":            kw,
                        "category":           cat,
                        "price_bucket":       bucket,
                        "top_product_title":  str(row["title"])[:60],
                        "top_product_price":  format_price(row.get("sale_price")),
                        "opportunity_score":  round(float(row.get("opportunity_score") or 0), 1),
                        "estimated_products": 0,
                    })
                    seen_cats.add(key)
                break

        if len(ideas) >= top:
            break

    # For each idea, count products, fetch top product_ids, and cache
    con2 = _connect(read_only=True)
    try:
        for idea in ideas:
            cat    = idea["category"]
            bucket = idea["price_bucket"]
            rows2 = con2.execute("""
                SELECT itemid,
                    (
                        COALESCE(item_sold, 0) * 0.40
                        + COALESCE("like", 0) * 0.15
                        + COALESCE(discount_percentage, 0) * 0.15
                        + COALESCE(shop_rating, 0) * 100 * 0.15
                        + COALESCE(item_rating, 0) * 100 * 0.15
                    ) AS opp
                FROM products
                WHERE (global_category3 = ? OR global_category2 = ? OR global_category1 = ?)
                AND sale_price <= ?
                AND item_sold >= ?
                ORDER BY opp DESC
                LIMIT 20
            """, [cat, cat, cat, bucket, min_sales]).fetchdf()

            product_ids = rows2["itemid"].tolist() if not rows2.empty else []
            idea["estimated_products"] = len(product_ids)
            idea["product_ids"]        = product_ids
            idea["search_category"]    = cat
            idea["price_max"]          = bucket

            idea_id = _make_idea_id(cat, bucket)
            idea["idea_id"] = idea_id
            _evict_ideas()
            _idea_cache[idea_id] = {
                "category":    cat,
                "price_max":   bucket,
                "product_ids": product_ids,
                "keyword":     idea["keyword"],
                "ts":          time.time(),
            }
    finally:
        con2.close()

    return sorted(ideas, key=lambda x: x["opportunity_score"], reverse=True)[:top]


def suggest_daily_plan(top: int = 5) -> list[dict]:
    """Suggest articles to create today, combining trends + coverage gaps."""
    from shopee_engine.trend_engine import get_today_trends
    trends = get_today_trends()

    seasonal = trends.get("seasonal_theme", "")
    override = trends.get("override", "")

    ideas = find_keyword_opportunities(top=top * 3)

    boost_keywords: list[str] = []
    for item in [override, seasonal]:
        if item:
            boost_keywords.append(str(item).lower())

    def _score(idea: dict) -> float:
        base = idea["opportunity_score"]
        for bk in boost_keywords:
            if bk and bk in idea["keyword"].lower():
                base *= 1.5
        return base

    ideas.sort(key=_score, reverse=True)

    plan = []
    for idea in ideas[:top]:
        article_title = f"{idea['estimated_products']} {idea['category']} ไม่เกิน {idea['price_bucket']:,} บาท ที่ดีที่สุด"
        plan.append({
            **idea,
            "suggested_title": article_title,
            "seasonal_relevance": bool(boost_keywords),
        })

    return plan


# ---------------------------------------------------------------------------
# Affiliate link resolution
# ---------------------------------------------------------------------------

def _get_affiliate_lookup() -> dict[str, dict]:
    """Return {product_link: {affiliate_link, link_type}} from affiliate_products."""
    try:
        from shopee_engine.affiliate_products_engine import get_all_affiliate_products
        raw = get_all_affiliate_products()  # {product_link: affiliate_short_url}
        return {k: {"affiliate_link": v, "link_type": "confirmed"} for k, v in raw.items()}
    except Exception:
        return {}


def _resolve_affiliate_link(
    product_link: str,
    datafeed_short_link: str | None,
    lookup: dict[str, dict],
) -> tuple[str, str]:
    """Resolve the best affiliate link for a product.

    Returns (link, link_type) where link_type is:
        'confirmed' — real s.shopee.co.th link from affiliate_products table
        'datafeed'  — shope.ee redirect from products datafeed
        'none'      — no link available
    """
    if product_link in lookup:
        entry = lookup[product_link]
        return entry["affiliate_link"], "confirmed"
    if datafeed_short_link and datafeed_short_link.strip():
        return datafeed_short_link.strip(), "datafeed"
    return "", "none"


# ---------------------------------------------------------------------------
# Product selection for an article
# ---------------------------------------------------------------------------

def fetch_products_for_keyword(
    keyword: str,
    category: str | None = None,
    price_max: int | None = None,
    top: int = 7,
    min_sales: int = 20,
) -> list[dict]:
    """Fetch top products from DB for a given keyword.

    All returned data is from the database — no AI inference.
    """
    con = _connect(read_only=True)
    try:
        parts: list[str] = []
        params: list[Any] = []

        # Extract price from keyword if not supplied explicitly
        cleaned_kw, kw_price = _extract_price_max(keyword) if keyword else (keyword, None)
        if price_max is None:
            price_max = kw_price

        # AND between concept groups, OR within each group's synonym terms.
        # Single-group (phrase synonym): title-only to prevent description false positives
        # (e.g. "ห้องพัดลม" in a pillow description passing a fan search).
        # Multi-group (individual tokens): title+description so less-specific terms cast
        # a wider net across both fields.
        term_groups = _keyword_to_term_groups(cleaned_kw) if cleaned_kw else []
        title_only = len(term_groups) == 1
        for group in term_groups:
            or_conditions = []
            for term in group:
                if title_only:
                    or_conditions.append("title ILIKE ?")
                    params.append(f"%{term}%")
                else:
                    or_conditions.append("(title ILIKE ? OR description ILIKE ?)")
                    params.extend([f"%{term}%", f"%{term}%"])
            parts.append(f"({' OR '.join(or_conditions)})")

        if category:
            db_cats = _SLUG_TO_DB_CATS.get(category)
            if db_cats:
                # Known editorial slug → exact match against DB category values
                ph = ", ".join("?" * len(db_cats))
                parts.append(
                    f"(global_category1 IN ({ph}) OR global_category2 IN ({ph}) OR global_category3 IN ({ph}))"
                )
                params.extend(db_cats * 3)
            else:
                # Raw DB category or subcategory — fall back to ILIKE
                parts.append("(global_category1 ILIKE ? OR global_category2 ILIKE ? OR global_category3 ILIKE ?)")
                params.extend([f"%{category}%", f"%{category}%", f"%{category}%"])

        if price_max:
            parts.append("sale_price <= ?")
            params.append(price_max)

        where = f"WHERE item_sold >= ? AND {' AND '.join(parts)}" if parts else "WHERE item_sold >= ?"
        params_final = [min_sales] + params

        rows = con.execute(f"""
            SELECT
                title,
                itemid,
                shopid,
                sale_price,
                price AS original_price,
                item_sold,
                "like" AS likes,
                shop_rating,
                item_rating,
                discount_percentage,
                global_category1 AS cat1,
                global_category2 AS cat2,
                global_category3 AS cat3,
                global_brand AS brand,
                image_link,
                product_link,
                "product_short link" AS datafeed_link,
                description,
                (
                    COALESCE(item_sold, 0) * 0.40
                    + COALESCE("like", 0) * 0.15
                    + COALESCE(discount_percentage, 0) * 0.15
                    + COALESCE(shop_rating, 0) * 100 * 0.15
                    + COALESCE(item_rating, 0) * 100 * 0.15
                ) AS opportunity_score
            FROM products
            {where}
            ORDER BY opportunity_score DESC
            LIMIT ?
        """, params_final + [top]).fetchdf()
        con.close()
    except Exception:
        con.close()
        raise

    if rows.empty:
        return []

    aff_lookup = _get_affiliate_lookup()
    all_search_terms = [t for g in term_groups for t in g]
    results = []
    for _, row in rows.iterrows():
        title = str(row.get("title") or "")
        desc  = str(row.get("description") or "")

        # Product relevance gate — block wrong product types before adding to results
        relevant, _relevance_reason = check_product_relevance(keyword or cleaned_kw, title)
        if not relevant:
            continue

        # Spec gate — block products that lack spec evidence required by keyword
        spec_ok, _spec_reason, _spec_ev = check_product_spec(keyword or cleaned_kw, title, desc)
        if not spec_ok:
            continue

        # Capacity gate — block products with wrong mAh for capacity keywords (Task 2e)
        _cap_ok, _cap_reason, _cap_ev = check_capacity_relevance(keyword or cleaned_kw, title, desc)
        if not _cap_ok:
            continue

        aff_link, link_type = _resolve_affiliate_link(
            str(row.get("product_link") or ""),
            str(row.get("datafeed_link") or ""),
            aff_lookup,
        )
        title_lo = title.lower()
        matched = [t for t in all_search_terms if t.lower() in title_lo]
        match_reason = f"title:{','.join(matched)}" if matched else "desc-only"
        results.append({
            "title":             title,
            "itemid":            int(row.get("itemid") or 0),
            "shopid":            int(row.get("shopid") or 0),
            "sale_price":        int(row.get("sale_price") or 0),
            "sale_price_fmt":    format_price(row.get("sale_price")),
            "original_price":    int(row.get("original_price") or 0),
            "original_price_fmt": format_price(row.get("original_price")),
            "item_sold":         int(row.get("item_sold") or 0),
            "shop_rating":       float(row.get("shop_rating") or 0),
            "item_rating":       float(row.get("item_rating") or 0),
            "discount_pct":      int(row.get("discount_percentage") or 0),
            "category":          str(row.get("cat3") or row.get("cat2") or row.get("cat1") or ""),
            "brand":             str(row.get("brand") or ""),
            "image_link":        str(row.get("image_link") or ""),
            "product_link":      str(row.get("product_link") or ""),
            "affiliate_link":    aff_link,
            "affiliate_link_type": link_type,
            "opportunity_score": round(float(row.get("opportunity_score") or 0), 1),
            "description_raw":   str(row.get("description") or "")[:500],
            "match_reason":      match_reason,
        })

    return results


def fetch_products_by_idea(idea_id: str, top: int = 7) -> list[dict] | None:
    """Fetch products using a cached idea (from find_keyword_opportunities).

    Returns:
        list[dict]  — products found
        None        — idea_id not in cache / expired (caller should ask user to re-run /seo-ideas)
    """
    _evict_ideas()
    cached = _idea_cache.get(idea_id)
    if cached is None:
        return None  # expired or unknown

    product_ids = cached.get("product_ids", [])
    category    = cached.get("category", "")
    price_max   = cached.get("price_max")

    # Primary: fetch by exact itemids selected during /seo-ideas
    if product_ids:
        con = _connect(read_only=True)
        try:
            placeholders = ", ".join(["?"] * len(product_ids[:top * 3]))
            rows = con.execute(f"""
                SELECT
                    title, itemid, shopid, sale_price,
                    price AS original_price,
                    item_sold, "like" AS likes, shop_rating, item_rating,
                    discount_percentage,
                    global_category1 AS cat1, global_category2 AS cat2, global_category3 AS cat3,
                    global_brand AS brand,
                    image_link, product_link,
                    "product_short link" AS datafeed_link, description,
                    (
                        COALESCE(item_sold, 0) * 0.40
                        + COALESCE("like", 0) * 0.15
                        + COALESCE(discount_percentage, 0) * 0.15
                        + COALESCE(shop_rating, 0) * 100 * 0.15
                        + COALESCE(item_rating, 0) * 100 * 0.15
                    ) AS opportunity_score
                FROM products
                WHERE itemid IN ({placeholders})
                ORDER BY opportunity_score DESC
                LIMIT ?
            """, product_ids[:top * 3] + [top]).fetchdf()
            con.close()
        except Exception:
            con.close()
            raise

        if not rows.empty and len(rows) >= 3:
            aff_lookup = _get_affiliate_lookup()
            results = []
            for _, row in rows.iterrows():
                aff_link, link_type = _resolve_affiliate_link(
                    str(row.get("product_link") or ""),
                    str(row.get("datafeed_link") or ""),
                    aff_lookup,
                )
                results.append({
                    "title":              str(row.get("title") or ""),
                    "itemid":             int(row.get("itemid") or 0),
                    "shopid":             int(row.get("shopid") or 0),
                    "sale_price":         int(row.get("sale_price") or 0),
                    "sale_price_fmt":     format_price(row.get("sale_price")),
                    "original_price":     int(row.get("original_price") or 0),
                    "original_price_fmt": format_price(row.get("original_price")),
                    "item_sold":          int(row.get("item_sold") or 0),
                    "shop_rating":        float(row.get("shop_rating") or 0),
                    "item_rating":        float(row.get("item_rating") or 0),
                    "discount_pct":       int(row.get("discount_percentage") or 0),
                    "category":           str(row.get("cat3") or row.get("cat2") or row.get("cat1") or ""),
                    "brand":              str(row.get("brand") or ""),
                    "image_link":         str(row.get("image_link") or ""),
                    "product_link":       str(row.get("product_link") or ""),
                    "affiliate_link":     aff_link,
                    "affiliate_link_type": link_type,
                    "opportunity_score":  round(float(row.get("opportunity_score") or 0), 1),
                    "description_raw":    str(row.get("description") or "")[:500],
                })
            return results

    # Fallback: use category + price_max query
    return fetch_products_for_keyword(
        keyword="",
        category=category,
        price_max=price_max,
        top=top,
    )


# ---------------------------------------------------------------------------
# Article generation
# ---------------------------------------------------------------------------

def _ai_intro(keyword: str, products: list[dict]) -> str:
    """Generate intro paragraph using AI (or template fallback)."""
    try:
        from shopee_engine.content_engine import call_ai, detect_provider
        provider = detect_provider()
        if provider == "template":
            raise ValueError("no api key")

        top_product = products[0]["title"] if products else keyword
        product_list = "\n".join(
            f"- {p['title']} ({p['sale_price_fmt']})" for p in products[:5]
        )
        prompt = textwrap.dedent(f"""
            เขียนย่อหน้าเปิดบทความ SEO ภาษาไทยสำหรับหัวข้อ: "{keyword}"

            สินค้าที่รีวิวในบทความนี้:
            {product_list}

            กฎสำคัญ:
            - ใช้ภาษาไทยธรรมชาติ ไม่เป็นทางการมากเกินไป
            - ห้ามระบุราคา สเปก หรือข้อมูลสินค้าที่ไม่ได้รับมา
            - ความยาว 2-3 ประโยค
            - เน้น pain point ของผู้อ่าน
            - ห้ามขึ้นต้นด้วย "คุณเคย" หรือ "น่าสนใจ"
        """).strip()

        return call_ai(
            system="คุณเป็นนักเขียน SEO ภาษาไทยที่เขียนเนื้อหาช่วยคนตัดสินใจซื้อสินค้า",
            user_prompt=prompt,
            max_tokens=300,
        )
    except Exception:
        count = len(products)
        return (
            f"หากกำลังมองหา {keyword} อยู่ บทความนี้รวบรวม {count} ตัวเลือก "
            f"ที่คัดสรรจากข้อมูลยอดขายและความนิยมจริงบน Shopee "
            f"เพื่อช่วยให้ตัดสินใจได้ง่ายขึ้น"
        )


def _ai_buying_guide(keyword: str, products: list[dict]) -> str:
    """Generate buying guide section using AI (or template fallback)."""
    try:
        from shopee_engine.content_engine import call_ai, detect_provider
        provider = detect_provider()
        if provider == "template":
            raise ValueError("no api key")

        prompt = textwrap.dedent(f"""
            เขียนคำแนะนำการเลือกซื้อ "{keyword}" สำหรับผู้บริโภคชาวไทย

            กฎสำคัญ:
            - ห้ามระบุหรืออ้างอิงสเปกหรือราคาของสินค้าในรายการที่ให้มา
            - เขียนเป็นหลักการทั่วไปเท่านั้น เช่น ควรดูอะไรก่อนซื้อ
            - ความยาว 3-4 ประโยค
            - ภาษาไทยเป็นธรรมชาติ
        """).strip()

        return call_ai(
            system="คุณเป็นนักเขียน SEO ภาษาไทย",
            user_prompt=prompt,
            max_tokens=400,
        )
    except Exception:
        return (
            f"ก่อนตัดสินใจซื้อ {keyword} ควรพิจารณาจากคะแนนรีวิวผู้ซื้อจริง "
            f"ยอดขายสะสม และเปรียบเทียบราคากับสินค้าในระดับเดียวกัน "
            f"เลือกร้านที่มีคะแนนร้านสูงและมีนโยบายคืนสินค้าที่ชัดเจน"
        )


def _ai_summary(keyword: str, products: list[dict]) -> str:
    """Generate summary using AI (or template fallback)."""
    try:
        from shopee_engine.content_engine import call_ai, detect_provider
        provider = detect_provider()
        if provider == "template":
            raise ValueError("no api key")

        top3 = products[:3]
        names = ", ".join(p["title"][:30] for p in top3)
        prompt = f'เขียนบทสรุปสั้น 2 ประโยคสำหรับบทความ "{keyword}" โดยกล่าวถึงสินค้าที่น่าสนใจ แต่ห้ามระบุราคาหรือสเปกเอง ให้กล่าวถึงชื่อสินค้าได้: {names}'

        return call_ai(
            system="คุณเป็นนักเขียน SEO ภาษาไทย",
            user_prompt=prompt,
            max_tokens=200,
        )
    except Exception:
        return (
            f"ทั้งหมดนี้คือตัวเลือกที่ดีสำหรับ {keyword} ที่คัดมาจากข้อมูลจริงบน Shopee "
            f"คลิกที่ปุ่มดูสินค้าเพื่อตรวจสอบราคาล่าสุดและรายละเอียดก่อนตัดสินใจ"
        )


def _build_comparison_table(products: list[dict]) -> str:
    """Build a markdown comparison table from real product data only."""
    if not products:
        return ""

    lines = [
        "| # | สินค้า | ราคา | ยอดขาย | คะแนน | ส่วนลด |",
        "|---|-------|------|--------|-------|--------|",
    ]
    for i, p in enumerate(products, 1):
        name = p["title"][:40].replace("|", "｜")
        price = p["sale_price_fmt"]
        sold = f'{p["item_sold"]:,}'
        rating = f'{p["item_rating"]:.1f}⭐' if p["item_rating"] else f'{p["shop_rating"]:.1f}⭐'
        disc = f'{p["discount_pct"]}%' if p["discount_pct"] else "-"
        lines.append(f"| {i} | {name} | {price} | {sold} | {rating} | {disc} |")

    return "\n".join(lines)


def _build_product_blocks(
    products: list[dict],
    product_highlights: dict[str, str] | None = None,
) -> str:
    """Build per-product detail blocks with data from DB only.

    product_highlights: optional dict keyed by 1-based string index ("1", "2", ...)
    containing editorial context lines generated by the editorial team (Cipher+Roxi).
    """
    highlights = product_highlights or {}
    blocks = []
    for i, p in enumerate(products, 1):
        name = p["title"]
        price = p["sale_price_fmt"]
        orig = p["original_price_fmt"] if p["original_price"] > p["sale_price"] else ""
        disc = f" (ลด {p['discount_pct']}%)" if p["discount_pct"] else ""
        rating = p["item_rating"] if p["item_rating"] else p["shop_rating"]
        sold = f'{p["item_sold"]:,}'
        aff = p["affiliate_link"]
        img = p["image_link"]

        block = f"### {i}. {name}\n\n"
        if img:
            block += f"![{name}]({img})\n\n"
        block += f"**ราคา:** {price}"
        if orig:
            block += f" ~~{orig}~~"
        block += f"{disc}\n\n"
        block += f"**คะแนน:** {rating:.1f} ⭐ | **ยอดขาย:** {sold} ชิ้น\n\n"

        # Editorial highlight — Cipher+Roxi context line
        highlight = highlights.get(str(i), "").strip()
        if highlight:
            block += f"> {highlight}\n\n"

        cta_url      = aff or p.get("product_link", "")
        is_affiliate = bool(aff)
        if cta_url:
            rel = "sponsored nofollow noopener" if is_affiliate else "nofollow noopener"
            block += (
                f'<a href="{cta_url}" class="affiliate-btn" '
                f'target="_blank" rel="{rel}">'
                f"ดูสินค้าบน Shopee</a>"
            )
            if not is_affiliate:
                block += ' <span class="non-affiliate-note">(ลิงก์ตรง Shopee)</span>'
            block += "\n\n"
        blocks.append(block)

    return "\n---\n\n".join(blocks)


def _build_faq(keyword: str, products: list[dict]) -> str:
    """Build an FAQ section — only factual questions, no invented answers."""
    price_min = min((p["sale_price"] for p in products if p["sale_price"]), default=0)
    price_max = max((p["sale_price"] for p in products if p["sale_price"]), default=0)
    count = len(products)

    lines = [
        "## คำถามที่พบบ่อย (FAQ)\n",
        f"**{keyword} ราคาเริ่มต้นเท่าไหร่?**\n\n"
        f"จากข้อมูลในบทความนี้ ราคาเริ่มต้นอยู่ที่ {format_price(price_min)} และสูงสุดที่ {format_price(price_max)}\n",
        f"**มีตัวเลือกกี่รุ่นในบทความนี้?**\n\nบทความนี้รวบรวม {count} รุ่นที่คัดสรรจากยอดขายและคะแนนรีวิวบน Shopee\n",
        f"**ซื้อ {keyword} ที่ไหนดี?**\n\nสามารถซื้อได้ผ่านลิงก์ Shopee ในบทความนี้ได้เลย มีระบบคุ้มครองผู้ซื้อของ Shopee\n",
    ]
    return "\n".join(lines)


def generate_article_draft(
    keyword: str = "",
    category: str | None = None,
    price_max: int | None = None,
    top_products: int = 5,
    idea_id: str | None = None,
) -> dict:
    """Generate a full SEO article draft and save to seo_articles table.

    Returns:
        {
          "success": bool,
          "article_id": str,
          "title": str,
          "products_count": int,
          "has_confirmed_affiliate": bool,
          "products_without_link": int,
          "ai_used": bool,
          "error": str | None,
        }
    """
    if idea_id:
        # idea_id path: use products selected during /seo-ideas (no keyword text search)
        products = fetch_products_by_idea(idea_id, top=top_products)
        if products is None:
            return {
                "success": False,
                "error": (
                    f"idea_id `{idea_id}` ไม่พบหรือหมดอายุแล้ว\n"
                    "กรุณารัน `/seo-ideas` ใหม่และใช้ idea_id ที่ได้รับ"
                ),
            }
        # Pull keyword + category from cache if not overridden
        cached = _idea_cache.get(idea_id, {})
        if not keyword:
            keyword = cached.get("keyword", cached.get("category", "สินค้า"))
        if not category:
            category = cached.get("category")
    else:
        # keyword path: normalize + OR search
        products = fetch_products_for_keyword(
            keyword=keyword,
            category=category,
            price_max=price_max,
            top=top_products,
        )

    if not products:
        # Show effective search terms, not raw SQL
        info = normalize_search_terms(keyword) if keyword else {}
        terms_display = info.get("display", keyword)
        return {
            "success": False,
            "error": (
                f"ไม่พบสินค้าที่ตรงกับ '{keyword}' ในฐานข้อมูล\n"
                f"Search terms used: {terms_display}"
                if not idea_id else
                f"idea_id `{idea_id}`: สินค้าทั้งหมดถูกลบหรือ affiliate link หาย\n"
                "ลอง `/seo-ideas` ใหม่หรือใช้ `/seo-draft keyword:<คำค้น>`"
            ),
        }

    count = len(products)
    title = f"{count} {keyword} ที่ดีที่สุด (อัปเดต {datetime.now().year})"
    meta_desc = (
        f"รวม {count} {keyword} คัดสรรจากข้อมูลยอดขายจริงบน Shopee "
        f"พร้อมตารางเปรียบเทียบราคาและรีวิว"
    )

    # ── Editorial Team generation (Sonnet, 7-persona single call) ──────────
    # Normalize raw category (e.g. "USB & Mobile Fans") to editorial slug (e.g. "mobile-gadgets")
    _raw_cat_for_editorial = category or (products[0].get("category", "") if products else "")
    _editorial_slug = category or ""
    if _editorial_slug not in _SLUG_TO_DB_CATS:
        from shopee_engine.taxonomy import map_to_canonical as _map
        _mapped = _map(_raw_cat_for_editorial)
        if _mapped:
            _editorial_slug = _mapped[0]

    from shopee_engine.editorial_team import generate_article_content
    editorial = generate_article_content(keyword, _editorial_slug, products)

    if editorial["_success"]:
        intro             = editorial["intro"]
        buying_scenario   = editorial["buying_scenario"]
        for_whom          = editorial["for_whom"]
        not_for_whom      = editorial["not_for_whom"]
        buying_guide      = editorial["buying_guide"]
        product_highlights = editorial["product_highlights"]
        summary           = editorial["summary"]
    else:
        # Fallback to legacy Haiku calls if editorial team fails
        intro             = _ai_intro(keyword, products)
        buying_scenario   = ""
        for_whom          = ""
        not_for_whom      = ""
        buying_guide      = _ai_buying_guide(keyword, products)
        product_highlights = {}
        summary           = _ai_summary(keyword, products)

    comp_table     = _build_comparison_table(products)
    product_blocks = _build_product_blocks(products, product_highlights=product_highlights)
    faq            = _build_faq(keyword, products)

    from shopee_engine.ai_status import get_ai_status
    ai_used = get_ai_status()["active"]

    # Frontmatter
    now_str = datetime.now(timezone.utc).isoformat()
    raw_cat = category or products[0].get("category", "")
    product_ids = [p["itemid"] for p in products]

    from shopee_engine.taxonomy import map_to_canonical, resolve_subcategory, is_canonical, CANONICAL_CATEGORIES
    _canonical = map_to_canonical(raw_cat)
    if _canonical:
        cat_slug, cat_label = _canonical
    elif is_canonical(raw_cat):
        # caller already passed a canonical slug (e.g. "mobile-gadgets") — use directly
        cat_slug, cat_label = raw_cat, CANONICAL_CATEGORIES[raw_cat]
    else:
        # raw Shopee category with no mapping yet — store as-is, review gate will block
        cat_slug, cat_label = raw_cat, raw_cat

    sub_slug, sub_label = resolve_subcategory(raw_cat)

    frontmatter = textwrap.dedent(f"""\
        ---
        article_id: "{{ARTICLE_ID}}"
        keyword: "{keyword}"
        category: "{cat_slug}"
        category_label: "{cat_label}"
        subcategory: "{sub_slug}"
        subcategory_label: "{sub_label}"
        title: "{title}"
        description: "{meta_desc}"
        product_ids: {product_ids}
        created_at: "{now_str}"
        updated_at: "{now_str}"
        last_product_sync: "{now_str}"
        article_status: "draft"
        affiliate_disclosure: true
        ---
    """)

    # Build buying context section (new editorial layer)
    buying_context_parts: list[str] = []
    if buying_scenario:
        buying_context_parts.append(f"## บริบทการซื้อ\n\n{buying_scenario}")
    if for_whom:
        buying_context_parts.append(f"**เหมาะกับ:**\n\n{for_whom}")
    if not_for_whom:
        buying_context_parts.append(f"**อาจไม่ใช่ตัวเลือกที่ดีถ้า:**\n\n{not_for_whom}")
    buying_context_block = ("\n\n".join(buying_context_parts) + "\n\n") if buying_context_parts else ""

    # Store product_highlights as HTML comment for retrieval at export time
    import json as _json
    highlights_comment = (
        f"\n<!-- editorial:product_highlights\n"
        f"{_json.dumps(product_highlights, ensure_ascii=False, indent=2)}\n"
        f"-->\n"
        if product_highlights else ""
    )

    body = f"""\
## บทนำ

{intro}

{buying_context_block}## ตารางเปรียบเทียบ

{comp_table}

## แนะนำสินค้า

{product_blocks}

## คำแนะนำการเลือกซื้อ

{buying_guide}

{faq}

## บทสรุป

{summary}
{highlights_comment}"""

    content_md = frontmatter + "\n" + body

    # Save to DB — atomic transaction; rollback on any INSERT failure
    con = _connect(read_only=False)
    try:
        _init_seo_tables(con)
        article_id = _unique_article_id(keyword, con)

        # Replace placeholder in frontmatter
        content_md = content_md.replace("{ARTICLE_ID}", article_id)

        con.begin()
        try:
            next_id = (con.execute(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {SEO_ARTICLES_TABLE}").fetchone()[0])
            con.execute(f"""
                INSERT INTO {SEO_ARTICLES_TABLE}
                    (id, article_id, keyword, category, category_label,
                     subcategory, subcategory_label,
                     title, meta_description,
                     content_md, status, created_at, updated_at, last_product_sync, affiliate_disclosure)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, true)
            """, [next_id, article_id, keyword, cat_slug, cat_label, sub_slug, sub_label, title, meta_desc, content_md])

            # Save product relationships
            for rank, p in enumerate(products, 1):
                prod_id = con.execute(
                    f"SELECT COALESCE(MAX(id), 0) + 1 FROM {SEO_ARTICLE_PRODUCTS_TABLE}"
                ).fetchone()[0]
                con.execute(f"""
                    INSERT INTO {SEO_ARTICLE_PRODUCTS_TABLE}
                        (id, article_id, itemid, shopid, product_title, sale_price,
                         image_link, affiliate_link, affiliate_link_type,
                         opportunity_score, rank_in_article, product_status, synced_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
                """, [
                    prod_id, article_id,
                    p["itemid"], p["shopid"], p["title"], p["sale_price"],
                    p["image_link"], p["affiliate_link"], p["affiliate_link_type"],
                    p["opportunity_score"], rank,
                ])
            con.commit()
        except Exception:
            con.rollback()
            raise

        con.close()
    except Exception as exc:
        con.close()
        raise RuntimeError(f"Failed to save article draft: {exc}") from exc

    confirmed = sum(1 for p in products if p["affiliate_link_type"] == "confirmed")
    no_link   = sum(1 for p in products if p["affiliate_link_type"] == "none")

    return {
        "success":                 True,
        "article_id":              article_id,
        "title":                   title,
        "keyword":                 keyword,
        "category":                cat_slug,
        "products_count":          count,
        "has_confirmed_affiliate": confirmed > 0,
        "confirmed_links":         confirmed,
        "datafeed_links":          count - confirmed - no_link,
        "products_without_link":   no_link,
        "ai_used":                 ai_used,
        "content_preview":         body[:400],
    }


# ---------------------------------------------------------------------------
# Article management
# ---------------------------------------------------------------------------

def get_article(article_id: str) -> dict | None:
    con = _connect(read_only=True)
    try:
        row = con.execute(
            f"SELECT * FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
        ).fetchdf()
        con.close()
        if row.empty:
            return None
        return row.iloc[0].to_dict()
    except Exception:
        con.close()
        raise


def get_article_product_count(article_id: str) -> int:
    """Return number of products linked to an article."""
    con = _connect(read_only=True)
    try:
        n = con.execute(
            f"SELECT COUNT(*) FROM {SEO_ARTICLE_PRODUCTS_TABLE} WHERE article_id = ?",
            [article_id],
        ).fetchone()[0]
        con.close()
        return int(n)
    except Exception:
        con.close()
        raise


def get_article_link_status(article_id: str) -> dict:
    """Return per-product affiliate link status for a draft article.

    Includes product_url (canonical Shopee URL) so the operator can open the
    product page and generate an affiliate link in the portal.
    """
    con = _connect(read_only=True)
    try:
        article_row = con.execute(
            f"SELECT title, keyword, status FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?",
            [article_id],
        ).fetchone()
        if not article_row:
            con.close()
            return {"success": False, "error": f"Article '{article_id}' not found"}

        article_title, keyword, status = article_row

        products_df = con.execute(
            f"""SELECT rank_in_article, itemid, shopid, product_title,
                       sale_price, affiliate_link, affiliate_link_type
                FROM {SEO_ARTICLE_PRODUCTS_TABLE}
                WHERE article_id = ?
                ORDER BY rank_in_article""",
            [article_id],
        ).fetchdf()
        con.close()
    except Exception as exc:
        con.close()
        return {"success": False, "error": str(exc)}

    products: list[dict] = []
    for _, r in products_df.iterrows():
        itemid = int(r["itemid"])
        shopid = int(r["shopid"])
        link_type = str(r["affiliate_link_type"] or "none")
        products.append({
            "rank":          int(r["rank_in_article"]),
            "itemid":        itemid,
            "shopid":        shopid,
            "product_title": str(r["product_title"] or ""),
            "sale_price":    int(r["sale_price"] or 0),
            "link_type":     link_type,
            "affiliate_link": str(r["affiliate_link"] or ""),
            "product_url":   f"https://shopee.co.th/product/{shopid}/{itemid}",
        })

    confirmed_count = sum(1 for p in products if p["link_type"] == "confirmed")
    datafeed_count  = sum(1 for p in products if p["link_type"] == "datafeed")
    missing_count   = sum(1 for p in products if p["link_type"] == "none")
    total_count     = len(products)

    missing_products = [p for p in products if p["link_type"] != "confirmed"]

    return {
        "success":         True,
        "article_id":      article_id,
        "article_title":   str(article_title or ""),
        "keyword":         str(keyword or ""),
        "status":          str(status or ""),
        "products":        products,
        "confirmed_count": confirmed_count,
        "datafeed_count":  datafeed_count,
        "missing_count":   missing_count,
        "total_count":     total_count,
        "all_confirmed":   confirmed_count == total_count,
        "missing_products": missing_products,
    }


_CCC_BRACKET_RE = re.compile(r"\[(?:[^]]*\+)?(?:3C|CCC)(?:\+[^]]*)?]", re.IGNORECASE)
_CCC_PLAIN_RE   = re.compile(r"\bCCC\b|\b3C\b", re.IGNORECASE)


def _detect_attribute_evidence(title: str, description: str, attribute_re_bracket: "re.Pattern", attribute_re_plain: "re.Pattern") -> dict:
    """Return evidence metadata for a product attribute without claiming verification.

    Returns:
      {
        evidence_source:  'title_bracket' | 'title_mention' | 'description_match' | 'no_evidence',
        evidence_text:    str,              # snippet showing where the term was found
        confidence_note:  str,             # plain-language note for operator
      }
    """
    title_str = title or ""
    desc_str  = description or ""

    # Highest signal: seller explicitly labeled in bracket (e.g. [CCC], [Qi2+CCC])
    m = attribute_re_bracket.search(title_str)
    if m:
        return {
            "evidence_source": "title_bracket",
            "evidence_text":   m.group(0),
            "confidence_note": "พบหลักฐานใน title (seller ระบุไว้ในชื่อสินค้า) — ควรตรวจสอบบนตัวสินค้าก่อนซื้อ",
        }

    # Medium signal: attribute mentioned in title but without bracket
    m = attribute_re_plain.search(title_str)
    if m:
        start = max(0, m.start() - 10)
        snippet = title_str[start : m.end() + 10].strip()
        return {
            "evidence_source": "title_mention",
            "evidence_text":   snippet,
            "confidence_note": "พบหลักฐานใน title — ควรตรวจสอบบนตัวสินค้าก่อนซื้อ",
        }

    # Lower signal: found in description (could be certification, not feature)
    m = attribute_re_plain.search(desc_str)
    if m:
        start = max(0, m.start() - 15)
        snippet = desc_str[start : m.end() + 30].strip()
        return {
            "evidence_source": "description_match",
            "evidence_text":   snippet[:80],
            "confidence_note": "พบในรายละเอียดสินค้า — อาจเป็นใบรับรองหรือคุณสมบัติ ควรตรวจสอบก่อนซื้อ",
        }

    return {
        "evidence_source": "no_evidence",
        "evidence_text":   "",
        "confidence_note": "ไม่พบหลักฐานในข้อมูล datafeed — ควรเปิดหน้าสินค้าตรวจก่อนซื้อ",
    }


def get_products_for_preview(article_id: str) -> list[dict]:
    """Return per-product data for /seo-preview with direct URLs and command templates.

    Each item contains:
      rank, itemid, shopid, title, shop_name, price, image_url,
      affiliate_type, affiliate_status, direct_url, url_status, cmd_template
    """
    con = _connect(read_only=True)
    try:
        # Check which shop-name columns exist in the products table
        _prod_cols = {
            r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='products'"
            ).fetchall()
        }
        _has_shop = "shop_name" in _prod_cols or "seller_name" in _prod_cols
        _has_desc = "description" in _prod_cols
        if _has_shop:
            _name_expr = "COALESCE(" + ", ".join(
                f"p.{c}" for c in ("shop_name", "seller_name") if c in _prod_cols
            ) + ", '') AS shop_name"
        else:
            _name_expr = "'' AS shop_name"
        _desc_expr = "COALESCE(p.description, '') AS description" if _has_desc else "'' AS description"
        _join = "LEFT JOIN products p ON ap.itemid = p.itemid AND ap.shopid = p.shopid" if (_has_shop or _has_desc) else ""
        rows_df = con.execute(f"""
            SELECT ap.rank_in_article, ap.itemid, ap.shopid, ap.product_title,
                   ap.sale_price, ap.image_link, ap.affiliate_link, ap.affiliate_link_type,
                   {_name_expr}, {_desc_expr}
            FROM {SEO_ARTICLE_PRODUCTS_TABLE} ap
            {_join}
            WHERE ap.article_id = ?
            ORDER BY ap.rank_in_article
        """, [article_id]).fetchdf()
    finally:
        con.close()

    if rows_df.empty:
        return []

    _AFF_STATUS = {"confirmed": "confirmed", "datafeed": "datafeed", "none": "missing"}
    _AFF_ICON   = {"confirmed": "✅", "datafeed": "📋", "missing": "❌"}

    products: list[dict] = []
    total = len(rows_df)
    for _, r in rows_df.iterrows():
        itemid    = int(r["itemid"])
        shopid    = int(r["shopid"])
        link_type = str(r["affiliate_link_type"] or "none")
        aff_status = _AFF_STATUS.get(link_type, "missing")

        if shopid > 0:
            direct_url = f"https://shopee.co.th/product/{shopid}/{itemid}"
            url_status = "resolved"
            cmd_template = (
                f"`/affiliate-link-add-product link:<วาง> itemid:{itemid} shopid:{shopid}`"
            )
        else:
            direct_url   = ""
            url_status   = "incomplete"
            cmd_template = f"`/affiliate-link-add-product link:<วาง> itemid:{itemid}`"

        title_str = str(r["product_title"] or "")
        desc_str  = str(r.get("description") or "")
        ccc_ev = _detect_attribute_evidence(
            title_str, desc_str, _CCC_BRACKET_RE, _CCC_PLAIN_RE
        )

        products.append({
            "rank":           int(r["rank_in_article"]),
            "total":          total,
            "itemid":         itemid,
            "shopid":         shopid,
            "title":          title_str,
            "shop_name":      str(r.get("shop_name") or ""),
            "price":          int(r["sale_price"] or 0),
            "image_url":      str(r["image_link"] or ""),
            "affiliate_link": str(r["affiliate_link"] or ""),
            "affiliate_type": link_type,
            "affiliate_status": aff_status,
            "aff_icon":       _AFF_ICON.get(aff_status, "❓"),
            "direct_url":     direct_url,
            "url_status":     url_status,
            "cmd_template":   cmd_template,
            # Attribute evidence — NOT verification of product capability
            "ccc_evidence_source": ccc_ev["evidence_source"],
            "ccc_evidence_text":   ccc_ev["evidence_text"],
            "ccc_confidence_note": ccc_ev["confidence_note"],
        })
    return products


def list_articles(status: str | None = None, limit: int = 20) -> list[dict]:
    con = _connect(read_only=True)
    try:
        if status:
            df = con.execute(
                f"SELECT id, article_id, keyword, category, title, status, created_at, updated_at "
                f"FROM {SEO_ARTICLES_TABLE} WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                [status, limit],
            ).fetchdf()
        else:
            df = con.execute(
                f"SELECT id, article_id, keyword, category, title, status, created_at, updated_at "
                f"FROM {SEO_ARTICLES_TABLE} ORDER BY updated_at DESC LIMIT ?",
                [limit],
            ).fetchdf()
        con.close()
        return df.to_dict("records")
    except Exception:
        con.close()
        raise


def get_article_stats() -> dict:
    con = _connect(read_only=True)
    try:
        df = con.execute(
            f"SELECT status, COUNT(*) AS cnt FROM {SEO_ARTICLES_TABLE} GROUP BY status"
        ).fetchdf()
        product_count = con.execute(
            f"SELECT COUNT(*) FROM {SEO_ARTICLE_PRODUCTS_TABLE}"
        ).fetchone()[0]
        confirmed = con.execute(
            f"SELECT COUNT(*) FROM {SEO_ARTICLE_PRODUCTS_TABLE} WHERE affiliate_link_type = 'confirmed'"
        ).fetchone()[0]
        con.close()
        stats = {row["status"]: int(row["cnt"]) for _, row in df.iterrows()}
        return {
            "draft":              stats.get("draft", 0),
            "reviewed":           stats.get("reviewed", 0),
            "published":          stats.get("published", 0),
            "archived":           stats.get("archived", 0),
            "total_products":     int(product_count),
            "confirmed_links":    int(confirmed),
        }
    except Exception:
        con.close()
        raise


def update_article_status(article_id: str, new_status: str) -> bool:
    if new_status not in ARTICLE_STATUSES:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {ARTICLE_STATUSES}")
    con = _connect(read_only=False)
    try:
        _init_seo_tables(con)
        # DuckDB rowcount is unreliable after UPDATE — check existence first
        exists = con.execute(
            f"SELECT COUNT(*) FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?",
            [article_id],
        ).fetchone()[0]
        if not exists:
            con.close()
            return False
        con.execute(
            f"UPDATE {SEO_ARTICLES_TABLE} SET status = ?, updated_at = CURRENT_TIMESTAMP "
            f"WHERE article_id = ?",
            [new_status, article_id],
        )
        con.close()
        return True
    except Exception:
        con.close()
        raise


def update_published_info(article_id: str, published_path: str, git_hash: str) -> None:
    con = _connect(read_only=False)
    try:
        con.execute(f"""
            UPDATE {SEO_ARTICLES_TABLE}
            SET status = 'published',
                published_path = ?,
                git_commit_hash = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE article_id = ?
        """, [published_path, git_hash, article_id])
        con.close()
    except Exception:
        con.close()
        raise


# ---------------------------------------------------------------------------
# Article validation (pre-publish checks)
# ---------------------------------------------------------------------------

def validate_article_for_publish(article_id: str) -> dict:
    """Run all pre-publish validations. Returns {valid: bool, errors: list, warnings: list}."""
    errors: list[str]   = []
    warnings: list[str] = []

    con = _connect(read_only=True)
    try:
        article = con.execute(
            f"SELECT * FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
        ).fetchdf()

        if article.empty:
            return {"valid": False, "errors": [f"Article '{article_id}' not found"], "warnings": []}

        row = article.iloc[0]
        status   = str(row.get("status") or "")
        title    = str(row.get("title") or "")
        meta     = str(row.get("meta_description") or "")
        content  = str(row.get("content_md") or "")
        category = str(row.get("category") or "")

        from shopee_engine.taxonomy import CANONICAL_CATEGORIES
        if status != "reviewed":
            errors.append(f"Status must be 'reviewed' before publishing (current: '{status}')")
        if not title:
            errors.append("Article title is empty")
        if not category:
            errors.append("Category is not set — cannot generate valid category URL")
        elif category not in CANONICAL_CATEGORIES:
            errors.append(
                f"Category '{category}' is not a canonical site category — "
                f"publishing would generate a 404 category URL. "
                f"Valid slugs: {', '.join(CANONICAL_CATEGORIES.keys())}"
            )
        if not meta:
            warnings.append("Meta description is empty — SEO impact")
        if len(content) < 500:
            errors.append("Article content is too short (< 500 chars)")

        products = con.execute(
            f"SELECT * FROM {SEO_ARTICLE_PRODUCTS_TABLE} WHERE article_id = ?", [article_id]
        ).fetchdf()

        if products.empty:
            errors.append("No products linked to this article")
        else:
            no_link = products[products["affiliate_link"].isna() | (products["affiliate_link"] == "")]
            if not no_link.empty:
                warnings.append(
                    f"{len(no_link)} product(s) have no affiliate link: "
                    + ", ".join(str(r) for r in no_link["product_title"].head(3))
                )
            confirmed_count = int((products["affiliate_link_type"] == "confirmed").sum())
            total_count     = len(products)
            if confirmed_count < total_count:
                missing_df = products[products["affiliate_link_type"] != "confirmed"]
                missing_titles = [str(t)[:40] for t in missing_df["product_title"].tolist()]
                missing_ids    = [str(int(i)) for i in missing_df["itemid"].tolist()]
                names_str = ", ".join(missing_titles[:3])
                if len(missing_titles) > 3:
                    names_str += f" (+{len(missing_titles) - 3} รายการ)"
                errors.append(
                    f"ต้องมี confirmed affiliate link ครบทุกสินค้า ก่อน publish — "
                    f"ขาด {total_count - confirmed_count}/{total_count} รายการ: {names_str}. "
                    f"itemid ที่ขาด: {', '.join(missing_ids)}. "
                    f"ใช้ /affiliate-link-add หรือ /seo-link-status เพื่อดูรายละเอียด"
                )
            # Check URL format for confirmed links
            confirmed_rows = products[products["affiliate_link_type"] == "confirmed"]
            for _, prow in confirmed_rows.iterrows():
                url_err = _validate_affiliate_url(str(prow.get("affiliate_link") or ""))
                if url_err:
                    errors.append(
                        f"itemid {int(prow['itemid'])}: {url_err}"
                    )

        con.close()
    except Exception as exc:
        con.close()
        return {"valid": False, "errors": [str(exc)], "warnings": []}

    return {
        "valid":    len(errors) == 0,
        "errors":   errors,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Pre-review validation (lighter than pre-publish — doesn't gate on "reviewed" status)
# ---------------------------------------------------------------------------

def validate_article_for_review(article_id: str) -> dict:
    """Run checks required before approving an article to 'reviewed' status."""
    errors: list[str]   = []
    warnings: list[str] = []

    con = _connect(read_only=True)
    try:
        article = con.execute(
            f"SELECT * FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
        ).fetchdf()

        if article.empty:
            return {"valid": False, "errors": [f"Article '{article_id}' not found"], "warnings": []}

        row      = article.iloc[0]
        title    = str(row.get("title") or "")
        meta     = str(row.get("meta_description") or "")
        content  = str(row.get("content_md") or "")
        keyword  = str(row.get("keyword") or "")
        category = str(row.get("category") or "")

        from shopee_engine.taxonomy import CANONICAL_CATEGORIES
        if not title:
            errors.append("Title ยังว่างอยู่")
        if not keyword:
            errors.append("Keyword ยังว่างอยู่")
        if not category:
            errors.append("Category ไม่ได้ระบุ — ต้องกำหนด canonical category ก่อน review")
        elif category not in CANONICAL_CATEGORIES:
            errors.append(
                f"Category '{category}' ไม่ใช่ canonical site category — "
                f"ห้าม review/publish จนกว่าจะ map ถูกต้อง. "
                f"Canonical ที่รองรับ: {', '.join(CANONICAL_CATEGORIES.keys())}. "
                f"raw Shopee category ที่มี & หรือ space ไม่สามารถใช้เป็น URL ได้โดยตรง"
            )
        if not meta:
            warnings.append("Meta description ยังว่างอยู่ — กระทบ SEO")
        if len(content) < 500:
            errors.append(f"Content สั้นเกินไป ({len(content)} ตัวอักษร ต้องการอย่างน้อย 500)")

        # JOIN products table for description + attrs (spec checks).
        # Detect available columns dynamically — test DBs may have minimal schemas.
        _prod_cols = {
            r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='products'"
            ).fetchall()
        }
        _has_desc  = "description" in _prod_cols
        _has_attrs = "global_item_attributes" in _prod_cols
        if _prod_cols:
            _desc_expr  = "COALESCE(p.description, '')"            if _has_desc  else "''"
            _attrs_expr = "COALESCE(p.global_item_attributes, '')" if _has_attrs else "''"
            products = con.execute(f"""
                SELECT
                    ap.*,
                    {_desc_expr}  AS _desc,
                    {_attrs_expr} AS _attrs
                FROM {SEO_ARTICLE_PRODUCTS_TABLE} ap
                LEFT JOIN products p ON ap.itemid = p.itemid
                WHERE ap.article_id = ?
            """, [article_id]).fetchdf()
        else:
            products = con.execute(
                f"SELECT * FROM {SEO_ARTICLE_PRODUCTS_TABLE} WHERE article_id = ?", [article_id]
            ).fetchdf()
            products["_desc"]  = ""
            products["_attrs"] = ""

        if products.empty:
            errors.append("ไม่มีสินค้าในบทความ")
        else:
            no_link = products[
                products["affiliate_link"].isna() | (products["affiliate_link"] == "")
            ]
            if not no_link.empty:
                warnings.append(f"{len(no_link)} สินค้าไม่มี affiliate link")
            confirmed_count = int((products["affiliate_link_type"] == "confirmed").sum())
            total_count     = len(products)
            if confirmed_count < total_count:
                missing_df = products[products["affiliate_link_type"] != "confirmed"]
                missing_titles = [str(t)[:40] for t in missing_df["product_title"].tolist()]
                missing_ids    = [str(int(i)) for i in missing_df["itemid"].tolist()]
                names_str = ", ".join(missing_titles[:3])
                if len(missing_titles) > 3:
                    names_str += f" (+{len(missing_titles) - 3} รายการ)"
                errors.append(
                    f"ต้องมี confirmed affiliate link ครบทุกสินค้า ก่อน review — "
                    f"ขาด {total_count - confirmed_count}/{total_count} รายการ: {names_str}. "
                    f"itemid ที่ขาด: {', '.join(missing_ids)}. "
                    f"ใช้ /affiliate-link-add หรือ /seo-link-status เพื่อดูรายละเอียด"
                )
            # Check URL format for confirmed links
            confirmed_rows = products[products["affiliate_link_type"] == "confirmed"]
            for _, prow in confirmed_rows.iterrows():
                url_err = _validate_affiliate_url(str(prow.get("affiliate_link") or ""))
                if url_err:
                    errors.append(
                        f"itemid {int(prow['itemid'])}: {url_err}"
                    )
            # Product relevance gate — block wrong product types
            # Spec gate — block products missing required wattage/iPhone evidence
            for _, prow in products.iterrows():
                ptitle = str(prow.get("product_title") or "")
                pdesc  = str(prow.get("_desc") or "")
                pattrs = str(prow.get("_attrs") or "")
                item_id_str = str(int(prow["itemid"]))

                relevant, rel_reason = check_product_relevance(keyword, ptitle)
                if not relevant:
                    errors.append(
                        f"itemid {item_id_str} ไม่ตรง product type: {rel_reason}. "
                        f"ใช้ /seo-product-remove และ /seo-product-add เพื่อแทนที่สินค้า"
                    )
                    continue  # no point spec-checking a wrong product type

                spec_ok, spec_reason, _ = check_product_spec(keyword, ptitle, pdesc, pattrs)
                if not spec_ok:
                    errors.append(
                        f"itemid {item_id_str} ไม่ผ่าน spec gate: {spec_reason}. "
                        f"ใช้ /seo-product-remove และ /seo-product-add เพื่อแทนที่สินค้า"
                    )

        con.close()
    except Exception as exc:
        con.close()
        return {"valid": False, "errors": [str(exc)], "warnings": []}

    # --- Task 1b: content consistency check (only for draft→reviewed transition) ---
    current_status_r = ""
    try:
        _con_st = _connect(read_only=True)
        _st_row = _con_st.execute(
            f"SELECT status FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
        ).fetchone()
        _con_st.close()
        if _st_row:
            current_status_r = str(_st_row[0] or "")
    except Exception:
        pass

    if current_status_r == "draft":
        try:
            _cc = validate_content_consistency(article_id)
            if not _cc["consistent"]:
                stale_str = ", ".join(_cc["stale_items"][:5])
                errors.append(
                    f"Content มีข้อมูลเก่าที่ไม่ตรงกับ product set ปัจจุบัน — "
                    f"stale items: {stale_str}. "
                    f"ใช้ rebuild_article_content() เพื่อสร้างเนื้อหาใหม่"
                )
        except Exception:
            pass

    # --- Task 2e: capacity relevance gate in review ---
    if not products.empty:
        for _, prow in products.iterrows():
            ptitle = str(prow.get("product_title") or "")
            pdesc  = str(prow.get("_desc") or "")
            pattrs = str(prow.get("_attrs") or "")
            item_id_str = str(int(prow["itemid"]))
            cap_ok, cap_reason, _ = check_capacity_relevance(keyword, ptitle, pdesc, pattrs)
            if not cap_ok:
                errors.append(
                    f"itemid {item_id_str} ไม่ผ่าน capacity gate: {cap_reason}. "
                    f"ใช้ /seo-product-remove และ /seo-product-add เพื่อแทนที่สินค้า"
                )
            elif cap_reason.startswith("warning:"):
                warnings.append(f"itemid {item_id_str}: {cap_reason}")

    # --- Task 3c: duplicate model gate in review ---
    if not products.empty:
        prod_list = [
            {"itemid": int(r["itemid"]), "product_title": str(r.get("product_title") or "")}
            for _, r in products.iterrows()
        ]
        dup_groups = check_duplicate_models(prod_list)
        for grp in dup_groups:
            key   = grp["key"]
            iids  = grp["itemids"]
            errors.append(
                f"Duplicate model detected — key={key}, "
                f"itemids: {iids}. "
                f"ลบ 1 รายการด้วย /seo-product-remove แล้วแทนที่ด้วยสินค้าอื่น"
            )

    # --- Task 4: feature copy guard (warning only) ---
    try:
        _con_art = _connect(read_only=True)
        _content_row = _con_art.execute(
            f"SELECT content_md FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
        ).fetchone()
        _con_art.close()
        if _content_row:
            offenders = check_content_feature_copy(keyword, str(_content_row[0] or ""))
            for phrase in offenders:
                warnings.append(f"content มี phrase ที่ไม่เกี่ยวกับ product type: '{phrase}'")
    except Exception:
        pass

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


# ---------------------------------------------------------------------------
# Article review workflow
# ---------------------------------------------------------------------------

def review_article(article_id: str, action: str, note: str = "") -> dict:
    """Change article status during editorial review.

    action='approve':         draft → reviewed  (runs pre-review validation)
    action='return_to_draft': reviewed → draft   (no validation required)

    Returns {success, action, article_id, from_status, to_status, warnings?, error?}
    """
    if action not in ("approve", "return_to_draft"):
        return {"success": False, "error": f"Invalid action: '{action}'"}

    # Load current status
    con_r = _connect(read_only=True)
    try:
        row = con_r.execute(
            f"SELECT status FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
        ).fetchone()
        con_r.close()
    except Exception as exc:
        con_r.close()
        return {"success": False, "error": str(exc)}

    if not row:
        return {"success": False, "error": f"Article '{article_id}' not found"}

    current_status = row[0]

    # Enforce strict source-status requirements for each action
    if action == "approve":
        if current_status != "draft":
            return {
                "success": False,
                "error": f"approve ใช้ได้เฉพาะ draft → reviewed (status ปัจจุบัน: '{current_status}')",
            }
        to_status = "reviewed"
    else:  # return_to_draft
        if current_status != "reviewed":
            return {
                "success": False,
                "error": f"return_to_draft ใช้ได้เฉพาะ reviewed → draft (status ปัจจุบัน: '{current_status}')",
            }
        to_status = "draft"

    validation_warnings: list[str] = []
    if action == "approve":
        val = validate_article_for_review(article_id)
        if not val["valid"]:
            return {
                "success":  False,
                "blocked":  True,
                "errors":   val["errors"],
                "warnings": val["warnings"],
                "error":    "Validation errors: " + "; ".join(val["errors"]),
            }
        validation_warnings = val.get("warnings", [])

    con_w = _connect(read_only=False)
    try:
        _init_seo_tables(con_w)
        if action == "approve":
            con_w.execute(f"""
                UPDATE {SEO_ARTICLES_TABLE}
                SET status = 'reviewed',
                    reviewed_at = CURRENT_TIMESTAMP,
                    review_note = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE article_id = ?
            """, [note or "", article_id])
        else:
            con_w.execute(f"""
                UPDATE {SEO_ARTICLES_TABLE}
                SET status = 'draft',
                    review_note = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE article_id = ?
            """, [note or "", article_id])
        con_w.close()
    except Exception as exc:
        con_w.close()
        return {"success": False, "error": str(exc)}

    return {
        "success":     True,
        "action":      "approved" if action == "approve" else "returned_to_draft",
        "article_id":  article_id,
        "from_status": current_status,
        "to_status":   to_status,
        "warnings":    validation_warnings,
        "note":        note,
    }


# ---------------------------------------------------------------------------
# Product refresh
# ---------------------------------------------------------------------------

def refresh_article_products(article_id: str) -> dict:
    """Re-sync product prices, images, and affiliate links from current DB.

    Rules:
    - Updates: sale_price, image_link, affiliate_link, affiliate_link_type
    - If product not found in products table: mark product_status='not_found'
    - If out of stock: mark product_status='out_of_stock'
    - NEVER auto-replace products or publish automatically
    """
    con = _connect(read_only=True)
    try:
        article_products = con.execute(
            f"SELECT * FROM {SEO_ARTICLE_PRODUCTS_TABLE} WHERE article_id = ?", [article_id]
        ).fetchdf()
        con.close()
    except Exception:
        con.close()
        raise

    if article_products.empty:
        return {"success": False, "error": "No products found for this article"}

    # Snapshot old link types before refresh
    old_link_types: dict[int, str] = {}
    for _, prod_row in article_products.iterrows():
        iid = int(prod_row.get("itemid") or 0)
        old_link_types[iid] = str(prod_row.get("affiliate_link_type") or "none")

    aff_lookup   = _get_affiliate_lookup()
    updated      = 0
    not_found    = 0
    out_of_stock = 0

    # Collect products that upgrade from datafeed/none → confirmed
    newly_confirmed: list[dict] = []

    con2 = _connect(read_only=False)
    try:
        for _, prod_row in article_products.iterrows():
            itemid = int(prod_row.get("itemid") or 0)
            shopid = int(prod_row.get("shopid") or 0)

            result = con2.execute("""
                SELECT title, sale_price, image_link, product_link,
                       "product_short link" AS datafeed_link, stock
                FROM products
                WHERE itemid = ? AND shopid = ?
                LIMIT 1
            """, [itemid, shopid]).fetchdf()

            if result.empty:
                con2.execute(f"""
                    UPDATE {SEO_ARTICLE_PRODUCTS_TABLE}
                    SET product_status = 'not_found', synced_at = CURRENT_TIMESTAMP
                    WHERE article_id = ? AND itemid = ? AND shopid = ?
                """, [article_id, itemid, shopid])
                not_found += 1
                continue

            p = result.iloc[0]
            stock_val = p.get("stock")
            stock = int(stock_val) if stock_val is not None else 1
            new_status = "out_of_stock" if stock == 0 else "active"
            if stock == 0:
                out_of_stock += 1

            aff_link, link_type = _resolve_affiliate_link(
                str(p.get("product_link") or ""),
                str(p.get("datafeed_link") or ""),
                aff_lookup,
            )

            if link_type == "confirmed" and old_link_types.get(itemid, "none") != "confirmed":
                newly_confirmed.append({
                    "itemid":        itemid,
                    "shopid":        shopid,
                    "product_title": str(prod_row.get("product_title") or ""),
                    "affiliate_link": aff_link,
                })

            con2.execute(f"""
                UPDATE {SEO_ARTICLE_PRODUCTS_TABLE}
                SET sale_price = ?,
                    image_link = ?,
                    affiliate_link = ?,
                    affiliate_link_type = ?,
                    product_status = ?,
                    synced_at = CURRENT_TIMESTAMP
                WHERE article_id = ? AND itemid = ? AND shopid = ?
            """, [
                int(p.get("sale_price") or 0),
                str(p.get("image_link") or ""),
                aff_link, link_type, new_status,
                article_id, itemid, shopid,
            ])
            updated += 1

        # Update last_product_sync on the article
        con2.execute(f"""
            UPDATE {SEO_ARTICLES_TABLE}
            SET last_product_sync = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE article_id = ?
        """, [article_id])
        con2.close()
    except Exception:
        con2.close()
        raise

    needs_review = not_found > 0 or out_of_stock > 0
    return {
        "success":         True,
        "updated":         updated,
        "not_found":       not_found,
        "out_of_stock":    out_of_stock,
        "needs_review":    needs_review,
        "newly_confirmed": newly_confirmed,
        "message":         (
            f"Refreshed {updated} products. "
            + (f"{not_found} not found. " if not_found else "")
            + (f"{out_of_stock} out of stock. " if out_of_stock else "")
            + (f"{len(newly_confirmed)} newly confirmed. " if newly_confirmed else "")
            + ("Manual review required." if needs_review else "All products active.")
        ),
    }


# ---------------------------------------------------------------------------
# Article revision history
# ---------------------------------------------------------------------------

def save_revision(
    article_id: str,
    change_summary: str = "",
    saved_by: str = "system",
) -> int:
    """Snapshot current article state as a new revision. Returns revision_number."""
    article = get_article(article_id)
    if not article:
        raise ValueError(f"Article '{article_id}' not found")

    con = _connect(read_only=False)
    try:
        _init_seo_tables(con)
        last = con.execute(
            f"SELECT COALESCE(MAX(revision_number), 0) FROM {SEO_ARTICLE_REVISIONS_TABLE} "
            f"WHERE article_id = ?",
            [article_id],
        ).fetchone()[0]
        rev_num = int(last) + 1
        next_id = con.execute(
            f"SELECT COALESCE(MAX(id), 0) + 1 FROM {SEO_ARTICLE_REVISIONS_TABLE}"
        ).fetchone()[0]
        con.execute(f"""
            INSERT INTO {SEO_ARTICLE_REVISIONS_TABLE}
                (id, article_id, revision_number, title, meta_description, content_md,
                 category, category_label, status, saved_by, change_summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, [
            next_id, article_id, rev_num,
            str(article.get("title") or ""),
            str(article.get("meta_description") or ""),
            str(article.get("content_md") or ""),
            str(article.get("category") or ""),
            str(article.get("category_label") or ""),
            str(article.get("status") or ""),
            saved_by, change_summary,
        ])
        con.close()
    except Exception:
        con.close()
        raise

    prune_old_revisions(article_id)
    return rev_num


def prune_old_revisions(article_id: str, keep: int = 5) -> int:
    """Delete oldest revisions keeping only the N most recent. Returns count deleted."""
    con = _connect(read_only=False)
    try:
        rows = con.execute(
            f"SELECT revision_number FROM {SEO_ARTICLE_REVISIONS_TABLE} "
            f"WHERE article_id = ? ORDER BY revision_number DESC",
            [article_id],
        ).fetchall()
        if len(rows) <= keep:
            con.close()
            return 0
        to_delete = [r[0] for r in rows[keep:]]
        placeholders = ",".join("?" * len(to_delete))
        con.execute(
            f"DELETE FROM {SEO_ARTICLE_REVISIONS_TABLE} "
            f"WHERE article_id = ? AND revision_number IN ({placeholders})",
            [article_id] + to_delete,
        )
        con.close()
        return len(to_delete)
    except Exception:
        con.close()
        raise


def get_article_history(article_id: str) -> list[dict]:
    """Return revision list for an article, newest first."""
    con = _connect(read_only=True)
    try:
        df = con.execute(f"""
            SELECT revision_number, title, category, status,
                   saved_by, change_summary, created_at
            FROM {SEO_ARTICLE_REVISIONS_TABLE}
            WHERE article_id = ?
            ORDER BY revision_number DESC
        """, [article_id]).fetchdf()
        con.close()
    except Exception:
        con.close()
        raise

    if df.empty:
        return []

    return [
        {
            "revision_number": int(row.get("revision_number") or 0),
            "title":           str(row.get("title") or ""),
            "category":        str(row.get("category") or ""),
            "status":          str(row.get("status") or ""),
            "saved_by":        str(row.get("saved_by") or ""),
            "change_summary":  str(row.get("change_summary") or ""),
            "created_at":      str(row.get("created_at") or "")[:19],
        }
        for _, row in df.iterrows()
    ]


def rollback_article(article_id: str, revision_number: int) -> dict:
    """Restore article to a saved revision. Auto-saves current state first. Demotes to draft."""
    con = _connect(read_only=True)
    try:
        rev_df = con.execute(
            f"SELECT * FROM {SEO_ARTICLE_REVISIONS_TABLE} "
            f"WHERE article_id = ? AND revision_number = ?",
            [article_id, revision_number],
        ).fetchdf()
        con.close()
    except Exception:
        con.close()
        raise

    if rev_df.empty:
        return {
            "success": False,
            "error": f"Revision #{revision_number} ไม่พบสำหรับบทความ '{article_id}'",
        }

    row = rev_df.iloc[0]

    # Auto-save current state before overwriting
    try:
        save_revision(article_id, f"Auto-save before rollback to #{revision_number}", "system")
    except Exception:
        pass  # non-blocking

    con_w = _connect(read_only=False)
    try:
        _init_seo_tables(con_w)
        con_w.execute(f"""
            UPDATE {SEO_ARTICLES_TABLE}
            SET title            = ?,
                meta_description = ?,
                content_md       = ?,
                category         = ?,
                category_label   = ?,
                status           = 'draft',
                updated_at       = CURRENT_TIMESTAMP
            WHERE article_id = ?
        """, [
            str(row.get("title") or ""),
            str(row.get("meta_description") or ""),
            str(row.get("content_md") or ""),
            str(row.get("category") or ""),
            str(row.get("category_label") or ""),
            article_id,
        ])
        con_w.close()
    except Exception:
        con_w.close()
        raise

    return {
        "success":         True,
        "article_id":      article_id,
        "revision_number": revision_number,
        "restored_title":  str(row.get("title") or ""),
        "status_after":    "draft",
        "message":         f"Rolled back to revision #{revision_number}. Status → draft.",
    }


# ---------------------------------------------------------------------------
# Article field editing
# ---------------------------------------------------------------------------

def _update_prose_section(content_md: str, section_name: str, new_text: str) -> str:
    """Replace the body of a ## section in content_md without touching other sections."""
    lines = content_md.split("\n")
    start = None
    end   = None

    for i, line in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(section_name)}\s*$", line):
            start = i
        elif start is not None and re.match(r"^##\s+", line):
            end = i
            break

    if start is not None:
        before = lines[: start + 1]
        after  = lines[end:] if end is not None else []
        return "\n".join(before + ["", new_text, ""] + after)

    # Section absent — insert before FAQ, or at end
    faq_idx = next(
        (i for i, l in enumerate(lines) if re.match(r"^##\s+คำถามที่พบบ่อย", l)),
        None,
    )
    if faq_idx is not None:
        return "\n".join(
            lines[:faq_idx] + [f"## {section_name}", "", new_text, "", ""] + lines[faq_idx:]
        )
    return "\n".join(lines + ["", f"## {section_name}", "", new_text, ""])


def edit_article_field(
    article_id: str,
    field: str,
    value: str,
    editor: str = "discord",
) -> dict:
    """Edit one field in the article DB record. Never edits the generated Markdown file.

    Supported fields: title, intro, summary, meta_description, category, category_label.
    - title: updates column; article_id (slug) is never changed.
    - intro/summary: patches the corresponding ## section inside content_md.
    - category: validated against CANONICAL_CATEGORIES.
    Saves a revision before any change. Updates updated_at.

    Returns {success, article_id, field, old_value, new_value,
             revision_saved, requires_republish, slug_unchanged, error}
    """
    if field not in EDITABLE_FIELDS:
        return {
            "success": False,
            "error": (
                f"Field '{field}' ไม่รองรับ. "
                f"รองรับ: {', '.join(sorted(EDITABLE_FIELDS))}"
            ),
        }

    article = get_article(article_id)
    if not article:
        return {"success": False, "error": f"Article '{article_id}' not found"}

    # Capture old value
    if field in _PROSE_FIELD_TO_SECTION:
        from shopee_engine.article_exporter import _extract_prose
        prose     = _extract_prose(str(article.get("content_md") or ""))
        section   = _PROSE_FIELD_TO_SECTION[field]
        old_value = prose.get(section, "")
    else:
        old_value = str(article.get(field) or "")

    value = value.strip()

    # Field-specific validation
    if field == "title" and not value:
        return {"success": False, "error": "Title ห้ามว่าง"}
    if field == "category" and value:
        from shopee_engine.taxonomy import CANONICAL_CATEGORIES
        if value not in CANONICAL_CATEGORIES:
            return {
                "success": False,
                "error": (
                    f"'{value}' ไม่ใช่ canonical category slug. "
                    f"รองรับ: {', '.join(sorted(CANONICAL_CATEGORIES.keys()))}"
                ),
            }

    # Snapshot current state before any change
    try:
        rev_num = save_revision(article_id, f"Before edit: {field}", editor)
    except Exception as exc:
        return {"success": False, "error": f"Failed to save revision: {exc}"}

    # Apply
    con = _connect(read_only=False)
    try:
        _init_seo_tables(con)
        if field in _PROSE_FIELD_TO_SECTION:
            section     = _PROSE_FIELD_TO_SECTION[field]
            content_md  = str(article.get("content_md") or "")
            new_content = _update_prose_section(content_md, section, value)
            con.execute(
                f"UPDATE {SEO_ARTICLES_TABLE} "
                f"SET content_md = ?, updated_at = CURRENT_TIMESTAMP WHERE article_id = ?",
                [new_content, article_id],
            )
        else:
            # field is validated against EDITABLE_FIELDS whitelist — safe interpolation
            con.execute(
                f"UPDATE {SEO_ARTICLES_TABLE} "
                f"SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE article_id = ?",
                [value, article_id],
            )
        con.close()
    except Exception as exc:
        con.close()
        return {"success": False, "error": str(exc)}

    current_status    = str(article.get("status") or "")
    requires_republish = current_status in ("published", "reviewed")

    return {
        "success":           True,
        "article_id":        article_id,
        "field":             field,
        "old_value":         old_value[:300],
        "new_value":         value[:300],
        "revision_saved":    rev_num,
        "requires_republish": requires_republish,
        "slug_unchanged":    True,
        "editor":            editor,
    }


# ---------------------------------------------------------------------------
# Article product management
# ---------------------------------------------------------------------------

def _demote_if_needed(article_id: str, current_status: str, con) -> bool:
    """Demote article to draft if it was reviewed or published. Returns True if demoted."""
    if current_status in ("reviewed", "published"):
        con.execute(
            f"UPDATE {SEO_ARTICLES_TABLE} "
            f"SET status = 'draft', updated_at = CURRENT_TIMESTAMP WHERE article_id = ?",
            [article_id],
        )
        return True
    con.execute(
        f"UPDATE {SEO_ARTICLES_TABLE} SET updated_at = CURRENT_TIMESTAMP WHERE article_id = ?",
        [article_id],
    )
    return False


def add_product_to_article(
    article_id: str,
    itemid: int,
    rank: int | None = None,
) -> dict:
    """Add a product to an article. Validates existence in products table and non-duplication."""
    article = get_article(article_id)
    if not article:
        return {"success": False, "error": f"Article '{article_id}' not found"}

    con = _connect(read_only=True)
    try:
        product_df = con.execute(
            "SELECT itemid, shopid, title, sale_price, image_link, product_link, "
            '"product_short link" AS datafeed_link '
            "FROM products WHERE itemid = ? LIMIT 1",
            [itemid],
        ).fetchdf()
        if product_df.empty:
            con.close()
            return {"success": False, "error": f"itemid {itemid} ไม่พบในฐานข้อมูลสินค้า"}

        dup = con.execute(
            f"SELECT itemid FROM {SEO_ARTICLE_PRODUCTS_TABLE} "
            f"WHERE article_id = ? AND itemid = ?",
            [article_id, itemid],
        ).fetchone()
        if dup:
            con.close()
            return {"success": False, "error": f"itemid {itemid} มีอยู่ในบทความนี้แล้ว"}

        max_rank = int(
            con.execute(
                f"SELECT COALESCE(MAX(rank_in_article), 0) "
                f"FROM {SEO_ARTICLE_PRODUCTS_TABLE} WHERE article_id = ?",
                [article_id],
            ).fetchone()[0]
        )
        con.close()
    except Exception:
        con.close()
        raise

    p = product_df.iloc[0]
    aff_link, link_type = _resolve_affiliate_link(
        str(p.get("product_link") or ""),
        str(p.get("datafeed_link") or ""),
        _get_affiliate_lookup(),
    )
    target_rank = rank if rank is not None else max_rank + 1

    try:
        rev_num = save_revision(article_id, f"Before add itemid={itemid}", "discord")
    except Exception:
        rev_num = None

    con_w = _connect(read_only=False)
    try:
        _init_seo_tables(con_w)
        next_id = int(
            con_w.execute(
                f"SELECT COALESCE(MAX(id), 0) + 1 FROM {SEO_ARTICLE_PRODUCTS_TABLE}"
            ).fetchone()[0]
        )
        con_w.execute(f"""
            INSERT INTO {SEO_ARTICLE_PRODUCTS_TABLE}
                (id, article_id, itemid, shopid, product_title, sale_price,
                 image_link, affiliate_link, affiliate_link_type,
                 rank_in_article, product_status, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        """, [
            next_id, article_id, int(p["itemid"]), int(p.get("shopid") or 0),
            str(p.get("title") or "")[:200], int(p.get("sale_price") or 0),
            str(p.get("image_link") or ""), aff_link, link_type, target_rank,
        ])
        demoted = _demote_if_needed(article_id, str(article.get("status") or ""), con_w)
        con_w.close()
    except Exception:
        con_w.close()
        raise

    return {
        "success":           True,
        "article_id":        article_id,
        "action":            "add",
        "itemid":            int(p["itemid"]),
        "product_title":     str(p.get("title") or "")[:80],
        "rank_in_article":   target_rank,
        "affiliate_link_type": link_type,
        "demoted_to_draft":  demoted,
        "revision_saved":    rev_num,
    }


def remove_product_from_article(article_id: str, itemid: int) -> dict:
    """Remove a product from an article and re-rank remaining products."""
    article = get_article(article_id)
    if not article:
        return {"success": False, "error": f"Article '{article_id}' not found"}

    con = _connect(read_only=True)
    try:
        target = con.execute(
            f"SELECT id, product_title, rank_in_article FROM {SEO_ARTICLE_PRODUCTS_TABLE} "
            f"WHERE article_id = ? AND itemid = ?",
            [article_id, itemid],
        ).fetchone()
        if not target:
            con.close()
            return {"success": False, "error": f"itemid {itemid} ไม่อยู่ในบทความนี้"}

        count = int(
            con.execute(
                f"SELECT COUNT(*) FROM {SEO_ARTICLE_PRODUCTS_TABLE} WHERE article_id = ?",
                [article_id],
            ).fetchone()[0]
        )
        if count <= 1:
            con.close()
            return {"success": False, "error": "ไม่สามารถลบสินค้าสุดท้ายในบทความได้"}
        con.close()
    except Exception:
        con.close()
        raise

    removed_title = str(target[1] or "")
    removed_rank  = int(target[2] or 0)

    try:
        rev_num = save_revision(article_id, f"Before remove itemid={itemid}", "discord")
    except Exception:
        rev_num = None

    con_w = _connect(read_only=False)
    try:
        _init_seo_tables(con_w)
        con_w.execute(
            f"DELETE FROM {SEO_ARTICLE_PRODUCTS_TABLE} WHERE article_id = ? AND itemid = ?",
            [article_id, itemid],
        )
        remaining = con_w.execute(
            f"SELECT id FROM {SEO_ARTICLE_PRODUCTS_TABLE} "
            f"WHERE article_id = ? ORDER BY rank_in_article ASC",
            [article_id],
        ).fetchall()
        for new_rank, (row_id,) in enumerate(remaining, 1):
            con_w.execute(
                f"UPDATE {SEO_ARTICLE_PRODUCTS_TABLE} "
                f"SET rank_in_article = ? WHERE id = ?",
                [new_rank, row_id],
            )
        demoted = _demote_if_needed(article_id, str(article.get("status") or ""), con_w)
        con_w.close()
    except Exception:
        con_w.close()
        raise

    _mark_content_stale(article_id)
    return {
        "success":        True,
        "article_id":     article_id,
        "action":         "remove",
        "itemid":         itemid,
        "removed_title":  removed_title[:80],
        "removed_rank":   removed_rank,
        "demoted_to_draft": demoted,
        "revision_saved": rev_num,
        "remaining_count": count - 1,
    }


def replace_product_in_article(
    article_id: str,
    old_itemid: int,
    new_itemid: int,
) -> dict:
    """Replace a product with another at the same rank position."""
    if old_itemid == new_itemid:
        return {"success": False, "error": "old_itemid และ new_itemid ต้องไม่เหมือนกัน"}

    article = get_article(article_id)
    if not article:
        return {"success": False, "error": f"Article '{article_id}' not found"}

    con = _connect(read_only=True)
    try:
        old_row = con.execute(
            f"SELECT id, product_title, rank_in_article FROM {SEO_ARTICLE_PRODUCTS_TABLE} "
            f"WHERE article_id = ? AND itemid = ?",
            [article_id, old_itemid],
        ).fetchone()
        if not old_row:
            con.close()
            return {"success": False, "error": f"itemid {old_itemid} ไม่อยู่ในบทความนี้"}

        new_df = con.execute(
            "SELECT itemid, shopid, title, sale_price, image_link, product_link, "
            '"product_short link" AS datafeed_link FROM products WHERE itemid = ? LIMIT 1',
            [new_itemid],
        ).fetchdf()
        if new_df.empty:
            con.close()
            return {"success": False, "error": f"itemid {new_itemid} ไม่พบในฐานข้อมูลสินค้า"}

        dup = con.execute(
            f"SELECT itemid FROM {SEO_ARTICLE_PRODUCTS_TABLE} "
            f"WHERE article_id = ? AND itemid = ?",
            [article_id, new_itemid],
        ).fetchone()
        if dup:
            con.close()
            return {"success": False, "error": f"itemid {new_itemid} มีอยู่ในบทความนี้แล้ว"}
        con.close()
    except Exception:
        con.close()
        raise

    target_rank = int(old_row[2] or 0)
    old_title   = str(old_row[1] or "")
    p = new_df.iloc[0]
    aff_link, link_type = _resolve_affiliate_link(
        str(p.get("product_link") or ""),
        str(p.get("datafeed_link") or ""),
        _get_affiliate_lookup(),
    )

    try:
        rev_num = save_revision(article_id, f"Before replace {old_itemid}→{new_itemid}", "discord")
    except Exception:
        rev_num = None

    con_w = _connect(read_only=False)
    try:
        _init_seo_tables(con_w)
        con_w.execute(
            f"DELETE FROM {SEO_ARTICLE_PRODUCTS_TABLE} WHERE article_id = ? AND itemid = ?",
            [article_id, old_itemid],
        )
        next_id = int(
            con_w.execute(
                f"SELECT COALESCE(MAX(id), 0) + 1 FROM {SEO_ARTICLE_PRODUCTS_TABLE}"
            ).fetchone()[0]
        )
        con_w.execute(f"""
            INSERT INTO {SEO_ARTICLE_PRODUCTS_TABLE}
                (id, article_id, itemid, shopid, product_title, sale_price,
                 image_link, affiliate_link, affiliate_link_type,
                 rank_in_article, product_status, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        """, [
            next_id, article_id, int(p["itemid"]), int(p.get("shopid") or 0),
            str(p.get("title") or "")[:200], int(p.get("sale_price") or 0),
            str(p.get("image_link") or ""), aff_link, link_type, target_rank,
        ])
        demoted = _demote_if_needed(article_id, str(article.get("status") or ""), con_w)
        con_w.close()
    except Exception:
        con_w.close()
        raise

    _mark_content_stale(article_id)
    return {
        "success":           True,
        "article_id":        article_id,
        "action":            "replace",
        "old_itemid":        old_itemid,
        "old_title":         old_title[:80],
        "new_itemid":        int(p["itemid"]),
        "new_title":         str(p.get("title") or "")[:80],
        "rank_in_article":   target_rank,
        "affiliate_link_type": link_type,
        "demoted_to_draft":  demoted,
        "revision_saved":    rev_num,
    }


# ---------------------------------------------------------------------------
# Task 1: Content consistency validation
# ---------------------------------------------------------------------------

_CONTENT_PRICE_RE  = re.compile(r"฿([\d,]+)", re.IGNORECASE)
_CONTENT_BAAT_RE   = re.compile(r"([\d,]+)\s*บาท", re.IGNORECASE)

def validate_content_consistency(article_id: str) -> dict:
    """Check whether content_md references prices/model names not in current product set.

    Returns {"consistent": bool, "stale_items": list[str]}
    """
    con = _connect(read_only=True)
    try:
        article = con.execute(
            f"SELECT content_md FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?",
            [article_id],
        ).fetchone()
        if not article:
            con.close()
            return {"consistent": True, "stale_items": []}

        content_md = str(article[0] or "")

        # Also join with products to get original price (shown as strikethrough in blocks)
        _prod_cols = {
            r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='products'"
            ).fetchall()
        }
        _has_origprc = "price" in _prod_cols
        _orig_expr = "COALESCE(p.price, ap.sale_price)" if _has_origprc else "ap.sale_price"
        products_df = con.execute(f"""
            SELECT ap.product_title, ap.sale_price, {_orig_expr} AS original_price
            FROM {SEO_ARTICLE_PRODUCTS_TABLE} ap
            LEFT JOIN products p ON ap.itemid = p.itemid
            WHERE ap.article_id = ?
        """, [article_id]).fetchdf()
        con.close()
    except Exception:
        con.close()
        raise

    if products_df.empty:
        return {"consistent": True, "stale_items": []}

    # Strip frontmatter — only check the body
    body = content_md
    if content_md.startswith("---"):
        end_fm = content_md.find("\n---", 3)
        if end_fm != -1:
            body = content_md[end_fm + 4:]

    # Build sets of current product prices and model codes (include original prices for strikethrough)
    current_prices: set[int] = set()
    for _, row in products_df.iterrows():
        for price_col in ("sale_price", "original_price"):
            price = row.get(price_col)
            if price is not None:
                try:
                    current_prices.add(int(price))
                except (TypeError, ValueError):
                    pass

    # Extract model codes from product titles (alphanumeric codes: PB-Y59, US304, KP15AC-01)
    _MODEL_CODE_RE = re.compile(r"\b([A-Z]{1,6}[-_]?[A-Z0-9]{2,12})\b")
    current_models: set[str] = set()
    for _, row in products_df.iterrows():
        title = str(row.get("product_title") or "")
        for m in _MODEL_CODE_RE.findall(title):
            current_models.add(m.upper())

    stale_items: list[str] = []

    # Only flag prices in clear product-data contexts:
    #   1. "ราคา ฿NNN" — product price label
    #   2. "| ฿NNN |"  — comparison table cell
    #   3. "~~฿NNN~~"  — strikethrough original price
    # This avoids flagging AI-generated prose (range references, midpoints, article titles).
    _PROD_PRICE_PATTERNS = [
        re.compile(r"ราคา\s*(?::\s*)?฿([\d,]+)", re.IGNORECASE),           # "ราคา: ฿990"
        re.compile(r"\|\s*฿([\d,]+)\s*\|", re.IGNORECASE),                  # "| ฿990 |"
        re.compile(r"~~฿([\d,]+)~~", re.IGNORECASE),                         # "~~฿2,580~~"
    ]

    checked_vals: set[int] = set()
    for pat in _PROD_PRICE_PATTERNS:
        for m in pat.finditer(body):
            raw = m.group(1).replace(",", "")
            try:
                val = int(raw)
            except ValueError:
                continue
            if val not in current_prices and val not in checked_vals:
                checked_vals.add(val)
                stale_items.append(f"฿{m.group(1)}")

    # Check model names in prose
    for m in _MODEL_CODE_RE.finditer(body):
        code = m.group(1).upper()
        # Only flag codes that look like product model codes (>=4 chars or contain dash)
        if (len(code) >= 4 or "-" in code) and code not in current_models:
            if code not in stale_items:
                stale_items.append(code)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_stale: list[str] = []
    for s in stale_items:
        if s not in seen:
            seen.add(s)
            unique_stale.append(s)

    return {"consistent": len(unique_stale) == 0, "stale_items": unique_stale}


# ---------------------------------------------------------------------------
# Task 2: Capacity relevance gate
# ---------------------------------------------------------------------------

_MAH_RE      = re.compile(r"(\d[\d,]*(?:[/|]\d[\d,]*)*)\s*mah", re.IGNORECASE)
# Keyword pattern: handle slug form "10000-mah" and natural "10000 mah" / Thai variants
_MAH_KW_RE   = re.compile(r"(\d[\d,]*)\s*[-\s]*(?:mah|มาห์|มิลลิแอมป์)", re.IGNORECASE)


def detect_capacity_evidence(title: str, description: str = "", attrs: str = "") -> dict:
    """Scan title/description/attrs for mAh capacity values.

    Returns:
        capacities_mah  — list of unique int capacity values found
        capacity_max    — largest capacity found (0 if none)
        capacity_source — "title" | "description" | "none"
    """
    def _extract_mah(text: str) -> list[int]:
        values = []
        for m in _MAH_RE.finditer(text):
            # group(1) may be "10000/20000/30000" — split on / and |
            for part in re.split(r"[/|]", m.group(1)):
                raw = part.strip().replace(",", "")
                try:
                    values.append(int(raw))
                except ValueError:
                    pass
        return values

    t_caps = _extract_mah(title)
    d_caps = _extract_mah(description)
    a_caps = _extract_mah(attrs)

    if t_caps:
        all_caps = sorted(set(t_caps), reverse=True)
        return {
            "capacities_mah": all_caps,
            "capacity_max":   max(all_caps),
            "capacity_source": "title",
        }
    if d_caps or a_caps:
        all_caps = sorted(set(d_caps + a_caps), reverse=True)
        return {
            "capacities_mah": all_caps,
            "capacity_max":   max(all_caps) if all_caps else 0,
            "capacity_source": "description",
        }
    return {"capacities_mah": [], "capacity_max": 0, "capacity_source": "none"}


def _extract_capacity_requirement(keyword: str) -> dict:
    """Extract mAh capacity requirement from keyword.

    Returns {"required_mah": int | None}
    """
    for m in _MAH_KW_RE.finditer(keyword):
        raw = m.group(1).replace(",", "")
        try:
            return {"required_mah": int(raw)}
        except ValueError:
            pass
    return {"required_mah": None}


def check_capacity_relevance(
    keyword: str,
    title: str,
    description: str = "",
    attrs: str = "",
) -> tuple[bool, str, dict]:
    """Validate product capacity against capacity requirement in keyword.

    Returns (is_valid, reason, evidence_dict).
    """
    req = _extract_capacity_requirement(keyword)
    ev  = detect_capacity_evidence(title, description, attrs)
    required_mah = req["required_mah"]

    if required_mah is None:
        return True, "ok (no capacity requirement in keyword)", ev

    caps = ev["capacities_mah"]

    if not caps:
        # No capacity found anywhere — warn but do not block
        return True, f"warning: ไม่พบ mAh ใน title/description (keyword ต้องการ {required_mah:,} mAh)", ev

    # Check for multi-variant title (e.g. "10000/20000mAh")
    if len(caps) > 1:
        tolerance = required_mah * 0.10
        if any(abs(c - required_mah) <= tolerance for c in caps):
            ev["ambiguous_variant"] = True
            return (
                True,
                f"warning: สินค้ามีหลาย variant ({'/'.join(str(c) for c in sorted(caps))} mAh) "
                f"ต้องตรวจว่า SKU ที่ link ไปคือ {required_mah:,} mAh",
                ev,
            )
        else:
            ev["ambiguous_variant"] = True
            return (
                False,
                f"หลาย variant ({'/'.join(str(c) for c in sorted(caps))} mAh) "
                f"ไม่มี variant ที่ตรงกับ {required_mah:,} mAh (±10%)",
                ev,
            )

    # Single capacity — check within ±10%
    found_mah = caps[0]
    tolerance = required_mah * 0.10
    if abs(found_mah - required_mah) <= tolerance:
        return True, "ok", ev

    return (
        False,
        f"ความจุ {found_mah:,} mAh ไม่ตรงกับ keyword ที่ต้องการ {required_mah:,} mAh (±10%)",
        ev,
    )


# ---------------------------------------------------------------------------
# Task 3: Duplicate model gate
# ---------------------------------------------------------------------------

def normalize_model_key(title: str) -> tuple:
    """Extract (brand, model_code, capacity_mah) from product title.

    Returns tuple with None for missing parts.
    Example: "[CCC] AUKEY PB-Y59 20W PD Power Bank 5000mAh" -> ("aukey", "pb-y59", 5000)
    """
    # Clean bracket tags
    cleaned = re.sub(r"\[[^\]]*\]", " ", title).strip()

    tokens = cleaned.split()
    brand: str | None = None
    model_code: str | None = None
    capacity_mah: int | None = None

    # Brand = first non-numeric alphabetic token
    for tok in tokens:
        tok_clean = re.sub(r"[^a-zA-Z0-9]", "", tok)
        if tok_clean and tok_clean[0].isalpha() and len(tok_clean) >= 2:
            brand = tok_clean.lower()
            break

    # Model code — matches: PB-Y59, KP15AC-01, US304, PB561
    # Strategy: prefer dash-containing codes (higher specificity), then nodash
    # Exclude single-letter + number patterns like "D22" (common in wattage tokens like "PD22")
    _mc_dash_re = re.compile(
        r"\b([A-Z]{1,6}[0-9]*[A-Z]*-[A-Z0-9]{1,12}(?:-[A-Z0-9]+)*)\b",
        re.IGNORECASE,
    )
    _mc_nodash_re = re.compile(
        r"\b([A-Z]{2,6}[0-9]{2,8}[A-Z]{0,4})\b",
        re.IGNORECASE,
    )
    # First pass: find dash-containing model codes
    for m in _mc_dash_re.finditer(cleaned):
        candidate = m.group(1)
        if any(c.isdigit() for c in candidate):
            model_code = candidate.lower()
            break
    # Second pass: nodash (only if no dash code found)
    if model_code is None:
        for m in _mc_nodash_re.finditer(cleaned):
            candidate = m.group(1)
            if any(c.isdigit() for c in candidate):
                model_code = candidate.lower()
                break

    # Capacity — take the first value from multi-variant if present
    cap_m = _MAH_RE.search(title)
    if cap_m:
        first_part = re.split(r"[/|]", cap_m.group(1))[0].strip()
        try:
            capacity_mah = int(first_part.replace(",", ""))
        except ValueError:
            pass

    return (brand, model_code, capacity_mah)


def check_duplicate_models(products: list[dict]) -> list[dict]:
    """Check products list for duplicate model keys.

    Input: list of dicts with 'itemid' and 'product_title' (or 'title').
    Returns list of duplicate groups: [{"key": (brand, model, cap), "itemids": [id1, id2]}]
    Only flags when model_code is not None.
    """
    key_to_itemids: dict[tuple, list[int]] = {}

    for p in products:
        itemid = int(p.get("itemid") or 0)
        title  = str(p.get("product_title") or p.get("title") or "")
        brand, model_code, capacity_mah = normalize_model_key(title)

        if model_code is None:
            continue

        key = (brand, model_code, capacity_mah)
        key_to_itemids.setdefault(key, []).append(itemid)

    duplicates = []
    for key, itemids in key_to_itemids.items():
        if len(itemids) >= 2:
            duplicates.append({"key": key, "itemids": itemids})

    return duplicates


# ---------------------------------------------------------------------------
# Task 4: Product-type-specific feature copy guard
# ---------------------------------------------------------------------------

_POWER_BANK_BLOCKED_FEATURES = ["remote shutter", "รีโมทชัตเตอร์", "shutter release"]

for _rule in _PRODUCT_TYPE_RULES:
    if "power bank" in _rule.get("triggers", frozenset()):
        _rule.setdefault("blocked_features", _POWER_BANK_BLOCKED_FEATURES)
    else:
        _rule.setdefault("blocked_features", [])
del _rule


def check_content_feature_copy(keyword: str, content_md: str) -> list[str]:
    """Return list of blocked feature phrases found in content_md for the given keyword.

    Returns empty list when no rule triggers or no blocked phrases found.
    """
    kw_lo = keyword.lower()
    offenders: list[str] = []

    body = content_md
    if content_md.startswith("---"):
        end_fm = content_md.find("\n---", 3)
        if end_fm != -1:
            body = content_md[end_fm + 4:]

    body_lo = body.lower()

    for rule in _PRODUCT_TYPE_RULES:
        if not any(trigger in kw_lo for trigger in rule["triggers"]):
            continue
        for phrase in rule.get("blocked_features", []):
            if phrase.lower() in body_lo:
                offenders.append(phrase)

    return offenders


# ---------------------------------------------------------------------------
# Task 5: Related articles
# ---------------------------------------------------------------------------

def get_related_articles(article_id: str, limit: int = 3) -> list[dict]:
    """Return up to limit related articles in the same category (reviewed or published).

    Returns list of {"article_id", "title", "keyword"}.
    """
    con = _connect(read_only=True)
    try:
        row = con.execute(
            f"SELECT category, keyword FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?",
            [article_id],
        ).fetchone()
        if not row:
            con.close()
            return []

        category, keyword = row

        related_df = con.execute(f"""
            SELECT article_id, title, keyword
            FROM {SEO_ARTICLES_TABLE}
            WHERE category = ?
              AND article_id != ?
              AND status IN ('reviewed', 'published')
            ORDER BY updated_at DESC
            LIMIT ?
        """, [category, article_id, limit]).fetchdf()
        con.close()
    except Exception:
        con.close()
        raise

    if related_df.empty:
        return []

    return [
        {
            "article_id": str(row.get("article_id") or ""),
            "title":      str(row.get("title") or ""),
            "keyword":    str(row.get("keyword") or ""),
        }
        for _, row in related_df.iterrows()
    ]


# ---------------------------------------------------------------------------
# Task 1d + 5: Rebuild article content
# ---------------------------------------------------------------------------

def rebuild_article_content(article_id: str) -> dict:
    """Rebuild content_md for an existing article using current seo_article_products rows.

    - Reads current products from seo_article_products JOIN products
    - Regenerates all content sections
    - Preserves YAML frontmatter, replaces body
    - Clears [CONTENT_STALE] from review_note
    - Appends Related Articles section if >= 1 related article exists
    - Returns {"success": bool, "article_id": str, "products_used": int}
    """
    con = _connect(read_only=True)
    try:
        article = con.execute(
            f"SELECT * FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
        ).fetchdf()
        if article.empty:
            con.close()
            return {"success": False, "article_id": article_id, "error": f"Article '{article_id}' not found"}

        art_row = article.iloc[0]
        keyword     = str(art_row.get("keyword") or "")
        old_content = str(art_row.get("content_md") or "")
        review_note = str(art_row.get("review_note") or "")

        _prod_cols = {
            r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='products'"
            ).fetchall()
        }
        _has_desc    = "description" in _prod_cols
        _has_sold    = "item_sold" in _prod_cols
        _has_rating  = "item_rating" in _prod_cols
        _has_shoprat = "shop_rating" in _prod_cols
        _has_disc    = "discount_percentage" in _prod_cols
        _has_origprc = "price" in _prod_cols
        _has_imglink = "image_link" in _prod_cols
        _has_plink   = "product_link" in _prod_cols
        _has_dflink  = "product_short link" in _prod_cols

        desc_expr    = "COALESCE(p.description, '')"        if _has_desc    else "''"
        sold_expr    = "COALESCE(p.item_sold, 0)"           if _has_sold    else "0"
        rating_expr  = "COALESCE(p.item_rating, 0.0)"       if _has_rating  else "0.0"
        shoprat_expr = "COALESCE(p.shop_rating, 0.0)"       if _has_shoprat else "0.0"
        disc_expr    = "COALESCE(p.discount_percentage, 0)" if _has_disc    else "0"
        origprc_expr = "COALESCE(p.price, ap.sale_price)"   if _has_origprc else "ap.sale_price"
        imglink_expr = "COALESCE(p.image_link, ap.image_link)" if _has_imglink else "ap.image_link"
        plink_expr   = "COALESCE(p.product_link, '')"       if _has_plink   else "''"
        dflink_expr  = 'COALESCE(p."product_short link", \'\')' if _has_dflink  else "''"

        rows_df = con.execute(f"""
            SELECT
                ap.rank_in_article,
                ap.itemid,
                ap.shopid,
                ap.product_title  AS title,
                ap.sale_price,
                ap.affiliate_link,
                ap.affiliate_link_type,
                {origprc_expr}  AS original_price,
                {sold_expr}     AS item_sold,
                {rating_expr}   AS item_rating,
                {shoprat_expr}  AS shop_rating,
                {disc_expr}     AS discount_pct,
                {imglink_expr}  AS image_link,
                {plink_expr}    AS product_link,
                {dflink_expr}   AS datafeed_link,
                {desc_expr}     AS description_raw
            FROM {SEO_ARTICLE_PRODUCTS_TABLE} ap
            LEFT JOIN products p ON ap.itemid = p.itemid
            WHERE ap.article_id = ?
            ORDER BY ap.rank_in_article
        """, [article_id]).fetchdf()
        con.close()
    except Exception:
        con.close()
        raise

    if rows_df.empty:
        return {"success": False, "article_id": article_id, "error": "No products found for article"}

    aff_lookup = _get_affiliate_lookup()
    products: list[dict] = []
    for _, row in rows_df.iterrows():
        sp      = int(row.get("sale_price") or 0)
        op      = int(row.get("original_price") or sp)
        sold    = int(row.get("item_sold") or 0)
        rating  = float(row.get("item_rating") or 0.0)
        shoprat = float(row.get("shop_rating") or 0.0)
        disc    = int(row.get("discount_pct") or 0)
        aff_link  = str(row.get("affiliate_link") or "")
        link_type = str(row.get("affiliate_link_type") or "none")
        img    = str(row.get("image_link") or "")
        plink  = str(row.get("product_link") or "")
        dflink = str(row.get("datafeed_link") or "")

        if link_type != "confirmed":
            aff_link, link_type = _resolve_affiliate_link(plink, dflink, aff_lookup)

        products.append({
            "title":              str(row.get("title") or ""),
            "itemid":             int(row.get("itemid") or 0),
            "shopid":             int(row.get("shopid") or 0),
            "sale_price":         sp,
            "sale_price_fmt":     format_price(sp),
            "original_price":     op,
            "original_price_fmt": format_price(op),
            "item_sold":          sold,
            "shop_rating":        shoprat,
            "item_rating":        rating,
            "discount_pct":       disc,
            "category":           "",
            "brand":              "",
            "image_link":         img,
            "product_link":       plink,
            "affiliate_link":     aff_link,
            "affiliate_link_type": link_type,
            "opportunity_score":  0.0,
            "description_raw":    str(row.get("description_raw") or "")[:500],
            "match_reason":       "rebuild",
        })

    from shopee_engine.editorial_team import generate_article_content
    editorial = generate_article_content(keyword, "", products)

    if editorial["_success"]:
        intro              = editorial["intro"]
        buying_scenario    = editorial["buying_scenario"]
        for_whom           = editorial["for_whom"]
        not_for_whom       = editorial["not_for_whom"]
        buying_guide       = editorial["buying_guide"]
        product_highlights = editorial["product_highlights"]
        summary            = editorial["summary"]
    else:
        intro              = _ai_intro(keyword, products)
        buying_scenario    = ""
        for_whom           = ""
        not_for_whom       = ""
        buying_guide       = _ai_buying_guide(keyword, products)
        product_highlights = {}
        summary            = _ai_summary(keyword, products)

    comp_table     = _build_comparison_table(products)
    product_blocks = _build_product_blocks(products, product_highlights=product_highlights)
    faq            = _build_faq(keyword, products)

    buying_context_parts: list[str] = []
    if buying_scenario:
        buying_context_parts.append(f"## บริบทการซื้อ\n\n{buying_scenario}")
    if for_whom:
        buying_context_parts.append(f"**เหมาะกับ:**\n\n{for_whom}")
    if not_for_whom:
        buying_context_parts.append(f"**อาจไม่ใช่ตัวเลือกที่ดีถ้า:**\n\n{not_for_whom}")
    buying_context_block = ("\n\n".join(buying_context_parts) + "\n\n") if buying_context_parts else ""

    import json as _json
    highlights_comment = (
        f"\n<!-- editorial:product_highlights\n"
        f"{_json.dumps(product_highlights, ensure_ascii=False, indent=2)}\n"
        f"-->\n"
        if product_highlights else ""
    )

    # Related articles section (Task 5)
    related = get_related_articles(article_id, limit=3)
    related_section = ""
    if related:
        lines = ["## บทความที่เกี่ยวข้อง"]
        for ra in related:
            ra_id    = ra["article_id"]
            ra_title = ra["title"] or ra["keyword"]
            lines.append(f"- [{ra_title}](/{ra_id}/)")
        related_section = "\n".join(lines) + "\n\n"

    body = f"""\
## บทนำ

{intro}

{buying_context_block}## ตารางเปรียบเทียบ

{comp_table}

## แนะนำสินค้า

{product_blocks}

## คำแนะนำการเลือกซื้อ

{buying_guide}

{faq}

## บทสรุป

{summary}
{related_section}{highlights_comment}"""

    # Preserve frontmatter from old content
    if old_content.startswith("---"):
        end_fm = old_content.find("\n---", 3)
        if end_fm != -1:
            frontmatter_block = old_content[: end_fm + 4]
            new_content = frontmatter_block + "\n\n" + body
        else:
            new_content = old_content + "\n\n" + body
    else:
        new_content = body

    # Clear [CONTENT_STALE] from review_note
    new_note = review_note.replace("[CONTENT_STALE]", "").strip()

    con_w = _connect(read_only=False)
    try:
        _init_seo_tables(con_w)
        con_w.execute(f"""
            UPDATE {SEO_ARTICLES_TABLE}
            SET content_md = ?,
                review_note = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE article_id = ?
        """, [new_content, new_note, article_id])
        con_w.close()
    except Exception:
        con_w.close()
        raise

    return {
        "success":       True,
        "article_id":    article_id,
        "products_used": len(products),
    }


# ---------------------------------------------------------------------------
# Hook: mark article stale after product changes (Task 1c)
# ---------------------------------------------------------------------------

def _mark_content_stale(article_id: str) -> None:
    """Append [CONTENT_STALE] to review_note. No-op on any error."""
    try:
        con = _connect(read_only=False)
        row = con.execute(
            f"SELECT review_note FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?",
            [article_id],
        ).fetchone()
        if row:
            old_note = str(row[0] or "")
            if "[CONTENT_STALE]" not in old_note:
                new_note = (old_note + " [CONTENT_STALE]").strip()
                con.execute(
                    f"UPDATE {SEO_ARTICLES_TABLE} SET review_note = ? WHERE article_id = ?",
                    [new_note, article_id],
                )
        con.close()
    except Exception:
        pass
