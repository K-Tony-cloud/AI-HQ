"""
Thai Content Intelligence — Comment Intelligence.

Patterns that make content feel like it was written BY Thai people,
designed to attract the comments that Thai people naturally leave.

Inspired by the linguistic patterns in viral Thai Facebook posts.
Goal: Comments like "บ้านกูก็เป็น" / "กูคนหนึ่ง" / "เออว่ะ จริง"
"""

from __future__ import annotations

import random
from typing import NamedTuple


class CommentPattern(NamedTuple):
    id: str
    text: str
    trigger: str    # what kind of comment this attracts
    weight: float = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Opening hooks — the first 1-2 lines that stop the scroll
# Ordered by effectiveness for อะไรของมัน voice
# ─────────────────────────────────────────────────────────────────────────────

ENGAGEMENT_OPENERS: dict[str, list[CommentPattern]] = {
    "comment_bait": [
        CommentPattern("eo_cb_01", "บ้านกูก็มีแบบนี้เลยนะ 😂", "relatable_me_too", 1.3),
        CommentPattern("eo_cb_02", "นี่คือทุกบ้านในไทยมั้ย 😂", "community_poll", 1.2),
        CommentPattern("eo_cb_03", "กูว่าคนไทยทุกคนเคยเจอ", "relatable_universal", 1.2),
        CommentPattern("eo_cb_04", "เพื่อนกูส่งมาให้ดู เลยรู้ว่ากูเป็นแบบนี้ 😂", "story_intro", 1.0),
        CommentPattern("eo_cb_05", "ใครเป็นแบบนี้บ้างวะ 👋", "community_call", 1.1),
        CommentPattern("eo_cb_06", "เมื่อกี้เพิ่งเป็นเรื่องนี้กับตัวเองเลย 😭", "timely_relatable", 1.2),
    ],
    "weird_product": [
        CommentPattern("eo_wp_01", "นี่มีขายจริงๆ เหรอ 💀", "surprise_confirm", 1.3),
        CommentPattern("eo_wp_02", "ใครเป็นคนคิดขึ้นมาได้ยังไงวะ", "curiosity", 1.2),
        CommentPattern("eo_wp_03", "กูงงมากว่ามีคนซื้อทำไม 😂", "confusion_humor", 1.3),
        CommentPattern("eo_wp_04", "โลก 2026 มันเป็นแบบนี้แล้ว 💀", "zeitgeist", 1.0),
        CommentPattern("eo_wp_05", "ราคาเท่าไหรคาดว่า...", "price_curiosity", 1.1),
    ],
    "nostalgia": [
        CommentPattern("eo_nos_01", "คนโตมายุค 90s จะเข้าใจ 🥹", "generational", 1.3),
        CommentPattern("eo_nos_02", "มีใครยังจำสิ่งนี้ได้บ้างมั้ย 🥹", "memory_check", 1.2),
        CommentPattern("eo_nos_03", "ความทรงจำวัยเด็ก 😭", "memory_trigger", 1.2),
        CommentPattern("eo_nos_04", "ยุคนี้เด็กๆ ไม่รู้จักแล้วนะ", "generational_gap", 1.1),
        CommentPattern("eo_nos_05", "กูเพิ่งนึกถึงเรื่องนี้เมื่อกี้เลย 🥹", "synchronous", 1.0),
    ],
    "visual_curiosity": [
        CommentPattern("eo_vc_01", "มองนานแค่ไหนกว่าจะเห็น 👀", "challenge", 1.3),
        CommentPattern("eo_vc_02", "สายตาเธอเห็นอะไรก่อน 👀", "direct_challenge", 1.2),
        CommentPattern("eo_vc_03", "ภาพนี้มันลวงตาหรือตาเราแย่ 😂", "self_doubt_humor", 1.1),
    ],
    "trending": [
        CommentPattern("eo_tr_01", "เรื่องนี้ทุกคนพูดถึงกันแล้ว", "social_proof", 1.2),
        CommentPattern("eo_tr_02", "กระแสนี้มาไวมากจริงๆ", "trend_confirm", 1.0),
        CommentPattern("eo_tr_03", "เธอตามทันเรื่องนี้รึยัง", "fomo", 1.1),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Community language — in-group phrases that make followers feel like "us"
# ─────────────────────────────────────────────────────────────────────────────

COMMUNITY_PHRASES: dict[str, list[str]] = {
    "vs_poll": [
        "กรุงฯ vs ต่างจังหวัด",
        "ทีมตื่นเช้า vs ทีมนอนดึก",
        "ทีมออมเงิน vs ทีมใช้หมดก่อนสิ้นเดือน",
        "ทีมล้างจานทันที vs ทีมแช่น้ำไว้ก่อน",
        "ทีมทำงานที่ออฟฟิศ vs ทีม WFH",
        "ทีมกินข้าวบ้าน vs ทีมสั่ง Grab",
        "ทีมดูหนังครบเรื่อง vs ทีมดูแค่ตอนจบ",
    ],
    "shared_experience": [
        "คนที่เคยทำแบบนี้รู้ดี",
        "ใครเจอเหมือนกันบ้าง",
        "คนที่เป็นแบบนี้ยกมือขึ้น",
        "นี่คือสัญลักษณ์ของคนที่...",
        "ใครเหมือนกันบ้างรู้กัน",
    ],
    "thai_universal": [
        "คนไทยทุกคนรู้จัก",
        "เกิดมาเป็นคนไทยต้องเคยเจอ",
        "คนไทยเข้าใจ",
        "ทุกบ้านในไทย",
        "เรื่องของคนไทย",
    ],
    "generational": [
        "เด็กยุค 90 จะรู้ว่า",
        "คนที่โตมายุค 2000 เท่านั้นที่รู้",
        "เด็กสมัยนี้ไม่รู้จักแล้ว",
        "ยุคก่อนมันเป็นแบบนี้",
        "คนรุ่นกูจะจำได้",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Humor patterns — joke structures that work in Thai Facebook context
# ─────────────────────────────────────────────────────────────────────────────

HUMOR_PATTERNS: dict[str, list[str]] = {
    "self_deprecating": [
        "กูก็ทำแบบนี้อยู่นะ 💀",
        "นี่คือกูทุกวัน 😭",
        "กูทำเรื่องนี้มา 5 ปีแล้วยังไม่รู้ 💀",
        "กูคือคนที่โพสต์นี้พูดถึง 555",
    ],
    "observation": [
        "สังเกตว่าคนที่... มักจะ...",
        "ทำไม...ถึงต้องเป็นแบบนี้เสมอ",
        "มีใครเคยคิดเรื่องนี้บ้างมั้ย",
        "เรื่องแบบนี้มันเกิดขึ้นได้ยังไง",
    ],
    "comparison": [
        "สมัยก่อน... แต่ตอนนี้...",
        "ถ้าเป็นกู vs ถ้าเป็นเธอ",
        "ก่อน vs หลัง",
        "ตอนเช้า vs ตอนเย็น",
    ],
    "understatement": [
        "ปกติมากเลยนะ 🙃",
        "ไม่มีอะไรน่าแปลกใจเลย",
        "เรื่องธรรมดาสุดๆ เลย 💀",
        "ก็โอเคนะ... (ไม่โอเคเลย)",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Engagement magnifiers — phrases placed near CTAs to boost comment rate
# ─────────────────────────────────────────────────────────────────────────────

ENGAGEMENT_MAGNIFIERS: dict[str, list[str]] = {
    "low_friction": [
        "แค่ comment สั้นๆ ก็ได้",
        "แค่คำเดียวก็ได้ 👇",
        "ตอบแค่ A หรือ B ก็พอ",
        "พิมพ์สั้นๆ ก็ได้ 👇",
    ],
    "social_proof": [
        "คนอื่นๆ ก็ comment กันเยอะแล้ว",
        "ดูว่าใครคิดเหมือนกันบ้าง 👇",
        "มาดูกันว่าทีมไหนมีคนมากกว่า 👇",
    ],
    "urgency": [
        "บอกมาเลยก่อนที่จะลืม",
        "คิดออกแล้วบอกเลย 👇",
    ],
    "permission": [
        "ไม่ตัดสินนะ 👇",
        "ไม่มีถูกผิด",
        "ตอบตรงๆ ได้เลย 👇",
        "บอกตามจริงเลย 👇",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_engagement_opener(post_type: str, rng: random.Random | None = None) -> str | None:
    """Return a scroll-stopping opener for the given post type."""
    r = rng or random.Random()
    bank = ENGAGEMENT_OPENERS.get(post_type, ENGAGEMENT_OPENERS.get("comment_bait", []))
    if not bank:
        return None
    total = sum(p.weight for p in bank)
    rand = r.uniform(0, total)
    cumulative = 0.0
    for pattern in bank:
        cumulative += pattern.weight
        if rand <= cumulative:
            return pattern.text
    return bank[-1].text


def get_community_phrase(phrase_type: str = "shared_experience",
                         rng: random.Random | None = None) -> str | None:
    """Return a community bonding phrase."""
    r = rng or random.Random()
    bank = COMMUNITY_PHRASES.get(phrase_type, [])
    if not bank:
        return None
    return r.choice(bank)


def get_vs_poll(rng: random.Random | None = None) -> str:
    """Return a random A vs B poll topic."""
    r = rng or random.Random()
    return r.choice(COMMUNITY_PHRASES["vs_poll"])


def get_humor_hook(humor_type: str = "self_deprecating",
                   rng: random.Random | None = None) -> str | None:
    """Return a humor pattern phrase."""
    r = rng or random.Random()
    bank = HUMOR_PATTERNS.get(humor_type, [])
    if not bank:
        return None
    return r.choice(bank)


def get_engagement_magnifier(magnifier_type: str = "low_friction",
                              rng: random.Random | None = None) -> str | None:
    """Return an engagement magnifier phrase."""
    r = rng or random.Random()
    bank = ENGAGEMENT_MAGNIFIERS.get(magnifier_type, [])
    if not bank:
        return None
    return r.choice(bank)
