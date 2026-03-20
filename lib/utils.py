import os
import sys


def get_assets_path():
    """
    Resolve path to 'assets' directory.

    Priority:
    1. Installed via pip (site-packages)
    2. Running from source repo
    """

    # --- Case 1: pip install (site-packages/assets) ---
    for path in sys.path:
        candidate = os.path.join(path, "assets")
        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "app_icon.png")):
            return candidate

    # --- Case 2: running from source repo ---
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        candidate = os.path.join(base_dir, "assets")
        if os.path.isdir(candidate):
            return candidate
    except Exception:
        pass

    raise RuntimeError(
        "Critical Error: 'assets' folder not found.\n"
        "Ensure installation is correct or run from repository root."
    )