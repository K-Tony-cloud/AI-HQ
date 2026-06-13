"""Content service — wraps shopee_engine.content_engine."""

from __future__ import annotations

import json


def generate_content_pack(keyword: str, provider: str = "auto") -> dict:
    try:
        from shopee_engine.content_engine import content_pack
        result = content_pack(keyword, provider=provider)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_queue() -> dict:
    try:
        from shopee_engine.content_engine import queue_list
        df = queue_list()
        return {"success": True, "data": df.to_dict("records"), "total": len(df)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def approve_queue_item(item_id: int) -> dict:
    try:
        from shopee_engine.content_engine import queue_approve
        ok = queue_approve(item_id)
        return {"success": ok, "id": item_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _safe_json(raw: str | None) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else [data]
    except Exception:
        return [str(raw)]
