#!/usr/bin/env python3
import json, sys, subprocess as sp, datetime

def run(cmd, check=True):
    print(f"$ {cmd}")
    return sp.run(cmd, shell=True, check=check)

def try_run(cmd):
    # exécute sans lever d'exception, retourne le code
    print(f"$ {cmd}")
    return sp.run(cmd, shell=True, check=False).returncode

def load_cfg():
    with open("git_settings.json", "r", encoding="utf-8") as f:
        return json.load(f)

def is_git_repo():
    return try_run("git rev-parse --is-inside-work-tree >NUL 2>&1") == 0

def ensure_git_initialized(cfg):
    if is_git_repo():
        return
    print("⚠️  Aucun dépôt Git ici : initialisation…")
    run("git init")
    # identités locales (optionnel)
    if cfg.get("user_name"):
        run(f'git config user.name "{cfg["user_name"]}"')
    if cfg.get("user_email"):
        run(f'git config user.email "{cfg["user_email"]}"')
    # remote origin
    repo_url = cfg["repo_url"]
    # set-url marche même si 'origin' n'existe pas encore (git >=2.37). Sinon, on tente add puis set-url.
    rc = try_run(f'git remote set-url origin {repo_url}')
    if rc != 0:
        run(f'git remote add origin {repo_url}', check=False)
        try_run(f'git remote set-url origin {repo_url}')
    # branche
    branch = cfg["branch"]
    # crée la branche locale si besoin
    try_run(f"git checkout -B {branch}")
    # tente de récupérer l’amont si le dépôt distant existe déjà
    try_run("git fetch --all --prune")
    # essaie de suivre la branche distante si elle existe déjà
    try_run(f"git branch --set-upstream-to=origin/{branch} {branch}")

def main():
    cfg = load_cfg()
    ensure_git_initialized(cfg)

    branch = cfg["branch"]

    # Sync avant commit (si remote accessible)
    try_run("git fetch --all --prune")
    try_run(f"git checkout {branch}")
    try_run(f"git pull --rebase origin {branch}")

    # Stage + commit
    run("git add -A")
    msg = " ".join(sys.argv[1:]).strip()
    if not msg:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f'{cfg.get("default_message", "update")} ({ts})'
    # commit (peut ne rien committer)
    rc = try_run(f'git commit -m "{msg}"')
    if rc != 0:
        print("ℹ️  Rien à committer, on continue…")

    # Push (+ set upstream s’il n’existe pas encore)
    rc = try_run(f"git push origin {branch}")
    if rc != 0:
        # première fois : crée la branche distante et la suit
        run(f"git push -u origin {branch}")

if __name__ == "__main__":
    main()
