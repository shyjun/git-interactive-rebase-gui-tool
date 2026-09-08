# Re-export all symbols so that ``from lib.dialogs import X`` continues to work unchanged.

from .diff_dialogs import (
    BranchDiffDialog,
    DiffViewerDialog,
    FileWiseViewDialog,
    SingleCommitViewDialog,
    StagedDiffDialog,
    UnstagedDiffDialog,
    ViewCommitDialog,
)

from .commit_action_dialogs import (
    AggressiveRemoveConfirmationDialog,
    CherryPickDialog,
    ConfirmDropFileDialog,
    ConfirmMoveFileDialog,
    ConfirmRemoveFileOnwardsDialog,
    DropDialog,
    DropFileFromCommitDialog,
    MultiSquashDialog,
    NewCommitMessageDialog,
    ProgressDialog,
    RefineFileSelectDialog,
    RephraseDialog,
    RevertCommitDialog,
    SplitCommitDialog,
    SquashDialog,
)

from .history_branch_dialogs import (
    ApplyPatchDialog,
    BlameFileDialog,
    BrowseBranchDialog,
    BrowseCommitLogDialog,
    BrowseFileLogDialog,
    DiffFileAtRefDialog,
    MergeBaseDialog,
    MergeBaseResultDialog,
    OpenFileAtRefDialog,
    StashNoticeDialog,
    TagCommitDialog,
)

from .hunk_file_dialogs import (
    BlameDialog,
    CommitSelectivelyDialog,
    DropHunkDialog,
    EditHunkDialog,
    ElidedLabel,
    HunkWidget,
    RefineChangesDialog,
    SelectiveHunkDialog,
    UnstagedChangesDialog,
    open_blame_window,
)

from .unstaged_dialogs import (
    StageFilesDialog,
    StagedChangesDialog,
)

from .configure_dialogs import (
    ConfigureDiffToolDialog,
)
