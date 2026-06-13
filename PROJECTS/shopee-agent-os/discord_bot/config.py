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

# Channel IDs (optional — set in .env to enable channel routing)
CHANNEL_DAILY_PICKS:      int | None = int(v) if (v := os.getenv("CHANNEL_DAILY_PICKS")) else None
CHANNEL_VIRAL:            int | None = int(v) if (v := os.getenv("CHANNEL_VIRAL")) else None
CHANNEL_PROFIT:           int | None = int(v) if (v := os.getenv("CHANNEL_PROFIT")) else None
CHANNEL_CONTENT_QUEUE:    int | None = int(v) if (v := os.getenv("CHANNEL_CONTENT_QUEUE")) else None
CHANNEL_ANALYTICS:        int | None = int(v) if (v := os.getenv("CHANNEL_ANALYTICS")) else None
CHANNEL_EXECUTIVE:        int | None = int(v) if (v := os.getenv("CHANNEL_EXECUTIVE_SUMMARY")) else None

PAGE_SIZE = 10  # Products per embed page
