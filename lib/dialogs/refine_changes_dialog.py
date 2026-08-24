
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
    QScrollArea,
    QMessageBox,
    QMainWindow,
)
# pyrefly: ignore [missing-import]
from PySide6.QtCore import (
    Qt,
    Signal,
)

from lib.dialogs.hunk_widgets import HunkWidget


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
