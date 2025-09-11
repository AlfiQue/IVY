from __future__ import annotations


class Plugin:
    meta = {
        "name": "RENAME_ME",
        "description": "Plugin de démonstration",
        "permissions": ["fs_read"],
        "inputs": {
            # Exemple de schéma: {"text": (str, ...)}
            "schema": {}
        },
    }

    def start(self):
        # Optionnel: initialisation
        pass

    def stop(self):
        # Optionnel: nettoyage
        pass

    def run(self, **kwargs):
        # Logique principale du plugin
        return {"ok": True, "kwargs": kwargs}


plugin = Plugin()

