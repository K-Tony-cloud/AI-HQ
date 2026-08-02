"""Pre-Publish QA Pipeline for Shopee SEO articles.

Provides:
  run_preflight(article_id)        — full gate suite
  build_staging_html(article_id)   — export HTML for visual inspection
  crawl_staging_html(article_id, html_content) — validate HTML against DB
  generate_preflight_json(...)     — machine-readable JSON report
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shopee_engine.seo_engine import (
    SEO_ARTICLES_TABLE,
    SEO_ARTICLE_PRODUCTS_TABLE,
    _connect,
    check_capacity_relevance,
    check_content_feature_copy,
    check_duplicate_models,
    check_product_relevance,
    check_product_spec,
    check_variant_price_plausibility,
    validate_content_consistency,
)
from shopee_engine.article_exporter import generate_preview_body
from shopee_engine.title_cleaner import clean_display_title

# CANONICAL_CATEGORIES imported lazily to avoid circular import issues
def _get_canonical_categories() -> dict[str, str]:
    from shopee_engine.taxonomy import CANONICAL_CATEGORIES
    return CANONICAL_CATEGORIES


# ---------------------------------------------------------------------------
# Staging directory
# ---------------------------------------------------------------------------

def _staging_dir() -> Path:
    """Return exports/staging/ directory relative to project root."""
    project_root = Path(__file__).resolve().parent.parent
    staging = project_root / "exports" / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    return staging


# ---------------------------------------------------------------------------
# Gate helpers
# ---------------------------------------------------------------------------

def _gate(passed: bool, errors: list[str], warnings: list[str] = None, evidence: dict = None) -> dict:
    return {
        "passed":   passed,
        "errors":   errors,
        "warnings": warnings or [],
        "evidence": evidence or {},
    }


# ---------------------------------------------------------------------------
# run_preflight
# ---------------------------------------------------------------------------

def run_preflight(article_id: str) -> dict:
    """Run all pre-publish gates and return comprehensive report.

    Returns:
        {
          "article_id":   str,
          "passed":       bool,
          "gates":        dict,
          "summary_errors":   list[str],
          "summary_warnings": list[str],
          "article_meta": dict,
          "products":     list[dict],
        }
    """
    summary_errors:   list[str] = []
    summary_warnings: list[str] = []
    gates: dict[str, dict] = {}
    products_out: list[dict] = []

    # ── Load article + products ──────────────────────────────────────────────
    con = _connect(read_only=True)
    try:
        art_df = con.execute(
            f"SELECT * FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
        ).fetchdf()
        if art_df.empty:
            con.close()
            return {
                "article_id":      article_id,
                "passed":          False,
                "gates":           {},
                "summary_errors":  [f"Article '{article_id}' not found"],
                "summary_warnings": [],
                "article_meta":    {},
                "products":        [],
            }

        art_row = art_df.iloc[0]

        # Detect optional columns
        _prod_cols = {
            r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='products'"
            ).fetchall()
        }
        _has_desc  = "description" in _prod_cols
        _has_attrs = "global_item_attributes" in _prod_cols
        _has_mn    = "model_names" in _prod_cols
        _desc_expr  = "COALESCE(p.description, '')"            if _has_desc  else "''"
        _attrs_expr = "COALESCE(p.global_item_attributes, '')" if _has_attrs else "''"
        _mn_expr    = "COALESCE(p.model_names, '')"             if _has_mn    else "''"

        if _prod_cols:
            prods_df = con.execute(f"""
                SELECT
                    ap.rank_in_article,
                    ap.itemid,
                    ap.shopid,
                    ap.product_title,
                    ap.sale_price,
                    ap.affiliate_link,
                    ap.affiliate_link_type,
                    {_desc_expr}  AS _desc,
                    {_attrs_expr} AS _attrs,
                    {_mn_expr}    AS _model_names
                FROM {SEO_ARTICLE_PRODUCTS_TABLE} ap
                LEFT JOIN products p ON ap.itemid = p.itemid
                WHERE ap.article_id = ?
                ORDER BY ap.rank_in_article
            """, [article_id]).fetchdf()
        else:
            prods_df = con.execute(
                f"SELECT * FROM {SEO_ARTICLE_PRODUCTS_TABLE} WHERE article_id = ?", [article_id]
            ).fetchdf()
            prods_df["_desc"]        = ""
            prods_df["_attrs"]       = ""
            prods_df["_model_names"] = ""

        # Duplicate-title check: same title in another article
        art_title = str(art_row.get("title") or "")
        dup_title_rows = con.execute(
            f"SELECT article_id FROM {SEO_ARTICLES_TABLE} "
            f"WHERE LOWER(title) = LOWER(?) AND article_id != ?",
            [art_title, article_id],
        ).fetchall()
        dup_title_ids = [r[0] for r in dup_title_rows]

        # Related articles count (for stale_prose gate context)
        related_count = con.execute(
            f"SELECT COUNT(*) FROM {SEO_ARTICLES_TABLE} "
            f"WHERE category = ? AND article_id != ? AND status IN ('reviewed','published')",
            [str(art_row.get("category") or ""), article_id],
        ).fetchone()[0]

        con.close()
    except Exception as exc:
        try:
            con.close()
        except Exception:
            pass
        return {
            "article_id":      article_id,
            "passed":          False,
            "gates":           {},
            "summary_errors":  [f"DB error: {exc}"],
            "summary_warnings": [],
            "article_meta":    {},
            "products":        [],
        }

    keyword  = str(art_row.get("keyword") or "")
    category = str(art_row.get("category") or "")
    status   = str(art_row.get("status") or "")
    title    = str(art_row.get("title") or "")
    content_md = str(art_row.get("content_md") or "")

    article_meta = {
        "title":         title,
        "keyword":       keyword,
        "category":      category,
        "status":        status,
        "product_count": len(prods_df),
    }

    # Build product list
    prod_list: list[dict] = []
    for _, row in prods_df.iterrows():
        prod_list.append({
            "itemid":         int(row.get("itemid") or 0),
            "shopid":         int(row.get("shopid") or 0),
            "rank":           int(row.get("rank_in_article") or 0),
            "product_title":  str(row.get("product_title") or ""),
            "sale_price":     int(row.get("sale_price") or 0),
            "affiliate_link": str(row.get("affiliate_link") or ""),
            "affiliate_link_type": str(row.get("affiliate_link_type") or "none"),
            "_desc":         str(row.get("_desc") or ""),
            "_attrs":        str(row.get("_attrs") or ""),
            "_model_names":  str(row.get("_model_names") or ""),
        })

    # ── Gate 1: canonical_category ──────────────────────────────────────────
    CANONICAL_CATEGORIES = _get_canonical_categories()
    if not category:
        g_errors = ["Category ไม่ได้ระบุ"]
        gates["canonical_category"] = _gate(False, g_errors)
        summary_errors.extend(g_errors)
    elif category not in CANONICAL_CATEGORIES:
        g_errors = [
            f"Category '{category}' ไม่ใช่ canonical — "
            f"Valid slugs: {', '.join(CANONICAL_CATEGORIES.keys())}"
        ]
        gates["canonical_category"] = _gate(False, g_errors)
        summary_errors.extend(g_errors)
    else:
        gates["canonical_category"] = _gate(True, [])

    # ── Gate 2: product_type_relevance ──────────────────────────────────────
    rel_errors: list[str] = []
    for p in prod_list:
        rel_ok, rel_reason = check_product_relevance(keyword, p["product_title"])
        if not rel_ok:
            rel_errors.append(f"itemid {p['itemid']}: {rel_reason}")
    gates["product_type_relevance"] = _gate(len(rel_errors) == 0, rel_errors)
    summary_errors.extend(rel_errors)

    # ── Gate 3: spec_relevance ───────────────────────────────────────────────
    spec_errors: list[str] = []
    for p in prod_list:
        spec_ok, spec_reason, spec_ev = check_product_spec(
            keyword, p["product_title"], p["_desc"], p["_attrs"]
        )
        if not spec_ok:
            spec_errors.append(f"itemid {p['itemid']}: {spec_reason}")
    gates["spec_relevance"] = _gate(len(spec_errors) == 0, spec_errors)
    summary_errors.extend(spec_errors)

    # ── Gate 4: capacity_relevance ───────────────────────────────────────────
    cap_errors:   list[str] = []
    cap_warnings: list[str] = []
    for p in prod_list:
        cap_ok, cap_reason, _ = check_capacity_relevance(
            keyword, p["product_title"], p["_desc"], p["_attrs"]
        )
        if not cap_ok:
            cap_errors.append(f"itemid {p['itemid']}: {cap_reason}")
        elif cap_reason.startswith("warning:"):
            cap_warnings.append(f"itemid {p['itemid']}: {cap_reason}")
    gates["capacity_relevance"] = _gate(len(cap_errors) == 0, cap_errors, cap_warnings)
    summary_errors.extend(cap_errors)
    summary_warnings.extend(cap_warnings)

    # ── Gate 5: duplicate_model ──────────────────────────────────────────────
    dup_errors: list[str] = []
    dup_groups = check_duplicate_models(
        [{"itemid": p["itemid"], "product_title": p["product_title"]} for p in prod_list]
    )
    for grp in dup_groups:
        dup_errors.append(f"Duplicate model key={grp['key']}, itemids={grp['itemids']}")
    gates["duplicate_model"] = _gate(len(dup_errors) == 0, dup_errors)
    summary_errors.extend(dup_errors)

    # ── Gate 6: variant_price_plausibility ──────────────────────────────────
    plaus_errors:   list[str] = []
    plaus_warnings: list[str] = []
    for p in prod_list:
        plaus_ok, plaus_reason, plaus_ev = check_variant_price_plausibility(
            p["product_title"], float(p["sale_price"]), p["_model_names"], keyword
        )
        if not plaus_ok:
            plaus_errors.append(f"itemid {p['itemid']}: {plaus_reason}")
        elif plaus_ev.get("is_multivariant") and p["rank"] == 1:
            plaus_warnings.append(f"itemid {p['itemid']}: multi-variant rank-1 product — ตรวจ SKU")
    gates["variant_price_plausibility"] = _gate(len(plaus_errors) == 0, plaus_errors, plaus_warnings)
    summary_errors.extend(plaus_errors)
    summary_warnings.extend(plaus_warnings)

    # ── Gate 7: affiliate_links ──────────────────────────────────────────────
    aff_errors: list[str] = []
    for p in prod_list:
        if p["affiliate_link_type"] != "confirmed":
            aff_errors.append(
                f"itemid {p['itemid']} ไม่มี confirmed affiliate link "
                f"(type: {p['affiliate_link_type']})"
            )
    gates["affiliate_links"] = _gate(len(aff_errors) == 0, aff_errors)
    summary_errors.extend(aff_errors)

    # ── Gate 8: content_consistency ─────────────────────────────────────────
    try:
        cc_result = validate_content_consistency(article_id)
        cc_errors: list[str] = []
        if not cc_result["consistent"]:
            stale_str = ", ".join(cc_result["stale_items"][:5])
            cc_errors.append(f"Stale content items: {stale_str}")
        gates["content_consistency"] = _gate(
            cc_result["consistent"], cc_errors, [],
            {"stale_items": cc_result["stale_items"]}
        )
        summary_errors.extend(cc_errors)
    except Exception as exc:
        gates["content_consistency"] = _gate(False, [f"Error: {exc}"])
        summary_errors.append(f"content_consistency error: {exc}")

    # ── Gate 9: feature_copy ────────────────────────────────────────────────
    try:
        copy_offenders = check_content_feature_copy(keyword, content_md)
        copy_warnings: list[str] = [f"Blocked phrase found: '{p}'" for p in copy_offenders]
        gates["feature_copy"] = _gate(True, [], copy_warnings)
        summary_warnings.extend(copy_warnings)
    except Exception as exc:
        gates["feature_copy"] = _gate(True, [], [f"Error checking feature copy: {exc}"])

    # ── Gate 10: title_duplication ───────────────────────────────────────────
    if dup_title_ids:
        tdup_errors = [f"Title ซ้ำกับ article_id: {', '.join(dup_title_ids)}"]
        gates["title_duplication"] = _gate(False, tdup_errors)
        summary_errors.extend(tdup_errors)
    else:
        gates["title_duplication"] = _gate(True, [])

    # ── Gate 11: stale_prose (reuse content_consistency output) ─────────────
    # Already captured in gate 8; re-check for prose-specific stale items
    try:
        stale_items = cc_result.get("stale_items", []) if "cc_result" in dir() else []
        stale_prose_errors: list[str] = []
        if stale_items:
            stale_prose_errors.append(
                f"Prose contains {len(stale_items)} stale reference(s): "
                + ", ".join(stale_items[:5])
            )
        gates["stale_prose"] = _gate(
            len(stale_prose_errors) == 0, stale_prose_errors, [],
            {"stale_count": len(stale_items)}
        )
        summary_errors.extend(stale_prose_errors)
    except Exception:
        gates["stale_prose"] = _gate(True, [], [], {})

    # ── Per-product gate results ─────────────────────────────────────────────
    for p in prod_list:
        title_clean = clean_display_title(p["product_title"])
        _, cap_reason_p, cap_ev_p = check_capacity_relevance(
            keyword, p["product_title"], p["_desc"], p["_attrs"]
        )
        _, spec_reason_p, spec_ev_p = check_product_spec(
            keyword, p["product_title"], p["_desc"], p["_attrs"]
        )
        rel_ok_p, rel_reason_p = check_product_relevance(keyword, p["product_title"])

        # Variant plausibility evidence for this specific product
        plaus_ok_p, plaus_reason_p, plaus_ev_p = check_variant_price_plausibility(
            p["product_title"], float(p["sale_price"]), p["_model_names"], keyword
        )
        is_mv = plaus_ev_p.get("is_multivariant", False)
        variant_evidence = {
            "is_multivariant":         is_mv,
            "selected_capacity":       plaus_ev_p.get("capacity_detected", 0),
            "displayed_price_variant": p["sale_price"],
            "variant_verified":        False,  # cannot verify without user action
            "variants":                plaus_ev_p.get("variants", []),
            "evidence_source":         "model_names" if is_mv else "single_variant",
            "evidence_note": (
                "Multi-variant listing — ตรวจว่า affiliate link ชี้ไปยัง variant ที่ถูกต้อง"
                if is_mv else "Single-variant — ไม่จำเป็นต้องตรวจ variant"
            ),
        }

        prod_gate_results = {
            "product_type_relevance": {"passed": rel_ok_p, "reason": rel_reason_p},
            "spec_relevance": {
                "passed": spec_ev_p.get("watt_max", 0) >= 0,
                "watt_max": spec_ev_p.get("watt_max", 0),
                "watt_source": spec_ev_p.get("watt_source", "none"),
            },
            "capacity_relevance": {
                "passed": not cap_reason_p.startswith("ความจุ"),
                "capacity_max": cap_ev_p.get("capacity_max", 0),
                "source": cap_ev_p.get("capacity_source", "none"),
            },
            "affiliate_link": {
                "passed": p["affiliate_link_type"] == "confirmed",
                "type": p["affiliate_link_type"],
            },
            "variant_plausibility": {
                "passed":   plaus_ok_p,
                "reason":   plaus_reason_p,
                "floor_used": plaus_ev_p.get("floor_used", 0),
            },
        }

        products_out.append({
            "rank":             p["rank"],
            "itemid":           p["itemid"],
            "shopid":           p["shopid"],
            "raw_title":        p["product_title"],
            "display_title":    title_clean["display_title"],
            "price":            p["sale_price"],
            "affiliate_link":   p["affiliate_link"],
            "affiliate_link_type": p["affiliate_link_type"],
            "capacity_evidence": str(cap_ev_p.get("capacity_max") or ""),
            "spec_evidence":    str(spec_ev_p.get("watt_max") or ""),
            "flags":            title_clean["flags"],
            "gate_results":     prod_gate_results,
            "variant_evidence": variant_evidence,
        })

    # ── Gate 12: editorial_brief_alignment ───────────────────────────────────
    try:
        from shopee_engine.editorial_brief import get_brief_for_keyword, get_brief_for_article
        brief = get_brief_for_keyword(keyword) or get_brief_for_article(article_id)
        if brief is None:
            gates["editorial_brief_alignment"] = _gate(
                False,
                ["ไม่มี Editorial Brief — สร้างด้วย /seo-brief-create"],
            )
            summary_errors.append("ไม่มี Editorial Brief")
        else:
            brief_errors: list[str] = []
            brief_warnings: list[str] = []
            brief_status = brief.get("brief_status", "draft")
            if brief_status != "approved":
                brief_errors.append(f"Brief status = '{brief_status}' (ต้อง approved)")

            # must_avoid: check if any forbidden phrase appears in content_md
            must_avoid = brief.get("must_avoid") or []
            for phrase in must_avoid:
                if phrase and phrase.lower() in content_md.lower():
                    brief_errors.append(f"Forbidden phrase in content: '{phrase}'")

            # must_compare_attributes: check that each attribute label appears
            must_compare = brief.get("must_compare_attributes") or []
            for attr in must_compare:
                if attr and attr not in content_md:
                    brief_warnings.append(f"Compare attribute missing from content: '{attr}'")

            gates["editorial_brief_alignment"] = _gate(
                len(brief_errors) == 0,
                brief_errors,
                brief_warnings,
                {
                    "brief_id":     brief.get("brief_id", ""),
                    "brief_status": brief_status,
                    "must_avoid_checked":   len(must_avoid),
                    "must_compare_checked": len(must_compare),
                },
            )
            summary_errors.extend(brief_errors)
            summary_warnings.extend(brief_warnings)
    except Exception as exc:
        gates["editorial_brief_alignment"] = _gate(True, [], [f"Brief check skipped: {exc}"])

    # ── Overall pass/fail ────────────────────────────────────────────────────
    all_passed = all(g["passed"] for g in gates.values())

    return {
        "article_id":       article_id,
        "passed":           all_passed,
        "gates":            gates,
        "summary_errors":   summary_errors,
        "summary_warnings": summary_warnings,
        "article_meta":     article_meta,
        "products":         products_out,
    }


# ---------------------------------------------------------------------------
# build_staging_html
# ---------------------------------------------------------------------------

def build_staging_html(article_id: str) -> dict:
    """Export article HTML to exports/staging/{article_id}.html for visual inspection.

    Returns:
        {"success": bool, "html_path": str, "html_content": str, "error": str|None}
    """
    preview = generate_preview_body(article_id)
    if not preview.get("success"):
        return {
            "success":      False,
            "html_path":    "",
            "html_content": "",
            "error":        preview.get("error", "generate_preview_body failed"),
        }

    body_md = preview.get("body", "")

    # Try to convert markdown to HTML; fall back to <pre> wrapping
    html_body = _md_to_html(body_md)

    # Load article title for the HTML template
    art_title = article_id
    try:
        con = _connect(read_only=True)
        row = con.execute(
            f"SELECT title FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
        ).fetchone()
        con.close()
        if row:
            art_title = str(row[0] or article_id)
    except Exception:
        pass

    html_content = _wrap_html(art_title, html_body, article_id)

    staging_path = _staging_dir() / f"{article_id}.html"
    try:
        staging_path.write_text(html_content, encoding="utf-8")
    except Exception as exc:
        return {
            "success":      False,
            "html_path":    str(staging_path),
            "html_content": html_content,
            "error":        f"Write error: {exc}",
        }

    return {
        "success":      True,
        "html_path":    str(staging_path),
        "html_content": html_content,
        "error":        None,
    }


def _md_to_html(md_text: str) -> str:
    """Convert markdown to HTML. Falls back to <pre> if markdown library unavailable."""
    try:
        import markdown as _markdown  # type: ignore
        return _markdown.markdown(
            md_text,
            extensions=["tables", "fenced_code"],
        )
    except ImportError:
        pass

    # Minimal fallback: convert most common markdown constructs
    html = md_text

    # Convert ### headings
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$",  r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$",   r"<h1>\1</h1>", html, flags=re.MULTILINE)

    # Bold
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)

    # Italic
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)

    # Strikethrough ~~text~~
    html = re.sub(r"~~(.+?)~~", r"<del>\1</del>", html)

    # Table rows (basic)
    html = re.sub(r"^\|(.+)\|$", lambda m: "<tr>" + "".join(
        f"<td>{c.strip()}</td>" for c in m.group(1).split("|")
    ) + "</tr>", html, flags=re.MULTILINE)

    # Separator lines (---)
    html = re.sub(r"^---+$", "<hr>", html, flags=re.MULTILINE)

    # Newlines to <br> for non-tag lines
    lines = html.split("\n")
    result_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("<"):
            result_lines.append(f"<p>{stripped}</p>")
        else:
            result_lines.append(line)
    html = "\n".join(result_lines)

    return html


def _wrap_html(title: str, body: str, article_id: str) -> str:
    """Wrap HTML body in a minimal HTML template."""
    return f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: sans-serif; max-width: 900px; margin: 0 auto; padding: 2rem; }}
    h1 {{ border-bottom: 2px solid #e44d26; padding-bottom: 0.5rem; }}
    h2 {{ color: #333; }}
    h3 {{ color: #555; }}
    table {{ border-collapse: collapse; width: 100%; }}
    td, th {{ border: 1px solid #ddd; padding: 8px; }}
    .affiliate-btn {{ background: #ee4d2d; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; display: inline-block; margin: 4px 0; }}
    hr {{ border: none; border-top: 1px solid #eee; margin: 2rem 0; }}
    img {{ max-width: 200px; }}
  </style>
</head>
<body>
  <p style="color: #999; font-size: 0.85rem;">Staging preview — article_id: <code>{article_id}</code></p>
  <h1>{title}</h1>
  {body}
</body>
</html>"""


# ---------------------------------------------------------------------------
# crawl_staging_html
# ---------------------------------------------------------------------------

def crawl_staging_html(article_id: str, html_content: str) -> dict:
    """Validate HTML content against DB expectations.

    Returns:
        {"passed": bool, "checks": dict[str, {"passed": bool, "detail": str}]}
    """
    checks: dict[str, dict] = {}

    # Load DB data for comparison
    products_db: list[dict] = []
    art_title_db = ""

    try:
        con = _connect(read_only=True)
        row = con.execute(
            f"SELECT title FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
        ).fetchone()
        if row:
            art_title_db = str(row[0] or "")

        prods_df = con.execute(
            f"SELECT product_title, sale_price, affiliate_link, affiliate_link_type "
            f"FROM {SEO_ARTICLE_PRODUCTS_TABLE} WHERE article_id = ? ORDER BY rank_in_article",
            [article_id],
        ).fetchdf()
        con.close()
        for _, r in prods_df.iterrows():
            products_db.append({
                "title":              str(r.get("product_title") or ""),
                "sale_price":         int(r.get("sale_price") or 0),
                "affiliate_link":     str(r.get("affiliate_link") or ""),
                "affiliate_link_type": str(r.get("affiliate_link_type") or "none"),
            })
    except Exception as exc:
        try:
            con.close()
        except Exception:
            pass
        return {
            "passed": False,
            "checks": {"db_load": {"passed": False, "detail": f"DB error: {exc}"}},
        }

    # Determine expected related articles using the same logic as the export pipeline
    try:
        from shopee_engine.seo_engine import get_related_articles
        related_articles_expected = get_related_articles(article_id, limit=4)
        related_count = len(related_articles_expected)
    except Exception:
        related_count = 0

    product_count_db = len(products_db)

    # ── Check 1: Exactly one H1 that matches article title ─────────────────
    h1_all = re.findall(r"<h1[^>]*>(.*?)</h1>", html_content, re.IGNORECASE | re.DOTALL)
    h1_count = len(h1_all)
    if h1_count == 0:
        checks["h1_exists"] = {"passed": False, "detail": "No <h1> tag found in HTML"}
    elif h1_count > 1:
        # Strip tags from each h1 for reporting
        h1_texts = [re.sub(r"<[^>]+>", "", h).strip()[:50] for h in h1_all]
        checks["h1_exists"] = {
            "passed": False,
            "detail": f"Multiple H1 tags found ({h1_count}): {h1_texts}",
        }
    else:
        h1_text = re.sub(r"<[^>]+>", "", h1_all[0]).strip()
        if art_title_db and art_title_db.lower()[:60] not in h1_text.lower():
            checks["h1_exists"] = {
                "passed": False,
                "detail": f"H1 '{h1_text[:60]}' does not match title '{art_title_db[:60]}'",
            }
        else:
            checks["h1_exists"] = {"passed": True, "detail": f"H1 found: {h1_text[:60]}"}

    # ── Check 1b: Heading hierarchy — no skipped levels ──────────────────────
    heading_tags = re.findall(r"<h([1-6])[^>]*>", html_content, re.IGNORECASE)
    heading_levels = [int(t) for t in heading_tags]
    hierarchy_errors: list[str] = []
    for i in range(1, len(heading_levels)):
        diff = heading_levels[i] - heading_levels[i - 1]
        if diff > 1:
            hierarchy_errors.append(
                f"H{heading_levels[i-1]}→H{heading_levels[i]} (skips level)"
            )
    checks["heading_hierarchy"] = {
        "passed": len(hierarchy_errors) == 0,
        "detail": (
            f"Heading jumps: {', '.join(hierarchy_errors[:5])}"
            if hierarchy_errors
            else f"Heading hierarchy ok: {heading_levels}"
        ),
    }

    # ── Check 2: Product count in HTML matches DB count ──────────────────────
    aff_btn_count = len(re.findall(r'class="affiliate-btn"', html_content, re.IGNORECASE))
    if aff_btn_count == product_count_db:
        checks["product_count"] = {
            "passed": True,
            "detail": f"Found {aff_btn_count} affiliate-btn matches DB ({product_count_db} products)",
        }
    else:
        checks["product_count"] = {
            "passed": False,
            "detail": (
                f"affiliate-btn count ({aff_btn_count}) != DB product count ({product_count_db})"
            ),
        }

    # ── Check 3: Each product's price appears in HTML ─────────────────────────
    price_check_passed = True
    price_check_detail = []
    for p in products_db:
        price_val = p["sale_price"]
        if price_val > 0:
            price_str_plain = str(price_val)
            price_str_comma = f"{price_val:,}"
            pattern = f"฿{price_str_plain}|฿{price_str_comma}"
            if not re.search(pattern, html_content):
                price_check_passed = False
                price_check_detail.append(f"฿{price_val} missing")
    checks["product_prices"] = {
        "passed": price_check_passed,
        "detail": ", ".join(price_check_detail) if price_check_detail else f"All {product_count_db} prices found",
    }

    # ── Check 4: Each product's name appears in HTML ──────────────────────────
    # Use a word-safe prefix: up to 25 chars, stopping at last word boundary.
    # This avoids false negatives when the title starts with a bracket tag that
    # gets stripped in the display, and avoids cutting inside a model code.
    name_check_passed = True
    name_check_detail = []
    for p in products_db:
        raw = p["title"]
        # Build a search key that stops at a word boundary within the first 25 chars
        m = re.match(r'^.{1,25}\b', raw)
        search_key = (m.group() if m else raw[:25]).strip()
        if search_key and search_key not in html_content:
            name_check_passed = False
            name_check_detail.append(f"'{search_key}' missing")
    checks["product_names"] = {
        "passed": name_check_passed,
        "detail": ", ".join(name_check_detail) if name_check_detail else "All product names found",
    }

    # ── Check 5: Related articles section present (if applicable) ────────────
    if related_count > 0:
        related_present = bool(
            re.search(r"บทความที่เกี่ยวข้อง|related.articles", html_content, re.IGNORECASE)
        )
        checks["related_articles"] = {
            "passed": related_present,
            "detail": (
                "Related articles section found"
                if related_present
                else f"Missing related articles section ({related_count} related expected)"
            ),
        }
    else:
        checks["related_articles"] = {
            "passed": True,
            "detail": "No related articles expected — section not required",
        }

    # ── Check 6: No unrendered Markdown or broken artifacts ─────────────────
    artifacts = []
    if "[object Object]" in html_content:
        artifacts.append("[object Object]")
    if "{ARTICLE_ID}" in html_content:
        artifacts.append("{ARTICLE_ID}")
    if "lorem ipsum" in html_content.lower():
        artifacts.append("lorem ipsum")
    # Unresolved template tokens e.g. {KEYWORD}, {PRODUCT_NAME}
    tok = re.search(r'\{[A-Z][A-Z_]{2,}\}', html_content)
    if tok:
        artifacts.append(f"unresolved template token: {tok.group()}")
    # Raw Markdown image syntax  ![alt](url)  → should be <img src="...">
    if re.search(r'!\[[^\]]*\]\([^)]+\)', html_content):
        artifacts.append("raw Markdown image syntax: ![...](url)")
    # Raw Markdown strikethrough ~~text~~ not converted to <del>
    if re.search(r'~~[^~\n]{1,60}~~', html_content):
        artifacts.append("raw Markdown strikethrough: ~~...~~")
    # Raw Markdown bold **text** not converted to <strong>
    if re.search(r'\*\*[^*\n]{1,80}\*\*', html_content):
        artifacts.append("raw Markdown bold: **...**")
    # Raw blockquote marker: <p>&gt; text</p> or <p>> text  (fallback renderer artefact)
    if re.search(r'<p>\s*(?:&gt;|>)\s+\S', html_content):
        artifacts.append("raw Markdown blockquote: > ...")
    # Markdown table separator cells: <td>---</td> or <td>:---:</td>
    if re.search(r'<td[^>]*>\s*:?-{2,}:?\s*</td>', html_content, re.IGNORECASE):
        artifacts.append("Markdown table separator in <td>")
    # <tr> elements present but no <table> wrapper → orphaned table rows
    if (re.search(r'<tr[\s>]', html_content, re.IGNORECASE)
            and not re.search(r'<table[\s>]', html_content, re.IGNORECASE)):
        artifacts.append("orphaned <tr> without <table> wrapper")

    checks["no_artifacts"] = {
        "passed": len(artifacts) == 0,
        "detail": f"Artifacts found: {artifacts}" if artifacts else "No broken artifacts found",
    }

    # ── Check 7: affiliate-btn links count matches product count ─────────────
    checks["affiliate_btn_count"] = {
        "passed": aff_btn_count == product_count_db,
        "detail": f"{aff_btn_count} affiliate-btn found, expected {product_count_db}",
    }

    # ── Check 8: Affiliate link href contains shopee.co.th domain ───────────
    aff_hrefs = re.findall(r'class="affiliate-btn"[^>]*href="([^"]+)"', html_content, re.IGNORECASE)
    aff_hrefs += re.findall(r'href="([^"]+)"[^>]*class="affiliate-btn"', html_content, re.IGNORECASE)
    aff_hrefs = list(dict.fromkeys(aff_hrefs))

    bad_hrefs = [h for h in aff_hrefs if "shopee.co.th" not in h and "shope.ee" not in h]
    checks["affiliate_link_domain"] = {
        "passed": len(bad_hrefs) == 0 or len(aff_hrefs) == 0,
        "detail": (
            f"Bad domains: {bad_hrefs[:3]}"
            if bad_hrefs
            else f"All {len(aff_hrefs)} affiliate links point to Shopee domain"
        ),
    }

    all_passed = all(c["passed"] for c in checks.values())
    return {"passed": all_passed, "checks": checks}


# ---------------------------------------------------------------------------
# generate_preflight_json
# ---------------------------------------------------------------------------

def generate_preflight_json(
    article_id: str,
    preflight_result: dict,
    html_result: dict,
    crawl_result: dict,
) -> dict:
    """Generate machine-readable JSON report combining all preflight results."""
    meta = preflight_result.get("article_meta", {})
    products_in = preflight_result.get("products", [])

    # Build per-product rows with clean display title and variant evidence
    products_out: list[dict] = []
    for p in products_in:
        clean = clean_display_title(p.get("raw_title", ""))
        products_out.append({
            "rank":               p.get("rank", 0),
            "itemid":             p.get("itemid", 0),
            "shopid":             p.get("shopid", 0),
            "raw_title":          p.get("raw_title", ""),
            "display_title":      clean["display_title"],
            "price":              p.get("price", 0),
            "capacity_evidence":  p.get("capacity_evidence", ""),
            "spec_evidence":      p.get("spec_evidence", ""),
            "affiliate_link_status": p.get("affiliate_link_type", "none"),
            "affiliate_link":     p.get("affiliate_link", ""),
            "gate_results":       p.get("gate_results", {}),
            "variant_evidence":   p.get("variant_evidence", {}),
            "flags":              clean["flags"] + p.get("flags", []),
        })

    gates = preflight_result.get("gates", {})
    brief_gate = gates.get("editorial_brief_alignment", {})

    return {
        "article_id":        article_id,
        "title":             meta.get("title", ""),
        "status":            meta.get("status", ""),
        "preflight_passed":  preflight_result.get("passed", False),
        "html_crawl_passed": crawl_result.get("passed", False),
        "products":          products_out,
        "gates":             gates,
        "html_checks":       crawl_result.get("checks", {}),
        "warnings":          preflight_result.get("summary_warnings", []),
        "errors":            preflight_result.get("summary_errors", []),
        "editorial_brief_alignment": {
            "passed":       brief_gate.get("passed", False),
            "brief_id":     (brief_gate.get("evidence") or {}).get("brief_id", ""),
            "brief_status": (brief_gate.get("evidence") or {}).get("brief_status", ""),
            "errors":       brief_gate.get("errors", []),
            "warnings":     brief_gate.get("warnings", []),
        },
        "generated_at":      datetime.now(timezone.utc).isoformat(),
    }
