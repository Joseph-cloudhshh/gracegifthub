"""
WSGI entry point for Gracegifthub Gift Hub.

Used directly by PythonAnywhere's WSGI configuration file (point its
`application` import at this module), and imported by passenger_wsgi.py
for LyteHosting/cPanel so both hosts share one application factory —
nothing is duplicated between them.

PythonAnywhere setup:
    In the "Code" section of your Web tab, set the WSGI configuration
    file to import from here, e.g. add this line near the bottom of
    the PythonAnywhere-generated WSGI file:

        import sys
        path = '/home/yourusername/gracegifthub-gift-hub/backend'
        if path not in sys.path:
            sys.path.insert(0, path)
        from wsgi import application

Generic WSGI/Passenger setup:
    Point the server at this file; it exposes a module-level
    `application` object, which is the standard WSGI entry point name.
"""

import os
import sys

# Make sure backend/ is on sys.path regardless of the directory the WSGI
# server was launched from, so `from config import Config`, `from models
# import db`, `from routes...` etc. keep working.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import create_app, print_product_api_status  # noqa: E402

application = create_app()

# Prints a clear PASS/FAIL for the TP Gifts Store integration in the
# server's error/startup log, same as running `python app.py` locally.
# Wrapped in try/except so a network hiccup during worker startup can
# never prevent the app itself from coming up.
try:
    print_product_api_status(application)
except Exception as e:  # noqa: BLE001
    print(f"TP Gifts API startup check failed to run: {e}")
