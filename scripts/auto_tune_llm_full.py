"""Optimisation complète de plusieurs paramètres LLM avec mesure de gain."""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from app.core.config import Settings
from scripts.auto_tune_llm import (
    AutoTuneSummary,
    TrialResult,
    auto_tune_parameter,
    measure_latency,
    _build_values,
)

DEFAULT_PLAN: list[dict[str, object]] = [
    {"param": "llm_speculative_max_draft_tokens", "kind": "int", "start": 128, "stop": 16, "step": 16},
    {"param": "llm_max_output_tokens", "kind": "int", "start": 512, "stop": 64, "step": 64},
    {"param": "llm_temperature", "kind": "float", "start": 0.9, "stop": 0.3, "step": 0.1},
    {"param": "llm_speculative_context_tokens", "kind": "int", "start": 4096, "stop": 1024, "step": 512},
]


@dataclass(slots=True)
class StepResult:
    summary: AutoTuneSummary


def _format_trial(label: str, trial: TrialResult) -> str:
    return (
        f"{label}: avg={trial.avg_latency_ms:.2f} ms "
        f"(min {trial.min_latency_ms:.2f} / max {trial.max_latency_ms:.2f}) "
        f"on {trial.samples} sample(s)"
    )


def _count_value_runs(kind: str, start: float, stop: float, step: float) -> int:
    try:
        return len(_build_values(kind, start, stop, step))
    except ValueError:
        return 0


async def _execute_plan(
    plan: Sequence[dict[str, object]],
    *,
    prompt: str,
    samples: int,
    config_path: Path,
) -> list[StepResult]:
    results: list[StepResult] = []
    total_steps = len(plan)
    for idx, spec in enumerate(plan, start=1):
        param = str(spec["param"])
        kind = str(spec.get("kind", "int"))
        start = float(spec.get("start", 0.0))
        stop = float(spec.get("stop", 0.0))
        step = float(spec.get("step", 1.0))

        value_count = _count_value_runs(kind, start, stop, step)
        print(
            f"\n[auto-tune/full] Étape {idx}/{total_steps} : {param} "
            f"({kind}, {value_count} valeur(s), ~{value_count * samples} run(s))"
        )
        step_started = time.perf_counter()
        summary = await auto_tune_parameter(
            param,
            kind=kind,
            start=start,
            stop=stop,
            step=step,
            prompt=prompt,
            samples=samples,
            apply=True,
            config_path=config_path,
        )
        print(
            _format_trial(
                f"  -> meilleur {param}={summary.best.value}",
                summary.best,
            )
        )
        step_elapsed = time.perf_counter() - step_started
        print(f"  Durée étape: {step_elapsed:.1f}s")
        results.append(StepResult(summary=summary))
    return results


async def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Optimisation complète (multi-paramètres) des réglages LLM.")
    parser.add_argument("--prompt", default="Explique en deux phrases comment optimiser un LLM local.", help="Prompt de référence.")
    parser.add_argument("--samples", type=int, default=2, help="Runs par mesure.")
    parser.add_argument("--config", default="config.json", help="Chemin du config.json à mettre à jour.")
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        help="Paramètres à ignorer (option répétable).",
    )
    parser.add_argument(
        "--include-gpu-layers",
        action="store_true",
        help="Ajoute l'optimisation de llm_n_gpu_layers (sautera si aucune valeur n'est disponible).",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    config_path = Path(args.config)
    if not config_path.exists():
        parser.error(f"config introuvable: {config_path}")

    base_settings = Settings()
    print("[auto-tune/full] Mesure de la latence initiale ...")
    baseline = await measure_latency(base_settings, prompt=args.prompt, samples=args.samples)
    print(_format_trial("  Latence initiale", baseline))

    plan = [spec for spec in DEFAULT_PLAN if spec["param"] not in set(args.skip or [])]
    if args.include_gpu_layers and "llm_n_gpu_layers" not in (spec["param"] for spec in plan):
        plan.append(
            {"param": "llm_n_gpu_layers", "kind": "int", "start": 20, "stop": 0, "step": 5}
        )

    if not plan:
        print("[auto-tune/full] Aucun paramètre à optimiser (plan vide).")
        return 0

    try:
        summaries = await _execute_plan(plan, prompt=args.prompt, samples=args.samples, config_path=config_path)
    except ValueError as exc:
        print(f"[auto-tune/full] Plan interrompu: {exc}")
        return 1
    except FileNotFoundError as exc:
        print(f"[auto-tune/full] {exc}")
        return 1

    # Mesure finale
    final_settings = Settings()
    print("\n[auto-tune/full] Mesure de la latence finale ...")
    final = await measure_latency(final_settings, prompt=args.prompt, samples=args.samples)
    print(_format_trial("  Latence finale", final))

    gain = baseline.avg_latency_ms - final.avg_latency_ms
    gain_pct = (gain / baseline.avg_latency_ms * 100.0) if baseline.avg_latency_ms else 0.0

    print("\nSynthèse :")
    for step in summaries:
        best = step.summary.best
        print(
            f"- {step.summary.param}: meilleur={best.value} "
            f"(avg {best.avg_latency_ms:.2f} ms)"
        )
    print(
        f"\nGain estimé: {gain:+.2f} ms ({gain_pct:+.1f} %) entre la configuration initiale et finale "
        f"(sur {args.samples} sample(s) par mesure)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
