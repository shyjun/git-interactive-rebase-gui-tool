
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QPushButton,
    QLabel,
    QLineEdit,
    QCheckBox,
    QApplication,
    QMessageBox,
    QTextEdit,
    QMainWindow,
    QListWidget,
    QListWidgetItem,
    QSplitter,
)
# pyrefly: ignore [missing-import]
from PySide6.QtCore import (
    Qt,
    QSettings,
    QTimer,
)
# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QFont,
    QAction,
    QShortcut,
    QKeySequence,
)

from lib.git_helpers import (
    get_unstaged_diff,
    get_unstaged_file_stats,
    get_current_branch,
    get_full_head_sha,
    classify_tracked_changes,
    get_unstaged_file_diff,
)
from lib.widgets import (
    DiffHighlighter,
    DiffSearchBar,
    DiffView,
    StatsItemDelegate,
)


class UnstagedChangesDialog(QDialog):
    """Warning dialog for unstaged changes on startup."""
    CommitEachResult = 2
    BulkCommitResult = 3
    AmendResult = 4
    ViewerModeResult = 5
    DiscardResult = 6
    MergeResult = 7
    SelectiveCommitResult = 8

    def __init__(self, num_files, parent=None, from_rescan=False, repo_path=None, unstaged_files=None, font_size=None, managed_stash_exists=False, managed_stash_sha=None, viewer_mode=False):
        super().__init__(parent)
        self.repo_path = repo_path
        self.unstaged_files = unstaged_files or []
        self.managed_stash_sha = managed_stash_sha
        self.managed_stash_exists = managed_stash_exists or bool(managed_stash_sha)
        self.viewer_mode = viewer_mode
        if font_size is None:
            font_size = int(QSettings("shyjun", "GitInteractiveRebase").value("font_size", 10))
        self.font_size = font_size
        self.setWindowTitle("Unstaged Changes Warning")
        self.setMinimumWidth(600)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        message = (
            "<b>You have unstaged changes in the repo.</b><br><br>"
            "If needed, we can stash the changes and go ahead with the app. "
            "But be very careful with what you are doing.<br><br>"
            "Alternatively, we can <b>commit the changes</b> in various ways before we proceed.<br><br>"
            "<b>Note:</b> Untracked files are <b>not considered</b> and will be left untouched.<br><br>"
            "Otherwise, please exit, commit/discard manually, and start the app again."
        )
        
        self.label = QLabel(message)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("font-size: 13px; font-weight: normal;")
        layout.addWidget(self.label)
        
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(10)
        
        self.view_changes_btn = QPushButton("Show unstaged changes")
        self.view_changes_btn.setToolTip("Open a read-only viewer with only the unstaged changes. No edits allowed.")
        
        self.stash_btn = QPushButton("Stash and proceed to app")
        self.stash_btn.setToolTip("Stash all uncommitted changes and proceed to the app.")

        self.commit_selectively_btn = QPushButton("Commit Selectively")
        self.commit_selectively_btn.setToolTip("Choose which files (or diff hunks) to commit before starting the app.")

        commit_each_text = f"Commit each file changes separately and start app ({num_files} files modified, {num_files} commits)"
        self.commit_each_btn = QPushButton(commit_each_text)
        self.commit_each_btn.setToolTip("Commit each file's changes as its own commit, then start the app.")
        
        bulk_commit_text = f"Commit all unsaved changes to a single 'bulk' commit (Number of modified files: {num_files})"
        self.bulk_commit_btn = QPushButton(bulk_commit_text)
        self.bulk_commit_btn.setToolTip("Commit all changes into a single 'bulk' commit, then start the app.")
        
        amend_text = "Amend all changes into the HEAD commit (--amend --no-edit)"
        self.amend_btn = QPushButton(amend_text)
        self.amend_btn.setToolTip("Amend all changes into the HEAD commit (--amend --no-edit).")
        
        self.discard_btn = QPushButton("Discard unstaged changes (git checkout .), staged changes if any is untouched")
        self.discard_btn.setToolTip("Discard only unstaged (worktree) changes in tracked files. Staged changes are left untouched. This cannot be undone.")
        
        viewer_label = "Switch to" if from_rescan else "Start in"
        self.viewer_mode_btn = QPushButton(f"{viewer_label} Viewer Mode (No history-modifying operations will be allowed)")
        self.viewer_mode_btn.setToolTip(f"{viewer_label} Viewer Mode. Warning: no history-modifying operations are allowed.")

        self.exit_btn = QPushButton("Exit")
        self.exit_btn.setToolTip("Exit the application.")
        
        # Style buttons a bit
        for btn in [self.view_changes_btn, self.stash_btn, self.commit_selectively_btn, self.commit_each_btn, self.bulk_commit_btn, self.amend_btn, self.discard_btn, self.viewer_mode_btn, self.exit_btn]:
            btn.setMinimumHeight(35)
        
        self.view_changes_btn.clicked.connect(self.show_unstaged_changes)
        self.stash_btn.clicked.connect(self._on_stash)
        self.commit_selectively_btn.clicked.connect(lambda: self.done(self.SelectiveCommitResult))
        self.commit_each_btn.clicked.connect(lambda: self.done(self.CommitEachResult))
        self.bulk_commit_btn.clicked.connect(lambda: self.done(self.BulkCommitResult))
        self.amend_btn.clicked.connect(lambda: self.done(self.AmendResult))
        self.discard_btn.clicked.connect(self._on_discard)
        self.viewer_mode_btn.clicked.connect(lambda: self.done(self.ViewerModeResult))
        self.exit_btn.clicked.connect(self.reject)

        if self.viewer_mode:
            not_allowed = "Not allowed in Viewer Mode."
            for btn in [self.stash_btn, self.commit_selectively_btn, self.commit_each_btn, self.bulk_commit_btn, self.amend_btn]:
                btn.setEnabled(False)
                btn.setToolTip(not_allowed)
            self.viewer_mode_btn.setVisible(False)
        
        btn_layout.addWidget(self.view_changes_btn)
        btn_layout.addWidget(self.stash_btn)
        btn_layout.addWidget(self.commit_selectively_btn)
        btn_layout.addWidget(self.commit_each_btn)
        btn_layout.addWidget(self.bulk_commit_btn)
        btn_layout.addWidget(self.amend_btn)
        btn_layout.addWidget(self.discard_btn)
        btn_layout.addWidget(self.viewer_mode_btn)
        btn_layout.addWidget(self.exit_btn)
        
        layout.addLayout(btn_layout)

    def show_unstaged_changes(self):
        """Open a read-only viewer (same layout as View PR Diff) with only the unstaged changes."""
        if not self.repo_path:
            return
        try:
            diff_text = get_unstaged_diff(self.repo_path, ignore_submodules=True)
            file_stats = get_unstaged_file_stats(self.repo_path, ignore_submodules=True)
            branch = get_current_branch(self.repo_path) or "HEAD"
            head_sha = get_full_head_sha(self.repo_path)
            from .diff_dialogs import UnstagedDiffDialog
            dlg = UnstagedDiffDialog(
                self.repo_path, self.unstaged_files, diff_text, file_stats,
                branch, head_sha, self.font_size, self
            )
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Unstaged Changes", f"Could not load unstaged changes: {e}")

    def _on_stash(self):
        """Handle 'Stash and proceed'. Only one managed stash is allowed per session."""
        if self.managed_stash_exists:
            box = QMessageBox(self)
            box.setWindowTitle("App-created stash already exists")
            box.setIcon(QMessageBox.Question)
            box.setTextFormat(Qt.RichText)
            box.setText(
                "An app-created stash already exists.<br><br>"
                f"Existing app-created stash:<br><b>{self.managed_stash_sha}</b><br><br>"
                "Would you like the application to attempt to merge the current unstaged "
                "changes with the existing app-created stash?<br><br>"
                "If the merge cannot be completed, the original app-created stash and your "
                "current unstaged changes will both be preserved."
            )
            merge_btn = box.addButton("Merge", QMessageBox.AcceptRole)
            cancel_btn = box.addButton("Cancel", QMessageBox.RejectRole)
            box.setDefaultButton(cancel_btn)
            box.exec()
            if box.clickedButton() != merge_btn:
                return
            self.done(self.MergeResult)
            return
        self.accept()

    def _on_discard(self):
        """Handle 'Discard unstaged changes (git checkout .)'. Destructive, so confirm first."""
        if not self.repo_path:
            return
        has_staged, has_unstaged = classify_tracked_changes(self.repo_path)

        if has_staged and not has_unstaged:
            QMessageBox.information(
                self,
                "Staged Changes",
                "All tracked changes are in the staged state.\n\n"
                "Discarding won't remove staged changes. Please commit them."
            )
            return

        if has_staged and has_unstaged:
            answer = QMessageBox.warning(
                self,
                "Discard Changes",
                "There are changes in the staged and unstaged areas.\n"
                "If you continue, the unstaged changes will be lost, "
                "and staged changes will not be touched. Are you sure?\n\n"
                "This can't be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes:
                self.done(self.DiscardResult)
            return

        answer = QMessageBox.warning(
            self,
            "Discard Changes",
            "Are you sure you want to discard all unstaged changes in tracked files?\n\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.done(self.DiscardResult)


class CommitSelectivelyDialog(QDialog):
    """Dialog to pick which files (with stats) to commit from the unstaged worktree
    changes. The bottom pane shows the combined (consolidated) diff of all CHECKED
    files, with a separator line before each file's diff, like the main diff pane.
    The commit buttons are greyed out while no file is checked."""
    CommitSelectedResult = 1
    GitAddPResult = 2
    AmendSelectedResult = 3

    def __init__(self, repo_path, files, file_stats, font_size=10, parent=None, colors=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.files = list(files)
        self.file_stats = file_stats or {}
        self.font_size = font_size

        if colors is None:
            main_win = parent if isinstance(parent, QMainWindow) else None
            if main_win and hasattr(main_win, 'current_theme_colors'):
                colors = main_win.current_theme_colors
            else:
                colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}
        self.colors = colors

        self.setWindowTitle("Commit Selectively")
        self.setMinimumSize(860, 620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        branch = get_current_branch(repo_path) or "HEAD"
        header = QLabel(
            f"Unstaged Changes: <b>{branch}</b> - {len(self.files)} file{'s' if len(self.files) != 1 else ''}<br>"
            "Select the files to commit. The bottom pane shows the combined diff "
            "of the selected (checked) files."
        )
        header.setTextFormat(Qt.RichText)
        header.setWordWrap(True)
        layout.addWidget(header)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        select_all_btn = QPushButton("Select All")
        deselect_all_btn = QPushButton("Deselect All")
        select_all_btn.setFixedWidth(110)
        deselect_all_btn.setFixedWidth(110)
        select_all_btn.setToolTip("Check all files.")
        deselect_all_btn.setToolTip("Uncheck all files.")
        select_all_btn.clicked.connect(lambda: self._set_all(True))
        deselect_all_btn.clicked.connect(lambda: self._set_all(False))
        top_row.addWidget(select_all_btn)
        top_row.addWidget(deselect_all_btn)
        top_row.addStretch()
        self.counter_label = QLabel()
        top_row.addWidget(self.counter_label)
        layout.addLayout(top_row)

        # File list with per-file stats; highlight/selection is independent of checkboxes
        self.file_list = QListWidget()
        self.file_list.setFont(QFont("Courier New", font_size))
        for f in self.files:
            item = QListWidgetItem(f)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, self.file_stats.get(f))
            self.file_list.addItem(item)
        self.stats_delegate = StatsItemDelegate(
            added_color=colors.get("added", "#22863a"),
            removed_color=colors.get("removed", "#cb2431"),
            parent=self.file_list
        )
        self.file_list.setItemDelegate(self.stats_delegate)
        self.file_list.itemChanged.connect(self._update_counter)
        self.file_list.itemChanged.connect(self._refresh_diff)

        # Diff preview with the shared search bar
        self.diff_view = DiffView()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont("Courier New", font_size))
        self.diff_view.setPlaceholderText("No files selected. Check files to preview their combined diff...")
        self.highlighter = DiffHighlighter(
            self.diff_view.document(),
            added_color=colors["added"],
            removed_color=colors["removed"],
            header_color=colors["header"]
        )
        self.search_bar = DiffSearchBar(target_view=self.diff_view, parent=self)
        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self.search_bar.show_and_focus)

        # Splitter so the file list pane and the diff preview pane are resizable
        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.file_list)
        diff_pane = QWidget()
        diff_pane_layout = QVBoxLayout(diff_pane)
        diff_pane_layout.setContentsMargins(0, 0, 0, 0)
        diff_pane_layout.setSpacing(4)
        diff_pane_layout.addWidget(self.search_bar)
        diff_pane_layout.addWidget(self.diff_view)
        self.main_splitter.addWidget(diff_pane)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setSizes([260, 400])
        layout.addWidget(self.main_splitter)

        # Bottom actions
        bot_row = QHBoxLayout()
        bot_row.setSpacing(10)

        self.amend_btn = QPushButton("commit --amend selected files")
        self.amend_btn.setToolTip("Stage only the checked files and amend them into the HEAD commit (message is editable).")
        self.amend_btn.setStyleSheet(
            "QPushButton { color: #8e44ad; border: 2px solid #8e44ad; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #f6eefb; }"
        )

        self.commit_btn = QPushButton("Commit Selected Files")
        self.commit_btn.setDefault(True)
        self.commit_btn.setToolTip("Stage only the checked files and commit them in a single commit.")
        self.commit_btn.setStyleSheet(
            "QPushButton { color: #0055cc; border: 2px solid #0055cc; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #eef4ff; }"
        )

        self.add_p_btn = QPushButton("git add -p")
        self.add_p_btn.setToolTip("Pick individual diff hunks to stage, then commit/amend.")
        self.add_p_btn.setStyleSheet(
            "QPushButton { color: #e67e22; border: 2px solid #e67e22; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #fff9f0; }"
        )

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Close without committing anything.")
        cancel_btn.setStyleSheet(
            "QPushButton { color: #555; border: 2px solid #555; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #f5f5f5; }"
        )

        self.amend_btn.clicked.connect(lambda: self.done(self.AmendSelectedResult))
        self.commit_btn.clicked.connect(lambda: self.done(self.CommitSelectedResult))
        self.add_p_btn.clicked.connect(lambda: self.done(self.GitAddPResult))
        cancel_btn.clicked.connect(self.reject)

        amend_col = QVBoxLayout()
        amend_col.setSpacing(2)
        amend_col.addWidget(self.amend_btn)
        amend_note = QLabel("(amend HEAD message)")
        amend_note.setStyleSheet("color: #8e44ad; font-size: 11px;")
        amend_note.setAlignment(Qt.AlignCenter)
        amend_col.addWidget(amend_note)

        commit_col = QVBoxLayout()
        commit_col.setSpacing(2)
        commit_col.addWidget(self.commit_btn)
        commit_note = QLabel("(unchecked files stay unstaged)")
        commit_note.setStyleSheet("color: #0055cc; font-size: 11px;")
        commit_note.setAlignment(Qt.AlignCenter)
        commit_col.addWidget(commit_note)

        addp_col = QVBoxLayout()
        addp_col.setSpacing(2)
        addp_col.addWidget(self.add_p_btn)
        addp_note = QLabel("(stage hunk by hunk)")
        addp_note.setStyleSheet("color: #e67e22; font-size: 11px;")
        addp_note.setAlignment(Qt.AlignCenter)
        addp_col.addWidget(addp_note)

        cancel_col = QVBoxLayout()
        cancel_col.setSpacing(2)
        cancel_col.addWidget(cancel_btn)
        cancel_note = QLabel("Cancel")
        cancel_note.setStyleSheet("color: #555; font-size: 11px;")
        cancel_note.setAlignment(Qt.AlignCenter)
        cancel_col.addWidget(cancel_note)

        bot_row.addStretch()
        bot_row.addLayout(amend_col)
        bot_row.addLayout(commit_col)
        bot_row.addLayout(addp_col)
        bot_row.addLayout(cancel_col)
        layout.addLayout(bot_row)

        self._update_counter()
        self._refresh_diff()

    def _refresh_diff(self, _=None):
        """Show the combined diff of the currently checked files (separator line
        before each file, like the main window diff pane). With no files checked,
        the pane is cleared and the commit actions are greyed out."""
        checked = self.checked_files()
        self.amend_btn.setEnabled(bool(checked))
        self.commit_btn.setEnabled(bool(checked))
        self.add_p_btn.setEnabled(bool(checked))
        if not checked:
            self.diff_view.clear()
            return
        try:
            parts = []
            for f in checked:
                d = get_unstaged_file_diff(self.repo_path, f).rstrip("\n")
                if d:
                    parts.append(d)
            text = "\n\n".join(parts) + ("\n" if parts else "")
            self.diff_view.setPlainText(text)
            self.diff_view.set_separator_color(self.colors.get("separator", "#444444"))
            self.search_bar._perform_search()
        except Exception as e:
            self.diff_view.setPlainText(f"Error loading diff: {e}")

    def _set_all(self, state):
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(Qt.Checked if state else Qt.Unchecked)

    def _update_counter(self, _=None):
        total = self.file_list.count()
        sel = len(self.checked_files())
        self.counter_label.setText(f"<b>Selected:</b> {sel}&nbsp;&nbsp;<b>Total:</b> {total}")
        self.counter_label.setTextFormat(Qt.RichText)

    def checked_files(self):
        return [self.file_list.item(i).text()
                for i in range(self.file_list.count())
                if self.file_list.item(i).checkState() == Qt.Checked]
