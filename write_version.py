#!/usr/bin/env python3
"""Generate assets/app_version.json with the current git SHA and date.
Run manually before building/publishing: python write_version.py"""
import subprocess
import json
from datetime import datetime, timezone
from pathlib import Path


def get_git_sha():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def main():
    data = {
        "sha": get_git_sha(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "repo": "https://github.com/shyjun/git-interactive-rebase-gui-tool",
    }
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)
    (assets_dir / "app_version.json").write_text(json.dumps(data, indent=2))
    print(f"Wrote assets/app_version.json: {data['sha'][:8]}")


if __name__ == "__main__":
    main()
