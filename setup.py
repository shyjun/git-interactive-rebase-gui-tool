"""
BUG-14 fix: setup.py now delegates SHA baking to setuptools command-class hooks
defined in _build_version_hook.py so that app_version.json is written reliably
under both PEP 517 (pip install) and legacy (python setup.py install) builds.

pyproject.toml remains the canonical source of metadata for modern tooling.
"""
from pathlib import Path
from setuptools import setup, find_packages
from _build_version_hook import (
    BuildPyWithVersion,
    EggInfoWithVersion,
    _write_version_file,
)

# Write the version file immediately so that a bare `python setup.py install`
# (legacy mode, no PEP 517) still produces a correct file even if the
# command-class hooks are never called by the caller.
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
    # BUG-14 fix: hook into build_py and egg_info so the SHA is baked at the
    # correct moment during both sdist and wheel builds under PEP 517.
    cmdclass={
        "build_py": BuildPyWithVersion,
        "egg_info": EggInfoWithVersion,
    },
)
