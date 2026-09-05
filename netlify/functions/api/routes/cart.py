from flask import Blueprint, request, jsonify
from models import db, CartItem, Product
from routes.auth_utils import login_required

cart_bp = Blueprint("cart", __name__, url_prefix="/api/cart")


@cart_bp.route("", methods=["GET"])
@login_required
def get_cart():
    user = request.current_user
    items = CartItem.query.filter_by(user_id=user.id).all()
    subtotal = sum(float(i.product.price) * i.quantity for i in items)
    return jsonify({"items": [i.to_dict() for i in items], "subtotal": subtotal})


@cart_bp.route("/add", methods=["POST"])
@login_required
def add_to_cart():
    user = request.current_user
    data = request.get_json(force=True)
    product_id = data.get("product_id")
    quantity = int(data.get("quantity", 1))

    product = Product.query.get(product_id)
    if not product:
        return jsonify({"error": "Product not found."}), 404

    item = CartItem.query.filter_by(user_id=user.id, product_id=product_id).first()
    if item:
        item.quantity += quantity
    else:
        item = CartItem(user_id=user.id, product_id=product_id, quantity=quantity)
        db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict()), 201


@cart_bp.route("/update/<int:item_id>", methods=["PUT"])
@login_required
def update_cart_item(item_id):
    user = request.current_user
    item = CartItem.query.filter_by(id=item_id, user_id=user.id).first_or_404()
    data = request.get_json(force=True)
    quantity = int(data.get("quantity", item.quantity))
    if quantity <= 0:
        db.session.delete(item)
        db.session.commit()
        return jsonify({"deleted": True})
    item.quantity = quantity
    db.session.commit()
    return jsonify(item.to_dict())


@cart_bp.route("/remove/<int:item_id>", methods=["DELETE"])
@login_required
def remove_cart_item(item_id):
    user = request.current_user
    item = CartItem.query.filter_by(id=item_id, user_id=user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    return jsonify({"deleted": True})
