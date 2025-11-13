from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings, get_settings
from app.core.jobs import jobs_manager
from app.core.security import maybe_reset_admin

try:  # pragma: no cover
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
task_cli = typer.Typer(help="Gestion des taches")
backup_cli = typer.Typer(help="Sauvegardes")
config_cli = typer.Typer(help="Configuration")

cli.add_typer(task_cli, name="task")
cli.add_typer(backup_cli, name="backup")
cli.add_typer(config_cli, name="config")


@cli.command()
def serve() -> None:
    """Demarrer le serveur FastAPI."""
    temp = maybe_reset_admin()
    if temp:
        print(f"[RESET-ADMIN] Nouveau mot de passe genere: {temp}")
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)


def _build_ui_app(static_dir: Path) -> FastAPI:
    app = FastAPI()
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")
    return app


@cli.command()
def ui(path: Optional[str] = typer.Option(None, "--path", help="Dossier webui/dist"), port: int = 5173) -> None:
    """Servir l'UI (build Vite) en statique."""
    dist = Path(path) if path else Path("webui") / "dist"
    if not dist.exists():
        typer.echo(f"Dossier introuvable: {dist}. Construisez le front (npm run build).")
        raise typer.Exit(code=1)
    app = _build_ui_app(dist)
    uvicorn.run(app, host="127.0.0.1", port=port)


@task_cli.command("list")
def task_list() -> None:
    typer.echo(json.dumps({"jobs": jobs_manager.list_jobs()}, ensure_ascii=False))


@task_cli.command("add")
def task_add(
    type: str = typer.Argument(..., help="plugin|llm|backup"),
    params: str = typer.Option("{}", "--params", help="JSON parametres"),
    schedule: str = typer.Option("{}", "--schedule", help="JSON schedule"),
    description: Optional[str] = typer.Option(None, "--desc"),
    tag: Optional[str] = typer.Option(None, "--tag"),
) -> None:
    job_id = jobs_manager.add_job(type, json.loads(params), json.loads(schedule), description=description, tag=tag)
    typer.echo(job_id)


@task_cli.command("remove")
def task_remove(job_id: str) -> None:
    ok = jobs_manager.remove_job(job_id)
    typer.echo("ok" if ok else "not_found")


@task_cli.command("run-now")
def task_run_now(job_id: str) -> None:
    ok = jobs_manager.run_now(job_id)
    typer.echo("scheduled" if ok else "not_found")


@task_cli.command("get")
def task_get(job_id: str) -> None:
    item = jobs_manager.get_job(job_id)
    if not item:
        typer.echo("not_found")
    else:
        typer.echo(json.dumps(item, ensure_ascii=False))


@task_cli.command("cancel")
def task_cancel(job_id: str) -> None:
    status = jobs_manager.cancel_job(job_id)
    typer.echo(status)


@task_cli.command("update")
def task_update(
    job_id: str,
    params: Optional[str] = typer.Option(None, "--params", help="JSON parametres"),
    schedule: Optional[str] = typer.Option(None, "--schedule", help="JSON schedule"),
    description: Optional[str] = typer.Option(None, "--desc"),
    tag: Optional[str] = typer.Option(None, "--tag"),
) -> None:
    parsed_params = json.loads(params) if params else None
    parsed_schedule = json.loads(schedule) if schedule else None
    ok = jobs_manager.update_job(job_id, params=parsed_params, schedule=parsed_schedule, description=description, tag=tag)
    typer.echo("updated" if ok else "not_found")


@backup_cli.command("export")
def backup_export() -> None:
    path = jobs_manager._export_backup()  # type: ignore[attr-defined]
    typer.echo(str(path))


@backup_cli.command("import")
def backup_import(zip_path: str, dry_run: bool = True) -> None:
    import zipfile

    with zipfile.ZipFile(zip_path, "r") as archive:
        names = archive.namelist()
        plan = {"files": names[:10], "total": len(names), "dry_run": dry_run}
        typer.echo(json.dumps(plan, ensure_ascii=False))


@config_cli.command("print")
def config_print() -> None:
    settings = Settings()
    typer.echo(json.dumps(settings.model_dump(), ensure_ascii=False, default=str))


@config_cli.command("edit")
def config_edit() -> None:
    path = Path("config.json").resolve()
    if not path.exists():
        path.write_text("{}", encoding="utf-8")
    typer.echo(str(path))


if __name__ == "__main__":
    cli()
