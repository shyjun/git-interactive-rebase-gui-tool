"""Minimal setup.py as fallback for pip versions that don't fully support
PEP 621 ([project] table in pyproject.toml).  pyproject.toml remains the
canonical source of metadata for modern pip / build tools."""
import subprocess
import json
from datetime import datetime, timezone
from pathlib import Path
from setuptools import setup


def get_git_sha():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def _write_version_file():
    data = {
        "sha": get_git_sha(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "repo": "https://github.com/shyjun/git-interactive-rebase-gui-tool",
    }
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)
    (assets_dir / "app_version.json").write_text(json.dumps(data, indent=2))


_write_version_file()

setup(
    name="git-interactive-rebase-gui-tool",
    version="0.1.0",
    description="A Python-based Git Interactive Rebase GUI tool",
    long_description=Path("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="shyjun",
    license="MIT",
    python_requires=">=3.10",
    install_requires=["PySide6"],
    packages=["lib", "assets"],
    py_modules=["git_interactive_rebase"],
    package_data={"assets": ["*"]},
    entry_points={
        "console_scripts": [
            "git_interactive_rebase=git_interactive_rebase:main",
        ],
    },
)
