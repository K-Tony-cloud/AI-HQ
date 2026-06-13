"""
Mock-based tests for Discord command center.

Tests verify:
  1. Service functions return the expected data shape
  2. Embed builders produce valid discord.Embed objects
  3. Commands call the correct service + embed functions

Run with:  python -m pytest discord_bot/tests/ -v
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Stub out discord before any bot code is imported
# ---------------------------------------------------------------------------

def _make_discord_stub() -> types.ModuleType:
    """Return a minimal discord stub so tests don't require discord.py installed."""
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

    m.Embed = _Embed
    m.ButtonStyle = _ButtonStyle
    m.ActivityType = _ActivityType
    m.Activity = _Activity
    m.Intents = _Intents
    m.Object = _Object

    ui = types.ModuleType("discord.ui")
    class _View:
        def __init__(self, **kw): pass
    class _Button: pass
    ui.View  = _View
    ui.Button = _Button
    def _button(*a, **kw):
        def deco(fn): return fn
        return deco
    ui.button = _button
    m.ui = ui

    app_commands = types.ModuleType("discord.app_commands")
    def _cmd(*a, **kw):
        def deco(fn): return fn
        return deco
    def _describe(**kw):
        def deco(fn): return fn
        return deco
    app_commands.command  = _cmd
    app_commands.describe = _describe
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

    sys.modules["discord"]              = m
    sys.modules["discord.ui"]           = ui
    sys.modules["discord.app_commands"] = app_commands
    sys.modules["discord.ext"]          = ext
    sys.modules["discord.ext.commands"] = commands_mod
    return m


_discord = _make_discord_stub()


# ---------------------------------------------------------------------------
# Tests: Embed builders (no Discord connection needed)
# ---------------------------------------------------------------------------

class TestDiscoveryEmbeds(unittest.TestCase):

    def test_top_opportunities_empty(self):
        from discord_bot.embeds.discovery_embeds import build_top_opportunities_pages
        pages = build_top_opportunities_pages([], None)
        self.assertGreater(len(pages), 0)
        self.assertIsInstance(pages[0], _discord.Embed)

    def test_top_opportunities_with_data(self):
        from discord_bot.embeds.discovery_embeds import build_top_opportunities_pages
        records = [
            {"title": f"Product {i}", "item_sold": i * 100,
             "sale_price": 299.0, "opportunity_score": i * 1000,
             "discount_pct": 20}
            for i in range(1, 6)
        ]
        pages = build_top_opportunities_pages(records, "Beauty")
        self.assertEqual(len(pages), 1)
        self.assertIn("Opportunities", pages[0].title)
        self.assertEqual(len(pages[0].fields), 5)

    def test_top_viral_pagination(self):
        from discord_bot.embeds.discovery_embeds import build_top_viral_pages
        records = [
            {"title": f"Viral {i}", "sale_price": 199.0,
             "item_sold": 500, "likes": 10000, "viral_score": i * 500}
            for i in range(1, 25)
        ]
        pages = build_top_viral_pages(records, None, page_size=10)
        self.assertEqual(len(pages), 3)  # 24 items / 10 per page = ceil(2.4) = 3

    def test_find_product_embed(self):
        from discord_bot.embeds.discovery_embeds import build_find_product_embed
        records = [{"title": "JisuLife Fan", "item_sold": 6177,
                    "sale_price": 2242, "opportunity_score": 19191}]
        embed = build_find_product_embed(records, "jisulife")
        self.assertIn("jisulife", embed.title.lower())
        self.assertGreater(len(embed.fields), 0)

    def test_daily_picks_embed(self):
        from discord_bot.embeds.discovery_embeds import build_daily_picks_embed
        picks = {
            "Gadget": [{"title": "Fan", "item_sold": 100, "sale_price": 299,
                        "opportunity_score": 1000}],
            "Health": [],
        }
        embeds = build_daily_picks_embed(picks)
        # Should only create embed for non-empty buckets
        self.assertEqual(len(embeds), 1)
        self.assertIn("Gadget", embeds[0].title)


class TestPerformanceEmbeds(unittest.TestCase):

    def test_top_profit_empty(self):
        from discord_bot.embeds.performance_embeds import build_top_profit_pages
        pages = build_top_profit_pages([])
        self.assertGreater(len(pages), 0)
        self.assertIn("No affiliate data", pages[0].description)

    def test_top_profit_with_data(self):
        from discord_bot.embeds.performance_embeds import build_top_profit_pages
        records = [
            {"product": f"Product {i}", "total_commission": i * 1000,
             "epc": 4.27, "conversion_rate": 8.5, "revenue": i * 10000}
            for i in range(1, 6)
        ]
        pages = build_top_profit_pages(records)
        self.assertEqual(len(pages[0].fields), 5)


class TestContentEmbeds(unittest.TestCase):

    def test_queue_empty(self):
        from discord_bot.embeds.content_embeds import build_queue_pages
        pages = build_queue_pages([])
        self.assertEqual(len(pages), 1)
        self.assertIn("empty", pages[0].description.lower())

    def test_queue_with_items(self):
        from discord_bot.embeds.content_embeds import build_queue_pages
        records = [
            {"id": i, "keyword": f"keyword_{i}", "status": "draft",
             "ai_provider": "template"}
            for i in range(1, 12)
        ]
        pages = build_queue_pages(records, page_size=8)
        self.assertEqual(len(pages), 2)

    def test_approve_embed_success(self):
        from discord_bot.embeds.content_embeds import build_approve_embed
        embed = build_approve_embed(3, True)
        self.assertIn("Approved", embed.title)

    def test_approve_embed_failure(self):
        from discord_bot.embeds.content_embeds import build_approve_embed
        embed = build_approve_embed(99, False)
        self.assertIn("Not Found", embed.title)


class TestOperatorEmbeds(unittest.TestCase):

    SAMPLE_BRIEF = {
        "top_opportunities": [("Product A", 939, 1499, 25192)],
        "top_viral":         [("Product B", 289, 48474)],
        "top_niches":        [("Disposable Diapers", 555, 169)],
        "top_profit":        [("JisuLife Fan", 12750, 4.27, 8.38)],
        "generated_at":      "2026-06-13 17:00",
    }

    SAMPLE_SUMMARY = {
        "opportunities":     [("Product A", 939, 1499, 25192)],
        "risks":             [("Dummy Product", 655446, 40)],
        "market_gaps":       [("Book Covers", 155, 123)],
        "viral_candidates":  [("Product B", 289, 48474)],
        "profit_candidates": [("JisuLife Fan", 12750, 4.27)],
        "total_products":    1000000,
        "total_commission":  40666.0,
        "generated_at":      "2026-06-13 17:00",
    }

    def test_morning_brief_embeds(self):
        from discord_bot.embeds.operator_embeds import build_morning_brief_embeds
        embeds = build_morning_brief_embeds(self.SAMPLE_BRIEF)
        self.assertGreaterEqual(len(embeds), 4)
        self.assertIn("Morning Brief", embeds[0].title)

    def test_executive_summary_embeds(self):
        from discord_bot.embeds.operator_embeds import build_executive_summary_embeds
        embeds = build_executive_summary_embeds(self.SAMPLE_SUMMARY)
        self.assertGreaterEqual(len(embeds), 5)
        self.assertIn("Executive Summary", embeds[0].title)


# ---------------------------------------------------------------------------
# Tests: Service layer (mock shopee_engine imports)
# ---------------------------------------------------------------------------

class TestDiscoveryService(unittest.TestCase):

    def _make_df(self, cols: list[str], rows: int = 3):
        """Create a minimal mock DataFrame."""
        import pandas as pd
        data = {c: [f"val_{c}_{i}" for i in range(rows)] for c in cols}
        return pd.DataFrame(data)

    def test_get_top_opportunities_success(self):
        cols = ["title", "sale_price", "item_sold", "opportunity_score",
                "likes", "shop_rating", "discount_pct", "category",
                "brand", "product_short_link"]
        mock_df = self._make_df(cols, 5)
        with patch("shopee_engine.discovery.top_opportunities", return_value=mock_df):
            from discord_bot.services.discovery_service import get_top_opportunities
            result = get_top_opportunities(top=5)
        self.assertTrue(result["success"])
        self.assertEqual(result["total"], 5)

    def test_get_top_opportunities_error(self):
        with patch("shopee_engine.discovery.top_opportunities",
                   side_effect=RuntimeError("No database")):
            from discord_bot.services import discovery_service
            import importlib
            importlib.reload(discovery_service)
            result = discovery_service.get_top_opportunities()
        self.assertFalse(result["success"])
        self.assertIn("error", result)


class TestPerformanceService(unittest.TestCase):

    def test_get_top_profit_no_data(self):
        with patch("shopee_engine.performance_engine.top_profit_products",
                   side_effect=RuntimeError("No affiliate data")):
            from discord_bot.services import performance_service
            import importlib
            importlib.reload(performance_service)
            result = performance_service.get_top_profit()
        self.assertFalse(result["success"])


class TestContentService(unittest.TestCase):

    def test_approve_success(self):
        with patch("shopee_engine.content_engine.queue_approve", return_value=True):
            from discord_bot.services import content_service
            import importlib
            importlib.reload(content_service)
            result = content_service.approve_queue_item(1)
        self.assertTrue(result["success"])

    def test_approve_not_found(self):
        with patch("shopee_engine.content_engine.queue_approve", return_value=False):
            from discord_bot.services import content_service
            import importlib
            importlib.reload(content_service)
            result = content_service.approve_queue_item(999)
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
