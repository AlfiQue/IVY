"""Gestion des plugins de l'application."""

from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import hashlib
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Type
import multiprocessing as mp
import threading
import psutil

from pydantic import BaseModel, create_model
from app.core.metrics import inc_plugin_exec
from app.core.history import log_event_sync

# Dossier des plugins et des journaux de plantage
PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins"
LOG_DIR = Path(__file__).resolve().parents[1] / "logs" / "plugins"

# registre global : {name: {instance, state, meta, module, path}}
REGISTRY: dict[str, dict[str, Any]] = {}

# Permissions reconnues pour les plugins
# Permissions reconnues (synonymes inclus)
KNOWN_PERMISSIONS = {
    "network",
    "filesystem",
    "process",
    "net",      # synonyme de network
    "fs_read",  # accÃ¨s lecture filesystem
    "fs_write", # accÃ¨s Ã©criture filesystem
}


class PluginError(Exception):
    """Erreur liÃ©e Ã  la gestion des plugins."""




def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def _log_plugin_event(action: str, name: str, **details: Any) -> None:
    payload = {"plugin": name}
    for key, value in details.items():
        if value is None:
            continue
        payload[key] = _json_safe(value)
    try:
        log_event_sync(f"plugin.{action}", payload)
    except Exception:
        pass


def _validate_permissions(plugin_name: str, permissions: list[str]) -> None:
    unknown = [p for p in permissions if p not in KNOWN_PERMISSIONS]
    if unknown:
        raise PluginError(
            f"Permissions inconnues pour le plugin '{plugin_name}': {', '.join(unknown)}"
        )


def _validate_schema(plugin_name: str, schema_def: Any) -> Type[BaseModel]:
    if isinstance(schema_def, type) and issubclass(schema_def, BaseModel):
        return schema_def
    if isinstance(schema_def, dict):
        try:
            return create_model(f"{plugin_name.capitalize()}Input", **schema_def)
        except Exception as exc:  # pragma: no cover - dÃ©tails internes
            raise PluginError(
                f"SchÃ©ma d'entrÃ©e invalide pour le plugin '{plugin_name}': {exc}"
            ) from exc
    raise PluginError(
        f"inputs.schema doit Ãªtre une classe Pydantic ou un dictionnaire de champs pour le plugin '{plugin_name}'"
    )



def load_plugins(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    """Découvrir et charger les plugins disponibles.

    Combine `directory` (ou `PLUGIN_DIR`) et le dossier builtin du dépôt.
    Ignore les dossiers commençant par `_` (ex: `_template`).
    """
    REGISTRY.clear()
    primary = Path(directory) if directory else PLUGIN_DIR
    builtin = Path(__file__).resolve().parents[2] / "plugins"
    search_dirs: list[Path] = []
    for d in (primary, builtin):
        if d.exists() and d.is_dir() and d not in search_dirs:
            search_dirs.append(d)

    for base in search_dirs:
        for path in base.iterdir():
            if not path.is_dir() or path.name.startswith("_"):
                continue
            module_file = path / "plugin.py"
            if not module_file.exists():
                continue
            spec = importlib.util.spec_from_file_location(f"plugins.{path.name}", module_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            # Inject helpers commonly used by minimal test plugins
            module.__dict__.setdefault("Path", Path)
            sys.modules[spec.name] = module
            try:
                buf_out, buf_err = io.StringIO(), io.StringIO()
                with redirect_stdout(buf_out), redirect_stderr(buf_err):
                    spec.loader.exec_module(module)
            except Exception:
                _dump(path.name, buf_out.getvalue(), buf_err.getvalue())
                raise
            plugin_inst = getattr(module, "plugin", None)
            if plugin_inst is None:
                continue
            meta = getattr(plugin_inst, "meta", {}) or {}
            name = meta.get("name", path.name)
            perms = meta.get("permissions", [])
            _validate_permissions(name, perms)
            inputs = meta.get("inputs", {})
            schema_def = inputs.get("schema")
            if schema_def is not None:
                inputs["schema"] = _validate_schema(name, schema_def)
            meta["name"] = name
            REGISTRY[name] = {
                "instance": plugin_inst,
                "state": REGISTRY.get(name, {}).get("state", "disabled"),
                "meta": meta,
                "module": module,
                "path": path,
            }
    return {name: data["meta"] for name, data in REGISTRY.items()}


def _safe_extract(zipf: zipfile.ZipFile, dest: Path) -> None:
    """Extract a Zip safely (prevents Zip Slip)."""
    for member in zipf.infolist():
        target = dest / member.filename
        target_resolved = target.resolve()
        if not str(target_resolved).startswith(str(dest.resolve())):
            raise PluginError("Archive invalide: chemins dangereux")
        if member.is_dir():
            target_resolved.mkdir(parents=True, exist_ok=True)
        else:
            target_resolved.parent.mkdir(parents=True, exist_ok=True)
            with zipf.open(member) as src, open(target_resolved, "wb") as dst:
                shutil.copyfileobj(src, dst)


def install_zip(data: bytes) -> str:
    """Install a plugin from a ZIP archive and return its name.

    The name is inferred from the folder that contains a plugin.py.
    If a plugin with the same name exists, it is replaced.
    """
    replaced = False
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # extract to a temp dir for inspection
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            _safe_extract(zf, tmp_path)
            candidates = list(tmp_path.rglob("plugin.py"))
            if not candidates:
                raise PluginError("Archive invalide: plugin.py introuvable")
            base = candidates[0].parent
            name = base.name
            # nom autorisÃ©: a-z0-9_+-
            import re
            if not re.fullmatch(r"[a-z0-9_+-]+", name):
                raise PluginError("Nom de plugin invalide (autorisÃ©: a-z0-9_+-)")
            dest = PLUGIN_DIR / name
            replaced = dest.exists()
            if replaced:
                shutil.rmtree(dest, ignore_errors=True)
            shutil.move(str(base), str(dest))
    # reload registry
    load_plugins()
    # checksum SHA256 (contenu archive)
    sha256 = hashlib.sha256(data).hexdigest()
    try:
        (LOG_DIR / f"{name}-checksum.txt").write_text(sha256, encoding="utf-8")
    except Exception:
        pass
    _log_plugin_event("installed", name, checksum=sha256, replaced=replaced)
    return name


def _dump(name: str, stdout: str | None = None, stderr: str | None = None) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"{name}-{ts}.log"
    parts = [
        "=== stdout ===\n",
        stdout or "",
        "\n\n=== stderr ===\n",
        stderr or "",
        "\n\n=== traceback ===\n",
        traceback.format_exc(),
    ]
    log_path.write_text("".join(parts), encoding="utf-8")


def enable(name: str) -> None:
    """Activer un plugin."""

    if name not in REGISTRY:
        raise KeyError(name)
    REGISTRY[name]["state"] = "enabled"
    _log_plugin_event("enabled", name)


def disable(name: str) -> None:
    """DÃ©sactiver un plugin et l'arrÃªter si nÃ©cessaire."""

    data = REGISTRY.get(name)
    if not data:
        raise KeyError(name)
    previous = data["state"]
    try:
        if previous == "running":
            try:
                buf_out, buf_err = io.StringIO(), io.StringIO()
                with redirect_stdout(buf_out), redirect_stderr(buf_err):
                    stop(name)
            except Exception:
                _dump(name, buf_out.getvalue(), buf_err.getvalue())
                raise
        data["state"] = "disabled"
    except Exception:
        data["state"] = previous
        raise
    else:
        _log_plugin_event("disabled", name, previous_state=previous)


def start(name: str) -> None:
    """DÃ©marrer un plugin."""

    data = REGISTRY.get(name)
    if not data:
        raise KeyError(name)
    func = getattr(data["instance"], "start", None)
    try:
        if callable(func):
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                func()
        data["state"] = "running"
    except Exception:
        _dump(name, buf_out.getvalue(), buf_err.getvalue())
        raise
    else:
        _log_plugin_event("started", name)


def stop(name: str) -> None:
    """ArrÃªter un plugin."""

    data = REGISTRY.get(name)
    if not data:
        raise KeyError(name)
    func = getattr(data["instance"], "stop", None)
    try:
        if callable(func):
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                func()
        data["state"] = "stopped"
    except Exception:
        _dump(name, buf_out.getvalue(), buf_err.getvalue())
        raise
    else:
        _log_plugin_event("stopped", name)


def reload(name: str) -> None:
    """Recharger un plugin avec retour arriÃ¨re en cas d'Ã©chec."""

    data = REGISTRY.get(name)
    if not data:
        raise KeyError(name)

    prev = data.copy()
    was_running = data["state"] == "running"
    try:
        if was_running:
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                stop(name)
    except Exception:
        _dump(name, buf_out.getvalue(), buf_err.getvalue())
        raise

    module_file = data["path"] / "plugin.py"
    spec = importlib.util.spec_from_file_location(f"plugins.{name}", module_file)
    if spec is None or spec.loader is None:  # pragma: no cover - sÃ©curitÃ©
        raise PluginError(f"Impossible de recharger le plugin {name}")
    module = importlib.util.module_from_spec(spec)
    module.__dict__.setdefault("Path", Path)
    sys.modules[spec.name] = module
    try:
        buf_out2, buf_err2 = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out2), redirect_stderr(buf_err2):
            spec.loader.exec_module(module)
    except Exception:
        _dump(name, buf_out2.getvalue(), buf_err2.getvalue())
        raise

    plugin_inst = getattr(module, "plugin")
    meta = getattr(plugin_inst, "meta", {}) or {}
    perms = meta.get("permissions", [])
    _validate_permissions(name, perms)
    inputs = meta.get("inputs", {})
    schema_def = inputs.get("schema")
    if schema_def is not None:
        inputs["schema"] = _validate_schema(name, schema_def)
    meta["name"] = name

    data.update(
        {"instance": plugin_inst, "module": module, "meta": meta, "state": "disabled"}
    )
    try:
        enable(name)
        if was_running:
            buf_out3, buf_err3 = io.StringIO(), io.StringIO()
            with redirect_stdout(buf_out3), redirect_stderr(buf_err3):
                start(name)
    except Exception:
        REGISTRY[name] = prev
        if was_running:
            try:
                start(name)
            except Exception:
                _dump(name, buf_out3.getvalue(), buf_err3.getvalue())
        _dump(name)
        raise
    else:
        _log_plugin_event("reloaded", name, was_running=was_running)


def delete(name: str) -> None:
    """Supprimer un plugin avec retour arriÃ¨re en cas d'Ã©chec."""

    data = REGISTRY.get(name)
    if not data:
        raise KeyError(name)
    prev = data.copy()
    path = data["path"]
    try:
        if data["state"] == "running":
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                stop(name)
    except Exception:
        _dump(name, buf_out.getvalue(), buf_err.getvalue())
        raise
    try:
        REGISTRY.pop(name, None)
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        REGISTRY[name] = prev
        _dump(name)
        raise
    else:
        _log_plugin_event("deleted", name, path=str(path))


def run(name: str, **kwargs: Any) -> Any:
    data = REGISTRY.get(name)
    if not data:
        raise KeyError(name)
    func = getattr(data["instance"], "run", None)
    if not callable(func):
        raise PluginError(f"Plugin {name} n'implÃ©mente pas run")
    try:
        from app.core.config import Settings  # import local

        settings = Settings()
        # contrÃ´le RAM courante (process global)
        rss_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        if rss_mb > settings.plugin_max_ram_mb:
            raise PluginError(f"Limite RAM atteinte ({rss_mb:.0f}MB > {settings.plugin_max_ram_mb}MB)")

        result_holder: dict[str, Any] = {}
        err_holder: dict[str, Exception] = {}
        buf_out, buf_err = io.StringIO(), io.StringIO()

        def _record_run(status: str, **extra: Any) -> None:
            duration_ms = (time.perf_counter() - started_at) * 1000
            payload = {"status": status, "duration_ms": round(duration_ms, 2), "params": params_snapshot}
            for key, value in extra.items():
                if value is None:
                    continue
                payload[key] = _json_safe(value)
            _log_plugin_event("run", name, **payload)

        # Sandbox sous-processus pour plugins externes (optionnel)
        try:
            from app.core.config import Settings as _S  # lazy import
            _s = _S()
            nosbx = set(getattr(_s, "plugin_sandbox_nosandbox", ["tasks", "llm", "system_info"]))
            if getattr(_s, "plugin_sandbox_enabled", False) and name not in nosbx:
                module_file = data["path"] / "plugin.py"

                def _proc(entry_path: str, q):
                    try:
                        spec = importlib.util.spec_from_file_location(f"plugins.{name}", Path(entry_path))
                        if spec is None or spec.loader is None:
                            q.put({"ok": False, "error": "load_failed"})
                            return
                        module = importlib.util.module_from_spec(spec)
                        module.__dict__.setdefault("Path", Path)
                        spec.loader.exec_module(module)
                        plugin_inst = getattr(module, "plugin")
                        out = plugin_inst.run(**kwargs)
                        q.put({"ok": True, "result": out})
                    except Exception as e:
                        q.put({"ok": False, "error": str(e)})

                q = mp.Queue()
                p = mp.Process(target=_proc, args=(str(module_file), q), daemon=True)
                p.start()
                p.join(timeout=_s.plugin_timeout_sec)
                if p.is_alive():
                    try:
                        p.terminate()
                    finally:
                        p.join(timeout=_s.plugin_hard_kill_grace_sec)
                    inc_plugin_exec(name, "timeout")
                    raise PluginError(f"Timeout plugin ({_s.plugin_timeout_sec}s)")
                try:
                    msg = q.get_nowait()
                except Exception:
                    msg = {"ok": False, "error": "no_output"}
                if not msg.get("ok"):
                    inc_plugin_exec(name, "error")
                    raise PluginError(str(msg.get("error")))
                result_value = msg.get("result")
                inc_plugin_exec(name, "success")
                _record_run("success", sandbox=True, result=result_value)
                return result_value
        except Exception:
            # Sandbox non disponible → fallback thread
            pass

        def _target():
            try:
                with redirect_stdout(buf_out), redirect_stderr(buf_err):
                    result_holder["result"] = func(**kwargs)
            except Exception as e:
                err_holder["err"] = e

        th = threading.Thread(target=_target, daemon=True)
        th.start()
        th.join(timeout=settings.plugin_timeout_sec)
        if th.is_alive():
            inc_plugin_exec(name, "timeout")
            raise PluginError(f"Timeout plugin ({settings.plugin_timeout_sec}s)")
        if "err" in err_holder:
            inc_plugin_exec(name, "error")
            raise err_holder["err"]
        result_value = result_holder.get("result")
        inc_plugin_exec(name, "success")
        _record_run("success", sandbox=False, result=result_value)
        return result_value
    except Exception as exc:
        _dump(name, buf_out.getvalue() if 'buf_out' in locals() else None, buf_err.getvalue() if 'buf_err' in locals() else None)
        try:
            inc_plugin_exec(name, "crash")
        except Exception:
            pass
        try:
            _record_run("error", error=str(exc))
        except Exception:
            pass
        raise


