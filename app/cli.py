from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings, get_settings
from app.core import plugins as plugins_module
from app.core.jobs import jobs_manager


# Compatibility shim for Click/Typer across versions (especially on Py3.10)
try:  # pragma: no cover - defensive
    import click  # type: ignore
    import inspect

    sig = inspect.signature(click.Parameter.make_metavar)
    if "ctx" in sig.parameters:
        _orig_make_metavar = click.Parameter.make_metavar

        def _patched_make_metavar(self, ctx=None):  # type: ignore[override]
            return _orig_make_metavar(self, ctx)

        click.Parameter.make_metavar = _patched_make_metavar  # type: ignore[assignment]
except Exception:
    pass

cli = typer.Typer(name="ivy", help="CLI IVY")
plugin_cli = typer.Typer(help="Gestion des plugins")
task_cli = typer.Typer(help="Gestion des tâches")
backup_cli = typer.Typer(help="Sauvegardes")
config_cli = typer.Typer(help="Configuration")

cli.add_typer(plugin_cli, name="plugin")
cli.add_typer(task_cli, name="task")
cli.add_typer(backup_cli, name="backup")
cli.add_typer(config_cli, name="config")


@cli.command()
def serve() -> None:
    """Démarrer le serveur FastAPI."""
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)


def _build_ui_app(static_dir: Path) -> FastAPI:
    app = FastAPI()
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")
    return app


@cli.command()
def ui(path: Optional[str] = typer.Option(None, "--path", help="Dossier webui/dist"), port: int = 5173):
    """Servir l'UI (build Vite) en statique."""
    dist = Path(path) if path else Path("webui") / "dist"
    if not dist.exists():
        typer.echo(f"Dossier introuvable: {dist}. Construisez le front (npm run build).")
        raise typer.Exit(code=1)
    app = _build_ui_app(dist)
    uvicorn.run(app, host="127.0.0.1", port=port)


@plugin_cli.command("list")
def plugin_list() -> None:
    plugins_module.load_plugins()
    items = [
        {"name": n, "state": d["state"], "meta": d["meta"]}
        for n, d in plugins_module.REGISTRY.items()
    ]
    typer.echo(json.dumps({"plugins": items}, ensure_ascii=False))


@plugin_cli.command("enable")
def plugin_enable(name: str):
    plugins_module.enable(name)
    typer.echo(f"Plugin {name} activé")


@plugin_cli.command("disable")
def plugin_disable(name: str):
    plugins_module.disable(name)
    typer.echo(f"Plugin {name} désactivé")


@plugin_cli.command("start")
def plugin_start(name: str):
    plugins_module.start(name)
    typer.echo(f"Plugin {name} démarré")


@plugin_cli.command("stop")
def plugin_stop(name: str):
    plugins_module.stop(name)
    typer.echo(f"Plugin {name} arrêté")


@plugin_cli.command("reload")
def plugin_reload(name: str):
    plugins_module.reload(name)
    typer.echo(f"Plugin {name} rechargé")


@plugin_cli.command("upload")
def plugin_upload(zip_path: str):
    data = Path(zip_path).read_bytes()
    name = plugins_module.install_zip(data)
    typer.echo(f"Plugin {name} installé")


@plugin_cli.command("scaffold")
def plugin_scaffold(name: str, output_dir: Optional[str] = typer.Option(None, "--dir", help="Répertoire plugins/ cible")):
    base = Path(output_dir) if output_dir else Path("plugins")
    target = base / name
    template = Path("plugins") / "_template" / "plugin.py"
    target.mkdir(parents=True, exist_ok=True)
    if not template.exists():
        typer.echo("Template introuvable: plugins/_template/plugin.py")
        raise typer.Exit(code=1)
    shutil.copyfile(template, target / "plugin.py")
    typer.echo(f"Créé: {target / 'plugin.py'}")


@task_cli.command("list")
def task_list():
    typer.echo(json.dumps({"jobs": jobs_manager.list_jobs()}, ensure_ascii=False))


@task_cli.command("add")
def task_add(
    type: str = typer.Argument(..., help="plugin|llm|backup"),
    params: str = typer.Option("{}", "--params", help="JSON paramètres"),
    schedule: str = typer.Option("{}", "--schedule", help="JSON schedule"),
    description: Optional[str] = typer.Option(None, "--desc"),
    tag: Optional[str] = typer.Option(None, "--tag"),
):
    pid = jobs_manager.add_job(type, json.loads(params), json.loads(schedule), description=description, tag=tag)
    typer.echo(pid)


@task_cli.command("remove")
def task_remove(job_id: str):
    ok = jobs_manager.remove_job(job_id)
    typer.echo("ok" if ok else "not_found")


@task_cli.command("run-now")
def task_run_now(job_id: str):
    ok = jobs_manager.run_now(job_id)
    typer.echo("scheduled" if ok else "not_found")


@task_cli.command("get")
def task_get(job_id: str):
    item = jobs_manager.get_job(job_id)
    if not item:
        typer.echo("not_found")
    else:
        typer.echo(json.dumps(item, ensure_ascii=False))


@task_cli.command("cancel")
def task_cancel(job_id: str):
    status = jobs_manager.cancel_job(job_id)
    typer.echo(status)


@task_cli.command("update")
def task_update(
    job_id: str,
    params: Optional[str] = typer.Option(None, "--params", help="JSON paramètres"),
    schedule: Optional[str] = typer.Option(None, "--schedule", help="JSON schedule"),
    description: Optional[str] = typer.Option(None, "--desc"),
    tag: Optional[str] = typer.Option(None, "--tag"),
):
    p = json.loads(params) if params else None
    s = json.loads(schedule) if schedule else None
    ok = jobs_manager.update_job(job_id, params=p, schedule=s, description=description, tag=tag)
    typer.echo("updated" if ok else "not_found")


@backup_cli.command("export")
def backup_export():
    path = jobs_manager._export_backup()  # type: ignore[attr-defined]
    typer.echo(str(path))


@backup_cli.command("import")
def backup_import(zip_path: str, dry_run: bool = True):
    import zipfile

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        plan = {"files": names[:10], "total": len(names), "dry_run": dry_run}
        typer.echo(json.dumps(plan, ensure_ascii=False))


@config_cli.command("print")
def config_print():
    s = Settings()
    typer.echo(json.dumps(s.model_dump(), ensure_ascii=False, default=str))


@config_cli.command("edit")
def config_edit():
    path = Path("config.json").resolve()
    if not path.exists():
        path.write_text("{}", encoding="utf-8")
    typer.echo(str(path))


if __name__ == "__main__":
    cli()
