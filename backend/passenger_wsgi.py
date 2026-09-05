"""
Passenger/cPanel entry point for LyteHosting.

LyteHosting's "Setup Python App" (Passenger) looks for passenger_wsgi.py
in the application root and expects a module-level `application` object.
This file does no work itself — it just puts backend/ on sys.path and
delegates to wsgi.py, so PythonAnywhere and LyteHosting share the exact
same create_app() factory and nothing is duplicated between them.

LyteHosting/cPanel setup:
    Application root: gracegifthub-gift-hub/backend
    Application startup file: passenger_wsgi.py
    Application Entry point: application
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from wsgi import application  # noqa: E402,F401
