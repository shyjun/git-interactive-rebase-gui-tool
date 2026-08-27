import os
import webbrowser
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QApplication, QMessageBox,
)


class IconPushButton(QPushButton):
    def __init__(self, text, pixmap, parent=None):
        super().__init__(text, parent)
        self._pixmap = pixmap
        self.setIconSize(pixmap.size())
        self.setMinimumHeight(50)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._pixmap and not self._pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            y = (self.height() - 32) // 2
            painter.drawPixmap(QRect(15, y, 32, 32), self._pixmap)
            painter.end()


class HelpDialog(QDialog):
    YOUTUBE_URL = "https://www.youtube.com/watch?v=JlV4O1C3uPU"
    README_URL = "https://github.com/shyjun/git-interactive-rebase-gui-tool/blob/master/README.md"
    MAILTO = "mailto:n.shyju@gmail.com"

    def __init__(self, parent=None):
        super().__init__(parent)
        from lib.git_helpers import get_head_sha
        tool_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        tool_sha = get_head_sha(tool_dir)
        if tool_sha == "Unknown":
            try:
                import json
                from lib.utils import get_assets_path
                assets_dir = get_assets_path()
                with open(os.path.join(assets_dir, "app_version.json")) as f:
                    tool_sha = json.load(f).get("sha", "unknown")
            except Exception:
                tool_sha = "unknown"
        if tool_sha and tool_sha != "unknown":
            tool_sha = tool_sha[:8]
        self.setWindowTitle(f"Help — git-interactive-rebase-gui-tool ({tool_sha})")
        self.setMinimumWidth(450)
        self.setModal(True)

        self.setStyleSheet("""
            QDialog {
                background-color: #f0f0f0;
            }
            QPushButton {
                background-color: white;
                color: #333;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 10px 15px 10px 55px;
                text-align: left;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #f9f9f9;
                border: 1px solid #ccc;
            }
            QPushButton:pressed {
                background-color: #ececec;
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

        def load_icon(name):
            try:
                from lib.utils import get_assets_path
                path = os.path.join(get_assets_path(), name)
                if os.path.exists(path):
                    p = QPixmap(path)
                    if not p.isNull():
                        return p.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            except Exception:
                pass
            return None

        def make_btn(text, icon_name, slot):
            pixmap = load_icon(icon_name)
            btn = IconPushButton(text, pixmap)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(slot)
            return btn

        layout.addWidget(make_btn("View Video Demo", "youtube_icon.png", self._open_video))
        layout.addWidget(make_btn("View Readme", "readme_icon.png", self._open_readme))
        layout.addWidget(make_btn("Mail to Author (n.shyju@gmail.com)", "mail_icon.png", self._open_mail))

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

    def _open_url(self, url):
        try:
            webbrowser.open(url)
        except Exception:
            QApplication.clipboard().setText(url)
            QMessageBox.information(self, "Link copied to clipboard",
                                    f"Could not open browser.\n\nLink copied to clipboard:\n{url}")

    def _open_video(self):
        self._open_url(self.YOUTUBE_URL)

    def _open_readme(self):
        self._open_url(self.README_URL)

    def _open_mail(self):
        self._open_url(self.MAILTO)
