import uuid
from flask import Blueprint, request, jsonify
from models import db, Order, OrderItem, CartItem, Wallet, WalletTransaction
from routes.auth_utils import login_required

orders_bp = Blueprint("orders", __name__, url_prefix="/api/orders")

DELIVERY_FEE = 5000  # flat fee in kobo/naira units, adjust as needed


@orders_bp.route("", methods=["GET"])
@login_required
def list_orders():
    user = request.current_user
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    return jsonify([o.to_dict() for o in orders])


@orders_bp.route("/<int:order_id>", methods=["GET"])
@login_required
def get_order(order_id):
    user = request.current_user
    order = Order.query.filter_by(id=order_id, user_id=user.id).first_or_404()
    return jsonify(order.to_dict())


@orders_bp.route("/checkout", methods=["POST"])
@login_required
def checkout():
    """Creates an order (status=pending) from the user's cart.
    Payment confirmation happens separately via /api/payments/verify.
    """
    user = request.current_user
    data = request.get_json(force=True)

    cart_items = CartItem.query.filter_by(user_id=user.id).all()
    if not cart_items:
        return jsonify({"error": "Your cart is empty."}), 400

    subtotal = sum(float(i.product.price) * i.quantity for i in cart_items)
    discount = float(data.get("discount", 0))
    total = subtotal + DELIVERY_FEE - discount

    order = Order(
        order_ref=f"GGH-{uuid.uuid4().hex[:8].upper()}",
        user_id=user.id,
        recipient_name=data.get("recipient_name"),
        recipient_phone=data.get("recipient_phone"),
        recipient_email=data.get("recipient_email"),
        delivery_country=data.get("delivery_country"),
        delivery_state=data.get("delivery_state"),
        delivery_address=data.get("delivery_address"),
        gift_message=data.get("gift_message"),
        subtotal=subtotal,
        delivery_fee=DELIVERY_FEE,
        discount=discount,
        total=total,
        status="pending",
    )
    db.session.add(order)
    db.session.flush()  # get order.id before commit

    for ci in cart_items:
        db.session.add(
            OrderItem(
                order_id=order.id,
                product_id=ci.product_id,
                quantity=ci.quantity,
                unit_price=ci.product.price,
            )
        )
        db.session.delete(ci)  # clear the cart

    db.session.commit()
    return jsonify(order.to_dict()), 201


@orders_bp.route("/<int:order_id>/pay-with-wallet", methods=["POST"])
@login_required
def pay_with_wallet(order_id):
    """Pays for a pending order out of the customer's wallet balance.

    Server does the final balance check (never trusts the frontend), and
    the debit + order-status update happen in a single DB transaction so
    the wallet can never be debited without the order being marked paid.
    """
    user = request.current_user
    order = Order.query.filter_by(id=order_id, user_id=user.id).first_or_404()

    if order.status != "pending":
        return jsonify({"error": "This order has already been processed."}), 400

    # Prevent double-processing if this endpoint is called twice.
    existing = WalletTransaction.query.filter_by(order_id=order.id, tx_type="purchase", status="successful").first()
    if existing:
        return jsonify({"paid": True, "order": order.to_dict()})

    wallet = Wallet.query.filter_by(user_id=user.id).first()
    balance = float(wallet.balance) if wallet else 0.0
    total = float(order.total)

    if not wallet or balance < total:
        return jsonify({
            "error": "Insufficient wallet balance. Please fund your wallet or choose another payment method.",
            "balance": balance,
            "required": total,
        }), 400

    tx_ref = f"GGH-WLT-PUR-{uuid.uuid4().hex[:10]}"
    wallet.balance = balance - total
    order.status = "processing"
    tx = WalletTransaction(
        wallet_id=wallet.id,
        tx_ref=tx_ref,
        tx_type="purchase",
        amount=total,
        balance_after=wallet.balance,
        status="successful",
        order_id=order.id,
        description=f"Payment for order {order.order_ref}",
    )
    db.session.add(tx)
    db.session.commit()

    # Admin notification + email, reusing the same helper used for gateway payments.
    try:
        from routes.payments import _create_notification, _log
        _create_notification(order, user)
        _log("wallet", f"Order paid from wallet: {tx_ref} | Order #{order.id} | ₦{total:,.2f}")
    except Exception:
        pass
    try:
        from routes.admin.email_utils import send_new_order_notification
        send_new_order_notification(order, user)
    except Exception:
        pass

    return jsonify({"paid": True, "order": order.to_dict(), "wallet_balance": float(wallet.balance)})
