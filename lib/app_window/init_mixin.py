import os
import subprocess
import time

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QMainWindow, QMessageBox

from lib.git_helpers import (
    get_full_head_sha, get_head_sha, get_current_branch,
    has_uncommitted_changes, _is_git_install,
)
from lib.widgets import BrowseDimOverlay
from lib.app_window.helpers import highlight_button_temporarily


class InitMixin:
    """__init__, settings, and lifecycle methods for GitInteractiveRebaseApp."""

    def __init__(self, repo_path, commit_sha, app_start_time, base_branch=None, viewer_mode=False, browse_branch=None, parent=None, browse_limit=50, browse_file=None, browse_reflog=False, browse_stash=False, browse_file_ref=None, browse_tags=False, browse_tag=False, cli_mode=False, auto_detect_base=False):
        super().__init__(parent)
        mode = "viewer" if viewer_mode else "browse" if (browse_branch or browse_file or browse_reflog or browse_stash or browse_tags) else "main"
        print(f"[init] Creating window: mode={mode}, branch='{browse_branch}', file='{browse_file}', "
              f"reflog={browse_reflog}, stash={browse_stash}, tags={browse_tags}, limit={browse_limit}")
        self.repo_path = repo_path
        self.commit_sha = commit_sha
        self.app_start_time = app_start_time
        self.base_branch = base_branch  # set only when auto-detected; None when SHA provided manually
        self._auto_detect_base = auto_detect_base
        self.viewer_mode = viewer_mode
        self.browse_branch = browse_branch
        self.browse_file = browse_file
        self.browse_file_ref = browse_file_ref
        self.browse_reflog = browse_reflog
        self.browse_stash = browse_stash
        self.browse_tags = browse_tags
        self.browse_tag = browse_tag
        self.browse_mode = bool(browse_branch or browse_file or browse_reflog or browse_stash or browse_tags)
        if browse_branch or browse_file or browse_reflog or browse_stash or browse_tags:
            self.viewer_mode = True
        if cli_mode:
            self.viewer_mode = True
            self.cli_mode = True
        else:
            self.cli_mode = False
        self.is_dark_theme = False  # refined in load_settings/apply_theme
        self.start_time_full_head = get_full_head_sha(self.repo_path)
        self.start_time_head = get_head_sha(self.repo_path)
        # Detect if the tool itself is running from a source repo (not pip-installed)
        _tool_dir = os.path.dirname(os.path.abspath(__file__))
        while _tool_dir and _tool_dir != os.path.dirname(_tool_dir):
            if os.path.isdir(os.path.join(_tool_dir, ".git")) or os.path.isfile(os.path.join(_tool_dir, ".git")):
                break
            _tool_dir = os.path.dirname(_tool_dir)
        self.is_running_from_repo = _is_git_install(_tool_dir) if _tool_dir else False
        self._tool_repo_path = _tool_dir if self.is_running_from_repo else None
        self.start_time_tool_head = get_head_sha(self._tool_repo_path) if self._tool_repo_path else None
        self.start_time_tool_full_head = get_full_head_sha(self._tool_repo_path) if self._tool_repo_path else None
        self.cached_current_head_full_sha = self.start_time_full_head
        self.cached_has_uncommitted = False
        self.last_head = None
        self.best_commit_sha = None
        self.marked_shas = set()
        self.browse_limit = browse_limit
        self.browse_windows = []
        self.viewer_windows = []
        self.app_managed_stash_sha = None
        self.consolidated_diff_start_sha = None

        # Search options (synced from the Search Options dropdown in setup_ui)
        # (state lives in CommitFilterController)

        # Global application icon is handled in the main entry point

        # Persistence
        self.settings = QSettings("shyjun", "GitInteractiveRebase")
        # Window-type specific key prefix so main and browse windows don't
        # clobber each other's saved size/position across sessions.
        self.settings_scope = "browse" if self.browse_mode else "main"
        self.current_font_size = int(self.settings.value("font_size", 10))
        self.show_diffs = self.settings.value(self._sk("show_diffs"), False, type=bool)
        self.show_origin_options = self.settings.value(self._sk("show_origin_options"), False, type=bool)
        self.show_rebase_options = self.settings.value(self._sk("show_rebase_options"), False, type=bool)
        self.show_squash_options = self.settings.value(self._sk("show_squash_options"), True, type=bool)
        self.show_local_branches = self.settings.value(self._sk("show_local_branches"), False, type=bool)
        self.show_tags = self.settings.value(self._sk("show_tags"), False, type=bool)
        self.show_stats = self.settings.value(self._sk("show_stats"), True, type=bool)
        self.show_date = self.settings.value(self._sk("show_date"), True, type=bool)

        # Browse mode is a strict read-only history viewer: force-hide the
        # mutating groups so the user only sees the commit list + diffs.
        if self.browse_mode:
            self.show_squash_options = False
            self.show_origin_options = False
            self.show_rebase_options = False

        self.setWindowTitle(f"git-interactive-rebase-gui-tool : branch=..., HEAD=..., path={self.repo_path}") # Temporary name until load_history updates it
        self.resize(1100, 800)
        self.setMinimumWidth(1100)

        # Performance Cache — created before setup_ui so CommitFilterController
        # can be wired with a reference to it.
        self.commit_cache = {} # sha -> {'meta': str, 'msg': str, 'diff': str, 'files': list}

        self.setup_ui()
        self.restore_visibility_settings()
        self.load_settings()

        # Debounce timer for side diff updates
        self.update_diff_timer = QTimer(self)
        self.update_diff_timer.setSingleShot(True)
        self.update_diff_timer.timeout.connect(self._do_update_side_diff)

        if self.browse_mode:
            self.load_browse_history_async()
        else:
            self.load_history()
            if self._auto_detect_base:
                QTimer.singleShot(0, self._detect_base_async)
        self.update_rebase_buttons()
        self.list_widget.setFocus()

        if self.viewer_mode and not self.browse_mode:
            QTimer.singleShot(0, self._notify_viewer_mode)

        # Check for updates on startup if enabled
        from PySide6.QtCore import QSettings as _QS
        _s = _QS("git-interactive-rebase-gui-tool", "config")
        if _s.value("startup/auto_check_updates", True, type=bool):
            QTimer.singleShot(500, self._check_updates_on_startup)
        else:
            print("[startup_check] auto-check updates disabled")

    def _sk(self, key):
        """Scopes a settings key by window type so main and browse windows keep
        independent saved options (e.g. show_date, show_stats)."""
        return f"{self.settings_scope}/{key}"

    def load_settings(self):
        """Loads persistent user settings like font size and theme."""
        # Diff Tab
        if self.browse_mode:
            # Always land on the plain-diff tab in browse mode so a diff is
            # visible immediately (the file-wise pane looks empty without a selection).
            diff_tab_index = 0
        else:
            diff_tab_index = self.settings.value(self._sk("diff_tab_index"), 0, type=int)
        if hasattr(self, 'diff_tab_widget'):
            self.diff_tab_widget.setCurrentIndex(diff_tab_index)

        # Font Size
        size = self.settings.value("font_size", 10, type=int)
        self.current_font_size = size
        self.update_font()

        # Theme
        theme = self.settings.value("theme", "light", type=str)
        self.is_dark_theme = (theme == "dark")
        if self.is_dark_theme:
            self.dark_radio.setChecked(True)
        else:
            self.light_radio.setChecked(True)
        self.apply_theme(theme)

        # Search options (Match Case / Whole Word / Display Only Matching)
        if hasattr(self, 'search_match_case_action'):
            mc = self.settings.value(self._sk("search_match_case"), False, type=bool)
            # Whole Word is intentionally not persisted: always start the tool with it off.
            ww = False
            self.settings.remove(self._sk("search_whole_word"))
            do = self.settings.value(self._sk("search_display_only"), False, type=bool)
            self._filter_controller.set_search_options(mc, ww, do)
            # Apply without firing toggled (avoids re-running the search during startup)
            for action, value in ((self.search_match_case_action, mc),
                                  (self.search_whole_word_action, ww),
                                  (self.search_display_only_action, do)):
                action.blockSignals(True)
                action.setChecked(value)
                action.blockSignals(False)

        # Window Geometry and State
        geometry = self.settings.value(self._sk("geometry"))
        if geometry:
            self.restoreGeometry(geometry)

        window_state = self.settings.value(self._sk("windowState"))
        if window_state:
            self.restoreState(window_state)

        is_maximized = self.settings.value(self._sk("isMaximized"), False, type=bool)
        if is_maximized:
            self.showMaximized()

    def closeEvent(self, event):
        """Save settings, close child browse windows, then exit."""
        self.settings.setValue(self._sk("geometry"), self.saveGeometry())
        self.settings.setValue(self._sk("windowState"), self.saveState())
        self.settings.setValue(self._sk("isMaximized"), self.isMaximized())
        self.settings.setValue(self._sk("show_stats"), self.show_stats)
        self.settings.setValue(self._sk("show_date"), self.show_date)
        for viewer in list(self.browse_windows):
            try:
                viewer.close()
            except Exception:
                pass
        self.browse_windows.clear()
        if self.browse_mode and self.parent():
            parent = self.parent()
            if hasattr(parent, 'browse_windows') and self in parent.browse_windows:
                parent.browse_windows.remove(self)
        super().closeEvent(event)

    def update_window_title(self):
        """Updates window title with branch, HEAD, and path."""
        app_time = self.app_start_time if self.app_start_time else "N/A"
        if self.browse_stash:
            title = (f"Browse Stashes (read-only, latest "
                     f"{self.browse_limit}), path={self.repo_path}")
            self.setWindowTitle(title)
            return
        if self.browse_reflog:
            title = (f"Browse Reflog (read-only, latest "
                     f"{self.browse_limit}), path={self.repo_path}")
            self.setWindowTitle(title)
            return
        if self.browse_tags:
            title = (f"Browse Tags (read-only, latest "
                     f"{self.browse_limit}), path={self.repo_path}")
            self.setWindowTitle(title)
            return
        if self.browse_file:
            if self.browse_file_ref:
                title = (f"Browse File: {self.browse_file} @ {self.browse_file_ref} (read-only, latest "
                         f"{self.browse_limit}), path={self.repo_path}")
            else:
                title = (f"Browse File: {self.browse_file} (read-only, latest "
                         f"{self.browse_limit}), path={self.repo_path}")
            self.setWindowTitle(title)
            return
        if self.browse_branch and self.browse_mode:
            label = "Browse Tag" if self.browse_tag else "Browse Branch"
            title = (f"{label}: {self.browse_branch} (read-only, latest "
                     f"{self.browse_limit}), path={self.repo_path}")
            self.setWindowTitle(title)
            return
        if self.browse_branch and getattr(self, 'cli_mode', False):
            title = f"git-interactive-rebase-gui-tool [VIEWER MODE] : branch={self.browse_branch} (read-only), path={self.repo_path}"
            self.setWindowTitle(title)
            return
        branch = get_current_branch(self.repo_path)
        mode_str = " [VIEWER MODE]" if self.viewer_mode else ""
        title = f"git-interactive-rebase-gui-tool{mode_str} : branch={branch}, path={self.repo_path}, app_start_time={app_time}"
        self.setWindowTitle(title)

    def get_head_sha(self):
        """Returns the current HEAD SHA of the repository."""
        try:
            return subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                          cwd=self.repo_path).decode().strip()
        except:
            return "unknown"

    def log_action(self, sha, action, old_head, new_head):
        """Prints a standardized, user-friendly log message for an action."""
        # Shorten SHAs for readability
        s_sha = sha[:8] if sha and len(sha) > 8 else (sha or "N/A")
        s_old = old_head[:8] if len(old_head) > 8 else old_head
        s_new = new_head[:8] if len(new_head) > 8 else new_head

        print(f"[{time.strftime('%H:%M:%S')}] {s_sha} {action}, HEAD before={s_old}, HEAD after={s_new}")

    def _check_head_unchanged(self):
        """
        Checks that the repository HEAD has not changed since the commit graph
        was last loaded/refreshed. Returns True if it is safe to proceed,
        False otherwise.

        When the HEAD has drifted this method shows a user-friendly informational
        dialog (OK-only) and returns False so every caller can abort immediately
        without performing any history-modifying operation.
        """
        current = get_full_head_sha(self.repo_path)
        if current == self.cached_current_head_full_sha:
            return True
        QMessageBox.information(
            self,
            "Repository Changed",
            "The repository has changed since it was last scanned.\n\n"
            "Please refresh the repository before performing this operation."
        )
        return False

    def _check_no_unstaged_changes(self):
        """
        Checks that the repository has no unstaged changes before performing
        a history-modifying operation. Returns True if safe to proceed,
        False otherwise.

        When unstaged changes are present this method shows a user-friendly
        informational dialog (OK-only) and returns False so every caller can
        abort immediately without performing any history-modifying operation.
        """
        if not has_uncommitted_changes(self.repo_path):
            return True
        highlight_button_temporarily(self.rescan_btn, blinks=5)
        QMessageBox.information(
            self,
            "Unstaged Changes Detected",
            "There are unstaged changes in the repository.\n\n"
            "Please use 'Rescan Repo' to handle the unstaged changes."
        )
        return False

    def _check_not_viewer_mode(self):
        """
        Checks whether Viewer Mode is enabled. Returns True if Viewer Mode is disabled,
        False otherwise.

        When Viewer Mode is enabled, displays a message informing the user to restart
        without --viewer-mode to perform history-modifying operations.
        """
        if not self.viewer_mode:
            return True
        highlight_button_temporarily(self.exit_viewer_mode_btn, blinks=5)
        if getattr(self, 'cli_mode', False):
            QMessageBox.information(
                self,
                "Viewer Mode",
                "git-interactive-rebase-gui-tool is running in Viewer Mode.\n\n"
                "This branch was opened in read-only mode with --branch. "
                "History-modifying operations are not available.")
        else:
            QMessageBox.information(
                self,
                "Viewer Mode",
                "git-interactive-rebase-gui-tool is running in Viewer Mode.\n\n"
                "Please press the 'Exit Viewer Mode' button or restart the tool without --viewer-mode "
                "to perform history-modifying operations."
            )
        return False

    def handle_exit_viewer_mode(self):
        if getattr(self, 'cli_mode', False):
            QMessageBox.information(
                self, "Viewer Mode",
                "Cannot exit viewer mode when opened with --branch.\n\n"
                "The branch was opened in read-only mode.")
            return
        self.viewer_mode = False
        self.exit_viewer_mode_btn.setVisible(False)
        self.update_window_title()

    def _notify_viewer_mode(self):
        """Highlight the 'Exit Viewer Mode' button and inform the user that the app is in Viewer Mode."""
        highlight_button_temporarily(self.exit_viewer_mode_btn, blinks=5)
        QMessageBox.information(
            self,
            "Viewer Mode",
            "git-interactive-rebase-gui-tool is running in Viewer Mode.\n\n"
            "Please press the 'Exit Viewer Mode' button to re-enable history-modifying operations."
        )

    def restore_visibility_settings(self):
        """Restores visibility of optional groups."""
        # Origin Options Visibility
        self.origin_group.setVisible(self.show_origin_options)

        # Rebase Options Visibility
        self.rebase_group.setVisible(self.show_rebase_options)

        # Squash Options Visibility
        self.squash_group.setVisible(self.show_squash_options)
