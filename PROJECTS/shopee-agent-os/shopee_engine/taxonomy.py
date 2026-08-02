"""Site taxonomy: canonical category slugs and Shopee-to-site mapping.

Rules:
- CANONICAL_CATEGORIES is the only source of truth for valid site category slugs.
- Raw Shopee/datafeed categories must be mapped through _RAW_TO_CANONICAL before use.
- Any category not in CANONICAL_CATEGORIES must be blocked at review/publish.
- Raw category strings containing '&', spaces, or display labels must NEVER be used as URL slugs.
"""

from __future__ import annotations

CANONICAL_CATEGORIES: dict[str, str] = {
    "home-living":    "บ้านและครัว",
    "mobile-gadgets": "มือถือ & แกดเจ็ต",
    "beauty":         "ความงาม",
    "health":         "สุขภาพ",
    "baby-kids":      "แม่และเด็ก",
    "sports":         "กีฬา",
    "food-drinks":    "อาหาร & เครื่องดื่ม",
}

# Raw Shopee/datafeed category name (global_category1/2/3) → canonical site slug
_RAW_TO_CANONICAL: dict[str, str] = {
    # Mobile & gadgets
    "USB & Mobile Fans":    "mobile-gadgets",
    "USB Fans":             "mobile-gadgets",
    "Mobile Fans":          "mobile-gadgets",
    "Fans":                 "mobile-gadgets",
    "Powerbanks":                     "mobile-gadgets",
    "Power Banks":                    "mobile-gadgets",
    "Powerbanks & Batteries":         "mobile-gadgets",
    "Power Banks & Batteries":        "mobile-gadgets",
    "Batteries":                      "mobile-gadgets",
    "Electric Sockets & Extension Cords": "mobile-gadgets",
    "Extension Cords":                "mobile-gadgets",
    "Mobile Lens":                    "mobile-gadgets",
    "Phone Lenses":                   "mobile-gadgets",
    "Mobile Accessories":             "mobile-gadgets",
    "Mobile & Gadgets":     "mobile-gadgets",
    "Electronics":          "mobile-gadgets",
    "Headphones":              "mobile-gadgets",
    "Speakers":                "mobile-gadgets",
    "Smart Watches":           "mobile-gadgets",
    "Cables & Converters":     "mobile-gadgets",
    "Chargers":                "mobile-gadgets",
    "Computer Accessories":    "mobile-gadgets",
    "Gaming Mice":             "mobile-gadgets",
    "Gaming Keyboards":        "mobile-gadgets",
    "Gaming Headsets":         "mobile-gadgets",
    "Gaming Monitors":         "mobile-gadgets",
    "Computer Peripherals":    "mobile-gadgets",
    "Tablets":                 "mobile-gadgets",
    "Laptops":                 "mobile-gadgets",
    "Cameras":                 "mobile-gadgets",
    # Home & living
    "Home & Living":           "home-living",
    "Home Appliances":         "home-living",
    "Large Household Appliances": "home-living",
    "Futon & Shoe Dryers":     "home-living",
    "Shoe Dryers":             "home-living",
    "Kitchen":                 "home-living",
    "Furniture":               "home-living",
    "Bedding":                 "home-living",
    "Storage & Organisation":  "home-living",
    "Cleaning":                "home-living",
    # Beauty
    "Beauty":                 "beauty",
    "Skincare":               "beauty",
    "Makeup":                 "beauty",
    "Fragrances":             "beauty",
    "Hair Care":              "beauty",
    "Facial Serum & Essence": "beauty",
    "Facial Serums":          "beauty",
    "Serums & Essences":      "beauty",
    "Face Care":              "beauty",
    "Moisturisers":           "beauty",
    "Sunscreen":              "beauty",
    # Health
    "Health":               "health",
    "Healthcare":           "health",
    "Medical Supplies":     "health",
    "Vitamins & Supplements": "health",
    "Sports Nutrition":     "health",
    # Baby & kids
    "Mom & Baby":           "baby-kids",
    "Baby":                 "baby-kids",
    "Kids":                 "baby-kids",
    "Toys & Games":         "baby-kids",
    # Sports
    "Sports":               "sports",
    "Sports & Outdoors":    "sports",
    "Outdoor":              "sports",
    "Fitness":              "sports",
    "Camping & Hiking":     "sports",
    # Food & drinks
    "Food & Beverages":     "food-drinks",
    "Food":                 "food-drinks",
    "Drinks":               "food-drinks",
    "Snacks":               "food-drinks",
}

# Raw Shopee category → (subcategory_slug, subcategory_label)
_RAW_TO_SUBCATEGORY: dict[str, tuple[str, str]] = {
    "USB & Mobile Fans":  ("usb-mobile-fans", "USB & Mobile Fans"),
    "USB Fans":           ("usb-mobile-fans", "USB & Mobile Fans"),
    "Mobile Fans":        ("usb-mobile-fans", "USB & Mobile Fans"),
    "Fans":               ("usb-mobile-fans", "USB & Mobile Fans"),
    "Powerbanks":                     ("powerbanks", "Powerbanks"),
    "Power Banks":                    ("powerbanks", "Powerbanks"),
    "Powerbanks & Batteries":         ("powerbanks", "Powerbanks"),
    "Power Banks & Batteries":        ("powerbanks", "Powerbanks"),
    "Headphones":         ("headphones", "หูฟัง"),
    "Smart Watches":      ("smart-watches", "สมาร์ทวอทช์"),
    "Skincare":           ("skincare", "สกินแคร์"),
    "Makeup":             ("makeup", "เครื่องสำอาง"),
}


def map_to_canonical(raw_category: str) -> tuple[str, str] | None:
    """Map a raw Shopee category string to (canonical_slug, thai_label).

    Returns None if no mapping exists — caller must block review/publish.
    """
    slug = _RAW_TO_CANONICAL.get(raw_category)
    if not slug:
        return None
    label = CANONICAL_CATEGORIES[slug]
    return (slug, label)


def resolve_subcategory(raw_category: str) -> tuple[str, str]:
    """Return (subcategory_slug, subcategory_label) for a raw Shopee category.

    Returns ('', '') when no subcategory mapping exists.
    """
    return _RAW_TO_SUBCATEGORY.get(raw_category, ("", ""))


def is_canonical(category: str) -> bool:
    """Return True if category is already a canonical site slug."""
    return category in CANONICAL_CATEGORIES
