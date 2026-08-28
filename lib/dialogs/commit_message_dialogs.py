
# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QDialog,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
    QLabel,
)
# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QFont,
)


class NewCommitMessageDialog(QDialog):
    """Dialog for entering a new commit message (e.g. during Move Hunks)."""
    def __init__(self, title, label_text, default_message="", font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(600, 400)
        self.font_size = font_size

        layout = QVBoxLayout(self)

        self.label = QLabel(label_text)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        self.message_edit = QTextEdit()
        self.message_edit.setFont(QFont("Courier New", self.font_size))
        self.message_edit.setPlainText(default_message)
        layout.addWidget(self.message_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.proceed_btn = QPushButton("Proceed")
        self.cancel_btn = QPushButton("Cancel")

        for btn in [self.proceed_btn, self.cancel_btn]:
            btn.setMinimumWidth(120)
            btn.setMinimumHeight(40)
            btn.setProperty("class", "dialog-btn")

        self.proceed_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self.message_edit.textChanged.connect(self.on_text_changed)
        self.on_text_changed()

        btn_layout.addWidget(self.proceed_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def get_message(self):
        return self.message_edit.toPlainText().strip()

    def on_text_changed(self):
        self.proceed_btn.setEnabled(bool(self.message_edit.toPlainText().strip()))
