"""Entry point for the PySide6 voice client."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from .ui.main_window import VoiceMainWindow


def run() -> None:
    """Start the voice UI."""
    app = QApplication.instance() or QApplication([])
    window = VoiceMainWindow()
    window.show()
    app.exec()
