"""
Editorial Engine — generates complete, ready-to-publish daily content plans
for อะไรของมัน Facebook page.

Operates like a social media editorial team:
- Knows the season, day mood, and current trends
- Generates full captions (copy-paste ready)
- Picks posting times based on audience behavior
- Overrides normal schedule when a major event is trending
"""

from __future__ import annotations

import os
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from .trend_engine import get_today_trends, _try_ai_trend_enrichment
from .humanize_engine import humanize_caption

TZ = ZoneInfo("Asia/Bangkok")

_THAI_DAYS = ["วันจันทร์", "วันอังคาร", "วันพุธ", "วันพฤหัสบดี", "วันศุกร์", "วันเสาร์", "วันอาทิตย์"]

# ─────────────────────────────────────────────────────────────────────────────
# Caption templates — full ready-to-publish Thai text
# Each has: type, caption (with {var} slots), image_rec, cta
# ─────────────────────────────────────────────────────────────────────────────

_CAPTIONS: dict[str, list[dict]] = {
    "comment_bait": [
        {
            "caption": (
                "คำถามที่อยากรู้มานาน 🤔\n\n"
                "คนกรุงเทพฯ กับคนต่างจังหวัด\n"
                "ใครเครียดกว่ากัน?\n\n"
                "A: คนกรุงฯ — รถติด ค่าครองชีพแพง\n"
                "B: คนต่างจังหวัด — หางานยาก ต้องฝากอนาคตไว้กับกรุงฯ\n\n"
                "Comment A หรือ B 👇"
            ),
            "image_rec": "Graphic แบบ poll: ซ้าย = ตึกกรุงเทพฯ ขวา = ทุ่งนาต่างจังหวัด พื้นหลังสีเข้ม ตัวหนังสือสีขาว",
            "cta": "A หรือ B?",
        },
        {
            "caption": (
                "ของในบ้านที่ 'ควรมี' VS ของที่มีจริง 😅\n\n"
                "ควรมี: อุปกรณ์ออกกำลังกาย เครื่องทำน้ำผลไม้ โต๊ะทำงานสวยๆ\n\n"
                "มีจริง: ขนม รีโมท โทรศัพท์ชาร์จอยู่\n\n"
                "บ้านใครเป็นแบบเดียวกันบ้าง? 🤣"
            ),
            "image_rec": "Meme 2 ช่อง: บนคือ 'expectation' ล่างคือ 'reality' สไตล์ Thai meme แบบเรียบๆ",
            "cta": "Comment รูปบ้านจริงของคุณมาเลย",
        },
        {
            "caption": (
                "เงินเดือนเท่าไหร่ถึงจะ 'พอ' ในกรุงเทพฯ\n\n"
                "เมื่อ 10 ปีที่แล้ว: 15,000 บาท ยังอยู่ได้\n"
                "ตอนนี้: ต้องเกิน 30,000 ถึงจะรอด\n\n"
                "คุณคิดว่าตัวเลขที่ 'พอดี' คือเท่าไหร่?\n\n"
                "Comment บอกได้เลย — ไม่มีคำตอบถูกหรือผิด 👇"
            ),
            "image_rec": "ภาพนับธนบัตร หรือกราฟิกสไตล์ infographic เรียบๆ สีเขียวเข้ม",
            "cta": "ตัวเลขของคุณคือเท่าไหร่?",
        },
        {
            "caption": (
                "ตื่นกี่โมง บอกนิสัยคนได้เลย 🕐\n\n"
                "05:00 — ชีวิตดีมาก ออกกำลังกายทุกวัน (หรือนอนไม่หลับ)\n"
                "07:00 — ปกติดี มีวินัยพอใช้\n"
                "09:00 — WFH หรือฟรีแลนซ์\n"
                "11:00+ — ทำงานดึก หรือพักร้อน\n\n"
                "คุณตื่นกี่โมง? 👇"
            ),
            "image_rec": "กราฟิกนาฬิกาตั้งปลุก พื้นหลังสีกรมท่า ตัวเลขสีทอง",
            "cta": "Comment เวลาตื่นของคุณ",
        },
        {
            "caption": (
                "ของที่ซื้อแล้วใช้จริง VS ของที่ซื้อแล้วเก็บฝุ่น\n\n"
                "ใช้จริงทุกวัน: โทรศัพท์ หูฟัง สายชาร์จ\n"
                "เก็บฝุ่น: อุปกรณ์ออกกำลังกาย เครื่องทำสมูทตี้ หม้อหุงข้าวใหม่\n\n"
                "บ้านคุณมีของเก็บฝุ่นอะไรบ้าง? 😅\n"
                "Comment บอกได้เลย ไม่ตัดสิน 👇"
            ),
            "image_rec": "ภาพของที่มีฝุ่นจับ หรือ before/after ก้องสะอาด VS ของกองเยอะ สไตล์ humorous",
            "cta": "ของเก็บฝุ่นชิ้นที่ 1 ของคุณคือ?",
        },
        {
            "caption": (
                "คำถาม: ชาไทยเย็น กับกาแฟเย็น\n"
                "เลือกได้แค่อย่างเดียวตลอดชีวิต\n\n"
                "คุณเลือกอะไร?\n\n"
                "A: ชาไทยเย็น 🧋\n"
                "B: กาแฟเย็น ☕\n\n"
                "Comment 👇 แล้วอธิบายด้วยว่าทำไม"
            ),
            "image_rec": "ภาพชาไทยเย็นสีส้มสวยๆ วางข้างกาแฟเย็นสีน้ำตาล พื้นหลังไม้ ดูอบอุ่น",
            "cta": "A หรือ B?",
        },
    ],
    "weird_product": [
        {
            "caption": (
                "เพิ่งเจอของชิ้นนี้บน Shopee 😳\n\n"
                "ตอนแรกคิดว่า... ใครจะซื้อ?\n"
                "อ่านรีวิวแล้ว: 4,200+ ออเดอร์ ดาว 4.9\n\n"
                "บางทีสิ่งที่ดูแปลก อาจเป็นของที่ดีที่สุดก็ได้\n\n"
                "คุณจะซื้อไหม? 🤔"
            ),
            "image_rec": "ภาพสินค้าแปลกๆ ที่ดูไม่รู้ว่าใช้ทำอะไร วางบนพื้นขาวสะอาด มี rating ดาวอยู่มุม",
            "cta": "Comment: ซื้อ / ไม่ซื้อ",
        },
        {
            "caption": (
                "ของชิ้นนี้มีอยู่จริง ขายบน Shopee\n\n"
                "ฟังก์ชัน: ใช้งานได้จริง 100%\n"
                "ดีไซน์: คนเห็นแล้วต้องถาม 'นั่นคืออะไร?'\n"
                "ราคา: ถูกกว่าที่คิดมาก\n\n"
                "อยากรู้ว่าใช้ทำอะไร? Comment ถามมาเลย 👇"
            ),
            "image_rec": "ภาพ close-up สินค้าที่ดูปริศนา แสงดี พื้นหลังเรียบ เหมือน product photography",
            "cta": "ทายว่าใช้ทำอะไร?",
        },
        {
            "caption": (
                "นักประดิษฐ์ไทยไม่แพ้ใครในโลก 🇹🇭\n\n"
                "ของชิ้นนี้ Made in Thailand\n"
                "แก้ปัญหาที่ทุกคนเจอ แต่ไม่มีใครคิดทำมาก่อน\n\n"
                "ราคา 299 บาท\n"
                "รีวิว: ดีเกินราคามาก\n\n"
                "อยากรู้จักของชิ้นนี้ไหม? 👇"
            ),
            "image_rec": "ภาพสินค้าสไตล์ไทยๆ มีโลโก้ Made in Thailand ดูน่าภูมิใจ",
            "cta": "Comment บอกว่าสนใจ",
        },
        {
            "caption": (
                "เดินช็อป Shopee แล้วเจอสิ่งนี้\n\n"
                "ไม่รู้จะเรียกว่าอัจฉริยะ หรือบ้า\n"
                "แต่แน่ใจว่า... ต้องมีในบ้าน\n\n"
                "มีใครซื้อแล้วบ้าง? รีวิวให้ฟังหน่อย 👇"
            ),
            "image_rec": "ภาพ screenshot จาก Shopee หรือภาพสินค้าจริง มี sticker 'ขายดี' หรือ 'hot'",
            "cta": "รีวิวหน่อย!",
        },
    ],
    "nostalgia": [
        {
            "caption": (
                "ขนมที่หาไม่ได้แล้ว 🥹\n\n"
                "ถ้ายังขายอยู่ วันนี้คงอยากกินทุกวัน\n"
                "ราคา 1-5 บาท แต่ความสุขไม่ต่างจากของแพงเลย\n\n"
                "ขนมแบบนี้คุณจำได้ไหม?\n"
                "Comment ชื่อขนมที่คิดถึงที่สุด 👇"
            ),
            "image_rec": "Collage ขนมไทยยุค 90s: ทอฟฟี่รูปสัตว์, มาลาบาร์, เยลลี่ถ้วย, ลูกอม ฝาจุก สีสันสดใส",
            "cta": "ขนมอะไรที่คิดถึงที่สุด?",
        },
        {
            "caption": (
                "เกมตู้หยอดเหรียญ 50 สตางค์ 🎮\n\n"
                "รอคิวนาน เล่นได้แค่ 2 นาที แต่ตื่นเต้นมาก\n"
                "แพ้แล้วก็ขอสตางค์แม่มาหยอดใหม่\n\n"
                "เด็กยุคนี้ไม่เคยรู้สึกแบบนี้อีกแล้ว\n\n"
                "ใครเคยเล่นบ้าง? 🙋"
            ),
            "image_rec": "ภาพตู้เกม Street Fighter หรือ Contra เก่าๆ สีสันจัด หรือรูปวินเทจในร้านเกม",
            "cta": "เกมที่ชอบเล่นที่สุดสมัยนั้นคืออะไร?",
        },
        {
            "caption": (
                "โทรหาเพื่อนสมัยก่อน ☎️\n\n"
                "ต้องโทรผ่านพ่อแม่เขาก่อน\n"
                "'สวัสดีครับ ขอคุยกับ... ได้ไหมครับ'\n"
                "ใจหายทุกครั้ง กลัวบอกว่าไม่อยู่\n\n"
                "ยุคนี้กด LINE ก็เสร็จ แต่ความตื่นเต้นหายไปหมดเลย\n\n"
                "ใครยังจำความรู้สึกนั้นได้บ้าง? 🥹"
            ),
            "image_rec": "ภาพโทรศัพท์บ้านแบบหมุน หรือโทรศัพท์ตั้งโต๊ะสมัย 90s สีเหลืองหรือขาว ดูคลาสสิค",
            "cta": "Share ให้คนที่โตมายุคเดียวกันเห็น",
        },
        {
            "caption": (
                "ข้าวกล่องโรงเรียน ราคา 10 บาท 🍱\n\n"
                "ข้าวเยอะมาก กับข้าว 3 อย่าง\n"
                "วันไหนมีไก่ทอดถือว่า lucky day\n\n"
                "ตอนนี้ข้าวกล่อง 10 บาทไม่มีให้เห็นแล้ว\n"
                "ราคาเดิม แต่ขนาดครึ่งเดียว\n\n"
                "ใครคิดถึงข้าวกล่องโรงเรียนบ้าง? 🥹"
            ),
            "image_rec": "ภาพข้าวกล่องโฟมสมัยก่อน หรือภาพโรงอาหารโรงเรียนเก่าๆ ดูอบอุ่น สีโทนวอร์ม",
            "cta": "ราคาข้าวกล่องตอนนี้ที่บ้านคุณกล่องละเท่าไหร่?",
        },
    ],
    "visual_curiosity": [
        {
            "caption": (
                "ดูภาพนี้ให้ดีๆ 👀\n\n"
                "บางคนเห็นแบบหนึ่ง\n"
                "บางคนเห็นอีกแบบหนึ่ง\n\n"
                "คุณเห็นอะไรก่อน?\n"
                "Comment บอกด้วย 👇"
            ),
            "image_rec": "ภาพลวงตาหรือ optical illusion ที่ดูได้ 2 แบบ เช่น กระต่าย/เป็ด หรือแก้ว/ใบหน้า",
            "cta": "คุณเห็นอะไร?",
        },
        {
            "caption": (
                "ขนาดจริงของสิ่งนี้คุณรู้ไหม? 🤯\n\n"
                "ส่วนใหญ่เดาผิดหมด\n"
                "เดาก่อนแล้วกด See More ดูคำตอบ\n\n"
                "Comment คำตอบของคุณ 👇"
            ),
            "image_rec": "ภาพ object ที่ดูขนาดยาก เช่น อุกกาบาต ฟันวาฬ ขนนก ที่ใหญ่กว่าคนคิด วางข้างคนเพื่อเปรียบขนาด",
            "cta": "เดาขนาดก่อน!",
        },
    ],
    "trending": [
        {
            "caption": (
                "กำลังมาแรงมากบน Social Media\n\n"
                "ทุกคนพูดถึงเรื่องนี้กัน\n"
                "คุณตามทันแล้วหรือยัง?\n\n"
                "Comment บอกความคิดเห็น 👇"
            ),
            "image_rec": "Graphic เทรนด์ มีไอคอน trending โทนสีสดใส พื้นหลังเข้ม",
            "cta": "คิดอะไรกับเรื่องนี้?",
        },
    ],
}

# World Cup 2026 special captions (June 11 – July 19, 2026)
_WORLDCUP_CAPTIONS = [
    {
        "caption": (
            "บอลโลก 2026 🏆⚽\n\n"
            "คืนนี้ดูบอลกับใคร?\n\n"
            "A: ดูคนเดียวเงียบๆ\n"
            "B: ดูกับเพื่อน เสียงดังมาก\n"
            "C: ดูกับครอบครัว\n"
            "D: ไม่ดูเลย ไม่ชอบบอล\n\n"
            "Comment A / B / C / D 👇"
        ),
        "image_rec": "Graphic บอลโลก 2026 โทนสีทอง-แดง มีลูกฟุตบอลและถ้วยรางวัล ดูตื่นเต้น",
        "cta": "A, B, C หรือ D?",
        "type": "comment_bait",
    },
    {
        "caption": (
            "ของที่ต้องมีคืนดูบอล 🍺⚽\n\n"
            "เจอชิ้นนี้บน Shopee\n"
            "เก้าอี้พร้อม mini cooler ในตัว เก็บน้ำเย็นได้ 6 กระป๋อง\n"
            "4,200+ ออเดอร์ แล้ว\n\n"
            "นักประดิษฐ์คนนี้เข้าใจชีวิตคนดูบอลมาก 😂"
        ),
        "image_rec": "ภาพเก้าอี้ lazy boy หรือของแปลกๆ ที่ใช้ดูบอล วางข้าง minibar หรือเบียร์เย็น ดูตลก",
        "cta": "ซื้อไหมถ้าราคาน่ารัก?",
        "type": "weird_product",
    },
    {
        "caption": (
            "ดูบอลโลกสมัยเด็ก 🥹\n\n"
            "ตื่น 2 ตี ปลุกพ่อดูด้วยกัน\n"
            "โฆษณายาวกว่าเกม ภาพแตกๆ\n"
            "แต่ตื่นเต้นมากกว่ายุคนี้เยอะ\n\n"
            "ยุคนี้ดูสดบนมือถือได้เลย\n"
            "แต่ความรู้สึกนั้นไม่เหมือนเดิม\n\n"
            "ใครเคยดูบอลโลกกับพ่อแม่สมัยเด็กบ้าง? 🥹"
        ),
        "image_rec": "ภาพทีวีเก่าๆ ยุค 90s เปิดอยู่ มีครอบครัวดูบอลด้วยกัน หรือภาพ vintage football ไทย",
        "cta": "Share ให้พ่อแม่เห็น",
        "type": "nostalgia",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Daily schedule templates
# ─────────────────────────────────────────────────────────────────────────────

_DAILY_SCHEDULES: dict[int, list[dict]] = {
    # Weekday (Mon-Fri)
    "weekday": [
        {"time": "09:00", "type": "comment_bait",    "reason": "เช้าวันทำงาน คนเช็คโทรศัพท์ระหว่างรถติด engagement สูง"},
        {"time": "12:00", "type": "weird_product",   "reason": "พักเที่ยง คนเลื่อนฟีดง่ายๆ เห็นของแปลกแล้วอยากแชร์"},
        {"time": "19:00", "type": "nostalgia",       "reason": "หลังเลิกงาน คนผ่อนคลาย content อ่อนหวานได้ผลดี"},
        {"time": "21:00", "type": "comment_bait",    "reason": "ก่อนนอน คนชอบ interact กับโพสต์ที่ถามความเห็น"},
    ],
    # Weekend
    "weekend": [
        {"time": "09:00", "type": "nostalgia",       "reason": "เช้าวันหยุด คนมีเวลา อ่านเนื้อหายาวได้"},
        {"time": "12:00", "type": "comment_bait",    "reason": "เที่ยงวันหยุด ครอบครัวอยู่ด้วยกัน engagement สูง"},
        {"time": "16:00", "type": "weird_product",   "reason": "บ่ายวันหยุด คนเริ่มช็อปออนไลน์ ดูของแปลกสนุก"},
        {"time": "20:00", "type": "visual_curiosity","reason": "คืนวันหยุด คน share ของสนุกๆ กับเพื่อน"},
    ],
    # Override (major event)
    "override": [
        {"time": "09:00", "type": "event_hook",      "reason": "เช้าวันสำคัญ ต้องพูดถึงก่อนใคร"},
        {"time": "12:00", "type": "event_product",   "reason": "เที่ยง event content ได้รับ share สูงมาก"},
        {"time": "19:00", "type": "event_nostalgia", "reason": "เย็น เชื่อมความรู้สึกกับ event ได้ดี"},
        {"time": "21:00", "type": "comment_bait",    "reason": "คืน สรุป event ของวัน ให้คน comment"},
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Caption builder
# ─────────────────────────────────────────────────────────────────────────────

def _pick_caption(post_type: str, trends: dict, slot_idx: int, now: datetime | None = None) -> dict:
    """Pick and return a caption for the given type, considering trends."""
    now  = now or datetime.now(tz=TZ)
    seed = int(now.strftime("%Y%m%d")) + slot_idx
    rng  = random.Random(seed)

    is_worldcup = (
        (now.year == 2026 and now.month == 6 and now.day >= 11) or
        (now.year == 2026 and now.month == 7 and now.day <= 19)
    )

    if is_worldcup and slot_idx == 0:
        wc = rng.choice(_WORLDCUP_CAPTIONS)
        return wc

    bank = _CAPTIONS.get(post_type, _CAPTIONS["comment_bait"])
    entry = rng.choice(bank)
    return {**entry, "type": post_type}


def _enrich_with_ai(post: dict, trends: dict) -> dict:
    """Optionally enhance caption with Claude. No-op if key missing."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return post
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        season  = trends.get("season", "")
        mood    = trends.get("mood", "")
        slang   = ", ".join(trends.get("slang_today", []))
        base    = post.get("caption", "")

        system = (
            "คุณคือนักเขียน Social Media ของเพจ 'อะไรของมัน' ที่รู้จักวัฒนธรรมไทยดีมาก "
            "เสียง: สนุก แปลก อยากรู้อยากเห็น พูดตรงๆ ไม่เป็นทางการ ไม่ดูเป็น AI "
            "ห้ามใช้ภาษาโฆษณา ห้ามพูดถึงแบรนด์ใดๆ ห้ามทำให้ดู corporate "
            "ตอบเป็น Caption เท่านั้น ไม่ต้องอธิบาย"
        )
        prompt = (
            f"วันนี้ {season} ช่วง {mood}\n"
            f"สแลงที่กำลังเป็นที่นิยม: {slang}\n\n"
            f"ปรับ Caption นี้ให้เป็นธรรมชาติขึ้น เพิ่มความรู้สึกของคนไทยเข้าไป:\n\n"
            f"{base}\n\n"
            f"ห้ามเปลี่ยน format หรือ CTA ให้คง structure เดิม แค่ทำให้ฟังดู human ขึ้น"
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        enhanced = msg.content[0].text.strip()
        if enhanced and len(enhanced) > 30:
            post = {**post, "caption": enhanced, "ai_enhanced": True}
    except Exception:
        pass
    return post


# ─────────────────────────────────────────────────────────────────────────────
# Main public API
# ─────────────────────────────────────────────────────────────────────────────

def generate_today_content(for_date: datetime | None = None) -> dict:
    """
    Generate complete editorial plan for a given date (defaults to today).
    Returns 3-4 ready-to-publish posts with captions, image recs, and reasoning.
    """
    now    = for_date or datetime.now(tz=TZ)
    trends = get_today_trends(for_date=now)
    trends = _try_ai_trend_enrichment(trends)

    weekday   = now.weekday()
    is_weekend = weekday >= 5
    override  = trends.get("override_active", False)

    # Pick schedule template
    if override:
        schedule_key = "override"
    elif is_weekend:
        schedule_key = "weekend"
    else:
        schedule_key = "weekday"

    template_slots = _DAILY_SCHEDULES[schedule_key]

    posts = []
    for idx, slot in enumerate(template_slots):
        slot_type = slot["type"]

        # Map event types to real types
        if slot_type.startswith("event_"):
            event_map = {
                "event_hook":      "comment_bait",
                "event_product":   "weird_product",
                "event_nostalgia": "nostalgia",
            }
            slot_type = event_map.get(slot_type, "comment_bait")

        entry = _pick_caption(slot_type, trends, idx, now=now)

        # Step 1: inject trend/season context
        entry = _enrich_with_ai(entry, trends)

        # Step 2: humanize — make it sound like Thai people, not AI
        raw_caption = entry.get("caption", "")
        human_caption = humanize_caption(raw_caption, post_type=entry.get("type", slot_type))
        entry = {**entry, "caption": human_caption}

        posts.append({
            "slot":        idx + 1,
            "time":        slot["time"],
            "type":        entry.get("type", slot_type),
            "caption":     entry.get("caption", ""),
            "image_rec":   entry.get("image_rec", ""),
            "cta":         entry.get("cta", ""),
            "reasoning":   slot["reason"],
            "ai_enhanced": entry.get("ai_enhanced", False),
            "humanized":   human_caption != raw_caption,
        })

    return {
        "date":            now.strftime("%Y-%m-%d"),
        "day_th":          _THAI_DAYS[weekday],
        "season":          trends.get("season", ""),
        "season_emoji":    trends.get("season_emoji", ""),
        "mood":            trends.get("mood", ""),
        "override_active": override,
        "override_label":  trends.get("override_label", ""),
        "posts":           posts,
        "ai_trending":     trends.get("ai_trending", []),
        "slang_today":     trends.get("slang_today", []),
    }
