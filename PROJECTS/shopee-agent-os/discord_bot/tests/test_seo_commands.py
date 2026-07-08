"""Tests for SEO Phase F: service layer and embed builders.

Tests verify:
  1. seo_service functions return the expected data shape
  2. Embed builders produce valid discord.Embed objects

Run with:  python -m pytest discord_bot/tests/test_seo_commands.py -v
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Discord stub (extends base stub with Choice / choices support)
# ---------------------------------------------------------------------------

def _make_discord_stub() -> types.ModuleType:
    m = types.ModuleType("discord")

    class _Embed:
        def __init__(self, title="", description="", color=0, **kw):
            self.title = title
            self.description = description
            self.color = color
            self.fields: list[dict] = []
            self._footer = ""

        def add_field(self, *, name, value, inline=True):
            self.fields.append({"name": name, "value": value})
            return self

        def set_footer(self, *, text="", **kw):
            self._footer = text
            return self

    class _ButtonStyle:
        secondary = 2

    class _ActivityType:
        watching = 3

    class _Activity:
        def __init__(self, **kw): pass

    class _Intents:
        @classmethod
        def default(cls): return cls()
        message_content = True

    class _Object:
        def __init__(self, *, id): self.id = id

    class _File:
        def __init__(self, fp=None, filename=""): pass

    m.Embed = _Embed
    m.ButtonStyle = _ButtonStyle
    m.ActivityType = _ActivityType
    m.Activity = _Activity
    m.Intents = _Intents
    m.Object = _Object
    m.File = _File

    ui = types.ModuleType("discord.ui")

    class _View:
        def __init__(self, **kw): pass

    class _Button:
        pass

    ui.View = _View
    ui.Button = _Button

    def _button(*a, **kw):
        def deco(fn): return fn
        return deco

    ui.button = _button
    m.ui = ui

    app_commands = types.ModuleType("discord.app_commands")

    class _Choice:
        def __init__(self, *, name, value):
            self.name = name
            self.value = value

    def _cmd(*a, **kw):
        def deco(fn): return fn
        return deco

    def _describe(**kw):
        def deco(fn): return fn
        return deco

    def _choices(**kw):
        def deco(fn): return fn
        return deco

    app_commands.command = _cmd
    app_commands.describe = _describe
    app_commands.choices = _choices
    app_commands.Choice = _Choice
    m.app_commands = app_commands

    ext = types.ModuleType("discord.ext")
    commands_mod = types.ModuleType("discord.ext.commands")

    class _Bot:
        def __init__(self, **kw): pass

    class _Cog:
        def __init__(self, bot=None): pass

    commands_mod.Bot = _Bot
    commands_mod.Cog = _Cog
    ext.commands = commands_mod
    m.ext = ext

    # Only install if not already present — prevents class identity conflicts
    # when test_commands.py has already installed its stub
    if "discord" not in sys.modules:
        sys.modules["discord"] = m
        sys.modules["discord.ui"] = ui
        sys.modules["discord.app_commands"] = app_commands
        sys.modules["discord.ext"] = ext
        sys.modules["discord.ext.commands"] = commands_mod
    return sys.modules.get("discord", m)


_discord = _make_discord_stub()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_ideas(n: int = 3) -> list[dict]:
    return [
        {
            "keyword":           f"สินค้า {i} ไม่เกิน 1,000 บาท",
            "category":          f"Category {i}",
            "price_bucket":      1000,
            "top_product_title": f"Product {i}",
            "top_product_price": "฿999",
            "opportunity_score": float(1000 - i * 100),
            "estimated_products": 50 + i,
        }
        for i in range(1, n + 1)
    ]


def _sample_article(status: str = "draft") -> dict:
    return {
        "article_id":    "gaming-mouse-1500",
        "keyword":       "เมาส์เกมมิ่ง ไม่เกิน 1500 บาท",
        "category":      "Mobile & Gadgets",
        "title":         "5 เมาส์เกมมิ่ง ไม่เกิน 1500 บาท ที่ดีที่สุด",
        "meta_description": "รวม 5 เมาส์เกมมิ่งยอดนิยม",
        "content_md":    "---\narticle_id: gaming-mouse-1500\n---\n\n## บทนำ\n\nเนื้อหาทดสอบ",
        "status":        status,
        "created_at":    "2026-07-08T10:00:00+00:00",
        "updated_at":    "2026-07-08T10:00:00+00:00",
        "affiliate_disclosure": True,
    }


def _sample_draft_result() -> dict:
    return {
        "success":                True,
        "article_id":             "gaming-mouse-1500",
        "title":                  "5 เมาส์เกมมิ่ง ไม่เกิน 1500 บาท ที่ดีที่สุด",
        "keyword":                "เมาส์เกมมิ่ง ไม่เกิน 1500 บาท",
        "category":               "Mobile & Gadgets",
        "products_count":         5,
        "has_confirmed_affiliate": True,
        "confirmed_links":        2,
        "datafeed_links":         3,
        "products_without_link":  0,
        "ai_used":                False,
        "content_preview":        "## บทนำ\n\nเนื้อหาตัวอย่าง",
    }


def _sample_stats() -> dict:
    return {"draft": 3, "reviewed": 1, "published": 2, "archived": 0, "total_products": 15, "confirmed_links": 4}


def _sample_articles(n: int = 3) -> list[dict]:
    return [
        {
            "article_id": f"article-{i}",
            "keyword":    f"keyword {i}",
            "category":   "Beauty",
            "title":      f"บทความที่ {i}",
            "status":     "draft",
            "created_at": "2026-07-08T10:00:00",
            "updated_at": "2026-07-08T10:00:00",
        }
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# Tests: seo_service — keyword opportunities
# ---------------------------------------------------------------------------

class TestSeoServiceIdeas(unittest.TestCase):

    def test_success(self):
        with patch("shopee_engine.seo_engine.find_keyword_opportunities", return_value=_sample_ideas()):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.get_keyword_opportunities()
        self.assertTrue(result["success"])
        self.assertEqual(result["total"], 3)
        self.assertIsInstance(result["data"], list)

    def test_with_category(self):
        with patch("shopee_engine.seo_engine.find_keyword_opportunities", return_value=_sample_ideas(1)):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.get_keyword_opportunities(category="Beauty", limit=5)
        self.assertTrue(result["success"])

    def test_engine_error(self):
        with patch("shopee_engine.seo_engine.find_keyword_opportunities",
                   side_effect=RuntimeError("DB error")):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.get_keyword_opportunities()
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_empty_result(self):
        with patch("shopee_engine.seo_engine.find_keyword_opportunities", return_value=[]):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.get_keyword_opportunities()
        self.assertTrue(result["success"])
        self.assertEqual(result["total"], 0)


# ---------------------------------------------------------------------------
# Tests: seo_service — article draft creation
# ---------------------------------------------------------------------------

class TestSeoServiceDraft(unittest.TestCase):

    def test_create_success(self):
        with patch("shopee_engine.seo_engine.check_duplicate_draft", return_value=None), \
             patch("shopee_engine.seo_engine.generate_article_draft", return_value=_sample_draft_result()):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.create_article_draft("เมาส์เกมมิ่ง")
        self.assertTrue(result["success"])
        self.assertEqual(result["article_id"], "gaming-mouse-1500")

    def test_create_duplicate_warns(self):
        existing = {"article_id": "gaming-mouse-1500", "status": "draft", "keyword": "เมาส์เกมมิ่ง", "updated_at": "2026-07-08"}
        with patch("shopee_engine.seo_engine.check_duplicate_draft", return_value=existing):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.create_article_draft("เมาส์เกมมิ่ง")
        self.assertFalse(result["success"])
        self.assertTrue(result.get("duplicate"))
        self.assertEqual(result["existing_id"], "gaming-mouse-1500")
        self.assertEqual(result["existing_status"], "draft")

    def test_no_products_returns_error(self):
        no_products = {"success": False, "error": "ไม่พบสินค้า"}
        with patch("shopee_engine.seo_engine.check_duplicate_draft", return_value=None), \
             patch("shopee_engine.seo_engine.generate_article_draft", return_value=no_products):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.create_article_draft("keyword ที่ไม่มีสินค้า")
        self.assertFalse(result["success"])
        self.assertNotIn("duplicate", result)

    def test_engine_exception_caught(self):
        with patch("shopee_engine.seo_engine.check_duplicate_draft", return_value=None), \
             patch("shopee_engine.seo_engine.generate_article_draft",
                   side_effect=RuntimeError("transaction failed")):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.create_article_draft("keyword")
        self.assertFalse(result["success"])
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Tests: seo_service — article preview
# ---------------------------------------------------------------------------

class TestSeoServicePreview(unittest.TestCase):

    def test_success(self):
        article = _sample_article()
        validation = {"valid": True, "errors": [], "warnings": []}
        with patch("shopee_engine.seo_engine.get_article", return_value=article), \
             patch("shopee_engine.seo_engine.get_article_product_count", return_value=5), \
             patch("shopee_engine.seo_engine.validate_article_for_publish", return_value=validation):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.preview_article("gaming-mouse-1500")
        self.assertTrue(result["success"])
        self.assertEqual(result["product_count"], 5)
        self.assertIn("article", result)
        self.assertIn("validation", result)

    def test_not_found(self):
        with patch("shopee_engine.seo_engine.get_article", return_value=None):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.preview_article("nonexistent-id")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"].lower())

    def test_with_validation_warnings(self):
        article = _sample_article(status="draft")
        validation = {"valid": False, "errors": ["Status must be reviewed"], "warnings": ["2 products use datafeed links"]}
        with patch("shopee_engine.seo_engine.get_article", return_value=article), \
             patch("shopee_engine.seo_engine.get_article_product_count", return_value=3), \
             patch("shopee_engine.seo_engine.validate_article_for_publish", return_value=validation):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.preview_article("gaming-mouse-1500")
        self.assertTrue(result["success"])
        self.assertFalse(result["validation"]["valid"])
        self.assertEqual(len(result["validation"]["errors"]), 1)


# ---------------------------------------------------------------------------
# Tests: seo_service — article list
# ---------------------------------------------------------------------------

class TestSeoServiceList(unittest.TestCase):

    def test_list_all(self):
        with patch("shopee_engine.seo_engine.list_articles", return_value=_sample_articles()), \
             patch("shopee_engine.seo_engine.get_article_stats", return_value=_sample_stats()):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.list_seo_articles()
        self.assertTrue(result["success"])
        self.assertEqual(result["total"], 3)
        self.assertIn("stats", result)

    def test_list_with_status_filter(self):
        with patch("shopee_engine.seo_engine.list_articles", return_value=_sample_articles(1)) as mock_list, \
             patch("shopee_engine.seo_engine.get_article_stats", return_value=_sample_stats()):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.list_seo_articles(status="draft", limit=5)
        self.assertTrue(result["success"])
        mock_list.assert_called_once_with(status="draft", limit=5)

    def test_list_error(self):
        with patch("shopee_engine.seo_engine.list_articles",
                   side_effect=RuntimeError("DB error")):
            from discord_bot.services import seo_service
            import importlib
            importlib.reload(seo_service)
            result = seo_service.list_seo_articles()
        self.assertFalse(result["success"])
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Tests: embed builders
# ---------------------------------------------------------------------------

class TestSeoIdeasEmbed(unittest.TestCase):

    def test_empty_ideas(self):
        from discord_bot.embeds.seo_embeds import build_ideas_embed
        embed = build_ideas_embed([], None, 10)
        self.assertIsInstance(embed, _discord.Embed)
        self.assertIn("Ideas", embed.title)

    def test_with_ideas(self):
        from discord_bot.embeds.seo_embeds import build_ideas_embed
        embed = build_ideas_embed(_sample_ideas(5), None, 10)
        self.assertIsInstance(embed, _discord.Embed)
        self.assertEqual(len(embed.fields), 5)

    def test_with_category_filter(self):
        from discord_bot.embeds.seo_embeds import build_ideas_embed
        embed = build_ideas_embed(_sample_ideas(2), "Beauty", 10)
        self.assertIn("Beauty", embed.title)

    def test_opportunity_score_label(self):
        from discord_bot.embeds.seo_embeds import build_ideas_embed
        embed = build_ideas_embed(_sample_ideas(1), None, 5)
        field_value = embed.fields[0]["value"]
        self.assertIn("Article Opportunity Score", field_value)
        self.assertNotIn("search volume", field_value.lower())


class TestSeoDraftEmbed(unittest.TestCase):

    def test_success_embed(self):
        from discord_bot.embeds.seo_embeds import build_draft_embed
        embed = build_draft_embed(_sample_draft_result())
        self.assertIsInstance(embed, _discord.Embed)
        self.assertIn("Draft Created", embed.title)
        field_names = [f["name"] for f in embed.fields]
        self.assertIn("Article ID", field_names)
        self.assertIn("Status", field_names)

    def test_no_confirmed_affiliate_shows_warning(self):
        from discord_bot.embeds.seo_embeds import build_draft_embed
        result = {**_sample_draft_result(), "has_confirmed_affiliate": False, "confirmed_links": 0}
        embed = build_draft_embed(result)
        field_names = [f["name"] for f in embed.fields]
        self.assertTrue(any("คำเตือน" in n for n in field_names))

    def test_all_confirmed_no_warning(self):
        from discord_bot.embeds.seo_embeds import build_draft_embed
        result = {**_sample_draft_result(), "has_confirmed_affiliate": True}
        embed = build_draft_embed(result)
        field_names = [f["name"] for f in embed.fields]
        self.assertFalse(any("คำเตือน Affiliate" in n for n in field_names))

    def test_duplicate_embed(self):
        from discord_bot.embeds.seo_embeds import build_draft_duplicate_embed
        embed = build_draft_duplicate_embed("เมาส์เกมมิ่ง", {"article_id": "gaming-mouse-1500", "status": "draft", "updated_at": ""})
        self.assertIsInstance(embed, _discord.Embed)
        self.assertIn("Duplicate", embed.title)
        field_names = [f["name"] for f in embed.fields]
        self.assertIn("Article ID", field_names)


class TestSeoPreviewEmbed(unittest.TestCase):

    def _make_result(self, status: str = "draft", content_len: int = 100) -> dict:
        article = {**_sample_article(status), "content_md": "A" * content_len}
        return {
            "article":       article,
            "product_count": 5,
            "validation":    {"valid": True, "errors": [], "warnings": []},
        }

    def test_draft_status_embed(self):
        from discord_bot.embeds.seo_embeds import build_preview_embed
        embed = build_preview_embed(self._make_result("draft"))
        self.assertIsInstance(embed, _discord.Embed)
        self.assertIn("Preview", embed.title)
        self.assertIn("DRAFT", embed.description.upper())

    def test_reviewed_status_embed(self):
        from discord_bot.embeds.seo_embeds import build_preview_embed
        embed = build_preview_embed(self._make_result("reviewed"))
        self.assertIn("REVIEWED", embed.description.upper())

    def test_validation_errors_shown(self):
        from discord_bot.embeds.seo_embeds import build_preview_embed
        result = self._make_result()
        result["validation"] = {"valid": False, "errors": ["Status must be reviewed"], "warnings": []}
        embed = build_preview_embed(result)
        field_names = [f["name"] for f in embed.fields]
        self.assertTrue(any("Error" in n for n in field_names))

    def test_validation_warnings_shown(self):
        from discord_bot.embeds.seo_embeds import build_preview_embed
        result = self._make_result()
        result["validation"] = {"valid": True, "errors": [], "warnings": ["2 products use datafeed links"]}
        embed = build_preview_embed(result)
        field_names = [f["name"] for f in embed.fields]
        self.assertTrue(any("Warning" in n for n in field_names))

    def test_file_attachment_hint_for_long_content(self):
        from discord_bot.embeds.seo_embeds import build_preview_embed
        embed = build_preview_embed(self._make_result(content_len=2000))
        field_names = [f["name"] for f in embed.fields]
        self.assertTrue(any("Full Content" in n for n in field_names))

    def test_no_file_hint_for_short_content(self):
        from discord_bot.embeds.seo_embeds import build_preview_embed
        embed = build_preview_embed(self._make_result(content_len=100))
        field_names = [f["name"] for f in embed.fields]
        self.assertFalse(any("Full Content" in n for n in field_names))


class TestSeoListEmbed(unittest.TestCase):

    def test_empty_list(self):
        from discord_bot.embeds.seo_embeds import build_list_embed
        embed = build_list_embed([], _sample_stats(), None, 10)
        self.assertIsInstance(embed, _discord.Embed)
        self.assertIn("Articles", embed.title)
        self.assertEqual(len(embed.fields), 0)

    def test_with_articles(self):
        from discord_bot.embeds.seo_embeds import build_list_embed
        embed = build_list_embed(_sample_articles(4), _sample_stats(), None, 10)
        self.assertEqual(len(embed.fields), 4)

    def test_status_filter_in_title(self):
        from discord_bot.embeds.seo_embeds import build_list_embed
        embed = build_list_embed([], _sample_stats(), "draft", 10)
        self.assertIn("draft", embed.title)

    def test_stats_in_description(self):
        from discord_bot.embeds.seo_embeds import build_list_embed
        embed = build_list_embed([], _sample_stats(), None, 10)
        self.assertIn("Draft", embed.description)
        self.assertIn("Published", embed.description)


if __name__ == "__main__":
    unittest.main(verbosity=2)
