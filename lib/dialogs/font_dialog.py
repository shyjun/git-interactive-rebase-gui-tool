
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFontComboBox,
    QSpinBox,
    QTextEdit,
    QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


_PREVIEW_TEXT = """\
9f2a31c  Fix commit ordering
abcdef0  src/main.py

git rebase -i HEAD~10"""


class FontDialog(QDialog):
    """Minimal font-selection dialog for choosing a monospace font family and size.

    Shows only monospaced fonts via QFontComboBox.MonospacedFonts.
    Cancel discards changes; OK applies and saves via the caller's
    update_font / settings infrastructure.
    """

    def __init__(self, current_family="Monospace", current_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Font")
        self.setMinimumWidth(380)
        self.setModal(True)

        self._selected_family = current_family
        self._selected_size = current_size

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Font family
        row_font = QHBoxLayout()
        row_font.addWidget(QLabel("Font:"))
        self.font_combo = QFontComboBox()
        self.font_combo.setFontFilters(QFontComboBox.MonospacedFonts)
        self.font_combo.setCurrentFont(QFont(current_family, current_size))
        self.font_combo.currentFontChanged.connect(self._on_font_changed)
        row_font.addWidget(self.font_combo, 1)
        layout.addLayout(row_font)

        # Font size
        row_size = QHBoxLayout()
        row_size.addWidget(QLabel("Size:"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 32)
        self.size_spin.setValue(current_size)
        self.size_spin.valueChanged.connect(self._on_size_changed)
        row_size.addWidget(self.size_spin, 1)
        layout.addLayout(row_size)

        # Preview
        layout.addWidget(QLabel("Preview"))
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlainText(_PREVIEW_TEXT)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setMinimumHeight(80)
        layout.addWidget(self.preview)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        self._update_preview()

    def _on_font_changed(self, font):
        self._selected_family = font.family()
        self._update_preview()

    def _on_size_changed(self, size):
        self._selected_size = size
        self._update_preview()

    def _update_preview(self):
        f = QFont(self._selected_family, self._selected_size)
        f.setStyleHint(QFont.StyleHint.Monospace)
        self.preview.setFont(f)

    def _on_ok(self):
        self._selected_family = self.font_combo.currentFont().family()
        self._selected_size = self.size_spin.value()
        self.accept()

    def selected_font(self):
        """Return (family, size) selected by the user."""
        return self._selected_family, self._selected_size
