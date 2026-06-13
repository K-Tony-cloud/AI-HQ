"""Discovery service — wraps shopee_engine.discovery and operator_center."""

from __future__ import annotations

from typing import Optional


def get_top_opportunities(category: Optional[str] = None, top: int = 20) -> dict:
    try:
        from shopee_engine.discovery import top_opportunities
        df = top_opportunities(top=top, category=category)
        return {"success": True, "data": df.to_dict("records"), "total": len(df)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_top_viral(category: Optional[str] = None, top: int = 20, price_max: float = 9999.0) -> dict:
    try:
        from shopee_engine.discovery import top_viral
        df = top_viral(top=top, price_max=price_max, category=category)
        return {"success": True, "data": df.to_dict("records"), "total": len(df)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_daily_picks(top: int = 5) -> dict:
    try:
        from shopee_engine.discovery import daily_picks
        picks = daily_picks(top=top)
        # picks is dict[bucket_name, DataFrame]
        result: dict[str, list] = {}
        for bucket, df in picks.items():
            result[bucket] = df.head(top).to_dict("records") if not df.empty else []
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


def find_products(keyword: str, category: Optional[str] = None, top: int = 15) -> dict:
    try:
        from shopee_engine.discovery import find_winning_products
        df = find_winning_products(
            keyword=keyword,
            category=category,
            top=top,
        )
        return {"success": True, "data": df.to_dict("records"), "total": len(df)}
    except Exception as e:
        return {"success": False, "error": str(e)}
