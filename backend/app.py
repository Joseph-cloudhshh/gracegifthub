import os

from flask import Flask, send_from_directory
from flask_cors import CORS
from config import Config
from models import db

from routes.auth import auth_bp
from routes.products import products_bp
from routes.cart import cart_bp
from routes.orders import orders_bp
from routes.payments import payments_bp
from routes.addresses import addresses_bp
from routes.wallet import wallet_bp
from routes.webhooks import webhooks_bp
from routes.public_settings import public_settings_bp
from routes.admin.views import admin_views_bp
from routes.admin.api import admin_api_bp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))


def create_app():
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
    app.config.from_object(Config)

    # ALLOWED_ORIGINS: comma-separated list of frontend origins allowed to call
    # this API cross-domain, e.g. "https://yourdomain.com,https://your-site.netlify.app".
    # Leave unset (defaults to "*") only while frontend+backend share one domain.
    allowed_origins = os.getenv("ALLOWED_ORIGINS", "*")
    origins = [o.strip() for o in allowed_origins.split(",")] if allowed_origins != "*" else "*"
    CORS(app, supports_credentials=True, origins=origins)
    db.init_app(app)

    # Customer blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(addresses_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(public_settings_bp)

    # Admin blueprints (registered BEFORE the catch-all static route)
    app.register_blueprint(admin_views_bp)
    app.register_blueprint(admin_api_bp)

    # Serve customer frontend
    @app.route("/")
    def landing():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.route("/<path:path>")
    def static_files(path):
        # Don't let the catch-all swallow /admin routes
        if path.startswith("admin"):
            from flask import abort
            abort(404)
        return send_from_directory(FRONTEND_DIR, path)

    with app.app_context():
        db.create_all()
        _init_admin()

    return app


def _init_admin():
    """Create the initial admin account from environment variables if none exists."""
    from models import AdminUser
    import os
    if AdminUser.query.count() == 0:
        email = os.getenv("ADMIN_EMAIL", "admin@gmail.com")
        password = os.getenv("ADMIN_PASSWORD", "admin1234")
        admin = AdminUser(email=email, full_name="Store Administrator")
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        print(f"[Gracegifthub] Initial admin account created: {email}")


def print_product_api_status(app):
    from routes.product_api_client import (
        check_account, fetch_products_page, mask_key,
        ProductApiError, ProductApiAuthError, ProductApiTimeoutError,
        ProductApiConnectionError, ProductApiResponseError,
    )
    base_url = app.config.get("PRODUCT_API_BASE_URL")
    api_key = app.config.get("PRODUCT_API_KEY")
    print("\n" + "-" * 60)
    print(f"Product catalog API configured: {'YES' if (base_url and api_key) else 'NO'}")
    if not base_url or not api_key:
        print("PRODUCT_API_BASE_URL and/or PRODUCT_API_KEY are not set — using seeded sample products.")
        print("-" * 60 + "\n")
        return
    print(f"Product catalog API base URL: {base_url}")
    print(f"Product catalog API key: {mask_key(api_key)}")
    try:
        account = check_account(base_url, api_key)
        print(f"Product catalog API /account: PASS ({account.get('email', account)})")
    except ProductApiError as e:
        print(f"Product catalog API /account: FAILED — {e}")
        print("-" * 60 + "\n")
        return
    try:
        items, pagination = fetch_products_page(base_url, api_key, page=1, limit=20)
        total = pagination.get("total", len(items))
        print(f"Product catalog API /products: PASS — {len(items)} item(s), {total} total.")
    except ProductApiError as e:
        print(f"Product catalog API /products: FAILED — {e}")
    print("-" * 60 + "\n")


if __name__ == "__main__":
    app = create_app()
    print_product_api_status(app)
    app.run(debug=True, host="0.0.0.0", port=5000)
