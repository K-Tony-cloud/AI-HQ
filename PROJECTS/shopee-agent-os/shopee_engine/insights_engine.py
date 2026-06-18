"""
Facebook Insights + Content Performance + Scheduling Engine.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Any

import duckdb

from .config import config
from .facebook_engine import (
    _creds_ok,
    _fb_get,
    _fb_post,
    _page_id,
)

try:
    from dotenv import load_dotenv
    load_dotenv(config.db_path.parent.parent / ".env")
except ImportError:
    pass

PERFORMANCE_TABLE = "post_performance"
SCHEDULED_TABLE   = "scheduled_posts"


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def _connect_rw() -> duckdb.DuckDBPyConnection:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(config.db_path), read_only=False)


def _connect_ro() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(config.db_path), read_only=True)


def _init_performance(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {PERFORMANCE_TABLE} (
            post_id          TEXT,
            created_at       TEXT,
            message          TEXT    DEFAULT '',
            post_type        TEXT    DEFAULT 'manual',
            reach            INTEGER DEFAULT 0,
            impressions      INTEGER DEFAULT 0,
            reactions        INTEGER DEFAULT 0,
            comments         INTEGER DEFAULT 0,
            shares           INTEGER DEFAULT 0,
            clicks           INTEGER DEFAULT 0,
            engagement_rate  DOUBLE  DEFAULT 0.0,
            score            DOUBLE  DEFAULT 0.0,
            synced_at        TEXT    DEFAULT ''
        )
    """)


def _init_scheduled(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {SCHEDULED_TABLE} (
            id          INTEGER,
            created_at  TEXT,
            message     TEXT,
            image_url   TEXT    DEFAULT '',
            link        TEXT    DEFAULT '',
            post_type   TEXT    DEFAULT 'manual',
            publish_at  TEXT,
            status      TEXT    DEFAULT 'pending',
            post_id     TEXT    DEFAULT '',
            note        TEXT    DEFAULT ''
        )
    """)


# ─────────────────────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────────────────────

def _compute_score(
    reach: int, reactions: int, comments: int, shares: int, clicks: int
) -> float:
    engagement = reactions + (comments * 2) + (shares * 3) + clicks
    rate = engagement / max(reach, 1) * 100
    return round(rate * math.log1p(reach), 4)


# ─────────────────────────────────────────────────────────────────────────────
# Facebook API — post-level metrics
# ─────────────────────────────────────────────────────────────────────────────

def _get_post_metrics(post_id: str) -> dict[str, int]:
    metrics: dict[str, int] = {
        "reach": 0, "impressions": 0,
        "reactions": 0, "comments": 0, "shares": 0, "clicks": 0,
    }
    # Insights endpoint (lifetime period)
    try:
        data = _fb_get(
            f"{post_id}/insights",
            metric="post_impressions_unique,post_impressions,post_engaged_users,post_clicks",
            period="lifetime",
        )
        mapping = {
            "post_impressions_unique": "reach",
            "post_impressions":        "impressions",
            "post_engaged_users":      "reactions",
            "post_clicks":             "clicks",
        }
        for item in data.get("data", []):
            key = mapping.get(item["name"])
            if key:
                vals = item.get("values", [])
                val  = vals[0].get("value", 0) if vals else 0
                if isinstance(val, (int, float)):
                    metrics[key] = int(val)
    except Exception:
        pass
    # Social counts — more reliable for reactions/comments/shares
    try:
        social = _fb_get(
            post_id,
            fields="reactions.summary(true),comments.summary(true),shares",
        )
        metrics["reactions"] = (
            social.get("reactions", {}).get("summary", {}).get("total_count", metrics["reactions"])
        )
        metrics["comments"] = (
            social.get("comments", {}).get("summary", {}).get("total_count", metrics["comments"])
        )
        metrics["shares"] = (
            social.get("shares", {}).get("count", metrics["shares"])
        )
    except Exception:
        pass
    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# Facebook API — page insights
# ─────────────────────────────────────────────────────────────────────────────

def fb_get_page_insights() -> dict[str, Any]:
    ok, err = _creds_ok()
    if not ok:
        return {"error": err}
    try:
        since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        until = datetime.now().strftime("%Y-%m-%d")
        metrics = (
            "page_impressions,"
            "page_impressions_unique,"
            "page_engaged_users,"
            "page_fan_adds,"
            "page_views_total"
        )
        data = _fb_get(
            f"{_page_id()}/insights",
            metric=metrics,
            period="day",
            since=since,
            until=until,
        )
        result: dict[str, Any] = {"page_id": _page_id(), "since": since, "until": until}
        for item in data.get("data", []):
            name   = item["name"]
            values = item.get("values", [])
            total  = sum(
                v.get("value", 0) if isinstance(v.get("value"), (int, float)) else 0
                for v in values
            )
            result[name] = int(total)
        return result
    except Exception as exc:
        return {"error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Facebook API — posts list
# ─────────────────────────────────────────────────────────────────────────────

def fb_get_posts(limit: int = 10) -> list[dict]:
    ok, err = _creds_ok()
    if not ok:
        return [{"error": err}]
    try:
        raw = _fb_get(
            f"{_page_id()}/posts",
            fields="id,message,story,created_time,permalink_url",
            limit=limit,
        )
        result = []
        for p in raw.get("data", []):
            post_id  = p.get("id", "")
            msg_text = (p.get("message") or p.get("story") or "")[:120]
            m        = _get_post_metrics(post_id)
            er = round(
                (m["reactions"] + m["comments"] + m["shares"]) / max(m["reach"], 1) * 100,
                4,
            )
            sc = _compute_score(m["reach"], m["reactions"], m["comments"], m["shares"], m["clicks"])
            result.append({
                "post_id":         post_id,
                "message":         msg_text,
                "created_at":      p.get("created_time", ""),
                "url":             p.get("permalink_url", ""),
                "reach":           m["reach"],
                "impressions":     m["impressions"],
                "reactions":       m["reactions"],
                "comments":        m["comments"],
                "shares":          m["shares"],
                "clicks":          m["clicks"],
                "engagement_rate": er,
                "score":           sc,
            })
        return result
    except Exception as exc:
        return [{"error": str(exc)}]


# ─────────────────────────────────────────────────────────────────────────────
# Performance DB sync
# ─────────────────────────────────────────────────────────────────────────────

def sync_post_performance(limit: int = 25) -> dict:
    posts = fb_get_posts(limit=limit)
    if not posts or (len(posts) == 1 and "error" in posts[0]):
        return {"synced": 0, "error": posts[0].get("error", "no data") if posts else "no posts"}

    con = _connect_rw()
    try:
        _init_performance(con)
        synced = 0
        now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for p in posts:
            if "error" in p:
                continue
            pid = p["post_id"]
            r, imp = p["reach"], p["impressions"]
            rx, cm, sh, cl = p["reactions"], p["comments"], p["shares"], p["clicks"]
            er, sc = p["engagement_rate"], p["score"]

            exists = con.execute(
                f"SELECT post_id FROM {PERFORMANCE_TABLE} WHERE post_id = ?", [pid]
            ).fetchone()
            if exists:
                con.execute(f"""
                    UPDATE {PERFORMANCE_TABLE} SET
                        reach=?, impressions=?, reactions=?, comments=?,
                        shares=?, clicks=?, engagement_rate=?, score=?, synced_at=?
                    WHERE post_id=?
                """, [r, imp, rx, cm, sh, cl, er, sc, now, pid])
            else:
                con.execute(f"""
                    INSERT INTO {PERFORMANCE_TABLE}
                        (post_id, created_at, message, reach, impressions, reactions,
                         comments, shares, clicks, engagement_rate, score, synced_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, [pid, p["created_at"], p["message"],
                      r, imp, rx, cm, sh, cl, er, sc, now])
            synced += 1
        return {"synced": synced, "success": True}
    except Exception as exc:
        return {"synced": 0, "error": str(exc)}
    finally:
        con.close()


# ─────────────────────────────────────────────────────────────────────────────
# Top posts & 30-day summary
# ─────────────────────────────────────────────────────────────────────────────

_VALID_METRICS = {"score", "reach", "reactions", "comments", "shares", "engagement_rate"}


def fb_get_top_posts(metric: str = "score", limit: int = 5) -> list[dict]:
    sync_post_performance()
    if not config.db_path.exists():
        return []
    if metric not in _VALID_METRICS:
        metric = "score"
    con = _connect_ro()
    try:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        if PERFORMANCE_TABLE not in tables:
            return []
        rows = con.execute(f"""
            SELECT post_id, created_at, message, reach, reactions,
                   comments, shares, engagement_rate, score
            FROM {PERFORMANCE_TABLE}
            ORDER BY {metric} DESC
            LIMIT {limit}
        """).fetchall()
        return [
            {
                "post_id":         r[0],
                "created_at":      r[1],
                "message":         r[2],
                "reach":           r[3],
                "reactions":       r[4],
                "comments":        r[5],
                "shares":          r[6],
                "engagement_rate": r[7],
                "score":           r[8],
            }
            for r in rows
        ]
    finally:
        con.close()


def fb_get_last_30_days() -> dict:
    page  = fb_get_page_insights()
    posts = fb_get_posts(limit=30)
    valid = [p for p in posts if "error" not in p]
    top   = max(valid, key=lambda p: p.get("score", 0), default=None) if valid else None
    return {
        "page_insights": page,
        "post_count":    len(valid),
        "top_post":      top,
        "recent_posts":  valid[:5],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Content recommendation
# ─────────────────────────────────────────────────────────────────────────────

_BEST_TIMES = [
    ("09:00", "Morning — phones checked after waking"),
    ("12:00", "Lunch break — peak mobile traffic"),
    ("19:00", "Evening — post-work scroll"),
    ("21:00", "Night — relaxed browsing"),
]

_TYPE_HOOKS: dict[str, list[str]] = {
    "comment_bait": [
        "เลือก A หรือ B? คนส่วนใหญ่ตอบผิดหมด 😅",
        "ใครเคยเจอแบบนี้บ้าง? Comment ด้วยนะ 👇",
        "คำถามนี้ไม่มีคำตอบถูกหรือผิด — แค่อยากรู้ว่าคุณคิดยังไง",
    ],
    "weird_product": [
        "ของชิ้นนี้มีอยู่จริง และขายดีมาก 😳",
        "ทำไมถึงมีคนซื้อสิ่งนี้ได้?",
        "เจอของนี้แล้วต้องหยุดคิด ว่าโลกไปถึงไหนแล้ว",
    ],
    "nostalgia": [
        "ใครที่โตมาในยุค 90s จะเข้าใจทันที",
        "ของชิ้นนี้พาความทรงจำกลับมา 🥹",
        "เด็กยุคนี้ไม่รู้จักแน่นอน",
    ],
    "visual_curiosity": [
        "ดูนานแค่ไหนถึงจะเห็น?",
        "ภาพนี้ซ่อนอะไรไว้ — ลองหาดู 👀",
        "ทำไมภาพนี้ถึงดูไม่ออก?",
    ],
    "trending": [
        "กระแสนี้มาแรงมาก — คุณเห็นแล้วหรือยัง?",
        "ทุกคนกำลังพูดถึงสิ่งนี้อยู่",
        "เทรนด์ใหม่ที่กำลังมาแรงใน Shopee",
    ],
    "affiliate": [
        "ของชิ้นนี้ขายดีอันดับต้นๆ ของสัปดาห์",
        "ราคานี้ไม่น่าเชื่อว่าจะมีจริง",
        "รีวิวจากลูกค้าจริง — ไม่ได้แต่ง",
    ],
}

_CALENDAR_CYCLE = [
    "comment_bait", "weird_product", "comment_bait",
    "nostalgia",    "comment_bait",  "visual_curiosity",
    "trending",     "comment_bait",  "weird_product",    "affiliate",
]


def get_content_recommendation() -> dict:
    best_type   = "comment_bait"
    best_reason = "default strategy — no performance data yet"

    if config.db_path.exists():
        try:
            con    = _connect_ro()
            tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
            if PERFORMANCE_TABLE in tables:
                row = con.execute(f"""
                    SELECT post_type, AVG(score) as avg_score, COUNT(*) as cnt
                    FROM {PERFORMANCE_TABLE}
                    WHERE score > 0 AND post_type != ''
                    GROUP BY post_type
                    ORDER BY avg_score DESC
                    LIMIT 1
                """).fetchone()
                if row and row[2] >= 3:
                    best_type   = row[0]
                    best_reason = f"avg score {row[1]:.2f} from {row[2]} tracked posts"
            con.close()
        except Exception:
            pass

    if best_reason.startswith("default"):
        day_offset = (datetime.now() - datetime(2026, 1, 1)).days
        best_type   = _CALENDAR_CYCLE[abs(day_offset) % len(_CALENDAR_CYCLE)]
        best_reason = f"calendar cycle — slot {(abs(day_offset) % len(_CALENDAR_CYCLE)) + 1}/10"

    time_label, time_note = _BEST_TIMES[datetime.now().weekday() % len(_BEST_TIMES)]
    hook = random.choice(_TYPE_HOOKS.get(best_type, _TYPE_HOOKS["comment_bait"]))

    return {
        "recommended_type": best_type,
        "recommended_time": time_label,
        "time_note":        time_note,
        "hook":             hook,
        "reason":           best_reason,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Image post
# ─────────────────────────────────────────────────────────────────────────────

def fb_post_with_image(message: str, image_url: str) -> dict:
    ok, err = _creds_ok()
    if not ok:
        return {"error": err, "success": False}
    if not message.strip():
        return {"error": "Message cannot be empty", "success": False}
    if not image_url.strip():
        return {"error": "image_url cannot be empty", "success": False}
    try:
        data     = _fb_post(f"{_page_id()}/photos", {"caption": message, "url": image_url})
        photo_id = data.get("id", "")
        post_id  = data.get("post_id", photo_id)
        post_url = (
            f"https://www.facebook.com/{post_id.replace('_', '/posts/')}"
            if post_id else ""
        )
        return {"post_id": post_id, "photo_id": photo_id, "url": post_url, "success": True}
    except Exception as exc:
        return {"error": str(exc), "success": False}


# ─────────────────────────────────────────────────────────────────────────────
# Scheduled posts
# ─────────────────────────────────────────────────────────────────────────────

def fb_schedule_post(
    message: str,
    publish_at: str,
    post_type: str = "manual",
    image_url: str = "",
    link: str = "",
    note: str = "",
) -> dict:
    if not message.strip():
        return {"error": "Message cannot be empty", "success": False}
    con = _connect_rw()
    try:
        _init_scheduled(con)
        max_id = con.execute(
            f"SELECT COALESCE(MAX(id), 0) FROM {SCHEDULED_TABLE}"
        ).fetchone()[0]
        new_id = (max_id or 0) + 1
        con.execute(f"""
            INSERT INTO {SCHEDULED_TABLE}
                (id, created_at, message, image_url, link, post_type, publish_at, status, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, [
            new_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            message, image_url, link, post_type, publish_at, note,
        ])
        return {"id": new_id, "publish_at": publish_at, "success": True}
    except Exception as exc:
        return {"error": str(exc), "success": False}
    finally:
        con.close()


def fb_get_scheduled_posts(limit: int = 10) -> list[dict]:
    if not config.db_path.exists():
        return []
    con = _connect_ro()
    try:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        if SCHEDULED_TABLE not in tables:
            return []
        rows = con.execute(f"""
            SELECT id, created_at, message, post_type, publish_at, status, note
            FROM {SCHEDULED_TABLE}
            WHERE status = 'pending'
            ORDER BY publish_at ASC
            LIMIT {limit}
        """).fetchall()
        return [
            {
                "id":         r[0],
                "created_at": r[1],
                "message":    r[2],
                "post_type":  r[3],
                "publish_at": r[4],
                "status":     r[5],
                "note":       r[6],
            }
            for r in rows
        ]
    finally:
        con.close()
