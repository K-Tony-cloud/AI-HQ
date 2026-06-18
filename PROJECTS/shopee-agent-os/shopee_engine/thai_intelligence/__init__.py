"""
Thai Content Intelligence Engine.

Subsystem for อะไรของมัน Facebook page.
Provides pattern library, slang dictionary, comment intelligence,
voice definition, and a DuckDB-backed self-learning loop.

Usage:
    from shopee_engine.thai_intelligence import get_hook, get_cta, check_quality
"""

from .pattern_library import (
    AI_OPENERS,
    SUBS,
    POLL_SIGNALS,
    HOOK_SIGNALS,
    get_hook,
    get_cta,
    get_pattern_weight,
)
from .slang_dictionary import (
    get_slang,
    get_slang_by_category,
    inject_slang,
)
from .comment_intelligence import (
    get_engagement_opener,
    get_community_phrase,
    get_humor_hook,
)
from .voice_definition import (
    PAGE_VOICE,
    check_content_quality,
)

__all__ = [
    "AI_OPENERS",
    "SUBS",
    "POLL_SIGNALS",
    "HOOK_SIGNALS",
    "get_hook",
    "get_cta",
    "get_pattern_weight",
    "get_slang",
    "get_slang_by_category",
    "inject_slang",
    "get_engagement_opener",
    "get_community_phrase",
    "get_humor_hook",
    "PAGE_VOICE",
    "check_content_quality",
]
