# Re-export all symbols so that ``from lib.dialogs import X`` continues to work unchanged.

from .diff_dialogs import (
    DiffViewerDialog,
    ViewCommitDialog,
    BranchDiffDialog,
    SingleCommitViewDialog,
    UnstagedDiffDialog,
    FileWiseViewDialog,
)

from .commit_action_dialogs import (
    SplitCommitDialog,
    DropFileFromCommitDialog,
    RefineFileSelectDialog,
    DropDialog,
    ConfirmDropFileDialog,
    ConfirmMoveFileDialog,
    ConfirmRemoveFileOnwardsDialog,
    AggressiveRemoveConfirmationDialog,
    RephraseDialog,
    NewCommitMessageDialog,
    CherryPickDialog,
    RevertCommitDialog,
    SquashDialog,
    MultiSquashDialog,
    ProgressDialog,
)

from .history_branch_dialogs import (
    StashNoticeDialog,
    BrowseBranchDialog,
    BrowseCommitLogDialog,
    BrowseFileLogDialog,
    ApplyPatchDialog,
    TagCommitDialog,
    MergeBaseDialog,
    MergeBaseResultDialog,
    OpenFileAtRefDialog,
    DiffFileAtRefDialog,
)

from .hunk_file_dialogs import (
    open_blame_window,
    BlameDialog,
    ElidedLabel,
    HunkWidget,
    EditHunkDialog,
    DropHunkDialog,
    SelectiveHunkDialog,
    RefineChangesDialog,
    CommitSelectivelyDialog,
    UnstagedChangesDialog,
)

from .configure_dialogs import (
    ConfigureDiffToolDialog,
)
