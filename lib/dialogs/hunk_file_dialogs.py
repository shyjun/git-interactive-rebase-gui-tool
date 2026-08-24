"""Re-export shim for backward compatibility.

The actual implementations have been split into:
- blame_dialog.py
- unstaged_dialogs.py
- hunk_widgets.py
- refine_changes_dialog.py
"""
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

from lib.dialogs.blame_dialog import _find_main_window, open_blame_window, BlameDialog
from lib.dialogs.unstaged_dialogs import UnstagedChangesDialog, CommitSelectivelyDialog
from lib.dialogs.hunk_widgets import (
    EditHunkDialog, DropHunkDialog, ElidedLabel, HunkWidget, SelectiveHunkDialog,
)
from lib.dialogs.refine_changes_dialog import RefineChangesDialog

__all__ = [
    "_find_main_window", "open_blame_window", "BlameDialog",
    "UnstagedChangesDialog", "CommitSelectivelyDialog",
    "EditHunkDialog", "DropHunkDialog", "ElidedLabel", "HunkWidget", "SelectiveHunkDialog",
    "RefineChangesDialog",
]
