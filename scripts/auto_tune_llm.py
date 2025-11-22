"""Automatise la recherche d'un réglage LLM optimal."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.core.config import Settings
from app.core.llm import LLMClient, build_chat_messages


@dataclass(slots=True)
class TrialResult:
    value: float
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    samples: int


@dataclass(slots=True)
class AutoTuneSummary:
    param: str
    results: list[TrialResult]
    best: TrialResult


async def measure_latency(
    settings: Settings,
    *,
    prompt: str,
    samples: int,
) -> TrialResult:
    """Mesure la latence moyenne sur un prompt donné."""
    client = LLMClient(settings)
    system = getattr(settings, "chat_system_prompt", "Tu es IVY, assistant local.")
    messages = build_chat_messages(system=system, prompt=prompt)

    latencies: list[float] = []
    for _ in range(samples):
        started = time.perf_counter()
        await client.chat(messages)
        latencies.append((time.perf_counter() - started) * 1000.0)

    avg = sum(latencies) / len(latencies)
    return TrialResult(
        value=0.0,
        avg_latency_ms=avg,
        min_latency_ms=min(latencies),
        max_latency_ms=max(latencies),
        samples=samples,
    )


async def _run_trial(
    param: str,
    target_value: float,
    base_settings: Settings,
    *,
    prompt: str,
    samples: int,
) -> TrialResult:
    overrides: dict[str, Any] = {param: target_value}
    if param.startswith("llm_speculative"):
        overrides.setdefault("llm_speculative_enabled", True)
    applied = base_settings.model_copy(update=overrides)

    result = await measure_latency(applied, prompt=prompt, samples=samples)
    return TrialResult(
        value=target_value,
        avg_latency_ms=result.avg_latency_ms,
        min_latency_ms=result.min_latency_ms,
        max_latency_ms=result.max_latency_ms,
        samples=samples,
    )


def _build_values(kind: str, start: float, stop: float, step: float) -> list[float]:
    if step <= 0:
        raise ValueError("step doit être > 0")
    values: list[float] = []
    current = start
    if kind == "int":
        current = int(round(current))
        stop = int(round(stop))
        step = int(round(step))
        while current >= stop:
            values.append(float(current))
            current -= step
    else:
        while current >= stop - 1e-9:
            values.append(round(current, 6))
            current -= step
    return values


def _apply_best_to_config(param: str, value: float, config_path: Path) -> None:
    doc = json.loads(config_path.read_text(encoding="utf-8"))
    doc[param] = int(value) if value.is_integer() else value
    if param.startswith("llm_speculative"):
        doc["llm_speculative_enabled"] = True
    config_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def auto_tune_parameter(
    param: str,
    *,
    kind: str,
    start: float,
    stop: float,
    step: float,
    prompt: str,
    samples: int,
    apply: bool,
    config_path: Path,
    base_settings: Settings | None = None,
) -> AutoTuneSummary:
    settings = base_settings or Settings()
    values = _build_values(kind, start, stop, step)
    if not values:
        raise ValueError("aucune valeur à tester")

    results: list[TrialResult] = []
    for value in values:
        result = await _run_trial(
            param,
            value,
            settings,
            prompt=prompt,
            samples=samples,
        )
        results.append(result)

    best = min(results, key=lambda r: r.avg_latency_ms)

    if apply:
        if not config_path.exists():
            raise FileNotFoundError(f"config introuvable: {config_path}")
        _apply_best_to_config(param, best.value, config_path)

    return AutoTuneSummary(param=param, results=results, best=best)


def _format_summary(summary: AutoTuneSummary) -> str:
    lines = ["Résultats :"]
    for result in summary.results:
        marker = "*" if result is summary.best else " "
        lines.append(
            f"{marker} {summary.param}={result.value:<8} "
            f"avg={result.avg_latency_ms:.2f}ms  "
            f"min={result.min_latency_ms:.2f}  "
            f"max={result.max_latency_ms:.2f}"
        )
    lines.append(
        f"\nMeilleure valeur: {summary.param}={summary.best.value} "
        f"(latence moyenne {summary.best.avg_latency_ms:.2f} ms)"
    )
    return "\n".join(lines)


async def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Optimisation automatique d'un paramètre LLM.")
    parser.add_argument("--param", default="llm_speculative_max_draft_tokens", help="Clé Settings à optimiser.")
    parser.add_argument("--kind", choices=("int", "float"), default="int", help="Type numérique du paramètre.")
    parser.add_argument("--start", type=float, default=128.0, help="Valeur de départ (testée en premier).")
    parser.add_argument("--stop", type=float, default=16.0, help="Valeur minimale à explorer.")
    parser.add_argument("--step", type=float, default=16.0, help="Pas entre deux essais (positif).")
    parser.add_argument("--prompt", default="Explique en deux phrases comment surveiller un serveur local.", help="Prompt de test.")
    parser.add_argument("--samples", type=int, default=2, help="Nombre de runs par valeur.")
    parser.add_argument("--apply", action="store_true", help="Écrit la meilleure valeur dans config.json.")
    parser.add_argument("--config", default="config.json", help="Chemin du config.json à mettre à jour.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        summary = await auto_tune_parameter(
            args.param,
            kind=args.kind,
            start=args.start,
            stop=args.stop,
            step=args.step,
            prompt=args.prompt,
            samples=args.samples,
            apply=args.apply,
            config_path=Path(args.config),
        )
    except ValueError as exc:
        print(f"Paramètres invalides: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"[auto-tune] Paramètre: {args.param}")
    print(f"[auto-tune] Valeurs testées: {[r.value for r in summary.results]}")
    for result in summary.results:
        print(
            f"[auto-tune] {args.param}={result.value} "
            f"=> {result.avg_latency_ms:.2f} ms "
            f"(min {result.min_latency_ms:.2f} / max {result.max_latency_ms:.2f})"
        )
    print()
    print(_format_summary(summary))
    if args.apply:
        print(f"[auto-tune] Mise à jour de {args.config} avec {args.param}={summary.best.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
