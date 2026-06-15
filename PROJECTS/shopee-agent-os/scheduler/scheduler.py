"""ShopeeScheduler — APScheduler wrapper for automated affiliate operations."""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Asia/Bangkok")

JOB_REGISTRY: dict[str, dict] = {
    "morning_brief": {
        "label":       "Morning Brief",
        "description": "08:00 — Top Opportunities, Viral, Profit, Daily Picks, Content Worklist",
        "cron":        {"hour": 8,  "minute": 0},
    },
    "trend_watch": {
        "label":       "Midday Trend Watch",
        "description": "12:00 — Emerging Products, Trending Categories, Viral Candidates",
        "cron":        {"hour": 12, "minute": 0},
    },
    "evening_summary": {
        "label":       "Evening Executive Summary",
        "description": "18:00 — Performance Summary, Top Profit, Opportunities, Risks",
        "cron":        {"hour": 18, "minute": 0},
    },
    "auto_queue": {
        "label":       "Auto Queue Generator",
        "description": "06:30 daily — Content queue for Gadget/Home/Mobile/Baby/Health/Camping",
        "cron":        {"hour": 6,  "minute": 30},
    },
    "weekly_report": {
        "label":       "Weekly Report",
        "description": "Sunday 20:00 — Export MD/HTML/CSV and post to Discord",
        "cron":        {"day_of_week": "sun", "hour": 20, "minute": 0},
    },
}


class ShopeeScheduler:
    """Manages all scheduled affiliate automation jobs."""

    def __init__(self, bot=None) -> None:
        self.bot = bot
        self._apscheduler = AsyncIOScheduler(timezone=TZ)
        self._register_jobs()

    def _register_jobs(self) -> None:
        from scheduler.jobs.morning_brief  import run_morning_brief
        from scheduler.jobs.trend_watch    import run_trend_watch
        from scheduler.jobs.evening_summary import run_evening_summary
        from scheduler.jobs.auto_queue     import run_auto_queue
        from scheduler.jobs.weekly_report  import run_weekly_report

        _funcs = {
            "morning_brief":   run_morning_brief,
            "trend_watch":     run_trend_watch,
            "evening_summary": run_evening_summary,
            "auto_queue":      run_auto_queue,
            "weekly_report":   run_weekly_report,
        }

        for job_id, meta in JOB_REGISTRY.items():
            self._apscheduler.add_job(
                _funcs[job_id],
                trigger=CronTrigger(**meta["cron"], timezone=TZ),
                id=job_id,
                kwargs={"bot": self.bot},
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=3600,
                coalesce=True,
            )
            logger.debug("[scheduler] registered: %s", job_id)

    def start(self) -> None:
        if not self._apscheduler.running:
            self._apscheduler.start()
            logger.info("[scheduler] Started — %d jobs registered", len(JOB_REGISTRY))

    def stop(self) -> None:
        if self._apscheduler.running:
            self._apscheduler.shutdown(wait=False)
            logger.info("[scheduler] Stopped")

    @property
    def running(self) -> bool:
        return self._apscheduler.running

    def status(self) -> dict:
        jobs = []
        for job in self._apscheduler.get_jobs():
            meta = JOB_REGISTRY.get(job.id, {})
            jobs.append({
                "id":          job.id,
                "label":       meta.get("label", job.id),
                "description": meta.get("description", ""),
                "next_run":    str(job.next_run_time) if job.next_run_time else "—",
            })
        return {"running": self.running, "jobs": jobs, "job_count": len(jobs)}

    async def run_job_now(self, job_id: str) -> None:
        job = self._apscheduler.get_job(job_id)
        if job is None:
            raise ValueError(
                f"Unknown job: '{job_id}'. Valid IDs: {list(JOB_REGISTRY)}"
            )
        await job.func(**job.kwargs)
