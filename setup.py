"""
BUG-14 fix: SHA baking is done inside setup.py itself via setuptools cmdclass
hooks. The logic intentionally lives here (not in a separate module file) so
that pip's isolated PEP-517 build environment can always find it — external
module imports at setup.py level are unreliable in isolated builds.
"""
import subprocess
import json
from datetime import datetime, timezone
from pathlib import Path
from setuptools import setup, find_packages
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


# Write the version file immediately so that a bare `python setup.py install`
# (legacy mode, no PEP 517) still produces a correct file.
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
    packages=find_packages(),
    py_modules=["git_interactive_rebase"],
    package_data={"assets": ["*"]},
    entry_points={
        "console_scripts": [
            "git_interactive_rebase=git_interactive_rebase:main",
        ],
    },
    # Hooks ensure the SHA is baked at the correct moment during both sdist
    # and wheel builds under PEP 517.
    cmdclass={
        "build_py": BuildPyWithVersion,
        "egg_info": EggInfoWithVersion,
    },
)
