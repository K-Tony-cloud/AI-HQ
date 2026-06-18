"""
Humanize Engine — rule-based Thai Facebook caption transformer.

Pipeline (4 passes):
  1. Strip AI openers
  2. Substitution table (formal → casual)
  3. Type-aware CTA replacement
  4. Relatable hook injection

Voice: คนไทยเมาท์กัน / คอมเมนต์ใต้โพสต์ไวรัล
Target: "เออว่ะ" / "จริง" / "บ้านกูก็เป็น" / "กูคนหนึ่ง"

No API needed. Seeded random for per-date variety.
"""

from __future__ import annotations

import logging
import os
import random

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"


# ─────────────────────────────────────────────────────────────────────────────
# Pass 1 — AI opener patterns to strip from the first block
# (longest-first so "คำถามที่อยากรู้มานาน 🤔\n\n" is matched before shorter variants)
# ─────────────────────────────────────────────────────────────────────────────

_AI_OPENERS: list[str] = [
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
]


# ─────────────────────────────────────────────────────────────────────────────
# Pass 2 — Substitution table (ordered longest-first)
# ─────────────────────────────────────────────────────────────────────────────

_SUBS: list[tuple[str, str]] = [
    # AI CTA patterns → casual
    ("Comment บอกได้เลยว่าคุณเป็นทีมไหน 👇",    "เธออยู่ทีมไหนวะ 👇"),
    ("Comment บอกได้เลยว่าคุณ",                   "บอกมาเลยว่าเธอ"),
    ("Comment บอกได้เลย — ไม่มีคำตอบถูกหรือผิด 👇", "บอกมาเลยนะ 👇"),
    ("Comment บอกได้เลย ไม่ตัดสิน 👇",           "บอกมาเลย ไม่ตัดสินนะ 👇"),
    ("Comment บอกได้เลย 👇",                      "บอกมาเลย 👇"),
    ("Comment บอกได้เลย",                         "บอกมาเลยนะ"),
    ("Comment A หรือ B 👇",                        "A หรือ B วะ 👇"),
    ("Comment 👇 แล้วอธิบายด้วยว่าทำไม",          "แล้วเธอล่ะ 👇 บอกด้วยว่าทำไม"),
    ("Comment ชื่อขนมที่คิดถึงที่สุด 👇",         "ขนมที่คิดถึงที่สุดคืออะไร 🥹👇"),
    ("Comment คำตอบของคุณ 👇",                    "เดาซิ 👇"),
    ("Comment บอกว่าสนใจ",                        "สนใจบอกมาเลย"),
    ("Comment: ซื้อ / ไม่ซื้อ",                   "ซื้อหรือไม่ซื้อ 👇"),
    ("แสดงความคิดเห็น 👇",                        "บอกมาเลย 👇"),
    # AI philosophical phrases
    ("บางทีสิ่งที่ดูแปลก อาจเป็นของที่ดีที่สุดก็ได้",   "คนที่ซื้อรู้อะไรที่กูไม่รู้แน่ๆ 💀"),
    ("ไม่มีคำตอบถูกหรือผิด — แค่อยากรู้ว่าคุณคิดยังไง", "แค่อยากรู้ว่าใครเป็นแบบเดียวกันบ้าง 😂"),
    ("ไม่มีคำตอบถูกหรือผิด",                            "ไม่มีถูกผิดนะ"),
    # Formal connectors
    ("อย่างไรก็ตาม",   "แต่"),
    ("เพราะฉะนั้น",    "เลย"),
    ("ดังนั้น",        "งั้น"),
    ("ทั้งนี้",        ""),
    ("ซึ่ง",           "ที่"),
    ("ดังกล่าว",       "นี้"),
    # Formal Thai → Spoken Thai
    ("หรือไม่",        "รึเปล่า"),
    ("อย่างไร",        "ยังไง"),
    ("ของคุณคือ",      "ของเธอคือ"),
    ("คุณคิดว่า",      "คิดว่า"),
    ("ที่คุณ",         "ที่เธอ"),
    ("คุณตื่นกี่โมง?", "เธอตื่นกี่โมงวะ 👇"),
    ("คุณเลือกอะไร?",  "เธอเลือกทีมไหนวะ 👇"),
    ("คุณจะซื้อไหม? 🤔", "ซื้อหรือไม่ซื้อ 👇"),
    ("คุณจะซื้อไหม?",  "ซื้อหรือไม่ซื้อ 👇"),
    # Question softening
    ("บ้างไหม?",       "บ้างมั้ย 👇"),
    ("บ้างไหม",        "บ้างมั้ย"),
    ("กันบ้าง?",       "กันบ้าง 👇"),
    ("ไหม?",           "มั้ย 👇"),
    ("ใช่ไหม?",        "จริงมั้ย 😂"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Pass 3 — Type-aware CTA banks
# Keys: post_type + "_poll" for A/B posts, post_type + "_general" otherwise
# ─────────────────────────────────────────────────────────────────────────────

_CTAS: dict[str, list[str]] = {
    "comment_bait_poll": [
        "A หรือ B วะ 👇",
        "เธออยู่ทีมไหน 👇",
        "ทีมไหนก็บอกมาเลย 👇",
        "A หรือ B? บอกด้วย 👇",
    ],
    "comment_bait_general": [
        "บ้านใครเป็นบ้าง 😂",
        "ใครเหมือนกันบ้างวะ 👇",
        "แค่กูรึเปล่า 😅",
        "มีใครเหมือนกันบ้าง 👇",
        "กูคนเดียวรึเปล่าที่เป็นแบบนี้ 😂",
    ],
    "weird_product": [
        "ซื้อหรือไม่ซื้อ 👇",
        "คิดว่ายังไงกัน 😂",
        "ใครซื้ออยู่บ้าง 👇",
        "โลกนี้ไปไกลมากจริงๆ 💀",
    ],
    "nostalgia": [
        "ยังจำได้บ้างไหม 🥹",
        "ใครยังมีอยู่บ้าง 🥹",
        "คิดถึงมั้ย 🥹",
        "เด็กสมัยนี้ไม่เข้าใจหรอก 😅",
    ],
    "visual_curiosity": [
        "เธอเห็นอะไรก่อนวะ 👇",
        "ใช้เวลานานแค่ไหน 👇",
        "เดาซิ 👇",
    ],
    "trending": [
        "คิดว่ายังไงกัน 👇",
        "เธอเห็นด้วยมั้ย 👇",
        "ตามทันกันหรือยัง 👇",
    ],
    "affiliate": [
        "สนใจบอกมาเลย 👇",
        "คุ้มไหม ลองดูได้เลย",
        "ใครซื้อแล้วรีวิวด้วยนะ 👇",
    ],
}

# Detect if post has A/B poll format
_POLL_SIGNALS = ["A:", "B:", "A :", "B :", "ทีม A", "ทีม B", "A หรือ B", "B หรือ A"]


# ─────────────────────────────────────────────────────────────────────────────
# Pass 4 — Relatable hook injection
# Injected between the content body and the closing CTA
# ─────────────────────────────────────────────────────────────────────────────

_HOOKS: dict[str, list[str]] = {
    "comment_bait": [
        "แค่กูรึเปล่าที่รู้สึกแบบนี้ 😅",
        "กูคนเดียวรึเปล่า 😂",
        "บ้านกูก็เป็นแบบนี้เลย",
        "555 จริงมากๆ",
        "โอ๊ย โดนใจจุงๆ เลย 😭",
        "ทำไมมันตรงใจมากขนาดนี้ 😅",
    ],
    "weird_product": [
        "กูยังงงอยู่ว่ามีคนซื้อทำไม 💀",
        "โลกนี้ไปไกลมากจริงๆ",
        "คนที่ซื้อเก่งมากเลยนะ กูคิดไม่ถึง",
        "555 อัจฉริยะหรือบ้า กูก็ไม่รู้",
    ],
    "nostalgia": [
        "คิดถึงจุงๆ เลย 🥹",
        "โห นึกถึงแล้วใจหาย",
        "สมัยนั้นมันดีกว่านี้จริงๆ",
        "เวลามันผ่านเร็วมากนะ 😢",
    ],
    "visual_curiosity": [
        "กูนั่งดูนานมาก 😂",
        "สายตากูมันไม่ดีหรือเปล่านะ",
    ],
    "trending": [
        "กระแสนี้มาแรงมากจริงๆ",
        "ทุกคนพูดถึงกันหมดเลย",
    ],
    "affiliate": [
        "กูก็เพิ่งรู้ว่ามีของแบบนี้",
        "ราคานี้คุ้มมากถ้าใช้บ่อย",
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline passes
# ─────────────────────────────────────────────────────────────────────────────

def _pass1_strip_opener(text: str) -> str:
    """Remove known AI opener patterns from the start of the text."""
    for opener in _AI_OPENERS:
        if text.startswith(opener):
            text = text[len(opener):]
            break
    return text


def _pass2_substitutions(text: str) -> str:
    """Apply formal→casual substitution table."""
    for old, new in _SUBS:
        text = text.replace(old, new)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def _is_poll(text: str) -> bool:
    return any(sig in text for sig in _POLL_SIGNALS)


def _pass3_cta(text: str, post_type: str, rng: random.Random) -> str:
    """
    Replace the last non-empty line if it looks like a generic CTA,
    using a type-appropriate casual alternative.
    """
    lines = text.rstrip().split("\n")
    if not lines:
        return text

    last = lines[-1].strip()

    # Already a good short CTA — leave it alone
    if len(last) <= 15 and ("👇" in last or "?" in last or "มั้ย" in last or "วะ" in last):
        return text

    # Detect generic AI CTA patterns
    _bad_endings = [
        "บอกความคิดเห็น 👇",
        "แสดงความคิดเห็น 👇",
        "อยากรู้จักของชิ้นนี้ไหม? 👇",
        "อยากรู้ว่าใช้ทำอะไร? Comment ถามมาเลย 👇",
        "Share ให้คนที่โตมายุคเดียวกันเห็น",
    ]
    is_bad = any(last.endswith(b.rstrip()) or last == b.strip() for b in _bad_endings)

    if not is_bad:
        return text

    # Pick CTA by type
    key = f"{post_type}_poll" if _is_poll(text) else f"{post_type}_general"
    bank = _CTAS.get(key) or _CTAS.get(post_type) or _CTAS["comment_bait_general"]
    lines[-1] = rng.choice(bank)
    return "\n".join(lines)


def _pass4_hook(text: str, post_type: str, rng: random.Random) -> str:
    """
    Inject a relatable hook before the last line (CTA) if the post
    doesn't already have one and is longer than 3 lines.
    """
    # Don't inject if one already exists
    _HOOK_SIGNALS = ["แค่กูรึเปล่า", "บ้านกูก็", "กูคนเดียว", "กูยังงง", "คิดถึงจุง", "โห นึก", "กูไม่รู้", "ซื้อรู้อะไร"]
    if any(sig in text for sig in _HOOK_SIGNALS):
        return text

    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) < 4:
        return text

    bank = _HOOKS.get(post_type, _HOOKS["comment_bait"])
    hook = rng.choice(bank)

    # Insert hook as a new paragraph before the last line
    all_lines = text.split("\n")
    # Find the index of the last non-empty line
    last_idx = len(all_lines) - 1
    while last_idx > 0 and not all_lines[last_idx].strip():
        last_idx -= 1

    all_lines.insert(last_idx, "")
    all_lines.insert(last_idx, hook)
    return "\n".join(all_lines)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def _rule_based(text: str, post_type: str = "comment_bait", seed: int = 0) -> str:
    """4-pass rule-based humanizer. Deterministic given same text + seed."""
    rng  = random.Random(seed)
    text = _pass1_strip_opener(text)
    text = _pass2_substitutions(text)
    text = _pass3_cta(text, post_type, rng)
    text = _pass4_hook(text, post_type, rng)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()


# ── AI path (used when ANTHROPIC_API_KEY is a real key) ──────────────────────

_SYSTEM = """\
คุณเป็น editor ของเพจ Facebook "อะไรของมัน" เพจไทยที่พูดเรื่องชีวิตประจำวัน

งาน: รับ draft post แล้วเขียนใหม่ให้ฟังดูเหมือนคนไทยคุยกับเพื่อน — ไม่ใช่ content creator ไม่ใช่ AI ไม่ใช่บทความ

VOICE: casual, slightly sarcastic, funny, relatable. เหมือนคนเมาท์กันเอง เหมือนคอมเมนต์ใต้โพสต์ไวรัล

RULES:
1. ประโยคสั้น — หนึ่งความคิดต่อหนึ่งบรรทัด ไม่มีย่อหน้ายาว
2. เปิดหัวแบบคนพูด — ห้ามขึ้นต้นด้วย "คุณเคย..." / "ในยุค..." / "น่าสนใจมาก..." / "คำถามที่..."
3. comment bait ต้องรู้สึก genuine — ห้ามใช้ "Comment บอกได้เลย 👇"
4. ห้ามใช้: ดังนั้น / เพราะฉะนั้น / อย่างไรก็ตาม / ที่น่าสนใจคือ / ไม่มีคำตอบถูกหรือผิด
5. แทน "หรือไม่" ด้วย "รึเปล่า", แทน "อย่างไร" ด้วย "ยังไง"
6. เก็บ emoji ทุกตัว เก็บ structure A/B ถ้ามี
7. สั้นลง 20-30% จาก draft เดิม
8. เพิ่ม relatable hook: "แค่กูรึเปล่า 😅" / "บ้านกูก็เป็น" / "กูคนหนึ่งนะ"

TARGET: อ่านแล้วรู้สึก "เออว่ะ จริง" ไม่ใช่ "interesting content"

Return ONLY the final caption. No explanation.\
"""

_TYPE_HINTS: dict[str, str] = {
    "comment_bait":     "ประเภท: comment bait — ถามความเห็น ให้คนอยากตอบ",
    "weird_product":    "ประเภท: weird product — ของแปลก ตลก น่าตกใจ",
    "nostalgia":        "ประเภท: nostalgia — ความทรงจำ คนเดิน 80s-90s",
    "visual_curiosity": "ประเภท: visual curiosity — ดึงดูดให้มองนาน แล้ว comment",
    "trending":         "ประเภท: trending — กระแสที่คนพูดถึงอยู่",
    "affiliate":        "ประเภท: affiliate — แนะนำสินค้า แบบเป็นกันเอง ไม่ขาย",
}


def _ai_humanize(text: str, post_type: str) -> str:
    import anthropic
    client  = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    hint    = _TYPE_HINTS.get(post_type, "")
    content = f"{hint}\n\n---\n{text}" if hint else text
    msg     = client.messages.create(
        model=_MODEL,
        max_tokens=600,
        system=_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    result = msg.content[0].text.strip()
    if len(result) < 20:
        logger.warning("[humanize] AI returned too-short result, using rule-based")
        seed = abs(hash(text)) % (2 ** 31)
        return _rule_based(text, post_type, seed)
    return result


def humanize_caption(text: str, post_type: str = "comment_bait") -> str:
    """
    Apply humanize layer. Claude Haiku if real ANTHROPIC_API_KEY, else 4-pass rule-based.
    """
    if not text or not text.strip():
        return text

    seed = abs(hash(text)) % (2 ** 31)

    from .ai_status import _is_real_key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if _is_real_key(api_key):
        logger.info("[humanize] BEFORE (%s): %s", post_type, text[:100].replace("\n", "↵"))
        try:
            result = _ai_humanize(text, post_type)
            logger.info("[humanize] AFTER  (claude/%s): %s", _MODEL, result[:100].replace("\n", "↵"))
            return result
        except Exception as exc:
            logger.warning("[humanize] Claude failed (%s) — rule-based fallback", exc)

    result = _rule_based(text, post_type, seed)
    logger.debug("[humanize] provider=rule-based post_type=%s", post_type)
    return result
