import os
import webbrowser
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from lib.utils import get_assets_path


class HelpDialog(QDialog):
    YOUTUBE_URL = "https://www.youtube.com/watch?v=JlV4O1C3uPU"
    README_URL = "https://github.com/shyjun/git-interactive-rebase-gui-tool/blob/master/README.md"
    MAILTO = "mailto:n.shyju@gmail.com"

    def __init__(self, parent=None):
        super().__init__(parent)
        # Get tool version (short git SHA) for title
        from lib.git_helpers import get_head_sha
        tool_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        tool_sha = get_head_sha(tool_dir)
        if tool_sha == "Unknown":
            try:
                from lib.utils import get_assets_path
                import json
                assets_dir = get_assets_path()
                with open(os.path.join(assets_dir, "app_version.json")) as f:
                    tool_sha = json.load(f).get("sha", "unknown")
            except Exception:
                tool_sha = "unknown"
        self.setWindowTitle(f"Help — git-interactive-rebase-gui-tool ({tool_sha})")
        self.setMinimumWidth(450)
        self.setModal(True)

        self.setStyleSheet("""
            QDialog {
                background-color: #f0f0f0;
            }
            QPushButton.help-btn {
                background-color: white;
                color: #333;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 10px;
                text-align: left;
                font-size: 14px;
                font-weight: normal;
            }
            QPushButton.help-btn:hover {
                background-color: #f9f9f9;
                border: 1px solid #ccc;
            }
            QPushButton.help-btn:pressed {
                background-color: #ececec;
            }
            QLabel.help-icon {
                margin-right: 10px;
            }
            QPushButton.close-btn {
                background-color: transparent;
                border: 1px solid #ccc;
                color: #666;
                border-radius: 4px;
                padding: 5px 15px;
            }
            QPushButton.close-btn:hover {
                background-color: #e0e0e0;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 20)

        def make_help_button(text, icon_path, slot):
            btn = QPushButton(self)
            btn.setObjectName("help_button")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(60)
            btn.setProperty("class", "help-btn")
            btn.setStyleSheet("QPushButton { padding-left: 60px; }")

            btn_layout = QHBoxLayout(btn)
            btn_layout.setContentsMargins(15, 0, 15, 0)

            icon_label = QLabel()
            if os.path.exists(icon_path):
                pixmap = QIcon(icon_path).pixmap(32, 32)
                icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(32, 32)
            icon_label.setStyleSheet("background: transparent;")

            text_label = QLabel(text)
            text_label.setStyleSheet("font-size: 15px; color: #444; background: transparent;")

            btn_layout.addWidget(icon_label)
            btn_layout.addWidget(text_label)
            btn_layout.addStretch()

            btn.clicked.connect(slot)
            return btn

        try:
            base_path = get_assets_path()
        except Exception:
            base_path = ""

        layout.addWidget(make_help_button("View Video Demo", os.path.join(base_path, "youtube_icon.png"), self._open_video))
        layout.addWidget(make_help_button("View Readme", os.path.join(base_path, "readme_icon.png"), self._open_readme))
        layout.addWidget(make_help_button("Mail to Author (n.shyju@gmail.com)", os.path.join(base_path, "mail_icon.png"), self._open_mail))

        layout.addSpacing(10)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setProperty("class", "close-btn")
        close_btn.setMinimumHeight(32)
        close_btn.setMinimumWidth(80)
        close_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(close_btn)
        bottom_layout.addStretch()

        layout.addLayout(bottom_layout)

    def _open_video(self):
        webbrowser.open(self.YOUTUBE_URL)

    def _open_readme(self):
        webbrowser.open(self.README_URL)

    def _open_mail(self):
        webbrowser.open(self.MAILTO)
