"""Admin HTML page views — serve the admin SPA pages."""
import os
from flask import Blueprint, send_from_directory, redirect, make_response
from routes.admin.auth_utils import get_admin_from_request

admin_views_bp = Blueprint("admin_views", __name__)

ADMIN_FRONTEND = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "admin")
)


@admin_views_bp.route("/admin")
@admin_views_bp.route("/admin/")
def admin_root():
    admin = get_admin_from_request()
    if not admin:
        return redirect("/admin/login")
    return send_from_directory(ADMIN_FRONTEND, "dashboard.html")


@admin_views_bp.route("/admin/login")
def admin_login_page():
    admin = get_admin_from_request()
    if admin:
        return redirect("/admin")
    return send_from_directory(ADMIN_FRONTEND, "login.html")


@admin_views_bp.route("/admin/<path:path>")
def admin_static(path):
    # Serve static assets (css/js/img inside frontend/admin)
    return send_from_directory(ADMIN_FRONTEND, path)
