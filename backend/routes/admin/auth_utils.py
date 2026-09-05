"""Admin authentication utilities - session-based, separate from customer JWT."""
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, redirect, url_for, current_app
from models import db, AdminSession, AdminUser, SystemLog


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_admin_session(admin: AdminUser, ip: str, ua: str) -> str:
    """Create a new admin session token (random, stored as hash)."""
    token = secrets.token_urlsafe(48)
    expires = datetime.utcnow() + timedelta(hours=8)
    sess = AdminSession(
        admin_id=admin.id,
        token_hash=_hash_token(token),
        expires_at=expires,
        ip_address=ip[:45] if ip else None,
        user_agent=(ua or "")[:255],
    )
    db.session.add(sess)
    db.session.commit()
    return token


def get_admin_from_request():
    """Extract admin from cookie or Authorization header."""
    token = request.cookies.get("admin_token") or ""
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1]
    if not token:
        return None
    token_hash = _hash_token(token)
    sess = AdminSession.query.filter_by(token_hash=token_hash, is_active=True).first()
    if not sess:
        return None
    if sess.expires_at < datetime.utcnow():
        sess.is_active = False
        db.session.commit()
        return None
    return sess.admin


def invalidate_admin_session(token: str):
    token_hash = _hash_token(token)
    sess = AdminSession.query.filter_by(token_hash=token_hash).first()
    if sess:
        sess.is_active = False
        db.session.commit()


def admin_required(f):
    """Decorator: requires authenticated admin session; returns JSON 401 for API routes."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        admin = get_admin_from_request()
        if not admin:
            if request.path.startswith("/admin/api/"):
                return jsonify({"error": "Admin authentication required."}), 401
            return redirect("/admin/login")
        request.current_admin = admin
        return f(*args, **kwargs)
    return wrapper


def log_event(category: str, message: str, level: str = "info", admin_id: int = None):
    """Write a system log entry. Never log secrets."""
    try:
        entry = SystemLog(
            level=level,
            category=category,
            message=message[:2000],
            ip_address=(request.remote_addr or "")[:45],
            admin_id=admin_id,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        pass  # Never let logging crash the app
