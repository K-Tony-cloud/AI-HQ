"""Phase 10 — AI Creative Factory.

Generates production-ready creative packs (captions, hooks, image/video prompts,
voice-over scripts) for Facebook, TikTok/Reels from affiliate products.

long_url  → product identity (in affiliate_products)
short_url → affiliate posting link used in all creatives
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import duckdb

from .config import config
from .affiliate_link_engine import _connect

logger = logging.getLogger(__name__)

CREATIVE_TABLE = "creative_assets"

# ── Table ─────────────────────────────────────────────────────────────────────

def _init_creative_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {CREATIVE_TABLE} (
            id                  INTEGER,
            itemid              BIGINT NOT NULL,
            shopid              BIGINT NOT NULL,
            title               VARCHAR DEFAULT '',
            platform            VARCHAR DEFAULT 'universal',
            format              VARCHAR DEFAULT 'post',
            caption_facebook    VARCHAR DEFAULT '',
            caption_tiktok      VARCHAR DEFAULT '',
            hooks               VARCHAR DEFAULT '[]',
            cta                 VARCHAR DEFAULT '',
            hashtags            VARCHAR DEFAULT '',
            affiliate_short_url VARCHAR DEFAULT '',
            image_prompt        VARCHAR DEFAULT '{{}}',
            video_prompt        VARCHAR DEFAULT '{{}}',
            voice_script        VARCHAR DEFAULT '{{}}',
            score               VARCHAR DEFAULT '{{}}',
            status              VARCHAR DEFAULT 'draft',
            created_at          VARCHAR,
            updated_at          VARCHAR
        )
    """)


def _table_exists(con: duckdb.DuckDBPyConnection) -> bool:
    return bool(con.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name=?",
        [CREATIVE_TABLE],
    ).fetchone()[0])


# ── Product lookup ─────────────────────────────────────────────────────────────

_PRODUCT_COLS = [
    "itemid", "shopid", "title", "affiliate_short_url", "category",
    "item_sold", "price", "discount_pct", "item_rating", "shop_rating",
    "category_full", "description",
]

_PRODUCT_SELECT = """
    SELECT
        ap.itemid,
        ap.shopid,
        ap.title,
        ap.affiliate_short_url,
        ap.category,
        TRY_CAST(p.item_sold          AS BIGINT) AS item_sold,
        TRY_CAST(p.price              AS DOUBLE) AS price,
        TRY_CAST(p.discount_percentage AS DOUBLE) AS discount_pct,
        TRY_CAST(p.item_rating        AS DOUBLE) AS item_rating,
        TRY_CAST(p.shop_rating        AS DOUBLE) AS shop_rating,
        COALESCE(p.global_category1, ap.category, '') AS category_full,
        SUBSTR(COALESCE(p.description, ''), 1, 400)   AS description
    FROM affiliate_products ap
    LEFT JOIN products p ON TRY_CAST(p.itemid AS BIGINT) = ap.itemid
"""


def search_products_for_creative(keyword: str) -> list[dict]:
    """Search affiliate_products by title keyword.
    Only returns products that have an affiliate_short_url set.
    """
    if not config.db_path.exists():
        return []
    con = _connect(read_only=True)
    try:
        if not con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='affiliate_products'"
        ).fetchone()[0]:
            return []
        rows = con.execute(
            _PRODUCT_SELECT + """
            WHERE ap.title ILIKE ?
              AND ap.affiliate_short_url IS NOT NULL
              AND ap.affiliate_short_url != ''
            ORDER BY TRY_CAST(p.item_sold AS BIGINT) DESC NULLS LAST
            LIMIT 5
            """,
            [f"%{keyword}%"],
        ).fetchall()
        return [dict(zip(_PRODUCT_COLS, r)) for r in rows]
    except Exception as exc:
        logger.error("search_products_for_creative: %s", exc)
        return []
    finally:
        con.close()


def _load_product(itemid: int, shopid: int) -> dict | None:
    con = _connect(read_only=True)
    try:
        row = con.execute(
            _PRODUCT_SELECT + " WHERE ap.itemid = ? AND ap.shopid = ? LIMIT 1",
            [itemid, shopid],
        ).fetchone()
        return dict(zip(_PRODUCT_COLS, row)) if row else None
    except Exception as exc:
        logger.error("_load_product: %s", exc)
        return None
    finally:
        con.close()


# ── AI generation ──────────────────────────────────────────────────────────────

def _call_claude(prompt: str) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as exc:
        logger.error("_call_claude: %s", exc)
        return None


def _build_creative_prompt(product: dict, platform: str) -> str:
    title     = (product.get("title") or "")[:160]
    price     = product.get("price") or 0
    discount  = product.get("discount_pct") or 0
    sold      = product.get("item_sold") or 0
    rating    = product.get("item_rating") or 0
    category  = product.get("category_full") or product.get("category") or ""
    short_url = product.get("affiliate_short_url", "")

    platform_guide = {
        "facebook":  "Facebook Page post — caption 3-5 lines, storytelling, Thai adult audience",
        "tiktok":    "TikTok video caption — 1-2 lines, punchy hook-first, Thai Gen Z/Millennial",
        "reels":     "Instagram Reels — visual-first lifestyle angle, Thai young adults",
        "universal": "Multi-platform — two captions: Facebook (long) + TikTok/Reels (short)",
    }.get(platform, "Multi-platform")

    return f"""คุณคือผู้เชี่ยวชาญการตลาดสินค้าไทยบน Social Media และ Affiliate Marketing

ข้อมูลสินค้า:
- ชื่อ: {title}
- หมวดหมู่: {category}
- ราคา: ฿{price:,.0f}
- ส่วนลด: {discount:.0f}%
- ยอดขาย: {sold:,} ชิ้น
- คะแนน: {rating:.1f}/5.0
- ลิงก์ Affiliate: {short_url}

แพลตฟอร์มเป้าหมาย: {platform_guide}

กฎสำคัญ:
1. เขียนภาษาไทยเป็นหลัก โทนเป็นกันเอง ไม่เป็นทางการ
2. เน้นประโยชน์จริง + แก้ pain point ของผู้ซื้อ ไม่ใช่แค่บรรยายสินค้า
3. Hook ต้องหยุด scroll ใน 1-2 วินาที — ห้ามน่าเบื่อ
4. Image/Video prompt ต้องบรรยาย original creative scene — ห้ามคัดลอกรูปจากร้านค้า
5. ทุก prompt ต้องอ้างอิงประเภทสินค้า + use case จริง ไม่ใช่ generic
6. ใส่ลิงก์ affiliate ใน CTA เสมอ

ตอบเป็น JSON เท่านั้น (ไม่มีข้อความอื่นนอก JSON):
{{
  "caption_facebook": "caption ยาว 3-5 บรรทัด สำหรับ Facebook post พร้อม emoji",
  "caption_tiktok": "caption สั้น 1-2 บรรทัดสำหรับ TikTok/Reels",
  "hooks": [
    "hook 1 — ตั้งคำถาม/ปัญหาที่คนเจอจริง",
    "hook 2 — ตัวเลขหรือข้อเท็จจริงที่น่าสนใจ",
    "hook 3 — testimonial style แบบสั้น"
  ],
  "cta": "ข้อความ CTA พร้อมลิงก์ {short_url}",
  "hashtags": "#แฮชแท็กไทย #และอังกฤษ #ไม่เกิน15อัน",
  "image_prompt": {{
    "1_1": "Midjourney/DALL-E prompt ภาษาอังกฤษ 1:1 Facebook feed — lifestyle scene ที่สะท้อน use case จริงของสินค้า",
    "4_5": "prompt 4:5 Facebook ad — แสดง benefit ของสินค้าผ่าน scene จริง ไม่ใช่ studio",
    "9_16": "prompt 9:16 TikTok/Reels thumbnail — vertical, energetic, eye-catching, trendy"
  }},
  "video_prompt": {{
    "5s": {{
      "scene": "บรรยาย 1 scene หลักให้ชัดเจน",
      "on_screen_text": "ข้อความ overlay บนหน้าจอ",
      "voice_over": "บทพูด 5 วินาที",
      "music_sfx": "ประเภท music หรือ SFX ที่แนะนำ"
    }},
    "10s": {{
      "scenes": [
        {{"sec": "0-3s", "scene": "hook scene", "text": "overlay text"}},
        {{"sec": "3-7s", "scene": "product benefit scene", "text": "overlay text"}},
        {{"sec": "7-10s", "scene": "CTA scene", "text": "overlay text", "cta": "{short_url}"}}
      ],
      "voice_over": "บทพูดรวม 10 วินาที",
      "music_sfx": "แนะนำ music"
    }},
    "15s": {{
      "scenes": [
        {{"sec": "0-3s",   "scene": "hook — pain point", "text": "overlay"}},
        {{"sec": "3-8s",   "scene": "product reveal + key feature", "text": "overlay"}},
        {{"sec": "8-12s",  "scene": "result/benefit shown", "text": "overlay"}},
        {{"sec": "12-15s", "scene": "CTA + link", "text": "overlay", "cta": "{short_url}"}}
      ],
      "voice_over": "บทพูดรวม 15 วินาที",
      "music_sfx": "แนะนำ music"
    }}
  }},
  "voice_script": {{
    "5s":  "บทพูด voice-over ฉบับย่อ 5 วินาที",
    "10s": "บทพูด 10 วินาที",
    "15s": "บทพูด 15 วินาที พร้อม CTA"
  }},
  "score": {{
    "hook_strength":    8,
    "clarity":          9,
    "purchase_intent":  8,
    "platform_fit":     9,
    "ad_readiness":     8,
    "total":           42,
    "verdict": "Ready to post — strong hooks, clear benefit, good platform fit"
  }}
}}"""


# ── Template fallback (no API key) ────────────────────────────────────────────

def _template_creative(product: dict, platform: str) -> dict:
    title    = (product.get("title") or "สินค้า")[:80]
    price    = product.get("price") or 0
    discount = product.get("discount_pct") or 0
    sold     = product.get("item_sold") or 0
    short_url = product.get("affiliate_short_url", "")
    cat_raw  = (product.get("category_full") or product.get("category") or "").lower()

    if any(k in cat_raw for k in ("beauty", "skin", "care", "cosmetic", "hair")):
        hooks = [
            f"ผิวดีขึ้นจริงไหม? {title[:40]}... ลองแล้วบอกเลย 🤍",
            f"ยอดขายกว่า {sold:,} ชิ้น! ทำไมสาวไทยถึงซื้อซ้ำ?",
            f"ราคา ฿{price:,.0f} ลด {discount:.0f}% — คุ้มกว่าที่คิด ✨",
        ]
        scene_ctx = "Thai woman applying skincare product in bright bathroom"
    elif any(k in cat_raw for k in ("gadget", "electronic", "tech", "phone", "computer")):
        hooks = [
            f"ทำไมต้องจ่ายแพงกว่านี้? {title[:40]} ทำได้ทุกอย่าง 🔧",
            f"ขายแล้ว {sold:,} ชิ้น — นี่คือสิ่งที่คนทำงานต้องการ",
            f"ลด {discount:.0f}% เหลือ ฿{price:,.0f} — จำกัดเวลา ⚡",
        ]
        scene_ctx = "person using tech gadget at modern workspace"
    elif any(k in cat_raw for k in ("home", "living", "kitchen", "decor", "furniture")):
        hooks = [
            f"บ้านดูดีขึ้นได้ง่ายๆ ด้วย {title[:35]} 🏠",
            f"แม่บ้านขายดี {sold:,} ชิ้น — รู้ว่าดีแน่",
            f"ลด {discount:.0f}% ราคาพิเศษ ฿{price:,.0f} 🔥",
        ]
        scene_ctx = "cozy Thai home interior with product in use"
    elif any(k in cat_raw for k in ("baby", "mother", "kid", "child", "toy")):
        hooks = [
            f"แม่ๆ ต้องรู้! {title[:40]} ดีกว่าที่คิด 🍼",
            f"ยอดขาย {sold:,} ชิ้น — แม่ไทยไว้วางใจ",
            f"ราคาเบา ฿{price:,.0f} ลด {discount:.0f}% สั่งให้ลูกเลย 💕",
        ]
        scene_ctx = "happy Thai mother and child using product at home"
    else:
        hooks = [
            f"เห็นแล้วต้องมี! {title[:40]} 🛒",
            f"ยอดขาย {sold:,} ชิ้น — สินค้าขายดีอันดับต้น",
            f"ลด {discount:.0f}% เหลือ ฿{price:,.0f} อย่าพลาด! 🔥",
        ]
        scene_ctx = "person happily using product in everyday life"

    caption_fb = (
        f"✨ {title[:70]}\n\n"
        f"💰 ราคาพิเศษ ฿{price:,.0f} (ลด {discount:.0f}%)\n"
        f"⭐ ยอดขายกว่า {sold:,} ชิ้น — ลูกค้าพอใจ\n\n"
        f"✅ ของดีที่คนแนะนำต่อกันไม่หยุด\n"
        f"👉 กดสั่งได้เลยที่ลิงก์: {short_url}"
    )

    caption_tiktok = (
        f"POV: เจอสินค้านี้แล้วชีวิตดีขึ้น 🤩\n"
        f"{title[:50]}\nกดสั่งด่วน👇 {short_url}"
    )

    image_prompt = {
        "1_1": (
            f"Product lifestyle photo, 1:1 square format, {scene_ctx}, "
            f"soft natural daylight, clean modern composition, "
            f"Thai aesthetic, professional commercial photography, no text overlay"
        ),
        "4_5": (
            f"Facebook ad creative, 4:5 portrait, {scene_ctx}, "
            f"warm lifestyle feel, showing clear product benefit, "
            f"space at bottom for text overlay, high quality advertising photo"
        ),
        "9_16": (
            f"TikTok/Reels vertical 9:16, {scene_ctx}, "
            f"dynamic energetic framing, vibrant colors, "
            f"space at top and bottom for text overlay, trendy Gen Z aesthetic, "
            f"eye-catching thumbnail quality"
        ),
    }

    video_prompt = {
        "5s": {
            "scene": f"Quick reveal: {scene_ctx}, satisfying product moment, zoom in on key feature",
            "on_screen_text": f"ลด {discount:.0f}% | ฿{price:,.0f}",
            "voice_over": f"ลด {discount:.0f}% แล้ว! {title[:30]} ราคา ฿{price:,.0f} กดลิงก์ด่วน!",
            "music_sfx": "Upbeat TikTok trending sound or satisfying product reveal SFX",
        },
        "10s": {
            "scenes": [
                {"sec": "0-3s",  "scene": "Hook — relatable problem moment",    "text": hooks[0]},
                {"sec": "3-7s",  "scene": f"Product solves it — show result",   "text": f"฿{price:,.0f} ลด {discount:.0f}%"},
                {"sec": "7-10s", "scene": "Happy outcome reveal",               "text": "กดลิงก์ด้านล่าง! 👇", "cta": short_url},
            ],
            "voice_over": (
                f"{hooks[0].split('?')[0]}... "
                f"{title[:30]} ตอบโจทย์ทุกอย่าง "
                f"ราคา ฿{price:,.0f} กดลิงก์ซื้อได้เลย!"
            ),
            "music_sfx": "Energetic Thai pop or lo-fi beat, builds to CTA",
        },
        "15s": {
            "scenes": [
                {"sec": "0-3s",   "scene": "Hook — pain point",                            "text": hooks[0]},
                {"sec": "3-8s",   "scene": f"Introduce {title[:25]}, show key features",   "text": f"ยอดขาย {sold:,} ชิ้น"},
                {"sec": "8-12s",  "scene": "Demonstrate result / benefit closeup",          "text": f"ลด {discount:.0f}% เหลือ ฿{price:,.0f}"},
                {"sec": "12-15s", "scene": "CTA overlay with affiliate link",               "text": "ซื้อตอนนี้ก่อนหมด 👇", "cta": short_url},
            ],
            "voice_over": (
                f"{hooks[0]}... "
                f"วันนี้มีโปรลด {discount:.0f}% เหลือแค่ ฿{price:,.0f}... "
                f"สั่งได้เลยที่ลิงก์ด้านล่าง!"
            ),
            "music_sfx": "Trending background music, energy builds toward CTA",
        },
    }

    voice_script = {
        "5s":  f"ลด {discount:.0f}%! {title[:30]} ราคา ฿{price:,.0f} กดลิงก์ด่วน!",
        "10s": (
            f"{hooks[0]}... {title[:30]} ตอบโจทย์ทุกอย่าง "
            f"ราคา ฿{price:,.0f} ลด {discount:.0f}% แล้ว กดลิงก์ซื้อได้เลย!"
        ),
        "15s": (
            f"{hooks[0]}... แนะนำ {title[:30]} "
            f"ยอดขายกว่า {sold:,} ชิ้น พิสูจน์แล้วว่าดี "
            f"ราคาพิเศษ ฿{price:,.0f} ลด {discount:.0f}% วันนี้เท่านั้น "
            f"กดลิงก์ด้านล่างเลย!"
        ),
    }

    return {
        "caption_facebook": caption_fb,
        "caption_tiktok":   caption_tiktok,
        "hooks":            hooks,
        "cta":              f"🛒 สั่งเลย → {short_url}",
        "hashtags": (
            f"#shopee #ลดราคา #แนะนำสินค้า #ของดีราคาถูก "
            f"#affiliate #ช้อปออนไลน์ #โปรโมชั่น"
        ),
        "image_prompt":  image_prompt,
        "video_prompt":  video_prompt,
        "voice_script":  voice_script,
        "score": {
            "hook_strength":   6,
            "clarity":         7,
            "purchase_intent": 7,
            "platform_fit":    6,
            "ad_readiness":    6,
            "total":          32,
            "verdict": "Template creative — set ANTHROPIC_API_KEY for AI-powered content",
        },
    }


# ── Core generation ────────────────────────────────────────────────────────────

def generate_creative_pack(itemid: int, shopid: int, platform: str = "universal") -> dict:
    """Generate and persist a full creative pack for one affiliate product."""
    if not config.db_path.exists():
        return {"success": False, "error": "Database not found"}

    product = _load_product(itemid, shopid)
    if not product:
        return {"success": False, "error": "Product not found in affiliate_products"}

    if not product.get("affiliate_short_url"):
        return {
            "success": False,
            "error": (
                "⚠️ Missing affiliate link — cannot create ready-to-post creative.\n"
                "Use `/affiliate-product-add` to add a short link first."
            ),
        }

    # Generate content (AI or template)
    creative: dict | None = None
    used_ai = False

    raw = _call_claude(_build_creative_prompt(product, platform))
    if raw:
        try:
            j_start = raw.find("{")
            j_end   = raw.rfind("}") + 1
            creative = json.loads(raw[j_start:j_end])
            used_ai  = True
        except Exception as exc:
            logger.warning("Claude JSON parse failed: %s", exc)

    if not creative:
        creative = _template_creative(product, platform)

    # Persist
    con = _connect()
    try:
        _init_creative_table(con)
        new_id = con.execute(
            f"SELECT COALESCE(MAX(id), 0) + 1 FROM {CREATIVE_TABLE}"
        ).fetchone()[0]
        now = datetime.now().isoformat(timespec="seconds")

        con.execute(
            f"""INSERT INTO {CREATIVE_TABLE} VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                new_id,
                product["itemid"],
                product["shopid"],
                product["title"],
                platform,
                "post",
                creative.get("caption_facebook", ""),
                creative.get("caption_tiktok", ""),
                json.dumps(creative.get("hooks", []),        ensure_ascii=False),
                creative.get("cta", ""),
                creative.get("hashtags", ""),
                product["affiliate_short_url"],
                json.dumps(creative.get("image_prompt", {}), ensure_ascii=False),
                json.dumps(creative.get("video_prompt", {}), ensure_ascii=False),
                json.dumps(creative.get("voice_script", {}), ensure_ascii=False),
                json.dumps(creative.get("score", {}),        ensure_ascii=False),
                "draft",
                now,
                now,
            ],
        )
    except Exception as exc:
        con.close()
        return {"success": False, "error": f"Save failed: {exc}"}
    finally:
        con.close()

    return {
        "success":     True,
        "creative_id": new_id,
        "product":     product,
        "creative":    creative,
        "used_ai":     used_ai,
    }


# ── CRUD ──────────────────────────────────────────────────────────────────────

def get_creative_by_id(creative_id: int) -> dict | None:
    if not config.db_path.exists():
        return None
    con = _connect(read_only=True)
    try:
        if not _table_exists(con):
            return None
        row = con.execute(
            f"""SELECT id, itemid, shopid, title, platform, format,
                       caption_facebook, caption_tiktok, hooks, cta, hashtags,
                       affiliate_short_url, image_prompt, video_prompt,
                       voice_script, score, status, created_at
                FROM {CREATIVE_TABLE} WHERE id = ?""",
            [creative_id],
        ).fetchone()
        if not row:
            return None
        cols = [
            "id", "itemid", "shopid", "title", "platform", "format",
            "caption_facebook", "caption_tiktok", "hooks", "cta", "hashtags",
            "affiliate_short_url", "image_prompt", "video_prompt",
            "voice_script", "score", "status", "created_at",
        ]
        data = dict(zip(cols, row))
        for f in ("image_prompt", "video_prompt", "voice_script", "score"):
            try:
                data[f] = json.loads(data[f] or "{}")
            except Exception:
                data[f] = {}
        try:
            data["hooks"] = json.loads(data["hooks"] or "[]")
        except Exception:
            data["hooks"] = []
        return data
    except Exception:
        return None
    finally:
        con.close()


def get_creative_list(status: str | None = None, limit: int = 20) -> list[dict]:
    if not config.db_path.exists():
        return []
    con = _connect(read_only=True)
    try:
        if not _table_exists(con):
            return []
        where = f"WHERE status = '{status}'" if status and status != "all" else ""
        rows = con.execute(
            f"""SELECT id, itemid, shopid, title, platform, status, score, created_at
                FROM {CREATIVE_TABLE}
                {where}
                ORDER BY id DESC LIMIT ?""",
            [limit],
        ).fetchall()
        cols = ["id", "itemid", "shopid", "title", "platform", "status", "score", "created_at"]
        result = []
        for r in rows:
            row = dict(zip(cols, r))
            try:
                row["score"] = json.loads(row["score"] or "{}")
            except Exception:
                row["score"] = {}
            result.append(row)
        return result
    except Exception:
        return []
    finally:
        con.close()


def approve_creative(creative_id: int) -> dict:
    return _set_status(creative_id, "approved")


def reject_creative(creative_id: int) -> dict:
    return _set_status(creative_id, "rejected")


def _set_status(creative_id: int, status: str) -> dict:
    if not config.db_path.exists():
        return {"success": False, "error": "DB not found"}
    con = _connect()
    try:
        if not _table_exists(con):
            return {"success": False, "error": "creative_assets table not found"}
        now = datetime.now().isoformat(timespec="seconds")
        con.execute(
            f"UPDATE {CREATIVE_TABLE} SET status=?, updated_at=? WHERE id=?",
            [status, now, creative_id],
        )
        return {"success": True, "status": status, "id": creative_id}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    finally:
        con.close()
