"""Operator service — wraps shopee_engine.operator_center."""

from __future__ import annotations

from typing import Optional


def get_morning_brief(top: int = 5) -> dict:
    try:
        from shopee_engine.operator_center import morning_brief
        data = morning_brief(top=top)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_executive_summary() -> dict:
    try:
        from shopee_engine.operator_center import executive_summary
        data = executive_summary()
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_category_brief(category: str, top: int = 20) -> dict:
    try:
        from shopee_engine.operator_center import category_brief
        data = category_brief(category=category, top=top)
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": str(e)}
