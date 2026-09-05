"""
Automatic product categorization.

Products coming from the external catalog API don't reliably include a
useful/consistent category (see product_api_client.py's notes on field
guessing), and even when they do, providers are inconsistent about naming
("Rose" vs "Roses" vs "Red Roses" vs "Rose Flower" all meaning the same
thing). Rather than trusting the raw category string verbatim, every
product is classified by matching keywords against ALL of its available
text (name, description, API-supplied category, type/tags/metadata) so
that products land in one consistent, deduplicated set of categories no
matter how the source data is worded.

This module is additive/self-contained: it doesn't touch the API client's
request/response handling, caching, or error handling — it only supplies
the `classify_category()` function that decides the "category" value
_normalize_item() stores on each product.
"""

import re

# Canonical categories, in priority order, each with keywords/phrases that
# indicate a product belongs there. Order matters when a product's text
# could plausibly match more than one entry (checked top to bottom, first
# match wins) — e.g. "chocolate covered strawberries" should land in
# Chocolates & Sweets rather than Fruits, so more specific/food-adjacent
# categories are listed before broader ones.
#
# This list is intentionally NOT exhaustive of every possible gift type —
# add more (category_name, [keywords]) tuples here as new kinds of
# products show up; nothing else in the app needs to change.
CATEGORY_RULES = [
    ("Flowers", [
        "rose", "roses", "flower", "flowers", "bouquet", "tulip", "orchid",
        "lily", "lilies", "daisy", "daisies", "peony", "peonies", "blossom",
        "carnation", "hydrangea", "floral",
    ]),
    ("Teddy Bears", [
        "teddy", "teddy bear", "plush", "stuffed animal", "stuffed toy",
        "soft toy", "cuddly toy",
    ]),
    ("Cakes", [
        "cake", "cakes", "cupcake", "cheesecake", "birthday cake",
        "pastry", "pastries",
    ]),
    ("Chocolates & Sweets", [
        "chocolate", "chocolates", "candy", "candies", "sweets", "cookie",
        "cookies", "biscuit", "biscuits", "sweet treat",
    ]),
    ("Pizza / Food", [
        "pizza", "food", "meal", "snack", "snacks", "burger", "pasta",
        "sandwich", "shawarma", "suya", "meat pie", "chicken", "rice",
        "catering", "restaurant",
    ]),
    ("Drinks & Refreshments", [
        "wine", "champagne", "drink", "drinks", "beverage", "beverages",
        "juice", "beer", "cocktail", "whisky", "whiskey", "vodka",
        "liquor", "soda", "smoothie",
    ]),
    ("Gift Baskets", [
        "basket", "hamper", "gift box", "gift set", "gift pack", "combo",
        "bundle",
    ]),
    ("Jewelry", [
        "jewelry", "jewellery", "necklace", "bracelet", "ring", "rings",
        "earring", "earrings", "pendant", "gold chain", "diamond",
        "watch", "watches",
    ]),
    ("Perfumes & Fragrances", [
        "perfume", "perfumes", "fragrance", "cologne", "scent", "body spray",
    ]),
    ("Balloons", [
        "balloon", "balloons",
    ]),
    ("Home & Decor", [
        "decor", "vase", "candle", "candles", "photo frame", "frame",
        "mug", "pillow", "cushion", "blanket", "wall art", "showpiece",
    ]),
    ("Electronics & Gadgets", [
        "gadget", "electronic", "electronics", "headphone", "headphones",
        "earbud", "earbuds", "speaker", "power bank", "phone case",
        "smartwatch",
    ]),
    ("Fashion & Accessories", [
        "handbag", "hand bag", "scarf", "sunglasses", "wallet", "purse",
        "clothing", "shirt", "dress", "cap", "sneaker", "sneakers",
    ]),
    ("Romantic Gifts", [
        "romantic", "valentine", "valentines", "love", "couple",
        "anniversary gift", "proposal", "date night",
    ]),
    ("Celebration Gifts", [
        "celebrat", "birthday", "congratulat", "party", "graduation",
        "wedding", "anniversary", "new baby", "housewarming",
    ]),
    ("Family Gifts", [
        "family", "mother's day", "mothers day", "father's day",
        "fathers day", "for mom", "for dad", "kids", "children", "baby",
        "grandma", "grandpa", "sibling",
    ]),
]

FALLBACK_CATEGORY = "Gifts"


def _tokenize(*parts):
    """Joins any mix of strings/lists/None into one lowercase search blob."""
    words = []
    for part in parts:
        if not part:
            continue
        if isinstance(part, (list, tuple, set)):
            words.extend(str(p) for p in part if p)
        else:
            words.append(str(part))
    return " ".join(words).lower()


def _matches(keyword, text):
    # Multi-word phrases already have natural word boundaries via spaces.
    # Single-word keywords use \b so e.g. "rose" doesn't match "roseanne".
    if " " in keyword:
        return keyword in text
    return re.search(r"\b" + re.escape(keyword) + r"\b", text) is not None


def classify_category(name=None, description=None, api_category=None, product_type=None, tags=None):
    """Determines a single canonical category for a product using whatever
    information is available: product name, description, the API's own
    category field (if any), product type, and tags/metadata.

    Matching runs over ALL of these fields together (not just api_category)
    so that differently-worded source data — "Rose", "Roses", "Red Roses",
    "Rose Flower" — all resolve to the same canonical "Flowers" category
    instead of creating duplicate near-identical categories.

    Falls back to a cleaned-up version of the API's own category (if it
    provided one) when no keyword rule matches, and only falls back to the
    generic "Gifts" bucket when there's truly nothing useful to go on.
    """
    text = _tokenize(name, description, api_category, product_type, tags)

    for category, keywords in CATEGORY_RULES:
        if any(_matches(kw, text) for kw in keywords):
            return category

    if api_category and str(api_category).strip():
        # Unknown-to-us category from the API — keep it (title-cased for
        # consistency) rather than losing information, but still route it
        # through this single function so future keyword rules can absorb
        # it into a canonical bucket later.
        return str(api_category).strip().title()

    return FALLBACK_CATEGORY
