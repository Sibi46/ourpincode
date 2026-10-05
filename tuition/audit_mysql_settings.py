"""Disposable localhost audit only. Never select these settings in production."""
from jobportal.test_settings import *

DATABASES = {'default': {
    'ENGINE': 'django.db.backends.mysql', 'NAME': 'tuition_audit',
    'USER': 'root', 'PASSWORD': '', 'HOST': '127.0.0.1', 'PORT': '13317',
    'OPTIONS': {'charset': 'utf8mb4', 'init_command': "SET sql_mode='STRICT_ALL_TABLES'", 'isolation_level': 'read committed'},
    'TEST': {'NAME': 'test_tuition_phase5'},
}}
