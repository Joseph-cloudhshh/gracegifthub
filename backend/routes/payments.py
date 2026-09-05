import uuid
import requests
from flask import Blueprint, request, jsonify, current_app
from models import db, Order, Payment, AdminNotification, AppSetting
from routes.auth_utils import login_required

payments_bp = Blueprint("payments", __name__, url_prefix="/api/payments")


@payments_bp.route("/config", methods=["GET"])
def public_config():
    """Frontend calls this to check whether the gateway is configured.
    Does NOT return the API key — Payscribe's own dashboard states their
    key must never be exposed to frontend apps, despite being labeled
    "public". Under the hosted-checkout redirect flow, the frontend never
    needs any Payscribe credential at all — it just redirects to the
    checkout_url returned by /initiate."""
    configured = bool(current_app.config.get("PAYSCRIBE_API_KEY")) and \
        not current_app.config["PAYSCRIBE_API_KEY"].endswith("_replace_me")
    return jsonify({"configured": configured})


@payments_bp.route("/initiate/<int:order_id>", methods=["POST"])
@login_required
def initiate_payment(order_id):
    user = request.current_user
    order = Order.query.filter_by(id=order_id, user_id=user.id).first_or_404()

    # Prevent duplicate pending payments for the same order
    existing = Payment.query.filter_by(order_id=order.id, status="pending").first()
    if existing:
        tx_ref = existing.tx_ref
    else:
        tx_ref = f"GGH-TX-{uuid.uuid4().hex[:10]}"
        payment = Payment(order_id=order.id, tx_ref=tx_ref, amount=order.total, status="pending")
        db.session.add(payment)
        db.session.commit()

    # TODO(payscribe-hosted-checkout): call Payscribe's hosted-checkout /
    # initiate-transaction endpoint here (see matching TODO in
    # routes/wallet.py fund_initiate) once we have its documented
    # request/response shape, and return the resulting checkout_url below.
    return jsonify({
        "tx_ref": tx_ref,
        "amount": float(order.total),
        "currency": "NGN",
        "customer": {"email": user.email, "name": user.full_name, "phone": user.phone},
        "checkout_url": None,  # TODO: populate from Payscribe hosted-checkout response
    })


@payments_bp.route("/verify/<tx_ref>", methods=["POST"])
@login_required
def verify_payment(tx_ref):
    """Called after the Payscribe checkout redirect completes — verifies
    server-side. This is a convenience/UX path only; the webhook below
    (/webhooks/payscribe) is the authoritative source of truth and will
    mark the order paid even if the customer never returns to this page."""
    payment = Payment.query.filter_by(tx_ref=tx_ref).first_or_404()

    if payment.status == "successful":
        return jsonify({"verified": True, "order": payment.order.to_dict()})

    result, error, status_code = verify_and_mark_payment_paid(payment)
    if error:
        return jsonify({"error": error}), status_code
    if not result:
        return jsonify({"verified": False, "error": "Payment could not be verified."}), 400
    return jsonify({"verified": True, "order": payment.order.to_dict()})


def verify_and_mark_payment_paid(payment):
    """Independently verifies an order payment directly with Payscribe's
    API (never trusting a frontend success message, and never trusting
    webhook-supplied amount/status without this same server-to-server
    check) and, only if genuinely successful, marks the order paid exactly
    once.

    Called from both:
    - POST /api/payments/verify/<tx_ref>  (frontend, after checkout redirect)
    - POST /webhooks/payscribe            (Payscribe's own webhook)

    Returns (verified: bool, error: str|None, http_status: int).
    """
    # Idempotent: if some other call already confirmed this payment
    # (frontend verify + webhook racing each other, or a duplicate
    # webhook delivery), don't re-process or re-notify.
    if payment.status == "successful":
        return True, None, 200

    headers = {
        "Authorization": f"Bearer {current_app.config['PAYSCRIBE_API_KEY']}",
        "Content-Type": "application/json"
    }
    url = f"{current_app.config['PAYSCRIBE_BASE_URL']}/transactions/verify"

    try:
        resp = requests.post(url, headers=headers, json={"reference": payment.tx_ref}, timeout=15)
        result = resp.json()
    except requests.RequestException as e:
        _log("payment", f"Gateway unreachable during verify: {e}", level="error")
        return False, f"Could not reach payment gateway: {e}", 502

    data = result.get("data", {})
    status_ok = (
        result.get("status") == "success"
        and data.get("status") == "successful"
        and data.get("reference") == payment.tx_ref  # tx_ref belongs to this exact payment
        and float(data.get("amount", 0)) >= float(payment.amount)  # amount matches (or exceeds)
        and data.get("currency") == "NGN"
    )

    if not status_ok:
        payment.status = "failed"
        db.session.commit()
        _log("payment", f"Payment verification failed: {payment.tx_ref}", level="warning")
        return False, None, 200

    # Re-fetch and re-check status inside the same commit boundary so a
    # concurrent call (webhook + frontend verify arriving at once) can't
    # both pass the idempotency check above and double-process.
    payment.status = "successful"
    payment.flutterwave_tx_id = str(data.get("id"))
    payment.order.status = "processing"

    # Calculate profit margins
    markup_type = AppSetting.get("markup_type", "percentage")
    markup_val = float(AppSetting.get("markup_value", "10") or 10)
    gateway_fee_pct = float(AppSetting.get("gateway_fee_pct", "1.4") or 1.4)
    amount = float(payment.amount)

    if markup_type == "percentage":
        provider_cost = amount / (1 + markup_val / 100)
    else:
        provider_cost = max(0, amount - markup_val)

    gross_profit = amount - provider_cost
    gateway_fee = amount * gateway_fee_pct / 100
    net_profit = gross_profit - gateway_fee

    payment.provider_cost = round(provider_cost, 2)
    payment.gross_profit = round(gross_profit, 2)
    payment.gateway_fee = round(gateway_fee, 2)
    payment.net_profit = round(net_profit, 2)
    payment.settlement_status = "pending"

    db.session.commit()

    # Admin notification
    order = payment.order
    customer = order.user
    _create_notification(order, customer)

    # Admin email (async-ish — catch all errors so they never block the customer)
    try:
        from routes.admin.email_utils import send_new_order_notification
        send_new_order_notification(order, customer)
    except Exception as e:
        _log("email", f"New-order email failed for order #{order.id}: {e}", level="error")

    _log("payment", f"Payment verified: {payment.tx_ref} | Order #{order.id} | ₦{amount:,.2f}")
    return True, None, 200


# ── Helpers ──────────────────────────────────────────────────────────────── #

def _create_notification(order, customer):
    """Create an admin notification for a new paid order (idempotent)."""
    existing = AdminNotification.query.filter_by(related_order_id=order.id).first()
    if existing:
        return
    items_summary = ", ".join(
        i.product.name for i in order.items[:3] if i.product
    )
    if len(order.items) > 3:
        items_summary += f" +{len(order.items)-3} more"
    notif = AdminNotification(
        title="New Order Received",
        message=(
            f"Order #{order.id} ({order.order_ref}) from "
            f"{customer.full_name if customer else 'Customer'} — "
            f"₦{float(order.total):,.2f} — {items_summary}"
        ),
        notif_type="order",
        related_order_id=order.id,
    )
    db.session.add(notif)
    db.session.commit()


def _log(category, message, level="info"):
    try:
        from models import SystemLog
        entry = SystemLog(level=level, category=category, message=message[:2000],
                          ip_address=(request.remote_addr or "")[:45])
        db.session.add(entry)
        db.session.commit()
    except Exception:
        pass
