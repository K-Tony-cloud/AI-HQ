"""Central configuration — paths, column mappings, defaults."""

from pathlib import Path
from dataclasses import dataclass, field

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "shopee.duckdb"

# Shopee affiliate datafeeds use different column names across partners/regions.
# Each key is the canonical name used internally; values are aliases to detect.
COLUMN_ALIASES: dict[str, list[str]] = {
    "product_id":       ["itemid", "item_id", "product_id", "id", "sku_id"],
    "product_name":     ["name", "product_name", "item_name", "title", "product_title"],
    "price":            ["price", "sale_price", "price_min", "current_price", "selling_price", "offer_price"],
    "original_price":   ["price_before_discount", "original_price", "market_price", "mrp"],
    "category":         ["category_name", "cat_name", "category", "catname", "cat"],
    "category_id":      ["catid", "category_id", "cat_id"],
    "sales":            ["sales", "sold", "sold_count", "monthly_sold", "total_sold"],
    "commission_rate":  ["commission_rate", "commission", "comm_rate", "affiliate_commission"],
    "rating":           ["rating_star", "rating", "star_rating", "avg_rating", "item_rating"],
    "rating_count":     ["rating_count", "num_rating", "review_count", "num_reviews"],
    "shop_name":        ["shop_name", "shopname", "seller_name", "store_name"],
    "image":            ["image", "image_url", "item_image", "thumbnail", "img_url"],
    "product_url":      ["product_url", "url", "item_url", "link", "product_link"],
    "affiliate_link":   ["affiliate_link", "deep_link", "tracking_link", "aff_link"],
    "brand":            ["brand", "brand_name"],
}


@dataclass
class Config:
    db_path: Path = field(default_factory=lambda: DB_PATH)
    data_dir: Path = field(default_factory=lambda: DATA_DIR)
    default_table: str = "products"
    # rows shown per page in Rich tables
    display_limit: int = 30


config = Config()


def resolve_column(actual_columns: list[str], canonical: str) -> str | None:
    """Return the first actual column name that matches a canonical alias."""
    aliases = COLUMN_ALIASES.get(canonical, [canonical])
    lower_actual = {c.lower(): c for c in actual_columns}
    for alias in aliases:
        if alias.lower() in lower_actual:
            return lower_actual[alias.lower()]
    return None


def build_column_map(actual_columns: list[str]) -> dict[str, str]:
    """Return {canonical: actual} for every canonical key that has a match."""
    return {
        canonical: col
        for canonical in COLUMN_ALIASES
        if (col := resolve_column(actual_columns, canonical)) is not None
    }
