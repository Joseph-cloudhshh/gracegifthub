"""Run this once (python seed.py) to populate sample gift products.
Replace these with your real catalog, or with data pulled from your
product API once PRODUCT_API_BASE_URL is confirmed and wired in.
"""
from app import create_app
from models import db, Product

SAMPLE_PRODUCTS = [
    {"name": "Birthday Gift Box", "category": "Gift Boxes", "price": 35000,
     "image_url": "/img/gift-box.jpg", "description": "A curated birthday surprise box."},
    {"name": "Premium Rose Bouquet", "category": "Flowers", "price": 25000,
     "image_url": "/img/roses.jpg", "description": "Fresh premium roses, hand-tied."},
    {"name": "Teddy Bear", "category": "Toys", "price": 15000,
     "image_url": "/img/teddy.jpg", "description": "Soft, huggable teddy bear."},
    {"name": "Chocolates Gift Box", "category": "Sweets", "price": 18000,
     "image_url": "/img/chocolates.jpg", "description": "Assorted premium chocolates."},
    {"name": "Perfume Gift Set", "category": "Fragrance", "price": 28000,
     "image_url": "/img/perfume.jpg", "description": "A luxury fragrance gift set."},
    {"name": "Photo Frame", "category": "Keepsakes", "price": 12000,
     "image_url": "/img/frame.jpg", "description": "Elegant custom photo frame."},
]

app = create_app()
with app.app_context():
    db.create_all()
    if Product.query.count() == 0:
        for p in SAMPLE_PRODUCTS:
            db.session.add(Product(**p))
        db.session.commit()
        print(f"Seeded {len(SAMPLE_PRODUCTS)} products.")
    else:
        print("Products already exist, skipping seed.")
