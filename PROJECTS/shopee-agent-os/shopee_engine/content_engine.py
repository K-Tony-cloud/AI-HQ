"""
Content Intelligence Engine — AI-powered affiliate content generation.

Provider priority: ANTHROPIC_API_KEY → claude-haiku-4-5-20251001
                   OPENAI_API_KEY     → gpt-4o-mini
                   (neither)          → high-quality Thai template mode
"""

from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime
from textwrap import dedent
from typing import Any

import duckdb
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .config import config

console = Console()

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

CLAUDE_MODEL = os.environ.get("SHOPEE_AI_MODEL",        "claude-haiku-4-5-20251001")
OPENAI_MODEL = os.environ.get("SHOPEE_OPENAI_MODEL",    "gpt-4o-mini")
QUEUE_TABLE  = "content_queue"

HOOK_LABELS: dict[str, str] = {
    "viral":            "🔥 Viral Hook",
    "curiosity":        "🤔 Curiosity Hook",
    "problem_solution": "💡 Problem/Solution Hook",
    "review":           "⭐ Review Hook",
    "before_after":     "✨ Before/After Hook",
}

STATUS_DRAFT    = "draft"
STATUS_APPROVED = "approved"
STATUS_POSTED   = "posted"

# ─────────────────────────────────────────────────────────────────────────────
# AI Provider
# ─────────────────────────────────────────────────────────────────────────────

def detect_provider() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "template"


def call_ai(
    system: str,
    user_prompt: str,
    provider: str = "auto",
    max_tokens: int = 2000,
) -> str:
    p = provider if provider != "auto" else detect_provider()
    if p == "claude":
        return _call_claude(system, user_prompt, max_tokens)
    if p == "openai":
        return _call_openai(system, user_prompt, max_tokens)
    return ""   # template mode: caller handles fallback


def _call_claude(system: str, user_prompt: str, max_tokens: int) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return msg.content[0].text
    except Exception as exc:
        console.print(f"[red]Claude API error:[/] {exc}")
        return ""


def _call_openai(system: str, user_prompt: str, max_tokens: int) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:
        console.print(f"[red]OpenAI API error:[/] {exc}")
        return ""


def _parse_json(text: str) -> Any | None:
    """Extract JSON from AI response, handles markdown code blocks."""
    for candidate in [
        text.strip(),
        re.sub(r"^[^{[]*", "", text.strip()),      # strip preamble
    ]:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Product Lookup
# ─────────────────────────────────────────────────────────────────────────────

def lookup_product(keyword: str, table_name: str | None = None) -> dict:
    """Find best matching product by keyword (highest item_sold)."""
    table_name = table_name or config.default_table
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")

    con = duckdb.connect(str(config.db_path), read_only=True)
    try:
        cols = [r[0] for r in con.execute(
            f"SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{table_name}'"
        ).fetchall()]
        lm = {c.lower(): c for c in cols}

        def g(key: str, fallback: str = "") -> str:
            return lm.get(key.lower(), fallback or key)

        short_col = g("product_short link") or g("product_link", "product_link")

        kw = keyword.replace("'", "''").lower()
        sql = f"""
            SELECT
                COALESCE("{g('title', 'title')}", '') AS title,
                COALESCE(TRY_CAST("{g('sale_price','sale_price')}" AS DOUBLE), 0) AS sale_price,
                COALESCE(TRY_CAST("{g('price','price')}" AS DOUBLE), 0) AS original_price,
                COALESCE(TRY_CAST("{g('item_sold','item_sold')}" AS BIGINT), 0) AS item_sold,
                COALESCE(TRY_CAST("{g('like','like')}" AS BIGINT), 0) AS likes,
                COALESCE(TRY_CAST("{g('shop_rating','shop_rating')}" AS DOUBLE), 0.0) AS shop_rating,
                COALESCE(TRY_CAST("{g('item_rating','item_rating')}" AS DOUBLE), 0.0) AS item_rating,
                COALESCE(TRY_CAST("{g('discount_percentage','discount_percentage')}" AS DOUBLE), 0) AS discount_pct,
                COALESCE("{g('global_category3','global_category3')}", '') AS category,
                COALESCE("{g('global_category1','global_category1')}", '') AS main_category,
                COALESCE("{g('global_brand','global_brand')}", '') AS brand,
                COALESCE("{g('shop_name','shop_name')}", '') AS shop_name,
                COALESCE("{short_col}", '') AS product_short_link,
                COALESCE(CAST("{g('itemid','itemid')}" AS VARCHAR), '') AS product_id
            FROM {table_name}
            WHERE LOWER("{g('title', 'title')}") LIKE '%{kw}%'
            ORDER BY COALESCE(TRY_CAST("{g('item_sold','item_sold')}" AS BIGINT), 0) DESC
            LIMIT 1
        """
        row = con.execute(sql).df()
    finally:
        con.close()

    if row.empty:
        raise ValueError(f"ไม่พบสินค้าที่ตรงกับ keyword: '{keyword}'")

    return row.iloc[0].to_dict()


def _product_context_str(p: dict) -> str:
    """Render product dict as Thai-language context block for AI prompts."""
    return dedent(f"""
        ชื่อสินค้า: {p['title']}
        ราคาขาย: ฿{p['sale_price']:,.0f}  (ลด {p['discount_pct']:.0f}%)
        หมวดหมู่: {p['category']} ({p.get('main_category','')})
        แบรนด์: {p['brand']}
        ร้านค้า: {p['shop_name']}
        ยอดขาย: {int(p['item_sold']):,} ชิ้น
        Likes: {int(p['likes']):,}
        คะแนนร้าน: ★{p['shop_rating']:.2f}
        คะแนนสินค้า: ★{p['item_rating']:.2f}
        ลิ้งค์: {p['product_short_link']}
    """).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Template Fallback (no API key)
# ─────────────────────────────────────────────────────────────────────────────

def _template_hooks(p: dict) -> dict[str, list[str]]:
    t    = p['title'][:60]
    brand = p['brand'] or t.split()[0]
    sold  = f"{int(p['item_sold']):,}"
    price = f"฿{p['sale_price']:,.0f}"
    disc  = f"{p['discount_pct']:.0f}%"
    likes = f"{int(p['likes']):,}"
    cat   = p['category']

    return {
        "viral": [
            f"สินค้านี้มีคนซื้อไปแล้วกว่า {sold} ชิ้น — แล้วทำไมคุณถึงยังไม่รู้จักมัน?",
            f"ลด {disc} เหลือแค่ {price} ทำไม {sold} คน ถึงแห่ซื้อ {brand} ตัวนี้?",
        ],
        "curiosity": [
            f"ฉันพกสิ่งนี้ทุกที่ตั้งแต่รู้จัก {brand} และชีวิตเปลี่ยนไปตลอดกาล...",
            f"รู้ไหมว่าทำไม {brand} ถึงมีคนกด Like ถึง {likes} ครั้ง? คำตอบอยู่ที่นี่",
        ],
        "problem_solution": [
            f"เบื่อกับ{cat}ที่ใช้แล้วไม่ได้เรื่อง? {brand} แก้ปัญหานี้ได้ครบในราคา {price}",
            f"ก่อนซื้อ{cat}ราคาแพง ลองดู {brand} ก่อน — {sold} คนพิสูจน์แล้วว่าคุ้มกว่า",
        ],
        "review": [
            f"ซื้อ {brand} มาเดือนนึง บอกได้เลยว่า {price} นี้ถูกมากเมื่อเทียบกับสิ่งที่ได้",
            f"เพื่อนถามว่าได้มาจากไหน... {brand} บน Shopee ลด {disc} อยู่ตอนนี้เลย",
        ],
        "before_after": [
            f"ก่อน: หาของใน{cat}ยากมาก | หลัง: {brand} ทำให้ทุกอย่างง่ายขึ้นใน {price}",
            f"ก่อน: ไม่รู้จะซื้ออะไร | หลัง: {brand} ตอบโจทย์ทุกอย่าง — {sold} คนเห็นด้วย",
        ],
    }


def _template_captions(p: dict) -> dict[str, list[str]]:
    t     = p['title'][:50]
    brand = p['brand'] or t.split()[0]
    price = f"฿{p['sale_price']:,.0f}"
    disc  = f"{p['discount_pct']:.0f}%"
    sold  = f"{int(p['item_sold']):,}"
    link  = p['product_short_link']
    cat   = p['category']

    hashtags = _build_hashtags(p)

    return {
        "tiktok": [
            f"🔥 {brand} ลด {disc} แค่ {price}!\n💯 {sold} คนซื้อแล้ว\n🛒 ลิ้งค์ใน bio\n{hashtags}",
            f"✨ เจอของดีมาฝาก {brand} {cat}\n💰 ราคา {price} ลด {disc}\n📲 {link}\n{hashtags}",
            f"🤩 ใครยังไม่มี {brand} ต้องดูนี่!\n🏆 {sold} คนเลือกแล้ว ★{p['shop_rating']:.1f}\n👇 {link}",
            f"💥 Flash Deal! {brand} เหลือ {price}\n⏰ สต็อกจำกัด กด order เลย!\n{hashtags}",
            f"🌟 รีวิว {brand} หลังใช้งานจริง\n✅ คุ้มค่ามาก {price} ลด {disc}\n{hashtags}",
        ],
        "facebook": [
            (
                f"🛍️ แนะนำ {brand} — {cat}\n\n"
                f"ทดลองใช้มาหลายอาทิตย์แล้วบอกได้เลยว่าคุ้มมาก "
                f"ราคา {price} แต่ลด {disc} ตอนนี้เลย "
                f"ยอดขายกว่า {sold} ชิ้น บอกเลยว่าไม่ใช่แค่กระแส\n\n"
                f"👉 ซื้อได้ที่: {link}\n{hashtags}"
            ),
            (
                f"💡 เคล็ดลับ: ถ้าหา {cat} ดีๆ ราคาไม่แพง ลอง {brand} ดูก่อนนะ\n\n"
                f"ตอนนี้ลดเหลือ {price} เท่านั้น ส่วนลด {disc} "
                f"มีคนรีวิวดีมาก ★{p['item_rating']:.1f} จาก {sold} ออเดอร์\n\n"
                f"🔗 {link}\n{hashtags}"
            ),
            (
                f"✨ มาแชร์ของดีที่เจอใน Shopee!\n\n"
                f"{brand} {t[:60]}...\n\n"
                f"📌 ราคา {price} (ลด {disc})\n"
                f"⭐ ★{p['item_rating']:.1f} | 🛒 {sold} ชิ้น | 🏪 {p['shop_name'][:30]}\n\n"
                f"👇 กดลิ้งค์เพื่อสั่งซื้อ: {link}"
            ),
        ],
        "reels": [
            f"✨ {brand} เปลี่ยนชีวิตฉันได้ยังไง?\n💰 {price} ลด {disc} | 🛒 {sold} sold\n👇 {link}\n{hashtags}",
            f"🔥 Of the day: {brand}\n✅ {cat} ราคา {price}\n💥 ลด {disc} วันนี้!\n{hashtags}",
            f"POV: เจอของดีลด {disc} แค่ {price} 😱\n{brand} — {sold} คนซื้อแล้ว\n🛒 {link}",
            f"สิ่งที่ฉันพกทุกวัน → {brand} 🤍\n{price} | ★{p['shop_rating']:.1f} | ลด {disc}\n{hashtags}",
            f"Worth it? {brand} ราคา {price} 🤔\n{sold} ออเดอร์บอกแทน ✅\n🛒 {link}",
        ],
    }


def _template_scripts(p: dict) -> dict[str, str]:
    t     = p['title'][:60]
    brand = p['brand'] or t.split()[0]
    price = f"฿{p['sale_price']:,.0f}"
    disc  = f"{p['discount_pct']:.0f}%"
    sold  = f"{int(p['item_sold']):,}"
    link  = p['product_short_link']
    cat   = p['category']
    shop  = p['shop_name'][:25]
    hashtags = _build_hashtags(p)

    s15 = dedent(f"""
        [0-3s] HOOK: "{brand} ลด {disc} เหลือ {price} — {sold} คนซื้อแล้ว!"
        [3-10s] PRODUCT: {t}
                 ราคา {price} | ส่วนลด {disc} | ★{p['item_rating']:.1f}
        [10-15s] CTA: "ลิ้งค์ใน bio เลย! {hashtags}"
    """).strip()

    s30 = dedent(f"""
        [0-5s]  HOOK: "รู้ยัง? {brand} กำลัง Flash Sale ลด {disc} อยู่ตอนนี้!"
        [5-12s] PROBLEM: "หา{cat}ดีๆ ราคาไม่แพงยากมาก..."
        [12-22s] SOLUTION: "{brand} {t[:40]}
                   — ราคาเพียง {price}
                   — ยอดขายแล้ว {sold} ชิ้น
                   — ★{p['item_rating']:.1f} | ร้าน: {shop}"
        [22-30s] CTA: "กดลิ้งค์ใน bio ได้เลย! หรือ comment ว่า 'ต้องการ'
                  ฉันส่งลิ้งค์ให้ทันที {hashtags}"
    """).strip()

    s60 = dedent(f"""
        [0-5s]   HOOK: "มีของแนะนำ — {brand} ที่คนซื้อกว่า {sold} ชิ้น บน Shopee!"

        [5-18s]  STORY / ปัญหา:
                 "ก่อนหน้านี้ฉันหา{cat}ดีๆ ยากมาก ลองมาหลายตัว
                  เสียเงินไปเยอะ จนมาเจอ {brand} ตัวนี้..."

        [18-35s] DEMO / ไฮไลท์:
                 "{t[:50]}
                  ✅ จุดเด่น 1: ราคา {price} ลด {disc}
                  ✅ จุดเด่น 2: คะแนน ★{p['item_rating']:.1f} จาก {sold} ออเดอร์
                  ✅ จุดเด่น 3: ร้าน {shop} Shop Rating ★{p['shop_rating']:.1f}"

        [35-50s] REVIEW / ความรู้สึก:
                 "หลังใช้จริงหลายอาทิตย์ บอกได้เลยว่าคุ้มมาก
                  ไม่แปลกใจเลยที่ {sold} คนเลือกซื้อ
                  ถ้าถามว่า recommend ไหม — recommend แน่นอน!"

        [50-60s] CTA:
                 "ตอนนี้ยังลด {disc} อยู่นะ! ลิ้งค์ใน bio หรือ
                  comment ว่า 'ต้องการ' รับลิ้งค์ตรงเลย
                  {hashtags}"
    """).strip()

    return {"15s": s15, "30s": s30, "60s": s60}


def _build_hashtags(p: dict) -> str:
    brand = re.sub(r"[^A-Za-zก-ฮ0-9]", "", p.get("brand", ""))
    cat   = re.sub(r"[^A-Za-zก-ฮ0-9&]", "", p.get("category", "").replace(" & ", ""))
    cat1  = re.sub(r"[^A-Za-zก-ฮ0-9]", "", p.get("main_category", ""))
    parts = ["#Shopee", "#ShopeeAffiliate", "#ของดีบนShopee", "#รีวิว"]
    if brand:
        parts.append(f"#{brand}")
    if cat:
        parts.append(f"#{cat[:20]}")
    if cat1 and cat1 != cat:
        parts.append(f"#{cat1[:20]}")
    parts += ["#ของดีราคาถูก", "#แนะนำสินค้า"]
    return " ".join(parts[:8])


def _template_cta(p: dict) -> list[str]:
    price = f"฿{p['sale_price']:,.0f}"
    disc  = f"{p['discount_pct']:.0f}%"
    link  = p['product_short_link']
    return [
        f"🛒 กดลิ้งค์ใน bio ซื้อเลย! ลด {disc} วันนี้",
        f"💬 Comment 'ต้องการ' รับลิ้งค์ซื้อตรงๆ เลย!",
        f"📲 {link}  ← กดตรงนี้เลย ก่อนของหมด",
        f"🔥 Flash Sale ลด {disc} เหลือ {price} สั่งได้เลย!",
        f"✅ ใส่ตะกร้าไว้ก่อน ราคา {price} จำกัดจำนวน",
    ]


# ─────────────────────────────────────────────────────────────────────────────
# AI Prompt Builders + Generators
# ─────────────────────────────────────────────────────────────────────────────

_HOOK_SYSTEM = dedent("""
    คุณเป็น Content Creator ชาวไทยผู้เชี่ยวชาญ Shopee Affiliate Marketing บน TikTok และ Reels
    งาน: สร้าง Hook ดึงดูดใจสำหรับโปรโมทสินค้าในภาษาไทย
    กฎ:
    - ภาษาไทยธรรมชาติ สั้น ไม่เกิน 2 ประโยค
    - ต้องดึงดูดใน 3 วินาทีแรก
    - ห้ามขึ้นต้นว่า "สินค้านี้" หรือ "ผลิตภัณฑ์นี้" โดยตรง
    - ตอบเป็น JSON เท่านั้น ไม่มีข้อความอื่น
""").strip()

_CAPTION_SYSTEM = dedent("""
    คุณเป็น Social Media Manager ชาวไทยที่เชี่ยวชาญ TikTok, Facebook, Instagram Reels
    งาน: สร้าง caption ภาษาไทยสำหรับ Shopee Affiliate Content
    กฎ:
    - TikTok: สั้น punchy มี emoji เหมาะ Gen-Z
    - Facebook: storytelling เน้น social proof อ่านง่าย
    - Reels: visual-first สั้น CTA ชัด
    - ใส่ hashtag ที่เกี่ยวข้องทุกแบบ
    - ตอบเป็น JSON เท่านั้น
""").strip()

_SCRIPT_SYSTEM = dedent("""
    คุณเป็น TikTok Script Writer ชาวไทยผู้เชี่ยวชาญ Affiliate Content
    งาน: สร้าง script สำหรับวิดีโอ TikTok ภาษาไทย
    โครงสร้างแต่ละความยาว:
    - 15s: Hook(3s) + Product(7s) + CTA(5s)
    - 30s: Hook(5s) + Problem(5s) + Solution(10s) + CTA(10s)
    - 60s: Hook(5s) + Story(15s) + Demo(20s) + Review(15s) + CTA(5s)
    กฎ:
    - บอกเวลา [Xs-Xs] ทุก segment
    - ภาษาพูดธรรมชาติ ไม่ formal
    - ตอบเป็น JSON เท่านั้น ไม่มีข้อความอื่น
""").strip()


def generate_hook(
    keyword: str,
    provider: str = "auto",
    table_name: str | None = None,
) -> dict:
    """Generate 10 hooks (5 types × 2 each). Returns {product, hooks} dict."""
    p = lookup_product(keyword, table_name)
    ctx = _product_context_str(p)

    ai_text = call_ai(
        system=_HOOK_SYSTEM,
        user_prompt=dedent(f"""
            {ctx}

            สร้าง Hooks สำหรับโปรโมทสินค้านี้ทั้งหมด 10 ข้อ (แต่ละประเภท 2 ข้อ):

            ตอบ JSON ดังนี้:
            {{
              "viral": ["hook1", "hook2"],
              "curiosity": ["hook1", "hook2"],
              "problem_solution": ["hook1", "hook2"],
              "review": ["hook1", "hook2"],
              "before_after": ["hook1", "hook2"]
            }}
        """).strip(),
        provider=provider,
        max_tokens=1200,
    )

    hooks = _parse_json(ai_text) if ai_text else None
    if not isinstance(hooks, dict):
        hooks = _template_hooks(p)
        used_template = True
    else:
        used_template = False

    return {"product": p, "hooks": hooks, "provider": "template" if used_template else provider}


def generate_caption(
    keyword: str,
    provider: str = "auto",
    table_name: str | None = None,
) -> dict:
    """Generate 5 captions each for TikTok, Facebook, Reels."""
    p = lookup_product(keyword, table_name)
    ctx = _product_context_str(p)

    ai_text = call_ai(
        system=_CAPTION_SYSTEM,
        user_prompt=dedent(f"""
            {ctx}

            สร้าง Caption ภาษาไทยสำหรับโปรโมทสินค้านี้:
            - tiktok: 5 caption (สั้น มี emoji)
            - facebook: 3 caption (เน้น storytelling)
            - reels: 5 caption (visual-first)

            ตอบ JSON:
            {{
              "tiktok": ["caption1", "caption2", "caption3", "caption4", "caption5"],
              "facebook": ["caption1", "caption2", "caption3"],
              "reels": ["caption1", "caption2", "caption3", "caption4", "caption5"]
            }}
        """).strip(),
        provider=provider,
        max_tokens=2000,
    )

    captions = _parse_json(ai_text) if ai_text else None
    if not isinstance(captions, dict):
        captions = _template_captions(p)
        used_template = True
    else:
        used_template = False

    return {"product": p, "captions": captions, "provider": "template" if used_template else provider}


def generate_script(
    keyword: str,
    provider: str = "auto",
    table_name: str | None = None,
) -> dict:
    """Generate TikTok scripts for 15s, 30s, 60s."""
    p = lookup_product(keyword, table_name)
    ctx = _product_context_str(p)

    ai_text = call_ai(
        system=_SCRIPT_SYSTEM,
        user_prompt=dedent(f"""
            {ctx}

            สร้าง TikTok Script สำหรับสินค้านี้:

            ตอบ JSON:
            {{
              "15s": "full script พร้อม timing",
              "30s": "full script พร้อม timing",
              "60s": "full script พร้อม timing"
            }}
        """).strip(),
        provider=provider,
        max_tokens=2500,
    )

    scripts = _parse_json(ai_text) if ai_text else None
    if not isinstance(scripts, dict):
        scripts = _template_scripts(p)
        used_template = True
    else:
        used_template = False

    return {"product": p, "scripts": scripts, "provider": "template" if used_template else provider}


def content_pack(
    keyword: str,
    provider: str = "auto",
    table_name: str | None = None,
) -> dict:
    """Full content package: product analysis + hooks + captions + scripts + CTA + hashtags."""
    p = lookup_product(keyword, table_name)
    ctx = _product_context_str(p)

    # Single AI call for everything to save tokens
    combined_prompt = dedent(f"""
        {ctx}

        สร้าง content pack สมบูรณ์สำหรับ Shopee Affiliate Marketing:

        ตอบ JSON ดังนี้:
        {{
          "hooks": {{
            "viral": ["h1", "h2"],
            "curiosity": ["h1", "h2"],
            "problem_solution": ["h1", "h2"],
            "review": ["h1", "h2"],
            "before_after": ["h1", "h2"]
          }},
          "captions": {{
            "tiktok": ["c1","c2","c3","c4","c5"],
            "facebook": ["c1","c2","c3"],
            "reels": ["c1","c2","c3","c4","c5"]
          }},
          "scripts": {{
            "15s": "script",
            "30s": "script",
            "60s": "script"
          }},
          "cta": ["cta1","cta2","cta3","cta4","cta5"],
          "hashtags": "#tag1 #tag2 #tag3 #tag4 #tag5 #tag6 #tag7 #tag8"
        }}
    """).strip()

    ai_text = call_ai(
        system="คุณเป็น Shopee Affiliate Marketing Expert ชาวไทย ตอบ JSON เท่านั้น",
        user_prompt=combined_prompt,
        provider=provider,
        max_tokens=4000,
    )

    data = _parse_json(ai_text) if ai_text else None

    if not isinstance(data, dict) or "hooks" not in data:
        # Assemble from templates
        data = {
            "hooks":    _template_hooks(p),
            "captions": _template_captions(p),
            "scripts":  _template_scripts(p),
            "cta":      _template_cta(p),
            "hashtags": _build_hashtags(p),
        }
        used_template = True
    else:
        data.setdefault("cta",      _template_cta(p))
        data.setdefault("hashtags", _build_hashtags(p))
        used_template = False

    return {
        "product":  p,
        "content":  data,
        "provider": "template" if used_template else provider,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Queue Management (DuckDB)
# ─────────────────────────────────────────────────────────────────────────────

def _init_queue(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {QUEUE_TABLE} (
            id               INTEGER,
            keyword          VARCHAR,
            product_id       VARCHAR,
            product_title    VARCHAR,
            sale_price       DOUBLE,
            category         VARCHAR,
            brand            VARCHAR,
            item_sold        BIGINT,
            shop_rating      DOUBLE,
            discount_pct     DOUBLE,
            product_link     VARCHAR,
            hooks_json       VARCHAR,
            captions_json    VARCHAR,
            scripts_json     VARCHAR,
            cta_json         VARCHAR,
            hashtags         VARCHAR,
            ai_provider      VARCHAR,
            status           VARCHAR DEFAULT 'draft',
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def queue_add(
    keyword: str,
    provider: str = "auto",
    table_name: str | None = None,
) -> int:
    """Generate content pack and save to queue. Returns new row ID."""
    pack = content_pack(keyword, provider=provider, table_name=table_name)
    p    = pack["product"]
    c    = pack["content"]

    con = duckdb.connect(str(config.db_path), read_only=False)
    try:
        _init_queue(con)
        next_id = con.execute(
            f"SELECT COALESCE(MAX(id), 0) + 1 FROM {QUEUE_TABLE}"
        ).fetchone()[0]

        con.execute(
            f"""
            INSERT INTO {QUEUE_TABLE} (
                id, keyword, product_id, product_title, sale_price,
                category, brand, item_sold, shop_rating, discount_pct,
                product_link, hooks_json, captions_json, scripts_json,
                cta_json, hashtags, ai_provider, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                next_id,
                keyword,
                str(p.get("product_id", "")),
                str(p.get("title", ""))[:200],
                float(p.get("sale_price", 0)),
                str(p.get("category", "")),
                str(p.get("brand", "")),
                int(p.get("item_sold", 0)),
                float(p.get("shop_rating", 0)),
                float(p.get("discount_pct", 0)),
                str(p.get("product_short_link", "")),
                json.dumps(c.get("hooks", {}),    ensure_ascii=False),
                json.dumps(c.get("captions", {}), ensure_ascii=False),
                json.dumps(c.get("scripts", {}),  ensure_ascii=False),
                json.dumps(c.get("cta", []),       ensure_ascii=False),
                str(c.get("hashtags", "")),
                pack["provider"],
                STATUS_DRAFT,
                datetime.now(),
                datetime.now(),
            ],
        )
        con.commit()
    finally:
        con.close()

    return next_id


def queue_list(table_name: str | None = None) -> pd.DataFrame:
    """Return all queue items as a DataFrame."""
    if not config.db_path.exists():
        raise RuntimeError("No database found. Run import-datafeed first.")
    con = duckdb.connect(str(config.db_path), read_only=True)
    try:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        if QUEUE_TABLE not in tables:
            return pd.DataFrame()
        df = con.execute(
            f"SELECT id, keyword, product_title, sale_price, category, "
            f"       brand, item_sold, shop_rating, ai_provider, status, "
            f"       strftime(created_at, '%Y-%m-%d %H:%M') AS created_at "
            f"FROM {QUEUE_TABLE} ORDER BY id DESC"
        ).df()
    finally:
        con.close()
    return df


def queue_approve(row_id: int) -> bool:
    """Change status from draft → approved. Returns True if updated."""
    if not config.db_path.exists():
        raise RuntimeError("No database found.")
    con = duckdb.connect(str(config.db_path), read_only=False)
    try:
        _init_queue(con)
        count_before = con.execute(
            f"SELECT COUNT(*) FROM {QUEUE_TABLE} WHERE id = {row_id}"
        ).fetchone()[0]
        if count_before == 0:
            return False
        con.execute(
            f"UPDATE {QUEUE_TABLE} "
            f"SET status = '{STATUS_APPROVED}', updated_at = NOW() "
            f"WHERE id = {row_id}"
        )
        con.commit()
    finally:
        con.close()
    return True


def queue_get_content(row_id: int) -> dict | None:
    """Fetch a full content pack from the queue by ID."""
    if not config.db_path.exists():
        return None
    con = duckdb.connect(str(config.db_path), read_only=True)
    try:
        row = con.execute(
            f"SELECT * FROM {QUEUE_TABLE} WHERE id = {row_id}"
        ).df()
    finally:
        con.close()
    if row.empty:
        return None
    r = row.iloc[0].to_dict()
    return {
        "id":             r["id"],
        "keyword":        r["keyword"],
        "product_title":  r["product_title"],
        "status":         r["status"],
        "hooks":    json.loads(r["hooks_json"]    or "{}"),
        "captions": json.loads(r["captions_json"] or "{}"),
        "scripts":  json.loads(r["scripts_json"]  or "{}"),
        "cta":      json.loads(r["cta_json"]      or "[]"),
        "hashtags": r["hashtags"],
        "provider": r["ai_provider"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Rich Display
# ─────────────────────────────────────────────────────────────────────────────

def _product_header(p: dict) -> None:
    price = f"฿{p['sale_price']:,.0f}"
    disc  = f"{p['discount_pct']:.0f}%"
    sold  = f"{int(p['item_sold']):,}"
    prov  = p.get("_provider", "")
    console.print(Panel(
        f"[bold white]{p['title'][:90]}[/]\n"
        f"[green]{price}[/]  [red]▼{disc}[/]  "
        f"[yellow]Sold {sold}[/]  "
        f"[magenta]★{p['shop_rating']:.2f}[/]  "
        f"[blue]{p['category']}[/]  "
        f"[dim]{p['brand']}[/]"
        + (f"\n[dim]AI: {prov}[/]" if prov else ""),
        title="[bold green]📦 Product",
        expand=False,
    ))


def print_hooks(result: dict) -> None:
    p = result["product"]
    p["_provider"] = result.get("provider", "")
    _product_header(p)

    hooks = result["hooks"]
    for hook_type, label in HOOK_LABELS.items():
        entries = hooks.get(hook_type, [])
        if entries:
            console.print(f"\n[bold]{label}[/]")
            for i, h in enumerate(entries, 1):
                console.print(f"  [dim]{i}.[/] {h}")


def print_captions(result: dict) -> None:
    p = result["product"]
    p["_provider"] = result.get("provider", "")
    _product_header(p)

    caps = result["captions"]
    sections = [
        ("tiktok",   "🎵 TikTok Captions",   "cyan"),
        ("facebook", "📘 Facebook Captions",  "blue"),
        ("reels",    "📸 Reels Captions",     "magenta"),
    ]
    for key, title, color in sections:
        items = caps.get(key, [])
        if items:
            console.print(f"\n[bold {color}]{title}[/]")
            for i, c in enumerate(items, 1):
                console.print(Panel(c, title=f"[dim]#{i}[/]", expand=False))


def print_scripts(result: dict) -> None:
    p = result["product"]
    p["_provider"] = result.get("provider", "")
    _product_header(p)

    scripts = result["scripts"]
    labels = [("15s", "⚡ 15-Second Script"), ("30s", "🎬 30-Second Script"), ("60s", "🎥 60-Second Script")]
    colors = ["yellow", "green", "cyan"]
    for (key, title), color in zip(labels, colors):
        text = scripts.get(key, "")
        if text:
            console.print(Panel(text, title=f"[bold {color}]{title}[/]", expand=False))
            console.print()


def print_content_pack(result: dict) -> None:
    p       = result["product"]
    content = result["content"]
    prov    = result.get("provider", "template")
    p["_provider"] = prov

    _product_header(p)

    # Hooks
    console.print(Rule("[bold]📌 HOOKS", style="green"))
    hooks = content.get("hooks", {})
    for hook_type, label in HOOK_LABELS.items():
        entries = hooks.get(hook_type, [])
        if entries:
            console.print(f"\n[bold]{label}[/]")
            for i, h in enumerate(entries, 1):
                console.print(f"  [dim]{i}.[/] {h}")

    # TikTok captions
    console.print(Rule("[bold]🎵 CAPTIONS", style="cyan"))
    caps = content.get("captions", {})
    for plat, plat_label, color in [
        ("tiktok",   "TikTok",   "cyan"),
        ("facebook", "Facebook", "blue"),
        ("reels",    "Reels",    "magenta"),
    ]:
        items = caps.get(plat, [])[:2]   # show first 2 per platform in pack
        if items:
            console.print(f"\n[bold {color}]{plat_label}[/]")
            for i, c in enumerate(items, 1):
                short = c[:180] + ("…" if len(c) > 180 else "")
                console.print(f"  [dim]{i}.[/] {short}")

    # Scripts summary
    console.print(Rule("[bold]🎬 SCRIPTS", style="yellow"))
    scripts = content.get("scripts", {})
    for key, label in [("15s", "15s"), ("30s", "30s"), ("60s", "60s")]:
        sc = scripts.get(key, "")
        if sc:
            preview = sc[:200].replace("\n", "  ") + ("…" if len(sc) > 200 else "")
            console.print(f"[yellow]{label}[/]: {preview}\n")

    # CTA
    console.print(Rule("[bold]📢 CTA", style="red"))
    for i, cta in enumerate(content.get("cta", [])[:3], 1):
        console.print(f"  [dim]{i}.[/] {cta}")

    # Hashtags
    console.print(Rule("[bold]🏷  HASHTAGS", style="dim"))
    console.print(f"  {content.get('hashtags', '')}")

    # Affiliate link status
    console.print(Rule("[bold]🔗 AFFILIATE LINK", style="green"))
    raw_link = p.get("product_short_link") or p.get("product_id", "")
    from .affiliate_link_engine import get_affiliate_link
    aff = get_affiliate_link(str(raw_link)) if raw_link else None
    if aff:
        console.print(f"  [bold green]✅ Ready to post:[/] [cyan]{aff}[/]")
    else:
        console.print(
            "  [bold red]⚠ Needs affiliate link[/]\n"
            "  Run: [dim]shopee export-link-tasks[/]  →  fill CSV  →  "
            "[dim]shopee import-affiliate-links <file>[/]"
        )


def print_queue(df: pd.DataFrame) -> None:
    if df.empty:
        console.print("[yellow]Queue is empty. Run 'shopee queue-add --keyword X' first.[/]")
        return

    STATUS_COLOR = {STATUS_DRAFT: "yellow", STATUS_APPROVED: "green", STATUS_POSTED: "dim"}
    tbl = Table(title="[bold green]Content Queue[/]", show_lines=True, expand=True)
    tbl.add_column("ID",       style="bold dim",  width=4,  justify="right")
    tbl.add_column("Keyword",  style="bold cyan",  max_width=18)
    tbl.add_column("Product",  style="white",      max_width=44)
    tbl.add_column("Price",    style="green",       width=10)
    tbl.add_column("Sold",     style="yellow",      width=8)
    tbl.add_column("Category", style="blue",       max_width=20)
    tbl.add_column("AI",       style="magenta",    max_width=10)
    tbl.add_column("Status",   style="white",       width=10)
    tbl.add_column("Created",  style="dim",        max_width=16)

    for _, row in df.iterrows():
        status = str(row.get("status", "draft"))
        color  = STATUS_COLOR.get(status, "white")
        tbl.add_row(
            str(row.get("id", "")),
            str(row.get("keyword", ""))[:18],
            str(row.get("product_title", ""))[:44],
            f"฿{float(row.get('sale_price', 0)):,.0f}",
            f"{int(row.get('item_sold', 0)):,}",
            str(row.get("category", ""))[:20],
            str(row.get("ai_provider", ""))[:10],
            f"[{color}]{status}[/]",
            str(row.get("created_at", ""))[:16],
        )
    console.print(tbl)


# ─────────────────────────────────────────────────────────────────────────────
# Content Intelligence — อะไรของมัน Facebook Page
# ─────────────────────────────────────────────────────────────────────────────

COMMISSION_TABLE = "commission_report"

_PAGE_SYSTEM = dedent("""
    คุณเป็น Admin เพจ Facebook "อะไรของมัน"
    สไตล์เพจ: ตลก ชอบสังเกต sarcastic แบบไทยๆ พูดแบบคนธรรมดา ไม่ formal ไม่ corporate
    Target: คนไทย 18-50 ปี ชอบของแปลก ชอบ viral
    กฎเหล็ก:
    - ห้ามฟังดู AI หรือ corporate
    - ใช้ภาษาพูดธรรมดา คำสแลงไทยได้
    - ต้องกระตุ้น comment/share
    - ตอบเป็น JSON เท่านั้น
""").strip()

_ENGAGEMENT_TEMPLATES: dict[str, list[dict]] = {
    "comment_bait": [
        {"hook": "ถ้าได้เงิน 100,000 บาทพรุ่งนี้เช้า จะทำอะไรเป็นอย่างแรก? 👇", "caption": "บอกมาเลยนะ ไม่ตัดสิน 555", "cta": "comment ด้านล่างได้เลย"},
        {"hook": "ของชิ้นไหนที่ซื้อแล้วไม่เคยเสียดายเงินเลยสักครั้ง?", "caption": "อยากรู้จริงๆ บางทีของราคาไม่แพงแต่เปลี่ยนชีวิตได้", "cta": "mention ชื่อสินค้าในคอมเม้นต์เลย"},
        {"hook": "เงินเดือนเท่าไหร่ถึงเรียกว่าอยู่สบายในกรุงเทพ?", "caption": "แต่ละคนนิยามไม่เหมือนกัน ขึ้นอยู่กับ lifestyle ด้วย", "cta": "บอกตัวเลขในคอมเม้นต์ได้เลย"},
    ],
    "nostalgia": [
        {"hook": "ใครทัน Tamagotchi บ้าง? 🐣", "caption": "เด็กยุค 90s-2000s ต้องรู้จัก ตอนนั้นเลี้ยงตายร้องไห้เลยนะ 😭", "cta": "comment ว่าเคยมีไหม"},
        {"hook": "โรตีหน้าหมูยอ ขายข้างถนน ยังมีอยู่ไหมนะ?", "caption": "ของกินที่หายไปจากความทรงจำ แต่รสชาติไม่เคยลืม", "cta": "ของกินยุคเด็กที่อยากกินอีกมีอะไรบ้าง?"},
    ],
    "visual_curiosity": [
        {"hook": "ทายราคาสิ่งของในรูปนี้ก่อนเลื่อนผ่าน 👀", "caption": "บางอย่างดูแพงแต่ไม่แพง บางอย่างดูถูกแต่แพงมาก", "cta": "ทายในคอมเม้นต์ได้เลย เดี๋ยวเฉลย"},
        {"hook": "มีอะไรผิดปกติในรูปนี้ไหม? 🤔", "caption": "ดูดีๆ นะ ตอบถูกจะ surprise", "cta": "บอกในคอมเม้นต์"},
    ],
    "weird_product": [
        {"hook": "อะไรของมันวะ 😂 เห็นครั้งแรกงงมาก", "caption": "แต่พอรู้ว่าทำอะไร... โอ้โห มันเจ๋งมากนะ ใช้ประโยชน์ได้จริงๆ", "cta": "คิดว่าใช้ทำอะไร? comment ก่อนเฉลย 👇"},
        {"hook": "เห็นของนี้ครั้งแรก คิดว่าคนขายจะโกงเงิน 555", "caption": "แต่มันใช้งานได้จริง และคนซื้อไปเยอะมากด้วย", "cta": "เคยเห็นของแปลกๆ แบบนี้บ้างไหม?"},
    ],
    "trending": [
        {"hook": "คนไทยกำลังเถียงกันว่า... ไปทำงานต่างจังหวัดดีกว่าอยู่กรุงเทพไหม?", "caption": "ต่างจังหวัด: ค่าครองชีพถูก สบายใจ | กรุงเทพ: โอกาสเยอะ เงินดี แต่เครียด", "cta": "คุณเลือกทางไหน? comment ได้เลย"},
        {"hook": "ถ้าเลือกได้อย่างเดียว จะเลือก มีเงิน 10 ล้านแต่หน้าตาธรรมดา หรือ หน้าดีมากแต่เงินเดือน 20,000?", "caption": "คำถามนี้ไม่มีคำตอบถูกผิด แต่อยากรู้ว่าคุณคิดยังไง", "cta": "เลือกข้อไหน? บอกในคอมเม้นต์"},
    ],
}

_CALENDAR_PATTERN = [
    {"slot": 1,  "type": "comment_bait",     "category": "engagement"},
    {"slot": 2,  "type": "weird_product",    "category": "product"},
    {"slot": 3,  "type": "nostalgia",        "category": "engagement"},
    {"slot": 4,  "type": "comment_bait",     "category": "engagement"},
    {"slot": 5,  "type": "weird_product",    "category": "product"},
    {"slot": 6,  "type": "trending",         "category": "engagement"},
    {"slot": 7,  "type": "visual_curiosity", "category": "engagement"},
    {"slot": 8,  "type": "comment_bait",     "category": "engagement"},
    {"slot": 9,  "type": "affiliate",        "category": "affiliate"},
    {"slot": 10, "type": "trending",         "category": "engagement"},
]

_CALENDAR_DESCRIPTIONS: dict[str, str] = {
    "comment_bait":     "โพสต์คำถามเกี่ยวกับการเงินหรือการใช้ชีวิต",
    "weird_product":    "โชว์ของแปลก ให้คนทาย ก่อนเฉลยว่าทำอะไร",
    "nostalgia":        "พาไปหาความทรงจำยุค 90s-2000s ให้คนมา comment",
    "trending":         "หยิบประเด็นที่คนกำลังเถียงมาให้เลือกข้าง",
    "visual_curiosity": "โพสต์รูปที่ชวนทาย ดึงความสนใจ",
    "affiliate":        "แนะนำสินค้าดีจาก Shopee แบบนุ่มๆ ไม่ขายตรง",
}


def get_content_picks(top_n: int = 5) -> list[dict]:
    """Find best products to feature today based on real commission data or product popularity."""
    if not config.db_path.exists():
        return []

    con = duckdb.connect(str(config.db_path), read_only=True)
    try:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]

        # Try commission_report first (real winner data)
        if COMMISSION_TABLE in tables:
            rows = con.execute(f"""
                SELECT
                    product_name,
                    SUM(commission) AS commission,
                    COUNT(*)        AS orders,
                    SUM(revenue)    AS revenue
                FROM {COMMISSION_TABLE}
                GROUP BY product_name
                ORDER BY commission DESC
                LIMIT {top_n}
            """).fetchall()
            if rows:
                return [
                    {
                        "name":       (r[0] or "")[:60],
                        "commission": float(r[1] or 0),
                        "orders":     float(r[2] or 0),
                        "revenue":    float(r[3] or 0),
                        "source":     "real",
                    }
                    for r in rows
                ]

        # Fallback: products table by item_sold
        if "products" in tables:
            prod_cols = [r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='products'"
            ).fetchall()]
            lm = {c.lower(): c for c in prod_cols}
            title_col = lm.get("title") or lm.get("name") or lm.get("product_name") or prod_cols[0]
            sold_col  = lm.get("item_sold") or lm.get("sales") or lm.get("sold")
            if sold_col:
                rows = con.execute(f"""
                    SELECT
                        "{title_col}" AS name,
                        0             AS commission,
                        0             AS orders,
                        0             AS revenue
                    FROM products
                    WHERE "{title_col}" IS NOT NULL
                    ORDER BY COALESCE(TRY_CAST("{sold_col}" AS BIGINT), 0) DESC
                    LIMIT {top_n}
                """).fetchall()
                return [
                    {
                        "name":       (r[0] or "")[:60],
                        "commission": float(r[1] or 0),
                        "orders":     float(r[2] or 0),
                        "revenue":    float(r[3] or 0),
                        "source":     "discovery",
                    }
                    for r in rows
                ]
    except Exception:
        pass
    finally:
        con.close()

    return []


def generate_engagement_post(post_type: str = "comment_bait") -> dict:
    """Generate a viral/engagement-only Facebook post for the อะไรของมัน page."""
    post_type_map = {
        "comment_bait":     "ถ้ามีเงิน 100,000 บาท จะเอาไปทำอะไรก่อน? style — open question that begs for comments",
        "nostalgia":        "ใครทันของพวกนี้บ้าง? style — reference Thai 90s/2000s things",
        "visual_curiosity": "ทายราคา / รูปนี้มีอะไรผิดปกติ style",
        "weird_product":    "อะไรของมันวะ 😂 → reveal ว่ามันมีประโยชน์ยังไง — lead with confusion, reveal usefulness",
        "trending":         "คนไทยกำลังเถียงกันเรื่อง... หรือ ถ้าเลือกได้ style",
    }
    style_hint = post_type_map.get(post_type, "engaging Thai Facebook post")

    ai_text = call_ai(
        system=_PAGE_SYSTEM,
        user_prompt=dedent(f"""
            สร้างโพสต์ Facebook สำหรับเพจ "อะไรของมัน" แบบ {post_type}
            สไตล์: {style_hint}

            ตอบ JSON:
            {{"caption": "...", "hook": "...", "cta": "..."}}
        """).strip(),
        max_tokens=600,
    )

    data = _parse_json(ai_text) if ai_text else None
    if isinstance(data, dict) and "hook" in data:
        data["type"]     = post_type
        data["provider"] = detect_provider()
        return data

    # Template fallback
    templates = _ENGAGEMENT_TEMPLATES.get(post_type, _ENGAGEMENT_TEMPLATES["comment_bait"])
    chosen = random.choice(templates)
    return {
        "type":     post_type,
        "hook":     chosen["hook"],
        "caption":  chosen["caption"],
        "cta":      chosen["cta"],
        "provider": "template",
    }


def _template_weird_product_post(p: dict) -> dict:
    name = p.get("name") or p.get("title", "สินค้านี้")
    return {
        "hook":     "อะไรของมันวะ 😂 เห็นครั้งแรกงงมากเลย",
        "post":     (
            f"อะไรของมันวะ 😂\n\n"
            f"เห็นครั้งแรกนึกว่าของแปลก แต่พอลองดูแล้ว...\n"
            f"{str(name)[:60]}\n\n"
            f"ปรากฏว่ามีคนซื้อไปเยอะมากแล้ว ใช้งานได้จริงด้วย\n\n"
            f"คิดว่ามันคืออะไร? comment ก่อนเฉลย 👇"
        ),
        "hashtags": "#อะไรของมัน #ของแปลก #ของดีบนShopee",
        "provider": "template",
    }


def generate_facebook_product_post(product: dict) -> dict:
    """Generate a Facebook post for a specific product in the อะไรของมัน page voice."""
    name  = product.get("name") or product.get("title", "สินค้านี้")
    price = product.get("sale_price") or product.get("price") or 0
    sold  = product.get("item_sold") or product.get("sold") or 0

    ai_text = call_ai(
        system=_PAGE_SYSTEM,
        user_prompt=dedent(f"""
            สร้างโพสต์ Facebook สำหรับเพจ "อะไรของมัน" โปรโมทสินค้านี้:
            ชื่อ: {name}
            ราคา: ฿{float(price):,.0f}
            ยอดขาย: {int(float(sold)):,} ชิ้น

            สไตล์: นำด้วยความแปลก/น่าสงสัย → reveal สินค้า → soft CTA
            ห้ามขายตรงหรือฟังดู corporate

            ตอบ JSON:
            {{"post": "...", "hook": "...", "hashtags": "..."}}
        """).strip(),
        max_tokens=800,
    )

    data = _parse_json(ai_text) if ai_text else None
    if isinstance(data, dict) and "post" in data:
        data["provider"] = detect_provider()
        return data

    return _template_weird_product_post(product)


def generate_content_calendar(days: int = 7) -> list[dict]:
    """Build a posting calendar using the 70/20/10 content mix pattern."""
    from datetime import timedelta

    today  = datetime.now()
    result = []

    for day_num in range(1, days + 1):
        slot_idx  = (day_num - 1) % len(_CALENDAR_PATTERN)
        slot      = _CALENDAR_PATTERN[slot_idx]
        post_date = today + timedelta(days=day_num - 1)
        date_str  = post_date.strftime("%Y-%m-%d")
        desc      = _CALENDAR_DESCRIPTIONS.get(slot["type"], "โพสต์ content")

        result.append({
            "day":         day_num,
            "date":        date_str,
            "type":        slot["type"],
            "category":    slot["category"],
            "time":        "19:00",
            "description": desc,
        })

    return result


def generate_content_mix(picks: list[dict] | None = None) -> dict:
    """Daily content package: 1 engagement + 1 weird product + 1 affiliate soft."""
    engagement = generate_engagement_post("comment_bait")

    # Product post: use first pick if available, else create a generic one
    if picks:
        product_post = generate_facebook_product_post(picks[0])
    else:
        product_post = _template_weird_product_post({"name": "สินค้าแปลกประจำวัน"})

    # Affiliate soft: use second pick or a template note
    if picks and len(picks) > 1:
        aff_name = picks[1].get("name", "สินค้า Shopee")
    else:
        aff_name = "สินค้าดีจาก Shopee"

    affiliate = {
        "type":     "affiliate",
        "hook":     f"ของดีที่อยากบอก: {aff_name[:50]}",
        "caption":  "ลองดูนะ คนซื้อเยอะ บอกตรงๆ ว่าใช้งานได้จริง",
        "cta":      "ลิ้งค์ใน bio หรือ comment 'ต้องการ'",
        "provider": "template",
    }

    return {
        "engagement": engagement,
        "product":    product_post,
        "affiliate":  affiliate,
        "date":       datetime.now().strftime("%Y-%m-%d"),
    }
