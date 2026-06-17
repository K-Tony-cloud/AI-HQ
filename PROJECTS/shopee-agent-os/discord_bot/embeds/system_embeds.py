"""Embeds for /system-status."""

from __future__ import annotations

import discord


def build_system_status_embed(status: dict) -> discord.Embed:
    host = status.get("host", "Unknown")
    region = status.get("region", "")
    host_label = f"{host} ({region})" if region else host

    uptime_str = status.get("uptime", "—")
    bot_name = status.get("bot_name", "—")
    guild_count = status.get("guild_count", 0)
    sched_running = status.get("scheduler_running", False)
    job_count = status.get("job_count", 0)
    next_brief = status.get("next_morning_brief", "—")
    db_path = status.get("db_path", "—")
    db_products = status.get("db_products", None)
    py_version = status.get("py_version", "—")

    color = discord.Color.green() if sched_running else discord.Color.orange()
    embed = discord.Embed(title="🖥 System Status — Shopee Agent OS", color=color)

    embed.add_field(name="🌐 Host", value=host_label, inline=True)
    embed.add_field(name="⏱ Uptime", value=uptime_str, inline=True)
    embed.add_field(name="🐍 Python", value=py_version, inline=True)

    bot_status = f"✅ {bot_name}" if bot_name != "—" else "❌ Disconnected"
    embed.add_field(name="🤖 Bot", value=bot_status, inline=True)
    embed.add_field(name="🏠 Guilds", value=str(guild_count), inline=True)

    sched_label = f"✅ Running ({job_count} jobs)" if sched_running else "⚠️ Stopped"
    embed.add_field(name="📅 Scheduler", value=sched_label, inline=True)

    embed.add_field(name="⏰ Next Morning Brief", value=next_brief, inline=False)

    db_label = db_path
    if db_products is not None:
        db_label += f" — {db_products:,} products"
    embed.add_field(name="🗄 Database", value=db_label, inline=False)

    jobs = status.get("jobs", [])
    if jobs:
        lines = "\n".join(
            f"`{j['id']}` — {j['next_run']}" for j in jobs
        )
        embed.add_field(name="📋 All Jobs", value=lines, inline=False)

    embed.set_footer(text="shopee-agent-os • Phase 10.6")
    return embed
