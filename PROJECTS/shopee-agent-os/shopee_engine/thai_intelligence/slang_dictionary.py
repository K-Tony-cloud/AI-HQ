"""
Thai Content Intelligence — Slang Dictionary.

Thai internet slang, meme phrases, and viral language for เพจอะไรของมัน.
Each entry has metadata for intelligent context-aware selection.

Categories:
  reaction     — express how you feel ("555", "โห", "อ้าว")
  relatable    — "same energy" phrases ("แค่กูรึเปล่า", "บ้านกูก็")
  sarcasm      — mild sarcastic spice ("งงมากกว่านี้ไม่มีแล้ว", "เก่งจริงๆ")
  hype         — amplify excitement ("เฮ้ยจริงดิ", "โคตรดี")
  community    — in-group bonding ("ทีมไหนกันบ้าง", "ใครเหมือนกัน")
  filler       — spoken sentence fillers ("อะ", "นะ", "วะ", "เว้ย")
  nostalgia    — past-tense relatable ("สมัยเด็ก", "ยุค 90s")
  meme         — recognizable meme formats ("เขาก็เลย...", "แต่ตอนนั้น")
"""

from __future__ import annotations

import random
from typing import NamedTuple


class Slang(NamedTuple):
    phrase: str
    category: str
    popularity: float   # 0-1, higher = more mainstream safe
    contexts: list[str] # post types this fits best
    note: str = ""


SLANG_DICT: list[Slang] = [
    # ── Reactions ──────────────────────────────────────────────────────────────
    Slang("555", "reaction", 1.0, ["comment_bait", "weird_product", "nostalgia"], "universal laugh"),
    Slang("555+", "reaction", 0.9, ["comment_bait", "weird_product"], "stronger laugh"),
    Slang("โห", "reaction", 0.9, ["nostalgia", "weird_product", "visual_curiosity"], "wow/impressed"),
    Slang("อ้าว", "reaction", 0.8, ["weird_product", "trending"], "surprised/confused"),
    Slang("แม่เจ้า", "reaction", 0.7, ["weird_product", "visual_curiosity"], "shocked"),
    Slang("โอ้โห", "reaction", 0.9, ["weird_product", "nostalgia"], "impressive wow"),
    Slang("เฮ้ย", "reaction", 0.9, ["comment_bait", "weird_product", "trending"], "hey/wait what"),
    Slang("อ่อ", "reaction", 0.8, ["trending", "affiliate"], "I see / ah okay"),
    Slang("เออ", "reaction", 0.9, ["comment_bait", "nostalgia"], "yeah/right"),
    Slang("อย่างงี้มีด้วย", "reaction", 0.8, ["weird_product"], "this exists??"),

    # ── Relatable ──────────────────────────────────────────────────────────────
    Slang("แค่กูรึเปล่า", "relatable", 1.0, ["comment_bait"], "am i the only one"),
    Slang("บ้านกูก็เป็น", "relatable", 1.0, ["comment_bait", "nostalgia"], "same at my house"),
    Slang("กูคนเดียวรึเปล่า", "relatable", 1.0, ["comment_bait"], "am i alone in this"),
    Slang("กูด้วย", "relatable", 0.9, ["comment_bait", "nostalgia"], "me too"),
    Slang("กูเลย", "relatable", 0.9, ["comment_bait"], "that's me"),
    Slang("กูทุกวัน", "relatable", 0.8, ["comment_bait"], "me every day"),
    Slang("นี่คือกูชัดๆ", "relatable", 0.9, ["comment_bait"], "this is literally me"),
    Slang("โดนใจมากๆ", "relatable", 0.9, ["comment_bait", "nostalgia"], "hits close to home"),
    Slang("ทำไมตรงใจขนาดนี้", "relatable", 0.9, ["comment_bait"], "why is this so accurate"),
    Slang("เหมือนโพสต์นี้เขียนถึงกูเลย", "relatable", 0.8, ["comment_bait"], "written about me"),

    # ── Sarcasm ────────────────────────────────────────────────────────────────
    Slang("เก่งมากเลยนะ 💀", "sarcasm", 0.8, ["weird_product"], "wow so smart (sarcastic)"),
    Slang("ฉลาดมากจริงๆ 💀", "sarcasm", 0.7, ["weird_product"], "so smart (sarcastic)"),
    Slang("อัจฉริยะหรือบ้ากันแน่", "sarcasm", 0.8, ["weird_product"], "genius or crazy"),
    Slang("งงมากกว่านี้ไม่มีแล้ว", "sarcasm", 0.8, ["weird_product", "trending"], "can't be more confused"),
    Slang("ยังไงอะ 💀", "sarcasm", 0.8, ["weird_product", "trending"], "how though (wtf)"),
    Slang("โลกนี้ไปไกลแล้ว", "sarcasm", 0.9, ["weird_product"], "world has gone far"),
    Slang("ปกติมากเลยนะ", "sarcasm", 0.7, ["weird_product"], "totally normal (not)"),

    # ── Hype ───────────────────────────────────────────────────────────────────
    Slang("เฮ้ยจริงดิ", "hype", 0.9, ["trending", "comment_bait"], "wait really"),
    Slang("โคตรดี", "hype", 0.8, ["affiliate", "weird_product"], "super good"),
    Slang("ดีมากๆ เลยนะ", "hype", 0.9, ["affiliate"], "really good"),
    Slang("จริงๆ เลย", "hype", 0.9, ["comment_bait", "nostalgia"], "for real"),
    Slang("มันส์มากเลย", "hype", 0.8, ["trending", "comment_bait"], "so fun"),
    Slang("แจ่มมาก", "hype", 0.7, ["affiliate", "nostalgia"], "awesome (older gen)"),

    # ── Community ──────────────────────────────────────────────────────────────
    Slang("ทีมไหนกันบ้าง", "community", 1.0, ["comment_bait"], "which team are you"),
    Slang("ใครเหมือนกันบ้าง", "community", 1.0, ["comment_bait"], "anyone else same"),
    Slang("ยกมือหน่อย", "community", 0.9, ["comment_bait"], "raise your hand"),
    Slang("กดถูกใจถ้าเหมือนกัน", "community", 0.8, ["comment_bait"], "like if same"),
    Slang("เพื่อนๆ ว่ายังไงกัน", "community", 0.9, ["comment_bait", "trending"], "what do y'all think"),
    Slang("ใครอยู่ทีมเดียวกัน", "community", 0.9, ["comment_bait"], "who's on same team"),

    # ── Fillers (spoken particles) ─────────────────────────────────────────────
    Slang("อะ", "filler", 1.0, ["comment_bait", "weird_product", "trending"], "sentence ender particle"),
    Slang("นะ", "filler", 1.0, ["comment_bait", "nostalgia", "affiliate"], "softening particle"),
    Slang("วะ", "filler", 0.9, ["comment_bait", "weird_product"], "casual emphasis"),
    Slang("เว้ย", "filler", 0.8, ["comment_bait", "weird_product"], "hey/wow (informal)"),
    Slang("ว่ะ", "filler", 0.8, ["comment_bait"], "casual emphasis (alt)"),
    Slang("จ้า", "filler", 0.7, ["affiliate", "nostalgia"], "polite friendly ender"),
    Slang("นะจ๊ะ", "filler", 0.6, ["affiliate"], "cute friendly ender"),

    # ── Nostalgia ──────────────────────────────────────────────────────────────
    Slang("สมัยเด็ก", "nostalgia", 1.0, ["nostalgia"], "when we were kids"),
    Slang("ยุค 90s", "nostalgia", 0.9, ["nostalgia"], "90s era"),
    Slang("ยุค 2000s", "nostalgia", 0.9, ["nostalgia"], "2000s era"),
    Slang("สมัยก่อน", "nostalgia", 1.0, ["nostalgia"], "back in the day"),
    Slang("ตอนเด็กๆ", "nostalgia", 1.0, ["nostalgia"], "as a kid"),
    Slang("เด็กยุค 90", "nostalgia", 0.9, ["nostalgia"], "90s kids"),
    Slang("คิดถึงมาก", "nostalgia", 1.0, ["nostalgia"], "miss it so much"),
    Slang("เวลาผ่านไปเร็วมาก", "nostalgia", 0.9, ["nostalgia"], "time flies"),

    # ── Meme formats ───────────────────────────────────────────────────────────
    Slang("แต่ตอนนั้น", "meme", 0.8, ["nostalgia", "comment_bait"], "but back then"),
    Slang("เขาก็เลย", "meme", 0.7, ["comment_bait", "weird_product"], "so they/he just"),
    Slang("ไม่มีใครบอกเลยว่า", "meme", 0.8, ["comment_bait"], "nobody told me that"),
    Slang("ตอนนี้เพิ่งรู้", "meme", 0.8, ["comment_bait", "trending"], "only just found out"),
    Slang("ทำไมไม่มีใครพูดถึง", "meme", 0.8, ["trending", "comment_bait"], "why doesn't anyone talk about this"),
    Slang("POV:", "meme", 0.8, ["comment_bait", "visual_curiosity"], "point of view format"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_slang(category: str, post_type: str = "", rng: random.Random | None = None,
              min_popularity: float = 0.7) -> str | None:
    """Return a random slang phrase for the given category and post type."""
    candidates = [
        s for s in SLANG_DICT
        if s.category == category
        and s.popularity >= min_popularity
        and (not post_type or post_type in s.contexts)
    ]
    if not candidates:
        return None
    r = rng or random.Random()
    return r.choice(candidates).phrase


def get_slang_by_category(category: str) -> list[Slang]:
    """Return all slang entries for a category."""
    return [s for s in SLANG_DICT if s.category == category]


def inject_slang(text: str, post_type: str = "comment_bait",
                 rng: random.Random | None = None) -> str:
    """
    Inject one contextual filler particle into the text where appropriate.
    Only fires if the text has fewer than 2 spoken particles already.
    """
    spoken_particles = ["อะ", "นะ", "วะ", "เว้ย", "ว่ะ"]
    particle_count = sum(text.count(p) for p in spoken_particles)
    if particle_count >= 2:
        return text

    r = rng or random.Random()
    slang = get_slang("filler", post_type, r)
    if not slang:
        return text

    # Find the first question mark or end of first sentence to inject after
    lines = text.split("\n")
    if not lines:
        return text

    first_line = lines[0]
    if first_line.endswith("?") or first_line.endswith("?"):
        lines[0] = first_line[:-1] + slang + "?"
    return "\n".join(lines)


def get_reaction(post_type: str = "", rng: random.Random | None = None) -> str:
    """Return a reaction phrase appropriate for the post type."""
    r = rng or random.Random()
    phrase = get_slang("reaction", post_type, r)
    return phrase or "โห"
