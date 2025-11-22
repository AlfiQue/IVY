"""Install audio resources required by the IVY voice client."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

from desktop.voice_client.config.paths import models_dir


ASR_SNAPSHOTS = {
    "faster-whisper-large-v3": {
        "repo_id": "Systran/faster-whisper-large-v3",
        "allow_patterns": ["*.bin", "*.json", "*.model", "*.txt"],
    },
    "faster-whisper-medium": {
        "repo_id": "Systran/faster-whisper-medium",
        "allow_patterns": ["*.bin", "*.json", "*.model", "*.txt"],
    },
    "faster-whisper-small": {
        "repo_id": "Systran/faster-whisper-small",
        "allow_patterns": ["*.bin", "*.json", "*.model", "*.txt"],
    },
    "faster-whisper-tiny": {
        "repo_id": "Systran/faster-whisper-tiny",
        "allow_patterns": ["*.bin", "*.json", "*.model", "*.txt"],
    },
}

TTS_PRESETS = {
    "fr_FR-mls-medium": {
        "repo_id": "rhasspy/piper-voices",
        "files": [
            "fr/fr_FR/mls/medium/fr_FR-mls-medium.onnx",
            "fr/fr_FR/mls/medium/fr_FR-mls-medium.onnx.json",
            "fr/LICENSE.md",
        ],
    },
    "fr_FR-jessica-high": {
        "repo_id": "rhasspy/piper-voices",
        "files": [
            "fr/fr_FR/jessica/high/fr_FR-jessica-high.onnx",
            "fr/fr_FR/jessica/high/fr_FR-jessica-high.onnx.json",
            "fr/LICENSE.md",
        ],
    },
    "fr_FR-gilles-low": {
        "repo_id": "rhasspy/piper-voices",
        "files": [
            "fr/fr_FR/gilles/low/fr_FR-gilles-low.onnx",
            "fr/fr_FR/gilles/low/fr_FR-gilles-low.onnx.json",
            "fr/LICENSE.md",
        ],
    },
    "fr_FR-siwis-medium": {
        "repo_id": "rhasspy/piper-voices",
        "files": [
            "fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx",
            "fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json",
            "fr/LICENSE.md",
        ],
    },
}


def download_snapshot(name: str, repo_id: str, destination: Path, *, allow_patterns: list[str]) -> None:
    """Download a Hugging Face snapshot into destination."""
    destination.mkdir(parents=True, exist_ok=True)
    print(f"[DL] {name} from {repo_id} -> {destination}")
    existing = {path.relative_to(destination) for path in destination.rglob("*")}
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(destination),
        allow_patterns=allow_patterns,
        local_dir_use_symlinks=False,
    )
    downloaded = [
        path
        for path in destination.rglob("*")
        if path.is_file() and path.relative_to(destination) not in existing
    ]
    if not downloaded:
        # Nothing new fetched; ensure required files already exist
        has_assets = any(path.suffix in {".onnx", ".json"} for path in destination.rglob("*"))
        if not has_assets:
            patterns = ", ".join(allow_patterns)
            raise RuntimeError(f"Aucune ressource telechargee pour {name} (patrons: {patterns}).")
    print(f"[OK] {name} installed.")


def install_asr(target: Path, models: list[str] | None = None) -> None:
    selected = models or ["faster-whisper-medium"]
    for name in selected:
        info = ASR_SNAPSHOTS.get(name)
        if info is None:
            available = ", ".join(sorted(ASR_SNAPSHOTS))
            raise ValueError(f"Modele ASR inconnu: {name}. Disponibles: {available}")
        destination = target / name
        if destination.exists():
            print(f"[SKIP] Modele ASR {name} deja present ({destination}).")
            continue
        download_snapshot(
            name=name,
            repo_id=info["repo_id"],
            destination=destination,
            allow_patterns=info["allow_patterns"],
        )


def install_tts(target: Path, voices: list[str]) -> None:
    for voice in voices:
        preset = TTS_PRESETS.get(voice)
        if preset is None:
            available = ", ".join(sorted(TTS_PRESETS))
            raise ValueError(f"Voix '{voice}' inconnue. Voix disponibles : {available}")
        destination = target / voice
        if destination.exists():
            print(f"[SKIP] Voix {voice} deja presente ({destination}).")
            continue
        patterns = preset["files"]
        download_snapshot(
            name=voice,
            repo_id=preset["repo_id"],
            destination=destination,
            allow_patterns=patterns,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Install IVY Voice ASR and TTS models.")
    parser.add_argument("--asr", action="store_true", help="Install ASR models only.")
    parser.add_argument("--tts", action="store_true", help="Install TTS models only.")
    parser.add_argument("--all", action="store_true", help="Install ASR et TTS (defaut).")
    parser.add_argument(
        "--voice",
        action="append",
        dest="voices",
        help="Voix Piper a installer (peut etre indiquee plusieurs fois). Defaut : fr_FR-mls-medium.",
    )
    parser.add_argument(
        "--asr-model",
        action="append",
        dest="asr_models",
        choices=sorted(ASR_SNAPSHOTS),
        help="Modele ASR a installer (peut etre indique plusieurs fois). Defaut : faster-whisper-medium.",
    )
    args = parser.parse_args()

    target = models_dir()
    voices = args.voices or ["fr_FR-mls-medium", "fr_FR-jessica-high"]
    asr_models = args.asr_models

    if args.all or (not args.asr and not args.tts):
        install_asr(target / "asr", asr_models)
        install_tts(target / "tts", voices)
    else:
        if args.asr:
            install_asr(target / "asr", asr_models)
        if args.tts:
            install_tts(target / "tts", voices)
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "ddgs"], check=True)
        print("[OK] Package ddgs installed.")
    except subprocess.CalledProcessError as exc:
        print(f"[WARN] Impossible d'installer ddgs automatiquement ({exc}). Installez-le manuellement si besoin.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(1)




