"""
Daily Trend Engine — discovers, scores, and caches trending topics for อะไรของมัน.

Sources (priority order):
1. Claude API if ANTHROPIC_API_KEY is set
2. Cultural calendar (Thai holidays + global events)
3. Seasonal themes (Thailand weather/culture)
4. Evergreen viral topic bank (weekly rotation)
"""

from __future__ import annotations

import os
import random
from datetime import datetime, date
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Bangkok")


# ─────────────────────────────────────────────────────────────────────────────
# Cultural calendar — (month, day): (label_th, keywords, urgency)
# urgency: "override" = replace normal schedule | "boost" = add extra post | "note" = mention only
# ─────────────────────────────────────────────────────────────────────────────

_CALENDAR: dict[tuple[int, int], tuple[str, list[str], str]] = {
    (1,  1):  ("ปีใหม่",         ["ปีใหม่", "ความตั้งใจ", "นับถอยหลัง"],           "override"),
    (1,  2):  ("หลังปีใหม่",     ["ปีใหม่ผ่านไป", "ควิตแล้ว", "ของขวัญ"],          "boost"),
    (2, 14):  ("วาเลนไทน์",      ["วาเลนไทน์", "คู่รัก", "ของขวัญ"],               "boost"),
    (4, 13):  ("สงกรานต์",        ["สงกรานต์", "น้ำ", "กลับบ้าน", "ครอบครัว"],     "override"),
    (4, 14):  ("สงกรานต์",        ["สงกรานต์", "วันครอบครัว", "อาหารไทย"],         "override"),
    (4, 15):  ("สงกรานต์",        ["สงกรานต์", "วันผู้สูงอายุ"],                   "override"),
    (5,  1):  ("วันแรงงาน",       ["วันหยุด", "พักผ่อน", "ออกเที่ยว"],             "boost"),
    (5,  5):  ("ฉัตรมงคล",        ["วันหยุด", "วันสำคัญ"],                         "note"),
    (6, 11):  ("บอลโลก 2026",    ["บอลโลก", "FIFA", "ฟุตบอล", "แมตช์แรก"],        "override"),
    (6, 18):  ("บอลโลก 2026",    ["บอลโลก", "กลุ่มแรก", "ฟุตบอล"],               "boost"),
    (7, 14):  ("บอลโลก รอบ 16",  ["บอลโลก", "รอบน็อคเอาท์", "ฟุตบอล"],           "override"),
    (7, 19):  ("บอลโลก รอบชิง",  ["บอลโลก", "รอบชิงชนะเลิศ", "แชมป์"],           "override"),
    (8, 12):  ("วันแม่",          ["วันแม่", "แม่", "ความรัก", "ครอบครัว"],        "override"),
    (10,13):  ("วันหยุดพิเศษ",    ["วันหยุด"],                                     "note"),
    (10,23):  ("วันปิยมหาราช",    ["วันหยุด", "วันสำคัญ"],                         "note"),
    (11,  5):  ("ลอยกระทง",      ["ลอยกระทง", "กระทง", "แม่น้ำ", "แสงเทียน"],    "override"),
    (12,  5):  ("วันพ่อ",         ["วันพ่อ", "พ่อ", "ความรัก"],                   "override"),
    (12, 31):  ("ส่งท้ายปีเก่า",  ["ปีใหม่", "นับถอยหลัง", "ความทรงจำ"],         "override"),
}

# ─────────────────────────────────────────────────────────────────────────────
# Seasonal themes (Thailand)
# ─────────────────────────────────────────────────────────────────────────────

_SEASONAL: dict[int, dict] = {
    3:  {"season": "ปลายหนาว/ต้นร้อน", "themes": ["อากาศเปลี่ยน", "ฝุ่น PM2.5", "แล้ง"],          "emoji": "🌤"},
    4:  {"season": "หน้าร้อน",          "themes": ["ร้อนมาก", "แอร์", "น้ำเย็น", "สงกรานต์"],      "emoji": "🔥"},
    5:  {"season": "ต้นฝน",            "themes": ["ฝนแรก", "ดินหอม", "รถติด"],                     "emoji": "🌧"},
    6:  {"season": "หน้าฝน",           "themes": ["ฝนตกทุกวัน", "น้ำท่วม", "ร้อนแล้วฝน", "ชุ่ม"], "emoji": "⛈"},
    7:  {"season": "กลางฝน",           "themes": ["น้ำท่วม", "ฝนหนัก", "บอลโลก"],                  "emoji": "🌊"},
    8:  {"season": "ปลายฝน",           "themes": ["อากาศดีขึ้น", "เมฆสวย", "วันแม่"],              "emoji": "🌥"},
    9:  {"season": "ต้นหนาว",          "themes": ["อากาศเริ่มเย็น", "เที่ยวเหนือ"],                "emoji": "🍃"},
    10: {"season": "หน้าหนาว",         "themes": ["หนาวตอนเช้า", "ลอยกระทง", "เที่ยว"],            "emoji": "🌬"},
    11: {"season": "กลางหนาว",         "themes": ["หนาว", "เสื้อกันหนาว", "เที่ยวดอย"],            "emoji": "❄"},
    12: {"season": "หนาว/ปลายปี",      "themes": ["เที่ยว", "ปีใหม่", "ของขวัญ", "ครอบครัว"],     "emoji": "🎄"},
    1:  {"season": "ต้นปี/ยังหนาว",   "themes": ["ความตั้งใจปีใหม่", "เริ่มต้นใหม่"],              "emoji": "🌱"},
    2:  {"season": "ปลายหนาว",         "themes": ["ใกล้ร้อน", "วาเลนไทน์", "มหาวิทยาลัย"],        "emoji": "💝"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Weekly mood — what audiences feel on each weekday
# ─────────────────────────────────────────────────────────────────────────────

_WEEKLY_MOOD: dict[int, dict] = {
    0: {"mood": "Monday blues — เริ่มสัปดาห์ใหม่",    "best_type": "comment_bait",    "time_peak": "12:00"},
    1: {"mood": "วันอังคาร — ชีวิตประจำวัน",           "best_type": "weird_product",   "time_peak": "19:00"},
    2: {"mood": "กลางสัปดาห์ — ยังอีกนาน",             "best_type": "nostalgia",       "time_peak": "21:00"},
    3: {"mood": "เกือบถึงวันหยุด — ลุ้นอยู่",          "best_type": "comment_bait",    "time_peak": "19:00"},
    4: {"mood": "TGIF — วันศุกร์!",                    "best_type": "trending",        "time_peak": "19:00"},
    5: {"mood": "วันหยุด — สบายๆ ออกเที่ยว",           "best_type": "visual_curiosity","time_peak": "10:00"},
    6: {"mood": "วันอาทิตย์ — พักผ่อน อยู่บ้าน",       "best_type": "nostalgia",       "time_peak": "20:00"},
}

# ─────────────────────────────────────────────────────────────────────────────
# Evergreen viral topic bank — grouped by type
# ─────────────────────────────────────────────────────────────────────────────

_VIRAL_TOPICS: dict[str, list[dict]] = {
    "comment_bait": [
        {"topic": "กินข้าวกี่มื้อ", "slant": "คนไทยกินข้าวกี่มื้อต่อวัน — ตอบตรงๆ เลย"},
        {"topic": "ตื่นกี่โมง",      "slant": "คนตื่นเช้า VS คนตื่นสาย — ชีวิตต่างกันยังไง"},
        {"topic": "ซื้อของก่อนกิน",  "slant": "ก่อนกินข้าว ชอบช็อปก่อน หรือกินก่อนช็อป?"},
        {"topic": "ชาหรือกาแฟ",      "slant": "เช้านี้ดื่มอะไร — ชาไทยหรือกาแฟ?"},
        {"topic": "รถหรือ BTS",      "slant": "นั่ง BTS กับขับรถ — คุณเลือกอะไรในกรุงเทพฯ"},
        {"topic": "ทำงานที่บ้าน",    "slant": "WFH ดีกว่าไปออฟฟิศ จริงไหม?"},
        {"topic": "เงินเดือน",       "slant": "เงินเดือนเท่าไหร่ถึงจะ 'พอ' ในกรุงเทพฯ"},
        {"topic": "คนเดียวหรือแก๊งค์", "slant": "กินข้าวคนเดียว VS กินกับเพื่อน — ชอบแบบไหน?"},
    ],
    "weird_product": [
        {"topic": "ที่จัดสายชาร์จ",    "slant": "ของชิ้นนี้ดูไม่มีประโยชน์ แต่รีวิวดีมาก"},
        {"topic": "ที่ใส่แว่น",         "slant": "ใครจะคิดว่าของนี้จะขายดี 10,000+ ออเดอร์"},
        {"topic": "เก้าอี้พกพา",        "slant": "ไม่รู้จะใช้ที่ไหน แต่อยากได้"},
        {"topic": "ที่กรองน้ำพกพา",    "slant": "ดื่มน้ำจากที่ไหนก็ได้ เชื่อไหม"},
        {"topic": "กระเป๋าระบายความร้อน", "slant": "ในรถร้อน แต่ขนมไม่ละลาย — ของนี้ทำได้"},
        {"topic": "ตู้กดน้ำมินิ",       "slant": "ทำไมถึงมีสิ่งนี้? แต่ขายดีมาก"},
        {"topic": "ที่วางโทรศัพท์บนรถ", "slant": "ดูแล้วรู้สึกว่าชีวิตสะดวกขึ้นจริงๆ"},
        {"topic": "หมอนนวดไฟฟ้า",       "slant": "ซื้อมาแล้วใช้ทุกวัน หรือเก็บฝุ่น?"},
    ],
    "nostalgia": [
        {"topic": "ขนมสมัยเด็ก",      "slant": "ขนมที่หาไม่ได้แล้ว ยังจำรสชาติได้ไหม"},
        {"topic": "เกมตู้",             "slant": "50 สตางค์ต่อตา เงินก้อนแรกหมดไปกับนี้"},
        {"topic": "โทรศัพท์บ้าน",       "slant": "สมัยก่อนโทรหาเพื่อนต้องผ่านพ่อแม่เขาก่อน"},
        {"topic": "น้ำแข็งไส",         "slant": "น้ำแข็งไส 5 บาท ยังจำความสุขนั้นได้ไหม"},
        {"topic": "หนังสือการ์ตูน",     "slant": "ยืมมาอ่านต่อๆ กัน ใครทำหาย โดนตามล่า"},
        {"topic": "รถเมล์",            "slant": "นั่งรถเมล์ไปโรงเรียน ลมพัดเต็มๆ หน้า"},
        {"topic": "ทีวีขาวดำ",          "slant": "ปรับเสาอากาศให้ภาพชัด — ทักษะที่ไม่มีใครสอน"},
        {"topic": "ข้าวกล่อง 10 บาท",  "slant": "ข้าวกล่องสมัยประถม — อยากได้ราคาเดิม"},
    ],
    "visual_curiosity": [
        {"topic": "ภาพลวงตา",          "slant": "ดูให้ดีๆ — สิ่งที่เห็นอาจไม่ใช่สิ่งที่มีอยู่จริง"},
        {"topic": "ของที่ตัดกัน",       "slant": "เอาของ 2 อย่างมาวางข้างกัน เห็นอะไรแปลกๆ"},
        {"topic": "ขนาดจริงของสิ่งของ", "slant": "คุณรู้ไหมว่าของนี้ใหญ่แค่ไหนจริงๆ"},
        {"topic": "ของสีแปลก",         "slant": "เห็นครั้งแรกแล้วตกใจ — สีนี้มีจริง"},
        {"topic": "ก่อน/หลัง",         "slant": "เปลี่ยนไปแบบนี้ได้ยังไง"},
    ],
    "trending": [
        {"topic": "ข่าวดัง",           "slant": "ทุกคนพูดถึงเรื่องนี้ — คุณรู้ยังหรือเปล่า"},
        {"topic": "เทรนด์ใหม่",        "slant": "กำลังมาแรงมาก ใครตามทันบ้าง"},
        {"topic": "ไวรัลสัปดาห์นี้",   "slant": "ไวรัลสัปดาห์นี้ — เห็นแล้วหรือยัง"},
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Thai slang bank (rotate into captions naturally)
# ─────────────────────────────────────────────────────────────────────────────

_THAI_SLANG = [
    "สุดปัง", "ปังมาก", "โคตรเด็ด", "ชิลๆ", "เฟี้ยวมาก",
    "โหดร้าย (ความหมายดี)", "ดีจนงง", "เข้าใจยาก",
    "สไตล์มาก", "อยากได้เลย", "ซื้อแล้ว บอกเลย",
    "ดีกว่าที่คิด", "แอบแซบ", "เริ่ดมาก",
]

# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_today_trends() -> dict:
    """
    Return trend data for today.
    Checks calendar override, seasonal context, weekly mood, and viral topic bank.
    """
    now     = datetime.now(tz=TZ)
    month   = now.month
    day     = now.day
    weekday = now.weekday()

    # Calendar event
    calendar_key = (month, day)
    calendar_event = _CALENDAR.get(calendar_key)

    override_active = False
    override_label  = ""
    override_topics: list[str] = []

    if calendar_event:
        label, topics, urgency = calendar_event
        if urgency == "override":
            override_active = True
            override_label  = label
            override_topics = topics
        elif urgency == "boost":
            override_active = False
            override_label  = label
            override_topics = topics

    # Seasonal
    season_data = _SEASONAL.get(month, {"season": "", "themes": [], "emoji": "🌤"})

    # Weekly mood
    mood_data = _WEEKLY_MOOD.get(weekday, _WEEKLY_MOOD[2])

    # Pick viral topics for today (deterministic by date seed)
    seed = now.year * 10000 + month * 100 + day
    rng  = random.Random(seed)

    def _pick(bank: list, n: int) -> list:
        return rng.sample(bank, min(n, len(bank)))

    viral_today = {
        "comment_bait":    _pick(_VIRAL_TOPICS["comment_bait"],    2),
        "weird_product":   _pick(_VIRAL_TOPICS["weird_product"],   2),
        "nostalgia":       _pick(_VIRAL_TOPICS["nostalgia"],       1),
        "visual_curiosity":_pick(_VIRAL_TOPICS["visual_curiosity"],1),
        "trending":        _pick(_VIRAL_TOPICS["trending"],        1),
    }

    # Trending slang for today
    slang_today = rng.sample(_THAI_SLANG, 3)

    return {
        "date":             now.strftime("%Y-%m-%d"),
        "weekday":          now.weekday(),
        "season":           season_data["season"],
        "season_themes":    season_data["themes"],
        "season_emoji":     season_data["emoji"],
        "mood":             mood_data["mood"],
        "best_type":        mood_data["best_type"],
        "time_peak":        mood_data["time_peak"],
        "override_active":  override_active,
        "override_label":   override_label,
        "override_topics":  override_topics,
        "viral_topics":     viral_today,
        "slang_today":      slang_today,
        "calendar_event":   calendar_event,
    }


def _try_ai_trend_enrichment(trends: dict) -> dict:
    """Attempt to enrich trends with Claude API. Silent no-op if key not available."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return trends
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            f"Today is {trends['date']} in Thailand ({trends['season']} season). "
            f"Generate 3 trending discussion topics on Thai Facebook right now, "
            f"focused on everyday life, humor, and culture. "
            f"Reply in Thai only. Format: one topic per line."
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        lines = msg.content[0].text.strip().split("\n")
        trends["ai_trending"] = [l.strip() for l in lines if l.strip()]
    except Exception:
        pass
    return trends
