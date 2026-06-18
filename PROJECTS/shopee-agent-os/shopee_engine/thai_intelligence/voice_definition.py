"""
Thai Content Intelligence — Page Voice Definition.

Defines the brand identity for เพจ "อะไรของมัน".
Used to validate content quality before publishing.

Voice summary: คนไทยเมาท์กัน / คอมเมนต์ใต้โพสต์ไวรัล
Target reaction: "เออว่ะ" / "จริง" / "บ้านกูก็เป็น" / "กูคนหนึ่ง"
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# Page Voice Definition
# ─────────────────────────────────────────────────────────────────────────────

PAGE_VOICE: dict = {
    "name": "อะไรของมัน",
    "platform": "Facebook",
    "language": "Thai casual",
    "personality": [
        "funny",
        "relatable",
        "slightly sarcastic",
        "curious",
        "unpretentious",
    ],
    "tone": "คนไทยคุยกับเพื่อน ไม่ใช่ content creator คุยกับ audience",
    "target_reaction": ["เออว่ะ", "จริง", "บ้านกูก็เป็น", "กูคนหนึ่ง", "555 จริงมาก"],
    "avoid": [
        "AI article opener (คุณเคย... / น่าสนใจมาก... / ในยุคปัจจุบัน...)",
        "educational/lecture tone",
        "motivational quote style",
        "review page style",
        "formal connectors (ดังนั้น / เพราะฉะนั้น / อย่างไรก็ตาม)",
        "generic CTAs (Comment บอกได้เลย / แสดงความคิดเห็น)",
        "academic / research language",
        "product review language (ข้อดี/ข้อเสีย, คะแนน, สเปค)",
    ],
    "content_mix": {
        "comment_bait": 0.40,    # relatable life observations
        "weird_product": 0.25,   # funny/odd Shopee finds
        "nostalgia": 0.15,       # 80s-90s-2000s childhood memories
        "visual_curiosity": 0.10, # optical illusions, "spot the difference"
        "trending": 0.07,        # current events, trends
        "affiliate": 0.03,       # product promotion (only after 1k-5k followers)
    },
    "caption_length": {
        "ideal_lines": (3, 8),     # 3-8 non-empty lines
        "ideal_chars": (80, 300),  # 80-300 characters
        "max_chars": 500,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Quality Checklist
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class QualityIssue:
    code: str
    severity: str   # "error" | "warning" | "info"
    message: str


@dataclass
class QualityResult:
    score: float                          # 0-100
    passed: bool                          # True if score >= 60
    issues: list[QualityIssue] = field(default_factory=list)
    badges: list[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        issues_str = " | ".join(f"[{i.severity.upper()}] {i.message}" for i in self.issues)
        badges_str = " ".join(self.badges)
        return f"{status} ({self.score:.0f}/100) {badges_str} — {issues_str or 'no issues'}"


# Known AI opener signatures (for quality check)
_AI_OPENER_SIGS: list[str] = [
    "คุณเคย", "ในยุคปัจจุบัน", "ในยุคที่", "น่าสนใจมาก",
    "ที่น่าสนใจคือ", "ปฏิเสธไม่ได้ว่า", "เชื่อหรือไม่ว่า",
    "น่าสนใจมากที่", "ในสังคมไทย", "มีการศึกษาพบว่า",
    "งานวิจัยพบว่า", "จากการสำรวจ", "เป็นที่ทราบกันดีว่า",
]

_FORMAL_CONNECTOR_SIGS: list[str] = [
    "ดังนั้น", "เพราะฉะนั้น", "อย่างไรก็ตาม", "ทั้งนี้",
    "กล่าวคือ", "ด้วยเหตุนี้", "โดยสรุป",
]

_BAD_CTA_SIGS: list[str] = [
    "Comment บอกได้เลย",
    "แสดงความคิดเห็น",
    "กดแชร์ให้เพื่อน",
    "อย่าลืม Like กด Share",
    "ฝากกด Like",
]

_GOOD_SPOKEN_SIGNALS: list[str] = [
    "อะ", "นะ", "วะ", "เว้ย", "ว่ะ", "มั้ย", "รึเปล่า",
    "จริงๆ", "555", "😂", "😅", "🥹", "💀", "👇",
]

_RELATABLE_SIGNALS: list[str] = [
    "แค่กูรึเปล่า", "บ้านกูก็", "กูคนเดียว", "กูด้วย",
    "โดนใจ", "ทำไมตรงใจ", "กูเป็นแบบนี้",
]


def check_content_quality(text: str, post_type: str = "comment_bait") -> QualityResult:
    """
    Score content against page voice standards.
    Returns a QualityResult with score (0-100), issues, and badges.
    """
    score = 100.0
    issues: list[QualityIssue] = []
    badges: list[str] = []

    if not text or not text.strip():
        return QualityResult(
            score=0.0,
            passed=False,
            issues=[QualityIssue("empty", "error", "Empty content")],
        )

    # ── Check: AI openers ──────────────────────────────────────────────────
    for sig in _AI_OPENER_SIGS:
        if text.startswith(sig):
            score -= 25
            issues.append(QualityIssue(
                "ai_opener", "error",
                f"Starts with AI opener: '{sig}'"
            ))
            break

    # ── Check: Formal connectors ───────────────────────────────────────────
    formal_found = [s for s in _FORMAL_CONNECTOR_SIGS if s in text]
    if formal_found:
        score -= 10 * len(formal_found)
        issues.append(QualityIssue(
            "formal_language", "warning",
            f"Formal connectors found: {', '.join(formal_found)}"
        ))

    # ── Check: Bad CTAs ────────────────────────────────────────────────────
    bad_ctas = [s for s in _BAD_CTA_SIGS if s in text]
    if bad_ctas:
        score -= 15
        issues.append(QualityIssue(
            "bad_cta", "warning",
            f"Generic CTAs: {', '.join(bad_ctas)}"
        ))

    # ── Check: Spoken language present ────────────────────────────────────
    spoken_count = sum(1 for s in _GOOD_SPOKEN_SIGNALS if s in text)
    if spoken_count < 2:
        score -= 15
        issues.append(QualityIssue(
            "too_formal", "warning",
            "Too few spoken Thai signals (particles, emoji, slang)"
        ))
    elif spoken_count >= 4:
        badges.append("🗣️ casual")

    # ── Check: Relatable hook present ─────────────────────────────────────
    relatable = any(s in text for s in _RELATABLE_SIGNALS)
    if relatable:
        score += 5
        badges.append("🤝 relatable")

    # ── Check: Length ──────────────────────────────────────────────────────
    char_count = len(text)
    non_empty_lines = [l for l in text.split("\n") if l.strip()]
    line_count = len(non_empty_lines)

    ideal_chars = PAGE_VOICE["caption_length"]["ideal_chars"]
    ideal_lines = PAGE_VOICE["caption_length"]["ideal_lines"]
    max_chars = PAGE_VOICE["caption_length"]["max_chars"]

    if char_count > max_chars:
        score -= 10
        issues.append(QualityIssue(
            "too_long", "warning",
            f"Caption too long: {char_count} chars (max {max_chars})"
        ))
    elif char_count < ideal_chars[0]:
        score -= 5
        issues.append(QualityIssue(
            "too_short", "info",
            f"Caption short: {char_count} chars (ideal ≥{ideal_chars[0]})"
        ))

    if line_count < ideal_lines[0]:
        score -= 5
        issues.append(QualityIssue(
            "few_lines", "info",
            f"Only {line_count} lines (ideal {ideal_lines[0]}-{ideal_lines[1]})"
        ))
    elif line_count > ideal_lines[1]:
        score -= 5
        issues.append(QualityIssue(
            "many_lines", "info",
            f"{line_count} lines (ideal {ideal_lines[0]}-{ideal_lines[1]})"
        ))

    # ── Check: Has closing CTA ────────────────────────────────────────────
    last_line = non_empty_lines[-1].strip() if non_empty_lines else ""
    has_cta = "👇" in last_line or "?" in last_line or "มั้ย" in last_line or "วะ" in last_line
    if not has_cta:
        score -= 10
        issues.append(QualityIssue(
            "no_cta", "warning",
            "No closing CTA found (should end with 👇 or question)"
        ))
    else:
        badges.append("📣 cta")

    # ── Clamp score ────────────────────────────────────────────────────────
    score = max(0.0, min(100.0, score))

    return QualityResult(
        score=score,
        passed=score >= 60,
        issues=issues,
        badges=badges,
    )


def get_content_mix_for_date(day_of_week: int) -> str:
    """
    Suggest content type based on day of week engagement patterns.
    day_of_week: 0=Monday, 6=Sunday
    """
    # Weekend: nostalgia + comment bait (people scroll more)
    # Weekday morning: trending + comment bait
    # Weekday evening: relatable + weird product
    schedule = {
        0: "comment_bait",
        1: "weird_product",
        2: "comment_bait",
        3: "trending",
        4: "nostalgia",
        5: "weird_product",
        6: "comment_bait",
    }
    return schedule.get(day_of_week % 7, "comment_bait")
