"""
Scheduler test suite.

Tests:
- Scheduler registration and lifecycle
- Job simulation: 08:00 / 12:00 / 18:00
- Discord delivery verification (mocked)
- Queue generation verification
- Report generation verification
- Embed builders
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Discord stub (no live connection required)
# ---------------------------------------------------------------------------

def _make_discord_stub() -> None:
    """Inject minimal Discord stubs so imports work without discord.py installed."""
    if "discord" in sys.modules and hasattr(sys.modules["discord"], "Embed"):
        return  # already available

    discord_mod = types.ModuleType("discord")

    class _Embed:
        def __init__(self, **kw):
            self.title = kw.get("title", "")
            self.description = kw.get("description", "")
            self.color = kw.get("color", 0)
            self._fields: list = []

        def add_field(self, *, name="", value="", inline=False):
            self._fields.append({"name": name, "value": value})

        def set_footer(self, **kw):
            pass

    class _File:
        def __init__(self, fp, *, filename=None):
            self.fp = fp
            self.filename = filename

    discord_mod.Embed = _Embed
    discord_mod.File  = _File
    discord_mod.Color = MagicMock()

    ui_mod = types.ModuleType("discord.ui")
    ui_mod.View   = object
    ui_mod.Button = MagicMock()
    ui_mod.button = lambda **kw: (lambda f: f)

    ext_mod = types.ModuleType("discord.ext")
    cmd_mod = types.ModuleType("discord.ext.commands")
    cmd_mod.Bot = object
    cmd_mod.Cog = object

    app_mod = types.ModuleType("discord.app_commands")
    app_mod.command  = lambda **kw: (lambda f: f)
    app_mod.describe = lambda **kw: (lambda f: f)
    app_mod.choices  = lambda **kw: (lambda f: f)

    class _Choice:
        def __init__(self, *, name, value): pass
    app_mod.Choice = _Choice

    discord_mod.ui           = ui_mod
    discord_mod.ext          = ext_mod
    discord_mod.app_commands = app_mod
    discord_mod.Intents      = MagicMock()
    discord_mod.Activity     = MagicMock()
    discord_mod.ActivityType = MagicMock()
    discord_mod.Object       = MagicMock()
    discord_mod.Interaction  = MagicMock()
    discord_mod.ButtonStyle  = MagicMock()
    discord_mod.Client       = MagicMock()

    for name, mod in [
        ("discord",              discord_mod),
        ("discord.ui",           ui_mod),
        ("discord.ext",          ext_mod),
        ("discord.ext.commands", cmd_mod),
        ("discord.app_commands", app_mod),
    ]:
        sys.modules[name] = mod


_make_discord_stub()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.get_channel.return_value = MagicMock()
    bot.fetch_channel = AsyncMock(return_value=MagicMock())
    return bot


# ---------------------------------------------------------------------------
# 1. Scheduler lifecycle
# ---------------------------------------------------------------------------

class TestSchedulerLifecycle(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        from scheduler.scheduler import ShopeeScheduler
        self.ShopeeScheduler = ShopeeScheduler

    async def test_scheduler_creates_all_jobs(self):
        from scheduler.scheduler import JOB_REGISTRY
        sched = self.ShopeeScheduler(bot=None)
        registered = {job.id for job in sched._apscheduler.get_jobs()}
        self.assertEqual(registered, set(JOB_REGISTRY.keys()))

    async def test_scheduler_starts_and_stops(self):
        import asyncio
        sched = self.ShopeeScheduler(bot=None)
        self.assertFalse(sched.running)
        sched.start()
        self.assertTrue(sched.running)
        sched.stop()
        await asyncio.sleep(0)  # yield to let AsyncIOScheduler update state
        self.assertFalse(sched.running)

    async def test_scheduler_status_structure(self):
        sched = self.ShopeeScheduler(bot=None)
        sched.start()
        status = sched.status()
        sched.stop()

        self.assertIn("running", status)
        self.assertIn("jobs", status)
        self.assertIn("job_count", status)
        self.assertEqual(status["job_count"], 5)
        for job in status["jobs"]:
            self.assertIn("id", job)
            self.assertIn("label", job)
            self.assertIn("next_run", job)

    async def test_run_job_now_raises_on_unknown_id(self):
        sched = self.ShopeeScheduler(bot=None)
        with self.assertRaises(ValueError):
            await sched.run_job_now("nonexistent_job")


# ---------------------------------------------------------------------------
# 2. Job simulation — 08:00 Morning Brief
# ---------------------------------------------------------------------------

class TestMorningBriefJob(unittest.IsolatedAsyncioTestCase):

    async def test_morning_brief_calls_services_and_sends(self):
        bot = _mock_bot()
        channel_mock = AsyncMock()
        bot.get_channel.return_value = channel_mock

        mock_brief_data = {
            "top_opportunities": [("Product A", 1000, 299.0, 5000)],
            "top_viral":         [("Product A", 299.0, 8000)],
            "top_niches":        [("Gadget", 50, 200)],
            "top_profit":        [],
            "generated_at":      "2026-06-13 08:00",
        }

        with (
            patch("discord_bot.services.operator_service.get_morning_brief",
                  return_value={"success": True, "data": mock_brief_data}),
            patch("discord_bot.services.discovery_service.get_daily_picks",
                  return_value={"success": True, "data": {}}),
            patch("shopee_engine.operator_center.content_worklist", return_value=[]),
            patch("discord_bot.config.CHANNEL_DAILY_PICKS", 111111),
        ):
            from scheduler.jobs.morning_brief import run_morning_brief
            await run_morning_brief(bot=bot)

        bot.get_channel.assert_called()

    async def test_morning_brief_handles_service_failure_gracefully(self):
        bot = _mock_bot()
        with (
            patch("discord_bot.services.operator_service.get_morning_brief",
                  return_value={"success": False, "error": "DB unavailable"}),
            patch("discord_bot.services.discovery_service.get_daily_picks",
                  return_value={"success": False, "error": "DB unavailable"}),
            patch("shopee_engine.operator_center.content_worklist", side_effect=Exception("err")),
            patch("discord_bot.config.CHANNEL_DAILY_PICKS", None),
        ):
            from scheduler.jobs.morning_brief import run_morning_brief
            await run_morning_brief(bot=bot)  # must not raise


# ---------------------------------------------------------------------------
# 3. Job simulation — 12:00 Trend Watch
# ---------------------------------------------------------------------------

class TestTrendWatchJob(unittest.IsolatedAsyncioTestCase):

    async def test_trend_watch_sends_three_embeds(self):
        bot = _mock_bot()
        channel_mock = AsyncMock()
        bot.get_channel.return_value = channel_mock

        trend_data = {
            "social_momentum": [("Prod A", 5000, 800, 199.0, 6.25)],
            "promo_surge":     [("Prod B", 35.0, 1200, 149.0)],
            "new_viral":       [("Prod C", 2500, 300, 299.0)],
        }

        with (
            patch("shopee_engine.operator_center.trend_watch", return_value=trend_data),
            patch("discord_bot.config.CHANNEL_ANALYTICS", 222222),
        ):
            from scheduler.jobs.trend_watch import run_trend_watch
            await run_trend_watch(bot=bot)

        bot.get_channel.assert_called_with(222222)

    async def test_trend_watch_handles_empty_data(self):
        bot = _mock_bot()
        with (
            patch("shopee_engine.operator_center.trend_watch",
                  return_value={"social_momentum": [], "promo_surge": [], "new_viral": []}),
            patch("discord_bot.config.CHANNEL_ANALYTICS", 222222),
        ):
            from scheduler.jobs.trend_watch import run_trend_watch
            await run_trend_watch(bot=bot)


# ---------------------------------------------------------------------------
# 4. Job simulation — 18:00 Evening Summary
# ---------------------------------------------------------------------------

class TestEveningSummaryJob(unittest.IsolatedAsyncioTestCase):

    async def test_evening_summary_sends_embeds(self):
        bot = _mock_bot()
        channel_mock = AsyncMock()
        bot.get_channel.return_value = channel_mock

        summary_data = {
            "total_products": 1000000,
            "total_commission": 1500.0,
            "opportunities": [("Prod A", 500, 299.0, 5000)],
            "market_gaps": [],
            "viral_candidates": [],
            "profit_candidates": [],
            "risks": [],
            "generated_at": "2026-06-13 18:00",
        }

        with (
            patch("discord_bot.services.operator_service.get_executive_summary",
                  return_value={"success": True, "data": summary_data}),
            patch("discord_bot.config.CHANNEL_EXECUTIVE", 333333),
        ):
            from scheduler.jobs.evening_summary import run_evening_summary
            await run_evening_summary(bot=bot)

        bot.get_channel.assert_called_with(333333)


# ---------------------------------------------------------------------------
# 5. Auto Queue verification
# ---------------------------------------------------------------------------

class TestAutoQueueJob(unittest.IsolatedAsyncioTestCase):

    async def test_auto_queue_generates_per_category(self):
        bot = _mock_bot()
        channel_mock = AsyncMock()
        bot.get_channel.return_value = channel_mock

        fake_brief = {
            "products": [
                ("Product X", 800, 199.0, 50, 10.0, 4.8, 4500),
                ("Product Y", 600, 149.0, 40, 8.0, 4.7, 3800),
                ("Product Z", 500, 99.0, 30, 5.0, 4.5, 3200),
            ]
        }

        added: list = []

        def _mock_queue_add(name, provider="template"):
            added.append(name)
            return len(added)

        with (
            patch("shopee_engine.operator_center.category_brief", return_value=fake_brief),
            patch("shopee_engine.content_engine.queue_add", side_effect=_mock_queue_add),
            patch("discord_bot.config.CHANNEL_CONTENT_QUEUE", 444444),
        ):
            from scheduler.jobs.auto_queue import run_auto_queue, AUTO_QUEUE_CATEGORIES
            await run_auto_queue(bot=bot)

        expected = len(AUTO_QUEUE_CATEGORIES) * 3
        self.assertEqual(len(added), expected)

    async def test_auto_queue_skips_on_engine_error(self):
        bot = _mock_bot()
        with (
            patch("shopee_engine.operator_center.category_brief",
                  side_effect=Exception("DB error")),
            patch("discord_bot.config.CHANNEL_CONTENT_QUEUE", None),
        ):
            from scheduler.jobs.auto_queue import run_auto_queue
            await run_auto_queue(bot=bot)  # must not raise


# ---------------------------------------------------------------------------
# 6. Weekly Report verification
# ---------------------------------------------------------------------------

class TestWeeklyReportJob(unittest.IsolatedAsyncioTestCase):

    async def test_weekly_report_exports_and_sends(self):
        bot = _mock_bot()
        channel_mock = AsyncMock()
        bot.get_channel.return_value = channel_mock

        from pathlib import Path
        fake_path = Path("/tmp/daily_report_2026-06-13.md")
        fake_path.touch()

        with (
            patch("shopee_engine.operator_center.daily_report", return_value=fake_path),
            patch("shopee_engine.operator_center.executive_summary",
                  return_value={"total_products": 1000000, "total_commission": 0.0,
                                "generated_at": "2026-06-13 20:00",
                                "opportunities": [], "market_gaps": [],
                                "viral_candidates": [], "profit_candidates": [], "risks": []}),
            patch("discord_bot.config.CHANNEL_ANALYTICS", 555555),
        ):
            from scheduler.jobs.weekly_report import run_weekly_report
            await run_weekly_report(bot=bot)

        fake_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 7. Embed builders
# ---------------------------------------------------------------------------

class TestSchedulerEmbeds(unittest.TestCase):

    def test_build_trend_watch_embeds_returns_three(self):
        from discord_bot.embeds.scheduler_embeds import build_trend_watch_embeds
        data = {
            "social_momentum": [("P1", 5000, 800, 199.0, 6.25)],
            "promo_surge":     [("P2", 35.0, 1200, 149.0)],
            "new_viral":       [("P3", 2500, 300, 299.0)],
        }
        embeds = build_trend_watch_embeds(data)
        self.assertEqual(len(embeds), 3)
        self.assertIn("Social Momentum", embeds[0].title)
        self.assertIn("Promo Surge",     embeds[1].title)
        self.assertIn("Emerging",        embeds[2].title)

    def test_build_trend_watch_embeds_empty_data(self):
        from discord_bot.embeds.scheduler_embeds import build_trend_watch_embeds
        embeds = build_trend_watch_embeds({"social_momentum": [], "promo_surge": [], "new_viral": []})
        self.assertEqual(len(embeds), 3)

    def test_build_content_worklist_embed(self):
        from discord_bot.embeds.scheduler_embeds import build_content_worklist_embed
        worklist = [
            {"name": "Product A", "priority": "P1 — URGENT", "hook": "ลดไป 35%",
             "format": "TikTok 15s", "platform": "TikTok"},
        ]
        e = build_content_worklist_embed(worklist)
        self.assertIn("Worklist", e.title)
        self.assertEqual(len(e._fields), 1)

    def test_build_auto_queue_result_embed(self):
        from discord_bot.embeds.scheduler_embeds import build_auto_queue_result_embed
        results = {"Gadget": ["Prod A", "Prod B"], "Health": ["Prod C"]}
        e = build_auto_queue_result_embed(results, total_ok=3, total_skip=0)
        self.assertIn("3", e.description)
        self.assertEqual(len(e._fields), 2)

    def test_build_scheduler_status_embed_running(self):
        from discord_bot.embeds.scheduler_embeds import build_scheduler_status_embed
        status = {
            "running": True,
            "job_count": 5,
            "jobs": [
                {"id": "morning_brief", "label": "Morning Brief",
                 "description": "08:00 test", "next_run": "2026-06-14 08:00"},
            ],
        }
        e = build_scheduler_status_embed(status)
        self.assertIn("Running", e.title)

    def test_build_scheduler_status_embed_stopped(self):
        from discord_bot.embeds.scheduler_embeds import build_scheduler_status_embed
        e = build_scheduler_status_embed({"running": False, "jobs": [], "job_count": 0})
        self.assertIn("Stopped", e.title)

    def test_build_job_result_embed_success(self):
        from discord_bot.embeds.scheduler_embeds import build_job_result_embed
        e = build_job_result_embed("morning_brief", "Morning Brief", success=True)
        self.assertIn("✅", e.title)

    def test_build_job_result_embed_failure(self):
        from discord_bot.embeds.scheduler_embeds import build_job_result_embed
        e = build_job_result_embed("morning_brief", "Morning Brief", success=False, detail="DB error")
        self.assertIn("❌", e.title)

    def test_build_weekly_report_embed(self):
        from discord_bot.embeds.scheduler_embeds import build_weekly_report_embed
        from pathlib import Path
        data = {
            "total_products": 1000000, "total_commission": 1500.0,
            "generated_at": "2026-06-13 20:00",
            "opportunities": [("P1", 500, 299.0, 5000)],
            "viral_candidates": [("P2", 199.0, 8000)],
        }
        e = build_weekly_report_embed(data, exported=[Path("report.md")])
        self.assertIn("Weekly Report", e.title)
        self.assertIn("1,000,000", e.description)


# ---------------------------------------------------------------------------
# 8. discord_notify
# ---------------------------------------------------------------------------

class TestDiscordNotify(unittest.IsolatedAsyncioTestCase):

    async def test_send_to_channel_no_channel_id(self):
        from scheduler.notifications.discord_notify import send_to_channel
        result = await send_to_channel(bot=MagicMock(), channel_id=None, embeds=[MagicMock()])
        self.assertFalse(result)

    async def test_send_to_channel_no_bot(self):
        from scheduler.notifications.discord_notify import send_to_channel
        result = await send_to_channel(bot=None, channel_id=123, embeds=[MagicMock()])
        self.assertFalse(result)

    async def test_send_to_channel_success(self):
        from scheduler.notifications.discord_notify import send_to_channel

        channel_mock = AsyncMock()
        channel_mock.send = AsyncMock()

        bot = MagicMock()
        bot.get_channel.return_value = channel_mock

        import sys, types as _t
        embed = sys.modules["discord"].Embed(title="Test")

        result = await send_to_channel(bot=bot, channel_id=123456, embeds=[embed])
        self.assertTrue(result)
        channel_mock.send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
