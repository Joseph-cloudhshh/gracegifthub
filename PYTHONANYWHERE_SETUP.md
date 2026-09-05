# PYTHONANYWHERE DEPLOYMENT GUIDE

## Quick Setup for PythonAnywhere

### Step 1: Upload This ZIP File
1. Log in to PythonAnywhere
2. Go to Files section
3. Upload this entire zip file to your home directory
4. Extract it

### Step 2: Create .env File

In PythonAnywhere file editor, create a file: `.env` in the project root

Add these lines (replace with YOUR values):
```
PAYSCRIBE_PUBLIC_KEY=your_payscribe_public_key
PAYSCRIBE_SECRET_KEY=your_payscribe_secret_key
PAYSCRIBE_BASE_URL=https://api.payscribe.com/v1
WEBHOOK_SECRET=your_payscribe_webhook_secret
SMTP_USERNAME=supportgracegifthubgifthub@gmail.com
SMTP_PASSWORD=your_gmail_app_password
ADMIN_EMAIL=your_admin@email.com
JWT_SECRET=your_secret_key
DB_PATH=/home/yourusername/gracegifthub.db
```

Used for both checkout and wallet funding — Flutterwave has been fully retired from this app.

### Step 3: Install Requirements

In PythonAnywhere console:
```bash
cd ~/gracegifthub-gift-hub/backend
pip install --user -r requirements.txt
```

### Step 4: Configure Web App

1. Go to Web → Add a new web app
2. Choose Python 3.10
3. Choose Flask
4. Source code: `/home/yourusername/gracegifthub-gift-hub/backend`
5. Working directory: `/home/yourusername/gracegifthub-gift-hub/backend`
6. WSGI configuration file: (auto-generated, then edit)

### Step 5: Edit WSGI File

Edit the WSGI file generated in step 4:

Replace the entire content with:
```python
import sys
import os
from dotenv import load_dotenv

# Load environment variables
path = '/home/yourusername/gracegifthub-gift-hub/backend'
sys.path.insert(0, path)
os.chdir(path)
load_dotenv()

from app import create_app
app = create_app()

if __name__ == "__main__":
    app.run()
```

Replace `yourusername` with your PythonAnywhere username.

### Step 6: Set Static Files

Go to Web tab, scroll to Static files:
- URL: `/static/`
- Directory: `/home/yourusername/gracegifthub-gift-hub/frontend/`

### Step 7: Reload Web App

Click "Reload" button in Web tab.

### Step 8: Test

Visit: `https://yourusername.pythonanywhere.com`

---

## Folder Structure

```
gracegifthub-gift-hub/
├── backend/
│   ├── app.py (main app)
│   ├── models.py
│   ├── config.py
│   ├── requirements.txt
│   ├── routes/
│   │   ├── auth.py
│   │   ├── products.py
│   │   ├── wallet.py (NEW)
│   │   ├── public_settings.py (NEW)
│   │   └── ...
│   └── .env (YOU CREATE THIS)
├── frontend/
│   ├── index.html
│   ├── dashboard.html
│   ├── login.html
│   ├── signup.html
│   ├── js/
│   ├── css/
│   └── admin/
└── PYTHONANYWHERE_SETUP.md (this file)
```

---

## Important Notes

- Database (`gracegifthub.db`) will be auto-created in backend/ on first run
- Tables will auto-create (no migration needed)
- Contact info defaults are pre-filled, admin can change anytime
- Payscribe keys required for checkout and wallet funding to work
- SMTP credentials required for email notifications

---

## Troubleshooting

**"ModuleNotFoundError"** → Run pip install command again
**"DB not found"** → Wait 10 seconds, page will auto-create it
**"Payscribe error"** → Check PAYSCRIBE_PUBLIC_KEY and PAYSCRIBE_SECRET_KEY in .env
**"Email not sending"** → Check SMTP_USERNAME and SMTP_PASSWORD in .env

---

That's it! Your Gracegifthub v2 is now live on PythonAnywhere.
