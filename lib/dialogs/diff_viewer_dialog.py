
# pyrefly: ignore [missing-import]
from PySide6.QtCore import Qt
# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QSplitter,
    QWidget,
    QDialog,
    QHBoxLayout,
    QLabel,
)
# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QShortcut,
    QKeySequence,
)

from lib.app_window.helpers import mono_font
from lib.widgets import (
    DiffHighlighter,
    DiffSearchBar,
    DiffView,
)


class DiffViewerDialog(QDialog):
    """Base dialog for viewing diffs with centered buttons."""
    def __init__(self, title, sha, diff_text, font_size=10, font_family=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(800, 600)
        self.font_size = font_size
        self.font_family = font_family

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Main splitter: content on top, buttons always visible at bottom
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.setChildrenCollapsible(False)

        # Top: header + diff
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.content_layout = content_layout

        # Header info (subclasses add to self.content_layout)
        self.setup_header(sha)

        # Full diff view
        self.diff_view = DiffView()
        self.diff_view.setReadOnly(True)
        self.diff_view.setFont(mono_font(self.font_size, family=self.font_family))
        self.diff_view.setPlainText(diff_text)

        # Determine highlighting colors based on parent theme or default to dark
        app = QApplication.instance()
        main_win = parent if isinstance(parent, QMainWindow) else None
        if main_win and hasattr(main_win, 'current_theme_colors'):
             colors = main_win.current_theme_colors
        else:
             # Default dark-ish colors if not found
             colors = {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef"}

        self.highlighter = DiffHighlighter(self.diff_view.document(),
                                           added_color=colors["added"],
                                           removed_color=colors["removed"],
                                           header_color=colors["header"])

        self.diff_view.set_separator_color(colors.get("separator", "#444444"))

        # Wrap search and diff view so they appear as one item
        diff_container = QWidget()
        diff_container_layout = QVBoxLayout(diff_container)
        diff_container_layout.setContentsMargins(0, 0, 0, 0)
        diff_container_layout.setSpacing(0)

        self.search_bar = DiffSearchBar(target_view=self.diff_view, parent=diff_container)
        diff_container_layout.addWidget(self.search_bar)

        diff_container_layout.addWidget(self.diff_view)

        content_layout.addWidget(diff_container)
        main_splitter.addWidget(content_widget)

        # Bottom: buttons always visible
        btn_widget = QWidget()
        self.btn_layout = QHBoxLayout(btn_widget)
        self.btn_layout.addStretch()
        self.setup_buttons()
        self.btn_layout.addStretch()
        main_splitter.addWidget(btn_widget)

        main_splitter.setSizes([500, 50])
        self.layout.addWidget(main_splitter)

        # Connect Ctrl+F explicitly just in case focus escapes
        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self.search_bar.show_and_focus)

    def setup_header(self, sha):
        pass # To be overridden

    def setup_buttons(self):
        pass # To be overridden
