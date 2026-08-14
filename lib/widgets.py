from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class BrowseDimOverlay(QWidget):
    """A semi-transparent grey veil laid over the whole browse window so it
    reads as a read-only/dimmed viewer at first glance.

    Mouse events pass straight through (WA_TransparentForMouseEvents), so the
    commit list stays fully interactive beneath the veil."""

    def __init__(self, parent, is_dark_theme):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.set_is_dark(is_dark_theme)

    def set_is_dark(self, is_dark):
        self._is_dark = is_dark
        # ~30% grey: dark theme dims toward black, light theme desaturates.
        self._color = QColor(80, 80, 80, 77) if not is_dark else QColor(30, 30, 30, 77)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._color)
        painter.end()