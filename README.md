# IVY

Assistant local avec mémoire conversationnelle, recherche DuckDuckGo et génération LLM (llama.cpp ou TensorRT-LLM).

## Installation rapide
```
py -m pip install -r scripts/requirements-dev-no-llama.txt`r`npy -m pip install llama-cpp-python`r`npython -m app.cli serve
```

## Documentation
• docs/USER_GUIDE.md — navigation de l’UI, configuration et sauvegardes.
• docs/PLUGINS.md — architecture mémoire (conversations/Q-R), intégrations (DuckDuckGo, Ollama, Jeedom) et API associées.

## Tests essentiels
```
py -m pytest tests/test_chat_api.py tests/test_history_api.py tests/test_health.py -q
```

## Ressources utiles
• Configuration exemple : config.json.example (prompts chat, embeddings, DuckDuckGo, TensorRT-LLM, Jeedom).
• Script d’assistance Windows : scripts/start-menu.bat.

## Licence
Voir le fichier LICENSE.


### CUDA (optionnel)
Pour une construction GPU de llama-cpp-python (CUDA 12.6) :
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
Ajustez DCMAKE_CUDA_ARCHITECTURES selon votre carte.

