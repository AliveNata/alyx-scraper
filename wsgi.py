"""
WSGI entry point untuk PythonAnywhere.

Di PythonAnywhere → Web → WSGI configuration file:
  Ganti isi file menjadi:
    import sys, os
    path = '/home/alivenata/pet-scraper'
    if path not in sys.path:
        sys.path.insert(0, path)
    from wsgi import application
"""
import sys
import os

# ── Tambahkan project directory ke sys.path ──────────────────────────
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# ── Import Flask app ─────────────────────────────────────────────────
from app import app as application  # noqa: F401

# PythonAnywhere menggunakan variabel 'application'
