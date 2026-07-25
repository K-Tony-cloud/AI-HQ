"""Slash commands: /seo-ideas, /seo-draft, /seo-preview, /seo-list"""

from __future__ import annotations

import asyncio
import io

import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands

from discord_bot.embeds.base import error_embed, send_and_confirm
from discord_bot.embeds.seo_embeds import (
    build_draft_duplicate_embed,
    build_draft_embed,
    build_edit_embed,
    build_history_embed,
    build_ideas_embed,
    build_link_status_embed,
    build_list_embed,
    build_preflight_embed,
    build_preview_embed,
    build_product_manage_embed,
    build_publish_embed,
    build_publish_failed_embed,
    build_refresh_embed,
    build_republish_embed,
    build_review_blocked_embed,
    build_review_embed,
    build_rollback_embed,
    build_unpublish_embed,
    build_upgrade_embed,
)
from discord_bot.services import seo_service


_CATEGORY_CHOICES = [
    Choice(name="บ้านและครัว",        value="Home & Living"),
    Choice(name="มือถือ & แกดเจ็ต",   value="Mobile & Gadgets"),
    Choice(name="ความงาม",            value="Beauty"),
    Choice(name="สุขภาพ",             value="Health"),
    Choice(name="แม่และเด็ก",         value="Mom & Baby"),
    Choice(name="กีฬา",               value="Sports & Outdoors"),
    Choice(name="อาหาร & เครื่องดื่ม", value="Food & Beverages"),
]


class SeoCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /seo-ideas
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-ideas",
        description="Show keyword opportunities for SEO article writing",
    )
    @app_commands.describe(
        category="กรอง keyword ตามหมวดสินค้า (optional)",
        limit="จำนวน keyword ที่แสดง (1-20, default 10)",
    )
    @app_commands.choices(category=_CATEGORY_CHOICES)
    async def cmd_seo_ideas(
        self,
        interaction: discord.Interaction,
        category: str | None = None,
        limit: int = 10,
    ) -> None:
        from discord_bot.config import CHANNEL_SEO_ARTICLES
        await interaction.response.defer(thinking=True)
        limit = max(1, min(20, limit))
        try:
            result = await asyncio.to_thread(
                seo_service.get_keyword_opportunities, category, limit
            )
            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return
            embed = build_ideas_embed(result["data"], category, limit)
            await send_and_confirm(interaction, [embed], CHANNEL_SEO_ARTICLES)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-draft
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-draft",
        description="Generate a new SEO article draft from Shopee product data",
    )
    @app_commands.describe(
        idea_id="Idea ID จาก /seo-ideas (แนะนำ — ค้นสินค้าตรง)",
        keyword="Keyword หลักของบทความ (ใช้เมื่อไม่มี idea_id)",
        category="หมวดสินค้าสำหรับกรองข้อมูล (optional)",
        product_count="จำนวนสินค้าในบทความ (3-7, default 5)",
    )
    @app_commands.choices(category=_CATEGORY_CHOICES)
    async def cmd_seo_draft(
        self,
        interaction: discord.Interaction,
        idea_id: str | None = None,
        keyword: str | None = None,
        category: str | None = None,
        product_count: int = 5,
    ) -> None:
        from discord_bot.config import CHANNEL_SEO_ARTICLES
        await interaction.response.defer(thinking=True)

        if not idea_id and not keyword:
            await interaction.followup.send(
                embed=error_embed("ต้องระบุ `idea_id` (จาก /seo-ideas) หรือ `keyword` อย่างใดอย่างหนึ่ง")
            )
            return

        product_count = max(3, min(7, product_count))
        try:
            result = await asyncio.to_thread(
                seo_service.create_article_draft,
                keyword or "",
                category,
                product_count,
                idea_id,
            )
            if not result.get("success"):
                if result.get("duplicate"):
                    embed = build_draft_duplicate_embed(keyword or idea_id or "", {
                        "article_id": result["existing_id"],
                        "status":     result["existing_status"],
                        "updated_at": result.get("existing_updated", ""),
                    })
                else:
                    embed = error_embed(result.get("error", "Unknown error"))
                await interaction.followup.send(embed=embed)
                return
            embed = build_draft_embed(result)
            await send_and_confirm(interaction, [embed], CHANNEL_SEO_ARTICLES)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-preview
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-preview",
        description="Preview an SEO article (never changes status)",
    )
    @app_commands.describe(article_id="Article ID ที่ต้องการดู")
    async def cmd_seo_preview(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(seo_service.preview_article, article_id)
            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return
            embed = build_preview_embed(result)
            content_md = str(result["article"].get("content_md", ""))
            if len(content_md) > 1800:
                f = discord.File(
                    io.BytesIO(content_md.encode("utf-8")),
                    filename=f"{article_id}.md",
                )
                await interaction.followup.send(embed=embed, file=f)
            else:
                await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-list
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # /seo-review
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-review",
        description="Approve or return a draft article for editorial review",
    )
    @app_commands.describe(
        article_id="Article ID ที่ต้องการ review",
        action="approve = draft→reviewed | return_to_draft = reviewed→draft",
        note="หมายเหตุ (optional)",
    )
    @app_commands.choices(action=[
        Choice(name="✅ Approve (draft → reviewed)", value="approve"),
        Choice(name="↩️ Return to Draft",            value="return_to_draft"),
    ])
    async def cmd_seo_review(
        self,
        interaction: discord.Interaction,
        article_id: str,
        action: str,
        note: str = "",
    ) -> None:
        from discord_bot.config import CHANNEL_SEO_ARTICLES
        await interaction.response.defer(thinking=True)
        try:
            # Guard: preflight must pass before approve
            if action == "approve":
                from shopee_engine.seo_engine import _connect, SEO_ARTICLES_TABLE
                def _check_pf():
                    con = _connect(read_only=True)
                    try:
                        r = con.execute(
                            f"SELECT preflight_status FROM {SEO_ARTICLES_TABLE} WHERE article_id=?",
                            [article_id]
                        ).fetchone()
                        con.close()
                        return r[0] if r else "pending"
                    except Exception:
                        con.close()
                        return "pending"
                pf_status = await asyncio.to_thread(_check_pf)
                if pf_status != "passed":
                    from discord_bot.embeds.base import error_embed as _err
                    await interaction.followup.send(
                        embed=_err(
                            f"Preflight ยังไม่ผ่าน (status: `{pf_status}`) — "
                            f"รัน `/seo-preflight {article_id}` ก่อน"
                        ),
                        ephemeral=True,
                    )
                    return

            result = await asyncio.to_thread(
                seo_service.review_article_action, article_id, action, note
            )
            if not result.get("success"):
                if result.get("blocked"):
                    embed = build_review_blocked_embed({**result, "article_id": article_id})
                else:
                    from discord_bot.embeds.base import error_embed as _err
                    embed = _err(result.get("error", "Unknown error"))
                await interaction.followup.send(embed=embed)
                return
            embed = build_review_embed(result)
            await send_and_confirm(interaction, [embed], CHANNEL_SEO_ARTICLES)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-preflight
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-preflight",
        description="รัน QA ครบทุก gate ก่อน review/publish พร้อมแนบ HTML preview และ JSON report",
    )
    @app_commands.describe(article_id="Article ID ที่ต้องการตรวจ")
    async def cmd_seo_preflight(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(seo_service.run_preflight_check, article_id)
            if not result.get("success"):
                await interaction.followup.send(
                    embed=error_embed(result.get("error", "Preflight failed")),
                    ephemeral=True,
                )
                return

            pf        = result["preflight"]
            html_r    = result["html_result"]
            json_r    = result["json_report"]
            all_passed = result["all_passed"]

            # Build Discord embed checklist
            embed = build_preflight_embed(pf, result["crawl_result"], all_passed)

            # Attachments: HTML preview + JSON report
            files = []

            html_content = html_r.get("html_content", "")
            if html_content:
                html_bytes = html_content.encode("utf-8")
                files.append(discord.File(io.BytesIO(html_bytes), filename=f"{article_id}_preview.html"))

            import json as _json
            json_bytes = _json.dumps(json_r, ensure_ascii=False, indent=2).encode("utf-8")
            files.append(discord.File(io.BytesIO(json_bytes), filename=f"{article_id}_preflight.json"))

            await interaction.followup.send(embed=embed, files=files)

        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)), ephemeral=True)

    # ------------------------------------------------------------------
    # /seo-publish
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-publish",
        description="Validate, build, and publish a reviewed SEO article",
    )
    @app_commands.describe(article_id="Article ID ที่ต้องการ publish (ต้องมี status reviewed)")
    async def cmd_seo_publish(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(seo_service.publish_article, article_id)
            if not result.get("success"):
                embed = build_publish_failed_embed(result)
            else:
                embed = build_publish_embed(result)
            # Path/git/env details are ephemeral
            await interaction.followup.send(embed=embed, ephemeral=not result.get("success") is False)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)), ephemeral=True)

    # ------------------------------------------------------------------
    # /seo-refresh
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-refresh",
        description="Sync article product prices, images, and affiliate links from DB",
    )
    @app_commands.describe(article_id="Article ID ที่ต้องการ refresh สินค้า")
    async def cmd_seo_refresh(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(seo_service.refresh_article, article_id)
            if not result.get("success"):
                await interaction.followup.send(embed=error_embed(result.get("error", "Refresh failed")))
                return
            embed = build_refresh_embed(result)
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-unpublish
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-unpublish",
        description="Remove a published article from the site (published → reviewed)",
    )
    @app_commands.describe(article_id="Article ID ที่ต้องการ unpublish")
    async def cmd_seo_unpublish(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(seo_service.unpublish_article, article_id)
            if not result.get("success"):
                embed = build_publish_failed_embed({**result, "article_id": article_id})
            else:
                embed = build_unpublish_embed(result)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)), ephemeral=True)

    # ------------------------------------------------------------------
    # /seo-link-status
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-link-status",
        description="แสดง affiliate link status รายสินค้าของ draft article",
    )
    @app_commands.describe(article_id="Article ID ที่ต้องการตรวจ")
    async def cmd_seo_link_status(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(seo_service.get_link_status, article_id)
            if not result.get("success"):
                await interaction.followup.send(embed=error_embed(result.get("error", "ไม่พบบทความ")))
                return
            embed = build_link_status_embed(result)

            # Attach CSV for missing products if any
            if not result.get("all_confirmed"):
                csv_bytes = await asyncio.to_thread(seo_service.export_missing_links_csv, article_id)
                if csv_bytes:
                    f = discord.File(
                        io.BytesIO(csv_bytes),
                        filename=f"{article_id}-missing-links.csv",
                    )
                    await interaction.followup.send(embed=embed, file=f)
                    return
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-edit
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-edit",
        description="แก้ไข field ของบทความใน DB (ไม่แก้ Markdown โดยตรง)",
    )
    @app_commands.describe(
        article_id="Article ID ที่ต้องการแก้ไข",
        field="Field ที่ต้องการแก้ (title/intro/summary/meta_description/category/category_label)",
        value="ค่าใหม่",
    )
    @app_commands.choices(field=[
        Choice(name="title",             value="title"),
        Choice(name="intro (บทนำ)",      value="intro"),
        Choice(name="summary (บทสรุป)",  value="summary"),
        Choice(name="meta_description",  value="meta_description"),
        Choice(name="category (slug)",   value="category"),
        Choice(name="category_label",    value="category_label"),
    ])
    async def cmd_seo_edit(
        self,
        interaction: discord.Interaction,
        article_id: str,
        field: str,
        value: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        editor = str(interaction.user) if interaction.user else "discord"
        try:
            result = await asyncio.to_thread(
                seo_service.edit_article_field, article_id, field, value, editor
            )
            if not result.get("success"):
                await interaction.followup.send(embed=error_embed(result.get("error", "Edit failed")))
                return
            embed = build_edit_embed(result)
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-product-add
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-product-add",
        description="เพิ่มสินค้าเข้าบทความ (ตรวจสอบว่ามีอยู่ใน DB และไม่ซ้ำ)",
    )
    @app_commands.describe(
        article_id="Article ID ที่ต้องการเพิ่มสินค้า",
        itemid="itemid ของสินค้าที่ต้องการเพิ่ม",
        rank="ลำดับที่ต้องการ (default: ต่อท้าย)",
    )
    async def cmd_seo_product_add(
        self,
        interaction: discord.Interaction,
        article_id: str,
        itemid: str,
        rank: int | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            iid = int(itemid)
        except ValueError:
            await interaction.followup.send(embed=error_embed(f"itemid ต้องเป็นตัวเลข: {itemid}"))
            return
        try:
            result = await asyncio.to_thread(seo_service.add_product, article_id, iid, rank)
            if not result.get("success"):
                await interaction.followup.send(embed=error_embed(result.get("error", "Failed")))
                return
            await interaction.followup.send(embed=build_product_manage_embed(result))
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-product-remove
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-product-remove",
        description="ลบสินค้าออกจากบทความ (re-rank สินค้าที่เหลือ)",
    )
    @app_commands.describe(
        article_id="Article ID ที่ต้องการแก้ไข",
        itemid="itemid ของสินค้าที่ต้องการลบ",
    )
    async def cmd_seo_product_remove(
        self,
        interaction: discord.Interaction,
        article_id: str,
        itemid: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            iid = int(itemid)
        except ValueError:
            await interaction.followup.send(embed=error_embed(f"itemid ต้องเป็นตัวเลข: {itemid}"))
            return
        try:
            result = await asyncio.to_thread(seo_service.remove_product, article_id, iid)
            if not result.get("success"):
                await interaction.followup.send(embed=error_embed(result.get("error", "Failed")))
                return
            await interaction.followup.send(embed=build_product_manage_embed(result))
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-product-replace
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-product-replace",
        description="แทนที่สินค้าด้วยสินค้าใหม่ในลำดับเดิม",
    )
    @app_commands.describe(
        article_id="Article ID ที่ต้องการแก้ไข",
        old_itemid="itemid ของสินค้าที่ต้องการแทนที่",
        new_itemid="itemid ของสินค้าใหม่",
    )
    async def cmd_seo_product_replace(
        self,
        interaction: discord.Interaction,
        article_id: str,
        old_itemid: str,
        new_itemid: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            old_iid = int(old_itemid)
            new_iid = int(new_itemid)
        except ValueError:
            await interaction.followup.send(embed=error_embed("itemid ต้องเป็นตัวเลข"))
            return
        try:
            result = await asyncio.to_thread(
                seo_service.replace_product, article_id, old_iid, new_iid
            )
            if not result.get("success"):
                await interaction.followup.send(embed=error_embed(result.get("error", "Failed")))
                return
            await interaction.followup.send(embed=build_product_manage_embed(result))
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-republish
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-republish",
        description="Republish บทความที่ published อยู่แล้วหลังแก้ไขเนื้อหา (คง published_at เดิม)",
    )
    @app_commands.describe(article_id="Article ID ที่มี status 'published'")
    async def cmd_seo_republish(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(seo_service.republish_article, article_id)
            if not result.get("success"):
                await interaction.followup.send(
                    embed=build_publish_failed_embed({**result, "article_id": article_id})
                )
                return
            await interaction.followup.send(embed=build_republish_embed(result))
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)), ephemeral=True)

    # ------------------------------------------------------------------
    # /seo-history
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-history",
        description="แสดง revision history ของบทความ (สูงสุด 5 รายการล่าสุด)",
    )
    @app_commands.describe(article_id="Article ID ที่ต้องการดู history")
    async def cmd_seo_history(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(seo_service.get_article_history, article_id)
            if not result.get("success"):
                await interaction.followup.send(embed=error_embed(result.get("error", "Failed")))
                return
            await interaction.followup.send(embed=build_history_embed(result))
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-rollback
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-rollback",
        description="ย้อนกลับบทความไปยัง revision ที่ระบุ (บันทึก state ปัจจุบันก่อนเสมอ)",
    )
    @app_commands.describe(
        article_id="Article ID ที่ต้องการ rollback",
        revision_number="หมายเลข revision ที่ต้องการกลับไป (ดูจาก /seo-history)",
    )
    async def cmd_seo_rollback(
        self,
        interaction: discord.Interaction,
        article_id: str,
        revision_number: int,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(
                seo_service.rollback_article, article_id, revision_number
            )
            if not result.get("success"):
                await interaction.followup.send(embed=error_embed(result.get("error", "Rollback failed")))
                return
            await interaction.followup.send(embed=build_rollback_embed(result))
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ------------------------------------------------------------------
    # /seo-list
    # ------------------------------------------------------------------

    @app_commands.command(
        name="seo-list",
        description="List SEO articles, newest first",
    )
    @app_commands.describe(
        status="กรองตาม status (default: ทั้งหมด)",
        limit="จำนวนบทความที่แสดง (1-25, default 10)",
    )
    @app_commands.choices(status=[
        Choice(name="ทั้งหมด",  value="all"),
        Choice(name="Draft",    value="draft"),
        Choice(name="Reviewed", value="reviewed"),
        Choice(name="Published", value="published"),
        Choice(name="Archived", value="archived"),
    ])
    async def cmd_seo_list(
        self,
        interaction: discord.Interaction,
        status: str = "all",
        limit: int = 10,
    ) -> None:
        await interaction.response.defer(thinking=True)
        limit = max(1, min(25, limit))
        status_filter = None if status == "all" else status
        try:
            result = await asyncio.to_thread(
                seo_service.list_seo_articles, status_filter, limit
            )
            if not result["success"]:
                await interaction.followup.send(embed=error_embed(result["error"]))
                return
            embed = build_list_embed(result["data"], result["stats"], status_filter, limit)
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))

    # ── /seo-upgrade ────────────────────────────────────────────────────────

    @app_commands.command(
        name="seo-upgrade",
        description="อัปเกรด prose บทความด้วย AI Editorial Team (Nova/Cipher/Luna/Roxi/Kiki/Speedy)",
    )
    @app_commands.describe(
        article_id="Article ID ที่ต้องการอัปเกรด",
    )
    async def cmd_seo_upgrade(
        self,
        interaction: discord.Interaction,
        article_id: str,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            result = await asyncio.to_thread(
                seo_service.upgrade_article_prose, article_id
            )
            if not result.get("success"):
                await interaction.followup.send(embed=error_embed(result.get("error", "Unknown error")))
                return
            embed = build_upgrade_embed(result)
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(embed=error_embed(str(exc)))
