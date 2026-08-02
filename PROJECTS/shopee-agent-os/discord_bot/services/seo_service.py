"""SEO service — wraps shopee_engine.seo_engine."""

from __future__ import annotations


def get_keyword_opportunities(
    category: str | None = None,
    limit: int = 10,
) -> dict:
    try:
        from shopee_engine.seo_engine import find_keyword_opportunities
        ideas = find_keyword_opportunities(category=category, top=limit)
        return {"success": True, "data": ideas, "total": len(ideas)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_article_draft(
    keyword: str = "",
    category: str | None = None,
    product_count: int = 5,
    idea_id: str | None = None,
) -> dict:
    try:
        from shopee_engine.seo_engine import check_duplicate_draft, generate_article_draft
        # Duplicate check: use cached keyword if idea_id given
        check_kw = keyword
        if idea_id and not keyword:
            from shopee_engine.seo_engine import _idea_cache
            cached = _idea_cache.get(idea_id, {})
            check_kw = cached.get("keyword", "")
        if check_kw:
            duplicate = check_duplicate_draft(check_kw)
            if duplicate:
                return {
                    "success":          False,
                    "duplicate":        True,
                    "existing_id":      str(duplicate.get("article_id", "")),
                    "existing_status":  str(duplicate.get("status", "")),
                    "existing_updated": str(duplicate.get("updated_at", "")),
                    "error": (
                        f"บทความสำหรับ '{check_kw}' มีอยู่แล้ว "
                        f"(article_id: {duplicate['article_id']}, status: {duplicate['status']})"
                    ),
                }
        result = generate_article_draft(
            keyword=keyword,
            category=category,
            top_products=product_count,
            idea_id=idea_id,
        )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def preview_article(article_id: str) -> dict:
    try:
        from shopee_engine.seo_engine import (
            get_article,
            get_article_product_count,
            validate_article_for_publish,
            get_products_for_preview,
        )
        from shopee_engine.article_exporter import generate_preview_body

        article = get_article(article_id)
        if not article:
            return {"success": False, "error": f"Article '{article_id}' not found"}

        product_count    = get_article_product_count(article_id)
        validation       = validate_article_for_publish(article_id)
        preview          = generate_preview_body(article_id)
        products_preview = get_products_for_preview(article_id)

        return {
            "success":        True,
            "article":        article,
            "product_count":  product_count,
            "validation":     validation,
            "preview_body":   preview.get("body", "") if preview.get("success") else "",
            "products":       products_preview,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def review_article_action(
    article_id: str,
    action: str,
    note: str = "",
) -> dict:
    """approve → draft→reviewed; return_to_draft → reviewed→draft."""
    try:
        from shopee_engine.seo_engine import review_article
        return review_article(article_id=article_id, action=action, note=note)
    except Exception as e:
        return {"success": False, "error": str(e)}


def publish_article(article_id: str) -> dict:
    try:
        from shopee_engine.git_publish_service import safe_publish
        return safe_publish(article_id)
    except Exception as e:
        return {"success": False, "error": str(e)}


def refresh_article(article_id: str) -> dict:
    try:
        from shopee_engine.seo_engine import (
            _connect,
            SEO_ARTICLES_TABLE,
            refresh_article_products,
            validate_status_transition,
            _init_seo_tables,
        )
        # Load current status
        con = _connect(read_only=True)
        try:
            row = con.execute(
                f"SELECT status FROM {SEO_ARTICLES_TABLE} WHERE article_id = ?", [article_id]
            ).fetchone()
            con.close()
        except Exception as exc:
            con.close()
            return {"success": False, "error": str(exc)}

        if not row:
            return {"success": False, "error": f"Article '{article_id}' not found"}

        current_status = row[0]
        demoted = False

        # If published, demote to reviewed before refresh
        if current_status == "published":
            con_w = _connect(read_only=False)
            try:
                _init_seo_tables(con_w)
                con_w.execute(
                    f"UPDATE {SEO_ARTICLES_TABLE} SET status='reviewed', updated_at=CURRENT_TIMESTAMP WHERE article_id=?",
                    [article_id],
                )
                con_w.close()
                demoted = True
            except Exception as exc:
                con_w.close()
                return {"success": False, "error": str(exc)}

        result = refresh_article_products(article_id)
        result["article_id"]    = article_id
        result["previous_status"] = current_status
        result["demoted_to_reviewed"] = demoted
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def unpublish_article(article_id: str) -> dict:
    try:
        from shopee_engine.git_publish_service import safe_unpublish
        return safe_unpublish(article_id)
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_link_status(article_id: str) -> dict:
    """Return per-product affiliate link status for a draft article."""
    try:
        from shopee_engine.seo_engine import get_article_link_status
        return get_article_link_status(article_id)
    except Exception as e:
        return {"success": False, "error": str(e)}


def export_missing_links_csv(article_id: str) -> bytes | None:
    """Return CSV bytes for products missing confirmed affiliate links, or None if all confirmed."""
    import csv
    import io
    result = get_link_status(article_id)
    if not result.get("success"):
        return None
    missing = result.get("missing_products", [])
    if not missing:
        return None

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "article_id", "rank", "itemid", "shopid",
        "product_title", "sale_price", "product_url", "affiliate_url",
    ])
    writer.writeheader()
    for p in missing:
        writer.writerow({
            "article_id":    article_id,
            "rank":          p["rank"],
            "itemid":        p["itemid"],
            "shopid":        p["shopid"],
            "product_title": p["product_title"],
            "sale_price":    p["sale_price"],
            "product_url":   p["product_url"],
            "affiliate_url": "",
        })
    return buf.getvalue().encode("utf-8")


def list_seo_articles(
    status: str | None = None,
    limit: int = 10,
) -> dict:
    try:
        from shopee_engine.seo_engine import get_article_stats, list_articles
        articles = list_articles(status=status, limit=limit)
        stats = get_article_stats()
        return {"success": True, "data": articles, "total": len(articles), "stats": stats}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Article editing
# ---------------------------------------------------------------------------

def edit_article_field(
    article_id: str,
    field: str,
    value: str,
    editor: str = "discord",
) -> dict:
    try:
        from shopee_engine.seo_engine import edit_article_field as _edit
        return _edit(article_id, field, value, editor)
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Product management
# ---------------------------------------------------------------------------

def add_product(article_id: str, itemid: int, rank: int | None = None) -> dict:
    try:
        from shopee_engine.seo_engine import add_product_to_article
        return add_product_to_article(article_id, itemid, rank)
    except Exception as e:
        return {"success": False, "error": str(e)}


def remove_product(article_id: str, itemid: int) -> dict:
    try:
        from shopee_engine.seo_engine import remove_product_from_article
        return remove_product_from_article(article_id, itemid)
    except Exception as e:
        return {"success": False, "error": str(e)}


def replace_product(article_id: str, old_itemid: int, new_itemid: int) -> dict:
    try:
        from shopee_engine.seo_engine import replace_product_in_article
        return replace_product_in_article(article_id, old_itemid, new_itemid)
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Republish
# ---------------------------------------------------------------------------

def republish_article(article_id: str) -> dict:
    try:
        from shopee_engine.git_publish_service import safe_republish
        return safe_republish(article_id)
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Version history & rollback
# ---------------------------------------------------------------------------

def get_article_history(article_id: str) -> dict:
    try:
        from shopee_engine.seo_engine import get_article_history as _history
        revisions = _history(article_id)
        return {"success": True, "article_id": article_id, "revisions": revisions}
    except Exception as e:
        return {"success": False, "error": str(e)}


def rollback_article(article_id: str, revision_number: int) -> dict:
    try:
        from shopee_engine.seo_engine import rollback_article as _rollback
        return _rollback(article_id, revision_number)
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Editorial Team upgrade
# ---------------------------------------------------------------------------

def upgrade_article_prose(article_id: str) -> dict:
    """Regenerate article prose with the 7-persona editorial team.

    Saves a revision first, then rewrites prose sections in content_md.
    Does NOT republish — user reviews via /seo-preview then /seo-republish.
    """
    try:
        import json
        from shopee_engine.seo_engine import (
            SEO_ARTICLES_TABLE,
            _connect,
            _init_seo_tables,
            _update_prose_section,
            get_article,
            save_revision,
        )
        from shopee_engine.article_exporter import (
            SEO_ARTICLE_PRODUCTS_TABLE,
            _extract_prose,
            _load_enriched_products,
        )
        from shopee_engine.editorial_team import generate_article_content

        # 1. Load article
        article = get_article(article_id)
        if not article:
            return {"success": False, "error": f"Article '{article_id}' not found"}

        # 2. Load products from DB
        con_r = _connect(read_only=True)
        try:
            products = _load_enriched_products(article_id, con_r)
        finally:
            con_r.close()

        if not products:
            return {"success": False, "error": "No active products found for this article"}

        keyword  = str(article.get("keyword", ""))
        category = str(article.get("category", ""))

        # 3. Capture old intro for diff display
        old_prose = _extract_prose(str(article.get("content_md", "")))
        old_intro = old_prose.get("บทนำ", "")[:200]

        # 4. Save revision before any change
        rev_num = save_revision(article_id, "Before upgrade: editorial team", "discord")

        # 5. Run editorial team
        editorial = generate_article_content(keyword, category, products)
        if not editorial["_success"]:
            return {
                "success": False,
                "error": f"Editorial team failed: {editorial.get('_error', 'unknown')}",
            }

        # 6. Build new content_md — replace prose sections + append highlights comment
        content_md = str(article.get("content_md", ""))

        # Update/insert each prose section
        sections_updated = []
        for section, key in [
            ("บทนำ",                 "intro"),
            ("บริบทการซื้อ",         "buying_scenario"),
            ("คำแนะนำการเลือกซื้อ", "buying_guide"),
            ("บทสรุป",              "summary"),
        ]:
            value = editorial.get(key, "").strip()
            if not value:
                continue
            content_md = _update_prose_section(content_md, section, value)
            sections_updated.append(section)

        # Append for_whom / not_for_whom inside บริบทการซื้อ block if both exist
        for_whom     = editorial.get("for_whom", "").strip()
        not_for_whom = editorial.get("not_for_whom", "").strip()
        if for_whom or not_for_whom:
            extras = ""
            if for_whom:
                extras += f"\n\n**เหมาะกับ:**\n\n{for_whom}"
            if not_for_whom:
                extras += f"\n\n**อาจไม่ใช่ตัวเลือกที่ดีถ้า:**\n\n{not_for_whom}"
            # Append extras after the บริบทการซื้อ section
            content_md = _update_prose_section(
                content_md,
                "บริบทการซื้อ",
                (editorial.get("buying_scenario", "") + extras).strip(),
            )

        # Replace or append editorial product_highlights comment
        highlights = editorial.get("product_highlights", {})
        if highlights:
            import re as _re
            comment_block = (
                f"<!-- editorial:product_highlights\n"
                f"{json.dumps(highlights, ensure_ascii=False, indent=2)}\n"
                f"-->"
            )
            # Remove old comment if present
            content_md = _re.sub(
                r"<!--\s*editorial:product_highlights\s*\n\{.*?\}\s*-->",
                "",
                content_md,
                flags=_re.DOTALL,
            ).rstrip()
            content_md += f"\n{comment_block}\n"

        # 7. Persist to DB
        con_w = _connect(read_only=False)
        try:
            _init_seo_tables(con_w)
            con_w.execute(
                f"UPDATE {SEO_ARTICLES_TABLE} "
                f"SET content_md = ?, updated_at = CURRENT_TIMESTAMP "
                f"WHERE article_id = ?",
                [content_md, article_id],
            )
            con_w.close()
        except Exception as exc:
            con_w.close()
            return {"success": False, "error": f"DB update failed: {exc}"}

        new_intro = editorial.get("intro", "")[:200]
        current_status = str(article.get("status", ""))

        return {
            "success":          True,
            "article_id":       article_id,
            "revision_saved":   rev_num,
            "sections_added":   sections_updated,
            "model_used":       editorial.get("_model", ""),
            "old_intro":        old_intro,
            "new_intro":        new_intro,
            "has_buying_context": bool(editorial.get("buying_scenario")),
            "has_highlights":   bool(highlights),
            "current_status":   current_status,
            "requires_republish": current_status in ("published", "reviewed"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_preflight_check(article_id: str) -> dict:
    """Run full preflight QA pipeline — gates + staging HTML + crawl + JSON report."""
    try:
        from shopee_engine.preflight import (
            run_preflight,
            build_staging_html,
            crawl_staging_html,
            generate_preflight_json,
        )
        from shopee_engine.seo_engine import update_preflight_status

        pf_result    = run_preflight(article_id)
        html_result  = build_staging_html(article_id)
        html_content = html_result.get("html_content", "")
        crawl_result = crawl_staging_html(article_id, html_content)

        json_report = generate_preflight_json(article_id, pf_result, html_result, crawl_result)

        # Persist result
        all_passed = pf_result["passed"] and crawl_result.get("passed", False)
        update_preflight_status(article_id, all_passed)

        return {
            "success":      True,
            "preflight":    pf_result,
            "html_result":  html_result,
            "crawl_result": crawl_result,
            "json_report":  json_report,
            "all_passed":   all_passed,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Editorial Brief services
# ---------------------------------------------------------------------------

def create_brief(keyword: str, markdown_text: str, source: str = "user") -> dict:
    try:
        from shopee_engine.editorial_brief import parse_brief_markdown, create_brief as _create
        parsed = parse_brief_markdown(markdown_text)
        # keyword from args takes priority over parsed value
        parsed.pop("keyword", None)
        brief = _create(keyword=keyword, brief_data=parsed, source=source)
        return {"success": True, "brief": brief}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_brief(brief_id: str) -> dict:
    try:
        from shopee_engine.editorial_brief import get_brief_by_id
        brief = get_brief_by_id(brief_id)
        if not brief:
            return {"success": False, "error": f"Brief `{brief_id}` ไม่พบ"}
        return {"success": True, "brief": brief}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_brief_for_keyword(keyword: str) -> dict:
    try:
        from shopee_engine.editorial_brief import get_brief_for_keyword as _get
        brief = _get(keyword)
        if not brief:
            return {"success": False, "error": f"ไม่มี brief สำหรับ keyword: {keyword}"}
        return {"success": True, "brief": brief}
    except Exception as e:
        return {"success": False, "error": str(e)}


def approve_brief(brief_id: str) -> dict:
    try:
        from shopee_engine.editorial_brief import approve_brief as _approve
        brief = _approve(brief_id)
        return {"success": True, "brief": brief}
    except Exception as e:
        return {"success": False, "error": str(e)}


def edit_brief(brief_id: str, markdown_text: str) -> dict:
    try:
        from shopee_engine.editorial_brief import parse_brief_markdown, update_brief, get_brief_by_id
        existing = get_brief_by_id(brief_id)
        if not existing:
            return {"success": False, "error": f"Brief `{brief_id}` ไม่พบ"}
        parsed = parse_brief_markdown(markdown_text)
        parsed.pop("keyword", None)  # keyword is immutable after creation
        brief = update_brief(brief_id, parsed)
        return {"success": True, "brief": brief}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_briefs(limit: int = 20) -> dict:
    try:
        from shopee_engine.editorial_brief import list_briefs as _list
        briefs = _list(limit=limit)
        return {"success": True, "briefs": briefs}
    except Exception as e:
        return {"success": False, "error": str(e)}


def research_article(article_id: str) -> dict:
    try:
        from shopee_engine.product_research import research_article_products
        return research_article_products(article_id)
    except Exception as e:
        return {"success": False, "error": str(e)}
