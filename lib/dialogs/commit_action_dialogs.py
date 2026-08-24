
# Re-export shim — all classes moved to dedicated modules.
# Existing ``from lib.dialogs.commit_action_dialogs import X`` continues to work.

from .diff_viewer_dialog import DiffViewerDialog
from .split_drop_dialogs import (
    SplitCommitDialog,
    DropFileFromCommitDialog,
    ConfirmDropFileDialog,
    ConfirmMoveFileDialog,
    ConfirmRemoveFileOnwardsDialog,
    AggressiveRemoveConfirmationDialog,
    RefineFileSelectDialog,
)
from .confirmation_dialogs import (
    DropDialog,
    RephraseDialog,
    CherryPickDialog,
    RevertCommitDialog,
    SquashDialog,
    MultiSquashDialog,
    ProgressDialog,
)
from .commit_message_dialogs import (
    NewCommitMessageDialog,
)

__all__ = [
    "DiffViewerDialog",
    "SplitCommitDialog",
    "DropFileFromCommitDialog",
    "ConfirmDropFileDialog",
    "ConfirmMoveFileDialog",
    "ConfirmRemoveFileOnwardsDialog",
    "AggressiveRemoveConfirmationDialog",
    "RefineFileSelectDialog",
    "DropDialog",
    "RephraseDialog",
    "CherryPickDialog",
    "RevertCommitDialog",
    "SquashDialog",
    "MultiSquashDialog",
    "ProgressDialog",
    "NewCommitMessageDialog",
]
