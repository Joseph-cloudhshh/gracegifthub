"""
Netlify Function entry point. Netlify invokes `handler(event, context)` for
every request matched by the `path` routes configured in netlify.toml
(/api/*, /admin/api/*, /webhooks/*). serverless_wsgi translates that request
into a normal WSGI call into the same Flask app used elsewhere, so all
existing route/blueprint code in routes/ runs completely unchanged.

Note: this app only registers the JSON API blueprints. The HTML admin pages
(frontend/admin/*.html) are served directly by Netlify as static files, not
by Flask — see netlify.toml redirects for the pretty /admin and /admin/login
URLs.
"""
import os
import serverless_wsgi
from flask import Flask
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
from routes.admin.api import admin_api_bp

_app = None


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    allowed_origins = os.getenv("ALLOWED_ORIGINS", "*")
    origins = [o.strip() for o in allowed_origins.split(",")] if allowed_origins != "*" else "*"
    CORS(app, supports_credentials=True, origins=origins)

    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(addresses_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(public_settings_bp)
    app.register_blueprint(admin_api_bp)

    with app.app_context():
        db.create_all()
        _init_admin()

    return app


def _init_admin():
    from models import AdminUser
    if AdminUser.query.count() == 0:
        email = os.getenv("ADMIN_EMAIL", "admin@gmail.com")
        password = os.getenv("ADMIN_PASSWORD", "admin1234")
        admin = AdminUser(email=email, full_name="Store Administrator")
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()


def _get_app():
    # Reused across warm invocations of the same container; recreated on a
    # fresh cold start. db.create_all() is safe to re-run (idempotent).
    global _app
    if _app is None:
        _app = create_app()
    return _app


def handler(event, context):
    return serverless_wsgi.handle_request(_get_app(), event, context)
