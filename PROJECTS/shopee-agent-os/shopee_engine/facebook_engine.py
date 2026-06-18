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


def fb_debug() -> dict:
    """Full token/page diagnostic — returns raw API responses for every call."""
    result: dict = {
        "page_id":       _page_id(),
        "token_preview": _mask_token(_token()),
        "token_set":     bool(_token()),
        "page_id_set":   bool(_page_id()),
    }

    if not _token():
        result["diagnosis"] = ["❌ FACEBOOK_PAGE_ACCESS_TOKEN is not set in .env"]
        return result
    if not _page_id():
        result["diagnosis"] = ["❌ FACEBOOK_PAGE_ID is not set in .env"]
        return result

    # ── 1. GET /me ────────────────────────────────────────────────────────────
    try:
        me = _fb_get("me", fields="id,name")
        result["me"] = me
        # If /me returns the same id as FACEBOOK_PAGE_ID → page token
        if me.get("id") == str(_page_id()):
            result["token_kind"] = "page_token"
        else:
            result["token_kind"] = "user_token"
    except Exception as exc:
        result["me_raw_error"] = str(exc)
        result["token_kind"] = "invalid_or_expired"

    # ── 2. GET /me/permissions ────────────────────────────────────────────────
    try:
        pdata = _fb_get("me/permissions")
        granted = [
            p["permission"]
            for p in pdata.get("data", [])
            if p.get("status") == "granted"
        ]
        result["permissions"] = granted
    except Exception as exc:
        result["permissions_raw_error"] = str(exc)
        result["permissions"] = []

    # ── 3. GET /me/accounts ───────────────────────────────────────────────────
    try:
        accts = _fb_get("me/accounts", fields="id,name,category,tasks")
        result["accounts"] = accts.get("data", [])
    except Exception as exc:
        result["accounts_raw_error"] = str(exc)
        result["accounts"] = []

    # ── 4. GET /{page_id} ─────────────────────────────────────────────────────
    try:
        page = _fb_get(_page_id(), fields="id,name,fan_count,category")
        result["page"] = page
    except Exception as exc:
        result["page_raw_error"] = str(exc)

    # ── 5. POST /{page_id}/feed — capture raw HTTP body ───────────────────────
    try:
        payload = {
            "message":      "[DEBUG PROBE — ignore]",
            "access_token": _token(),
        }
        encoded = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{FB_BASE}/{_page_id()}/feed",
            data=encoded,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", errors="replace")
            result["post_test"] = {"success": True, "raw_body": body}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        result["post_test"] = {
            "success":     False,
            "http_status": exc.code,
            "raw_body":    raw,
        }
        try:
            result["post_test"]["parsed"] = json.loads(raw)
        except Exception:
            pass
    except Exception as exc:
        result["post_test"] = {"success": False, "error": str(exc)}

    # ── Diagnosis ─────────────────────────────────────────────────────────────
    diagnosis: list[str] = []
    kind = result.get("token_kind", "unknown")

    if kind == "invalid_or_expired":
        diagnosis.append("❌ Token is INVALID or EXPIRED — /me call failed")
    elif kind == "user_token":
        diagnosis.append(
            "⚠️ Token is a USER TOKEN — you need a PAGE ACCESS TOKEN.\n"
            "   Get one from Graph API Explorer → switch dropdown to 'Page Token'."
        )
    elif kind == "page_token":
        diagnosis.append("✅ Token is a PAGE TOKEN")

    required = {"pages_manage_posts", "pages_read_engagement"}
    granted_set = set(result.get("permissions", []))
    missing = required - granted_set
    if missing and kind != "page_token":
        diagnosis.append(f"❌ Missing permissions: {', '.join(sorted(missing))}")
    elif not result.get("permissions") and kind == "page_token":
        diagnosis.append(
            "ℹ️ /me/permissions returns nothing for page tokens — that is normal.\n"
            "   Permissions are embedded in the token itself."
        )

    accts = result.get("accounts", [])
    page_ids_in_accounts = [str(a.get("id")) for a in accts]
    if accts and str(_page_id()) not in page_ids_in_accounts:
        diagnosis.append(
            f"❌ Page ID {_page_id()} not found in /me/accounts — "
            "token may belong to a different user or wrong page."
        )
    elif accts and str(_page_id()) in page_ids_in_accounts:
        matched = next(a for a in accts if str(a.get("id")) == str(_page_id()))
        tasks = matched.get("tasks", [])
        diagnosis.append(f"✅ Page found in /me/accounts — tasks: {tasks or 'none listed'}")

    post = result.get("post_test", {})
    if post.get("success"):
        diagnosis.append("✅ TEST POST SUCCEEDED (was actually published — delete it!)")
    else:
        parsed = post.get("parsed", {})
        fb_err = parsed.get("error", {})
        if fb_err:
            diagnosis.append(
                f"📋 Post error {post.get('http_status')}: "
                f"[{fb_err.get('type','?')} #{fb_err.get('code','?')}/{fb_err.get('error_subcode','?')}] "
                f"{fb_err.get('message','')}"
            )
        elif post.get("error"):
            diagnosis.append(f"❌ Post network error: {post['error']}")

    result["diagnosis"] = diagnosis
    return result
