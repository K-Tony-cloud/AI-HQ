"""
Thai Content Intelligence — Pattern Library.

Central store for all engagement patterns.
Each pattern has an ID (used by learning loop) and a mutable weight.
Weights start at 1.0. Learning loop raises/lowers based on engagement.

Pattern ID format:
  h_<type>_<nn>  = hook
  cta_<key>_<nn> = CTA
  sub_<nn>       = substitution rule (static, never weighted)
"""

from __future__ import annotations

import random
from typing import NamedTuple


class Pattern(NamedTuple):
    id: str
    text: str
    weight: float = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# AI opener patterns to strip (Pass 1) — ordered longest-first
# ─────────────────────────────────────────────────────────────────────────────

AI_OPENERS: list[str] = [
    "คำถามที่อยากรู้มานาน 🤔\n\n",
    "คำถามที่อยากรู้มานาน\n\n",
    "คำถามที่น่าสนใจ:\n\n",
    "คำถาม:\n\n",
    "คำถาม: ",
    "น่าสนใจมากที่",
    "น่าสนใจมาก: ",
    "ที่น่าสนใจคือ ",
    "ปฏิเสธไม่ได้ว่า ",
    "เชื่อหรือไม่ว่า ",
    "เชื่อหรือไม่ ",
    "ในยุคปัจจุบัน ",
    "ในยุคที่ ",
    "ในสังคมไทย ",
    "คุณเคยสังเกตไหมว่า ",
    "คุณเคย ",
    "ในปัจจุบัน ",
    "มีการศึกษาพบว่า ",
    "งานวิจัยพบว่า ",
    "จากการสำรวจ ",
    "ผลการศึกษา ",
    "เป็นที่ทราบกันดีว่า ",
    "ไม่ว่าจะ ",
    "สิ่งที่น่าสนใจคือ ",
]


# ─────────────────────────────────────────────────────────────────────────────
# Substitution table (Pass 2) — ordered longest-first
# (static rules, no weighting needed)
# ─────────────────────────────────────────────────────────────────────────────

SUBS: list[tuple[str, str]] = [
    # AI CTA blocks → casual
    ("Comment บอกได้เลยว่าคุณเป็นทีมไหน 👇",         "เธออยู่ทีมไหนวะ 👇"),
    ("Comment บอกได้เลยว่าคุณ",                        "บอกมาเลยว่าเธอ"),
    ("Comment บอกได้เลย — ไม่มีคำตอบถูกหรือผิด 👇",   "บอกมาเลยนะ 👇"),
    ("Comment บอกได้เลย ไม่ตัดสิน 👇",                "บอกมาเลย ไม่ตัดสินนะ 👇"),
    ("Comment บอกได้เลย 👇",                           "บอกมาเลย 👇"),
    ("Comment บอกได้เลย",                              "บอกมาเลยนะ"),
    ("Comment A หรือ B 👇",                             "A หรือ B วะ 👇"),
    ("Comment 👇 แล้วอธิบายด้วยว่าทำไม",               "แล้วเธอล่ะ 👇 บอกด้วยว่าทำไม"),
    ("Comment ชื่อขนมที่คิดถึงที่สุด 👇",              "ขนมที่คิดถึงที่สุดคืออะไร 🥹👇"),
    ("Comment คำตอบของคุณ 👇",                         "เดาซิ 👇"),
    ("Comment บอกว่าสนใจ",                             "สนใจบอกมาเลย"),
    ("Comment: ซื้อ / ไม่ซื้อ",                        "ซื้อหรือไม่ซื้อ 👇"),
    ("แสดงความคิดเห็น 👇",                             "บอกมาเลย 👇"),
    # AI philosophical filler
    ("บางทีสิ่งที่ดูแปลก อาจเป็นของที่ดีที่สุดก็ได้",    "คนที่ซื้อรู้อะไรที่กูไม่รู้แน่ๆ 💀"),
    ("ไม่มีคำตอบถูกหรือผิด — แค่อยากรู้ว่าคุณคิดยังไง",  "แค่อยากรู้ว่าใครเป็นแบบเดียวกันบ้าง 😂"),
    ("ไม่มีคำตอบถูกหรือผิด",                             "ไม่มีถูกผิดนะ"),
    ("ทุกคนมีมุมมองที่แตกต่างกัน",                       "ใครเหมือนกันบ้างวะ 😂"),
    ("ขึ้นอยู่กับแต่ละคน",                               "ของใครของมันนะ"),
    # Formal connectors → spoken
    ("อย่างไรก็ตาม",    "แต่"),
    ("เพราะฉะนั้น",     "เลย"),
    ("ดังนั้น",         "งั้น"),
    ("ทั้งนี้",         ""),
    ("ซึ่ง",            "ที่"),
    ("ดังกล่าว",        "นี้"),
    ("กล่าวคือ",        "คือ"),
    ("เนื่องจาก",       "เพราะ"),
    ("สำหรับ",          "สำหรับ"),  # keep but track
    # Formal Thai → spoken Thai
    ("หรือไม่?",        "รึเปล่า"),   # formal question only — NOT inside ซื้อหรือไม่ซื้อ
    ("หรือไม่ ",        "รึเปล่า "),  # followed by space
    ("อย่างไร",         "ยังไง"),
    ("ของคุณคือ",       "ของเธอคือ"),
    ("คุณคิดว่า",       "คิดว่า"),
    ("ที่คุณ",          "ที่เธอ"),
    ("คุณตื่นกี่โมง?",  "เธอตื่นกี่โมงวะ 👇"),
    ("คุณเลือกอะไร?",   "เธอเลือกทีมไหนวะ 👇"),
    ("คุณจะซื้อไหม? 🤔","ซื้อหรือไม่ซื้อ 👇"),
    ("คุณจะซื้อไหม?",   "ซื้อหรือไม่ซื้อ 👇"),
    ("ของท่าน",         "ของเธอ"),
    # Question softening
    ("บ้างไหม?",        "บ้างมั้ย 👇"),
    ("บ้างไหม",         "บ้างมั้ย"),
    ("กันบ้าง?",        "กันบ้าง 👇"),
    ("ไหม?",            "มั้ย 👇"),
    ("ใช่ไหม?",         "จริงมั้ย 😂"),
    ("เพื่อน ๆ",        "เพื่อนๆ"),
    # Remove over-formal address
    ("ท่านผู้อ่าน",     "เธอ"),
    ("ผู้อ่านทุกท่าน",  "ทุกคน"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Poll detection signals
# ─────────────────────────────────────────────────────────────────────────────

POLL_SIGNALS: list[str] = [
    "A:", "B:", "A :", "B :",
    "ทีม A", "ทีม B",
    "A หรือ B", "B หรือ A",
    "ทีม 1", "ทีม 2",
    "แบบ A", "แบบ B",
]


# ─────────────────────────────────────────────────────────────────────────────
# Hook injection prevention signals
# (don't add hook if text already contains one of these)
# ─────────────────────────────────────────────────────────────────────────────

HOOK_SIGNALS: list[str] = [
    "แค่กูรึเปล่า",
    "บ้านกูก็",
    "กูคนเดียว",
    "กูยังงง",
    "คิดถึงจุง",
    "โห นึก",
    "กูไม่รู้",
    "ซื้อรู้อะไร",
    "คนที่ซื้อรู้",
    "กูก็เพิ่งรู้",
    "ทำไมมันตรง",
    "โดนใจจุง",
    "555 จริงมาก",
]


# ─────────────────────────────────────────────────────────────────────────────
# CTA Pattern banks (Pass 3) — keyed by post_type or post_type_poll
# ─────────────────────────────────────────────────────────────────────────────

_CTA_BANKS: dict[str, list[Pattern]] = {
    "comment_bait_poll": [
        Pattern("cta_cbp_01", "A หรือ B วะ 👇", 1.2),
        Pattern("cta_cbp_02", "เธออยู่ทีมไหน 👇", 1.0),
        Pattern("cta_cbp_03", "ทีมไหนก็บอกมาเลย 👇", 1.0),
        Pattern("cta_cbp_04", "A หรือ B? บอกด้วย 👇", 0.9),
        Pattern("cta_cbp_05", "เลือกข้างแล้วบอกเลย 👇", 0.8),
    ],
    "comment_bait_general": [
        Pattern("cta_cbg_01", "บ้านใครเป็นบ้าง 😂", 1.3),
        Pattern("cta_cbg_02", "ใครเหมือนกันบ้างวะ 👇", 1.2),
        Pattern("cta_cbg_03", "แค่กูรึเปล่า 😅", 1.2),
        Pattern("cta_cbg_04", "มีใครเหมือนกันบ้าง 👇", 1.0),
        Pattern("cta_cbg_05", "กูคนเดียวรึเปล่าที่เป็นแบบนี้ 😂", 1.0),
        Pattern("cta_cbg_06", "เธอล่ะเป็นแบบนี้บ้างมั้ย 👇", 0.9),
        Pattern("cta_cbg_07", "บอกมาเลยว่าเธอเป็นทีมไหน 👇", 0.8),
    ],
    "weird_product": [
        Pattern("cta_wp_01", "ซื้อหรือไม่ซื้อ 👇", 1.3),
        Pattern("cta_wp_02", "คิดว่ายังไงกัน 😂", 1.1),
        Pattern("cta_wp_03", "ใครซื้ออยู่บ้าง 👇", 1.0),
        Pattern("cta_wp_04", "โลกนี้ไปไกลมากจริงๆ 💀", 1.2),
        Pattern("cta_wp_05", "อัจฉริยะหรือบ้า ตัดสินเอาเอง 😂", 1.0),
        Pattern("cta_wp_06", "ใครคิดจะซื้อบ้าง 🤔", 0.9),
    ],
    "nostalgia": [
        Pattern("cta_nos_01", "ยังจำได้บ้างไหม 🥹", 1.3),
        Pattern("cta_nos_02", "ใครยังมีอยู่บ้าง 🥹", 1.0),
        Pattern("cta_nos_03", "คิดถึงมั้ย 🥹", 1.2),
        Pattern("cta_nos_04", "เด็กสมัยนี้ไม่เข้าใจหรอก 😅", 1.1),
        Pattern("cta_nos_05", "ใครโตมากับสิ่งนี้บ้าง 🥹", 0.9),
        Pattern("cta_nos_06", "เธอเคยใช้บ้างมั้ย 🥹", 0.8),
    ],
    "visual_curiosity": [
        Pattern("cta_vc_01", "เธอเห็นอะไรก่อนวะ 👇", 1.3),
        Pattern("cta_vc_02", "ใช้เวลานานแค่ไหน 👇", 1.0),
        Pattern("cta_vc_03", "เดาซิ 👇", 1.2),
        Pattern("cta_vc_04", "บอกว่าเห็นอะไร 👇", 0.9),
    ],
    "trending": [
        Pattern("cta_tr_01", "คิดว่ายังไงกัน 👇", 1.2),
        Pattern("cta_tr_02", "เธอเห็นด้วยมั้ย 👇", 1.0),
        Pattern("cta_tr_03", "ตามทันกันหรือยัง 👇", 1.0),
        Pattern("cta_tr_04", "กระแสนี้เธอว่ายังไง 👇", 0.9),
    ],
    "affiliate": [
        Pattern("cta_aff_01", "สนใจบอกมาเลย 👇", 1.2),
        Pattern("cta_aff_02", "คุ้มไหม ลองดูได้เลย", 1.0),
        Pattern("cta_aff_03", "ใครซื้อแล้วรีวิวด้วยนะ 👇", 1.1),
        Pattern("cta_aff_04", "ลิ้งค์อยู่ใน bio นะ", 0.8),
    ],
}

# Bad CTA endings that should be replaced
BAD_CTA_ENDINGS: list[str] = [
    "บอกความคิดเห็น 👇",
    "แสดงความคิดเห็น 👇",
    "อยากรู้จักของชิ้นนี้ไหม? 👇",
    "อยากรู้ว่าใช้ทำอะไร? Comment ถามมาเลย 👇",
    "Share ให้คนที่โตมายุคเดียวกันเห็น",
    "แชร์ให้เพื่อนด้วยนะ",
    "กดแชร์ให้เพื่อนดูด้วย",
    "อย่าลืม Like กด Share นะคะ",
    "ฝากกด Like กด Share ด้วยนะครับ",
]


# ─────────────────────────────────────────────────────────────────────────────
# Hook Pattern banks (Pass 4) — injected before closing CTA
# ─────────────────────────────────────────────────────────────────────────────

_HOOK_BANKS: dict[str, list[Pattern]] = {
    "comment_bait": [
        Pattern("h_cb_01", "แค่กูรึเปล่าที่รู้สึกแบบนี้ 😅", 1.3),
        Pattern("h_cb_02", "กูคนเดียวรึเปล่า 😂", 1.2),
        Pattern("h_cb_03", "บ้านกูก็เป็นแบบนี้เลย", 1.3),
        Pattern("h_cb_04", "555 จริงมากๆ", 1.0),
        Pattern("h_cb_05", "โอ๊ย โดนใจจุงๆ เลย 😭", 1.1),
        Pattern("h_cb_06", "ทำไมมันตรงใจมากขนาดนี้ 😅", 1.1),
        Pattern("h_cb_07", "กูเป็นแบบนี้ทุกวันเลยนะ 😭", 1.0),
        Pattern("h_cb_08", "เพื่อนกูคนนึงเป็นแบบนี้ตลอด 😂", 0.9),
    ],
    "weird_product": [
        Pattern("h_wp_01", "กูยังงงอยู่ว่ามีคนซื้อทำไม 💀", 1.3),
        Pattern("h_wp_02", "โลกนี้ไปไกลมากจริงๆ", 1.2),
        Pattern("h_wp_03", "คนที่ซื้อเก่งมากเลยนะ กูคิดไม่ถึง", 1.1),
        Pattern("h_wp_04", "555 อัจฉริยะหรือบ้า กูก็ไม่รู้", 1.0),
        Pattern("h_wp_05", "นี่คืออนาคตเหรอ 💀", 1.0),
        Pattern("h_wp_06", "คนคิดสิ่งนี้ขึ้นมาได้ยังไงวะ", 0.9),
    ],
    "nostalgia": [
        Pattern("h_nos_01", "คิดถึงจุงๆ เลย 🥹", 1.3),
        Pattern("h_nos_02", "โห นึกถึงแล้วใจหาย", 1.2),
        Pattern("h_nos_03", "สมัยนั้นมันดีกว่านี้จริงๆ", 1.1),
        Pattern("h_nos_04", "เวลามันผ่านเร็วมากนะ 😢", 1.1),
        Pattern("h_nos_05", "ถ้าย้อนเวลากลับไปได้ 🥹", 1.0),
        Pattern("h_nos_06", "ชีวิตมันง่ายกว่านี้มากเลยสมัยนั้น", 0.9),
    ],
    "visual_curiosity": [
        Pattern("h_vc_01", "กูนั่งดูนานมาก 😂", 1.3),
        Pattern("h_vc_02", "สายตากูมันไม่ดีหรือเปล่านะ", 1.0),
        Pattern("h_vc_03", "ลองนานมากกว่าจะเห็น 😂", 1.1),
        Pattern("h_vc_04", "คนอื่นเห็นอะไรบ้างวะ", 0.9),
    ],
    "trending": [
        Pattern("h_tr_01", "กระแสนี้มาแรงมากจริงๆ", 1.2),
        Pattern("h_tr_02", "ทุกคนพูดถึงกันหมดเลย", 1.0),
        Pattern("h_tr_03", "เพิ่งรู้ตอนนี้เองมั้ยกูนะ 😂", 1.1),
    ],
    "affiliate": [
        Pattern("h_aff_01", "กูก็เพิ่งรู้ว่ามีของแบบนี้", 1.2),
        Pattern("h_aff_02", "ราคานี้คุ้มมากถ้าใช้บ่อย", 1.1),
        Pattern("h_aff_03", "ใช้มาสักพักแล้ว ดีจริงๆ", 1.0),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def _weighted_choice(patterns: list[Pattern], rng: random.Random) -> Pattern:
    """Pick one pattern using weights."""
    if not patterns:
        raise ValueError("empty pattern list")
    total = sum(p.weight for p in patterns)
    r = rng.uniform(0, total)
    cumulative = 0.0
    for pattern in patterns:
        cumulative += pattern.weight
        if r <= cumulative:
            return pattern
    return patterns[-1]


def get_cta(post_type: str, is_poll: bool, rng: random.Random,
            weight_overrides: dict[str, float] | None = None) -> str:
    """Return a CTA text string for the given post type."""
    key = f"{post_type}_poll" if is_poll else f"{post_type}_general"
    bank = _CTA_BANKS.get(key) or _CTA_BANKS.get(post_type) or _CTA_BANKS["comment_bait_general"]

    if weight_overrides:
        bank = [Pattern(p.id, p.text, weight_overrides.get(p.id, p.weight)) for p in bank]

    return _weighted_choice(bank, rng).text


def get_hook(post_type: str, rng: random.Random,
             weight_overrides: dict[str, float] | None = None) -> str:
    """Return a hook text string for the given post type."""
    bank = _HOOK_BANKS.get(post_type, _HOOK_BANKS["comment_bait"])

    if weight_overrides:
        bank = [Pattern(p.id, p.text, weight_overrides.get(p.id, p.weight)) for p in bank]

    return _weighted_choice(bank, rng).text


def get_pattern_weight(pattern_id: str) -> float:
    """Return the default weight for a pattern ID."""
    for bank in list(_CTA_BANKS.values()) + list(_HOOK_BANKS.values()):
        for p in bank:
            if p.id == pattern_id:
                return p.weight
    return 1.0


def list_all_patterns() -> list[Pattern]:
    """Return all patterns across all banks (for seeding the learning loop DB)."""
    result: list[Pattern] = []
    for bank in list(_CTA_BANKS.values()) + list(_HOOK_BANKS.values()):
        result.extend(bank)
    return result
