"""Installer PyTorch CUDA (cu121) avec journalisation détaillée."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PACKAGES = ["torch", "torchvision", "torchaudio"]
CU121_INDEX = "https://download.pytorch.org/whl/cu121"
PYPI_INDEX = "https://pypi.org/simple"


def run(cmd: list[str], *, check: bool = True) -> int:
    """Run a subprocess and stream its output."""
    print(f"[CUDA] $ {' '.join(cmd)}")
    proc = subprocess.run(cmd)
    if check and proc.returncode != 0:
        raise RuntimeError(f"Commande echouee (code {proc.returncode}) : {' '.join(cmd)}")
    return proc.returncode


def main() -> int:
    python_path = Path(sys.executable).resolve()
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"[CUDA] Python detecte : {python_path}")
    print(f"[CUDA] Version interpreter : {version}")

    print(f"[CUDA] Desinstallation des paquets existants : {' '.join(PACKAGES)}")
    run([sys.executable, "-m", "pip", "uninstall", "-y", *PACKAGES], check=False)

    print("[CUDA] Installation des roues cu121...")
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--index-url",
            CU121_INDEX,
            "--extra-index-url",
            PYPI_INDEX,
            *PACKAGES,
        ]
    )

    try:
        import torch
    except Exception as exc:  # pragma: no cover
        print("[CUDA] torch est introuvable apres installation :", exc)
        return 1

    build_cuda = getattr(torch.version, "cuda", "NA")
    cuda_ok = torch.cuda.is_available()
    print(f"[CUDA] torch={torch.__version__}  build_cuda={build_cuda}  cuda_available={cuda_ok}")

    if build_cuda in (None, "", "NA"):
        print(
            "[CUDA] Aucune roue CUDA n'est disponible pour cette combinaison Python/OS."
            " PyTorch CPU a ete installee par defaut."
        )
    elif not cuda_ok:
        print(
            "[CUDA] PyTorch a ete installe avec CUDA "
            f"{build_cuda} mais torch.cuda.is_available() est False."
            " Verifiez les drivers GPU et la presence de CUDA runtime compatible."
        )
    else:
        print("[CUDA] GPU detecte, PyTorch CUDA pret a l'emploi.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
