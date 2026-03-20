import os
import sys

def get_assets_path():
    """
    Robustly resolves the path to the 'assets' directory.
    Handles both running from the source repository and when installed as a package.
    """
    # Case 1: Running from the source repository (assets is one level up from lib/utils.py)
    # lib/utils.py -> lib/ -> root/assets
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        assets_path = os.path.join(base_dir, "assets")
        if os.path.exists(assets_path) and os.path.isdir(assets_path):
            return assets_path
    except Exception:
        pass

    # Case 2: Running from the root directory (assets is in the current directory)
    # This handles the case if __file__ is not behaving as expected
    try:
        cwd_assets = os.path.join(os.getcwd(), "assets")
        if os.path.exists(cwd_assets) and os.path.isdir(cwd_assets):
            return cwd_assets
    except Exception:
        pass

    # Case 3: Installed via pip (assets might be in a different location in sys.path)
    # This searches sys.path for a directory named 'assets' that contains 'app_icon.png'
    for path in sys.path:
        candidate = os.path.join(path, "assets")
        if os.path.exists(candidate) and os.path.isdir(candidate):
            # Verify it's OUR assets folder by checking for a known file
            if os.path.exists(os.path.join(candidate, "app_icon.png")):
                return candidate

    # Fallback: Check if it's in the same directory as the main script
    try:
        main_file = sys.modules['__main__'].__file__
        if main_file:
            candidate = os.path.join(os.path.dirname(os.path.abspath(main_file)), "assets")
            if os.path.exists(candidate) and os.path.isdir(candidate):
                return candidate
    except Exception:
        pass

    raise RuntimeError("Critical Error: 'assets' folder not found. Please ensure the project is correctly installed or run within the repository.")
