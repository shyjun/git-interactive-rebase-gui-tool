
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
# pyrefly: ignore [missing-import]
from PySide6.QtCore import (
    Qt,
    Signal,
)

# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QColor,
)

from lib.app_window.helpers import mono_font
from lib.git_helpers import (
    STATUS_POINTER,
    STATUS_DIRTY,
    commit_submodule_pointers,
    discard_submodule_changes,
    list_submodules,
    stage_submodule_pointers,
)

_STATUS_LABELS = {
    "clean": "clean",
    "pointer": "new commits (pointer changed)",
    "dirty": "modified content",
    "uninitialized": "not initialized",
    "conflict": "conflict",
}


class SubmodulesDialog(QDialog):
    """Manage the repository's submodules.

    All unstaged-change flows (bulk commit, amend, stash, discard, commit
    each/selectively) deliberately exclude submodules, so pointer changes are
    handled here instead: stage the pointer, commit it as its own commit, or
    discard it (git submodule update)."""

    # Emitted BEFORE a pointer commit is created, so the main window can save
    # an undo state while the dialog is still open (direct connection =>
    # synchronous).
    will_mutate_history = Signal()
    # Emitted after any successful mutation; True when a commit was created.
    changed = Signal(bool)

    def __init__(self, repo_path, font_size=10, font_family=None, can_modify=True, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.font_size = font_size
        self.font_family = font_family
        self.can_modify = can_modify
        self.submodules = []
        self._populating = False
        # Tickable rows render bright (white on dark / near-black on light);
        # disabled rows render grey so the two are visually distinct.
        is_dark = getattr(parent, "is_dark_theme", True)
        self._enabled_fg = QColor("#ffffff" if is_dark else "#333333")
        self._disabled_fg = QColor("#808080")

        self.setWindowTitle("Submodules")
        self.setMinimumSize(720, 360)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.header = QLabel(
            "Submodule changes are excluded from all unstaged-change flows "
            "(bulk commit, amend, stash, discard).<br>"
            "Tick the changed submodule(s) to act on: stage the pointer, "
            "commit it, or discard it. Unchanged ones are disabled."
        )
        self.header.setTextFormat(Qt.RichText)
        self.header.setWordWrap(True)
        layout.addWidget(self.header)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["✓", "Path", "Status", "Current SHA", "Recorded SHA"])
        self.table.setFont(mono_font(self.font_size, family=self.font_family))
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(self._update_buttons)
        layout.addWidget(self.table)

        self.empty_label = QLabel("No submodules configured in this repository.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        check_all_btn = QPushButton("Check All")
        check_all_btn.setToolTip("Tick all modifiable (changed) submodules.")
        check_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        uncheck_all_btn = QPushButton("Uncheck All")
        uncheck_all_btn.setToolTip("Untick all submodules.")
        uncheck_all_btn.clicked.connect(lambda: self._set_all_checked(False))
        self.stage_btn = QPushButton("Stage Pointer")
        self.stage_btn.setToolTip("Record the currently checked-out commit of the ticked submodule(s) in the superproject (git add <path>).")
        self.stage_btn.clicked.connect(self._on_stage)
        self.discard_btn = QPushButton("Discard Pointer Change")
        self.discard_btn.setToolTip("Check out the recorded commit in the ticked submodule(s) (git submodule update <path>).")
        self.discard_btn.clicked.connect(self._on_discard)
        self.commit_btn = QPushButton("Commit Pointer…")
        self.commit_btn.setToolTip("Commit the pointer change of the ticked submodule(s) as a new commit (git commit --only <path>).")
        self.commit_btn.clicked.connect(self._on_commit)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(check_all_btn)
        btn_row.addWidget(uncheck_all_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.stage_btn)
        btn_row.addWidget(self.discard_btn)
        btn_row.addWidget(self.commit_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        for btn in (self.stage_btn, self.discard_btn, self.commit_btn):
            btn.setEnabled(False)

    def refresh(self):
        self.submodules = list_submodules(self.repo_path)
        has_subs = bool(self.submodules)
        self._populating = True
        try:
            self.table.setRowCount(len(self.submodules))
            for row, sub in enumerate(self.submodules):
                status_text = _STATUS_LABELS.get(sub["status"], sub["status"])
                if sub.get("embedded"):
                    status_text += " · embedded (no .gitmodules)"
                tickable = sub["status"] in (STATUS_POINTER, STATUS_DIRTY)
                fg = self._enabled_fg if tickable else self._disabled_fg

                check_item = QTableWidgetItem()
                check_item.setFlags(
                    Qt.ItemIsUserCheckable | Qt.ItemIsEnabled if tickable
                    else Qt.NoItemFlags)
                check_item.setCheckState(
                    Qt.Checked if tickable else Qt.Unchecked)
                check_item.setForeground(fg)
                self.table.setItem(row, 0, check_item)

                values = [sub["path"], status_text,
                          (sub["current_sha"] or "")[:8], sub["record_sha"][:8]]
                for col, value in enumerate(values, start=1):
                    item = QTableWidgetItem(value)
                    if not tickable:
                        item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                    item.setForeground(fg)
                    self.table.setItem(row, col, item)
        finally:
            self._populating = False
        self.table.setVisible(has_subs)
        self.empty_label.setVisible(not has_subs)
        self.table.clearSelection()
        self._update_buttons()

    def _checked(self, statuses=None):
        """Paths of ticked, modifiable rows, optionally filtered by status."""
        paths = []
        for row, sub in enumerate(self.submodules):
            item = self.table.item(row, 0)
            if item is None or item.checkState() != Qt.Checked:
                continue
            if statuses is None or sub["status"] in statuses:
                paths.append(sub["path"])
        return paths

    def _set_all_checked(self, checked):
        self._populating = True
        try:
            for row, sub in enumerate(self.submodules):
                if sub["status"] not in (STATUS_POINTER, STATUS_DIRTY):
                    continue
                item = self.table.item(row, 0)
                if item is not None:
                    item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        finally:
            self._populating = False
        self._update_buttons()

    def _update_buttons(self, *_args):
        if getattr(self, "_populating", False):
            return
        can_modify = self.can_modify and bool(self.submodules)
        pointer_paths = self._checked({STATUS_POINTER})
        restorable = self._checked({STATUS_POINTER, STATUS_DIRTY})
        self.stage_btn.setEnabled(can_modify and bool(pointer_paths))
        self.discard_btn.setEnabled(can_modify and bool(restorable))
        self.commit_btn.setEnabled(can_modify and bool(pointer_paths))

    def _on_stage(self):
        paths = self._checked({STATUS_POINTER})
        ok, detail = stage_submodule_pointers(self.repo_path, paths)
        if not ok:
            QMessageBox.critical(self, "Error", f"Failed to stage submodule pointer(s).\n\n{detail}")
            return
        self.refresh()
        self.changed.emit(False)

    def _on_discard(self):
        paths = self._checked({STATUS_POINTER, STATUS_DIRTY})
        answer = QMessageBox.question(
            self, "Discard Pointer Change",
            f"Check out the recorded commit in {len(paths)} submodule(s)?\n\n"
            + "\n".join(paths) +
            "\n\nUncommitted work inside a submodule that would be lost makes "
            "this fail safely (git's error will be shown)."
        )
        if answer != QMessageBox.Yes:
            return
        ok, detail = discard_submodule_changes(self.repo_path, paths)
        if not ok:
            QMessageBox.critical(self, "Error", f"Failed to discard submodule change(s).\n\n{detail}")
            return
        self.refresh()
        self.changed.emit(False)

    def _on_commit(self):
        paths = self._checked({STATUS_POINTER})
        default_msg = (
            f"update submodule(s): {', '.join(paths)}"
        )
        from lib.dialogs.commit_message_dialogs import NewCommitMessageDialog
        msg_dlg = NewCommitMessageDialog(
            "Commit Submodule Pointer",
            f"Committing the pointer change of {len(paths)} submodule(s) into a new commit.",
            default_msg, self.font_size, self.font_family, self,
        )
        if msg_dlg.exec() != QDialog.Accepted:
            return
        msg = msg_dlg.get_message()
        if not msg:
            return
        self.will_mutate_history.emit()
        ok, detail = commit_submodule_pointers(self.repo_path, paths, msg)
        if not ok:
            QMessageBox.critical(self, "Error", f"Failed to commit submodule pointer(s).\n\n{detail}")
            return
        self.refresh()
        self.changed.emit(True)
