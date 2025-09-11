# IVY Desktop (Tauri)

Application Windows (FR) avec STT Whisper.cpp, TTS Coqui, envoi texte → serveur et vérification de mises à jour.

Prérequis
- Rust + Tauri CLI (`npm i -g @tauri-apps/cli` ou via `desktop/package.json`).
- Whisper.cpp binaire Windows (ex: `whisper.exe`) et modèle `ggml-large-v3.bin`.
- Coqui TTS (CLI `tts`) et voix FR (ex: `tts_models/fr/css10/vits`).
- Poppler/Tesseract non requis pour Desktop (déjà côté serveur RAG).

Chemins recommandés (Windows)
- Whisper.exe: `C:\IVY\tools\whisper\whisper.exe`
- Modèle large: `C:\IVY\models\whisper\ggml-large-v3.bin`
- Modèle small: `C:\IVY\models\whisper\ggml-small.bin`

Paramètres (réglables dans l’app)
- Serveur: `http://127.0.0.1:8000`.
- STT: chemin `whisper.exe`, chemin modèle, VAD ON/OFF, seuil VAD, durée max (s).
  - Préréglage modèle: `large-v3` (qualité) ou `small` (rapide). Bouton “Appliquer chemin recommandé”.
- TTS: commande `tts`, voix FR, débit (rate/speed).

Mises à jour
- L’app récupère `/updates/desktop/manifest.json` depuis le serveur et propose le téléchargement du MSI si une version plus récente est trouvée. Le SHA256 est vérifié côté client.

Scripts de test
- `scripts/test_stt_tts.ps1`: simule une transcription sur un WAV et lit une courte phrase via TTS.

Construction
- Dev: `cd desktop && npm i && npm run dev`
- Build MSI: `npm run build`
