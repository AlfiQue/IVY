from __future__ import annotations

from typing import Any, Dict

from app.core.llm import LLM


class Plugin:
    meta = {
        "name": "llm",
        "permissions": ["fs_read"],
        "description": "Accès au LLM local",
        "inputs": {"schema": {"prompt": (str, ...), "options": (dict, None)}},
    }

    def run(self, prompt: str, options: Dict[str, Any] | None = None) -> str:
        llm = LLM()
        return llm.infer(prompt, options)


plugin = Plugin()

