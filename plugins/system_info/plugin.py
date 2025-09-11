from __future__ import annotations

import platform
import shutil
from typing import Any, Dict


class Plugin:
    meta = {
        "name": "system_info",
        "permissions": ["fs_read"],
        "description": "Informations système (OS/CPU/GPU/RAM)",
        "inputs": {},
    }

    def _gpu(self) -> Dict[str, Any]:
        # Détection simple via torch si présent
        try:
            import torch  # type: ignore

            return {"cuda": bool(torch.cuda.is_available())}
        except Exception:
            return {"cuda": False}

    def _ram(self) -> Dict[str, Any]:
        try:
            import psutil  # type: ignore

            mem = psutil.virtual_memory()
            return {"total": mem.total, "available": mem.available}
        except Exception:
            return {"total": None, "available": None}

    def run(self) -> Dict[str, Any]:
        return {
            "os": f"{platform.system()} {platform.release()}",
            "cpu": platform.processor() or platform.machine(),
            "gpu": self._gpu(),
            "ram": self._ram(),
        }


plugin = Plugin()

