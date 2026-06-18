"""
Humanize Engine — Thai Facebook caption transformer.

Pipeline (4 passes):
  1. Strip AI openers
  2. Substitution table (formal → casual)
  3. Type-aware CTA replacement
  4. Relatable hook injection

Backed by Thai Content Intelligence Engine:
  - Pattern Library: weighted CTAs and hooks
  - Learning Loop: applies learned weight overrides from DuckDB
  - Voice Definition: quality scoring

Voice: คนไทยเมาท์กัน / คอมเมนต์ใต้โพสต์ไวรัล
Target: "เออว่ะ" / "จริง" / "บ้านกูก็เป็น" / "กูคนหนึ่ง"
"""

from __future__ import annotations

import logging
import os
import random

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"


# ─────────────────────────────────────────────────────────────────────────────
# Intelligence imports (lazy — graceful fallback if package missing)
# ─────────────────────────────────────────────────────────────────────────────

def _get_intelligence():
    """Return (pattern_library, learning_loop) or (None, None) on import error."""
    try:
        from .thai_intelligence import pattern_library, learning_loop
        return pattern_library, learning_loop
    except Exception as exc:
        logger.warning("[humanize] thai_intelligence unavailable: %s", exc)
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Pass 1 — strip AI openers
# ─────────────────────────────────────────────────────────────────────────────

def _pass1_strip_opener(text: str) -> str:
    lib, _ = _get_intelligence()
    openers = lib.AI_OPENERS if lib else _FALLBACK_OPENERS
    for opener in openers:
        if text.startswith(opener):
            return text[len(opener):]
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Pass 2 — formal → casual substitutions
# ─────────────────────────────────────────────────────────────────────────────

def _pass2_substitutions(text: str) -> str:
    lib, _ = _get_intelligence()
    subs = lib.SUBS if lib else _FALLBACK_SUBS
    for old, new in subs:
        text = text.replace(old, new)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Pass 3 — type-aware CTA replacement
# ─────────────────────────────────────────────────────────────────────────────

def _is_poll(text: str) -> bool:
    lib, _ = _get_intelligence()
    signals = lib.POLL_SIGNALS if lib else _FALLBACK_POLL_SIGNALS
    return any(sig in text for sig in signals)


def _pass3_cta(text: str, post_type: str, rng: random.Random) -> str:
    lines = text.rstrip().split("\n")
    if not lines:
        return text

    last = lines[-1].strip()

    # Already a good short casual CTA — leave it alone
    if len(last) <= 15 and ("👇" in last or "?" in last or "มั้ย" in last or "วะ" in last):
        return text

    # Check if ending looks like a bad generic CTA
    lib, _ = _get_intelligence()
    bad_endings = lib.BAD_CTA_ENDINGS if lib else _FALLBACK_BAD_ENDINGS
    is_bad = any(last.endswith(b.rstrip()) or last == b.strip() for b in bad_endings)

    if not is_bad:
        return text

    # Get learned weight overrides
    weight_overrides: dict[str, float] | None = None
    if lib:
        try:
            from .thai_intelligence import learning_loop
            weight_overrides = learning_loop.get_weight_overrides(post_type)
        except Exception:
            pass

    is_poll = _is_poll(text)
    if lib:
        new_cta = lib.get_cta(post_type, is_poll, rng, weight_overrides)
    else:
        key = f"{post_type}_poll" if is_poll else f"{post_type}_general"
        bank = _FALLBACK_CTAS.get(key) or _FALLBACK_CTAS.get(post_type) or _FALLBACK_CTAS["comment_bait_general"]
        new_cta = rng.choice(bank)

    lines[-1] = new_cta
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Pass 4 — relatable hook injection
# ─────────────────────────────────────────────────────────────────────────────

def _pass4_hook(text: str, post_type: str, rng: random.Random) -> str:
    lib, _ = _get_intelligence()
    hook_signals = lib.HOOK_SIGNALS if lib else _FALLBACK_HOOK_SIGNALS

    if any(sig in text for sig in hook_signals):
        return text

    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) < 4:
        return text

    weight_overrides: dict[str, float] | None = None
    if lib:
        try:
            from .thai_intelligence import learning_loop
            weight_overrides = learning_loop.get_weight_overrides(post_type)
        except Exception:
            pass

    if lib:
        hook = lib.get_hook(post_type, rng, weight_overrides)
    else:
        bank = _FALLBACK_HOOKS.get(post_type, _FALLBACK_HOOKS["comment_bait"])
        hook = rng.choice(bank)

    all_lines = text.split("\n")
    last_idx = len(all_lines) - 1
    while last_idx > 0 and not all_lines[last_idx].strip():
        last_idx -= 1

    all_lines.insert(last_idx, "")
    all_lines.insert(last_idx, hook)
    return "\n".join(all_lines)


# ─────────────────────────────────────────────────────────────────────────────
# Public rule-based entry point
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


# ─────────────────────────────────────────────────────────────────────────────
# Claude AI path (only when real ANTHROPIC_API_KEY present)
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def humanize_caption(text: str, post_type: str = "comment_bait") -> str:
    """
    Apply humanize layer. Claude Haiku if real ANTHROPIC_API_KEY, else 4-pass rule-based.
    Automatically applies learned pattern weights from the intelligence loop.
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


def score_caption(text: str, post_type: str = "comment_bait") -> dict:
    """
    Score a caption against page voice standards.
    Returns quality result dict with score, passed, issues, badges.
    """
    try:
        from .thai_intelligence.voice_definition import check_content_quality
        result = check_content_quality(text, post_type)
        return {
            "score": result.score,
            "passed": result.passed,
            "issues": [{"code": i.code, "severity": i.severity, "message": i.message}
                       for i in result.issues],
            "badges": result.badges,
            "summary": result.summary(),
        }
    except Exception as exc:
        logger.debug("[humanize] score_caption failed: %s", exc)
        return {"score": 0, "passed": False, "issues": [], "badges": [], "summary": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Fallback data (used if thai_intelligence package fails to import)
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_OPENERS: list[str] = [
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

_FALLBACK_SUBS: list[tuple[str, str]] = [
    ("Comment บอกได้เลยว่าคุณเป็นทีมไหน 👇", "เธออยู่ทีมไหนวะ 👇"),
    ("Comment บอกได้เลย 👇",                  "บอกมาเลย 👇"),
    ("Comment A หรือ B 👇",                    "A หรือ B วะ 👇"),
    ("แสดงความคิดเห็น 👇",                    "บอกมาเลย 👇"),
    ("บางทีสิ่งที่ดูแปลก อาจเป็นของที่ดีที่สุดก็ได้", "คนที่ซื้อรู้อะไรที่กูไม่รู้แน่ๆ 💀"),
    ("ไม่มีคำตอบถูกหรือผิด — แค่อยากรู้ว่าคุณคิดยังไง", "แค่อยากรู้ว่าใครเป็นแบบเดียวกันบ้าง 😂"),
    ("อย่างไรก็ตาม", "แต่"),
    ("เพราะฉะนั้น", "เลย"),
    ("ดังนั้น", "งั้น"),
    ("หรือไม่", "รึเปล่า"),
    ("อย่างไร", "ยังไง"),
    ("คุณจะซื้อไหม? 🤔", "ซื้อหรือไม่ซื้อ 👇"),
    ("คุณจะซื้อไหม?", "ซื้อหรือไม่ซื้อ 👇"),
    ("ไหม?", "มั้ย 👇"),
    ("ใช่ไหม?", "จริงมั้ย 😂"),
]

_FALLBACK_POLL_SIGNALS: list[str] = ["A:", "B:", "A :", "B :", "ทีม A", "ทีม B", "A หรือ B"]

_FALLBACK_HOOK_SIGNALS: list[str] = [
    "แค่กูรึเปล่า", "บ้านกูก็", "กูคนเดียว", "กูยังงง",
    "คิดถึงจุง", "โห นึก", "กูไม่รู้", "ซื้อรู้อะไร",
]

_FALLBACK_BAD_ENDINGS: list[str] = [
    "บอกความคิดเห็น 👇",
    "แสดงความคิดเห็น 👇",
    "Share ให้คนที่โตมายุคเดียวกันเห็น",
    "กดแชร์ให้เพื่อนด้วย",
]

_FALLBACK_CTAS: dict[str, list[str]] = {
    "comment_bait_poll":    ["A หรือ B วะ 👇", "เธออยู่ทีมไหน 👇"],
    "comment_bait_general": ["บ้านใครเป็นบ้าง 😂", "แค่กูรึเปล่า 😅", "ใครเหมือนกันบ้างวะ 👇"],
    "weird_product":        ["ซื้อหรือไม่ซื้อ 👇", "โลกนี้ไปไกลมากจริงๆ 💀"],
    "nostalgia":            ["ยังจำได้บ้างไหม 🥹", "คิดถึงมั้ย 🥹"],
    "visual_curiosity":     ["เธอเห็นอะไรก่อนวะ 👇", "เดาซิ 👇"],
    "trending":             ["คิดว่ายังไงกัน 👇"],
    "affiliate":            ["สนใจบอกมาเลย 👇"],
}

_FALLBACK_HOOKS: dict[str, list[str]] = {
    "comment_bait":     ["แค่กูรึเปล่าที่รู้สึกแบบนี้ 😅", "บ้านกูก็เป็นแบบนี้เลย", "กูคนเดียวรึเปล่า 😂"],
    "weird_product":    ["กูยังงงอยู่ว่ามีคนซื้อทำไม 💀", "โลกนี้ไปไกลมากจริงๆ"],
    "nostalgia":        ["คิดถึงจุงๆ เลย 🥹", "เวลามันผ่านเร็วมากนะ 😢"],
    "visual_curiosity": ["กูนั่งดูนานมาก 😂"],
    "trending":         ["กระแสนี้มาแรงมากจริงๆ"],
    "affiliate":        ["กูก็เพิ่งรู้ว่ามีของแบบนี้"],
}
