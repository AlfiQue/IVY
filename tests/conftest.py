from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "tests-secret-value")

from app.core.config import get_settings  # noqa: E402

def _reset_settings() -> None:
    get_settings.cache_clear()
    get_settings()

_reset_settings()
