"""
Generic, provider-agnostic client for an external gift-card/product catalog
API. Originally built against TP Gifts Store / TopGiftCard specifically —
that integration has been removed, and this module is kept as a pluggable
scaffold: point PRODUCT_API_BASE_URL / PRODUCT_API_KEY (see config.py) at
whichever provider is configured, and this client's request/response
handling, caching, and fallback logic keep working unchanged. If a new
provider uses different auth or a different response shape, only
_headers()/_normalize_item()/the endpoint path constants below need to
change.

Auth: every request currently sends the key in the X-API-KEY header (never
Bearer, never the URL) — matches the previous provider's convention.

Endpoints used here:
  GET /account   -> confirms the key is valid; { account: {id, name, email, created_at} }
  GET /products  -> paginated catalog; { success, products: [...], pagination: {...} }
  GET /price     -> per-product converted price + availability (helper, not
                    wired into the main catalog fetch since the store already
                    displays the documented NGN base price from /products).

Response contract (from docs):
  Success: {"success": true, ...}
  Error:   {"success": false, "message": "..."}

Status codes (from docs):
  200 success
  401 missing/invalid key or suspended account
  404 not found / not owned by this key
  405 wrong method
  422 missing/invalid parameter
  500 server error

NOTE ON PRODUCT FIELDS: the documentation screenshots provided confirm the
top-level response shape (success/products/pagination) but not the exact
key names inside each product object. _normalize_item() below therefore
accepts several common aliases (name/title, price/amount, image/image_url,
etc.) so the app keeps working either way, and logs a one-time warning if
it has to fall back to an alias so this can be tightened once real product
JSON has been seen (e.g. via test_product_api.py).
"""

import logging
import time
import requests

from routes.category_classifier import classify_category

log = logging.getLogger("product_provider")

ACCOUNT_PATH = "/account"
PRODUCTS_PATH = "/products"
PRICE_PATH = "/price"
PRODUCT_PATH = "/product"

DEFAULT_PAGE_LIMIT = 20
MAX_PAGES_SAFETY = 50  # hard ceiling so a broken pagination response can never loop forever


class ProductApiError(Exception):
    """Base class for all product provider API failures."""


class ProductApiAuthError(ProductApiError):
    """401 — missing/invalid key or suspended account."""


class ProductApiNotFoundError(ProductApiError):
    """404 — not found, or resource not owned by this key."""


class ProductApiValidationError(ProductApiError):
    """422 — missing or invalid parameter."""


class ProductApiServerError(ProductApiError):
    """500 — server error on the product provider's side."""


class ProductApiTimeoutError(ProductApiError):
    """Request didn't complete within the timeout window."""


class ProductApiConnectionError(ProductApiError):
    """Couldn't reach the API at all (DNS/TLS/refused connection/etc)."""


class ProductApiResponseError(ProductApiError):
    """Got a response but it wasn't usable (bad JSON, success:false, wrong shape)."""


def mask_key(key):
    """Masks an API key for safe logging, e.g. '********a7a4'. Never log the full key."""
    if not key:
        return "(not set)"
    if len(key) <= 4:
        return "*" * len(key)
    return "*" * 8 + key[-4:]


def _headers(api_key):
    return {"X-API-KEY": api_key, "Accept": "application/json"}


def _request(method, base_url, path, api_key, params=None, timeout=10):
    """Low-level request wrapper: raises the typed errors above based on
    the documented status codes, and never leaks the API key in an
    exception message."""
    url = f"{base_url.rstrip('/')}{path}"

    try:
        resp = requests.request(method, url, headers=_headers(api_key), params=params, timeout=timeout)
    except requests.exceptions.Timeout as e:
        raise ProductApiTimeoutError(f"Timed out after {timeout}s calling {path}.") from e
    except requests.exceptions.ConnectionError as e:
        raise ProductApiConnectionError(f"Could not connect to {url}: {e}") from e
    except requests.RequestException as e:
        raise ProductApiConnectionError(f"Request to {url} failed: {e}") from e

    if resp.status_code == 401:
        raise ProductApiAuthError(
            "Product provider API authentication failed. Check PRODUCT_API_KEY. "
            f"(key used: {mask_key(api_key)})"
        )
    if resp.status_code == 404:
        raise ProductApiNotFoundError(f"{path} returned 404 (not found, or not owned by this key).")
    if resp.status_code == 405:
        raise ProductApiError(f"{path} returned 405 (wrong HTTP method — this client only uses GET).")
    if resp.status_code == 422:
        try:
            msg = resp.json().get("message", "missing or invalid parameter")
        except ValueError:
            msg = "missing or invalid parameter"
        raise ProductApiValidationError(f"{path} returned 422: {msg}")
    if resp.status_code == 500:
        raise ProductApiServerError(f"{path} returned 500 (product provider server error). Retry later.")
    if resp.status_code != 200:
        raise ProductApiError(f"{path} returned unexpected HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except ValueError as e:
        raise ProductApiResponseError(f"{path} returned HTTP 200 but the body wasn't valid JSON.") from e

    if isinstance(data, dict) and data.get("success") is False:
        raise ProductApiResponseError(f"{path} responded success:false — {data.get('message', 'no message given')}")

    return data


def check_account(base_url, api_key, timeout=10):
    """Confirms the API key is valid and the store is reachable.

    The documented API (see gracegifthub-api-integration-guide.txt) has no
    dedicated /account endpoint — GET /products IS the auth check: a bad
    key gets a 401 from it just the same. So this calls /products (with a
    small limit) and returns the store-level metadata from that response
    instead. Kept as its own function/name so callers (app.py startup
    check, admin "Test API" button, test_product_api.py) don't need to
    change."""
    data = _request("GET", base_url, PRODUCTS_PATH, api_key, params={"limit": 1}, timeout=timeout)
    return {
        "store": data.get("store"),
        "currency": data.get("currency"),
        "count": data.get("count"),
    }


_warned_about_field_guessing = False


def _normalize_item(raw):
    global _warned_about_field_guessing

    name = raw.get("name") or raw.get("title") or raw.get("product_name")
    price = raw.get("price")
    image = raw.get("image_url") or raw.get("image") or raw.get("photo") or raw.get("thumbnail")
    in_stock = raw.get("in_stock")
    if in_stock is None:
        in_stock = raw.get("available")
    if in_stock is None:
        in_stock = raw.get("stock_status", "in_stock") != "out_of_stock"

    if (name is None or price is None or image is None) and not _warned_about_field_guessing:
        log.warning(
            "Product catalog: one or more fields (name/price/image) weren't found under the "
            "expected key and were guessed from an alias. Run test_product_api.py and check the "
            "raw product JSON to confirm the exact field names, then tighten _normalize_item()."
        )
        _warned_about_field_guessing = True

    description = raw.get("description") or ""
    category = classify_category(
        name=name,
        description=description,
        api_category=raw.get("category"),
        product_type=raw.get("type") or raw.get("product_type"),
        tags=raw.get("tags") or raw.get("keywords"),
    )

    return {
        "id": raw.get("id") or raw.get("product_id"),
        "name": name or "Unnamed product",
        "category": category,
        "price": float(price) if price not in (None, "") else 0.0,
        "image_url": image or "",
        "description": description,
        "in_stock": bool(in_stock),
    }


def fetch_products_page(base_url, api_key, page=1, limit=DEFAULT_PAGE_LIMIT, timeout=10):
    """GET /products?page=&limit= — returns (items, pagination_dict) for one page."""
    data = _request(
        "GET", base_url, PRODUCTS_PATH, api_key,
        params={"page": page, "limit": limit}, timeout=timeout,
    )
    items = data.get("products")
    if not isinstance(items, list):
        raise ProductApiResponseError("/products response did not contain a 'products' array.")
    pagination = data.get("pagination") or {}
    return items, pagination


def fetch_all_products(base_url, api_key, limit=DEFAULT_PAGE_LIMIT, timeout=10):
    """Paginates through GET /products, following the documented rule:
    keep requesting while page < total_pages. Stops safely if pagination
    data is missing/inconsistent, and never loops more than MAX_PAGES_SAFETY
    times regardless of what the API reports.

    A failure on page 1 is raised as normal (there's nothing to fall back
    to). A failure on any later page — e.g. a free/limited product provider
    plan that blocks pagination past a certain page, or a transient error —
    does NOT discard the pages already fetched successfully; it stops and
    returns what was collected so far, so one bad page can't wipe out an
    otherwise-working catalog."""
    all_items = []
    page = 1
    total_pages = 1

    while True:
        try:
            items, pagination = fetch_products_page(base_url, api_key, page=page, limit=limit, timeout=timeout)
        except ProductApiError as e:
            if page == 1:
                raise
            log.warning(
                f"Product catalog: page {page} failed ({e}) — returning the "
                f"{len(all_items)} item(s) already fetched from earlier page(s) instead of discarding them."
            )
            break

        all_items.extend(items)

        reported_page = pagination.get("page", page)
        total_pages = pagination.get("total_pages", 1)

        log.info(f"Product catalog: page {reported_page}/{total_pages}, {len(items)} item(s) this page.")

        if not isinstance(total_pages, int) or total_pages < 1:
            log.warning("Product catalog: pagination.total_pages missing or invalid — stopping after this page.")
            break
        if page >= total_pages:
            break
        if page >= MAX_PAGES_SAFETY:
            log.warning(f"Product catalog: hit the {MAX_PAGES_SAFETY}-page safety limit — stopping early.")
            break

        page += 1

    return [_normalize_item(item) for item in all_items if isinstance(item, dict)]


def fetch_price(base_url, api_key, product_id, country=None, timeout=10):
    """GET /price — converted price/currency/availability for one product.
    Not called automatically by the catalog (the store already shows the
    documented NGN base price from /products); use this if/when you need a
    real-time quote or country-specific availability check before checkout."""
    params = {"product_id": product_id}
    if country:
        params["country"] = country
    return _request("GET", base_url, PRICE_PATH, api_key, params=params, timeout=timeout)


# ---------- Simple in-process cache ----------
# Avoids hammering the external API on every visitor while still refreshing
# often enough for newly added products to show up. TTL is configurable via
# PRODUCT_CACHE_TTL_SECONDS (default 5 minutes). Falls back to the last good
# cached result (rather than failing outright) if a refresh attempt errors.
_cache = {"products": None, "fetched_at": 0, "last_error": None}


def get_products_cached(base_url, api_key, ttl_seconds=300, limit=DEFAULT_PAGE_LIMIT, timeout=10, force_refresh=False):
    now = time.time()
    is_fresh = _cache["products"] is not None and (now - _cache["fetched_at"]) < ttl_seconds

    if is_fresh and not force_refresh:
        return _cache["products"], True  # (products, served_from_cache)

    try:
        products = fetch_all_products(base_url, api_key, limit=limit, timeout=timeout)
        _cache["products"] = products
        _cache["fetched_at"] = now
        _cache["last_error"] = None
        return products, False
    except ProductApiError as e:
        _cache["last_error"] = str(e)
        if _cache["products"] is not None:
            log.warning(f"Product catalog: refresh failed ({e}) — serving last known-good cached catalog.")
            return _cache["products"], True
        raise


def clear_cache():
    _cache["products"] = None
    _cache["fetched_at"] = 0
    _cache["last_error"] = None
