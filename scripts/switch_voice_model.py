"""Utility to switch IVY voice client ASR / GPU settings."""

from __future__ import annotations

import argparse

from desktop.voice_client.config.paths import config_dir
from desktop.voice_client.config.store import load_settings, save_settings

ASR_MODELS = [
    "faster-whisper-large-v3",
    "faster-whisper-medium",
    "faster-whisper-small",
    "faster-whisper-tiny",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure the IVY voice client audio models.")
    parser.add_argument(
        "--asr",
        choices=ASR_MODELS,
        help="Set the ASR model (download with scripts/install_voice_resources.py --asr if needed).",
    )
    parser.add_argument(
        "--gpu",
        choices=["on", "off"],
        help="Enable or disable GPU acceleration for ASR.",
    )
    parser.add_argument(
        "--vad",
        choices=["on", "off"],
        help="Enable or disable VAD (silence filtering).",
    )
    parser.add_argument(
        "--vad-aggr",
        type=int,
        choices=[0, 1, 2, 3],
        help="Set VAD aggressiveness (0=sensible, 3=strict).",
    )
    parser.add_argument(
        "--tts-voice",
        help="Set the Piper TTS voice (path under models/tts, e.g. fr-FR-piper-high/fr/fr_FR/jessica/high).",
    )
    parser.add_argument(
        "--tts-speed",
        type=float,
        help="Set the Piper length_scale (0.5 = plus rapide, 1.0 = normal).",
    )
    parser.add_argument(
        "--tts-pitch",
        type=float,
        help="Set the Piper pitch/expression (noise_scale).",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show current configuration without changing anything.",
    )
    args = parser.parse_args()

    settings = load_settings()
    changed = False
    messages: list[str] = []

    if args.show:
        print_status(settings)
        return

    if args.asr:
        if settings.audio.asr_model != args.asr:
            settings.audio.asr_model = args.asr
            changed = True
            messages.append(f"ASR model set to {args.asr}")
        else:
            messages.append(f"ASR model already set to {args.asr}")

    if args.gpu:
        enable = args.gpu == "on"
        if settings.audio.enable_gpu != enable:
            settings.audio.enable_gpu = enable
            changed = True
            messages.append(f"GPU acceleration {'enabled' if enable else 'disabled'}")
        else:
            messages.append(f"GPU acceleration already {'enabled' if enable else 'disabled'}")

    if args.vad:
        eco = args.vad == "on"
        if settings.audio.eco_mode != eco:
            settings.audio.eco_mode = eco
            changed = True
            messages.append(f"VAD (silence filtering) {'enabled' if eco else 'disabled'}")
        else:
            messages.append(f"VAD already {'enabled' if eco else 'disabled'}")
    if args.vad_aggr is not None:
        if settings.audio.vad_aggressiveness != args.vad_aggr:
            settings.audio.vad_aggressiveness = args.vad_aggr
            changed = True
            messages.append(f"VAD aggressiveness set to {args.vad_aggr}")
        else:
            messages.append(f"VAD aggressiveness already set to {args.vad_aggr}")
    if args.tts_voice:
        if settings.audio.tts_voice != args.tts_voice:
            settings.audio.tts_voice = args.tts_voice
            changed = True
            messages.append(f"TTS voice set to {args.tts_voice}")
        else:
            messages.append("TTS voice already set to desired value")
    if args.tts_speed is not None:
        value = round(float(args.tts_speed), 2)
        if settings.audio.tts_length_scale != value:
            settings.audio.tts_length_scale = value
            changed = True
            messages.append(f"TTS length_scale set to {value}")
        else:
            messages.append(f"TTS length_scale already {value}")
    if args.tts_pitch is not None:
        value = round(float(args.tts_pitch), 2)
        if settings.audio.tts_pitch != value:
            settings.audio.tts_pitch = value
            changed = True
            messages.append(f"TTS pitch set to {value}")
        else:
            messages.append(f"TTS pitch already {value}")

    if changed:
        save_settings(settings)
        messages.append("voice_settings.json updated.")
    if messages:
        print("\n".join(messages))
    else:
        print_status(settings)


def print_status(settings) -> None:
    print("Current IVY voice client configuration:")
    print(f"  ASR model : {settings.audio.asr_model}")
    print(f"  GPU       : {'enabled' if settings.audio.enable_gpu else 'disabled'}")
    print(f"  VAD       : {'enabled' if settings.audio.eco_mode else 'disabled'}")
    print(f"  VAD-aggr  : {settings.audio.vad_aggressiveness}")
    print(f"  TTS voice : {settings.audio.tts_voice}")
    print(f"  TTS speed : {settings.audio.tts_length_scale}")
    print(f"  TTS pitch : {settings.audio.tts_pitch}")
    settings_path = config_dir() / "voice_settings.json"
    print(f"  Settings  : {settings_path}")


if __name__ == "__main__":
    main()
