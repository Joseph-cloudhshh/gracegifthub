"""Public, read-only site settings (contact info, etc.) for the
customer-facing frontend. Values are stored centrally in AppSetting and
managed from the admin dashboard — never hard-coded in templates."""
from flask import Blueprint, jsonify
from models import AppSetting

public_settings_bp = Blueprint("public_settings", __name__, url_prefix="/api/settings")

# Sensible real defaults so the site works out of the box; admin can change
# these any time from the dashboard and the change takes effect immediately.
_DEFAULTS = {
    "support_email": "supportgracegifthub@gmail.com",
    "support_phone": "+234 708 837 6847",
    "whatsapp_link": "https://wa.link/y9ozfj",
}


@public_settings_bp.route("/contact", methods=["GET"])
def public_contact():
    return jsonify({k: AppSetting.get(k, v) for k, v in _DEFAULTS.items()})
