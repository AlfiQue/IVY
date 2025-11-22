"""DPAPI helpers (Windows only)."""

from __future__ import annotations

try:
    import win32crypt  # type: ignore[import]
except ImportError:  # pragma: no cover - Windows only dependency
    win32crypt = None  # type: ignore[assignment]


def protect(data: bytes) -> bytes:
    """Encrypt data with DPAPI (user scope)."""
    if win32crypt is None:  # pragma: no cover
        raise RuntimeError("win32crypt not available. Please install pywin32.")
    return win32crypt.CryptProtectData(data, None, None, None, None, 0)[1]


def unprotect(data: bytes) -> bytes:
    """Decrypt data with DPAPI."""
    if win32crypt is None:  # pragma: no cover
        raise RuntimeError("win32crypt not available. Please install pywin32.")
    return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
