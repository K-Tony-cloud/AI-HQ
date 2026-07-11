"""Editorial Batch CLI — Claude Code editorial enrichment pipeline.

NO AI CALLS — pure Python export/import.  A human developer runs export,
pastes the JSON into a Claude Code terminal session for enrichment, then
runs import to write the results back to the DB.

Usage:
  python -m shopee_engine.editorial_batch export \\
      --status draft --limit 5 --model sonnet \\
      --output editorial_jobs/batch_001_input.json

  python -m shopee_engine.editorial_batch import \\
      editorial_jobs/batch_001_output.json --dry-run

  python -m shopee_engine.editorial_batch import \\
      editorial_jobs/batch_001_output.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EDITORIAL_VERSION = "1.0"

# Sections that Claude Code may rewrite
REWRITABLE_SECTIONS: frozenset[str] = frozenset({
    "บทนำ",
    "buying_scenario",
    "for_whom",
    "not_for_whom",
    "คำแนะนำการเลือกซื้อ",
    "บทสรุป",
    "product_highlights",   # dict keyed by product_id (str(itemid))
})

# ---------------------------------------------------------------------------
# Content quality scoring
# ---------------------------------------------------------------------------

_WEAK_PATTERNS: list[tuple[str, str]] = [
    (r"ทั้ง\s*\d+\s*ตัวเลือก",                     "generic_all_options"),
    (r"คุณภาพดี",                                    "generic_quality"),
    (r"เหมาะสำหรับทุกคน",                           "generic_for_all"),
    (r"น่าซื้อมาก",                                  "generic_recommend"),
    (r"(?:^|\n)บทความนี้นำเสนอ",                    "template_opening"),
    (r"(?:^|\n)ในบทความนี้",                         "template_opening"),
    (r"ฟีเจอร์ครบกว่า",                              "vague_feature"),
    (r"(?:ดีกว่า|เหนือกว่า)(?:เดิม|ทั่วไป)$",       "vague_comparison"),
    (r"สินค้า #\d+.*สินค้า #\d+.*สินค้า #\d+",      "template_product_refs"),
]


def _score_section(name: str, text: str) -> tuple[float, list[str]]:
    """Return (score 0.0–1.0, weakness tags)."""
    if not text or not text.strip():
        return 0.0, ["empty"]
    t = text.strip()
    if len(t) < 30:
        return 0.2, ["too_short"]
    tags: list[str] = []
    for pattern, tag in _WEAK_PATTERNS:
        if re.search(pattern, t, re.MULTILINE | re.IGNORECASE):
            tags.append(tag)
    if name in ("for_whom", "not_for_whom"):
        bullets = [l for l in t.split("\n") if l.strip().startswith("-")]
        if len(bullets) < 2:
            tags.append("sparse_bullets")
    if len(t) < 80:
        tags.append("short")
    if tags:
        return max(0.3, round(0.7 - 0.1 * len(tags), 1)), tags
    return (1.0 if len(t) > 150 else 0.8), []


def _score_article_sections(sections: dict[str, Any]) -> tuple[dict[str, float], list[str]]:
    """Return (section_scores, weak_sections)."""
    scores: dict[str, float] = {}
    weak: list[str] = []
    for name, content in sections.items():
        if name == "product_highlights":
            if not content:
                scores[name] = 0.0
                weak.append(name)
            else:
                hs = [_score_section(name, str(v))[0] for v in content.values()]
                scores[name] = min(hs) if hs else 0.0
                if scores[name] < 0.7:
                    weak.append(name)
        else:
            score, _ = _score_section(name, str(content or ""))
            scores[name] = score
            if score < 0.7:
                weak.append(name)
    return scores, weak


# ---------------------------------------------------------------------------
# Content parsing helpers
# ---------------------------------------------------------------------------

def _extract_buying_context_parts(content_md: str) -> tuple[str, str, str]:
    """Return (buying_scenario, for_whom, not_for_whom) from content_md."""
    from shopee_engine.article_exporter import _extract_prose
    prose = _extract_prose(content_md)
    section = prose.get("บริบทการซื้อ", "")
    if not section:
        return "", "", ""
    fw_m   = re.search(r"\*\*เหมาะกับ:\*\*", section)
    nfw_m  = re.search(r"\*\*อาจไม่ใช่ตัวเลือกที่ดีถ้า:\*\*", section)
    if fw_m:
        buying = section[: fw_m.start()].strip()
        if nfw_m:
            for_whom    = section[fw_m.end() : nfw_m.start()].strip()
            not_for_whom = section[nfw_m.end() :].strip()
        else:
            for_whom    = section[fw_m.end() :].strip()
            not_for_whom = ""
    else:
        buying = section.strip()
        for_whom = not_for_whom = ""
    return buying, for_whom, not_for_whom


def _rebuild_buying_context_block(
    buying_scenario: str,
    for_whom: str,
    not_for_whom: str,
) -> str:
    parts: list[str] = []
    if buying_scenario:
        parts.append(buying_scenario)
    if for_whom:
        parts.append(f"**เหมาะกับ:**\n\n{for_whom}")
    if not_for_whom:
        parts.append(f"**อาจไม่ใช่ตัวเลือกที่ดีถ้า:**\n\n{not_for_whom}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Prohibited-content check
# ---------------------------------------------------------------------------

_PROHIBITED: list[tuple[str, str]] = [
    (r"ดีที่สุดแน่นอน",                             "guarantee"),
    (r"รับประกัน(?:ว่า|ผล)",                        "guarantee"),
    (r"ฉัน(?:ได้)?ทดลองใช้",                        "fake_testimonial"),
    (r"เราได้ทดสอบ",                                 "fake_testimonial"),
    (r"ทดลองใช้จริงแล้ว",                            "fake_testimonial"),
    (r"\bguaranteed\b",                              "guarantee_en"),
    (r"(?:^|\s)100\s*%\s*(?:รับประกัน|มั่นใจ|ดี)",  "guarantee_pct"),
]


def _check_prohibited(text: str) -> list[str]:
    return [tag for pat, tag in _PROHIBITED if re.search(pat, text, re.M | re.I)]


# ---------------------------------------------------------------------------
# Numbers integrity check
# ---------------------------------------------------------------------------

# Units where a wrong number is a factual claim about the product.
# Negative lookbehind (?<![#\d]) prevents matching "#1 ฿" (rank markers like #1, #2).
_CLAIM_UNIT_PAT = re.compile(
    r"(?<![#\d])(\d[\d,]*(?:\.\d+)?)\s*"
    r"(?:ชิ้น|บาท|฿|คะแนน|ดาว|mAh|W\b|วัตต์|ml\b|กก\.?|กรัม|cm\b|mm\b|นิ้ว|%|เปอร์เซ็นต์)",
    re.IGNORECASE,
)


def _extract_known_numbers(products: list[dict]) -> set[str]:
    """Collect all numeric values from source facts + product titles."""
    nums: set[str] = set()
    for p in products:
        sf = p.get("source_facts", {})
        for field, v in sf.items():
            if v is None:
                continue
            nums.add(str(v))
            try:
                fv = float(v)
                if fv >= 1000:
                    nums.add(f"{int(fv):,}")
                if field == "rating":
                    nums.add(f"{fv:.1f}")
            except (ValueError, TypeError):
                pass
        for m in re.findall(r"\d+(?:\.\d+)?", p.get("title", "")):
            nums.add(m)
    return nums


def _check_invented_numbers(new_text: str, known_numbers: set[str]) -> list[str]:
    """Return list of unit-claim numbers not found in known_numbers."""
    invented: list[str] = []
    for m in _CLAIM_UNIT_PAT.finditer(new_text):
        raw = m.group(1)
        normalized = raw.replace(",", "")
        if normalized not in known_numbers and raw not in known_numbers:
            invented.append(f"{raw} (near '{m.group()}')")
    # Also flag 4+ digit or comma-formatted numbers not in source (prices, sold counts).
    # Pattern: `\d+(?:,\d{3})+` matches "12,000"; `\d{4,}` matches "12000".
    # This avoids matching "000" split from "12,000" by the boundary.
    for m in re.finditer(r"\b(\d+(?:,\d{3})+|\d{4,})\b", new_text):
        raw = m.group(1)
        normalized = raw.replace(",", "")
        if 2020 <= int(normalized) <= 2035:
            continue  # skip years
        if normalized not in known_numbers and raw not in known_numbers:
            if not any(raw in existing for existing in invented):
                invented.append(raw)
    return invented


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_article_output(
    out_article: dict,
    source_article: dict,
) -> tuple[list[str], list[str]]:
    """Return (hard_errors, warnings)."""
    errors: list[str] = []
    warns:  list[str] = []

    rewritten = out_article.get("rewritten_sections", {})
    if not rewritten:
        errors.append("rewritten_sections is empty or missing")
        return errors, warns

    src_products = source_article.get("products", [])
    src_pids     = {str(p["product_id"]) for p in src_products}

    # Unknown section keys
    for k in rewritten:
        if k not in REWRITABLE_SECTIONS:
            errors.append(f"Section '{k}' is not in REWRITABLE_SECTIONS — remove it")

    # product_highlights key validation
    ph_new = rewritten.get("product_highlights")
    if ph_new and isinstance(ph_new, dict):
        for k in ph_new:
            if str(k) not in src_pids:
                errors.append(f"product_highlights has unknown product_id '{k}'")
        # Must have exactly the same keys as source (not a subset — we require all)
        missing_pids = src_pids - {str(k) for k in ph_new}
        if missing_pids:
            warns.append(f"product_highlights missing product_ids: {missing_pids} (will keep originals)")

    # Collect all new text
    all_new = " ".join(
        (" ".join(str(x) for x in v.values()) if isinstance(v, dict) else str(v or ""))
        for v in rewritten.values()
    )

    # Prohibited content
    for tag in _check_prohibited(all_new):
        errors.append(f"Prohibited content: {tag}")

    # Numbers integrity
    known = _extract_known_numbers(src_products)
    invented = _check_invented_numbers(all_new, known)
    if invented:
        errors.append(f"Invented numbers not in source_facts: {', '.join(invented[:5])}")

    return errors, warns


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def cmd_export(args: argparse.Namespace) -> int:
    from shopee_engine.seo_engine import (
        list_articles,
        get_article,
        _connect,
        SEO_ARTICLE_PRODUCTS_TABLE,
    )
    from shopee_engine.article_exporter import _extract_prose, _extract_product_highlights

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    articles_meta = list_articles(status=args.status, limit=args.limit)
    if not articles_meta:
        print(f"[export] No articles found with status='{args.status}'")
        return 1

    batch_id = f"batch-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    batch: dict[str, Any] = {
        "editorial_version": EDITORIAL_VERSION,
        "batch_id":          batch_id,
        "created_at":        datetime.now(timezone.utc).isoformat(),
        "requested_model":   args.model,
        "articles":          [],
    }

    con = _connect(read_only=True)
    try:
        for meta in articles_meta:
            article_id = str(meta.get("article_id", ""))
            article = get_article(article_id)
            if not article:
                print(f"[export] SKIP {article_id}: not found")
                continue

            content_md = str(article.get("content_md") or "")
            prose      = _extract_prose(content_md)
            buying_scenario, for_whom, not_for_whom = _extract_buying_context_parts(content_md)
            highlights = _extract_product_highlights(content_md)

            current_sections: dict[str, Any] = {
                "บทนำ":                    prose.get("บทนำ", ""),
                "buying_scenario":         buying_scenario,
                "for_whom":                for_whom,
                "not_for_whom":            not_for_whom,
                "คำแนะนำการเลือกซื้อ":    prose.get("คำแนะนำการเลือกซื้อ", ""),
                "บทสรุป":                  prose.get("บทสรุป", ""),
                "product_highlights":      highlights,
            }
            section_scores, weak_sections = _score_article_sections(current_sections)

            # Load products enriched with item_sold / item_rating
            df = con.execute(f"""
                SELECT
                    ap.rank_in_article,
                    ap.itemid,
                    ap.shopid,
                    ap.product_title        AS title,
                    ap.sale_price,
                    ap.image_link,
                    ap.affiliate_link,
                    ap.affiliate_link_type,
                    COALESCE(p.item_sold,    0)   AS item_sold,
                    COALESCE(p.item_rating,  0.0) AS item_rating,
                    COALESCE(p.shop_rating,  0.0) AS shop_rating,
                    COALESCE(p.product_link, '')  AS product_link
                FROM {SEO_ARTICLE_PRODUCTS_TABLE} ap
                LEFT JOIN products p ON (ap.itemid = p.itemid AND ap.shopid = p.shopid)
                WHERE ap.article_id = ? AND ap.product_status != 'not_found'
                ORDER BY ap.rank_in_article ASC
            """, [article_id]).fetchdf()

            products: list[dict] = []
            protected_aff:   dict[str, str] = {}
            protected_imgs:  dict[str, str] = {}
            product_order:   list[str]      = []

            for _, row in df.iterrows():
                pid        = str(int(row.get("itemid") or 0))
                aff_link   = str(row.get("affiliate_link") or "")
                image_link = str(row.get("image_link") or "")
                price      = int(row.get("sale_price") or 0)
                sold       = int(row.get("item_sold") or 0)
                rating     = round(float(row.get("item_rating") or 0.0), 1)

                products.append({
                    "product_id":          pid,
                    "rank":                int(row.get("rank_in_article") or 0),
                    "title":               str(row.get("title") or ""),
                    "price":               price,
                    "rating":              rating,
                    "sold_count":          sold,
                    "affiliate_link":      aff_link,
                    "affiliate_link_type": str(row.get("affiliate_link_type") or "none"),
                    "image_link":          image_link,
                    "product_url": (
                        f"https://shopee.co.th/product/"
                        f"{int(row.get('shopid') or 0)}/{int(row.get('itemid') or 0)}"
                    ),
                    "source_facts": {
                        "price":      price,
                        "rating":     rating,
                        "sold_count": sold,
                    },
                })
                product_order.append(pid)
                protected_aff[pid]  = aff_link
                protected_imgs[pid] = image_link

            batch["articles"].append({
                "article_id":     article_id,
                "article_status": str(article.get("status") or ""),
                "keyword":        str(article.get("keyword") or ""),
                "category":       str(article.get("category") or ""),
                "current_sections": current_sections,
                "weak_sections":    weak_sections,
                "section_scores":   section_scores,
                "products":         products,
                "protected_fields": {
                    "product_order":   product_order,
                    "affiliate_links": protected_aff,
                    "image_urls":      protected_imgs,
                },
            })
    finally:
        con.close()

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)

    print(f"[export] {len(batch['articles'])} articles → {out_path}")
    print(f"[export] batch_id:        {batch_id}")
    print(f"[export] requested_model: {args.model}")
    print()
    for a in batch["articles"]:
        weak_str = ", ".join(a["weak_sections"]) or "none"
        print(f"  {a['article_id']:42s} weak: {weak_str}")
    return 0


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _find_input_file(output_path: Path, batch_id: str) -> Path | None:
    """Locate the corresponding input file for a given output path."""
    # Convention: batch_XXX_output.json → batch_XXX_input.json
    candidate = Path(str(output_path).replace("_output.json", "_input.json"))
    if candidate.exists():
        return candidate
    # Fallback: scan directory for any input file with matching batch_id
    for p in output_path.parent.glob("*_input.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("batch_id") == batch_id:
                return p
        except Exception:
            continue
    return None


def cmd_import(args: argparse.Namespace) -> int:
    from shopee_engine.seo_engine import (
        get_article,
        save_revision,
        _connect,
        _update_prose_section,
        SEO_ARTICLES_TABLE,
    )
    from shopee_engine.article_exporter import _HIGHLIGHTS_RE

    in_path = Path(args.input_file)
    dry_run = args.dry_run

    if not in_path.exists():
        print(f"[import] File not found: {in_path}")
        return 1

    batch_out  = json.loads(in_path.read_text(encoding="utf-8"))
    batch_id   = batch_out.get("batch_id", "")
    model_used = batch_out.get("model_used", "unknown")
    articles_out: list[dict] = batch_out.get("articles", [])

    if not batch_id:
        print("[import] ERROR: batch_id missing from output file")
        return 1

    input_path = _find_input_file(in_path, batch_id)
    if input_path is None:
        print(f"[import] ERROR: Cannot find input file for batch_id='{batch_id}'")
        return 1

    batch_in   = json.loads(input_path.read_text(encoding="utf-8"))
    if batch_in.get("batch_id") != batch_id:
        print(f"[import] ERROR: batch_id mismatch (output='{batch_id}', input='{batch_in.get('batch_id')}')")
        return 1

    source_by_id = {a["article_id"]: a for a in batch_in.get("articles", [])}

    ok_count = skip_count = warn_count = 0

    for out_article in articles_out:
        article_id = out_article.get("article_id", "")
        print(f"\n── {article_id} ──")

        # article_id must exist in DB
        article = get_article(article_id)
        if not article:
            print(f"  ERROR: article_id not in DB — SKIP")
            skip_count += 1
            continue

        # Must be in source batch
        if article_id not in source_by_id:
            print(f"  ERROR: article_id not in source batch — SKIP")
            skip_count += 1
            continue

        source_article = source_by_id[article_id]

        # Validate
        errors, warns = _validate_article_output(out_article, source_article)
        for w in warns:
            print(f"  WARN: {w}")
            warn_count += 1
        if errors:
            print(f"  VALIDATION FAILED — SKIP:")
            for e in errors:
                print(f"    • {e}")
            skip_count += 1
            continue

        rewritten = out_article.get("rewritten_sections", {})

        if dry_run:
            print(f"  OK (dry-run): {sorted(rewritten.keys())}")
            confidence = out_article.get("confidence")
            if confidence is not None:
                print(f"  confidence: {confidence}")
            ok_count += 1
            continue

        # Save revision before touching anything
        rev_reason = f"editorial-batch:{batch_id}:{model_used}"
        try:
            rev_num = save_revision(article_id, rev_reason, "editorial-batch")
            print(f"  Revision #{rev_num} saved  ({rev_reason})")
        except Exception as exc:
            print(f"  ERROR saving revision: {exc} — SKIP")
            skip_count += 1
            continue

        # Apply section rewrites to content_md
        content_md = str(article.get("content_md") or "")

        # Strip existing highlights comment before prose updates so that
        # _update_prose_section("บทสรุป") doesn't discard it (it lives inside
        # the last section body which has no trailing ## header to mark the end).
        existing_highlights_comment = ""
        m_hl = _HIGHLIGHTS_RE.search(content_md)
        if m_hl:
            existing_highlights_comment = m_hl.group(0)
            content_md = _HIGHLIGHTS_RE.sub("", content_md).rstrip()

        # Handle buying context sub-parts → rebuild บริบทการซื้อ
        buying_keys = {"buying_scenario", "for_whom", "not_for_whom"}
        if any(k in rewritten for k in buying_keys):
            src = source_article.get("current_sections", {})
            buying = rewritten.get("buying_scenario", src.get("buying_scenario", ""))
            fw     = rewritten.get("for_whom",        src.get("for_whom", ""))
            nfw    = rewritten.get("not_for_whom",     src.get("not_for_whom", ""))
            content_md = _update_prose_section(
                content_md, "บริบทการซื้อ",
                _rebuild_buying_context_block(buying, fw, nfw),
            )

        # Direct prose section updates
        for sec in ("บทนำ", "คำแนะนำการเลือกซื้อ", "บทสรุป"):
            if sec in rewritten:
                content_md = _update_prose_section(content_md, sec, str(rewritten[sec] or ""))

        # Re-append product_highlights comment (new or existing)
        ph_new = rewritten.get("product_highlights")
        if ph_new and isinstance(ph_new, dict):
            highlights_json = json.dumps(
                {str(k): str(v) for k, v in ph_new.items()},
                ensure_ascii=False, indent=2,
            )
            new_comment = f"<!-- editorial:product_highlights\n{highlights_json}\n-->"
        elif existing_highlights_comment:
            new_comment = existing_highlights_comment
        else:
            new_comment = ""
        if new_comment:
            content_md = content_md.rstrip() + "\n" + new_comment + "\n"

        # Persist
        con = _connect(read_only=False)
        try:
            con.execute(
                f"UPDATE {SEO_ARTICLES_TABLE} "
                f"SET content_md = ?, review_note = ?, updated_at = CURRENT_TIMESTAMP "
                f"WHERE article_id = ?",
                [content_md, rev_reason, article_id],
            )
            con.close()
            print(f"  Updated sections: {sorted(rewritten.keys())}")
            ok_count += 1
        except Exception as exc:
            con.close()
            print(f"  ERROR writing to DB: {exc} — SKIP")
            skip_count += 1

    mode = "DRY RUN" if dry_run else "IMPORT"
    print(f"\n[{mode}] Done. ok={ok_count}  skip={skip_count}  warnings={warn_count}")
    if dry_run:
        print("[import] No DB changes written (--dry-run).")
    return 0 if skip_count == 0 else 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m shopee_engine.editorial_batch",
        description="Claude Code Editorial Batch — export/import enrichment pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # export
    exp_p = sub.add_parser("export", help="Export articles to batch JSON for Claude Code")
    exp_p.add_argument("--status", default="draft",
                       help="Article status filter (default: draft)")
    exp_p.add_argument("--limit",  type=int, default=5,
                       help="Max articles to export (default: 5)")
    exp_p.add_argument("--model",  default="sonnet",
                       choices=["haiku", "sonnet", "opus"],
                       help="Suggested Claude model for enrichment (default: sonnet)")
    exp_p.add_argument("--output", required=True,
                       help="Output path for input batch JSON")

    # import
    imp_p = sub.add_parser("import", help="Import enriched batch JSON back to DB")
    imp_p.add_argument("input_file",
                       help="Path to the enriched output JSON from Claude Code")
    imp_p.add_argument("--dry-run", action="store_true", dest="dry_run",
                       help="Validate only — do not write to DB")

    args = parser.parse_args(argv)
    if args.command == "export":
        return cmd_export(args)
    if args.command == "import":
        return cmd_import(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
