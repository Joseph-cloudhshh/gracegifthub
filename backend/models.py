from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ─────────────────── Customer Models ─────────────────── #

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"id": self.id, "full_name": self.full_name, "email": self.email, "phone": self.phone}


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    image_url = db.Column(db.String(500))
    description = db.Column(db.Text)
    in_stock = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "category": self.category,
                "price": float(self.price), "image_url": self.image_url,
                "description": self.description, "in_stock": self.in_stock}


class CartItem(db.Model):
    __tablename__ = "cart_items"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    product = db.relationship("Product")

    def to_dict(self):
        return {"id": self.id, "product": self.product.to_dict(), "quantity": self.quantity}


class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    order_ref = db.Column(db.String(40), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    recipient_name = db.Column(db.String(150))
    recipient_phone = db.Column(db.String(30))
    recipient_email = db.Column(db.String(150))
    delivery_country = db.Column(db.String(80))
    delivery_state = db.Column(db.String(80))
    delivery_address = db.Column(db.String(255))
    gift_message = db.Column(db.Text)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    delivery_fee = db.Column(db.Numeric(12, 2), default=0)
    discount = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.Enum("pending", "processing", "in_transit", "delivered", "cancelled"), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="orders")
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "order_ref": self.order_ref, "recipient_name": self.recipient_name,
                "recipient_phone": self.recipient_phone, "recipient_email": self.recipient_email,
                "status": self.status, "subtotal": float(self.subtotal),
                "delivery_fee": float(self.delivery_fee), "discount": float(self.discount),
                "total": float(self.total), "created_at": self.created_at.isoformat(),
                "items": [i.to_dict() for i in self.items]}


class OrderItem(db.Model):
    __tablename__ = "order_items"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    product = db.relationship("Product")

    def to_dict(self):
        return {"product_name": self.product.name if self.product else None,
                "quantity": self.quantity, "unit_price": float(self.unit_price)}


class Address(db.Model):
    __tablename__ = "addresses"
    __table_args__ = (db.UniqueConstraint("user_id", "country", name="uq_address_user_country"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    country = db.Column(db.String(80), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    street = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(120), nullable=False)
    state = db.Column(db.String(120))
    postal_code = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "country": self.country, "full_name": self.full_name,
                "phone": self.phone, "street": self.street, "city": self.city,
                "state": self.state, "postal_code": self.postal_code,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    tx_ref = db.Column(db.String(60), unique=True, nullable=False)
    flutterwave_tx_id = db.Column(db.String(60))
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    gateway_fee = db.Column(db.Numeric(12, 2), default=0)
    provider_cost = db.Column(db.Numeric(12, 2), default=0)
    gross_profit = db.Column(db.Numeric(12, 2), default=0)
    net_profit = db.Column(db.Numeric(12, 2), default=0)
    settlement_status = db.Column(db.Enum("pending", "settled", "failed"), default="pending")
    status = db.Column(db.Enum("pending", "successful", "failed", "refunded"), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    order = db.relationship("Order", backref="payments")

    def to_dict(self):
        return {"id": self.id, "order_id": self.order_id, "tx_ref": self.tx_ref,
                "flutterwave_tx_id": self.flutterwave_tx_id, "amount": float(self.amount),
                "gateway_fee": float(self.gateway_fee or 0), "provider_cost": float(self.provider_cost or 0),
                "gross_profit": float(self.gross_profit or 0), "net_profit": float(self.net_profit or 0),
                "settlement_status": self.settlement_status, "status": self.status,
                "created_at": self.created_at.isoformat()}


# ─────────────────── Admin Models ─────────────────── #

class AdminUser(db.Model):
    __tablename__ = "admin_users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), default="Administrator")
    totp_secret = db.Column(db.String(64))
    totp_enabled = db.Column(db.Boolean, default=False)
    totp_backup_codes = db.Column(db.Text)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"id": self.id, "email": self.email, "full_name": self.full_name,
                "totp_enabled": self.totp_enabled,
                "last_login": self.last_login.isoformat() if self.last_login else None}


class AdminSession(db.Model):
    __tablename__ = "admin_sessions"
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"), nullable=False)
    token_hash = db.Column(db.String(128), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    admin = db.relationship("AdminUser", backref="sessions")


class AdminNotification(db.Model):
    __tablename__ = "admin_notifications"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notif_type = db.Column(db.String(50), default="info")
    is_read = db.Column(db.Boolean, default=False)
    related_order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "title": self.title, "message": self.message,
                "notif_type": self.notif_type, "is_read": self.is_read,
                "related_order_id": self.related_order_id,
                "created_at": self.created_at.isoformat()}


class SystemLog(db.Model):
    __tablename__ = "system_logs"
    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(20), default="info")
    category = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    ip_address = db.Column(db.String(45))
    admin_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "level": self.level, "category": self.category,
                "message": self.message, "ip_address": self.ip_address,
                "created_at": self.created_at.isoformat()}


class AppSetting(db.Model):
    __tablename__ = "app_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get(cls, key, default=None):
        row = cls.query.filter_by(key=key).first()
        return row.value if row else default

    @classmethod
    def set_value(cls, key, value):
        row = cls.query.filter_by(key=key).first()
        if row:
            row.value = value
            row.updated_at = datetime.utcnow()
        else:
            row = cls(key=key, value=value)
            db.session.add(row)
        db.session.commit()


class Wallet(db.Model):
    """One wallet per customer. Balance is only ever changed server-side
    inside an atomic DB transaction — never trust a balance sent by the
    frontend."""
    __tablename__ = "wallets"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    balance = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("wallet", uselist=False))

    def to_dict(self):
        return {"balance": float(self.balance), "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class WalletTransaction(db.Model):
    __tablename__ = "wallet_transactions"
    id = db.Column(db.Integer, primary_key=True)
    wallet_id = db.Column(db.Integer, db.ForeignKey("wallets.id"), nullable=False)
    tx_ref = db.Column(db.String(60), unique=True, nullable=False)
    tx_type = db.Column(db.Enum("funding", "purchase", "refund"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    balance_after = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.Enum("pending", "successful", "failed"), default="pending")
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True)
    flutterwave_tx_id = db.Column(db.String(60))
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    wallet = db.relationship("Wallet", backref="transactions")
    order = db.relationship("Order")

    def to_dict(self):
        return {"id": self.id, "tx_ref": self.tx_ref, "tx_type": self.tx_type,
                "amount": float(self.amount), "balance_after": float(self.balance_after),
                "status": self.status, "order_id": self.order_id,
                "description": self.description, "created_at": self.created_at.isoformat()}


class Coupon(db.Model):
    __tablename__ = "coupons"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_type = db.Column(db.Enum("percentage", "fixed"), default="percentage")
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)
    min_order = db.Column(db.Numeric(12, 2), default=0)
    max_uses = db.Column(db.Integer)
    times_used = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "code": self.code, "discount_type": self.discount_type,
                "discount_value": float(self.discount_value), "min_order": float(self.min_order),
                "max_uses": self.max_uses, "times_used": self.times_used, "is_active": self.is_active,
                "expires_at": self.expires_at.isoformat() if self.expires_at else None,
                "created_at": self.created_at.isoformat()}
