# TensorRT-LLM : preparation et execution

Ce guide resume la procedure issue de la documentation officielle [TensorRT-LLM - Build From Source (Linux)](https://nvidia.github.io/TensorRT-LLM/installation/build-from-source-linux.html) pour compiler TensorRT-LLM, convertir un modele et exposer une API REST compatible avec IVY.

Avertissement : toutes les commandes ci-dessous sont a executer sur un hote Linux equipe d'un GPU NVIDIA (et non dans l'environnement virtuel Python d'IVY). IVY se contente d'appeler l'API HTTP du serveur TensorRT-LLM.

## 1. Prerequis systeme

```bash
sudo apt-get update
sudo apt-get -y install build-essential cmake python3-dev python3-venv libssl-dev \
                        libffi-dev libopenmpi-dev git git-lfs
sudo git lfs install
```

Assurez-vous qu'un driver NVIDIA et CUDA 12.8 (ou version compatible avec votre GPU) sont installes.

## 2. Preparer l'environnement Python

```bash
python3 -m venv ~/trtllm-env
source ~/trtllm-env/bin/activate
pip3 install --upgrade pip setuptools wheel
pip3 install torch==2.7.1 torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cu128
pip3 install tensorrt_llm
```

## 3. Cloner TensorRT-LLM

```bash
mkdir -p ~/workspace && cd ~/workspace
git clone https://github.com/NVIDIA/TensorRT-LLM.git
cd TensorRT-LLM
git submodule update --init --recursive
git lfs pull
```

## 4. Compilation (CMake)

Adaptez les chemins `TENSORRT_ROOT` et `TRT_LIB_DIR` a votre installation TensorRT.

```bash
export TENSORRT_ROOT=/usr/lib/x86_64-linux-gnu
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DPython3_EXECUTABLE=$(which python3) \
  -DTENSORRT_ROOT=${TENSORRT_ROOT}
cmake --build build -j$(nproc)
cmake --install build --prefix build/install
```

A l'issue du `cmake --install`, les binaires (`trtllm-build`, `trtllm-launcher`, ...) sont disponibles dans `build/install/bin`.

## 5. Conversion d'un modele

La documentation NVIDIA fournit des scripts par famille de modeles. Exemple pour Llama 3.1 Instruct (chemins a adapter) :

```bash
# 5.1 Convertir le checkpoint HuggingFace vers un plan TensorRT-LLM
python3 examples/llama/convert_checkpoint.py \
  --model_dir /data/models/Meta-Llama-3.1-8B-Instruct \
  --output_dir ~/workspace/llama-3.1-8b-trtllm \
  --dtype float16

# 5.2 Generer le moteur TensorRT (plan) a partir du fichier de configuration
trtllm-build --config ~/workspace/llama-3.1-8b-trtllm/trtllm_config.json \
  --output_dir ~/workspace/engines/llama-3.1-8b
```

Reportez-vous aux pages "Model Guidance" du site TensorRT-LLM pour d'autres modeles (Mixtral, Phi, etc.) et les options `--quantization`, `--tp_size`, ...

## 6. Demarrer un serveur REST

Une fois l'engin TensorRT genere, vous pouvez exposer une API chat :

```bash
trtllm-launcher \
  --engine_dir ~/workspace/engines/llama-3.1-8b \
  --model meta/llama-3.1-8b-instruct \
  --chat \
  --rest_port 8000 \
  --rest_api /v1/chat/completions \
  --listen 0.0.0.0
```

- `--listen 0.0.0.0` autorise les connexions distantes (necessaire si IVY tourne sur une autre machine).
- Si vous souhaitez exiger une cle API, placez votre proxy ou passerelle HTTPS devant ce service puis transmettez la cle a IVY (`tensorrt_llm_api_key`).

## 7. Exemple de service systemd

```ini
# /etc/systemd/system/trtllm.service
[Unit]
Description=TensorRT-LLM REST server
After=network.target

[Service]
Type=simple
User=trtllm
WorkingDirectory=/home/trtllm/workspace/TensorRT-LLM
Environment="PATH=/home/trtllm/trtllm-env/bin:/usr/local/bin:/usr/bin"
ExecStart=/home/trtllm/trtllm-env/bin/trtllm-launcher \
  --engine_dir /home/trtllm/workspace/engines/llama-3.1-8b \
  --model meta/llama-3.1-8b-instruct --chat --rest_port 8000 --rest_api /v1/chat/completions --listen 0.0.0.0
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Activez ensuite le service :

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now trtllm.service
```

## 8. Scenario Docker / NIM

Pour eviter la compilation, NVIDIA publie des images Docker :

```bash
docker login nvcr.io
docker pull nvcr.io/nvidia/nim/tensorrt-llm:24.08
```

Lancement d'un conteneur exposant l'API chat :

```bash
docker run --gpus all --rm \
  -p 8000:8000 \
  -v /data/models:/models \
  -e TRTLLM_MODEL=meta/llama-3.1-8b-instruct \
  nvcr.io/nvidia/nim/tensorrt-llm:24.08
```

Commandes utiles :

```bash
# Start/Stop via Docker Compose
docker compose up -d
docker compose down

# Logs
docker logs -f <container_id>

# Mise a jour
docker pull nvcr.io/nvidia/nim/tensorrt-llm:24.08
```

Adaptez les variables exposees par l'image (`TRTLLM_MODEL`, `TRTLLM_ENGINE_DIR`, `NIM_MODEL_NAME`, etc.) ainsi que les volumes montes.

## 9. Configuration cote IVY

Dans `config.json` ou `.env` d'IVY, renseignez :

```json
{
  "tensorrt_llm_base_url": "http://trtllm-server:8000",
  "tensorrt_llm_chat_endpoint": "/v1/chat/completions",
  "tensorrt_llm_model": "meta/llama-3.1-8b-instruct",
  "tensorrt_llm_api_key": null
}
```

Puis redemarrez IVY (`python -m app.cli serve`). IVY utilisera desormais exclusivement TensorRT-LLM pour toutes les requetes LLM.
