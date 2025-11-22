"""Packager PyInstaller pour la console vocale IVY."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP_APP = ROOT / "desktop" / "voice_client" / "app.py"
RESOURCES = ROOT / "desktop" / "voice_client" / "resources"
CONFIG_DIR = ROOT / "desktop" / "voice_client" / "config"
DIST_ROOT = ROOT / "dist" / "voice_client"
BUILD_DIR = DIST_ROOT / "build"
SPEC_DIR = DIST_ROOT / "specs"


def ensure_pyinstaller() -> None:
    """Install or upgrade PyInstaller in the current environment."""
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"],
        check=True,
    )


def package_voice_client() -> Path:
    """Build the standalone PySide6 application."""
    if not DESKTOP_APP.exists():
        raise FileNotFoundError(f"Entrée PySide6 introuvable: {DESKTOP_APP}")

    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    if SPEC_DIR.exists():
        shutil.rmtree(SPEC_DIR)

    ensure_pyinstaller()

    add_data = [
        f"{RESOURCES}{os.pathsep}desktop/voice_client/resources",
        f"{CONFIG_DIR}{os.pathsep}desktop/voice_client/config",
    ]

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        "IVYVoice",
        "--clean",
        "--noconfirm",
        "--windowed",
        "--distpath",
        str(DIST_ROOT),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(SPEC_DIR),
    ]
    for item in add_data:
        command.extend(["--add-data", item])
    command.append(str(DESKTOP_APP))

    subprocess.run(command, check=True)
    exe_path = DIST_ROOT / "IVYVoice" / ("IVYVoice.exe" if os.name == "nt" else "IVYVoice")
    if not exe_path.exists():
        raise RuntimeError(f"Executable introuvable après construction: {exe_path}")
    return exe_path


def main() -> None:
    exe_path = package_voice_client()
    print(f"[OK] Client vocal empaqueté: {exe_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        print(f"[ERREUR] {exc}")
        raise
