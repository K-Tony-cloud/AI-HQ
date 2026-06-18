"""
Facebook Graph API engine — manual post management for อะไรของมัน page.

Reads FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN from environment.
Uses stdlib urllib only — no extra dependencies.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import duckdb

from .config import config

# Load .env so credentials are available whether called from bot or CLI
try:
    from dotenv import load_dotenv
    load_dotenv(config.db_path.parent.parent / ".env")
except ImportError:
    pass

FB_API_VERSION = "v19.0"
FB_BASE        = f"https://graph.facebook.com/{FB_API_VERSION}"

DRAFTS_TABLE = "facebook_drafts"

STATUS_DRAFT   = "draft"
STATUS_POSTED  = "posted"
STATUS_DELETED = "deleted"


# ─────────────────────────────────────────────────────────────────────────────
# Credentials helpers
# ─────────────────────────────────────────────────────────────────────────────

def _page_id() -> str:
    return os.getenv("FACEBOOK_PAGE_ID", "")


def _token() -> str:
    return os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")


def _mask_token(token: str) -> str:
    if len(token) < 12:
        return "***"
    return token[:6] + "..." + token[-4:]


def _creds_ok() -> tuple[bool, str]:
    if not _page_id():
        return False, "FACEBOOK_PAGE_ID not set in .env"
    if not _token():
        return False, "FACEBOOK_PAGE_ACCESS_TOKEN not set in .env"
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fb_get(path: str, **params) -> dict:
    params["access_token"] = _token()
    url = f"{FB_BASE}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", body[:200])
        except Exception:
            msg = body[:200]
        raise RuntimeError(f"Facebook API {e.code}: {msg}") from e


def _fb_post(path: str, data: dict) -> dict:
    data = dict(data)
    data["access_token"] = _token()
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        f"{FB_BASE}/{path}",
        data=encoded,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", body[:200])
        except Exception:
            msg = body[:200]
        raise RuntimeError(f"Facebook API {e.code}: {msg}") from e


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def _connect_rw() -> duckdb.DuckDBPyConnection:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(config.db_path), read_only=False)


def _connect_ro() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(config.db_path), read_only=True)


def _init_drafts(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {DRAFTS_TABLE} (
            id          INTEGER,
            created_at  TEXT,
            post_type   TEXT,
            message     TEXT,
            status      TEXT DEFAULT 'draft',
            post_id     TEXT DEFAULT '',
            posted_at   TEXT DEFAULT '',
            note        TEXT DEFAULT ''
        )
    """)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def fb_get_page_info() -> dict:
    """Return basic page info: id, name, fan_count, category."""
    ok, err = _creds_ok()
    if not ok:
        return {"error": err}
    try:
        data = _fb_get(_page_id(), fields="name,id,fan_count,about,category")
        return {
            "page_id":   data.get("id", ""),
            "name":      data.get("name", ""),
            "fan_count": data.get("fan_count", 0),
            "about":     data.get("about", ""),
            "category":  data.get("category", ""),
            "token_preview": _mask_token(_token()),
        }
    except Exception as exc:
        return {"error": str(exc)}


def fb_post_message(message: str, link: str = "") -> dict:
    """Post a message to the page feed. Returns {post_id, url, success}."""
    ok, err = _creds_ok()
    if not ok:
        return {"error": err, "success": False}
    if not message.strip():
        return {"error": "Message cannot be empty", "success": False}
    try:
        payload: dict[str, str] = {"message": message}
        if link:
            payload["link"] = link
        data = _fb_post(f"{_page_id()}/feed", payload)
        post_id = data.get("id", "")
        post_url = f"https://www.facebook.com/{post_id.replace('_', '/posts/')}" if post_id else ""
        return {"post_id": post_id, "url": post_url, "success": True}
    except Exception as exc:
        return {"error": str(exc), "success": False}


def fb_save_draft(message: str, post_type: str = "manual", note: str = "") -> dict:
    """Save a post draft to DuckDB for review before publishing."""
    con = _connect_rw()
    try:
        _init_drafts(con)
        max_id = con.execute(
            f"SELECT COALESCE(MAX(id), 0) FROM {DRAFTS_TABLE}"
        ).fetchone()[0]
        new_id = (max_id or 0) + 1
        con.execute(f"""
            INSERT INTO {DRAFTS_TABLE} (id, created_at, post_type, message, status, note)
            VALUES (?, ?, ?, ?, 'draft', ?)
        """, [new_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), post_type, message, note])
        return {"id": new_id, "status": STATUS_DRAFT, "success": True}
    except Exception as exc:
        return {"error": str(exc), "success": False}
    finally:
        con.close()


def fb_get_drafts(limit: int = 10, status: str = "") -> list[dict]:
    """List recent drafts. Filter by status if provided."""
    if not config.db_path.exists():
        return []
    con = _connect_ro()
    try:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        if DRAFTS_TABLE not in tables:
            return []
        where = f"WHERE status = '{status}'" if status else ""
        rows = con.execute(f"""
            SELECT id, created_at, post_type, message, status, post_id, note
            FROM {DRAFTS_TABLE}
            {where}
            ORDER BY id DESC
            LIMIT {limit}
        """).fetchall()
        return [
            {
                "id":         r[0],
                "created_at": r[1],
                "type":       r[2],
                "message":    r[3],
                "status":     r[4],
                "post_id":    r[5],
                "note":       r[6],
            }
            for r in rows
        ]
    finally:
        con.close()
