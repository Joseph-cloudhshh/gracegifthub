"""Admin API endpoints - all require admin session."""
import os, io, json, secrets, base64
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, make_response, current_app
from sqlalchemy import func, desc
from models import (db, AdminUser, AdminSession, AdminNotification, SystemLog,
                    AppSetting, Order, OrderItem, Product, Payment, User, Coupon,
                    Wallet, WalletTransaction)
from routes.admin.auth_utils import (admin_required, create_admin_session,
                                     invalidate_admin_session, log_event, get_admin_from_request)
from routes.admin.email_utils import send_email, send_new_order_notification

admin_api_bp = Blueprint("admin_api", __name__, url_prefix="/admin/api")

# ──────────── Auth ──────────── #

@admin_api_bp.route("/login", methods=["POST"])
def admin_login():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    totp_code = (data.get("totp_code") or "").strip()
    ip = request.remote_addr or ""

    admin = AdminUser.query.filter_by(email=email).first()

    # Rate-limit: lock after 5 bad attempts for 15 minutes
    if admin and admin.locked_until and admin.locked_until > datetime.utcnow():
        remaining = int((admin.locked_until - datetime.utcnow()).total_seconds() // 60) + 1
        log_event("auth", f"Blocked login for locked account: {email}", "warning")
        return jsonify({"error": f"Account locked. Try again in {remaining} minute(s)."}), 429

    if not admin or not admin.check_password(password):
        if admin:
            admin.failed_login_attempts = (admin.failed_login_attempts or 0) + 1
            if admin.failed_login_attempts >= 5:
                admin.locked_until = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()
        log_event("auth", f"Failed admin login attempt for: {email}", "warning")
        return jsonify({"error": "Invalid email or password."}), 401

    # Check 2FA
    if admin.totp_enabled:
        if not totp_code:
            return jsonify({"error": "2FA code required.", "require_2fa": True}), 401
        import pyotp
        totp = pyotp.TOTP(admin.totp_secret)
        if not totp.verify(totp_code, valid_window=1):
            # Check backup codes
            backup_ok = False
            if admin.totp_backup_codes:
                from werkzeug.security import check_password_hash
                codes = json.loads(admin.totp_backup_codes)
                for i, hashed in enumerate(codes):
                    if check_password_hash(hashed, totp_code):
                        codes.pop(i)
                        admin.totp_backup_codes = json.dumps(codes)
                        db.session.commit()
                        backup_ok = True
                        break
            if not backup_ok:
                log_event("auth", f"Failed 2FA for admin: {email}", "warning")
                return jsonify({"error": "Invalid 2FA code."}), 401

    # Success
    admin.failed_login_attempts = 0
    admin.locked_until = None
    admin.last_login = datetime.utcnow()
    db.session.commit()

    token = create_admin_session(admin, ip, request.headers.get("User-Agent", ""))
    log_event("auth", f"Admin login: {email}", admin_id=admin.id)

    # `token` is also returned in the JSON body (in addition to the cookie)
    # so the admin frontend can work cross-origin (e.g. Netlify frontend +
    # PythonAnywhere backend on different domains) by sending it back as an
    # Authorization: Bearer header, since cross-site cookies are unreliable.
    resp = make_response(jsonify({"ok": True, "admin": admin.to_dict(), "token": token}))
    resp.set_cookie("admin_token", token, httponly=True, samesite="Lax",
                    max_age=8 * 3600, secure=request.is_secure)
    return resp


@admin_api_bp.route("/logout", methods=["POST"])
def admin_logout():
    token = request.cookies.get("admin_token", "")
    admin = get_admin_from_request()
    if admin:
        log_event("auth", f"Admin logout: {admin.email}", admin_id=admin.id)
    invalidate_admin_session(token)
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie("admin_token")
    return resp


@admin_api_bp.route("/me", methods=["GET"])
@admin_required
def admin_me():
    return jsonify({"admin": request.current_admin.to_dict()})


# ──────────── Dashboard Stats ──────────── #

@admin_api_bp.route("/dashboard/stats", methods=["GET"])
@admin_required
def dashboard_stats():
    total_orders = Order.query.count()
    total_users = User.query.count()
    total_products = Product.query.count()

    total_sales = db.session.query(func.sum(Payment.amount)).filter_by(status="successful").scalar() or 0

    # 30-day comparison
    now = datetime.utcnow()
    prev_start = now - timedelta(days=60)
    prev_end = now - timedelta(days=30)
    curr_start = now - timedelta(days=30)

    orders_30 = Order.query.filter(Order.created_at >= curr_start).count()
    orders_prev = Order.query.filter(Order.created_at.between(prev_start, prev_end)).count()
    orders_change = _pct_change(orders_prev, orders_30)

    sales_30 = db.session.query(func.sum(Payment.amount)).filter(
        Payment.status == "successful", Payment.created_at >= curr_start).scalar() or 0
    sales_prev = db.session.query(func.sum(Payment.amount)).filter(
        Payment.status == "successful", Payment.created_at.between(prev_start, prev_end)).scalar() or 0
    sales_change = _pct_change(float(sales_prev), float(sales_30))

    users_30 = User.query.filter(User.created_at >= curr_start).count()
    users_prev = User.query.filter(User.created_at.between(prev_start, prev_end)).count()
    users_change = _pct_change(users_prev, users_30)

    return jsonify({
        "total_orders": total_orders,
        "total_sales": float(total_sales),
        "total_users": total_users,
        "total_sellers": 0,
        "total_products": total_products,
        "orders_change": orders_change,
        "sales_change": sales_change,
        "users_change": users_change,
    })


def _pct_change(prev, curr):
    if prev == 0:
        return 100.0 if curr > 0 else 0.0
    return round((curr - prev) / prev * 100, 1)


@admin_api_bp.route("/dashboard/sales-chart", methods=["GET"])
@admin_required
def sales_chart():
    period = request.args.get("period", "30")
    days = {"today": 1, "7": 7, "30": 30, "90": 90, "365": 365}.get(period, 30)
    since = datetime.utcnow() - timedelta(days=days)

    payments = Payment.query.filter(
        Payment.status == "successful", Payment.created_at >= since
    ).all()

    # Group by date
    groups: dict = {}
    for p in payments:
        key = p.created_at.strftime("%Y-%m-%d")
        groups[key] = groups.get(key, 0) + float(p.amount)

    # Fill missing dates
    result = []
    for i in range(days):
        d = (datetime.utcnow() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
        result.append({"date": d, "revenue": groups.get(d, 0)})

    return jsonify(result)


@admin_api_bp.route("/dashboard/order-status", methods=["GET"])
@admin_required
def order_status_chart():
    rows = db.session.query(Order.status, func.count(Order.id)).group_by(Order.status).all()
    return jsonify([{"status": r[0], "count": r[1]} for r in rows])


@admin_api_bp.route("/dashboard/bottom-stats", methods=["GET"])
@admin_required
def bottom_stats():
    total_revenue = db.session.query(func.sum(Payment.amount)).filter_by(status="successful").scalar() or 0
    provider_cost = db.session.query(func.sum(Payment.provider_cost)).filter(Payment.status=="successful").scalar() or 0
    gross_profit = db.session.query(func.sum(Payment.gross_profit)).filter(Payment.status=="successful").scalar() or 0
    gateway_fees = db.session.query(func.sum(Payment.gateway_fee)).filter(Payment.status=="successful").scalar() or 0
    net_profit = db.session.query(func.sum(Payment.net_profit)).filter(Payment.status=="successful").scalar() or 0
    pending_payouts = db.session.query(func.sum(Payment.amount)).filter(Payment.settlement_status=="pending", Payment.status=="successful").scalar() or 0
    active_coupons = Coupon.query.filter_by(is_active=True).count()
    low_stock = Product.query.filter_by(in_stock=False).count()

    return jsonify({
        "total_revenue": float(total_revenue),
        "provider_cost": float(provider_cost),
        "gross_profit": float(gross_profit),
        "gateway_fees": float(gateway_fees),
        "net_profit": float(net_profit),
        "pending_payouts": float(pending_payouts),
        "active_coupons": active_coupons,
        "low_stock": low_stock,
    })


# ──────────── Orders ──────────── #

@admin_api_bp.route("/orders", methods=["GET"])
@admin_required
def list_orders():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    status = request.args.get("status")

    q = Order.query
    if status:
        q = q.filter_by(status=status)
    paginated = q.order_by(desc(Order.created_at)).paginate(page=page, per_page=per_page, error_out=False)

    orders = []
    for o in paginated.items:
        d = o.to_dict()
        d["customer"] = o.user.full_name if o.user else "Unknown"
        d["customer_email"] = o.user.email if o.user else ""
        orders.append(d)

    return jsonify({"orders": orders, "total": paginated.total, "pages": paginated.pages, "page": page})


@admin_api_bp.route("/orders/<int:order_id>", methods=["GET"])
@admin_required
def get_order(order_id):
    o = Order.query.get_or_404(order_id)
    d = o.to_dict()
    d["customer"] = o.user.full_name if o.user else "Unknown"
    d["customer_email"] = o.user.email if o.user else ""
    d["payments"] = [p.to_dict() for p in o.payments]
    return jsonify(d)


@admin_api_bp.route("/orders/<int:order_id>/status", methods=["PATCH"])
@admin_required
def update_order_status(order_id):
    o = Order.query.get_or_404(order_id)
    data = request.get_json(force=True) or {}
    new_status = data.get("status")
    allowed = ["pending", "processing", "in_transit", "delivered", "cancelled"]
    if new_status not in allowed:
        return jsonify({"error": "Invalid status."}), 400
    o.status = new_status
    db.session.commit()
    log_event("order", f"Order #{order_id} status changed to {new_status}", admin_id=request.current_admin.id)
    return jsonify({"ok": True})


@admin_api_bp.route("/orders/recent", methods=["GET"])
@admin_required
def recent_orders():
    limit = int(request.args.get("limit", 10))
    orders = Order.query.order_by(desc(Order.created_at)).limit(limit).all()
    result = []
    for o in orders:
        d = o.to_dict()
        d["customer"] = o.user.full_name if o.user else "Unknown"
        result.append(d)
    return jsonify(result)


# ──────────── Top-Selling Products ──────────── #

@admin_api_bp.route("/products/top-selling", methods=["GET"])
@admin_required
def top_selling():
    limit = int(request.args.get("limit", 10))
    rows = db.session.query(
        Product.id, Product.name, Product.category, Product.image_url,
        func.sum(OrderItem.quantity).label("units_sold"),
        func.sum(OrderItem.quantity * OrderItem.unit_price).label("revenue")
    ).join(OrderItem, OrderItem.product_id == Product.id)\
     .join(Order, Order.id == OrderItem.order_id)\
     .group_by(Product.id)\
     .order_by(desc("units_sold"))\
     .limit(limit).all()

    return jsonify([{"id": r.id, "name": r.name, "category": r.category,
                     "image_url": r.image_url, "units_sold": int(r.units_sold or 0),
                     "revenue": float(r.revenue or 0)} for r in rows])


# ──────────── Users ──────────── #

@admin_api_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    search = request.args.get("search", "")
    q = User.query
    if search:
        q = q.filter((User.full_name.ilike(f"%{search}%")) | (User.email.ilike(f"%{search}%")))
    pag = q.order_by(desc(User.created_at)).paginate(page=page, per_page=per_page, error_out=False)
    users = []
    for u in pag.items:
        d = u.to_dict()
        d["created_at"] = u.created_at.isoformat()
        d["order_count"] = Order.query.filter_by(user_id=u.id).count()
        users.append(d)
    return jsonify({"users": users, "total": pag.total, "pages": pag.pages, "page": page})


# ──────────── Products (Admin) ──────────── #

@admin_api_bp.route("/products", methods=["GET"])
@admin_required
def list_products():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    q = Product.query
    pag = q.order_by(Product.name).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({"products": [p.to_dict() for p in pag.items],
                    "total": pag.total, "pages": pag.pages, "page": page})


# ──────────── Payments / Transactions ──────────── #

@admin_api_bp.route("/payments", methods=["GET"])
@admin_required
def list_payments():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    pag = Payment.query.order_by(desc(Payment.created_at)).paginate(page=page, per_page=per_page, error_out=False)
    items = []
    for p in pag.items:
        d = p.to_dict()
        if p.order and p.order.user:
            d["customer"] = p.order.user.full_name
        items.append(d)
    return jsonify({"payments": items, "total": pag.total, "pages": pag.pages, "page": page})


# ──────────── Finance ──────────── #

@admin_api_bp.route("/finance/summary", methods=["GET"])
@admin_required
def finance_summary():
    period = request.args.get("period", "30")
    days = {"today": 1, "7": 7, "30": 30, "90": 90}.get(period, 30)
    since = datetime.utcnow() - timedelta(days=days)

    base = Payment.query.filter(Payment.status == "successful", Payment.created_at >= since)
    total_revenue = base.with_entities(func.sum(Payment.amount)).scalar() or 0
    provider_cost = base.with_entities(func.sum(Payment.provider_cost)).scalar() or 0
    gross_profit = base.with_entities(func.sum(Payment.gross_profit)).scalar() or 0
    gateway_fees = base.with_entities(func.sum(Payment.gateway_fee)).scalar() or 0
    net_profit = base.with_entities(func.sum(Payment.net_profit)).scalar() or 0
    pending_settlement = base.filter(Payment.settlement_status == "pending")\
                            .with_entities(func.sum(Payment.amount)).scalar() or 0
    settled = base.filter(Payment.settlement_status == "settled")\
                  .with_entities(func.sum(Payment.amount)).scalar() or 0

    return jsonify({
        "total_revenue": float(total_revenue),
        "provider_cost": float(provider_cost),
        "gross_profit": float(gross_profit),
        "gateway_fees": float(gateway_fees),
        "net_profit": float(net_profit),
        "pending_settlement": float(pending_settlement),
        "settled": float(settled),
    })


# ──────────── Coupons ──────────── #

@admin_api_bp.route("/coupons", methods=["GET"])
@admin_required
def list_coupons():
    coupons = Coupon.query.order_by(desc(Coupon.created_at)).all()
    return jsonify([c.to_dict() for c in coupons])


@admin_api_bp.route("/coupons", methods=["POST"])
@admin_required
def create_coupon():
    data = request.get_json(force=True) or {}
    c = Coupon(
        code=(data.get("code") or "").upper().strip(),
        discount_type=data.get("discount_type", "percentage"),
        discount_value=float(data.get("discount_value", 0)),
        min_order=float(data.get("min_order", 0)),
        max_uses=data.get("max_uses"),
        is_active=data.get("is_active", True),
    )
    if data.get("expires_at"):
        c.expires_at = datetime.fromisoformat(data["expires_at"])
    db.session.add(c)
    db.session.commit()
    log_event("settings", f"Coupon created: {c.code}", admin_id=request.current_admin.id)
    return jsonify(c.to_dict()), 201


@admin_api_bp.route("/coupons/<int:coupon_id>", methods=["DELETE"])
@admin_required
def delete_coupon(coupon_id):
    c = Coupon.query.get_or_404(coupon_id)
    db.session.delete(c)
    db.session.commit()
    return jsonify({"ok": True})


# ──────────── Notifications ──────────── #

@admin_api_bp.route("/notifications", methods=["GET"])
@admin_required
def list_notifications():
    notifs = AdminNotification.query.order_by(desc(AdminNotification.created_at)).limit(50).all()
    unread = AdminNotification.query.filter_by(is_read=False).count()
    return jsonify({"notifications": [n.to_dict() for n in notifs], "unread": unread})


@admin_api_bp.route("/notifications/<int:nid>/read", methods=["PATCH"])
@admin_required
def mark_read(nid):
    n = AdminNotification.query.get_or_404(nid)
    n.is_read = True
    db.session.commit()
    return jsonify({"ok": True})


@admin_api_bp.route("/notifications/read-all", methods=["POST"])
@admin_required
def mark_all_read():
    AdminNotification.query.filter_by(is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True})


# ──────────── System Logs ──────────── #

@admin_api_bp.route("/logs", methods=["GET"])
@admin_required
def system_logs():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    level = request.args.get("level")
    category = request.args.get("category")
    q = SystemLog.query
    if level:
        q = q.filter_by(level=level)
    if category:
        q = q.filter_by(category=category)
    pag = q.order_by(desc(SystemLog.created_at)).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({"logs": [l.to_dict() for l in pag.items],
                    "total": pag.total, "pages": pag.pages, "page": page})


# ──────────── Contact Information ──────────── #

_CONTACT_KEYS = ["support_email", "support_phone", "whatsapp_link"]
_CONTACT_DEFAULTS = {
    "support_email": "supportgracegifthub@gmail.com",
    "support_phone": "+234 708 837 6847",
    "whatsapp_link": "https://wa.link/y9ozfj",
}


@admin_api_bp.route("/settings/contact", methods=["GET"])
@admin_required
def get_contact_settings():
    return jsonify({k: AppSetting.get(k, _CONTACT_DEFAULTS.get(k, "")) for k in _CONTACT_KEYS})


@admin_api_bp.route("/settings/contact", methods=["POST"])
@admin_required
def save_contact_settings():
    data = request.get_json(force=True) or {}
    for k in _CONTACT_KEYS:
        if k in data and str(data[k]).strip():
            AppSetting.set_value(k, str(data[k]).strip())
    log_event("settings", "Contact information updated", admin_id=request.current_admin.id)
    return jsonify({"ok": True})


# ──────────── Wallets ──────────── #

@admin_api_bp.route("/wallets", methods=["GET"])
@admin_required
def list_wallets():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    q = (db.session.query(Wallet, User)
         .join(User, User.id == Wallet.user_id)
         .order_by(desc(Wallet.balance)))
    pag = q.paginate(page=page, per_page=per_page, error_out=False)
    items = [{
        "user_id": u.id, "full_name": u.full_name, "email": u.email,
        "balance": float(w.balance), "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    } for w, u in pag.items]
    total_balance = db.session.query(func.coalesce(func.sum(Wallet.balance), 0)).scalar()
    return jsonify({"wallets": items, "total": pag.total, "pages": pag.pages,
                    "page": page, "total_balance": float(total_balance)})


@admin_api_bp.route("/wallets/<int:user_id>/transactions", methods=["GET"])
@admin_required
def wallet_transactions_for_user(user_id):
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if not wallet:
        return jsonify({"transactions": []})
    txs = (WalletTransaction.query.filter_by(wallet_id=wallet.id)
           .order_by(desc(WalletTransaction.created_at)).limit(200).all())
    return jsonify({"transactions": [t.to_dict() for t in txs]})


# ──────────── Settings ──────────── #

@admin_api_bp.route("/settings/general", methods=["GET"])
@admin_required
def get_general_settings():
    keys = ["site_name", "markup_type", "markup_value", "gateway_fee_pct",
            "smtp_host", "smtp_port", "smtp_username", "smtp_from_email",
            "smtp_from_name", "smtp_use_tls", "admin_email"]
    data = {k: AppSetting.get(k, "") for k in keys}
    return jsonify(data)


@admin_api_bp.route("/settings/general", methods=["POST"])
@admin_required
def save_general_settings():
    data = request.get_json(force=True) or {}
    allowed = ["site_name", "markup_type", "markup_value", "gateway_fee_pct",
               "smtp_host", "smtp_port", "smtp_username", "smtp_from_email",
               "smtp_from_name", "smtp_use_tls", "admin_email"]
    for k in allowed:
        if k in data:
            AppSetting.set_value(k, str(data[k]))
    log_event("settings", "General settings updated", admin_id=request.current_admin.id)
    return jsonify({"ok": True})


@admin_api_bp.route("/settings/smtp-test", methods=["POST"])
@admin_required
def smtp_test():
    admin = request.current_admin
    to = admin.email
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto">
      <div style="background:#1a3a6b;color:#fff;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">✅ SMTP Test Successful</h2>
      </div>
      <div style="padding:20px;background:#f8f9fa">
        <p>This is a test email from <strong>Gracegifthub Gift Hub Admin</strong>.</p>
        <p>Sent at: <strong>{now}</strong></p>
        <p>If you received this email, your SMTP configuration is working correctly.</p>
      </div>
    </div>"""
    ok, err = send_email(to, "Gracegifthub Gift Hub SMTP Test", html)
    if ok:
        log_event("email", "SMTP test email sent successfully", admin_id=admin.id)
        return jsonify({"ok": True, "message": f"Test email sent to {to}"})
    log_event("email", f"SMTP test failed: {err}", level="error", admin_id=admin.id)
    return jsonify({"ok": False, "error": err}), 500


@admin_api_bp.route("/settings/account", methods=["POST"])
@admin_required
def update_account():
    admin = request.current_admin
    data = request.get_json(force=True) or {}
    if data.get("email"):
        admin.email = data["email"].strip().lower()
    if data.get("full_name"):
        admin.full_name = data["full_name"].strip()
    if data.get("new_password"):
        if len(data["new_password"]) < 8:
            return jsonify({"error": "Password must be at least 8 characters."}), 400
        if not data.get("current_password") or not admin.check_password(data["current_password"]):
            return jsonify({"error": "Current password is incorrect."}), 401
        admin.set_password(data["new_password"])
    db.session.commit()
    log_event("settings", f"Admin account updated: {admin.email}", admin_id=admin.id)
    return jsonify({"ok": True, "admin": admin.to_dict()})


# ──────────── 2FA ──────────── #

@admin_api_bp.route("/settings/2fa/setup", methods=["POST"])
@admin_required
def setup_2fa():
    import pyotp, qrcode, qrcode.image.svg
    admin = request.current_admin
    secret = pyotp.random_base32()
    admin.totp_secret = secret
    db.session.commit()

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=admin.email, issuer_name="Gracegifthub Gift Hub")

    # Generate QR code as base64 PNG
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return jsonify({"secret": secret, "qr_code": f"data:image/png;base64,{qr_b64}", "uri": uri})


@admin_api_bp.route("/settings/2fa/verify", methods=["POST"])
@admin_required
def verify_2fa():
    import pyotp
    from werkzeug.security import generate_password_hash
    admin = request.current_admin
    data = request.get_json(force=True) or {}
    code = (data.get("code") or "").strip()
    if not admin.totp_secret:
        return jsonify({"error": "No 2FA secret set. Run setup first."}), 400
    totp = pyotp.TOTP(admin.totp_secret)
    if not totp.verify(code, valid_window=1):
        return jsonify({"error": "Invalid code."}), 400

    # Generate 8 backup codes
    backup_codes = [secrets.token_hex(4).upper() for _ in range(8)]
    admin.totp_backup_codes = json.dumps([generate_password_hash(c) for c in backup_codes])
    admin.totp_enabled = True
    db.session.commit()
    log_event("auth", "2FA enabled for admin", admin_id=admin.id)
    return jsonify({"ok": True, "backup_codes": backup_codes})


@admin_api_bp.route("/settings/2fa/disable", methods=["POST"])
@admin_required
def disable_2fa():
    admin = request.current_admin
    data = request.get_json(force=True) or {}
    if not admin.check_password(data.get("password", "")):
        return jsonify({"error": "Password incorrect."}), 401
    admin.totp_enabled = False
    admin.totp_secret = None
    admin.totp_backup_codes = None
    db.session.commit()
    log_event("auth", "2FA disabled for admin", admin_id=admin.id)
    return jsonify({"ok": True})


# ──────────── API Settings (TP Gifts) ──────────── #

@admin_api_bp.route("/settings/api-test", methods=["GET"])
@admin_required
def api_test():
    from routes.product_api_client import (check_account, fetch_products_page,
                                            mask_key, ProductApiError)
    base_url = current_app.config.get("PRODUCT_API_BASE_URL")
    api_key = current_app.config.get("PRODUCT_API_KEY")
    if not base_url or not api_key:
        return jsonify({"ok": False, "error": "API not configured (check PRODUCT_API_KEY env var)."})
    try:
        account = check_account(base_url, api_key)
        items, pag = fetch_products_page(base_url, api_key, page=1, limit=5)
        return jsonify({"ok": True, "account": account,
                        "product_count": pag.get("total", len(items)),
                        "key_masked": mask_key(api_key)})
    except ProductApiError as e:
        return jsonify({"ok": False, "error": str(e)})


@admin_api_bp.route("/settings/pricing", methods=["GET"])
@admin_required
def get_pricing():
    return jsonify({
        "markup_type": AppSetting.get("markup_type", "percentage"),
        "markup_value": AppSetting.get("markup_value", "10"),
        "gateway_fee_pct": AppSetting.get("gateway_fee_pct", "1.4"),
    })


@admin_api_bp.route("/settings/pricing", methods=["POST"])
@admin_required
def save_pricing():
    data = request.get_json(force=True) or {}
    for k in ["markup_type", "markup_value", "gateway_fee_pct"]:
        if k in data:
            AppSetting.set_value(k, str(data[k]))
    log_event("settings", "Pricing settings updated", admin_id=request.current_admin.id)
    return jsonify({"ok": True})


# ──────────── Reports ──────────── #

@admin_api_bp.route("/reports/overview", methods=["GET"])
@admin_required
def reports_overview():
    # Last 12 months revenue
    months = []
    for i in range(11, -1, -1):
        start = (datetime.utcnow().replace(day=1) - timedelta(days=30 * i)).replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        rev = db.session.query(func.sum(Payment.amount)).filter(
            Payment.status == "successful",
            Payment.created_at >= start,
            Payment.created_at < end
        ).scalar() or 0
        months.append({"month": start.strftime("%b %Y"), "revenue": float(rev)})
    return jsonify({"monthly_revenue": months})
