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
        )
        article = get_article(article_id)
        if not article:
            return {"success": False, "error": f"Article '{article_id}' not found"}

        product_count = get_article_product_count(article_id)
        validation = validate_article_for_publish(article_id)

        return {
            "success":       True,
            "article":       article,
            "product_count": product_count,
            "validation":    validation,
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
