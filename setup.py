import subprocess
import json
from datetime import datetime
from pathlib import Path
from setuptools import setup


def get_git_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    except Exception:
        return "unknown"


data = {
    "sha": get_git_sha(),
    "date": datetime.utcnow().strftime("%Y-%m-%d"),
    "repo": "https://github.com/shyjun/git-interactive-rebase-gui-tool",
}

# ensure assets dir exists
assets_dir = Path("assets")
assets_dir.mkdir(exist_ok=True)

# write inside assets
(assets_dir / "app_version.json").write_text(json.dumps(data, indent=2))

setup()