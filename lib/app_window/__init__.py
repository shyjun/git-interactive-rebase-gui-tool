from lib.app_window.helpers import (
    _diff_search_matches,
    get_theme_stylesheet,
)

def __getattr__(name):
    if name == "GitInteractiveRebaseApp":
        from lib.app_window.main import GitInteractiveRebaseApp
        return GitInteractiveRebaseApp
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = ["GitInteractiveRebaseApp", "get_theme_stylesheet", "_diff_search_matches"]

