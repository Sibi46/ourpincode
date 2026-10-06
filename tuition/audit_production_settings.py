"""Inspect secure production defaults with synthetic credentials, never .env."""
import os
import runpy
from pathlib import Path
from unittest.mock import patch
import dotenv

with patch.dict(os.environ, {'DJANGO_SECRET_KEY': 'synthetic-audit-only-89e530c8-c659-4968-a986-1f0ca8d166fd'}, clear=True), patch.object(dotenv, 'load_dotenv'):
    _config = runpy.run_path(str(Path(__file__).resolve().parents[1]/'jobportal/settings.py'))
globals().update({key: value for key, value in _config.items() if key.isupper()})
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
