# Gracegifthub

Online gift store: landing page, real account signup/login, dashboard
(orders, payment history, cart, checkout), and Payscribe payment.

- **Frontend:** HTML, CSS, JavaScript (`/frontend`)
- **Backend:** Python (Flask) (`/backend`)
- **Database:** SQLite (single file, `backend/gracegifthub.db` — created automatically, no separate DB server or dashboard setup)

No tracking-order page is included, per your request. Fully mobile-responsive.

## 1. Set up the backend

```
cd backend
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Now open `.env` and fill in:
- `PAYSCRIBE_PUBLIC_KEY` / `PAYSCRIBE_SECRET_KEY` / `WEBHOOK_SECRET` — from
  your Payscribe dashboard (API Keys & Webhook tab). **The secret key only
  ever goes in this backend `.env` file — it must never appear in any
  frontend/JS file**, so the code is wired to keep it there. Used for both
  checkout and wallet funding (Flutterwave has been fully retired).
- `PRODUCT_API_KEY` / `PRODUCT_API_BASE_URL` — credentials for an external
  product/gift-card catalog provider, if you use one (TopGiftCard / TP
  Gifts Store has been removed). Auth uses the `X-API-KEY` header, never a
  Bearer token, and the key never leaves the backend. On startup the app
  prints `Product catalog API /account: PASS` / `FAILED` and `/products:
  PASS` / `FAILED` so you know immediately whether it's working; it falls
  back to the seeded sample products below (with a clear log message) if
  left unset or if the live API call fails for any reason. Run
  `python test_product_api.py` any time for a full diagnostic
  (account auth, pagination, field parsing).

Seed sample products (useful as a fallback / for local testing), then run the server:

```
python seed.py
python app.py
```

The whole site (frontend + API) runs from **http://localhost:5000**.

## 3. Test it

1. Visit `http://localhost:5000`
2. Create an account, log in
3. Add a gift to cart from the shop section
4. Go to Dashboard → Cart → fill in delivery details → Proceed to Payment
5. Payscribe's hosted checkout opens — complete a test payment

## Project structure

```
gracegifthub-gift-hub/
├── backend/
│   ├── app.py            # Flask app + serves the frontend
│   ├── config.py         # env-based settings (SQLite path, Payscribe/product API keys)
│   ├── models.py         # SQLAlchemy models
│   ├── schema.sql         # schema reference (SQLite via SQLAlchemy — see models.py)
│   ├── seed.py            # sample product seeder
│   ├── requirements.txt
│   ├── .env.example
│   └── routes/
│       ├── auth.py        # signup/login (JWT, hashed passwords)
│       ├── auth_utils.py  # @login_required decorator
│       ├── products.py
│       ├── cart.py
│       ├── orders.py
│       └── payments.py    # Payscribe initiate + server-side verify
└── frontend/
    ├── index.html          # landing page
    ├── login.html / signup.html
    ├── dashboard.html      # Gracegifthub dashboard
    ├── css/style.css
    └── js/ (main.js, auth.js, dashboard.js)
```

## Notes

- Passwords are hashed (never stored in plain text) and sessions use JWT.
- Payments are verified **server-side** with Payscribe's `/transactions/verify`
  endpoint before an order is marked paid — never trust the browser alone
  for that.
- Delivery fee is currently a flat ₦5,000 in `orders.py` — change
  `DELIVERY_FEE` there if you want it to vary.

## Deploying to PythonAnywhere

1. Upload/clone the project so it ends up at
   `/home/yourusername/gracegifthub-gift-hub/`.
2. Open a Bash console: `cd gracegifthub-gift-hub/backend`, create a
   virtualenv, `pip install -r requirements.txt`, `cp .env.example .env`
   and fill in the real values (SECRET_KEY, PAYSCRIBE_* keys, PRODUCT_API_KEY if used).
3. Web tab → Add a new web app → Manual configuration → your Python
   version → point the **virtualenv** field at the venv you just made.
4. Edit the generated **WSGI configuration file** (linked from the Web
   tab) so it ends with:
   ```python
   import sys
   path = '/home/yourusername/gracegifthub-gift-hub/backend'
   if path not in sys.path:
       sys.path.insert(0, path)
   from wsgi import application
   ```
5. Set the **Source code** / **Working directory** to
   `/home/yourusername/gracegifthub-gift-hub/backend`.
6. Reload the web app. Check the **Error log** — on startup it prints
   `Product catalog API /account: PASS/FAILED` and `/products: PASS/FAILED`
   so you know immediately if the product API key is working (if configured).
7. The SQLite file is created automatically at
   `backend/gracegifthub.db` (or wherever `DB_PATH` points) the first time
   the app starts, and is never recreated on later restarts.

## Deploying to LyteHosting / cPanel

1. Upload the project so `backend/` ends up as the application root,
   e.g. `gracegifthub-gift-hub/backend`.
2. cPanel → **Setup Python App** → Create Application:
   - Application root: `gracegifthub-gift-hub/backend`
   - Application URL: your domain (`gracegifthubgifthub.top`)
   - Application startup file: `passenger_wsgi.py`
   - Application Entry point: `application`
3. Once created, cPanel gives you an "Enter to the virtual environment"
   command — run it, then `cd` into the application root and
   `pip install -r requirements.txt`.
4. Create `backend/.env` (copy `.env.example`) and fill in the real
   SECRET_KEY, PAYSCRIBE_* keys, and PRODUCT_API_KEY (if used). cPanel's "Environment
   variables" section on the Setup Python App page works too — either
   way, `config.py` reads them.
5. Make sure the `backend/` directory (where `gracegifthub.db` will be
   created) is writable by the application's user — cPanel's Python App
   users normally already own this directory, so no extra chmod is
   usually needed; confirm with your host if the DB file fails to create.
6. Restart the app from the Setup Python App page. Check its log for the
   same `Product catalog API /account` / `/products` PASS/FAILED lines.
7. `passenger_wsgi.py` and `wsgi.py` both build the app from the same
   `create_app()` factory in `app.py` — nothing is duplicated between the
   PythonAnywhere and LyteHosting setups, so the same codebase serves both.
