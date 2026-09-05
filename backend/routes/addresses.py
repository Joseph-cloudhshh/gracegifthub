from flask import Blueprint, request, jsonify
from models import db, Address
from routes.auth_utils import login_required

addresses_bp = Blueprint("addresses", __name__, url_prefix="/api/addresses")


@addresses_bp.route("", methods=["GET"])
@login_required
def list_addresses():
    user = request.current_user
    addresses = Address.query.filter_by(user_id=user.id).order_by(Address.country).all()
    return jsonify([a.to_dict() for a in addresses])


@addresses_bp.route("", methods=["POST"])
@login_required
def upsert_address():
    """Creates or updates the saved address for a given country (one per country per user)."""
    user = request.current_user
    data = request.get_json(force=True)

    country = (data.get("country") or "").strip()
    full_name = (data.get("full_name") or "").strip()
    phone = (data.get("phone") or "").strip()
    street = (data.get("street") or "").strip()
    city = (data.get("city") or "").strip()

    if not country or not full_name or not phone or not street or not city:
        return jsonify({"error": "Country, full name, phone, street and city are required."}), 400

    address = Address.query.filter_by(user_id=user.id, country=country).first()
    if not address:
        address = Address(user_id=user.id, country=country)
        db.session.add(address)

    address.full_name = full_name
    address.phone = phone
    address.street = street
    address.city = city
    address.state = (data.get("state") or "").strip()
    address.postal_code = (data.get("postal_code") or "").strip()

    db.session.commit()
    return jsonify(address.to_dict()), 200


@addresses_bp.route("/<int:address_id>", methods=["DELETE"])
@login_required
def delete_address(address_id):
    user = request.current_user
    address = Address.query.filter_by(id=address_id, user_id=user.id).first_or_404()
    db.session.delete(address)
    db.session.commit()
    return jsonify({"deleted": True})
