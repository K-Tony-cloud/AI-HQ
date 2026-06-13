"""Performance service — wraps shopee_engine.performance_engine."""

from __future__ import annotations


def get_top_profit(top: int = 20) -> dict:
    try:
        from shopee_engine.performance_engine import top_profit_products
        df = top_profit_products(top=top)
        return {"success": True, "data": df.to_dict("records"), "total": len(df)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_daily_performance(days: int = 7) -> dict:
    try:
        from shopee_engine.performance_engine import daily_performance
        df = daily_performance(days=days)
        return {"success": True, "data": df.to_dict("records"), "total": len(df)}
    except Exception as e:
        return {"success": False, "error": str(e)}
