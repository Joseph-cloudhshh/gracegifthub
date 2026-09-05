import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key")

    # SQLite — absolute path so WSGI/Passenger can always find it
    DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "gracegifthub.db"))
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # PayScribe Payment Gateway — secret key NEVER exposed to frontend
    # Used for BOTH checkout (routes/payments.py) and wallet funding
    # (routes/wallet.py) — Flutterwave has been fully retired from this app.
    # PayScribe: only ONE API key exists (labeled "Public API Key" in
    # Payscribe's own dashboard, but their dashboard explicitly states
    # "Safe to store on your server. Do NOT expose in frontend apps" — so
    # despite the name, this is a server-side secret, not a client key.
    # There is no separate secret key for Payscribe.
    PAYSCRIBE_API_KEY = os.getenv("PAYSCRIBE_API_KEY", "pk_test_replace_me")
    PAYSCRIBE_BASE_URL = os.getenv("PAYSCRIBE_BASE_URL", "https://api.payscribe.com/v1")
    PAYSCRIBE_WEBHOOK_SECRET = os.getenv("PAYSCRIBE_WEBHOOK_SECRET", "")

    # Product catalog provider — a pluggable external gift-card/product API.
    # TopGiftCard/TP Gifts Store has been removed; this now points at
    # whichever provider is configured, or falls back to local sample
    # products automatically if left unset (see routes/products.py).
    PRODUCT_API_KEY = os.getenv("PRODUCT_API_KEY", "")
    PRODUCT_API_BASE_URL = os.getenv("PRODUCT_API_BASE_URL", "")
    PRODUCT_CACHE_TTL_SECONDS = int(os.getenv("PRODUCT_CACHE_TTL_SECONDS", "300"))

    # Customer JWT expiry
    JWT_EXPIRY_HOURS = 24

    # Admin session expiry (hours)
    ADMIN_SESSION_HOURS = 8
