import jwt
import datetime
from flask import Blueprint, request, jsonify, current_app
from models import db, User

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def make_token(user):
    payload = {
        "user_id": user.id,
        "exp": datetime.datetime.utcnow()
        + datetime.timedelta(hours=current_app.config["JWT_EXPIRY_HOURS"]),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(force=True)
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    phone = (data.get("phone") or "").strip()

    if not full_name or not email or len(password) < 6:
        return jsonify({"error": "Full name, valid email and a password (6+ chars) are required."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with that email already exists."}), 409

    user = User(full_name=full_name, email=email, phone=phone)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    _notify_admin_new_user(user)

    token = make_token(user)
    return jsonify({"token": token, "user": user.to_dict()}), 201


def _notify_admin_new_user(user):
    """Admin notification + email for a new signup. Wrapped so a failure
    here (e.g. SMTP down) never blocks account creation."""
    try:
        from models import AdminNotification
        db.session.add(AdminNotification(
            title="New User Registered",
            message=f"{user.full_name} ({user.email}) just created an account.",
            notif_type="user",
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        import os
        from models import AppSetting
        from routes.admin.email_utils import send_email
        admin_email = os.getenv("ADMIN_EMAIL") or AppSetting.get("admin_email", "")
        if not admin_email:
            return
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto">
          <div style="background:#1a3a6b;color:#fff;padding:20px;border-radius:8px 8px 0 0">
            <h2 style="margin:0">👤 New User Registered</h2>
          </div>
          <div style="background:#f8f9fa;padding:20px">
            <p><strong>Name:</strong> {user.full_name}</p>
            <p><strong>Email:</strong> {user.email}</p>
            <p><strong>Phone:</strong> {user.phone or '—'}</p>
            <p><strong>Date:</strong> {user.created_at.strftime('%Y-%m-%d %H:%M UTC')}</p>
          </div>
        </div>"""
        send_email(admin_email, "New User Registered - Gracegifthub Gift Hub", html)
    except Exception:
        pass


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password."}), 401

    token = make_token(user)
    return jsonify({"token": token, "user": user.to_dict()}), 200
