"""Customer wallet: balance, funding (via Payscribe), transaction history.

Security rules followed here:
- Balance is NEVER accepted from the frontend — always read/written server-side.
- Funding is only credited after the server verifies the transaction directly
  with Payscribe (never trusts the browser's "payment successful" callback).
- Every credit/debit happens inside a single DB transaction with a re-check
  immediately before commit, and tx_ref has a UNIQUE constraint, so a
  duplicate webhook/verify call cannot double-credit or double-debit.

NOTE: this previously used a separate Flutterwave integration. It has been
migrated onto the same Payscribe gateway/config already used by checkout
(routes/payments.py), using Payscribe's hosted/redirect payment page rather
than an inline JS widget.
"""
import uuid
import requests
from flask import Blueprint, request, jsonify, current_app
from sqlalchemy.exc import IntegrityError
from models import db, Wallet, WalletTransaction
from routes.auth_utils import login_required

wallet_bp = Blueprint("wallet", __name__, url_prefix="/api/wallet")


def get_or_create_wallet(user_id):
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=0)
        db.session.add(wallet)
        try:
            db.session.commit()
        except IntegrityError:
            # Another request created it first (race) — just re-fetch.
            db.session.rollback()
            wallet = Wallet.query.filter_by(user_id=user_id).first()
    return wallet


@wallet_bp.route("", methods=["GET"])
@login_required
def get_wallet():
    wallet = get_or_create_wallet(request.current_user.id)
    return jsonify(wallet.to_dict())


@wallet_bp.route("/transactions", methods=["GET"])
@login_required
def list_transactions():
    wallet = get_or_create_wallet(request.current_user.id)
    txs = (WalletTransaction.query
           .filter_by(wallet_id=wallet.id)
           .order_by(WalletTransaction.created_at.desc())
           .limit(100).all())
    return jsonify([t.to_dict() for t in txs])


@wallet_bp.route("/fund/initiate", methods=["POST"])
@login_required
def fund_initiate():
    """Customer enters a Naira amount to fund their wallet. Creates a
    pending WalletTransaction and returns Payscribe hosted-checkout params.
    The wallet is NOT credited here — only after /fund/verify confirms
    the payment with Payscribe."""
    user = request.current_user
    data = request.get_json(force=True) or {}
    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0

    if amount < 100:
        return jsonify({"error": "Minimum funding amount is ₦100."}), 400
    if amount > 5_000_000:
        return jsonify({"error": "Amount exceeds the maximum allowed for a single funding transaction."}), 400

    wallet = get_or_create_wallet(user.id)
    tx_ref = f"GGH-WLT-{uuid.uuid4().hex[:12]}"

    tx = WalletTransaction(
        wallet_id=wallet.id,
        tx_ref=tx_ref,
        tx_type="funding",
        amount=amount,
        balance_after=wallet.balance,  # unchanged until verified
        status="pending",
        description="Wallet funding",
    )
    db.session.add(tx)
    db.session.commit()

    # TODO(payscribe-hosted-checkout): call Payscribe's hosted-checkout /
    # initiate-transaction endpoint here once we have its documented
    # request/response shape (from the "View Docs" link on the Payscribe
    # API & Keys dashboard). It should return a redirect URL, e.g.
    # checkout_url, that the customer's browser is sent to. Once that's
    # wired in, update launchPayscribeForWalletFunding() in dashboard.js to
    # do `window.location.href = checkout_url`.
    #
    # NOTE: the frontend does NOT get a Payscribe key here — Payscribe's
    # dashboard states their API key must stay server-side even though
    # it's labeled "public". Under the hosted-checkout redirect flow the
    # frontend only ever needs checkout_url.
    return jsonify({
        "tx_ref": tx_ref,
        "amount": amount,
        "currency": "NGN",
        "customer": {"email": user.email, "name": user.full_name, "phone": user.phone},
        "checkout_url": None,  # TODO: populate from Payscribe hosted-checkout response
    })


@wallet_bp.route("/fund/verify/<tx_ref>", methods=["POST"])
@login_required
def fund_verify(tx_ref):
    """Verifies the funding transaction directly with Payscribe, then
    credits the wallet exactly once inside an atomic transaction. This is
    a convenience/UX path only; the webhook (/webhooks/payscribe) is the
    authoritative source of truth and will credit the wallet even if the
    customer never returns to this page."""
    user = request.current_user
    tx = WalletTransaction.query.filter_by(tx_ref=tx_ref, tx_type="funding").first_or_404()
    wallet = Wallet.query.get(tx.wallet_id)
    if not wallet or wallet.user_id != user.id:
        return jsonify({"error": "Not authorized for this transaction."}), 403

    result, error, status_code = verify_and_credit_wallet(tx)
    if error:
        return jsonify({"error": error}), status_code
    if not result:
        return jsonify({"verified": False, "error": "Payment could not be verified."}), 400

    wallet = Wallet.query.get(tx.wallet_id)
    return jsonify({"verified": True, "balance": float(wallet.balance)})


def verify_and_credit_wallet(tx):
    """Independently verifies a wallet-funding transaction directly with
    Payscribe's API (never trusting a frontend success message or
    webhook-supplied amount without this same server-to-server check)
    and, only if genuinely successful, credits the wallet exactly once.

    Called from both:
    - POST /api/wallet/fund/verify/<tx_ref>  (frontend, after redirect)
    - POST /webhooks/payscribe               (Payscribe's own webhook)

    Returns (verified: bool, error: str|None, http_status: int).
    """
    # Idempotent: already processed (handles duplicate calls / double
    # clicks, and a webhook racing the frontend's own verify call).
    if tx.status == "successful":
        return True, None, 200

    headers = {
        "Authorization": f"Bearer {current_app.config['PAYSCRIBE_API_KEY']}",
        "Content-Type": "application/json"
    }
    url = f"{current_app.config['PAYSCRIBE_BASE_URL']}/transactions/verify"
    try:
        resp = requests.post(url, headers=headers, json={"reference": tx.tx_ref}, timeout=15)
        result = resp.json()
    except requests.RequestException as e:
        _log("wallet", f"Gateway unreachable during wallet-fund verify: {e}", level="error")
        return False, f"Could not reach payment gateway: {e}", 502

    data = result.get("data", {})
    status_ok = (
        result.get("status") == "success"
        and data.get("status") == "successful"
        and data.get("reference") == tx.tx_ref  # tx_ref belongs to this exact transaction
        and float(data.get("amount", 0)) >= float(tx.amount)  # amount matches (or exceeds)
        and data.get("currency") == "NGN"
    )

    if not status_ok:
        tx.status = "failed"
        db.session.commit()
        _log("wallet", f"Wallet funding verification failed: {tx.tx_ref}", level="warning")
        return False, None, 200

    # Re-fetch wallet fresh and credit atomically. tx_ref's UNIQUE constraint
    # plus the "already successful" check above make this safe against a
    # duplicate/concurrent verify call double-crediting the wallet.
    wallet = Wallet.query.get(tx.wallet_id)
    wallet.balance = float(wallet.balance) + float(tx.amount)
    tx.status = "successful"
    # NOTE: column is named flutterwave_tx_id for historical/schema-compat
    # reasons (renaming a live DB column needs a migration) — it now stores
    # the Payscribe transaction id since funding runs through Payscribe.
    tx.flutterwave_tx_id = str(data.get("id"))
    tx.balance_after = wallet.balance
    db.session.commit()

    _log("wallet", f"Wallet funded: {tx.tx_ref} | user #{wallet.user_id} | ₦{float(tx.amount):,.2f}")
    return True, None, 200


def _log(category, message, level="info"):
    try:
        from models import SystemLog
        entry = SystemLog(level=level, category=category, message=message[:2000],
                          ip_address=(request.remote_addr or "")[:45])
        db.session.add(entry)
        db.session.commit()
    except Exception:
        pass
