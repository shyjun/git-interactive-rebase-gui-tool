import os
import sys


def get_theme_colors(theme_name):
    """Return the diff-highlighter color dict for the given theme name (\"dark\" or \"light\")."""
    if theme_name == "dark":
        return {
            "added": "#4ec9b0",   # Soft teal/green
            "removed": "#f48771", # Soft coral/red
            "header": "#569cd6",  # VS Code blue
            "bg": "#1e1e1e",      # Main background
            "fg": "#cccccc",      # Standard text
            "accent": "#007acc",  # VS Code accent blue
            "separator": "#CCCCCC" # Neutral Slate Gray
        }
    # light theme
    return {
        "added": "#228b22",  # Darker green for light bg
        "removed": "#b22222", # Darker red for light bg
        "header": "#00008b", # Darker blue for light bg
        "bg": "#f5f5f7",
        "fg": "#333333",
        "accent": "#007aff",
        "separator": "#CCCCCC" # Neutral Slate Gray
    }


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