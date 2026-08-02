"""Editorial Brief Workflow — structured brief model, parser, and DB CRUD.

A brief must be created and approved before /seo-draft can generate a full
article. This enforces human-strategy → bot-execution rather than
bot-driven keyword→template.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

import duckdb

from shopee_engine.config import config

EDITORIAL_BRIEFS_TABLE = "editorial_briefs"

# ---------------------------------------------------------------------------
# DB init
# ---------------------------------------------------------------------------

def _connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(config.db_path), read_only=read_only)


def init_briefs_table() -> None:
    """Create editorial_briefs table if it does not exist (idempotent)."""
    con = _connect(read_only=False)
    try:
        con.execute(f"""
            CREATE TABLE IF NOT EXISTS {EDITORIAL_BRIEFS_TABLE} (
                brief_id                       VARCHAR PRIMARY KEY,
                article_id                     VARCHAR,
                keyword                        VARCHAR NOT NULL,
                proposed_title                 VARCHAR DEFAULT '',
                canonical_category             VARCHAR DEFAULT '',
                why_now                        VARCHAR DEFAULT '',
                user_problem                   VARCHAR DEFAULT '',
                search_intent                  VARCHAR DEFAULT '',
                target_audience                VARCHAR DEFAULT '',
                article_angle                  VARCHAR DEFAULT '',
                must_compare_attributes        JSON,
                product_diversity_requirements VARCHAR DEFAULT '',
                must_include                   JSON,
                must_avoid                     JSON,
                claims_requiring_evidence      JSON,
                recommended_product_count      INTEGER DEFAULT 5,
                seasonal_context               VARCHAR DEFAULT '',
                editorial_notes                VARCHAR DEFAULT '',
                source                         VARCHAR DEFAULT 'user',
                brief_status                   VARCHAR DEFAULT 'draft',
                created_at                     TIMESTAMP DEFAULT current_timestamp,
                updated_at                     TIMESTAMP DEFAULT current_timestamp
            )
        """)
        con.close()
    except Exception as exc:
        con.close()
        raise RuntimeError(f"init_briefs_table failed: {exc}") from exc


def _brief_id_for(keyword: str) -> str:
    raw = f"{keyword}_{time.time()}"
    return "brief-" + hashlib.md5(raw.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Markdown parser
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

# Map section headers (lowercased, stripped) → field name
_HEADER_MAP: dict[str, str] = {
    "keyword":                      "keyword",
    "คำค้น":                        "keyword",
    "proposed title":               "proposed_title",
    "proposed_title":               "proposed_title",
    "title":                        "proposed_title",
    "หัวข้อที่เสนอ":                "proposed_title",
    "category":                     "canonical_category",
    "หมวดหมู่":                     "canonical_category",
    "why now":                      "why_now",
    "why_now":                      "why_now",
    "ทำไมตอนนี้":                   "why_now",
    "user problem":                 "user_problem",
    "user_problem":                 "user_problem",
    "ปัญหาของผู้ใช้":               "user_problem",
    "search intent":                "search_intent",
    "search_intent":                "search_intent",
    "intent":                       "search_intent",
    "เจตนาการค้นหา":                "search_intent",
    "target audience":              "target_audience",
    "target_audience":              "target_audience",
    "กลุ่มเป้าหมาย":               "target_audience",
    "article angle":                "article_angle",
    "article_angle":                "article_angle",
    "มุมของบทความ":                 "article_angle",
    "must compare":                 "must_compare_attributes",
    "must_compare":                 "must_compare_attributes",
    "must compare attributes":      "must_compare_attributes",
    "ต้องเปรียบเทียบ":              "must_compare_attributes",
    "product diversity":            "product_diversity_requirements",
    "product_diversity":            "product_diversity_requirements",
    "ความหลากหลายของสินค้า":        "product_diversity_requirements",
    "must include":                 "must_include",
    "must_include":                 "must_include",
    "ต้องรวม":                      "must_include",
    "must avoid":                   "must_avoid",
    "must_avoid":                   "must_avoid",
    "ห้ามรวม":                      "must_avoid",
    "ห้ามใส่":                      "must_avoid",
    "claims requiring evidence":    "claims_requiring_evidence",
    "claims_requiring_evidence":    "claims_requiring_evidence",
    "claims":                       "claims_requiring_evidence",
    "ต้องมีหลักฐาน":                "claims_requiring_evidence",
    "recommended product count":    "recommended_product_count",
    "recommended_product_count":    "recommended_product_count",
    "จำนวนสินค้าแนะนำ":            "recommended_product_count",
    "seasonal context":             "seasonal_context",
    "seasonal_context":             "seasonal_context",
    "บริบทตามฤดูกาล":               "seasonal_context",
    "editorial notes":              "editorial_notes",
    "editorial_notes":              "editorial_notes",
    "notes":                        "editorial_notes",
    "หมายเหตุบรรณาธิการ":           "editorial_notes",
}

_JSON_ARRAY_FIELDS = {
    "must_compare_attributes",
    "must_include",
    "must_avoid",
    "claims_requiring_evidence",
}


def _parse_list_body(body: str) -> list[str]:
    """Parse a markdown bullet list into a Python list (strips '- ', '* ', '• ' prefixes)."""
    items: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*•]\s+", "", line)
        if line:
            items.append(line)
    return items


def parse_brief_markdown(text: str) -> dict[str, Any]:
    """Parse a Papatha/user Markdown brief into a structured dict.

    Expected format:
        ## Keyword
        power bank มีสายในตัว รุ่นไหนดี

        ## Proposed title
        5 Power Bank มีสายในตัว รุ่นไหนดี (อัปเดต 2026)

        ## Must avoid
        - Generic content
        - "เลนส์ครบชุด"
        ...

    Returns a dict with keys matching DB columns.
    Required key: 'keyword'.
    """
    result: dict[str, Any] = {}

    # Split on ## headers
    matches = list(_SECTION_RE.finditer(text))
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        header = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((header, body))

    for header, body in sections:
        field = _HEADER_MAP.get(header.lower().strip())
        if field is None:
            continue

        if field in _JSON_ARRAY_FIELDS:
            # Could be a bullet list or comma-separated
            if re.search(r"^[-*•]", body, re.MULTILINE):
                result[field] = _parse_list_body(body)
            else:
                result[field] = [s.strip() for s in re.split(r"[,\n]+", body) if s.strip()]
        elif field == "recommended_product_count":
            m2 = re.search(r"\d+", body)
            result[field] = int(m2.group()) if m2 else 5
        else:
            result[field] = body

    return result


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def _row_to_dict(row: tuple, columns: list[str]) -> dict[str, Any]:
    d: dict[str, Any] = dict(zip(columns, row))
    for f in _JSON_ARRAY_FIELDS:
        if f in d and isinstance(d[f], str):
            try:
                d[f] = json.loads(d[f])
            except Exception:
                d[f] = []
    return d


def create_brief(
    keyword: str,
    brief_data: dict[str, Any],
    source: str = "user",
    article_id: str | None = None,
) -> dict[str, Any]:
    """Insert a new editorial brief. Returns the created brief dict."""
    init_briefs_table()
    brief_id = _brief_id_for(keyword)
    now = datetime.now(tz=timezone.utc)

    fields = {
        "keyword":                      keyword,
        "proposed_title":               brief_data.get("proposed_title", ""),
        "canonical_category":           brief_data.get("canonical_category", ""),
        "why_now":                      brief_data.get("why_now", ""),
        "user_problem":                 brief_data.get("user_problem", ""),
        "search_intent":                brief_data.get("search_intent", ""),
        "target_audience":              brief_data.get("target_audience", ""),
        "article_angle":                brief_data.get("article_angle", ""),
        "must_compare_attributes":      json.dumps(brief_data.get("must_compare_attributes") or [], ensure_ascii=False),
        "product_diversity_requirements": brief_data.get("product_diversity_requirements", ""),
        "must_include":                 json.dumps(brief_data.get("must_include") or [], ensure_ascii=False),
        "must_avoid":                   json.dumps(brief_data.get("must_avoid") or [], ensure_ascii=False),
        "claims_requiring_evidence":    json.dumps(brief_data.get("claims_requiring_evidence") or [], ensure_ascii=False),
        "recommended_product_count":    brief_data.get("recommended_product_count", 5),
        "seasonal_context":             brief_data.get("seasonal_context", ""),
        "editorial_notes":              brief_data.get("editorial_notes", ""),
        "source":                       source,
        "brief_status":                 "draft",
        "article_id":                   article_id or "",
        "created_at":                   now,
        "updated_at":                   now,
    }

    cols = list(fields.keys())
    placeholders = ", ".join(["?" for _ in cols])
    values = list(fields.values())

    con = _connect(read_only=False)
    try:
        con.execute(
            f"INSERT INTO {EDITORIAL_BRIEFS_TABLE} (brief_id, {', '.join(cols)}) "
            f"VALUES (?, {placeholders})",
            [brief_id] + values,
        )
        con.close()
    except Exception as exc:
        con.close()
        raise RuntimeError(f"create_brief failed: {exc}") from exc

    return get_brief_by_id(brief_id) or {}


def get_brief_by_id(brief_id: str) -> dict[str, Any] | None:
    """Fetch a brief by its brief_id."""
    init_briefs_table()
    con = _connect(read_only=True)
    try:
        rows = con.execute(
            f"SELECT * FROM {EDITORIAL_BRIEFS_TABLE} WHERE brief_id = ?",
            [brief_id],
        ).fetchall()
        cols = [d[0] for d in con.description]
        con.close()
    except Exception as exc:
        con.close()
        raise RuntimeError(f"get_brief_by_id failed: {exc}") from exc

    if not rows:
        return None
    return _row_to_dict(rows[0], cols)


def get_brief_for_keyword(keyword: str) -> dict[str, Any] | None:
    """Return the most recent brief for a keyword (any status)."""
    init_briefs_table()
    # Normalize: strip year tokens + trailing spaces for comparison
    norm_kw = re.sub(r"ปี\s*\d{4}|\b(25\d{2}|20\d{2})\b", "", keyword).strip()
    con = _connect(read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT * FROM {EDITORIAL_BRIEFS_TABLE}
            WHERE keyword = ? OR keyword = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            [keyword, norm_kw],
        ).fetchall()
        cols = [d[0] for d in con.description]
        con.close()
    except Exception as exc:
        con.close()
        raise RuntimeError(f"get_brief_for_keyword failed: {exc}") from exc

    if not rows:
        return None
    return _row_to_dict(rows[0], cols)


def get_brief_for_article(article_id: str) -> dict[str, Any] | None:
    """Return the most recent brief linked to an article_id."""
    init_briefs_table()
    con = _connect(read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT * FROM {EDITORIAL_BRIEFS_TABLE}
            WHERE article_id = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            [article_id],
        ).fetchall()
        cols = [d[0] for d in con.description]
        con.close()
    except Exception as exc:
        con.close()
        raise RuntimeError(f"get_brief_for_article failed: {exc}") from exc

    if not rows:
        return None
    return _row_to_dict(rows[0], cols)


def get_brief_status(keyword_or_article_id: str) -> str:
    """Return brief_status for a keyword or article_id, or 'none' if not found."""
    brief = get_brief_for_keyword(keyword_or_article_id)
    if brief:
        return brief.get("brief_status", "none")
    brief = get_brief_for_article(keyword_or_article_id)
    if brief:
        return brief.get("brief_status", "none")
    return "none"


def approve_brief(brief_id: str) -> dict[str, Any]:
    """Set brief_status to 'approved'. Returns updated brief."""
    init_briefs_table()
    now = datetime.now(tz=timezone.utc)
    con = _connect(read_only=False)
    try:
        con.execute(
            f"UPDATE {EDITORIAL_BRIEFS_TABLE} SET brief_status = 'approved', updated_at = ? WHERE brief_id = ?",
            [now, brief_id],
        )
        con.close()
    except Exception as exc:
        con.close()
        raise RuntimeError(f"approve_brief failed: {exc}") from exc

    brief = get_brief_by_id(brief_id)
    if not brief:
        raise RuntimeError(f"brief_id '{brief_id}' not found after approve")
    return brief


def update_brief(brief_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update arbitrary fields on a brief. Returns updated brief."""
    init_briefs_table()
    now = datetime.now(tz=timezone.utc)
    allowed = {
        "proposed_title", "canonical_category", "why_now", "user_problem",
        "search_intent", "target_audience", "article_angle",
        "must_compare_attributes", "product_diversity_requirements",
        "must_include", "must_avoid", "claims_requiring_evidence",
        "recommended_product_count", "seasonal_context", "editorial_notes",
        "article_id", "brief_status",
    }
    set_parts: list[str] = []
    values: list[Any] = []
    for k, v in updates.items():
        if k not in allowed:
            continue
        if k in _JSON_ARRAY_FIELDS and isinstance(v, list):
            v = json.dumps(v, ensure_ascii=False)
        set_parts.append(f"{k} = ?")
        values.append(v)

    if not set_parts:
        return get_brief_by_id(brief_id) or {}

    set_parts.append("updated_at = ?")
    values.append(now)
    values.append(brief_id)

    con = _connect(read_only=False)
    try:
        con.execute(
            f"UPDATE {EDITORIAL_BRIEFS_TABLE} SET {', '.join(set_parts)} WHERE brief_id = ?",
            values,
        )
        con.close()
    except Exception as exc:
        con.close()
        raise RuntimeError(f"update_brief failed: {exc}") from exc

    return get_brief_by_id(brief_id) or {}


def link_brief_to_article(brief_id: str, article_id: str) -> None:
    """Set article_id on a brief (called after draft is created)."""
    update_brief(brief_id, {"article_id": article_id})


def list_briefs(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent briefs ordered by updated_at desc."""
    init_briefs_table()
    con = _connect(read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT brief_id, keyword, proposed_title, canonical_category,
                   brief_status, source, created_at, updated_at
            FROM {EDITORIAL_BRIEFS_TABLE}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        cols = [d[0] for d in con.description]
        con.close()
    except Exception as exc:
        con.close()
        raise RuntimeError(f"list_briefs failed: {exc}") from exc

    return [dict(zip(cols, r)) for r in rows]
