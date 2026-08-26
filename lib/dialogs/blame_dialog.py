
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
    QMenu,
    QApplication,
    QMessageBox,
    QTextEdit,
    QFrame,
    QTableWidget,
    QHeaderView,
    QTableWidgetItem,
    QToolButton,
    QMainWindow,
    QProgressBar,
)
# pyrefly: ignore [missing-import]
from PySide6.QtCore import (
    Qt,
    QTimer,
    QEvent,
    QSettings,
)
# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
    QColor,
    QAction,
)

from lib.widgets import (
    BrowseDimOverlay,
    DiffHighlighter,
)


def _find_main_window(widget):
    """Walk up the widget tree to find the main application window."""
    w = widget
    while w:
        from PySide6.QtWidgets import QMainWindow
        if isinstance(w, QMainWindow):
            return w
        w = w.parent()
    return widget


def open_blame_window(parent, filename, branch=None):
    ref = branch or "HEAD"
    print(f"[blame] Opening blame viewer for '{filename}' at {ref}")
    repo_path = getattr(parent, "repo_path", None)
    if not repo_path:
        print("[blame] ERROR: Repository path not available on parent.")
        QMessageBox.critical(parent, "Error", "Repository path not available.")
        return
    main_win = _find_main_window(parent)
    font_size = getattr(main_win, "current_font_size", None) or getattr(parent, "current_font_size", None) or getattr(parent, "font_size", 10)
    is_dark = getattr(main_win, "is_dark_theme", None)
    if is_dark is None:
        is_dark = getattr(parent, "is_dark_theme", False)
    print(f"[blame] font_size={font_size}, is_dark={is_dark}, parent_type={type(parent).__name__}")
    dlg = BlameDialog(repo_path, filename, ref=branch, font_size=font_size, parent=parent, is_dark_theme=is_dark)
    dlg.setAttribute(Qt.WA_DeleteOnClose)
    if hasattr(parent, "browse_windows"):
        dlg._browse_windows_ref = parent.browse_windows
        parent.browse_windows.append(dlg)
        print(f"[blame] Tracked via parent.browse_windows ({len(parent.browse_windows)} total)")
    else:
        root = parent
        while root.parent():
            root = root.parent()
        if hasattr(root, "browse_windows"):
            dlg._browse_windows_ref = root.browse_windows
            root.browse_windows.append(dlg)
            print(f"[blame] Tracked via root.browse_windows ({len(root.browse_windows)} total)")
        else:
            root.browse_windows = [dlg]
            dlg._browse_windows_ref = root.browse_windows
            print("[blame] Created root.browse_windows list")
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    print(f"[blame] Window shown: '{dlg.windowTitle()}'")


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

    def __init__(self, repo_path, filename, ref=None, font_size=10, parent=None, is_dark_theme=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window)
        self.repo_path = repo_path
        self.filename = filename
        self.ref = ref
        self.font_size = font_size
        self.current_font_size = font_size
        self._records = []
        self._sha_color = {}
        self._next_color_idx = 0
        if is_dark_theme is not None:
            self.is_dark_theme = is_dark_theme
        elif parent and hasattr(parent, "is_dark_theme"):
            self.is_dark_theme = parent.is_dark_theme
        else:
            self.is_dark_theme = False

        self.setWindowTitle(f"Blame: {filename} (blame at {ref or 'HEAD'})")
        self.setMinimumSize(1100, 650)
        print(f"[blame] BlameDialog created: '{self.windowTitle()}', parent={type(parent).__name__ if parent else 'None'}")

        # Restore saved geometry
        self._settings = QSettings("shyjun", "GitInteractiveRebase")
        geometry = self._settings.value("blame/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1100, 650)

        self._setup_ui()

        # Keyboard shortcuts (consistent with main app)
        from PySide6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("/"), self).activated.connect(self._focus_search)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self._clear_search)
        QShortcut(QKeySequence("F5"), self).activated.connect(self._load)

        self._browse_overlay = BrowseDimOverlay(self, self.is_dark_theme)
        self._browse_overlay.raise_()

        QTimer.singleShot(0, self._load)

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

        self.filter_by_commit_cb = QCheckBox("Commit")
        self.filter_by_commit_cb.setChecked(False)
        self.filter_by_commit_cb.toggled.connect(self._apply_filter)
        search_row.addWidget(self.filter_by_commit_cb)

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
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        root.addWidget(self.table, 1)

        # Progress overlay (shown during loading)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setFixedHeight(28)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("Loading blame…")
        self._progress_bar.setStyleSheet(
            "QProgressBar { text-align: center; font-size: 12px; "
            "border: 1px solid gray; border-radius: 4px; background: #3c3c3c; color: white; }"
            "QProgressBar::chunk { background: #569cd6; border-radius: 3px; }"
        )
        self._progress_bar.hide()
        root.addWidget(self._progress_bar)

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
        print(f"[blame] Closing: '{self.windowTitle()}'")
        # Save geometry for next session
        self._settings.setValue("blame/geometry", self.saveGeometry())
        bw = getattr(self, "_browse_windows_ref", None)
        if bw is not None and self in bw:
            bw.remove(self)
            print(f"[blame] Removed from browse_windows ({len(bw)} remaining)")
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

    def _on_cell_double_clicked(self, row, col):
        """Double-click on a blame row opens the commit viewer."""
        records = self._get_filtered_records()
        if row < 0 or row >= len(records):
            return
        sha = records[row]["sha"]
        self._open_view_commit(sha)

    def _focus_search(self):
        """Focus the search bar (bound to / shortcut)."""
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def _clear_search(self):
        """Clear search filter (bound to Esc shortcut)."""
        if self.search_edit.text():
            self.search_edit.clear()
        else:
            self.close()

    def _show_table_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        rec = self._get_filtered_records()[row]
        sha = rec["sha"]
        print(f"[blame] Context menu on row {row}, SHA={sha[:10]}")

        menu = QMenu(self)
        view_action = QAction("View commit", self)
        view_action.setToolTip("Open the diff viewer for this commit.")
        menu.addAction(view_action)
        from lib.app_window.helpers import add_open_with_system_default_action
        orig_filename = rec.get("filename") or self.filename
        add_open_with_system_default_action(menu, orig_filename, self, sha=sha, is_head=False)
        menu.addSeparator()
        copy_sha_action = QAction("Copy SHA to clipboard", self)
        copy_sha_action.setToolTip("Copy the commit SHA to the clipboard.")
        blame_action = QAction("Blame before this", self)
        blame_action.setToolTip("Blame the file at the parent of this commit (the version just before).")
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
        print(f"[blame] View commit: {sha[:10]}")
        try:
            res = subprocess.run(
                ["git", "show", "--name-status", "--format=", sha],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            if res.returncode != 0 or not res.stdout.strip():
                print(f"[blame] No files changed in {sha[:10]}")
                QMessageBox.information(self, "No Files", f"Commit {sha[:10]} has no file changes to view.")
                return
            from lib.dialogs import SingleCommitViewDialog
            colors = None
            w = self
            while w:
                from PySide6.QtWidgets import QMainWindow
                if isinstance(w, QMainWindow) and hasattr(w, 'current_theme_colors'):
                    colors = w.current_theme_colors
                    break
                w = w.parent()
            dlg = SingleCommitViewDialog(self.repo_path, sha, self.current_font_size, parent=self, colors=colors)
            dlg.setAttribute(Qt.WA_DeleteOnClose)
            flags = (dlg.windowFlags() & ~Qt.Dialog) | Qt.Window
            dlg.setWindowFlags(flags)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
            print(f"[blame] SingleCommitViewDialog shown for {sha[:10]}")
        except Exception as e:
            print(f"[blame] ERROR: Could not open commit view: {e}")
            QMessageBox.critical(self, "Error", f"Could not open commit view: {str(e)}")

    def _open_blame_before(self, sha):
        import subprocess
        print(f"[blame] Blame before: {sha[:10]} for '{self.filename}'")
        try:
            res = subprocess.run(
                ["git", "rev-parse", f"{sha}^"],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            if res.returncode != 0:
                print(f"[blame] No parent for {sha[:8]} (root commit)")
                QMessageBox.information(
                    self, "No parent",
                    f"Commit {sha[:8]} has no parent (root commit). Cannot blame before it."
                )
                return
            parent_sha = res.stdout.strip()
            print(f"[blame] Parent SHA: {parent_sha[:10]}")

            check = subprocess.run(
                ["git", "show", f"{parent_sha}:{self.filename}"],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            if check.returncode != 0:
                print(f"[blame] File '{self.filename}' did not exist at {parent_sha[:8]}")
                QMessageBox.information(
                    self, "File not found",
                    f"'{self.filename}' did not exist before {sha[:8]}."
                )
                return

            print(f"[blame] Creating new BlameDialog for '{self.filename}' at {parent_sha[:10]}")
            dlg = BlameDialog(self.repo_path, self.filename, ref=parent_sha,
                              font_size=self.current_font_size, parent=self)
            dlg.setAttribute(Qt.WA_DeleteOnClose)
            if hasattr(self, "_browse_windows_ref"):
                dlg._browse_windows_ref = self._browse_windows_ref
                self._browse_windows_ref.append(dlg)
            else:
                root = self
                while root.parent():
                    root = root.parent()
                if hasattr(root, "browse_windows"):
                    dlg._browse_windows_ref = root.browse_windows
                    root.browse_windows.append(dlg)
                else:
                    root.browse_windows = [dlg]
                    dlg._browse_windows_ref = root.browse_windows
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open blame before: {str(e)}")

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load(self):
        ref_str = self.ref or "HEAD"
        print(f"[blame] Loading blame for '{self.filename}' at {ref_str} ...")
        self._progress_bar.show()
        self._progress_bar.setFormat(f"Loading blame for {self.filename} …")
        QApplication.processEvents()
        from lib.git_helpers import get_git_blame
        try:
            self._records = get_git_blame(self.repo_path, self.filename, self.ref)
            print(f"[blame] Loaded {len(self._records)} blame lines for '{self.filename}' at {ref_str}")
        except Exception as e:
            print(f"[blame] Failed: {e}")
            QMessageBox.critical(self, "Blame failed", str(e))
            self._records = []
        self._progress_bar.hide()
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
        total = len(self._records) if hasattr(self, '_records') else 0
        print(f"[blame] Refreshing table: {len(filtered)}/{total} rows")
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
            if self.filter_by_commit_cb.isChecked() and _match(rec.get("sha", "")):
                hits.append(rec)
            elif self.filter_by_author_cb.isChecked() and _match(rec.get("author", "")):
                hits.append(rec)
            elif self.filter_by_subject_cb.isChecked() and _match(rec.get("summary", "")):
                hits.append(rec)
            elif self.filter_by_code_cb.isChecked() and _match(rec.get("code", "")):
                hits.append(rec)
        return hits

    def _apply_filter(self):
        query = self.search_edit.text().strip() if hasattr(self, 'search_edit') else ""
        if query:
            case = self.match_case_action.isChecked()
            whole = self.whole_word_action.isChecked()
            commit = self.filter_by_commit_cb.isChecked()
            author = self.filter_by_author_cb.isChecked()
            subject = self.filter_by_subject_cb.isChecked()
            code = self.filter_by_code_cb.isChecked()
            print(f"[blame] Filter: '{query}' case={case} whole_word={whole} commit={commit} author={author} subject={subject} code={code}")
        self._refresh_table()
