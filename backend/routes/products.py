import logging
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import or_, func
from models import db, Product
from routes.product_api_client import (
    get_products_cached,
    clear_cache,
    mask_key,
    ProductApiError,
    ProductApiAuthError,
    ProductApiTimeoutError,
    ProductApiConnectionError,
    ProductApiResponseError,
)

products_bp = Blueprint("products", __name__, url_prefix="/api/products")
log = logging.getLogger("product_provider")


def _local_products(category=None):
    query = Product.query.filter_by(in_stock=True)
    if category:
        query = query.filter_by(category=category)
    return [p.to_dict() for p in query.all()]


def _sync_products_to_db(products):
    """Upserts the live catalog into the local products table, keyed by the
    same id the API uses. Cart/order rows have a foreign key to this table,
    so this keeps 'Add to cart' working against live products instead of
    only the old seeded sample rows."""
    for p in products:
        pid = p.get("id")
        if pid is None:
            continue
        existing = Product.query.get(pid)
        if existing:
            existing.name = p.get("name") or existing.name
            existing.category = p.get("category") or existing.category
            existing.price = p.get("price") if p.get("price") is not None else existing.price
            existing.image_url = p.get("image_url") or existing.image_url
            existing.description = p.get("description") or existing.description
            existing.in_stock = p.get("in_stock", existing.in_stock)
        else:
            db.session.add(Product(
                id=pid,
                name=p.get("name") or "Unnamed product",
                category=p.get("category") or "Gifts",
                price=p.get("price") or 0,
                image_url=p.get("image_url") or "",
                description=p.get("description") or "",
                in_stock=p.get("in_stock", True),
            ))
    db.session.commit()


@products_bp.route("", methods=["GET"])
def list_products():
    category = request.args.get("category")
    force_refresh = request.args.get("refresh") == "1"
    base_url = current_app.config.get("PRODUCT_API_BASE_URL")
    api_key = current_app.config.get("PRODUCT_API_KEY")

    if base_url and api_key:
        try:
            products, from_cache = get_products_cached(
                base_url, api_key,
                ttl_seconds=current_app.config.get("PRODUCT_CACHE_TTL_SECONDS", 300),
                force_refresh=force_refresh,
            )
            log.info(
                f"Product catalog: served {len(products)} product(s) "
                f"({'cache' if from_cache else 'live fetch'})."
            )
            try:
                _sync_products_to_db(products)
            except Exception as e:
                db.session.rollback()
                log.error(f"Product catalog: failed to sync live catalog into local DB: {e}")

            if category:
                products = [p for p in products if p.get("category") == category]
            return jsonify(products)
        except ProductApiAuthError as e:
            log.error(f"Product provider API authentication failed. Check PRODUCT_API_KEY "
                       f"(key: {mask_key(api_key)}). Falling back to local sample products. Detail: {e}")
        except ProductApiTimeoutError as e:
            log.warning(f"Product provider API timed out — falling back to local sample products: {e}")
        except ProductApiConnectionError as e:
            log.warning(f"Product provider API unreachable — falling back to local sample products: {e}")
        except ProductApiResponseError as e:
            log.warning(f"Product provider API returned an unusable response — falling back to local sample products: {e}")
        except ProductApiError as e:
            log.warning(f"Product provider API unavailable — falling back to local sample products: {e}")
    else:
        log.warning("Product provider API not configured (PRODUCT_API_BASE_URL/PRODUCT_API_KEY missing) — "
                    "using local sample products.")

    log.warning("Serving LOCAL SAMPLE products, not a live external catalog.")
    return jsonify(_local_products(category))


@products_bp.route("/search", methods=["GET"])
def search_products():
    """Global search across name, description and category. Works against
    whatever the live catalog most recently synced into the local table
    (list_products() keeps this table up to date), so it works alongside
    the existing product provider integration without touching it."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])
    like = f"%{q}%"
    matches = Product.query.filter(
        Product.in_stock.is_(True),
        or_(
            Product.name.ilike(like),
            Product.description.ilike(like),
            Product.category.ilike(like),
        ),
    ).all()
    return jsonify([p.to_dict() for p in matches])


@products_bp.route("/categories", methods=["GET"])
def list_categories():
    """Distinct categories currently present in the local catalog, so the
    storefront can offer category browsing without breaking the existing
    single live-feed integration."""
    rows = db.session.query(Product.category, func.count(Product.id)).filter(
        Product.in_stock.is_(True)
    ).group_by(Product.category).order_by(Product.category.asc()).all()
    return jsonify([{"category": c, "count": n} for c, n in rows if c])


@products_bp.route("/<int:product_id>", methods=["GET"])
def get_product(product_id):
    product = Product.query.get(product_id)
    if product:
        return jsonify(product.to_dict())

    # Not synced locally yet (e.g. direct link before the list endpoint
    # ran) — check the live catalog cache/fetch and sync on demand.
    base_url = current_app.config.get("PRODUCT_API_BASE_URL")
    api_key = current_app.config.get("PRODUCT_API_KEY")
    if base_url and api_key:
        try:
            products, _ = get_products_cached(
                base_url, api_key,
                ttl_seconds=current_app.config.get("PRODUCT_CACHE_TTL_SECONDS", 300),
            )
            match = next((p for p in products if p.get("id") == product_id), None)
            if match:
                try:
                    _sync_products_to_db([match])
                except Exception as e:
                    db.session.rollback()
                    log.error(f"Product catalog: failed to sync product {product_id}: {e}")
                return jsonify(match)
        except ProductApiError as e:
            log.warning(f"Product provider API unavailable while resolving product {product_id}: {e}")

    return jsonify({"error": "Product not found."}), 404


@products_bp.route("/refresh", methods=["POST"])
def refresh_products():
    """Manually clears the product cache so the next /api/products call
    re-fetches from the configured product provider immediately. No API key is exposed here."""
    clear_cache()
    return jsonify({"cleared": True})
