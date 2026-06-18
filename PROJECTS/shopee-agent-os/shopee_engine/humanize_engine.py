"""
Humanize Engine — transforms Thai Facebook captions from AI-draft quality
into natural conversational Thai for page อะไรของมัน.

Pipeline: AI Draft → humanize_caption() → Publish

Voice: casual, slightly sarcastic, funny, relatable — like friends chatting.
Target reaction: "เออว่ะ" / "จริง" / "บ้านกูก็เป็น" / "กูคนหนึ่ง"
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# AI humanize — system prompt
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM = """\
คุณเป็น editor ของเพจ Facebook "อะไรของมัน" เพจไทยที่พูดเรื่องชีวิตประจำวัน

งาน: รับ draft post แล้วเขียนใหม่ให้ฟังดูเหมือนคนไทยคุยกับเพื่อน — ไม่ใช่ content creator ไม่ใช่ AI ไม่ใช่บทความ

VOICE:
- พูดสั้นๆ ตรงๆ ตลก เจ็บปวด relatable
- อ่านแล้วรู้สึก "เออว่ะ จริง" หรือ "บ้านกูก็เป็น" — ไม่ใช่ "interesting content"
- ถ้ามีสแลงหรือ particle ให้ใช้แบบ natural: อะ / นะ / เว้ย / ไง / วะ / โว้ย / อ่ะ
- ห้ามใส่ทุกคำในประโยค เลือกใช้เฉพาะตรงที่มันเข้าที่จริงๆ

RULES:
1. ประโยคสั้น — หนึ่งความคิดต่อหนึ่งบรรทัด ไม่มีย่อหน้ายาว
2. เปิดหัวแบบคนพูด — ห้ามขึ้นต้นด้วย "คุณเคย..." / "ในยุค..." / "น่าสนใจมาก..." / "คำถามที่น่าสนใจ..."
3. คำถาม / comment bait ต้องรู้สึก genuine ห้ามใช้ "Comment บอกได้เลย 👇" — มันดู AI มาก
4. ห้ามใช้: ดังนั้น / เพราะฉะนั้น / อย่างไรก็ตาม / ที่น่าสนใจคือ / ไม่มีคำตอบถูกหรือผิด
5. แทน "หรือไม่" ด้วย "รึเปล่า", แทน "อย่างไร" ด้วย "ยังไง"
6. เก็บ emoji ทุกตัวจาก draft เดิม
7. ถ้า draft มี format A/B ให้คง format ไว้
8. สั้นลง 20-30% จาก draft เดิม

ตัวอย่าง:
Draft: "คำถามที่อยากรู้มานาน 🤔\n\nคนกรุงเทพฯ กับคนต่างจังหวัด ใครเครียดกว่ากัน?\n\nA: คนกรุงฯ — รถติด ค่าครองชีพแพง\nB: คนต่างจังหวัด — หางานยาก ต้องฝากอนาคตไว้กับกรุงฯ\n\nComment A หรือ B 👇"
ดี:    "กรุงฯ vs ต่างจังหวัด ใครเครียดกว่ากันวะ 😤\n\nกรุงฯ: รถติด ค่าเช่าแพง คิวหมอนาน\nต่างจังหวัด: งานน้อย โรงบาลไกล ต้องฝากอนาคตไว้กับกรุงฯ อยู่ดี\n\nแค่กูรึเปล่าที่รู้สึกว่าไม่ว่าจะอยู่ไหนก็โดนครบ 😂\n\nA หรือ B ?"

Draft: "ของในบ้านที่ 'ควรมี' VS ของที่มีจริง 😅\n\nบ้านใครเป็นแบบเดียวกันบ้าง? 🤣"
ดี:    "ของที่ 'ควรมี' VS ของที่มีจริงในบ้าน 😅\n\nควรมี: ดัมเบล เครื่องคั้นน้ำผลไม้ โต๊ะทำงาน\nมีจริง: ขนม รีโมท โทรศัพท์ชาร์จค้างไว้\n\nบ้านใครเป็นบ้าง 😂"

Draft: "ของชิ้นนี้มีอยู่จริง และขายดีมาก 😳\n\nทำไมถึงมีคนซื้อสิ่งนี้ได้?"
ดี:    "เฮ้ย ของนี้มีจริงนะ 😳\n\nแล้วยังขายดีด้วย 💀\n\nโลกไปไกลมากแล้วจริงๆ"

Return ONLY the final caption. No explanation. No "Here is..." prefix.\
"""


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based fallback (no API key)
# ─────────────────────────────────────────────────────────────────────────────

_RULES = [
    # AI CTA patterns → casual
    ("Comment บอกได้เลยว่าคุณเป็นทีมไหน 👇",    "เธออยู่ทีมไหนอะ 👇"),
    ("Comment บอกได้เลย 👇",                       "บอกด้วยนะ 👇"),
    ("Comment บอกได้เลย",                          "บอกด้วยนะ"),
    ("ไม่มีคำตอบถูกหรือผิด — แค่อยากรู้ว่าคุณคิดยังไง", "แค่อยากรู้ว่าใครเป็นแบบเดียวกันบ้าง 😂"),
    ("ไม่มีคำตอบถูกหรือผิด",                       "ไม่มีถูกผิดนะ"),
    # Formal connectors → casual
    ("อย่างไรก็ตาม",                               "แต่"),
    ("เพราะฉะนั้น",                                "เลย"),
    ("ดังนั้น",                                    "งั้น"),
    ("ที่น่าสนใจคือ",                              ""),
    ("ทั้งนี้",                                    ""),
    # Formal Thai → spoken Thai
    ("หรือไม่",                                    "รึเปล่า"),
    ("อย่างไร",                                    "ยังไง"),
    ("ของคุณคือ",                                  "ของเธอคือ"),
    ("คุณคิดว่า",                                  "คิดว่า"),
    ("ที่คุณ",                                     "ที่เธอ"),
]

# AI-style openers to strip from line 1
_AI_OPENERS = [
    "คำถามที่อยากรู้มานาน 🤔\n\n",
    "คำถามที่อยากรู้มานาน\n\n",
    "คุณเคยสังเกตไหมว่า",
    "คุณเคย",
    "ในยุคที่",
    "ในยุคปัจจุบัน",
    "ปฏิเสธไม่ได้ว่า",
    "เชื่อหรือไม่",
    "น่าสนใจมากที่",
    "น่าสนใจมาก",
    "คำถามที่น่าสนใจ",
]


def _rule_based(text: str) -> str:
    for old, new in _RULES:
        text = text.replace(old, new)
    for opener in _AI_OPENERS:
        if text.startswith(opener):
            text = text[len(opener):]
            break
    # Clean up any double blank lines left by removals
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# AI humanize
# ─────────────────────────────────────────────────────────────────────────────

_TYPE_HINTS: dict[str, str] = {
    "comment_bait":     "ประเภท: comment bait — ถามความคิดเห็น ให้คนอยากตอบ",
    "weird_product":    "ประเภท: weird product — ของแปลก ตลก น่าตกใจ คนอยากแชร์",
    "nostalgia":        "ประเภท: nostalgia — ความทรงจำวัยเด็ก คนเดิน 80s-90s",
    "visual_curiosity": "ประเภท: visual curiosity — ดึงดูดให้มองนานขึ้น แล้วก็ comment",
    "trending":         "ประเภท: trending — กระแสที่คนพูดถึงอยู่",
    "affiliate":        "ประเภท: affiliate — แนะนำสินค้า แบบเป็นกันเอง ไม่ขาย",
}


_MODEL = "claude-haiku-4-5-20251001"


def _ai_humanize(text: str, post_type: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    hint    = _TYPE_HINTS.get(post_type, "")
    content = f"{hint}\n\n---\n{text}" if hint else text

    msg = client.messages.create(
        model=_MODEL,
        max_tokens=600,
        system=_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    result = msg.content[0].text.strip()
    if len(result) < 20:
        logger.warning("[humanize] AI returned too-short result, using rule-based")
        return _rule_based(text)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def humanize_caption(text: str, post_type: str = "comment_bait") -> str:
    """
    Apply humanize layer to a Thai Facebook caption.
    Uses Claude Haiku if ANTHROPIC_API_KEY is set, else rule-based fallback.
    """
    if not text or not text.strip():
        return text

    from .ai_status import _is_real_key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if _is_real_key(api_key):
        logger.info("[humanize] BEFORE (%s): %s", post_type, text[:120].replace("\n", "↵"))
        try:
            result = _ai_humanize(text, post_type)
            logger.info("[humanize] AFTER  (claude/%s): %s", _MODEL, result[:120].replace("\n", "↵"))
            logger.info("[humanize] provider=claude model=%s", _MODEL)
            return result
        except Exception as exc:
            logger.warning("[humanize] Claude failed (%s) — using rule-based fallback", exc)

    result = _rule_based(text)
    logger.info("[humanize] provider=rule-based (no valid API key)")
    return result
