from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence


def resolve_restart_command() -> list[str] | None:
    """Retourne la commande a utiliser pour redemarrer l'application."""
    override = os.environ.get("IVY_RESTART_CMD")
    if override:
        try:
            parts = shlex.split(override)
        except ValueError:
            return None
        return parts or None
    # fallback: lecteur .env si present
    env_path = Path(".env")
    if env_path.is_file():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("IVY_RESTART_CMD="):
                    candidate = line.split("=", 1)[1].strip()
                    if candidate:
                        try:
                            parts = shlex.split(candidate)
                        except ValueError:
                            parts = []
                        if parts:
                            return parts
        except Exception:
            pass
    executable = sys.executable
    if not executable:
        return None
    argv = sys.argv[1:]
    if argv:
        return [executable, *argv]
    return [executable, "-m", "app.cli", "serve"]


def _spawn_process(command: Sequence[str], delay: float = 0.0) -> bool:
    try:
        if delay > 0:
            time.sleep(delay)
        popen_kwargs: dict[str, object] = {}
        if os.name == "nt":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            popen_kwargs["creationflags"] = creation_flags
        else:
            popen_kwargs["start_new_session"] = True
        subprocess.Popen(
            list(command),
            close_fds=os.name != "nt",
            cwd=os.getcwd(),
            **popen_kwargs,
        )
    except Exception:
        return False
    return True


def restart_and_exit(delay: float = 0.5) -> None:
    """Lance le redemarrage puis termine brutalement le processus courant."""
    cmd = resolve_restart_command()
    if not cmd or not _spawn_process(cmd, delay=delay):
        os._exit(0)
    os._exit(0)
