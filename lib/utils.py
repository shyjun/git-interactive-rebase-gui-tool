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

    The lookup is anchored to *this file's* location (lib/utils.py) so that
    the correct assets/ directory is always found regardless of sys.path
    ordering or whether both a pip-installed version and a source checkout are
    simultaneously present on sys.path.

    Layout for both source-checkout and pip-install:
        <root>/
            lib/         ← __file__ lives here
            assets/      ← always a sibling of lib/
    """
    # BUG-3 fix: use __file__ as an anchor, not sys.path scanning.
    # Both `pip install` (site-packages/lib/) and source checkout share the
    # same relative layout: lib/ and assets/ are siblings under the same root.
    try:
        lib_dir = os.path.dirname(os.path.abspath(__file__))  # .../lib
        root_dir = os.path.dirname(lib_dir)                   # .../
        candidate = os.path.join(root_dir, "assets")
        if os.path.isdir(candidate):
            return candidate
    except Exception:
        pass

    raise RuntimeError(
        "Critical Error: 'assets' folder not found.\n"
        "Ensure installation is correct or run from repository root."
    )
