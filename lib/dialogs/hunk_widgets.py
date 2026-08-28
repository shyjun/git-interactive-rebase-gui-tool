
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
    QCheckBox,
    QApplication,
    QMessageBox,
    QTextEdit,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QMainWindow,
    QMenu,
)
# pyrefly: ignore [missing-import]
from PySide6.QtCore import (
    Qt,
    QTimer,
    Signal,
)
# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
    QAction,
)

from lib.widgets import (
    DiffHighlighter,
)


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
        from PySide6.QtGui import QPainter
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
