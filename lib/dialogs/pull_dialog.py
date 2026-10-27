# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from .push_dialog import create_warning_pixmap

PULL_YELLOW = "#f0b429"


class PullDialog(QDialog):
    """Dialog allowing the user to choose how to pull from the remote.

    Follows the same flat layout pattern as PushDialog so the global app
    stylesheet (bold QPushButtons, bold QLabels, themed QDialog background,
    etc.) applies uniformly.
    """

    OPTION_FETCH = "fetch"
    OPTION_MERGE = "merge"
    OPTION_REBASE = "rebase"

    def __init__(self, parent=None, branch=None):
        super().__init__(parent)
        self.setWindowTitle("Pull")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.branch = branch

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # ── Header: Icon + Title ──
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(create_warning_pixmap(36, PULL_YELLOW))
        self.icon_label.setFixedSize(36, 36)
        self.icon_label.setToolTip("Fetching updates from the remote.")
        header_layout.addWidget(self.icon_label)

        self.header_title = QLabel("Pull from origin")
        header_layout.addWidget(self.header_title)
        layout.addLayout(header_layout)

        # ── Subtitle ──
        upstream = f"origin/{self.branch}" if self.branch else "the remote"
        self.header_subtitle = QLabel(
            f"Fetch updates from <b>{upstream}</b>, then integrate them "
            "into your local commits."
        )
        self.header_subtitle.setWordWrap(True)
        self.header_subtitle.setStyleSheet("font-size: 13px; color: gray;")
        layout.addWidget(self.header_subtitle)

        # ── Pull option radio buttons ──
        self.button_group = QButtonGroup(self)

        self.fetch_radio = QRadioButton("Fetch only  (git fetch)")
        self.fetch_radio.setToolTip(
            "Update remote-tracking refs only. No local branch or working "
            "tree changes are made."
        )
        self.button_group.addButton(self.fetch_radio, 0)
        layout.addWidget(self.fetch_radio)

        self.merge_radio = QRadioButton("Fetch and merge  (git pull --no-rebase)")
        self.merge_radio.setChecked(True)
        self.merge_radio.setToolTip(
            "Fetch, then merge origin into the local branch (creates a merge "
            "commit when histories diverge). Conflicts are previewed first."
        )
        self.button_group.addButton(self.merge_radio, 1)
        layout.addWidget(self.merge_radio)

        self.rebase_radio = QRadioButton("Fetch and rebase  (git pull --rebase)")
        self.rebase_radio.setToolTip(
            "Fetch, then replay local commits on top of origin for a linear "
            "history. Conflicts are previewed first."
        )
        self.button_group.addButton(self.rebase_radio, 2)
        layout.addWidget(self.rebase_radio)

        for radio in (self.fetch_radio, self.merge_radio, self.rebase_radio):
            radio.toggled.connect(self._update_action_label)

        # ── Buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("class", "dialog-btn")
        self.cancel_btn.setToolTip("Close without pulling.")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.pull_btn = QPushButton("Pull")
        self.pull_btn.setProperty("class", "dialog-btn")
        self.pull_btn.setDefault(True)
        self.pull_btn.setToolTip("Run the selected git command.")
        self.pull_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.pull_btn)

        layout.addLayout(btn_layout)

    def _update_action_label(self):
        if self.fetch_radio.isChecked():
            self.pull_btn.setText("Fetch")
            self.pull_btn.setToolTip("Run git fetch.")
        else:
            self.pull_btn.setText("Pull")
            self.pull_btn.setToolTip("Run the selected git pull command.")

    def get_selected_option(self):
        """Returns the selected option identifier: 'fetch', 'merge', or 'rebase'."""
        if self.fetch_radio.isChecked():
            return self.OPTION_FETCH
        if self.rebase_radio.isChecked():
            return self.OPTION_REBASE
        return self.OPTION_MERGE

    def get_git_command(self):
        """Returns the git command argument list and human-readable label."""
        option = self.get_selected_option()
        if option == self.OPTION_FETCH:
            return ["git", "fetch"], "git fetch"
        if option == self.OPTION_REBASE:
            return ["git", "pull", "--rebase"], "git pull --rebase"
        return ["git", "pull", "--no-rebase"], "git pull"
