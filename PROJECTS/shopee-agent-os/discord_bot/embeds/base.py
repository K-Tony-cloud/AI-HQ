"""Base embed helpers and paginated view for shopee-agent-os Discord bot."""

from __future__ import annotations

from datetime import datetime, timezone

import discord

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

COLORS = {
    "opportunity": 0x00C851,  # Green
    "viral":       0xAA00FF,  # Purple
    "profit":      0xFFBB33,  # Gold
    "content":     0x0099CC,  # Blue
    "operator":    0x00ACC1,  # Teal
    "queue":       0x33B5E5,  # Light blue
    "niche":       0x00BCD4,  # Cyan
    "trend":       0xFF6D00,  # Orange
    "error":       0xFF4444,  # Red
    "success":     0x00C851,  # Green
    "info":        0x607D8B,  # Grey
}

FOOTER_TEXT = "shopee-agent-os • Affiliate Intelligence"


# ---------------------------------------------------------------------------
# Base embed factory
# ---------------------------------------------------------------------------

def make_embed(
    title: str,
    color_key: str = "operator",
    description: str = "",
    url: str | None = None,
) -> discord.Embed:
    e = discord.Embed(
        title=title,
        description=description,
        color=COLORS.get(color_key, 0x00ACC1),
        timestamp=datetime.now(tz=timezone.utc),
        url=url,
    )
    e.set_footer(text=FOOTER_TEXT)
    return e


def error_embed(message: str) -> discord.Embed:
    e = discord.Embed(
        title="❌ Error",
        description=f"```\n{message[:2000]}\n```",
        color=COLORS["error"],
        timestamp=datetime.now(tz=timezone.utc),
    )
    e.set_footer(text=FOOTER_TEXT)
    return e


def loading_embed(text: str = "Loading…") -> discord.Embed:
    return make_embed(f"⏳ {text}", color_key="info")


# ---------------------------------------------------------------------------
# Paginated view
# ---------------------------------------------------------------------------

class PaginatedView(discord.ui.View):
    """Button pagination for multi-page embed lists."""

    def __init__(self, pages: list[discord.Embed], timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current = 0
        self._update()

    def _update(self) -> None:
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current >= len(self.pages) - 1
        # Show page number in embed footer
        for i, page in enumerate(self.pages):
            page.set_footer(text=f"{FOOTER_TEXT} • Page {i+1}/{len(self.pages)}")

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.current -= 1
        self._update()
        await interaction.response.edit_message(
            embed=self.pages[self.current], view=self
        )

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.current += 1
        self._update()
        await interaction.response.edit_message(
            embed=self.pages[self.current], view=self
        )

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Channel-routing helper for slash commands
# ---------------------------------------------------------------------------

async def send_and_confirm(
    interaction: discord.Interaction,
    embeds: list[discord.Embed],
    channel_id: int | None,
    *,
    content: str | None = None,
) -> None:
    """Post embeds to a configured channel and acknowledge the interaction.

    If channel_id is set the embeds go to that channel and the interaction
    receives a short confirmation.  If channel_id is None the embeds are
    sent as the interaction reply (original in-place behaviour).
    """
    if channel_id:
        bot = interaction.client
        try:
            ch = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
            for i in range(0, max(len(embeds), 1), 10):
                batch = embeds[i : i + 10]
                if batch:
                    await ch.send(content=content if i == 0 else None, embeds=batch)
            await interaction.followup.send(f"✅ Posted to <#{channel_id}>", ephemeral=True)
            return
        except Exception:
            pass  # fall through to in-place reply on any channel error

    # Fallback: reply in-place with pagination if needed
    if not embeds:
        return
    if len(embeds) == 1:
        await interaction.followup.send(content=content, embed=embeds[0])
    else:
        view = PaginatedView(embeds)
        await interaction.followup.send(content=content, embed=embeds[0], view=view)
