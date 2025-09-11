from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    try:
        from app.core.config import get_settings
    except Exception as exc:
        print(f"ERROR: cannot import settings: {exc}")
        return 1

    s = get_settings()
    ret = 0

    # JWT secret
    try:
        if getattr(s, "jwt_secret", "CHANGE_ME") == "CHANGE_ME":
            print("WARNING: JWT_SECRET uses default value. Set JWT_SECRET or config.json.")
    except Exception:
        pass

    # LLM model
    model_path = os.environ.get("LLM_MODEL_PATH")
    if not model_path:
        print("INFO: LLM_MODEL_PATH not set. LLM endpoints may return errors until configured.")
    else:
        p = Path(model_path)
        if not p.exists():
            print(f"WARNING: LLM model file not found: {p}")

    # Directories for RAG
    try:
        for key in ("rag_inbox_dir", "rag_knowledge_dir", "rag_index_dir"):
            d = Path(getattr(s, key))
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                print(f"INFO: created directory: {d}")
    except Exception as exc:
        print(f"WARNING: could not ensure RAG dirs: {exc}")

    # DB path parent
    try:
        dbp = Path(s.db_path)
        dbp.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"WARNING: could not ensure DB dir: {exc}")

    # Plugins dir
    plug = Path("plugins")
    if not plug.exists():
        try:
            plug.mkdir(parents=True, exist_ok=True)
            print(f"INFO: created plugins directory: {plug}")
        except Exception as exc:
            print(f"WARNING: could not create plugins dir: {exc}")

    return ret


if __name__ == "__main__":
    sys.exit(main())

