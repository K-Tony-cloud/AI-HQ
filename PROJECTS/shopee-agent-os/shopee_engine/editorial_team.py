"""
Editorial Team — multi-provider article generation with deterministic fallback.

Provider priority (first available wins):
  1. ANTHROPIC_API_KEY (real key, sk-ant-api..., >40 chars) → Claude Sonnet
  2. OPENROUTER_API_KEY → free/paid OpenRouter model (Thai-capable)
  3. OPENAI_API_KEY → GPT-4o-mini
  4. Deterministic → data-driven Thai content, always available, zero cost

Interface is stable across all providers — same dict returned every time.
Switching provider = add env var, no code change needed.
"""

from __future__ import annotations

import json
import os
import re

try:
    import anthropic as anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

EDITORIAL_MODEL     = os.environ.get("SHOPEE_EDITORIAL_MODEL", "claude-sonnet-4-6")
OPENROUTER_MODEL    = os.environ.get("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

# ---------------------------------------------------------------------------
# Category context — primes deterministic engine and AI system prompts
# ---------------------------------------------------------------------------

_CATEGORY_CONTEXT: dict[str, dict] = {
    "home-living": {
        "contexts": ["คอนโด", "บ้าน", "ห้องเช่า", "ห้องนอน", "ครอบครัว", "อยู่คนเดียว"],
        "pain_points": ["ทำความสะอาดยาก", "เปลืองไฟ", "เสียงดัง", "ประหยัดพื้นที่"],
        "use_cases": ["ใช้ทุกวัน", "ทำอาหาร", "ซักรีด", "ทำความสะอาด", "ตกแต่งบ้าน"],
    },
    "mobile-gadgets": {
        "contexts": ["ทำงาน", "เรียน", "เล่นเกม", "ถ่ายรูป/วิดีโอ", "พกพา", "ใช้งานหนัก"],
        "pain_points": ["แบตหมดเร็ว", "ช้า ค้าง", "กล้องไม่คมชัด", "หนักเกินพกพา"],
        "use_cases": ["Social Media", "เล่นเกม", "ดูหนัง", "ทำงาน", "ถ่ายภาพ"],
    },
    "beauty": {
        "contexts": ["ผิวแพ้ง่าย", "ผิวมัน", "ผิวแห้ง", "ผิวผสม", "มือใหม่", "ใช้มานาน"],
        "pain_points": ["แพ้สารเคมี", "ผลลัพธ์ช้า", "ราคาแพง", "หาซื้อยาก", "ปลอมเยอะ"],
        "use_cases": ["ดูแลผิวหน้า", "แต่งหน้า", "ดูแลผม", "บำรุงผิวกาย"],
    },
    "health": {
        "contexts": ["ออกกำลังกาย", "ฟื้นฟูร่างกาย", "ผู้สูงอายุ", "เด็ก", "คนทำงาน"],
        "pain_points": ["ปวดหลัง ปวดคอ", "นอนไม่หลับ", "ภูมิแพ้", "ฝุ่น PM2.5"],
        "use_cases": ["ออกกำลังกายที่บ้าน", "พักฟื้น", "ดูแลสุขภาพประจำวัน"],
    },
    "sports": {
        "contexts": ["นักกีฬาจริงจัง", "ออกกำลังกายเพื่อสุขภาพ", "มือใหม่"],
        "pain_points": ["ไม่ทนทาน", "สวมใส่ไม่สบาย", "ราคาต่อคุณภาพ", "ของแท้ยาก"],
        "use_cases": ["วิ่ง", "ฟิตเนส", "กีฬาทีม", "กลางแจ้ง"],
    },
    "baby-kids": {
        "contexts": ["เด็กแรกเกิด", "เด็กเล็ก", "พ่อแม่มือใหม่", "ของขวัญ"],
        "pain_points": ["ความปลอดภัย", "วัสดุสารเคมี", "ทนทาน", "ทำความสะอาดยาก"],
        "use_cases": ["พัฒนาการ", "ความบันเทิง", "ความปลอดภัย", "ลดภาระพ่อแม่"],
    },
    "food-drinks": {
        "contexts": ["ทำอาหารเอง", "สุขภาพ", "ของฝาก", "ของกิน"],
        "pain_points": ["รสชาติ", "ส่วนผสม", "อายุการเก็บ", "ราคาต่อปริมาณ"],
        "use_cases": ["กินเพื่อสุขภาพ", "ทำขนม", "ของฝาก", "อาหารด่วน"],
    },
}

# ---------------------------------------------------------------------------
# AI system prompt (used when real AI provider is available)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
คุณคือทีม Editorial AI ของเว็บไซต์รีวิวสินค้าภาษาไทย ประกอบด้วยผู้เชี่ยวชาญ 7 คนที่ทำงานร่วมกัน:

Nova    → วางโครงบทความ เปิดบทความด้วย Context ที่ทำให้คนอยากอ่าน ไม่ใช่แค่บอกว่า "บทความนี้รวบรวม..."
Cipher  → ตรวจสอบตัวเลขและ Spec ทุกตัว — ต้องอธิบายว่าหมายความว่าอะไรในชีวิตจริง ไม่ใช่แค่ระบุค่า
Luna    → ปรับ Search Intent ให้ตอบคำถามที่คนค้นหาจริง ๆ วางโครงให้ครอบคลุม Buying Journey
Roxi    → เขียน Buyer Guide: เหมาะกับใคร ในบริบทอะไร ใครอาจไม่เหมาะ — กล้าพูดตรง ๆ
Vixi    → ฝัง CTA และ Affiliate อย่างเป็นธรรมชาติ ไม่ aggressive
Kiki    → ทำให้บทความอ่านเหมือนเพื่อนแนะนำ ไม่ใช่ AI เรียงข้อมูล ลบภาษาโรบอท
Speedy  → อ่านซ้ำ ตัดความซ้ำ ปรับ Flow ให้ลื่น ลดประโยคที่แข็งและเป็นทางการเกินไป

มาตรฐานที่ทีมยึดถือทุกบทความ:
1. ทุก Spec ต้องมี "ความหมาย" — เช่น "RAM 16GB เหมาะกับการเปิด Chrome 20 แท็บพร้อมกัน"
2. ต้องมี Buying Scenario ที่ชัด — คนซื้อสินค้านี้ไปใช้ทำอะไร ในบริบทไหน
3. ต้องบอกว่า "ใครเหมาะ" และ "ใครอาจไม่เหมาะ" อย่างตรงไปตรงมา
4. ห้ามรับประกันราคา ส่วนลด ดอกเบี้ย หรือรางวัล เพราะข้อมูลอาจเปลี่ยนได้
5. ห้ามสร้างข้อมูลที่ไม่ได้รับมา — ถ้าไม่รู้ให้บอกว่า "ขึ้นอยู่กับรุ่นและร้านค้า"
6. ภาษาไทยธรรมชาติ อ่านง่าย เหมือนเพื่อนแนะนำ ไม่ formal ไม่ใช่ภาษาโฆษณา"""


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def generate_article_content(
    keyword: str,
    category: str,
    products: list[dict],
) -> dict:
    """
    Generate full article prose. Returns same dict structure regardless of provider.

    Provider priority:
      1. Anthropic (real key only — must start with sk-ant-api and be >40 chars)
      2. OpenRouter (OPENROUTER_API_KEY)
      3. OpenAI (OPENAI_API_KEY)
      4. Deterministic (always available, data-driven, zero cost)
    """
    # 1. Anthropic — validate key is real, not a placeholder
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if (
        anthropic is not None
        and anthropic_key.startswith("sk-ant-api")
        and len(anthropic_key) > 40
    ):
        result = _call_claude(keyword, category, products, anthropic_key)
        if result["_success"]:
            return result

    # 2. OpenRouter
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter_key:
        result = _call_openrouter(keyword, category, products, openrouter_key)
        if result["_success"]:
            return result

    # 3. OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        result = _call_openai_provider(keyword, category, products, openai_key)
        if result["_success"]:
            return result

    # 4. Deterministic — always works
    return _deterministic_content(keyword, category, products)


# ---------------------------------------------------------------------------
# AI provider calls (shared prompt/response logic)
# ---------------------------------------------------------------------------

def _build_ai_prompt(keyword: str, category: str, products: list[dict]) -> str:
    cat_ctx = _CATEGORY_CONTEXT.get(category, {})
    contexts_str  = "、".join(cat_ctx.get("contexts", []))
    pain_str      = "、".join(cat_ctx.get("pain_points", []))
    use_cases_str = "、".join(cat_ctx.get("use_cases", []))
    product_brief = _build_product_brief(products)
    n = len(products)
    highlights_keys = ", ".join(f'"{i}"' for i in range(1, n + 1))

    return f"""\
หัวข้อบทความ: "{keyword}"
หมวดหมู่: {category}
จำนวนสินค้า: {n} รายการ

ข้อมูลสินค้าในบทความ:
{product_brief}

บริบทการซื้อที่เกี่ยวข้อง: {contexts_str or "ทั่วไป"}
ปัญหาที่ผู้ซื้อมักเจอ: {pain_str or "-"}
การใช้งานหลัก: {use_cases_str or "-"}

ทีม Editorial ต้องสร้างเนื้อหาบทความโดยตอบใน **JSON เท่านั้น** ตาม schema นี้:

{{
  "intro": "Nova เขียนย่อหน้าเปิด 3-5 ประโยค เปิดด้วย Context ไม่ใช่แค่ บทความนี้รวบรวม... ห้ามขึ้นต้นด้วยคุณ",
  "buying_scenario": "Luna เขียน 2-3 ย่อหน้า ว่าคนค้นหา {keyword!r} มักซื้อไปใช้ทำอะไร ในบริบทอะไร",
  "for_whom": "Roxi เขียน Markdown list 3-5 ข้อ ใคร + บริบท + ทำไมเหมาะ",
  "not_for_whom": "Roxi เขียน Markdown list 2-3 ข้อ บอกตรง ๆ ว่าใครอาจไม่เหมาะ",
  "buying_guide": "Roxi+Cipher+Luna เขียน 4-5 ย่อหน้า คำแนะนำการเลือกซื้อ แต่ละ factor อธิบายว่าสำคัญอย่างไรในชีวิตจริง",
  "product_highlights": {{{highlights_keys}: "Cipher+Roxi เขียน 1-2 ประโยคต่อสินค้า บอกว่าโดดเด่นอย่างไร เหมาะกับใคร ต้องมีครบทุก key จาก 1 ถึง {n}"}},
  "summary": "Speedy+Nova เขียนบทสรุป 3-4 ประโยค Practical Advice ช่วยตัดสินใจ ปิดด้วยคำแนะนำสุดท้าย"
}}

กฎเพิ่มเติม:
- ภาษาไทยธรรมชาติ อ่านลื่น เหมือนเพื่อนแนะนำ
- ห้ามระบุราคาหรือส่วนลดที่แน่นอนในส่วน prose
- ห้ามรับประกันผลลัพธ์หรือรางวัล
- product_highlights ต้องมีครบทุก key จาก "1" ถึง "{n}"
- ตอบ JSON เท่านั้น ไม่ต้องมี markdown code block"""


def _parse_ai_response(raw: str, model: str) -> dict:
    """Parse JSON from AI response, strip markdown fences."""
    raw = raw.strip()
    raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    data = json.loads(raw)

    highlights = data.get("product_highlights", {})
    if not isinstance(highlights, dict):
        highlights = {}
    data["product_highlights"] = {str(k): v for k, v in highlights.items()}
    data["_success"] = True
    data["_model"] = model
    return data


def _call_claude(keyword: str, category: str, products: list[dict], api_key: str) -> dict:
    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=EDITORIAL_MODEL,
            max_tokens=3500,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_ai_prompt(keyword, category, products)}],
        )
        return _parse_ai_response(msg.content[0].text, EDITORIAL_MODEL)
    except Exception as exc:
        return _error_result(str(exc), EDITORIAL_MODEL)


def _call_openrouter(keyword: str, category: str, products: list[dict], api_key: str) -> dict:
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        resp = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            max_tokens=3500,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_ai_prompt(keyword, category, products)},
            ],
        )
        return _parse_ai_response(resp.choices[0].message.content or "", OPENROUTER_MODEL)
    except ImportError:
        return _error_result("openai package not installed (needed for OpenRouter)", OPENROUTER_MODEL)
    except Exception as exc:
        return _error_result(str(exc), OPENROUTER_MODEL)


def _call_openai_provider(keyword: str, category: str, products: list[dict], api_key: str) -> dict:
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            max_tokens=3500,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_ai_prompt(keyword, category, products)},
            ],
        )
        return _parse_ai_response(resp.choices[0].message.content or "", model)
    except ImportError:
        return _error_result("openai package not installed", model)
    except Exception as exc:
        return _error_result(str(exc), model)


def _error_result(error: str, model: str) -> dict:
    return {
        "_success": False, "_error": error, "_model": model,
        "intro": "", "buying_scenario": "", "for_whom": "",
        "not_for_whom": "", "buying_guide": "", "product_highlights": {}, "summary": "",
    }


# ---------------------------------------------------------------------------
# Deterministic content engine — data-driven Thai content, zero API cost
# ---------------------------------------------------------------------------

_TITLE_FEATURES: list[tuple[list[str], str]] = [
    # Connectivity / power
    (["ไร้สาย", "wireless"], "ไร้สาย"),
    (["type-c", "type c", "usb-c", "usb c", "usbc"], "ชาร์จ USB-C"),
    (["ชาร์จเร็ว", "fast charge", "quick charge"], "ชาร์จเร็ว"),
    (["4000mah", "5000mah", "6000mah", "8000mah", "10000mah", "20000mah"], "แบตเตอรี่ความจุสูง"),
    (["แบตในตัว", "built-in battery", "in-built"], "แบตในตัว"),
    # Form factor / portability
    (["พกพา", "portable", "handheld"], "พกพาสะดวก"),
    (["มินิ", "mini"], "ขนาดมินิ"),
    (["พับได้", "foldable", "fold"], "พับเก็บได้"),
    (["หนีบ", "clip"], "หนีบติดได้"),
    # Fan / cooling features
    (["หมอกเย็น", "ไอเย็น", "mist", "ไอน้ำ"], "มีระบบหมอกเย็น"),
    (["100 ระดับ", "หลายระดับ", "หน้าจอสัมผัส", "touch"], "ปรับลมหลายระดับ"),
    (["เงียบ", "silent", "quiet"], "เงียบขณะใช้งาน"),
    # Protection
    (["กันน้ำ", "waterproof", "ipx"], "กันน้ำ"),
    (["กันน้ำกันเหงื่อ", "ไม่ตกร่อง", "ไม่หลุด"], "กันน้ำกันเหงื่อ"),
    # Photography / selfie
    (["3 in1", "3in1", "fish eye", "wide angle", "macro"], "เลนส์ครบชุด"),
    (["magsafe", "magnetic", "แม่เหล็ก"], "ติดแม่เหล็กได้"),
    (["360°", "360 °", "หมุน 360", "rotate 360"], "หมุน 360°"),
    # Beauty / cosmetics
    (["ติดทนนาน", "ทนนาน", "long lasting", "16ชม", "24ชม", "12ชม", "ติดทน"], "ติดทนนาน"),
    (["แมท", "matte", "แมตต์", "เนื้อแมท", "แมทติดทน"], "เนื้อแมท"),
    (["spf", "กันแดด uv", "pa++++", "pa+++"], "ป้องกันแสงแดด"),
    (["สีพาสเทล", "pastel", "หลายสี", "หลายเฉดสี"], "มีให้เลือกหลายสี"),
    # Health supplements
    (["collagen", "คอลลาเจน"], "มีคอลลาเจน"),
    (["coq10", "โคคิว", "coenzyme"], "มี CoQ10"),
    (["50+", "silver 50", "สูงอายุ"], "สำหรับอายุ 50+"),
    (["สตรี", "ferti w", "สำหรับผู้หญิง", "for women"], "สูตรสำหรับผู้หญิง"),
    (["multivitamin", "วิตามิน 14", "วิตามิน 12", "วิตามิน 13"], "วิตามินหลายชนิด"),
    # Home fragrance / living
    (["ก้านไม้หอม", "reed diffuser", "ก้านหอม"], "แบบก้านไม้"),
    (["60วัน", "90วัน", "60 วัน", "90 วัน", "หอมนาน"], "หอมนาน"),
    (["กลิ่นโรงแรม", "กลิ่นหรู", "luxury scent"], "กลิ่นระดับโรงแรม"),
    # Camping / outdoor
    (["รับน้ำหนัก 300", "รับน้ำหนัก300", "รับน้ำหนัก200", "รับน้ำหนัก 200"], "รับน้ำหนักสูง"),
    (["อลูมิเนียม", "aluminium", "aluminum"], "โครงอลูมิเนียม"),
]

# ---------------------------------------------------------------------------
# Category-scoped feature situations (intro sentence context)
# ---------------------------------------------------------------------------

_CAT_FEATURE_SITUATIONS: dict[str, dict[str, str]] = {
    "mobile-gadgets": {
        "พกพาสะดวก":     "พกใช้งานนอกบ้านหรือระหว่างเดินทาง",
        "ขนาดมินิ":       "ใส่กระเป๋าได้ ใช้งานได้ทุกที่",
        "ติดแม่เหล็กได้":  "ต่อเข้า MagSafe ได้ทันที ไม่ต้องแคลมป์หรือคลิป",
        "หมุน 360°":      "ปรับมุมกล้องได้ทุกทิศ เหมาะกับ vlog และ live",
        "ไร้สาย":         "ใช้รีโมตชัตเตอร์หรือเชื่อมต่อโดยไม่ต้องต่อสาย",
        "ชาร์จ USB-C":    "ชาร์จร่วมกับโทรศัพท์ได้เลย",
    },
    "sports": {
        "พกพาสะดวก":    "พกไปแคมป์ ปิคนิค เดินป่า หรือริมน้ำ",
        "พับเก็บได้":    "เก็บท้ายรถหรือเต็นท์ได้ ไม่กินพื้นที่",
        "รับน้ำหนักสูง":  "รองรับน้ำหนักได้มาก นั่งได้นานหลายชั่วโมง",
        "โครงอลูมิเนียม": "เบาแต่แข็งแรง เหมาะกับเดินป่าหรือพกระยะไกล",
        "กันน้ำ":         "ใช้งานได้แม้ฝนตกหรืออากาศชื้น",
    },
    "beauty": {
        "ติดทนนาน":      "ใช้งานได้ตลอดวันโดยไม่ต้องแต้มซ้ำบ่อย",
        "เนื้อแมท":       "ปากไม่มัน สีชัด ดูสะอาดตลอดวัน",
        "ป้องกันแสงแดด":  "ออกแดดได้โดยไม่ต้องกังวลเรื่อง UV",
        "กันน้ำกันเหงื่อ": "ใส่ได้แม้อากาศร้อนหรือวันที่ออกกำลังกาย",
        "มีให้เลือกหลายสี": "เลือกสีให้เข้ากับผิวหรือ outfit ได้",
    },
    "health": {
        "มีคอลลาเจน":        "บำรุงข้อต่อและผิวพรรณไปพร้อมกัน",
        "มี CoQ10":           "ให้พลังงานระดับเซลล์และต้านอนุมูลอิสระ",
        "สำหรับอายุ 50+":     "ออกแบบมาสำหรับความต้องการของร่างกายช่วงอายุ 50 ขึ้นไป",
        "สูตรสำหรับผู้หญิง":  "มีส่วนผสมที่ตอบโจทย์เฉพาะสำหรับผู้หญิง",
        "วิตามินหลายชนิด":   "ครอบคลุมวิตามินและแร่ธาตุหลายชนิดในเม็ดเดียว",
    },
    "home-living": {
        "แบบก้านไม้":         "กระจายกลิ่นช้าๆ ต่อเนื่อง เหมาะกับห้องนอนหรือห้องนั่งเล่น",
        "หอมนาน":             "ใช้งานได้นานโดยไม่ต้องเติมบ่อย",
        "กลิ่นระดับโรงแรม":   "ให้บรรยากาศเหมือนโรงแรมหรูในบ้าน",
    },
}

# Category-scoped buyer intent for for_whom bullets
_CAT_FEATURE_FOR_WHOM: dict[str, dict[str, str]] = {
    "mobile-gadgets": {
        "พกพาสะดวก":     "พกใช้งานนอกบ้านหรือระหว่างเดินทาง",
        "ขนาดมินิ":       "ใส่กระเป๋าได้ ไม่หนักมือขณะถือนาน",
        "ติดแม่เหล็กได้":  "ใช้กับมือถือ MagSafe ได้ทันทีโดยไม่ต้องคลิป",
        "หมุน 360°":      "ถ่ายวิดีโอ vlog หรือ live แบบหมุนติดตามได้",
        "ไร้สาย":         "ใช้งานโดยไม่ต้องต่อสายหรือหาปลั๊ก",
        "ชาร์จ USB-C":    "ชาร์จร่วมกับโทรศัพท์ ไม่ต้องพกสายพิเศษ",
    },
    "sports": {
        "พกพาสะดวก":    "ต้องการพกไปแคมป์ ปิคนิค เดินป่า หรือเล่นริมน้ำ",
        "พับเก็บได้":    "เก็บท้ายรถหรือใส่เป้ได้ง่าย ไม่เกะกะ",
        "รับน้ำหนักสูง":  "คนน้ำหนักมาก หรือต้องการนั่งนานหลายชั่วโมง",
        "โครงอลูมิเนียม": "ต้องการเก้าอี้เบาแต่แข็งแรงสำหรับเดินป่า",
        "กันน้ำ":         "ใช้ในสภาพอากาศเปียกชื้นหรือกลางแจ้ง",
    },
    "beauty": {
        "ติดทนนาน":      "ต้องการสีปากที่ติดทนตลอดวัน ไม่ต้องแต้มซ้ำบ่อย",
        "เนื้อแมท":       "ชอบเนื้อลิปแห้งแมท สีชัด ดูสะอาดตลอดวัน",
        "ป้องกันแสงแดด":  "ออกแดดบ่อยหรือต้องการ SPF รวมอยู่ในขั้นตอนเดียว",
        "กันน้ำกันเหงื่อ": "ทนเหงื่อ ฝน หรืออากาศร้อนชื้น",
        "มีให้เลือกหลายสี": "ต้องการเลือกสีหลายเฉดสำหรับ look ที่หลากหลาย",
    },
    "health": {
        "มีคอลลาเจน":        "ต้องการบำรุงข้อและผิวพรรณไปพร้อมกัน",
        "มี CoQ10":           "ต้องการสารต้านอนุมูลอิสระควบคู่กับวิตามินรวม",
        "สำหรับอายุ 50+":     "วัย 50 ขึ้นไปที่ต้องการวิตามินเฉพาะสำหรับช่วงอายุนี้",
        "สูตรสำหรับผู้หญิง":  "ผู้หญิงที่ต้องการวิตามินที่ออกแบบมาสำหรับเพศหญิงโดยเฉพาะ",
        "วิตามินหลายชนิด":   "ต้องการวิตามินครบถ้วนในเม็ดเดียว ไม่ต้องกินหลายชนิด",
    },
    "home-living": {
        "แบบก้านไม้":         "ต้องการกระจายกลิ่นต่อเนื่องโดยไม่ต้องจุดเทียนหรือฉีดสเปรย์",
        "หอมนาน":             "ต้องการกลิ่นหอมในบ้านโดยไม่ต้องเปลี่ยนบ่อย",
        "กลิ่นระดับโรงแรม":   "ต้องการบรรยากาศห้องพักโรงแรมในบ้านตัวเอง",
    },
}


def _title_features(title: str) -> list[str]:
    t = title.lower()
    return [label for kws, label in _TITLE_FEATURES if any(kw in t for kw in kws)][:2]


def _safe_int(val) -> int:
    try:
        return int(float(val or 0))
    except (TypeError, ValueError):
        return 0


def _safe_float(val) -> float:
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _price_stats(products: list[dict]) -> dict:
    prices = [_safe_float(p.get("sale_price")) for p in products if p.get("sale_price")]
    if not prices:
        return {"min": 0, "max": 0, "avg": 0, "has_range": False}
    return {
        "min": int(min(prices)),
        "max": int(max(prices)),
        "avg": int(sum(prices) / len(prices)),
        "has_range": (max(prices) - min(prices)) > 50,
    }


def _rank_products(products: list[dict]) -> dict[str, tuple[dict, int]]:
    """Return notable products by category. Values are (product, 0-based-index)."""
    if not products:
        return {}

    def _idx_of_max(key: str, reverse: bool = True) -> tuple[dict, int]:
        best_i = 0
        best_v = _safe_float(products[0].get(key))
        for i, p in enumerate(products):
            v = _safe_float(p.get(key))
            if (reverse and v > best_v) or (not reverse and v < best_v):
                best_v, best_i = v, i
        return products[best_i], best_i

    def _idx_of_price(reverse: bool) -> tuple[dict, int]:
        candidates = [(i, p) for i, p in enumerate(products) if p.get("sale_price")]
        if not candidates:
            return products[0], 0
        best_i, best_p = min(
            candidates,
            key=lambda t: _safe_float(t[1].get("sale_price")) * (-1 if reverse else 1),
        )
        return best_p, best_i

    return {
        "sold_leader":   _idx_of_max("item_sold"),
        "rating_leader": _idx_of_max("item_rating"),
        "cheapest":      _idx_of_price(reverse=False),
        "premium":       _idx_of_price(reverse=True),
    }


def _det_highlights(products: list[dict]) -> dict[str, str]:
    if not products:
        return {}

    ranks = _rank_products(products)
    sold_idx   = ranks["sold_leader"][1]   if "sold_leader"   in ranks else -1
    rating_idx = ranks["rating_leader"][1] if "rating_leader" in ranks else -1
    cheap_idx  = ranks["cheapest"][1]      if "cheapest"      in ranks else -1
    premium_idx = ranks["premium"][1]      if "premium"       in ranks else -1

    used: set[int] = set()
    highlights: dict[str, str] = {}

    for i, p in enumerate(products, 1):
        idx = i - 1
        feat = _title_features(str(p.get("title", "")))
        feat_str = "、".join(feat)
        sold   = _safe_int(p.get("item_sold"))
        rating = _safe_float(p.get("item_rating"))
        price  = _safe_int(p.get("sale_price"))

        if idx == sold_idx and sold > 100 and idx not in used:
            used.add(idx)
            highlights[str(i)] = (
                f"ขายดีที่สุดในกลุ่ม ยอดขาย {sold:,} ชิ้น"
                + (f" • {feat_str}" if feat_str else "")
                + " — เป็นตัวเลือกที่ผ่านการพิสูจน์จากผู้ซื้อจริงมากที่สุด"
            )
        elif idx == rating_idx and rating >= 4.8 and idx not in used:
            used.add(idx)
            highlights[str(i)] = (
                f"คะแนนรีวิวสูงสุดในกลุ่ม {rating:.1f} ⭐"
                + (f" • {feat_str}" if feat_str else "")
                + (f" ราคา ฿{price:,}" if price else "")
            )
        elif idx == cheap_idx and idx not in used and cheap_idx != sold_idx:
            used.add(idx)
            highlights[str(i)] = (
                f"ราคาประหยัดที่สุดในกลุ่ม ฿{price:,}"
                + (f" • {feat_str}" if feat_str else "")
                + " — เหมาะสำหรับผู้ที่ต้องการทดลองก่อนลงทุนรุ่นสูง"
            )
        elif idx == premium_idx and idx not in used and premium_idx not in {sold_idx, rating_idx, cheap_idx}:
            used.add(idx)
            highlights[str(i)] = (
                f"ตัวเลือกระดับพรีเมียมในกลุ่ม ฿{price:,}"
                + (f" • {feat_str}" if feat_str else "")
                + f" คะแนน {rating:.1f} ⭐ สำหรับคนที่เน้นคุณภาพ"
            )
        else:
            parts: list[str] = []
            if feat_str:
                parts.append(feat_str)
            if sold > 300:
                parts.append(f"ผู้ซื้อ {sold:,} ราย")
            if rating >= 4.7:
                parts.append(f"คะแนน {rating:.1f} ⭐")
            if price:
                parts.append(f"฿{price:,}")
            highlights[str(i)] = " • ".join(parts) if parts else f"ราคา ฿{price:,} คะแนน {rating:.1f} ⭐"

    return highlights


# Generic feature situations — used when no category-scoped entry exists
_FEATURE_SITUATIONS: dict[str, str] = {
    "พกพาสะดวก":          "พกพาใช้งานนอกบ้านหรือระหว่างเดินทาง",
    "ขนาดมินิ":            "ใช้ได้ทุกที่โดยไม่เปลืองพื้นที่",
    "ไร้สาย":              "ใช้งานได้ทุกที่โดยไม่ต้องหาปลั๊กไฟ",
    "ชาร์จ USB-C":         "ชาร์จร่วมกับโทรศัพท์ได้เลย",
    "มีระบบหมอกเย็น":      "ต้องการทั้งลมเย็นและความชื้นในอากาศ",
    "ปรับลมหลายระดับ":     "ปรับลมแรง-เบาได้ตามต้องการ",
    "เงียบขณะใช้งาน":      "ห้องทำงานหรือห้องนอน",
    "หนีบติดได้":           "หนีบขอบโต๊ะหรือรถเข็นได้สะดวก",
    "แบตเตอรี่ความจุสูง":   "ใช้งานต่อเนื่องได้นานโดยไม่ต้องชาร์จบ่อย",
    "ชาร์จเร็ว":            "ชาร์จเสร็จเร็วพร้อมใช้ทันที",
    "กันน้ำ":               "ใช้ได้แม้ในที่ชื้นหรือระหว่างออกกำลังกาย",
    "พับเก็บได้":           "เก็บง่าย ไม่กินพื้นที่",
    "โครงอลูมิเนียม":       "เบาแต่แข็งแรง",
    "ติดทนนาน":            "ใช้งานได้ตลอดวัน",
    "เนื้อแมท":             "สีชัด ปากไม่มัน",
    "ป้องกันแสงแดด":        "ออกแดดได้ปลอดภัยขึ้น",
    "มีคอลลาเจน":           "บำรุงข้อและผิวพรรณ",
    "มี CoQ10":             "ต้านอนุมูลอิสระ",
    "แบบก้านไม้":           "กระจายกลิ่นต่อเนื่องในห้อง",
    "หอมนาน":              "ใช้งานได้นานโดยไม่ต้องเติมบ่อย",
}

# Generic buyer intent — used when no category-scoped entry exists
_FEATURE_FOR_WHOM: dict[str, str] = {
    "เงียบขณะใช้งาน":      "ใช้ในห้องทำงานหรือห้องนอนโดยไม่รบกวนการประชุมหรือการนอน",
    "พกพาสะดวก":           "พกพาติดตัวไปทำงานหรือเดินทาง",
    "ขนาดมินิ":             "ใส่กระเป๋าได้ ใช้พื้นที่น้อย",
    "ไร้สาย":               "ใช้งานโดยไม่ต้องหาปลั๊กหรือสายพ่วง",
    "ชาร์จ USB-C":          "ชาร์จร่วมกับโทรศัพท์ได้ ไม่ต้องพกสายพิเศษ",
    "มีระบบหมอกเย็น":       "ต้องการทั้งลมเย็นและความชื้นช่วงอากาศร้อนแห้ง",
    "ปรับลมหลายระดับ":      "ต้องการควบคุมความแรงลมได้ละเอียด",
    "หนีบติดได้":            "ต้องการติดตั้งโดยไม่ต้องวางบนโต๊ะ",
    "แบตเตอรี่ความจุสูง":    "ต้องการใช้งานต่อเนื่องนานหลายชั่วโมง",
    "ชาร์จเร็ว":             "ต้องการเติมแบตเตอรี่ได้เร็ว",
    "กันน้ำ":                "ใช้งานในที่ชื้นหรือระหว่างออกกำลังกาย",
    "พับเก็บได้":            "ต้องการเก็บสะดวก ไม่กินพื้นที่",
    "โครงอลูมิเนียม":        "ต้องการน้ำหนักเบาแต่แข็งแรง",
    "ติดทนนาน":             "ต้องการสีหรือผลลัพธ์ที่ติดทนตลอดวัน",
    "เนื้อแมท":              "ชอบเนื้อสัมผัสแห้งแมท ไม่มัน",
    "ป้องกันแสงแดด":         "ออกแดดบ่อยหรือต้องการ SPF ในผลิตภัณฑ์เดียว",
    "มีคอลลาเจน":            "ต้องการบำรุงข้อและผิวพรรณ",
    "มี CoQ10":              "ต้องการสารต้านอนุมูลอิสระเพิ่มเติม",
    "แบบก้านไม้":            "ต้องการกลิ่นหอมต่อเนื่องในห้องโดยไม่ต้องจุดเทียน",
    "หอมนาน":               "ต้องการกลิ่นหอมในบ้านโดยไม่ต้องเปลี่ยนบ่อย",
}


def _feature_situation(feature: str, category: str) -> str:
    """Return category-scoped situation text, fall back to generic."""
    return (
        _CAT_FEATURE_SITUATIONS.get(category, {}).get(feature)
        or _FEATURE_SITUATIONS.get(feature, "")
    )


def _feature_for_whom_text(feature: str, category: str) -> str:
    """Return category-scoped buyer intent text, fall back to generic."""
    return (
        _CAT_FEATURE_FOR_WHOM.get(category, {}).get(feature)
        or _FEATURE_FOR_WHOM.get(feature, f"ต้องการ{feature}")
    )


def _premium_descriptor(product: dict, category: str) -> str:
    """Return a grounded descriptor for the premium product. Empty string → skip bullet."""
    title = str(product.get("title", ""))
    title_lo = title.lower()

    if category == "health":
        m = re.search(r'(\d+)\s*ชนิด', title)
        if m:
            return f"วิตามิน {m.group(1)} ชนิด"
        for pattern, desc in [
            (r'coq10|โคคิว',                 "มี CoQ10"),
            (r'collagen|คอลลาเจน',           "มีคอลลาเจน"),
            (r'50\+|silver',                  "สำหรับอายุ 50+"),
            (r'สตรี|ferti\s*w|สำหรับผู้หญิง', "สูตรสำหรับผู้หญิง"),
        ]:
            if re.search(pattern, title_lo):
                return desc

    if category == "home-living":
        m = re.search(r'(\d+)\s*ml', title_lo)
        if m and int(m.group(1)) >= 100:
            return f"ปริมาณ {m.group(1)} ml"
        if re.search(r'60\s*วัน|90\s*วัน', title):
            return "หอมได้นานถึง 60–90 วัน"
        if re.search(r'premium|luxury|หรู', title_lo):
            return "กลิ่นระดับพรีเมียม"

    if category == "beauty":
        m = re.search(r'spf\s*(\d+)', title_lo)
        if m:
            return f"SPF {m.group(1)}"
        if re.search(r'pa\+{3,4}', title_lo):
            return "PA++++ ป้องกัน UVA สูงสุด"
        if re.search(r'แพ็กคู่|ซื้อ 1 แถม 1|2 ขวด|2 ชิ้น', title_lo):
            return "มาแบบ 2 ชิ้น คุ้มกว่า"
        if re.search(r'ติดทนนาน|ทนนาน|16ชม|24ชม', title_lo):
            return "ติดทนนานกว่า"

    if category in ("camping", "sports"):
        m = re.search(r'รับน้ำหนัก\s*(\d+)', title)
        if m:
            return f"รับน้ำหนักได้ {m.group(1)} กก."
        if re.search(r'ชุดโต๊ะ|โต๊ะ.*เก้าอี้|เก้าอี้.*โต๊ะ', title):
            return "เป็นชุดโต๊ะและเก้าอี้"
        if re.search(r'อลูมิเนียม|alumin', title_lo):
            return "โครงอลูมิเนียม เบาแต่แข็งแรง"

    if category == "mobile-gadgets":
        m = re.search(r'(\d+\.?\d*)\s*ม\b|(\d+\.?\d*)\s*(?:m|metre)\b', title_lo)
        if m:
            length = m.group(1) or m.group(2)
            return f"ยาว {length} เมตร ถ่ายได้ในระยะไกล"
        if re.search(r'magsafe|แม่เหล็ก|magnetic', title_lo):
            return "รองรับ MagSafe"
        if re.search(r'\bled\b|ไฟ led', title_lo):
            return "มีไฟ LED เสริม"

    # Generic: fall back to first detected feature
    feats = _title_features(title)
    if feats:
        return f"มาพร้อม{feats[0]}"

    return ""  # No grounded descriptor → caller should skip premium bullet


def _det_intro(keyword: str, products: list[dict], cat_ctx: dict, category: str = "") -> str:
    stats = _price_stats(products)
    n = len(products)

    all_features: list[str] = []
    for p in products:
        all_features.extend(_title_features(str(p.get("title", ""))))
    unique_features = list(dict.fromkeys(all_features))

    ranks = _rank_products(products)
    sold_p = ranks.get("sold_leader", (None, 0))[0]

    # Category-scoped feature situations
    situations = [
        (f, _feature_situation(f, category))
        for f in unique_features
        if _feature_situation(f, category)
    ]

    if situations and stats["has_range"] and stats["min"] > 0:
        if len(situations) >= 2:
            feat_text = (
                f"ทั้งรุ่นที่{situations[0][0]}สำหรับ{situations[0][1]} "
                f"และรุ่น{situations[1][0]}สำหรับ{situations[1][1]}"
            )
        else:
            feat_text = f"รุ่นที่{situations[0][0]}สำหรับ{situations[0][1]}"
        opener = (
            f"ถ้ากำลังมองหา {keyword} ในงบ ฿{stats['min']:,}–฿{stats['max']:,} "
            f"มีตัวเลือกหลายแบบ {feat_text}"
        )
    elif stats["has_range"] and stats["min"] > 0:
        opener = (
            f"ถ้ากำลังมองหา {keyword} ราคาในกลุ่มนี้อยู่ระหว่าง "
            f"฿{stats['min']:,}–฿{stats['max']:,} มีหลายแบบให้เลือก"
        )
    else:
        opener = f"สำหรับ {keyword} มีตัวเลือกหลายแบบในฐานข้อมูลนี้"

    body = (
        f"บทความนี้คัดมา {n} ตัวเลือกจากข้อมูลยอดขายและคะแนนรีวิวจริงบน Shopee "
        f"เพื่อช่วยเปรียบเทียบก่อนตัดสินใจ"
    )

    sold_note = ""
    if sold_p:
        sold = _safe_int(sold_p.get("item_sold"))
        if sold > 500:
            sold_note = f"ตัวเลือกที่ขายดีสุดในกลุ่มมียอดขายแล้วกว่า {sold:,} ชิ้น"

    return " ".join(filter(None, [opener, body, sold_note]))


def _det_buying_scenario(keyword: str, products: list[dict], cat_ctx: dict) -> str:
    pain_points = cat_ctx.get("pain_points", [])
    stats = _price_stats(products)

    # Derive segments from price + product features rather than category use_cases
    ranks = _rank_products(products)
    sold_p  = ranks.get("sold_leader", (None,))[0]
    cheap_p = ranks.get("cheapest", (None,))[0]

    sold_note = ""
    if sold_p:
        sold = _safe_int(sold_p.get("item_sold"))
        sold_name = str(sold_p.get("title", ""))[:25]
        if sold > 500:
            sold_note = f" สินค้าที่ผู้ซื้อเลือกมากที่สุดคือ '{sold_name}' ด้วยยอดขาย {sold:,} ชิ้น"

    range_note = ""
    if stats["has_range"] and stats["min"] > 0:
        range_note = (
            f" งบประมาณในกลุ่มนี้เริ่มต้นที่ ฿{stats['min']:,} สำหรับตัวเลือกพื้นฐาน "
            f"และขึ้นไปถึง ฿{stats['max']:,} สำหรับรุ่นที่มีฟีเจอร์เพิ่มขึ้น"
        )

    para1 = (
        f"คนที่ค้นหา {keyword} ส่วนใหญ่กำลังเปรียบเทียบตัวเลือกก่อนตัดสินใจ "
        f"ไม่ว่าจะเป็นการซื้อครั้งแรกหรือเปลี่ยนจากรุ่นเดิมที่ใช้อยู่"
        + range_note
        + sold_note
    )

    para2 = (
        f"สินค้าทุกรายการในบทความนี้คัดกรองจากยอดขายจริงและคะแนนรีวิวจากผู้ซื้อ "
        f"สินค้าที่มีคะแนน 4.8 ขึ้นไปและยอดขายสูงมักผ่านการทดสอบจากผู้ใช้จริงมาแล้ว "
        f"ซึ่งช่วยลดความเสี่ยงในการซื้อผิดได้มาก"
    )

    return f"{para1}\n\n{para2}"


def _det_for_whom(keyword: str, products: list[dict], cat_ctx: dict, category: str = "") -> str:
    stats = _price_stats(products)
    ranks = _rank_products(products)

    cheap_entry   = ranks.get("cheapest",    (None, 0))
    sold_entry    = ranks.get("sold_leader", (None, 0))
    premium_entry = ranks.get("premium",     (None, 0))

    cheap_p,   cheap_idx   = cheap_entry
    sold_p,    sold_idx    = sold_entry
    premium_p, premium_idx = premium_entry

    def _short(p: dict, chars: int = 18) -> str:
        t = str(p.get("title", ""))
        return t[:chars] + "..." if len(t) > chars else t

    items: list[str] = []
    mentioned_idxs: set[int] = set()

    # Build feature → (first product with that feature, 1-based rank)
    feature_product_map: dict[str, tuple[dict, int]] = {}
    for i, p in enumerate(products):
        for feat in _title_features(str(p.get("title", ""))):
            if feat not in feature_product_map:
                feature_product_map[feat] = (p, i + 1)

    # Slot 1: Budget buyer (cheapest, or cheapest+sold if same product)
    if cheap_p:
        cp = _safe_int(cheap_p.get("sale_price"))
        cr = cheap_idx + 1
        if cheap_idx == sold_idx and sold_p:
            sold = _safe_int(sold_p.get("item_sold"))
            items.append(
                f"- **คนที่เน้นประหยัดหรืออยากลองก่อน** — "
                f"สินค้า #{cr} ราคา ฿{cp:,} เป็นทั้งตัวถูกสุดและขายดีสุดในกลุ่ม ({sold:,} ชิ้น)"
            )
        else:
            items.append(
                f"- **คนที่เน้นประหยัดหรืออยากลองก่อน** — "
                f"สินค้า #{cr} ({_short(cheap_p)}) ราคา ฿{cp:,}"
            )
        mentioned_idxs.add(cheap_idx)

    # Slot 2: Sold leader — always present if different from cheapest
    if sold_p and sold_idx not in mentioned_idxs:
        sold = _safe_int(sold_p.get("item_sold"))
        sr = sold_idx + 1
        items.append(
            f"- **คนที่ให้ความสำคัญกับตัวเลือกที่มีผู้ซื้อจำนวนมาก** — "
            f"สินค้า #{sr} ({_short(sold_p)}) มียอดขายกว่า {sold:,} ชิ้น "
            f"ซึ่งเป็นสัญญาณว่ามีผู้ใช้จริงจำนวนมาก"
        )
        mentioned_idxs.add(sold_idx)

    # Slot 3+: Feature-based bullets (category-scoped text)
    feat_count = 0
    for feat, (feat_p, feat_rank) in feature_product_map.items():
        if feat_count >= 2:
            break
        feat_idx = feat_rank - 1
        if feat_idx in mentioned_idxs:
            continue
        usage = _feature_for_whom_text(feat, category)
        price = _safe_int(feat_p.get("sale_price"))
        items.append(
            f"- **คนที่{usage}** — "
            f"สินค้า #{feat_rank} ({_short(feat_p)}) ฿{price:,}"
        )
        mentioned_idxs.add(feat_idx)
        feat_count += 1

    # Slot last: Premium buyer — only when a grounded descriptor exists
    if premium_p and premium_idx not in mentioned_idxs and stats["has_range"]:
        desc = _premium_descriptor(premium_p, category)
        if desc:
            pp = _safe_int(premium_p.get("sale_price"))
            pr = premium_idx + 1
            items.append(
                f"- **คนที่งบมากขึ้น** — "
                f"สินค้า #{pr} ({_short(premium_p)}) ฿{pp:,} {desc}"
            )
            mentioned_idxs.add(premium_idx)

    if not items:
        items = [
            f"- ผู้ที่ต้องการ {keyword} สำหรับการใช้งานทั่วไป",
            f"- คนที่ต้องการเปรียบเทียบตัวเลือกก่อนตัดสินใจ",
        ]

    return "\n".join(items[:5])


def _det_not_for_whom(keyword: str, products: list[dict], cat_ctx: dict) -> str:
    stats = _price_stats(products)
    pain_points = cat_ctx.get("pain_points", [])

    items: list[str] = []

    if stats["max"] > 0:
        items.append(
            f"- **คนที่ต้องการสินค้าระดับสูงกว่า ฿{stats['max']:,}** — "
            f"ควรมองในกลุ่มราคาที่สูงขึ้น เพื่อให้ได้ฟีเจอร์และความทนทานที่ดีกว่า"
        )

    if pain_points:
        items.append(
            f"- **คนที่มีปัญหาเฉพาะเรื่อง {pain_points[0]} แบบจริงจัง** — "
            f"อาจต้องพิจารณาสินค้าเฉพาะทางหรืองบที่สูงกว่า"
        )

    items.append(
        f"- **คนที่ต้องการใช้งานระดับพาณิชย์หรือมืออาชีพ** — "
        f"สินค้าในกลุ่มนี้เน้นการใช้งานทั่วไป ไม่ได้ออกแบบมาสำหรับงานหนักระยะยาว"
    )

    return "\n".join(items[:3])


def _det_buying_guide(keyword: str, products: list[dict], cat_ctx: dict) -> str:
    pain_points = cat_ctx.get("pain_points", [])
    stats = _price_stats(products)

    all_features: list[str] = []
    for p in products:
        all_features.extend(_title_features(str(p.get("title", ""))))
    unique_features = list(dict.fromkeys(all_features))[:3]

    paras: list[str] = []

    feat_ctx = f"เช่น {', '.join(unique_features)}" if unique_features else ""
    paras.append(
        f"ก่อนซื้อ {keyword} ควรระบุให้ชัดว่าต้องการฟีเจอร์อะไร {feat_ctx} "
        f"เพราะสินค้าในระดับราคาเดียวกันอาจมีฟีเจอร์ที่แตกต่างกันมาก "
        f"การรู้ว่าต้องการอะไรช่วยตัดตัวเลือกที่ไม่ตอบโจทย์ออกได้เลย"
    )

    paras.append(
        f"คะแนนรีวิวและยอดขายเป็นตัวกรองที่น่าเชื่อถือที่สุดสำหรับสินค้าบน Shopee "
        f"สินค้าที่มีคะแนน 4.8 ขึ้นไปและยอดขายเกิน 500 ชิ้นผ่านการทดสอบจากผู้ซื้อจริงมาแล้ว "
        f"อ่านรีวิวล่าสุดเพื่อตรวจสอบปัญหาที่ผู้ซื้อพบจริง เพราะ spec บนหน้าสินค้าอาจไม่ครอบคลุมทุกกรณีใช้งาน"
    )

    if stats["has_range"] and stats["min"] > 0:
        feat_extra = f"เช่น {', '.join(unique_features)}" if unique_features else ""
        paras.append(
            f"งบ ฿{stats['min']:,}–{stats['avg']:,} เหมาะสำหรับการใช้งานพื้นฐาน "
            f"ขณะที่งบ ฿{stats['avg']:,}–{stats['max']:,} มักให้ฟีเจอร์เพิ่มขึ้น {feat_extra} "
            f"ที่ตอบโจทย์การใช้งานหนักหรือบ่อยครั้งขึ้น"
        )

    paras.append(
        "ก่อนกดซื้อ แนะนำอ่านรีวิวที่มีรูปประกอบและรีวิวล่าสุดก่อน "
        "เพราะ spec และคุณภาพของรุ่นเดียวกันอาจมีการเปลี่ยนแปลงโดยที่ชื่อสินค้าไม่เปลี่ยน "
        "และตรวจสอบว่าร้านค้ามีคะแนนร้านสูงพร้อมนโยบายคืนสินค้าที่ชัดเจน"
    )

    return "\n\n".join(paras)


def _det_summary(keyword: str, products: list[dict], category: str = "") -> str:
    ranks = _rank_products(products)
    sold_entry  = ranks.get("sold_leader", (None, 0))
    cheap_entry = ranks.get("cheapest",    (None, 0))
    prem_entry  = ranks.get("premium",     (None, 0))
    sold_p,  sold_idx  = sold_entry
    cheap_p, cheap_idx = cheap_entry
    prem_p,  prem_idx  = prem_entry

    parts: list[str] = []
    mentioned_idxs: set[int] = set()

    if sold_p:
        sold       = _safe_int(sold_p.get("item_sold"))
        sold_price = _safe_int(sold_p.get("sale_price"))
        sold_rank  = sold_idx + 1
        if sold_idx == cheap_idx:
            parts.append(
                f"สินค้า #{sold_rank} ราคา ฿{sold_price:,} เป็นทั้งตัวเลือกที่ราคาต่ำสุดในกลุ่ม "
                f"และขายดีสุดด้วยยอดขายกว่า {sold:,} ชิ้น — น่าสนใจสำหรับคนที่เพิ่งเริ่มใช้"
            )
        else:
            if cheap_p:
                cp        = _safe_int(cheap_p.get("sale_price"))
                cheap_rank = cheap_idx + 1
                parts.append(f"ถ้างบจำกัด สินค้า #{cheap_rank} ราคา ฿{cp:,} เป็นจุดเริ่มต้นที่คุ้มค่า")
                mentioned_idxs.add(cheap_idx)
            parts.append(
                f"ถ้าเน้นสินค้าผ่านการพิสูจน์ สินค้า #{sold_rank} ขายแล้ว {sold:,} ชิ้น "
                f"เป็นตัวเลือกที่ผู้ซื้อไว้วางใจมากที่สุดในกลุ่ม"
            )
        mentioned_idxs.add(sold_idx)

    if prem_p and prem_idx not in mentioned_idxs:
        pp        = _safe_int(prem_p.get("sale_price"))
        prem_rank = prem_idx + 1
        desc = _premium_descriptor(prem_p, category)
        if desc:
            parts.append(
                f"คนที่งบมากขึ้น สินค้า #{prem_rank} ฿{pp:,} {desc}"
            )
            mentioned_idxs.add(prem_idx)

    parts.append("ราคาบน Shopee เปลี่ยนตาม Flash Sale ควรตรวจราคาและคูปองล่าสุดก่อนสั่งซื้อ")
    return " ".join(parts)


def _deterministic_content(
    keyword: str,
    category: str,
    products: list[dict],
) -> dict:
    """Data-driven Thai content from product data. No API required."""
    cat_ctx = _CATEGORY_CONTEXT.get(category, {})
    try:
        return {
            "intro":               _det_intro(keyword, products, cat_ctx, category),
            "buying_scenario":     _det_buying_scenario(keyword, products, cat_ctx),
            "for_whom":            _det_for_whom(keyword, products, cat_ctx, category),
            "not_for_whom":        _det_not_for_whom(keyword, products, cat_ctx),
            "buying_guide":        _det_buying_guide(keyword, products, cat_ctx),
            "product_highlights":  _det_highlights(products),
            "summary":             _det_summary(keyword, products, category),
            "_success":            True,
            "_model":              "deterministic",
        }
    except Exception as exc:
        return _error_result(str(exc), "deterministic")


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _build_product_brief(products: list[dict]) -> str:
    """Concise product list to prime the AI system prompt."""
    lines = []
    for i, p in enumerate(products[:8], 1):
        name  = str(p.get("title", p.get("item_name", "")))[:55]
        price = p.get("sale_price_fmt") or p.get("price_display") or str(p.get("sale_price", ""))
        rating = p.get("item_rating") or p.get("avg_rating") or 0
        sold   = p.get("item_sold") or p.get("sold") or 0
        try:
            rating_str = f"{float(rating):.1f}"
        except (TypeError, ValueError):
            rating_str = str(rating)
        try:
            sold_str = f"{int(sold):,}"
        except (TypeError, ValueError):
            sold_str = str(sold)
        lines.append(f"{i}. {name}")
        lines.append(f"   ราคา: {price} | คะแนน: {rating_str} | ขายแล้ว: {sold_str}+")
    return "\n".join(lines)
