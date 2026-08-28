
# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QDialog,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QLineEdit,
    QSplitter,
    QProgressBar,
    QScrollArea,
)
# pyrefly: ignore [missing-import]
from PySide6.QtCore import (
    Qt,
)
# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QFont,
)

from .diff_viewer_dialog import DiffViewerDialog


class DropDialog(DiffViewerDialog):
    def __init__(self, sha, diff_text, font_size=10, parent=None):
        super().__init__("Confirm Drop Commit", sha, diff_text, font_size, parent)

    def setup_header(self, sha):
        label = QLabel(f"Are you sure you want to drop the commit: <b>{sha}</b>?")
        # Use theme-aware warning color
        app = QApplication.instance()
        main_win = self.parent() if isinstance(self.parent(), QMainWindow) else None
        warning_color = "#f92672" # Default red
        if main_win and hasattr(main_win, 'current_theme_colors'):
             warning_color = main_win.current_theme_colors["removed"]

        label.setStyleSheet(f"color: {warning_color};") 
        self.layout.addWidget(label)

    def setup_buttons(self):
        self.yes_btn = QPushButton("Yes, Drop it")
        self.no_btn = QPushButton("No, Cancel")

        self.yes_btn.setMinimumWidth(120)
        self.no_btn.setMinimumWidth(120)

        self.yes_btn.setProperty("class", "dialog-btn")
        self.no_btn.setProperty("class", "dialog-btn")

        self.yes_btn.clicked.connect(self.accept)
        self.no_btn.clicked.connect(self.reject)

        self.btn_layout.addWidget(self.yes_btn)
        self.btn_layout.addWidget(self.no_btn)


class RephraseDialog(QDialog):
    """Dialog for editing commit message."""
    def __init__(self, sha, current_message, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Rephrase Commit: {sha}")
        self.setMinimumSize(600, 400)
        self.font_size = font_size

        layout = QVBoxLayout(self)

        label = QLabel(f"Edit commit message for: <b>{sha}</b>")
        layout.addWidget(label)

        self.message_edit = QTextEdit()
        self.message_edit.setFont(QFont("Courier New", self.font_size))
        self.message_edit.setPlainText(current_message)
        layout.addWidget(self.message_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.apply_btn = QPushButton("Apply")
        self.discard_btn = QPushButton("Discard")

        for btn in [self.apply_btn, self.discard_btn]:
            btn.setMinimumWidth(120)
            btn.setMinimumHeight(40)
            btn.setProperty("class", "dialog-btn")

        self.apply_btn.clicked.connect(self.accept)
        self.discard_btn.clicked.connect(self.reject)

        self.message_edit.textChanged.connect(self.on_text_changed)
        self.on_text_changed()

        btn_layout.addWidget(self.apply_btn)
        btn_layout.addWidget(self.discard_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def get_message(self):
        return self.message_edit.toPlainText().strip()

    def on_text_changed(self):
        self.apply_btn.setEnabled(bool(self.message_edit.toPlainText().strip()))


class CherryPickDialog(QDialog):
    """Dialog for entering a commit SHA to cherry-pick."""
    def __init__(self, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cherry-pick Commit")
        self.setFixedSize(600, 180)
        self.font_size = font_size
        self.chosen = None

        layout = QVBoxLayout(self)

        self.label = QLabel("Enter the commit SHA.")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        self.sha_edit = QLineEdit()
        self.sha_edit.setPlaceholderText("Commit SHA")
        self.sha_edit.setFont(QFont("Courier New", self.font_size))
        self.sha_edit.setMinimumHeight(36)
        layout.addWidget(self.sha_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cherry_pick_btn = QPushButton("Cherry-pick")
        self.no_commit_btn = QPushButton("Cherry-pick (--no-commit)")
        self.cancel_btn = QPushButton("Cancel")

        for btn in [self.cherry_pick_btn, self.no_commit_btn, self.cancel_btn]:
            btn.setMinimumWidth(120)
            btn.setMinimumHeight(40)
            btn.setProperty("class", "dialog-btn")

        self.cherry_pick_btn.clicked.connect(lambda: self._choose("normal"))
        self.no_commit_btn.clicked.connect(lambda: self._choose("no_commit"))
        self.cancel_btn.clicked.connect(self.reject)

        self.sha_edit.textChanged.connect(self.on_text_changed)
        self.on_text_changed()

        btn_layout.addWidget(self.cherry_pick_btn)
        btn_layout.addWidget(self.no_commit_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def _choose(self, choice):
        self.chosen = choice
        self.accept()

    def get_sha(self):
        return self.sha_edit.text().strip()

    def on_text_changed(self):
        has_text = bool(self.sha_edit.text().strip())
        self.cherry_pick_btn.setEnabled(has_text)
        self.no_commit_btn.setEnabled(has_text)


class RevertCommitDialog(QDialog):
    """Dialog for editing the commit message before reverting a commit."""
    def __init__(self, sha, revert_message, font_size=10, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Revert Commit: {sha}")
        self.setMinimumSize(600, 300)
        self.font_size = font_size

        layout = QVBoxLayout(self)

        label = QLabel(
            f"Reverting commit <b>{sha}</b>. "
            "Edit the revert commit message below:"
        )
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        layout.addWidget(label)

        self.message_edit = QTextEdit()
        self.message_edit.setFont(QFont("Courier New", self.font_size))
        self.message_edit.setPlainText(revert_message)
        layout.addWidget(self.message_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.revert_btn = QPushButton("Revert")
        self.cancel_btn = QPushButton("Cancel")

        for btn in [self.revert_btn, self.cancel_btn]:
            btn.setMinimumWidth(120)
            btn.setMinimumHeight(40)
            btn.setProperty("class", "dialog-btn")

        self.revert_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self.message_edit.textChanged.connect(self._on_text_changed)
        self._on_text_changed()

        btn_layout.addWidget(self.revert_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def get_message(self):
        return self.message_edit.toPlainText().strip()

    def _on_text_changed(self):
        self.revert_btn.setEnabled(bool(self.message_edit.toPlainText().strip()))


class SquashDialog(QDialog):
    """Dialog for choosing and editing commit message during squash."""
    def __init__(self, sha1, msg1, sha2, msg2, font_size=10, parent=None, default_radio=1):
        super().__init__(parent)
        self.setWindowTitle("Interactive Squash")
        self.setMinimumSize(600, 400)
        self.font_size = font_size

        self.msg1 = msg1
        self.msg2 = msg2

        layout = QVBoxLayout(self)

        # Label
        layout.addWidget(QLabel("Select or edit the final commit message:"))

        # Radio Buttons
        self.radio1 = QRadioButton(f"Use commit msg of {sha1}: {msg1.splitlines()[0][:50]}...")
        self.radio2 = QRadioButton(f"Use commit msg of {sha2}: {msg2.splitlines()[0][:50]}...")

        layout.addWidget(self.radio1)
        layout.addWidget(self.radio2)

        # Text Editor
        self.editor = QTextEdit()
        self.editor.setFont(QFont("Courier New", self.font_size))
        layout.addWidget(self.editor)

        # Connections
        self.radio1.toggled.connect(self.on_radio_toggled)
        self.radio2.toggled.connect(self.on_radio_toggled)

        # Default selection
        if default_radio == 2:
            self.radio2.setChecked(True)
            self.editor.setPlainText(self.msg2)
        else:
            self.radio1.setChecked(True)
            self.editor.setPlainText(self.msg1)

        # Buttons
        btn_layout = QHBoxLayout()
        self.proceed_btn = QPushButton("Proceed")
        self.cancel_btn = QPushButton("Cancel")

        self.proceed_btn.setProperty("class", "dialog-btn")
        self.cancel_btn.setProperty("class", "dialog-btn")

        self.proceed_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self.editor.textChanged.connect(self.on_text_changed)
        self.on_text_changed()

        btn_layout.addStretch()
        btn_layout.addWidget(self.proceed_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def on_radio_toggled(self):
        if self.radio1.isChecked():
            self.editor.setPlainText(self.msg1)
        elif self.radio2.isChecked():
            self.editor.setPlainText(self.msg2)

    def get_message(self):
        return self.editor.toPlainText().strip()

    def on_text_changed(self):
        self.proceed_btn.setEnabled(bool(self.editor.toPlainText().strip()))


class MultiSquashDialog(QDialog):
    """Dialog for squashing N commits — shows one radio per commit for message selection."""
    def __init__(self, sha_msg_pairs, font_size=10, parent=None):
        """
        sha_msg_pairs: list of (sha, full_commit_message) in newest→oldest order
        """
        super().__init__(parent)
        self.setWindowTitle("Squash Commits — Choose Final Commit Message")
        self.setMinimumSize(680, 480)
        self.sha_msg_pairs = sha_msg_pairs

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"<b>Squashing {len(sha_msg_pairs)} commits.</b>  "
            "Select which commit message to use as the base, then edit:"
        ))

        # Main splitter to allow resizing between the list and the editor
        self.splitter = QSplitter(Qt.Vertical)

        # Scroll area for the radio buttons
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.scroll_area.setMinimumHeight(100)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(5, 5, 5, 5)

        # Dynamic radio buttons — one per commit
        self.radios = []
        for sha, msg in sha_msg_pairs:
            first_line = msg.splitlines()[0][:60] if msg else "(empty)"
            radio = QRadioButton(f"{sha}: {first_line}...")
            self.scroll_layout.addWidget(radio)
            self.radios.append(radio)

        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)

        # Text editor
        self.editor = QTextEdit()
        self.editor.setFont(QFont("Courier New", font_size))
        self.editor.setMinimumHeight(100)

        # Add to splitter
        self.splitter.addWidget(self.scroll_area)
        self.splitter.addWidget(self.editor)

        # Disable collapsing for both panes to ensure minimum heights are respected
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)

        # Set stretch factors: list area gets some, editor gets more
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)

        layout.addWidget(self.splitter)

        # Wire radio toggling to update editor
        for i, radio in enumerate(self.radios):
            radio.toggled.connect(lambda checked, idx=i: self._on_radio(checked, idx))

        # Default: first commit selected
        self.radios[0].setChecked(True)
        self.editor.setPlainText(sha_msg_pairs[0][1])

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.proceed_btn = QPushButton("Proceed")
        self.cancel_btn = QPushButton("Cancel")
        self.proceed_btn.setProperty("class", "dialog-btn")
        self.cancel_btn.setProperty("class", "dialog-btn")
        self.proceed_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self.editor.textChanged.connect(self.on_text_changed)
        self.on_text_changed()
        btn_layout.addWidget(self.proceed_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def _on_radio(self, checked, idx):
        if checked:
            self.editor.setPlainText(self.sha_msg_pairs[idx][1])

    def get_message(self):
        return self.editor.toPlainText().strip()

    def on_text_changed(self):
        self.proceed_btn.setEnabled(bool(self.editor.toPlainText().strip()))


class ProgressDialog(QDialog):
    """Indeterminate progress dialog for background operations."""
    def __init__(self, title, message, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(450, 150)
        self.setModal(True)

        # Disable close button and other hints to make it more "locked"
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint & ~Qt.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(10)

        self.label = QLabel(message)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setMinimumHeight(20)
        layout.addWidget(self.progress_bar)

        # Add some spacing at the bottom
        layout.addSpacing(10)
