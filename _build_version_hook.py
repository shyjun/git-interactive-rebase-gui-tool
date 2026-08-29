"""
BUG-14 fix: SHA-baking build hook for setuptools (PEP 517).

setuptools calls any module listed under [tool.setuptools.build-hook] in
pyproject.toml, but the simplest reliable mechanism for both `pip install`
and `python setup.py install` is to keep the baking in setup.py *and* also
run it as part of the sdist/wheel build via a setuptools command class hook.

This module is imported at build time and patches the `build_py` and
`egg_info` commands so that app_version.json is always freshly written before
files are copied into the build tree or the egg-info directory.  It is also
called unconditionally at the bottom of setup.py for older pip/setuptools
versions.

Usage:  referenced from setup.py (see bottom of that file).
"""
import subprocess
import json
from datetime import datetime, timezone
from pathlib import Path

from setuptools.command.build_py import build_py as _build_py
from setuptools.command.egg_info import egg_info as _egg_info


def _get_git_sha() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


def _write_version_file() -> None:
    """Write assets/app_version.json with the current HEAD SHA."""
    data = {
        "sha": _get_git_sha(),
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "repo": "https://github.com/shyjun/git-interactive-rebase-gui-tool",
    }
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)
    # Always write UTF-8 so the file is byte-identical regardless of locale.
    (assets_dir / "app_version.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


class BuildPyWithVersion(_build_py):
    """build_py subclass that bakes the SHA before copying package files."""

    def run(self):
        _write_version_file()
        super().run()


class EggInfoWithVersion(_egg_info):
    """egg_info subclass that bakes the SHA before generating egg-info."""

    def run(self):
        _write_version_file()
        super().run()
