# Guide Utilisateur

Connexion et sécurité
- Connexion admin via l’UI (formulaire en haut). Le serveur place un cookie JWT HttpOnly et renvoie un `csrf_token`. Toutes les requêtes POST/PUT/DELETE doivent inclure `X‑CSRF‑Token`.
- Reset admin (mot de passe temporaire): créer le fichier `C:\IVY\reset_admin.flag` puis redémarrer (le mot de passe s’affiche en console et est journalisé).

Pages UI (menu)
- Plugins: liste, activer/désactiver/démarrer/arrêter/recharger, upload ZIP. Les plugins réseau doivent être autorisés par `allowlist_domains`.
- Historique: lancer la relecture des 30 derniers événements (si implémenté côté API).
- LLM: console pour inférence texte et streaming (WS). Les tokens s’affichent en temps réel.
- Système: vignettes `/health` (DB, FAISS, GPU, version, nombre de plugins).
- Sessions: sessions actives (webui/desktop), bouton “Terminer”.
- Configuration: host/port (lecture), allowlist, RAG (dossiers), LLM (modèle), logs, rate‑limit, reset admin.
- Sauvegardes: export ZIP (via job), téléchargement direct, import ZIP (dry‑run puis application).

PWA mobile
- L’UI est installable sur mobile (manifest + service worker). Page “Commande vocale”: dictée Web Speech (si disponible) → envoi du texte au serveur.

Note PWA (installation & cache)
- Installation (Android/Chrome): ouvrir l’UI puis “Ajouter à l’écran d’accueil”. iOS/Safari: partager → “Sur l’écran d’accueil”.
- Mises à jour: le Service Worker (sw.js) met en cache le shell. En cas de mise à jour UI:
  - Forcer l’actualisation: Ctrl/Cmd+F5 (desktop) ou tirer pour rafraîchir (mobile) 2×.
  - Ou supprimer l’ancienne PWA (icône) puis réinstaller pour repartir avec un cache propre.
  - Option avancée (desktop): onglet Application → Service Workers → “Unregister” puis recharger.

Desktop Windows
- App Tauri (voir `desktop/`):
  - STT: Whisper.cpp (large‑v3 par défaut, VAD activable, 90s max).
  - TTS: Coqui voix FR (débit réglable).
  - Mises à jour: l’app lit `/updates/desktop/manifest.json` et propose l’installation du MSI (SHA256 vérifié).

RAG local
- Dossiers surveillés: `rag_inbox_dir`, `rag_knowledge_dir` (config). L’index FAISS persiste dans `rag_index_dir`.
- OCR FR activable: `rag_enable_ocr=true`, langue multi: `rag_ocr_lang=fra+eng`.
- Reindexation: `POST /rag/reindex` (UI bouton). Requêtes: `POST /rag/query`.

Pare‑feu sortant
- Autorisez explicitement les domaines dans `allowlist_domains` (ex: `open-meteo.com`, `duckduckgo.com`). Les sous‑domaines sont pris en charge.

Captures d’écran
- Ajoutez vos captures dans `docs/img/` et référencez‑les dans `README.md`.
