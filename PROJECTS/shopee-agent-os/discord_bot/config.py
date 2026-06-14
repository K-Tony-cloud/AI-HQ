"""Load Discord bot configuration from .env file."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # python-dotenv optional; can use env vars directly

DISCORD_TOKEN: str    = os.getenv("DISCORD_TOKEN", "")
DISCORD_GUILD_ID: str = os.getenv("DISCORD_GUILD_ID", "")


def _ch(key: str) -> int | None:
    v = os.getenv(key)
    return int(v) if v else None


# ── CONTROL CENTER ────────────────────────────────────────────────────────────
CHANNEL_CONTROL_CENTER: int | None = _ch("CHANNEL_CONTROL_CENTER")
CHANNEL_BOT_COMMANDS:   int | None = _ch("CHANNEL_BOT_COMMANDS")

# ── DAILY INTELLIGENCE ───────────────────────────────────────────────────────
CHANNEL_MORNING_BRIEF:  int | None = _ch("CHANNEL_MORNING_BRIEF")
CHANNEL_DAILY_PICKS:    int | None = _ch("CHANNEL_DAILY_PICKS")
CHANNEL_TREND_WATCH:    int | None = _ch("CHANNEL_TREND_WATCH")
CHANNEL_VIRAL:          int | None = _ch("CHANNEL_VIRAL")

# ── CONTENT FACTORY ──────────────────────────────────────────────────────────
CHANNEL_CONTENT_QUEUE:    int | None = _ch("CHANNEL_CONTENT_QUEUE")
CHANNEL_APPROVED_CONTENT: int | None = _ch("CHANNEL_APPROVED_CONTENT")

# ── AFFILIATE OPERATIONS ─────────────────────────────────────────────────────
CHANNEL_AFFILIATE_LINKS: int | None = _ch("CHANNEL_AFFILIATE_LINKS")
CHANNEL_MISSING_LINKS:   int | None = _ch("CHANNEL_MISSING_LINKS")
CHANNEL_LINK_COVERAGE:   int | None = _ch("CHANNEL_LINK_COVERAGE")

# ── REVENUE & ANALYTICS ──────────────────────────────────────────────────────
CHANNEL_REVENUE:          int | None = _ch("CHANNEL_REVENUE")
CHANNEL_TOP_EARNERS:      int | None = _ch("CHANNEL_TOP_EARNERS")
CHANNEL_LEARNING_REPORTS: int | None = _ch("CHANNEL_LEARNING_REPORTS")
CHANNEL_PROFIT:           int | None = _ch("CHANNEL_PROFIT")
CHANNEL_ANALYTICS:        int | None = _ch("CHANNEL_ANALYTICS")
CHANNEL_EXECUTIVE:        int | None = _ch("CHANNEL_EXECUTIVE_SUMMARY")
CHANNEL_WEEKLY_REPORT:    int | None = _ch("CHANNEL_WEEKLY_REPORT")

# ── SYSTEM ───────────────────────────────────────────────────────────────────
CHANNEL_SYSTEM_LOG:    int | None = _ch("CHANNEL_SYSTEM_LOG")
CHANNEL_SCHEDULER_LOG: int | None = _ch("CHANNEL_SCHEDULER_LOG")
CHANNEL_BOT_STATUS:    int | None = _ch("CHANNEL_BOT_STATUS")

PAGE_SIZE = 10  # Products per embed page

SCHEDULER_TIMEZONE: str = os.getenv("SCHEDULER_TIMEZONE", "Asia/Bangkok")
