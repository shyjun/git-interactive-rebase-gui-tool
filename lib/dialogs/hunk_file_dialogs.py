
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

import os

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
    QMenu,
    QApplication,
    QMessageBox,
    QTextEdit,
    QFrame,
    QSplitter,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QMainWindow,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
    QComboBox,
    QSpinBox,
    QPlainTextEdit,
    QProgressBar,
    QFileDialog,
)
# pyrefly: ignore [missing-import]
from PySide6.QtCore import (
    Qt,
    QSize,
    QSettings,
    QTimer,
    Signal,
    QRect,
    QEvent,
)
# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
    QColor,
    QAction,
    QShortcut,
    QKeySequence,
    QPainter,
)

from lib.git_helpers import (
    get_unstaged_diff,
    get_unstaged_file_stats,
    get_current_branch,
    get_full_head_sha,
    classify_tracked_changes,
    get_unstaged_file_diff,
    get_commit_file_stats,
    get_commit_metadata_and_message,
)
from lib.utils import get_theme_colors
from lib.widgets import (
    BrowseDimOverlay,
    DiffHighlighter,
    DiffSearchBar,
    DiffView,
    FILE_ENTRY_ROLE,
    StatsItemDelegate,
)


def open_blame_window(parent, filename, branch=None):
    ref = branch or "HEAD"
    print(f"[blame] Opening blame viewer for '{filename}' at {ref}")
    repo_path = getattr(parent, "repo_path", None)
    if not repo_path:
        QMessageBox.critical(parent, "Error", "Repository path not available.")
        return
    font_size = getattr(parent, "current_font_size", 10)
    dlg = BlameDialog(repo_path, filename, ref=branch, font_size=font_size)
    dlg.setAttribute(Qt.WA_DeleteOnClose)
    if hasattr(parent, "browse_windows"):
        dlg._browse_windows_ref = parent.browse_windows
        parent.browse_windows.append(dlg)
        offset = len(parent.browse_windows) * 30
        if offset > 150:
            offset = offset % 150
        dlg.move(offset, offset)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()


class BlameDialog(QDialog):
    """Read-only blame viewer showing per-line commit attribution in a table.

    Layout follows the same greyish pattern as other browse windows:
    - Search bar + Search Options ▼ dropdown
    - Filter: checkboxes (Author, Subject, Code)
    - 6-column table (Commit, Author, Date, Subject, Line, Code)
    - Bottom bar: Always On Top, Show Author/Date/Subject, Refresh, Exit
    """

    _PALETTE = [
        "#4ec9b0", "#f48771", "#569cd6", "#dcdcaa",
        "#c586c0", "#ce9178", "#b5cea8", "#9cdcfe",
    ]

    def __init__(self, repo_path, filename, ref=None, font_size=10, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.filename = filename
        self.ref = ref
        self.font_size = font_size
        self.current_font_size = font_size
        self._records = []
        self._sha_color = {}
        self._next_color_idx = 0
        self.is_dark_theme = False

        if parent and hasattr(parent, "is_dark_theme"):
            self.is_dark_theme = parent.is_dark_theme

        self.setWindowTitle(f"Blame: {filename} (blame at {ref or 'HEAD'})")
        self.setMinimumSize(1100, 650)

        self._setup_ui()

        self._browse_overlay = BrowseDimOverlay(self, self.is_dark_theme)
        self._browse_overlay.raise_()

        self._load()

    def update_font(self):
        """Called when the parent window zooms in/out — updates table font."""
        self.font_size = self.current_font_size
        font = QFont("Monospace", self.current_font_size)
        self.table.setFont(font)
        self.table.horizontalHeader().setFont(font)
        self._refresh_table()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Search / Filter bar — same pattern as main app window
        search_row = QHBoxLayout()
        search_row.setSpacing(4)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search (in this file) ...")
        self.search_edit.setToolTip("Search blame output.")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.search_edit, 1)

        self.search_opts_btn = QToolButton()
        self.search_opts_btn.setText("Search Options ▼")
        self.search_opts_btn.setToolTip("Search options: Match Case, Whole Word")
        self.search_opts_btn.setPopupMode(QToolButton.InstantPopup)
        self.search_opts_btn.setMinimumHeight(28)
        self.search_opts_btn.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
        opts_menu = QMenu(self)
        self.match_case_action = QAction("Match Case", self)
        self.match_case_action.setCheckable(True)
        self.match_case_action.setChecked(False)
        self.whole_word_action = QAction("Whole Word", self)
        self.whole_word_action.setCheckable(True)
        self.whole_word_action.setChecked(False)
        opts_menu.addAction(self.match_case_action)
        opts_menu.addAction(self.whole_word_action)
        self.match_case_action.triggered.connect(self._apply_filter)
        self.whole_word_action.triggered.connect(self._apply_filter)
        self.search_opts_btn.setMenu(opts_menu)
        search_row.addWidget(self.search_opts_btn)

        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("font-size: 11px; color: gray;")
        search_row.addWidget(filter_label)

        self.filter_by_author_cb = QCheckBox("Author")
        self.filter_by_author_cb.setChecked(True)
        self.filter_by_author_cb.toggled.connect(self._apply_filter)
        search_row.addWidget(self.filter_by_author_cb)

        self.filter_by_subject_cb = QCheckBox("Subject")
        self.filter_by_subject_cb.setChecked(True)
        self.filter_by_subject_cb.toggled.connect(self._apply_filter)
        search_row.addWidget(self.filter_by_subject_cb)

        self.filter_by_code_cb = QCheckBox("Code")
        self.filter_by_code_cb.setChecked(True)
        self.filter_by_code_cb.toggled.connect(self._apply_filter)
        search_row.addWidget(self.filter_by_code_cb)

        root.addLayout(search_row)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Commit", "Author", "Date", "Subject", "Line", "Code"])
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Interactive)
        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 200)
        self.table.setColumnWidth(4, 60)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.setWordWrap(False)
        font = QFont("Monospace", self.current_font_size)
        self.table.setFont(font)
        self.table.horizontalHeader().setFont(font)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        root.addWidget(self.table, 1)

        # Bottom bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)

        self.always_on_top_cb = QCheckBox("Always On Top")
        self.always_on_top_cb.toggled.connect(self._on_always_on_top_toggled)
        bottom_bar.addWidget(self.always_on_top_cb)

        sep1 = QLabel("|")
        sep1.setStyleSheet("color: gray;")
        bottom_bar.addWidget(sep1)

        self.show_author_cb = QCheckBox("Show Author")
        self.show_author_cb.setChecked(True)
        self.show_author_cb.toggled.connect(self._refresh_table)
        bottom_bar.addWidget(self.show_author_cb)

        self.show_date_cb = QCheckBox("Show Date")
        self.show_date_cb.setChecked(True)
        self.show_date_cb.toggled.connect(self._refresh_table)
        bottom_bar.addWidget(self.show_date_cb)

        self.show_subject_cb = QCheckBox("Show Subject")
        self.show_subject_cb.setChecked(True)
        self.show_subject_cb.toggled.connect(self._refresh_table)
        bottom_bar.addWidget(self.show_subject_cb)

        bottom_bar.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Re-run git blame and reload.")
        refresh_btn.setMinimumHeight(40)
        refresh_btn.setMinimumWidth(100)
        refresh_btn.clicked.connect(self._load)
        bottom_bar.addWidget(refresh_btn)

        exit_btn = QPushButton("Exit")
        exit_btn.setToolTip("Close this blame window.")
        exit_btn.setMinimumHeight(40)
        exit_btn.setMinimumWidth(100)
        exit_btn.clicked.connect(self.close)
        exit_btn.setStyleSheet("color: red; font-weight: bold;")
        bottom_bar.addWidget(exit_btn)

        root.addLayout(bottom_bar)

    def closeEvent(self, event):
        bw = getattr(self, "_browse_windows_ref", None)
        if bw is not None and self in bw:
            bw.remove(self)
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, '_browse_overlay', None) is not None:
            self._browse_overlay.setGeometry(self.rect())

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, '_browse_overlay', None) is not None:
            self._browse_overlay.setGeometry(self.rect())
            self._browse_overlay.raise_()

    def _on_always_on_top_toggled(self, checked):
        flags = self.windowFlags()
        if checked:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        self.show()

    # ------------------------------------------------------------------
    # Table context menu
    # ------------------------------------------------------------------

    def _show_table_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        rec = self._get_filtered_records()[row]
        sha = rec["sha"]

        menu = QMenu(self)
        view_action = QAction("View commit", self)
        view_action.setToolTip("Open the diff viewer for this commit.")
        copy_sha_action = QAction("Copy SHA to clipboard", self)
        copy_sha_action.setToolTip("Copy the commit SHA to the clipboard.")
        blame_action = QAction("Blame before this", self)
        blame_action.setToolTip("Blame the file at the parent of this commit (the version just before).")
        menu.addAction(view_action)
        menu.addAction(copy_sha_action)
        menu.addAction(blame_action)

        action = menu.exec(self.table.mapToGlobal(pos))

        if action == view_action:
            self._open_view_commit(sha)
        elif action == copy_sha_action:
            QApplication.clipboard().setText(sha)
        elif action == blame_action:
            self._open_blame_before(sha)

    def _open_view_commit(self, sha):
        import subprocess
        try:
            res = subprocess.run(
                ["git", "show", "--name-status", "--format=", sha],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            if res.returncode != 0 or not res.stdout.strip():
                QMessageBox.information(self, "No Files", f"Commit {sha[:10]} has no file changes to view.")
                return
            from lib.dialogs import SingleCommitViewDialog
            dlg = SingleCommitViewDialog(self.repo_path, sha, self.current_font_size, parent=self)
            dlg.setAttribute(Qt.WA_DeleteOnClose)
            dlg.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open commit view: {str(e)}")

    def _open_blame_before(self, sha):
        import subprocess
        try:
            res = subprocess.run(
                ["git", "rev-parse", f"{sha}^"],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            if res.returncode != 0:
                QMessageBox.information(
                    self, "No parent",
                    f"Commit {sha[:8]} has no parent (root commit). Cannot blame before it."
                )
                return
            parent_sha = res.stdout.strip()

            check = subprocess.run(
                ["git", "show", f"{parent_sha}:{self.filename}"],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            if check.returncode != 0:
                QMessageBox.information(
                    self, "File not found",
                    f"'{self.filename}' did not exist before {sha[:8]}."
                )
                return

            dlg = BlameDialog(self.repo_path, self.filename, ref=parent_sha,
                              font_size=self.current_font_size)
            dlg.setAttribute(Qt.WA_DeleteOnClose)
            if hasattr(self, "_browse_windows_ref"):
                dlg._browse_windows_ref = self._browse_windows_ref
                self._browse_windows_ref.append(dlg)
            dlg.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open blame before: {str(e)}")

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load(self):
        ref_str = self.ref or "HEAD"
        print(f"[blame] Loading blame for '{self.filename}' at {ref_str} ...")
        from lib.git_helpers import get_git_blame
        try:
            self._records = get_git_blame(self.repo_path, self.filename, self.ref)
            print(f"[blame] Loaded {len(self._records)} blame lines for '{self.filename}' at {ref_str}")
        except Exception as e:
            print(f"[blame] Failed: {e}")
            QMessageBox.critical(self, "Blame failed", str(e))
            self._records = []
        self._assign_colors()
        self._refresh_table()

    def _assign_colors(self):
        self._sha_color.clear()
        self._next_color_idx = 0
        for rec in self._records:
            sha = rec["sha"]
            if sha not in self._sha_color:
                self._sha_color[sha] = QColor(self._PALETTE[self._next_color_idx % len(self._PALETTE)])
                self._next_color_idx += 1

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------

    def _refresh_table(self):
        self.table.setRowCount(0)
        filtered = self._get_filtered_records()
        self.table.setRowCount(len(filtered))

        for row_idx, rec in enumerate(filtered):
            sha_short = rec["sha"][:7]
            code = rec.get("code", "")
            line_no = str(rec.get("line_no", ""))
            author = rec.get("author", "")
            date = rec.get("date", "")
            subject = rec.get("summary", "")

            colour = self._sha_color.get(rec["sha"], QColor("#888888"))

            commit_item = QTableWidgetItem(sha_short)
            commit_item.setForeground(colour)
            f = commit_item.font()
            f.setBold(True)
            commit_item.setFont(f)
            commit_item.setToolTip(rec["sha"])
            self.table.setItem(row_idx, 0, commit_item)

            a = QTableWidgetItem(author)
            a.setForeground(colour)
            self.table.setItem(row_idx, 1, a)

            d = QTableWidgetItem(date)
            d.setForeground(colour)
            self.table.setItem(row_idx, 2, d)

            s = QTableWidgetItem(subject)
            s.setForeground(colour)
            self.table.setItem(row_idx, 3, s)

            li = QTableWidgetItem(line_no)
            li.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_idx, 4, li)

            ci = QTableWidgetItem(code)
            ci.setFont(QFont("Monospace", self.current_font_size))
            self.table.setItem(row_idx, 5, ci)

        self.table.setColumnHidden(1, not self.show_author_cb.isChecked())
        self.table.setColumnHidden(2, not self.show_date_cb.isChecked())
        self.table.setColumnHidden(3, not self.show_subject_cb.isChecked())
        self.table.resizeRowsToContents()

    # ------------------------------------------------------------------
    # Filter
    # ------------------------------------------------------------------

    def _get_filtered_records(self):
        term = self.search_edit.text().strip()
        if not term:
            return self._records

        case_sensitive = self.match_case_action.isChecked()
        whole_word = self.whole_word_action.isChecked()

        if not case_sensitive:
            term = term.lower()

        def _match(text):
            if not text:
                return False
            if not case_sensitive:
                text = text.lower()
            if whole_word:
                import re
                pattern = re.compile(r'\b' + re.escape(term) + r'\b')
                return bool(pattern.search(text))
            return term in text

        hits = []
        for rec in self._records:
            if self.filter_by_author_cb.isChecked() and _match(rec.get("author", "")):
                hits.append(rec)
            elif self.filter_by_subject_cb.isChecked() and _match(rec.get("summary", "")):
                hits.append(rec)
            elif self.filter_by_code_cb.isChecked() and _match(rec.get("code", "")):
                hits.append(rec)
        return hits

    def _apply_filter(self):
        self._refresh_table()


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


class SelectiveHunkDialog(QDialog):
    """Hunk-level selection for 'git add -p'. Lists every hunk of all chosen files
    grouped under a per-file header. Only the checked hunks are staged (and then
    committed or amended); unchecked hunks are left untouched in the working tree."""
    CommitResult = 1
    AmendResult = 2

    def __init__(self, repo_path, files, diff_by_file, hunks_by_file, font_size=10, parent=None, colors=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.files = list(files)
        self.diff_by_file = diff_by_file
        self.hunks_by_file = hunks_by_file
        self.font_size = font_size
        self.result_action = None

        if colors is None:
            main_win = parent if isinstance(parent, QMainWindow) else None
            if main_win and hasattr(main_win, 'current_theme_colors'):
                colors = main_win.current_theme_colors
            else:
                colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}
        self.colors = colors

        self.setWindowTitle("Commit Selectively - git add -p")
        self.setMinimumSize(920, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QLabel(
            "<b>git add -p</b> - pick individual hunks to stage.<br>"
            "Only the checked hunks will be staged and committed. "
            "Unchecked hunks stay in the working tree untouched."
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
        select_all_btn.clicked.connect(lambda: self._set_all(True))
        deselect_all_btn.clicked.connect(lambda: self._set_all(False))
        top_row.addWidget(select_all_btn)
        top_row.addWidget(deselect_all_btn)
        top_row.addStretch()
        self.counter_label = QLabel()
        top_row.addWidget(self.counter_label)
        layout.addLayout(top_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        hunks_layout = QVBoxLayout(container)
        hunks_layout.setSpacing(8)

        self.hunk_widgets = []   # list of (filepath, HunkWidget) in display order
        for f in self.files:
            hunks = self.hunks_by_file.get(f, [])
            if not hunks:
                continue
            file_label = QLabel(f"<b>File:</b> {f}")
            file_label.setTextFormat(Qt.RichText)
            file_label.setWordWrap(True)
            hunks_layout.addWidget(file_label)
            for i, (hdr, body) in enumerate(hunks):
                hw = HunkWidget(i + 1, hdr, body, self.colors, font_size,
                                sha=None, filepath=f, allow_edit=False)
                hw.checkbox.stateChanged.connect(self._update_counter)
                self.hunk_widgets.append((f, hw))
                hunks_layout.addWidget(hw)

        hunks_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Bottom: exactly git commit / git commit --amend / Cancel
        bot_row = QHBoxLayout()
        bot_row.setSpacing(10)

        self.commit_btn = QPushButton("git commit")
        self.commit_btn.setDefault(True)
        self.commit_btn.setToolTip("Stage the checked hunks and commit them with a new message.")
        self.commit_btn.setStyleSheet(
            "QPushButton { color: #0055cc; border: 2px solid #0055cc; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #eef4ff; }"
        )

        self.amend_btn = QPushButton("git commit --amend")
        self.amend_btn.setToolTip("Stage the checked hunks and amend them into the HEAD commit (message is editable).")
        self.amend_btn.setStyleSheet(
            "QPushButton { color: #e67e22; border: 2px solid #e67e22; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #fff9f0; }"
        )

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Close without staging anything.")
        cancel_btn.setStyleSheet(
            "QPushButton { color: #555; border: 2px solid #555; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #f5f5f5; }"
        )

        self.commit_btn.clicked.connect(lambda: self._finish("commit"))
        self.amend_btn.clicked.connect(lambda: self._finish("amend"))
        cancel_btn.clicked.connect(self.reject)

        commit_col = QVBoxLayout()
        commit_col.setSpacing(2)
        commit_col.addWidget(self.commit_btn)
        commit_note = QLabel("(new message)")
        commit_note.setStyleSheet("color: #0055cc; font-size: 11px;")
        commit_note.setAlignment(Qt.AlignCenter)
        commit_col.addWidget(commit_note)

        amend_col = QVBoxLayout()
        amend_col.setSpacing(2)
        amend_col.addWidget(self.amend_btn)
        amend_note = QLabel("(edit HEAD message)")
        amend_note.setStyleSheet("color: #e67e22; font-size: 11px;")
        amend_note.setAlignment(Qt.AlignCenter)
        amend_col.addWidget(amend_note)

        cancel_col = QVBoxLayout()
        cancel_col.setSpacing(2)
        cancel_col.addWidget(cancel_btn)
        cancel_note = QLabel("Cancel")
        cancel_note.setStyleSheet("color: #555; font-size: 11px;")
        cancel_note.setAlignment(Qt.AlignCenter)
        cancel_col.addWidget(cancel_note)

        bot_row.addStretch()
        bot_row.addLayout(commit_col)
        bot_row.addLayout(amend_col)
        bot_row.addLayout(cancel_col)
        layout.addLayout(bot_row)

        self._update_counter()

    def _set_all(self, state):
        for _, hw in self.hunk_widgets:
            hw.set_selected(state)

    def _update_counter(self, _=None):
        total = len(self.hunk_widgets)
        sel = sum(1 for _, hw in self.hunk_widgets if hw.is_selected())
        self.counter_label.setText(f"<b>Selected hunks:</b> {sel}&nbsp;&nbsp;<b>Total:</b> {total}")
        self.counter_label.setTextFormat(Qt.RichText)

    def _finish(self, action):
        self.result_action = action
        self.done(self.CommitResult if action == "commit" else self.AmendResult)

    def selected_indices_by_file(self):
        """Returns {filepath: [kept hunk indices]} from the current checkbox states."""
        idx = 0
        kept = {}
        for f in self.files:
            n = len(self.hunks_by_file.get(f, []))
            kept[f] = [j for j in range(n)
                       if self.hunk_widgets[idx + j][1].is_selected()]
            idx += n
        return kept


class EditHunkDialog(QDialog):
    """A small lightweight dialog to edit a single diff hunk."""
    def __init__(self, sha, filepath, hunk_index, hunk_text, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Hunk")
        self.setMinimumSize(800, 500)
        self.original_hunk = hunk_text
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # Header info
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        
        commit_label = QLabel(f"<b>Commit:</b> <span style='color:{self.parent().colors['header'] if self.parent() and hasattr(self.parent(), 'colors') else '#66d9ef'};'>{sha}</span>&nbsp;&nbsp;changes in {filepath}")
        commit_label.setTextFormat(Qt.RichText)
        header_layout.addWidget(commit_label)
        
        file_label = QLabel(f"<b>File:</b> {filepath}")
        file_label.setTextFormat(Qt.RichText)
        header_layout.addWidget(file_label)
        
        hunk_label = QLabel("Edit the selected hunk below. Only valid patch format should be kept.")
        hunk_label.setStyleSheet("color: #666;")
        header_layout.addWidget(hunk_label)
        
        layout.addLayout(header_layout)
        
        # Editor
        editor_label = QLabel("Hunk (editable)")
        editor_label.setContentsMargins(2, 0, 0, 0)
        layout.addWidget(editor_label)
        
        self.editor = QTextEdit()
        self.editor.setFont(QFont("Courier New", font_size))
        self.editor.setPlainText(hunk_text)
        self.editor.setAcceptRichText(False)
        self.editor.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.editor)
        
        # Tip/Warning row
        tip_row = QHBoxLayout()
        tip_row.setSpacing(8)
        warning_icon = QLabel("ⓘ")
        warning_icon.setStyleSheet("font-size: 16px; color: #e67e22;")
        warning_text = QLabel("Invalid patch edits may fail to apply.")
        warning_text.setStyleSheet("color: #666; font-size: 11px;")
        tip_row.addStretch()
        tip_row.addWidget(warning_icon)
        tip_row.addWidget(warning_text)
        layout.addLayout(tip_row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        reset_btn = QPushButton("Reset to Original Hunk")
        reset_btn.setMinimumHeight(32)
        reset_btn.clicked.connect(self._reset)
        
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setMinimumHeight(32)
        self.apply_btn.setMinimumWidth(100)
        self.apply_btn.clicked.connect(self.accept)
        self.apply_btn.setStyleSheet("font-weight: bold;")
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(32)
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)

    def _reset(self):
        self.editor.setPlainText(self.original_hunk)

    def get_hunk_text(self):
        return self.editor.toPlainText()


class DropHunkDialog(QDialog):
    """A small lightweight dialog to confirm dropping a single diff hunk."""
    def __init__(self, sha, filepath, hunk_index, hunk_text, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Drop Hunk")
        self.setMinimumSize(800, 500)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # Header info
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        
        main_win = self.parent().parent() if self.parent() else None
        header_color = main_win.colors['header'] if main_win and hasattr(main_win, 'colors') else '#66d9ef'
        
        commit_label = QLabel(f"<b>Commit:</b> <span style='color:{header_color};'>{sha}</span>&nbsp;&nbsp;changes in {filepath}")
        commit_label.setTextFormat(Qt.RichText)
        header_layout.addWidget(commit_label)
        
        file_label = QLabel(f"<b>File:</b> {filepath}")
        file_label.setTextFormat(Qt.RichText)
        header_layout.addWidget(file_label)
        
        msg_label = QLabel("<b>Are you sure you want to drop this hunk from the commit?</b><br><br>This hunk will be removed from the current commit. This action can be undone using app undo/reset mechanisms if needed.")
        msg_label.setStyleSheet("color: #cc2200; font-size: 13px;")
        msg_label.setWordWrap(True)
        msg_label.setTextFormat(Qt.RichText)
        header_layout.addWidget(msg_label)
        
        layout.addLayout(header_layout)
        
        # Viewer
        viewer_label = QLabel("Hunk (read-only)")
        viewer_label.setContentsMargins(2, 0, 0, 0)
        layout.addWidget(viewer_label)
        
        self.viewer = QTextEdit()
        self.viewer.setFont(QFont("Courier New", font_size))
        self.viewer.setPlainText(hunk_text)
        self.viewer.setReadOnly(True)
        self.viewer.setAcceptRichText(False)
        self.viewer.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.viewer)
        
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        
        self.drop_btn = QPushButton("Drop Hunk")
        self.drop_btn.setMinimumHeight(32)
        self.drop_btn.setMinimumWidth(100)
        self.drop_btn.clicked.connect(self.accept)
        self.drop_btn.setStyleSheet("color: #cc2200; font-weight: bold; border: 2px solid #cc2200; border-radius: 4px; padding: 5px;")
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(32)
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_row.addStretch()
        btn_row.addWidget(self.drop_btn)
        btn_row.addWidget(self.cancel_btn)
        layout.addLayout(btn_row)


class ElidedLabel(QLabel):
    """A QLabel that strictly stays on one line and elides text with '...' when space is constrained."""
    def __init__(self, text, checkbox_to_toggle=None, parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self.checkbox = checkbox_to_toggle
        self.setMinimumWidth(10)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMaximumHeight(35)
        self._elided_text = text
        
    def setText(self, text):
        if self._full_text != text:
            self._full_text = text
            self._update_elided()
            self.update()
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elided()

    def _update_elided(self):
        fm = self.fontMetrics()
        self._elided_text = fm.elidedText(self._full_text, Qt.ElideRight, self.width())
        
    def mouseReleaseEvent(self, event):
        if self.checkbox and event.button() == Qt.LeftButton:
            self.checkbox.toggle()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, self._elided_text)


class HunkWidget(QFrame):
    """A framed widget displaying a single diff hunk with a checkbox."""
    apply_hunk_modification = Signal(int)
    drop_hunk = Signal(int)

    def __init__(self, hunk_index, hunk_header, hunk_text, colors, font_size, sha=None, filepath=None, is_only_hunk=False, is_only_file=False, allow_edit=True):
        super().__init__()
        self.hunk_index = hunk_index
        self.hunk_header = hunk_header
        self.original_hunk_header = hunk_header
        self.original_hunk_text = hunk_text
        self.current_hunk_text = hunk_text
        self.colors = colors
        self.font_size = font_size
        self.sha = sha
        self.filepath = filepath
        self.is_only_hunk = is_only_hunk
        self.is_only_file = is_only_file
        self.allow_edit = allow_edit

        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Header row wrapped in a fixed-height widget to prevent expansion from long hunk headers
        self.header_widget = QWidget()
        self.header_widget.setFixedHeight(34)
        header_row = QHBoxLayout(self.header_widget)
        header_widget = self.header_widget  # alias for addWidget below
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        self.checkbox = QCheckBox("")
        self.checkbox.setChecked(True)
        self.checkbox.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        bold_font = self.checkbox.font()
        bold_font.setBold(True)
        
        self.hunk_header_label = ElidedLabel(f"Change {hunk_index}   {hunk_header}", self.checkbox)
        self.hunk_header_label.setFont(bold_font)
        
        header_row.addWidget(self.checkbox)
        header_row.addWidget(self.hunk_header_label, stretch=1)
        
        header_row.addStretch()

        changed = sum(1 for l in hunk_text.splitlines() if l.startswith(('+', '-')) and not l.startswith(('+++', '---')))
        self.line_count_label = QLabel(f"{changed} line{'s' if changed != 1 else ''}")
        self.line_count_label.setStyleSheet("color: gray;")
        header_row.addWidget(self.line_count_label)
        
        if self.allow_edit:
            self.edit_btn = QPushButton("Edit")
            self.edit_btn.setFixedWidth(70)
            self.edit_btn.setFixedHeight(26)
            self.edit_btn.setCursor(Qt.PointingHandCursor)
            self.edit_btn.clicked.connect(self.show_hunk_menu)
            header_row.addWidget(self.edit_btn)
        
        layout.addWidget(header_widget)

        self.diff_view = QTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(QFont("Courier New", font_size))
        self.diff_view.setPlainText(hunk_text)
        self.diff_view.setLineWrapMode(QTextEdit.NoWrap)

        _fm = QFontMetrics(self.diff_view.font())
        _stripped = hunk_text.rstrip('\n')
        _lines = _stripped.count('\n') + 1 if _stripped else 1
        _doc_margin = int(self.diff_view.document().documentMargin())
        _h = (_lines * _fm.lineSpacing()
              + _doc_margin * 2
              + self.diff_view.frameWidth() * 2
              + self.diff_view.contentsMargins().top()
              + self.diff_view.contentsMargins().bottom()
              + 4)
        _final_h = min(max(_h, 50), 320)
        self.diff_view.setMinimumHeight(_final_h)
        self.diff_view.setMaximumHeight(_final_h)

        self.highlighter = DiffHighlighter(
            self.diff_view.document(),
            added_color=colors["added"],
            removed_color=colors["removed"],
            header_color=colors["header"]
        )
        layout.addWidget(self.diff_view)

        # Deferred height adjustment: re-measure after the widget is shown and laid out
        QTimer.singleShot(0, self._adjust_diff_view_height)

    def _adjust_diff_view_height(self):
        """Re-measure and fix the diff_view height after the first event loop cycle."""
        doc_h = self.diff_view.document().size().height()
        m = self.diff_view.contentsMargins()
        h = int(doc_h) + self.diff_view.frameWidth() * 2 + m.top() + m.bottom() + 2
        h = min(max(h, 50), 320)

        self.diff_view.setMinimumHeight(h)
        self.diff_view.setMaximumHeight(h)

        lm = self.layout().contentsMargins()
        total_h = (lm.top() + self.header_widget.height() +
                   self.layout().spacing() + h + lm.bottom())
        self.setFixedHeight(total_h)

        parent = self.parent()
        while parent:
            parent.updateGeometry()
            parent.adjustSize() if hasattr(parent, 'adjustSize') else None
            parent = parent.parent() if not isinstance(parent, QScrollArea) else None

    def show_hunk_menu(self):
        menu = QMenu(self)
        edit_action = menu.addAction("Edit Hunk")
        copy_action = menu.addAction("Copy Hunk")
        menu.addSeparator()
        drop_action = menu.addAction("Drop Hunk")

        # Position menu below the edit button
        action = menu.exec(self.edit_btn.mapToGlobal(self.edit_btn.rect().bottomLeft()))

        if action == edit_action:
            self.open_edit_dialog()
        elif action == copy_action:
            QApplication.clipboard().setText(self.current_hunk_text)
        elif action == drop_action:
            self.open_drop_dialog()

    def open_drop_dialog(self):
        if self.is_only_hunk and self.is_only_file:
            QMessageBox.information(
                self,
                "Cannot Drop Hunk",
                "This is the only hunk in the entire commit.\n\n"
                "Dropping this hunk would effectively remove the whole commit. Please use the regular \"Drop Commit\" feature instead."
            )
            return

        full_text = f"{self.hunk_header}\n{self.current_hunk_text}"
        dlg = DropHunkDialog(self.sha, self.filepath, self.hunk_index, full_text, self.font_size, self)
        if dlg.exec() == QDialog.Accepted:
            self.set_selected(False)
            self.drop_hunk.emit(self.hunk_index)

    def open_edit_dialog(self):
        full_text = f"{self.hunk_header}\n{self.current_hunk_text}"
        dlg = EditHunkDialog(self.sha, self.filepath, self.hunk_index, full_text, self.font_size, self)
        if dlg.exec() == QDialog.Accepted:
            new_full_text = dlg.get_hunk_text()
            if '\n' in new_full_text:
                self.hunk_header, self.current_hunk_text = new_full_text.split('\n', 1)
            else:
                self.hunk_header = new_full_text
                self.current_hunk_text = ""

            # Update the label text to show potentially new header
            self.hunk_header_label.setText(f"Change {self.hunk_index}   {self.hunk_header}")
            self.diff_view.setPlainText(self.current_hunk_text)
            self._update_line_count()

            # Immediately apply the edited hunk — no intermediate MODIFIED state
            self.apply_hunk_modification.emit(self.hunk_index)

    def _update_line_count(self):
        changed = sum(1 for l in self.current_hunk_text.splitlines() if l.startswith(('+', '-')) and not l.startswith(('+++', '---')))
        self.line_count_label.setText(f"{changed} line{'s' if changed != 1 else ''}")

    def get_current_text(self):
        return self.current_hunk_text

    def is_selected(self):
        return self.checkbox.isChecked()

    def set_selected(self, state):
        self.checkbox.setChecked(state)


class RefineChangesDialog(QDialog):
    """Hunk selection dialog for Refine Changes in File feature."""
    apply_hunk_modification = Signal(int)
    drop_hunk = Signal(int)

    def __init__(self, sha, filepath, commit_msg, hunks, font_size=10, parent=None, is_only_file=False):
        """
        hunks: list of (hunk_header_str, hunk_body_str)
        """
        super().__init__(parent)
        self.setWindowTitle(f"Refine/Edit Changes in File: {filepath}")
        self.setMinimumSize(920, 720)
        self.hunk_widgets = []
        self.result_action = None   # 'keep' or 'drop'
        self.kept_indices = []

        main_win = parent if isinstance(parent, QMainWindow) else None
        if main_win and hasattr(main_win, 'current_theme_colors'):
            colors = main_win.current_theme_colors
        else:
            colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # --- Header ---
        short_msg = commit_msg.split('\n')[0] if commit_msg else ""
        header_html = (
            f"<b>Commit:</b> <span style='color:{colors['header']};'>{sha}</span>"
            f"&nbsp;&nbsp;{short_msg}<br>"
            "<br>"
            f"File: {filepath}<br>"
        )
        header_label = QLabel(header_html)
        header_label.setTextFormat(Qt.RichText)
        header_label.setWordWrap(True)
        layout.addWidget(header_label)

        # --- Select All / Deselect All + counter ---
        top_row = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        deselect_all_btn = QPushButton("Deselect All")
        select_all_btn.setFixedWidth(110)
        deselect_all_btn.setFixedWidth(110)
        select_all_btn.clicked.connect(lambda: self._set_all(True))
        deselect_all_btn.clicked.connect(lambda: self._set_all(False))
        top_row.addWidget(select_all_btn)
        top_row.addWidget(deselect_all_btn)
        top_row.addStretch()
        self.counter_label = QLabel()
        top_row.addWidget(self.counter_label)
        layout.addLayout(top_row)

        # --- Scrollable hunk list ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        hunks_layout = QVBoxLayout(container)
        hunks_layout.setSpacing(8)

        for i, (hdr, body) in enumerate(hunks):
            hw = HunkWidget(i + 1, hdr, body, colors, font_size, sha=sha, filepath=filepath, 
                            is_only_hunk=(len(hunks) == 1), is_only_file=is_only_file)
            hw.apply_hunk_modification.connect(self.apply_hunk_modification.emit)
            hw.drop_hunk.connect(self.drop_hunk.emit)
            hw.checkbox.stateChanged.connect(self._update_counter)
            self.hunk_widgets.append(hw)
            hunks_layout.addWidget(hw)

        hunks_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        self._update_counter()

        # --- Bottom buttons ---
        bot_row = QHBoxLayout()
        bot_row.setSpacing(10)

        self.drop_btn = QPushButton()
        self.drop_btn.setText("Drop Selected Hunks")
        self.drop_btn.setToolTip("Checked hunks will be removed from the commit; unchecked will be kept.")
        self.drop_btn.setStyleSheet(
            "QPushButton { color: #cc2200; border: 2px solid #cc2200; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #fff0ee; }"
        )

        self.keep_btn = QPushButton()
        self.keep_btn.setText("Apply Only Selected Hunks")
        self.keep_btn.setDefault(True)
        self.keep_btn.setToolTip("Checked hunks (including your edits) will remain in the commit; unchecked will be dropped.")
        self.keep_btn.setStyleSheet(
            "QPushButton { color: #0055cc; border: 2px solid #0055cc; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #eef4ff; }"
        )

        self.move_btn = QPushButton()
        self.move_btn.setText("Move Selected Changes to New Commit")
        self.move_btn.setToolTip("Checked hunks will be moved out to a new commit; unchecked will remain.")
        self.move_btn.setStyleSheet(
            "QPushButton { color: #e67e22; border: 2px solid #e67e22; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #fff9f0; }"
        )

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(80)
        cancel_btn.setToolTip("Close the refine window and return to history.")
        cancel_btn.setStyleSheet(
            "QPushButton { color: #555; border: 2px solid #555; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #f5f5f5; }"
        )

        self.drop_btn.clicked.connect(self._on_drop)
        self.keep_btn.clicked.connect(self._on_keep)
        self.move_btn.clicked.connect(self._on_move)
        cancel_btn.clicked.connect(self.reject)

        # Sub-labels
        drop_col = QVBoxLayout()
        drop_col.setSpacing(2)
        drop_col.addWidget(self.drop_btn)
        drop_note = QLabel("(Unchecked will be kept)")
        drop_note.setStyleSheet("color: #cc2200; font-size: 11px;")
        drop_note.setAlignment(Qt.AlignCenter)
        drop_col.addWidget(drop_note)

        keep_col = QVBoxLayout()
        keep_col.setSpacing(2)
        keep_col.addWidget(self.keep_btn)
        keep_note = QLabel("(Unchecked will be dropped)")
        keep_note.setStyleSheet("color: #0055cc; font-size: 11px;")
        keep_note.setAlignment(Qt.AlignCenter)
        keep_col.addWidget(keep_note)

        cancel_col = QVBoxLayout()
        cancel_col.setSpacing(2)
        cancel_col.addWidget(cancel_btn)
        cancel_note = QLabel("Cancel/Done")
        cancel_note.setStyleSheet("color: #555; font-size: 11px;")
        cancel_note.setAlignment(Qt.AlignCenter)
        cancel_col.addWidget(cancel_note)

        move_col = QVBoxLayout()
        move_col.setSpacing(2)
        move_col.addWidget(self.move_btn)
        move_note = QLabel("(Unchecked will remain in current commit)")
        move_note.setStyleSheet("color: #e67e22; font-size: 11px;")
        move_note.setAlignment(Qt.AlignCenter)
        move_col.addWidget(move_note)

        bot_row.addLayout(drop_col)
        bot_row.addLayout(keep_col)
        bot_row.addLayout(move_col)
        bot_row.addLayout(cancel_col)
        
        layout.addLayout(bot_row)

    def _update_counter(self, _=None):
        total = len(self.hunk_widgets)
        sel = sum(1 for hw in self.hunk_widgets if hw.is_selected())
        drop = total - sel
        self.counter_label.setText(
            f"<b>Selected:</b> {sel}&nbsp;&nbsp;<b>Un-Selected:</b> {drop}&nbsp;&nbsp;<b>Total:</b> {total}"
        )
        self.counter_label.setTextFormat(Qt.RichText)

    def _set_all(self, state):
        for hw in self.hunk_widgets:
            hw.set_selected(state)

    def _warn_single_hunk(self, action_label):
        """Show a warning when the file has only one hunk. Returns True to proceed."""
        if len(self.hunk_widgets) == 1:
            reply = QMessageBox.warning(
                self,
                "Single Change Warning",
                f"This file has only <b>one change (hunk)</b>.<br><br>"
                f"<b>{action_label}</b> on a single hunk will affect the <b>entire file change</b>.<br>"
                "Are you sure you want to continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            return reply == QMessageBox.Yes
        return True

    def _on_drop(self):
        if not self._warn_single_hunk("Drop Selected"):
            return
        self.kept_indices = [i for i, hw in enumerate(self.hunk_widgets) if not hw.is_selected()]
        self.result_action = "keep"
        self.accept()

    def _on_keep(self):
        if not self._warn_single_hunk("Apply Selected Changes"):
            return
        self.kept_indices = [i for i, hw in enumerate(self.hunk_widgets) if hw.is_selected()]
        self.result_action = "keep"
        self.accept()

    def _on_move(self):
        if not self._warn_single_hunk("Move Selected Changes to New Commit"):
            return
        self.moved_indices = [i for i, hw in enumerate(self.hunk_widgets) if hw.is_selected()]
        self.kept_indices = [i for i, hw in enumerate(self.hunk_widgets) if not hw.is_selected()]
        self.result_action = "move"
        self.accept()

    def get_hunk_data(self):
        """Returns a list of (hunk_header, hunk_text) for all hunks."""
        return [(hw.hunk_header, hw.get_current_text()) for hw in self.hunk_widgets]

    def reject(self):
        super().reject()
