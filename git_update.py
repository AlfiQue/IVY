#!/usr/bin/env python3
import json, subprocess as sp, sys

def run(cmd, check=True):
    print(f"$ {cmd}")
    return sp.run(cmd, shell=True, check=check)

def try_run(cmd):
    print(f"$ {cmd}")
    return sp.run(cmd, shell=True, check=False).returncode

def load_cfg():
    with open("git_settings.json", "r", encoding="utf-8") as f:
        return json.load(f)

def is_git_repo():
    return try_run("git rev-parse --is-inside-work-tree >NUL 2>&1") == 0

def main():
    if not is_git_repo():
        raise SystemExit("❌ Ce dossier n’est pas un dépôt Git. Lance d’abord `git_push.py` (qui initialise) ou fais `git init` + `git remote add origin <url>`.")

    cfg = load_cfg()
    branch = cfg["branch"]

    do_stash = "--stash" in sys.argv
    did_stash = False

    if do_stash:
        rc = try_run('git stash push -u -m "auto-stash before update"')
        did_stash = (rc == 0)

    run("git fetch --all --prune")
    run(f"git checkout {branch}")
    run(f"git pull --rebase origin {branch}")

    if did_stash:
        try_run("git stash pop")

if __name__ == "__main__":
    main()
