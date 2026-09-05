"""
Diagnostic test for the product catalog API integration (works with whichever provider is configured in .env).

Run this yourself to get a real, first-hand PASS/FAIL — this sandbox has
no outbound network access, so Claude cannot execute this test against
the live product provider API itself.

USAGE:
    cd backend
    pip install -r requirements.txt
    python test_product_api.py

Reads PRODUCT_API_BASE_URL / PRODUCT_API_KEY from backend/.env (via
config.py). Optionally override:
    python test_product_api.py <base_url> <api_key>

Never prints the full API key.
"""

import sys

try:
    from config import Config
    DEFAULT_BASE_URL = Config.PRODUCT_API_BASE_URL
    DEFAULT_API_KEY = Config.PRODUCT_API_KEY
except Exception:
    DEFAULT_BASE_URL = ""
    DEFAULT_API_KEY = ""

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
API_KEY = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_API_KEY

from routes.product_api_client import (
    check_account,
    fetch_products_page,
    fetch_all_products,
    mask_key,
    ProductApiError,
    ProductApiAuthError,
)


def line():
    print("-" * 50)


def run():
    print("=== PRODUCT PROVIDER API TEST ===\n")

    print("Environment:")
    print(f"  API Base URL: {'PASS' if BASE_URL else 'FAIL (not set)'} — {BASE_URL or '(empty)'}")
    print(f"  API Key: {'PRESENT (' + mask_key(API_KEY) + ')' if API_KEY else 'MISSING'}")
    print()

    if not BASE_URL or not API_KEY:
        print("Cannot continue — PRODUCT_API_BASE_URL and/or PRODUCT_API_KEY are not set.")
        print("Fill them in backend/.env, or pass them as arguments:")
        print("  python test_product_api.py <base_url> <api_key>")
        print("\nFINAL RESULT: FAIL")
        return

    overall_pass = True

    # ---- /account ----
    print("Account:")
    try:
        account = check_account(BASE_URL, API_KEY)
        print("  Authentication: PASS")
        print(f"  Account: {account}")
    except ProductApiAuthError as e:
        print("  Authentication: FAIL")
        print(f"  {e}")
        print("\nFINAL RESULT: FAIL (fix PRODUCT_API_KEY before continuing)")
        return
    except ProductApiError as e:
        print("  Authentication: FAIL")
        print(f"  {e}")
        print("\nFINAL RESULT: FAIL")
        return
    print()

    # ---- /products (first page) ----
    print("Products:")
    try:
        items, pagination = fetch_products_page(BASE_URL, API_KEY, page=1, limit=20)
        print("  Endpoint: PASS")
        print(f"  Products returned (page 1): {len(items)}")
        print(f"  Pagination: {'PASS' if pagination else 'FAIL (missing)'}")
        if pagination:
            print(f"  Total products: {pagination.get('total')}")
            print(f"  Total pages: {pagination.get('total_pages')}")
        else:
            overall_pass = False
    except ProductApiError as e:
        print(f"  Endpoint: FAIL — {e}")
        print("\nFINAL RESULT: FAIL")
        return
    print()

    # ---- Full pagination walk ----
    print("Pagination walk (all pages):")
    try:
        all_products = fetch_all_products(BASE_URL, API_KEY)
        print(f"  Additional pages requested successfully: PASS")
        print(f"  Total products fetched across all pages: {len(all_products)}")
    except ProductApiError as e:
        print(f"  FAIL — {e}")
        overall_pass = False
        all_products = items  # fall back to page 1 for the parsing check below
    print()

    # ---- Product field parsing ----
    print("Product parsing:")
    if all_products:
        sample = all_products[0]
        id_ok = sample.get("id") is not None
        name_ok = bool(sample.get("name")) and sample.get("name") != "Unnamed product"
        price_ok = isinstance(sample.get("price"), (int, float)) and sample.get("price") > 0
        print(f"  Product ID: {'PASS' if id_ok else 'FAIL'}")
        print(f"  Product name: {'PASS' if name_ok else 'FAIL'}")
        print(f"  Product price: {'PASS' if price_ok else 'FAIL'}")
        print(f"  Sample (normalized): {sample}")
        if not (id_ok and name_ok and price_ok):
            overall_pass = False
    else:
        print("  No products returned to parse — check the account has products, or check page/limit params.")
        overall_pass = False
    print()

    print("FINAL RESULT:", "PASS" if overall_pass else "FAIL")


if __name__ == "__main__":
    run()
