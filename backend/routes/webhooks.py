"""Payscribe webhook endpoint.

Payscribe → POST /webhooks/payscribe → this handler:
  1. Verifies the request actually came from Payscribe (signature check).
  2. Looks up which of our own transactions the reference belongs to
     (an order payment, or a wallet-funding transaction).
  3. Re-verifies the transaction directly with Payscribe's API (does NOT
     trust the webhook body's amount/status — see verify_and_mark_payment_paid
     / verify_and_credit_wallet in routes/payments.py and routes/wallet.py,
     which this endpoint calls into so there is exactly ONE place that
     decides "is this payment real", shared with the frontend-verify path).
  4. Only then marks the order paid / credits the wallet — and does so
     idempotently, so a retried or duplicate webhook delivery can never
     process the same transaction twice.

⚠️ SIGNATURE VERIFICATION — NEEDS CONFIRMATION AGAINST YOUR PAYSCRIBE ACCOUNT
Payscribe's own "Webhooks" documentation page (in your dashboard / at
docs.payscribe.co) is what defines:
  - the exact header name Payscribe sends the signature in, and
  - the exact algorithm used to compute it (e.g. HMAC-SHA256 vs SHA512,
    signing the raw body vs. body+timestamp, hex vs base64 encoding).
That page is a JavaScript-rendered Postman doc site that couldn't be
read automatically while building this, so the constants below
(PAYSCRIBE_SIGNATURE_HEADER, _compute_signature) use the convention most
Nigerian payment gateways follow (HMAC-SHA256 of the raw JSON body, hex
digest, sent in a "X-Payscribe-Signature" header) as a starting point.
Please confirm this against your dashboard's Webhooks page and adjust
the two spots marked "CONFIRM" below if it differs — nothing else in
this file needs to change.
"""
import hashlib
import hmac

from flask import Blueprint, request, jsonify, current_app

from models import Payment, WalletTransaction
from routes.payments import verify_and_mark_payment_paid
from routes.wallet import verify_and_credit_wallet

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")

# CONFIRM: exact header name Payscribe sends the signature in.
PAYSCRIBE_SIGNATURE_HEADER = "X-Payscribe-Signature"


def _compute_signature(raw_body: bytes, secret: str) -> str:
    # CONFIRM: exact algorithm (HMAC-SHA256 assumed here).
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _signature_is_valid(raw_body: bytes, provided_signature: str, secret: str) -> bool:
    if not provided_signature or not secret:
        return False
    expected = _compute_signature(raw_body, secret)
    # Constant-time comparison — never use `==` for secret comparisons.
    return hmac.compare_digest(expected, provided_signature)


@webhooks_bp.route("/payscribe", methods=["POST"])
def payscribe_webhook():
    secret = current_app.config.get("PAYSCRIBE_WEBHOOK_SECRET")
    provided_signature = request.headers.get(PAYSCRIBE_SIGNATURE_HEADER, "")
    raw_body = request.get_data()  # raw bytes — must hash the exact bytes received

    if not _signature_is_valid(raw_body, provided_signature, secret):
        _log("webhook", "Rejected Payscribe webhook: invalid or missing signature", level="warning")
        return jsonify({"error": "Invalid signature"}), 401

    payload = request.get_json(silent=True) or {}
    data = payload.get("data", payload)
    tx_ref = data.get("reference") or data.get("tx_ref") or data.get("transaction_reference")

    if not tx_ref:
        _log("webhook", "Payscribe webhook missing transaction reference", level="warning")
        return jsonify({"error": "Missing transaction reference"}), 400

    # Match the reference to one of OUR OWN transactions before doing
    # anything else — this is what stops a customer (or anyone else) from
    # pointing a webhook call at an arbitrary/mismatched reference.
    payment = Payment.query.filter_by(tx_ref=tx_ref).first()
    if payment:
        verified, error, status_code = verify_and_mark_payment_paid(payment)
        if error:
            # Gateway-side problem verifying — ask Payscribe to retry later.
            return jsonify({"received": True, "error": error}), status_code
        _log("webhook", f"Payscribe webhook processed order payment {tx_ref}: verified={verified}")
        return jsonify({"received": True, "verified": verified}), 200

    wallet_tx = WalletTransaction.query.filter_by(tx_ref=tx_ref, tx_type="funding").first()
    if wallet_tx:
        verified, error, status_code = verify_and_credit_wallet(wallet_tx)
        if error:
            return jsonify({"received": True, "error": error}), status_code
        _log("webhook", f"Payscribe webhook processed wallet funding {tx_ref}: verified={verified}")
        return jsonify({"received": True, "verified": verified}), 200

    # Unknown reference — acknowledge with 200 so Payscribe doesn't keep
    # retrying something that will never match (e.g. a test event, or a
    # transaction type this store doesn't use), but log it for visibility.
    _log("webhook", f"Payscribe webhook: no matching transaction for reference {tx_ref}", level="warning")
    return jsonify({"received": True, "verified": False, "reason": "No matching transaction"}), 200


def _log(category, message, level="info"):
    try:
        from models import db, SystemLog
        entry = SystemLog(level=level, category=category, message=message[:2000],
                          ip_address=(request.remote_addr or "")[:45])
        db.session.add(entry)
        db.session.commit()
    except Exception:
        pass
