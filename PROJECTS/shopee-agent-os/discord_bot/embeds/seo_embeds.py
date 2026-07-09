"""Embed builders for SEO slash commands."""

from __future__ import annotations

import discord

from discord_bot.embeds.base import make_embed


def build_ideas_embed(
    ideas: list[dict],
    category: str | None,
    limit: int,
) -> discord.Embed:
    cat_str = f" — {category}" if category else ""
    title = f"💡 SEO Article Ideas{cat_str}"

    if not ideas:
        return make_embed(
            title,
            color_key="info",
            description="ไม่พบ keyword opportunities ในหมวดนี้ ลองเพิ่ม limit หรือเปลี่ยนหมวด",
        )

    e = make_embed(
        title,
        color_key="opportunity",
        description=f"พบ **{len(ideas)}** keyword ที่มีโอกาสเขียนบทความ (เรียงตาม article opportunity score)",
    )

    for i, idea in enumerate(ideas, 1):
        kw        = idea["keyword"]
        score     = idea["opportunity_score"]
        est       = idea["estimated_products"]
        top_title = idea.get("top_product_title", "")[:40]
        top_price = idea.get("top_product_price", "")
        idea_id   = idea.get("idea_id", "")

        field_val = (
            f"**ID:** `{idea_id}` → `/seo-draft idea_id:{idea_id}`\n"
            f"**Article Opportunity Score:** {score:,.1f}\n"
            f"**สินค้าที่ตรงกัน:** {est:,} รายการ\n"
            f"**Top Product:** {top_title} ({top_price})"
        )
        e.add_field(name=f"{i}. {kw}"[:256], value=field_val[:1024], inline=False)

    return e


def build_draft_embed(result: dict) -> discord.Embed:
    keyword  = result.get("keyword", "")
    e = make_embed(
        f"✅ Draft Created: {keyword}"[:256],
        color_key="success",
    )

    e.add_field(name="Article ID", value=f"`{result['article_id']}`", inline=True)
    e.add_field(name="Status",     value="📝 draft",                  inline=True)
    e.add_field(name="Category",   value=result.get("category") or "—", inline=True)
    e.add_field(name="Title",      value=result.get("title", "")[:256], inline=False)

    confirmed = result.get("confirmed_links", 0)
    datafeed  = result.get("datafeed_links", 0)
    no_link   = result.get("products_without_link", 0)
    count     = result.get("products_count", 0)

    link_info = (
        f"✅ Confirmed: {confirmed}  "
        f"📋 Datafeed: {datafeed}  "
        f"❌ ไม่มีลิงก์: {no_link}"
    )
    e.add_field(name=f"สินค้า ({count} รายการ)", value=link_info, inline=False)

    if not result.get("has_confirmed_affiliate"):
        e.add_field(
            name="⚠️ คำเตือน Affiliate",
            value=(
                "ยังไม่มี confirmed affiliate link — "
                "ลิงก์บางส่วนเป็น datafeed (คอมมิชชันไม่รับประกัน)"
            ),
            inline=False,
        )

    ai_tag = "✅ AI" if result.get("ai_used") else "📄 Template"
    e.add_field(name="Content Source", value=ai_tag, inline=True)
    e.add_field(
        name="Next Step",
        value=f"ตรวจสอบด้วย `/seo-preview {result['article_id']}`",
        inline=True,
    )

    return e


def build_draft_duplicate_embed(keyword: str, existing: dict) -> discord.Embed:
    article_id = existing.get("article_id", "")
    status     = existing.get("status", "")
    updated_at = str(existing.get("updated_at", ""))[:20]

    e = make_embed(
        f"⚠️ Duplicate — {keyword}"[:256],
        color_key="trend",
        description=(
            f"มีบทความสำหรับ **{keyword}** อยู่แล้ว\n"
            f"ใช้ `/seo-preview {article_id}` เพื่อดูบทความ"
        ),
    )
    e.add_field(name="Article ID", value=f"`{article_id}`", inline=True)
    e.add_field(name="Status",     value=status or "—",    inline=True)
    if updated_at:
        e.add_field(name="Updated", value=updated_at, inline=True)
    e.add_field(
        name="ไม่ได้สร้างบทความใหม่",
        value="หากต้องการสร้างบทความใหม่สำหรับ keyword นี้ ให้ archive บทความเดิมก่อน",
        inline=False,
    )
    return e


def build_preview_embed(result: dict) -> discord.Embed:
    article       = result["article"]
    validation    = result["validation"]
    product_count = result["product_count"]

    title_text = str(article.get("title", ""))
    status     = str(article.get("status", "draft"))
    keyword    = str(article.get("keyword", ""))
    category   = str(article.get("category", "")) or "—"
    article_id = str(article.get("article_id", ""))
    updated_at = str(article.get("updated_at", ""))[:20]

    status_emoji = {"draft": "📝", "reviewed": "✅", "published": "🌐", "archived": "📦"}.get(status, "❓")
    color_map    = {"draft": "info", "reviewed": "success", "published": "opportunity", "archived": "error"}

    e = make_embed(
        f"👁 Preview: {title_text}"[:256],
        color_key=color_map.get(status, "info"),
        description=f"**{status_emoji} {status.upper()}** — `{article_id}`",
    )

    e.add_field(name="Keyword",  value=keyword,           inline=True)
    e.add_field(name="Category", value=category,          inline=True)
    e.add_field(name="Products", value=str(product_count), inline=True)
    e.add_field(name="Updated",  value=updated_at,        inline=True)

    errors   = validation.get("errors", [])
    warnings = validation.get("warnings", [])

    if errors:
        e.add_field(
            name="❌ Errors (บล็อก publish)",
            value="\n".join(f"• {err}" for err in errors)[:1024],
            inline=False,
        )
    if warnings:
        e.add_field(
            name="⚠️ Warnings",
            value="\n".join(f"• {w}" for w in warnings)[:1024],
            inline=False,
        )
    if not errors and not warnings:
        e.add_field(name="✅ Validation", value="ผ่านการตรวจสอบทั้งหมด", inline=False)

    # Use live-regenerated body (same pipeline as republish) — never stale stored content_md
    content_md = str(result.get("preview_body") or article.get("content_md", ""))
    body_start = content_md.find("## ")
    body_preview = content_md[body_start:body_start + 800] if body_start != -1 else content_md[:800]

    if body_preview:
        e.add_field(
            name="📄 Content Preview",
            value=f"```\n{body_preview[:900]}\n```",
            inline=False,
        )

    if len(content_md) > 1800:
        e.add_field(
            name="📎 Full Content",
            value="ไฟล์ Markdown ฉบับเต็มแนบมาพร้อมข้อความนี้",
            inline=False,
        )

    return e


def build_review_embed(result: dict) -> discord.Embed:
    action     = result.get("action", "")
    article_id = result.get("article_id", "")
    from_st    = result.get("from_status", "")
    to_st      = result.get("to_status", "")
    note       = result.get("note", "")
    warnings   = result.get("warnings", [])

    if action == "approved":
        color, emoji = "success", "✅"
        title = f"✅ Reviewed: `{article_id}`"
    else:
        color, emoji = "info", "↩️"
        title = f"↩️ Returned to Draft: `{article_id}`"

    e = make_embed(title, color_key=color,
                   description=f"{from_st} → **{to_st}**")
    e.add_field(name="Article ID", value=f"`{article_id}`", inline=True)
    e.add_field(name="Status",     value=f"{emoji} {to_st}",  inline=True)
    if note:
        e.add_field(name="Note", value=note[:1024], inline=False)
    if warnings:
        e.add_field(name="⚠️ Warnings",
                    value="\n".join(f"• {w}" for w in warnings)[:1024],
                    inline=False)
    if action == "approved":
        e.add_field(name="Next Step",
                    value=f"เผยแพร่ด้วย `/seo-publish {article_id}`",
                    inline=False)
    return e


def build_review_blocked_embed(result: dict) -> discord.Embed:
    article_id = result.get("article_id", result.get("error", "?"))
    errors   = result.get("errors", [])
    warnings = result.get("warnings", [])

    e = make_embed(f"❌ Review Blocked: `{article_id}`", color_key="error",
                   description="บทความไม่ผ่านการตรวจสอบก่อน review")
    if errors:
        e.add_field(name="❌ Errors",
                    value="\n".join(f"• {err}" for err in errors)[:1024],
                    inline=False)
    if warnings:
        e.add_field(name="⚠️ Warnings",
                    value="\n".join(f"• {w}" for w in warnings)[:1024],
                    inline=False)
    e.add_field(name="แก้ไขแล้ว", value="แก้ไขปัญหาข้างต้นแล้วลอง `/seo-review` อีกครั้ง",
                inline=False)
    return e


def build_publish_embed(result: dict) -> discord.Embed:
    dry_run    = result.get("dry_run", False)
    article_id = result.get("article_id", "")
    page_url   = result.get("page_url")
    commit_hash = result.get("commit_hash", "")
    warnings   = result.get("warnings", [])
    in_sitemap = result.get("in_sitemap", False)

    if dry_run:
        color = "info"
        title = f"🧪 Dry-Run Publish: `{article_id}`"
        desc  = result.get("message", "Dry-run complete — SEO_PUBLISH_ENABLED=false")
    else:
        color = "opportunity"
        title = f"🌐 Published: `{article_id}`"
        desc  = f"**{page_url}**" if page_url else "Published successfully"

    e = make_embed(title, color_key=color, description=desc)

    if not dry_run and commit_hash:
        e.add_field(name="Commit", value=f"`{commit_hash[:8]}`", inline=True)
    e.add_field(name="Sitemap", value="✅ included" if in_sitemap else "⏳ pending next build",
                inline=True)
    if dry_run:
        e.add_field(name="ต้องการเผยแพร่จริง",
                    value="ตั้ง `SEO_PUBLISH_ENABLED=true` ใน .env แล้วรันใหม่",
                    inline=False)
    if warnings:
        e.add_field(name="⚠️ Warnings",
                    value="\n".join(f"• {w}" for w in warnings)[:1024],
                    inline=False)
    return e


def build_publish_failed_embed(result: dict) -> discord.Embed:
    article_id  = result.get("article_id", "")
    commit_hash = result.get("commit_hash")
    error       = result.get("error", "Unknown error")

    e = make_embed(f"❌ Publish Failed: `{article_id}`", color_key="error",
                   description=error[:800])
    if commit_hash:
        e.add_field(name="⚠️ Local Commit Exists",
                    value=f"`{commit_hash[:8]}` — push failed. รัน git push ด้วยมือหรือลอง `/seo-publish` อีกครั้ง",
                    inline=False)
    e.add_field(name="Status DB", value="คงเป็น `reviewed` — ยังไม่เปลี่ยน", inline=False)
    return e


def build_refresh_embed(result: dict) -> discord.Embed:
    article_id      = result.get("article_id", "")
    updated         = result.get("updated", 0)
    not_found       = result.get("not_found", 0)
    oos             = result.get("out_of_stock", 0)
    demoted         = result.get("demoted_to_reviewed", False)
    prev_st         = result.get("previous_status", "")
    newly_confirmed = result.get("newly_confirmed", [])

    color = "trend" if (not_found or oos) else "success"
    e = make_embed(f"🔄 Refresh: `{article_id}`", color_key=color)
    e.add_field(name="Updated",       value=str(updated),    inline=True)
    e.add_field(name="Not Found",     value=str(not_found),  inline=True)
    e.add_field(name="Out of Stock",  value=str(oos),        inline=True)

    if newly_confirmed:
        names = "\n".join(
            f"✅ {p['product_title'][:50]}" for p in newly_confirmed[:5]
        )
        if len(newly_confirmed) > 5:
            names += f"\n(+{len(newly_confirmed) - 5} รายการ)"
        e.add_field(
            name=f"🎉 Newly Confirmed ({len(newly_confirmed)} รายการ)",
            value=names,
            inline=False,
        )

    if demoted:
        e.add_field(name="⚠️ Status Changed",
                    value=f"บทความถูก demote จาก `{prev_st}` → `reviewed` เพื่อรอตรวจและ publish ใหม่",
                    inline=False)
    if not_found or oos:
        e.add_field(name="ต้องดำเนินการ",
                    value="ตรวจสินค้าที่หายหรือหมดสต็อก แล้ว review ใหม่ก่อน publish",
                    inline=False)
    elif not demoted:
        e.add_field(name="✅ สถานะ", value="สินค้าทุกรายการยังคงใช้งานได้", inline=False)
    return e


def build_link_status_embed(result: dict) -> discord.Embed:
    article_id    = result.get("article_id", "")
    article_title = result.get("article_title", "")
    status        = result.get("status", "draft")
    confirmed     = result.get("confirmed_count", 0)
    datafeed      = result.get("datafeed_count", 0)
    missing       = result.get("missing_count", 0)
    total         = result.get("total_count", 0)
    all_ok        = result.get("all_confirmed", False)

    color = "success" if all_ok else "error"
    status_line = "✅ พร้อม publish" if all_ok else f"❌ ขาด {total - confirmed}/{total} confirmed links"

    e = make_embed(
        f"🔗 Link Status: `{article_id}`",
        color_key=color,
        description=f"**{article_title[:80]}**\n{status_line}",
    )
    e.add_field(name="✅ Confirmed", value=str(confirmed), inline=True)
    e.add_field(name="📋 Datafeed",  value=str(datafeed),  inline=True)
    e.add_field(name="❌ Missing",   value=str(missing),   inline=True)

    products = result.get("products", [])
    if products:
        _TYPE_ICON = {"confirmed": "✅", "datafeed": "📋", "none": "❌"}
        rows: list[str] = []
        for p in products:
            icon  = _TYPE_ICON.get(p["link_type"], "❓")
            title = p["product_title"][:32]
            price = f"฿{p['sale_price']:,}"
            rows.append(f"{icon} **{p['rank']}.** {title} ({price})")
        e.add_field(name="สินค้าทั้งหมด", value="\n".join(rows)[:1024], inline=False)

    missing_products = result.get("missing_products", [])
    if missing_products:
        cmd_lines: list[str] = []
        for p in missing_products[:5]:
            cmd_lines.append(
                f"`/affiliate-link-add` itemid:`{p['itemid']}` "
                f"— {p['product_title'][:30]}"
            )
        if len(missing_products) > 5:
            cmd_lines.append(f"(+{len(missing_products) - 5} รายการ — ดูไฟล์ CSV ที่แนบ)")
        e.add_field(
            name="คำสั่งที่ต้องใช้",
            value="\n".join(cmd_lines)[:1024],
            inline=False,
        )
        e.add_field(
            name="วิธีสร้าง Affiliate Link",
            value=(
                "1. เปิด shopee.co.th/product/<shopid>/<itemid> (ดูจาก CSV)\n"
                "2. ไปที่ affiliate.shopee.co.th → สร้างลิงก์\n"
                "3. วาง URL สินค้า → รับ s.shopee.co.th/... \n"
                "4. `/affiliate-link-add link:<s.shopee.co.th/...>`\n"
                "5. `/seo-refresh " + article_id + "` → ตรวจ confirmed count"
            ),
            inline=False,
        )

    return e


def build_unpublish_embed(result: dict) -> discord.Embed:
    dry_run    = result.get("dry_run", False)
    article_id = result.get("article_id", "")
    commit_hash = result.get("commit_hash", "")

    if dry_run:
        color = "info"
        title = f"🧪 Dry-Run Unpublish: `{article_id}`"
        desc  = result.get("message", "Dry-run complete")
    else:
        color = "operator"
        title = f"📦 Unpublished: `{article_id}`"
        desc  = "บทความถูกนำออกจากเว็บไซต์แล้ว สถานะ DB กลับเป็น reviewed"

    e = make_embed(title, color_key=color, description=desc)
    if not dry_run and commit_hash:
        e.add_field(name="Commit", value=f"`{commit_hash[:8]}`", inline=True)
    e.add_field(name="Status DB", value="`reviewed`", inline=True)
    if dry_run:
        e.add_field(name="ต้องการ unpublish จริง",
                    value="ตั้ง `SEO_PUBLISH_ENABLED=true` ใน .env แล้วรันใหม่",
                    inline=False)
    return e


def build_edit_embed(result: dict) -> discord.Embed:
    article_id  = result.get("article_id", "")
    field       = result.get("field", "")
    old_val     = str(result.get("old_value", "") or "")[:200] or "—"
    new_val     = str(result.get("new_value", "") or "")[:200] or "—"
    rev         = result.get("revision_saved")
    req_repub   = result.get("requires_republish", False)

    e = make_embed(
        f"✏️ Edited: `{article_id}`",
        color_key="success",
        description=f"**{field}** อัปเดตสำเร็จ",
    )
    e.add_field(name="Field",     value=f"`{field}`", inline=True)
    e.add_field(name="Revision",  value=f"#{rev}" if rev else "—", inline=True)
    e.add_field(name="ค่าเดิม",   value=f"```{old_val}```", inline=False)
    e.add_field(name="ค่าใหม่",   value=f"```{new_val}```", inline=False)
    if result.get("slug_unchanged"):
        e.add_field(name="🔗 Slug", value="ไม่เปลี่ยน (article_id คงเดิม)", inline=False)
    if req_repub:
        e.add_field(
            name="⚠️ ต้อง republish",
            value=f"บทความนี้ถูกเผยแพร่แล้ว ต้อง `/seo-republish {article_id}` เพื่อให้การแก้ไขมีผลบนเว็บ",
            inline=False,
        )
    return e


def build_product_manage_embed(result: dict) -> discord.Embed:
    action      = result.get("action", "")
    article_id  = result.get("article_id", "")
    demoted     = result.get("demoted_to_draft", False)
    rev         = result.get("revision_saved")

    _ACTION_EMOJI = {"add": "➕", "remove": "🗑️", "replace": "🔄"}
    _ACTION_LABEL = {"add": "Added", "remove": "Removed", "replace": "Replaced"}
    emoji = _ACTION_EMOJI.get(action, "✏️")
    label = _ACTION_LABEL.get(action, action.title())

    e = make_embed(
        f"{emoji} Product {label}: `{article_id}`",
        color_key="success" if not demoted else "trend",
    )

    if action == "add":
        e.add_field(name="itemid",    value=str(result.get("itemid", "")),          inline=True)
        e.add_field(name="ลำดับที่",  value=str(result.get("rank_in_article", "")), inline=True)
        e.add_field(name="Link Type", value=result.get("affiliate_link_type", ""),  inline=True)
        e.add_field(name="สินค้า",    value=str(result.get("product_title", ""))[:80], inline=False)
    elif action == "remove":
        e.add_field(name="itemid",        value=str(result.get("itemid", "")),          inline=True)
        e.add_field(name="ลำดับเดิม",    value=str(result.get("removed_rank", "")),    inline=True)
        e.add_field(name="คงเหลือ",       value=str(result.get("remaining_count", "")), inline=True)
        e.add_field(name="สินค้าที่ลบ",  value=str(result.get("removed_title", ""))[:80], inline=False)
    elif action == "replace":
        e.add_field(name="Old itemid", value=str(result.get("old_itemid", "")), inline=True)
        e.add_field(name="New itemid", value=str(result.get("new_itemid", "")), inline=True)
        e.add_field(name="ลำดับที่",   value=str(result.get("rank_in_article", "")), inline=True)
        e.add_field(name="เปลี่ยนจาก", value=str(result.get("old_title", ""))[:80], inline=False)
        e.add_field(name="เป็น",        value=str(result.get("new_title", ""))[:80], inline=False)

    if rev:
        e.add_field(name="Revision Saved", value=f"#{rev}", inline=True)
    if demoted:
        e.add_field(
            name="⚠️ Status → draft",
            value="บทความถูก demote เพราะสินค้าเปลี่ยน ต้อง review และ publish ใหม่",
            inline=False,
        )
    return e


def build_republish_embed(result: dict) -> discord.Embed:
    dry_run     = result.get("dry_run", False)
    article_id  = result.get("article_id", "")
    page_url    = result.get("page_url")
    commit_hash = result.get("commit_hash", "")
    warnings    = result.get("warnings", [])
    in_sitemap  = result.get("in_sitemap", False)

    if dry_run:
        color = "info"
        title = f"🧪 Dry-Run Republish: `{article_id}`"
        desc  = result.get("message", "Dry-run complete — SEO_PUBLISH_ENABLED=false")
    else:
        color = "opportunity"
        title = f"🔁 Republished: `{article_id}`"
        desc  = f"**{page_url}**" if page_url else "Republished successfully"

    e = make_embed(title, color_key=color, description=desc)
    e.add_field(name="published_at", value="คงเดิม (ไม่เปลี่ยน)", inline=True)
    e.add_field(name="updated_at",   value="อัปเดตแล้ว",           inline=True)
    if not dry_run and commit_hash:
        e.add_field(name="Commit", value=f"`{commit_hash[:8]}`", inline=True)
    e.add_field(name="Sitemap", value="✅ included" if in_sitemap else "⏳ pending", inline=True)
    if warnings:
        e.add_field(name="⚠️ Warnings",
                    value="\n".join(f"• {w}" for w in warnings)[:1024], inline=False)
    return e


def build_history_embed(result: dict) -> discord.Embed:
    article_id = result.get("article_id", "")
    revisions  = result.get("revisions", [])

    if not revisions:
        return make_embed(
            f"📜 History: `{article_id}`",
            color_key="info",
            description="ยังไม่มี revision history สำหรับบทความนี้",
        )

    e = make_embed(
        f"📜 History: `{article_id}`",
        color_key="operator",
        description=f"**{len(revisions)}** revision(s) บันทึกล่าสุด (เก็บสูงสุด 5 รายการ)",
    )
    for rev in revisions[:5]:
        rev_num   = rev.get("revision_number", "?")
        title_str = str(rev.get("title", ""))[:50] or "—"
        summary   = str(rev.get("change_summary", ""))[:60] or "—"
        by        = str(rev.get("saved_by", "system"))
        ts        = str(rev.get("created_at", ""))[:16]
        status    = str(rev.get("status", ""))
        e.add_field(
            name=f"#{rev_num} — {ts}",
            value=f"**{title_str}**\n{summary}\nby {by} | status: {status}",
            inline=False,
        )

    e.add_field(
        name="Rollback",
        value=f"ใช้ `/seo-rollback article_id:{article_id} revision_number:<#>` เพื่อย้อนกลับ",
        inline=False,
    )
    return e


def build_rollback_embed(result: dict) -> discord.Embed:
    article_id  = result.get("article_id", "")
    rev_num     = result.get("revision_number", "?")
    title_after = result.get("restored_title", "")

    e = make_embed(
        f"⏪ Rollback: `{article_id}`",
        color_key="trend",
        description=f"Rolled back to revision **#{rev_num}**",
    )
    e.add_field(name="Article ID",     value=f"`{article_id}`",              inline=True)
    e.add_field(name="Restored To",    value=f"Revision #{rev_num}",         inline=True)
    e.add_field(name="Status After",   value="📝 draft",                     inline=True)
    if title_after:
        e.add_field(name="Title Restored", value=title_after[:100], inline=False)
    e.add_field(
        name="Next Step",
        value=(
            f"ตรวจสอบด้วย `/seo-preview {article_id}` แล้ว "
            f"`/seo-review {article_id} action:approve` ก่อน publish ใหม่"
        ),
        inline=False,
    )
    return e


def build_list_embed(
    articles: list[dict],
    stats: dict,
    status_filter: str | None,
    limit: int,
) -> discord.Embed:
    filter_str = f" — {status_filter}" if status_filter else " — ทั้งหมด"
    title = f"📋 SEO Articles{filter_str}"

    desc = (
        f"📝 Draft: **{stats.get('draft', 0)}** | "
        f"✅ Reviewed: **{stats.get('reviewed', 0)}** | "
        f"🌐 Published: **{stats.get('published', 0)}** | "
        f"📦 Archived: **{stats.get('archived', 0)}**"
    )

    if not articles:
        return make_embed(title, color_key="info", description=f"{desc}\n\nยังไม่มีบทความ")

    e = make_embed(title, color_key="operator", description=desc)

    status_emoji = {"draft": "📝", "reviewed": "✅", "published": "🌐", "archived": "📦"}

    for a in articles:
        article_id = str(a.get("article_id", ""))
        keyword    = str(a.get("keyword", ""))[:40]
        status     = str(a.get("status", ""))
        updated_at = str(a.get("updated_at", ""))[:16]
        category   = str(a.get("category", "")) or "—"
        emoji      = status_emoji.get(status, "❓")

        e.add_field(
            name=f"{emoji} `{article_id}`"[:256],
            value=f"**{keyword}**\n{category} · {updated_at}"[:1024],
            inline=True,
        )

    return e
