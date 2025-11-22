import os

os.environ.setdefault("DISABLE_AUTH", "true")
os.environ.setdefault("JWT_SECRET", "test-secret-super-long-ivyx1234567890")

from app.core.config import get_settings

get_settings.cache_clear()
