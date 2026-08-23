from PySide6.QtWidgets import QMainWindow

from lib.app_window.init_mixin import InitMixin
from lib.app_window.ui_mixin import UIMixin
from lib.app_window.appearance_mixin import AppearanceMixin
from lib.app_window.toolbar_mixin import ToolbarMixin
from lib.app_window.diff_mixin import DiffMixin
from lib.app_window.undo_mixin import UndoMixin
from lib.app_window.update_mixin import UpdateMixin
from lib.app_window.reset_mixin import ResetMixin
from lib.app_window.cherry_pick_mixin import CherryPickMixin
from lib.app_window.browse_mixin import BrowseMixin
from lib.app_window.commit_ops_mixin import CommitOpsMixin
from lib.app_window.squash_mixin import SquashMixin
from lib.app_window.split_mixin import SplitMixin
from lib.app_window.rebase_mixin import RebaseMixin
from lib.app_window.stash_mixin import StashMixin
from lib.app_window.rescan_mixin import RescanMixin
from lib.app_window.menus_mixin import MenusMixin


class GitInteractiveRebaseApp(
    InitMixin,
    UIMixin,
    AppearanceMixin,
    ToolbarMixin,
    DiffMixin,
    UndoMixin,
    UpdateMixin,
    ResetMixin,
    CherryPickMixin,
    BrowseMixin,
    CommitOpsMixin,
    SquashMixin,
    SplitMixin,
    RebaseMixin,
    StashMixin,
    RescanMixin,
    MenusMixin,
    QMainWindow,
):
    pass
