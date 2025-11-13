# Installation

## 1. Pre-requis
- Windows 11 (teste) ou Linux/macOS, Python 3.11, Git.
- Pour l'UI : Node.js 18+.
- Pour TensorRT-LLM : un serveur NVIDIA (TensorRT-LLM, Triton ou NIM) sur une machine GPU accessible.

## 2. Installation Python
```
py -m pip install -e .[dev]
```
Cette commande installe la pile API et les outils de developpement.

En environnement restreint (offline), utilisez :
```
py -m pip install -r scripts/requirements-dev-no-llama.txt
```

## 3. Lancement
```
python -m app.cli serve
```
L'application initialise la base `app/data/history.db` et expose l'UI sur http://127.0.0.1:8000/admin.

UI en mode dev :
```
cd webui
npm install
npm run dev   # http://127.0.0.1:5173 (VITE_API_URL=http://127.0.0.1:8000)
```

UI buildée :
```
npm run build
python -m app.cli ui --path webui/dist --port 5174
```

## 4. Configuration
- Copier `config.json.example` en `config.json` et ajuster :
  - `chat_system_prompt`, `embedding_model_name`, `duckduckgo_*`, `tensorrt_llm_*`, `jeedom_*`.
  - `allowlist_domains` pour le pare-feu sortant.
  - `reset_admin_flag` (fichier declenchant un mot de passe admin temporaire).
- Variables possibles via `.env` (chargees par `pydantic-settings`).

## 5. Tests rapides
```
py -m pytest tests/test_chat_api.py tests/test_history_api.py tests/test_health.py -q
```

## 6. OCR / RAG (optionnel)
- Installer Tesseract + Poppler (cf. `OCR.md`).
- Ajuster `rag_enable_ocr`, `rag_ocr_lang`, etc. si vous utilisez la partie RAG.

## 7. Conseils
- Pour repartir d'une base vide :
  ```bash
  python -m app.cli serve  # cree le schema
  python - <<'PY'
  import asyncio
  from app.core import chat_store
  asyncio.run(chat_store.clear_all())
  PY
  ```
- Les journaux sont ecrits dans `app/logs/*.jsonl` (audit, server, llm).
- Pensez a definir `jwt_secret` et a activer `cookie_secure=true` derriere HTTPS.

Bon demarrage !

## Installation TensorRT-LLM

Exemple de sequence (Ubuntu + CUDA 12.8) pour preparer un serveur TensorRT-LLM (voir `docs/TENSORRT_LLM.md` pour le guide detaille) :
```bash
pip3 install torch==2.7.1 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
sudo apt-get -y install libopenmpi-dev
pip3 install --upgrade pip setuptools
pip3 install tensorrt_llm
sudo apt-get update && sudo apt-get -y install git git-lfs
sudo git lfs install

git clone https://github.com/NVIDIA/TensorRT-LLM.git
cd TensorRT-LLM
git submodule update --init --recursive
git lfs pull
```

Puis compiler/installer TensorRT-LLM :
```bash
cd TensorRT-LLM
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
cmake --install build --prefix build/install
```

Adaptez les options CMake (`-DTORCH_PATH`, `-DTENSORRT_ROOT`, etc.) selon votre configuration GPU et la documentation NVIDIA.

## Installation TensorRT-LLM via Docker
```bash
docker login nvcr.io
docker pull nvcr.io/nvidia/nim/tensorrt-llm:24.08
```

Lancement en exposant l'API chat :
```bash
docker run --gpus all --rm \
  -p 8000:8000 \
  -v /data/models:/models \
  -e TRTLLM_MODEL=meta/llama-3.1-8b-instruct \
  nvcr.io/nvidia/nim/tensorrt-llm:24.08
```

Consultez `docs/TENSORRT_LLM.md` (section Docker & NIM) pour plus de details (volumes, cle API, service systemd).


### Option GPU (CUDA)
Pour compiler llama-cpp-python avec CUDA 12.6 sur Windows :
`
set "CUDA_PATH=C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.6"
set "CUDA_HOME=%CUDA_PATH%"
set "CUDACXX=%CUDA_PATH%/bin/nvcc.exe"
set "PATH=%CUDA_PATH%/bin;%PATH%"
set CMAKE_ARGS=
set "CMAKE_ARGS=-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=89 -DCUDAToolkit_ROOT=%CUDA_PATH%"
pip install --no-build-isolation --force-reinstall "llama-cpp-python==0.3.16"
set "CMAKE_ARGS=-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=89 -DCUDAToolkit_ROOT=%CUDA_PATH% -DCMAKE_CUDA_COMPILER:FILEPATH=%CUDACXX%"
`
Réglez DCMAKE_CUDA_ARCHITECTURES en fonction de votre GPU (par exemple 75 pour Turing, 89 pour Ada Lovelace).

