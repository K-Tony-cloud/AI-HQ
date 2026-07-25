"""Title cleaning utilities for Shopee SEO articles.

Cleans raw Shopee product titles for web display without modifying spec values.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Leading bracket promo tags like [ส่งด่วน], [พร้อมส่ง], [แถมถุง...], [ส่งฟรี], [โปรโมชั่น]
_BRACKET_PROMO_RE = re.compile(
    r"^\s*(?:\[[^\]]{0,50}\]\s*)+",
    re.IGNORECASE,
)

# Leading emoji prefixes (common promo emojis)
_EMOJI_PREFIX_RE = re.compile(
    r"^[\s🔥✅🎁💥⚡🏆🎉]+",
)

# Repeated punctuation: !!!, ..., ~~~, ???
_REPEATED_PUNCT_RE = re.compile(r"([!?.~]{2,})")

# Price patterns like ฿209, ฿1,990
_PRICE_PATTERN_RE = re.compile(r"฿[\d,]+\b\s*")

# Suspicious mAh: ends in digit 1 but not a round number (e.g. 10001, 20001, 30001)
# Pattern: 4-6 digit number ending in 1 followed by mAh (case-insensitive)
_SUSPICIOUS_MAH_RE = re.compile(
    r"\b(\d{4,6}1)\s*mAh\b",
    re.IGNORECASE,
)

# Max chars before flagging "too long"
_FLAG_LONG_THRESHOLD = 120

# Truncate display_title at this many chars
_TRUNCATE_AT = 80


def clean_display_title(raw_title: str) -> dict:
    """Clean a raw Shopee product title for web display.

    Returns:
        {
          "display_title": str,   # cleaned title for web display
          "raw_title":     str,   # original unchanged
          "flags":         list[str],  # list of issues found
          "truncated":     bool,
        }

    Cleaning rules applied (in order):
    1. Strip leading bracket promo tags (e.g. [ส่งด่วน], [พร้อมส่ง])
    2. Strip leading emoji prefixes (🔥✅🎁💥⚡🏆🎉)
    3. Remove repeated punctuation (!!!, ..., ~~~)
    4. Remove price patterns (฿XXX) — shown separately
    5. Strip trailing/leading whitespace and collapse internal spaces

    Flags added (do NOT modify spec values):
    - "suspicious_mah: NNNNNmAh" if mAh value ends in 1 (e.g. 20001, 30001)
    - "title_too_long" if cleaned title > 120 chars

    Truncation:
    - display_title truncated at 80 chars with … suffix if longer
    - raw_title is always untouched
    """
    flags: list[str] = []

    # --- Step 1: Strip leading bracket promo tags ---
    cleaned = _BRACKET_PROMO_RE.sub("", raw_title)

    # --- Step 2: Strip leading emoji prefixes ---
    cleaned = _EMOJI_PREFIX_RE.sub("", cleaned)

    # --- Step 3: Remove repeated punctuation ---
    cleaned = _REPEATED_PUNCT_RE.sub(lambda m: m.group(1)[0], cleaned)

    # --- Step 4: Remove price patterns ---
    cleaned = _PRICE_PATTERN_RE.sub("", cleaned)

    # --- Step 5: Normalize whitespace ---
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()

    # --- Flagging: suspicious mAh (ends in 1, not round) ---
    for m in _SUSPICIOUS_MAH_RE.finditer(raw_title):
        mah_val = m.group(1)
        flags.append(f"suspicious_mah: {mah_val}mAh")

    # --- Flagging: title too long (after cleaning) ---
    if len(cleaned) > _FLAG_LONG_THRESHOLD:
        flags.append("title_too_long")

    # --- Truncation for display ---
    truncated = False
    display_title = cleaned
    if len(cleaned) > _TRUNCATE_AT:
        display_title = cleaned[:_TRUNCATE_AT].rstrip() + "…"
        truncated = True

    return {
        "display_title": display_title,
        "raw_title":     raw_title,
        "flags":         flags,
        "truncated":     truncated,
    }
