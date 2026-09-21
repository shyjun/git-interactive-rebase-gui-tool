
# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
        self.content_layout = self.layout

        # Header info
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

        # Wrap search and diff view so they appear as one item in self.layout
        diff_container = QWidget()
        diff_container_layout = QVBoxLayout(diff_container)
        diff_container_layout.setContentsMargins(0, 0, 0, 0)
        diff_container_layout.setSpacing(0)

        self.search_bar = DiffSearchBar(target_view=self.diff_view, parent=diff_container)
        diff_container_layout.addWidget(self.search_bar)

        diff_container_layout.addWidget(self.diff_view)

        self.layout.addWidget(diff_container)

        # Connect Ctrl+F explicitly just in case focus escapes
        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self.search_bar.show_and_focus)

        # Buttons
        self.btn_layout = QHBoxLayout()
        self.btn_layout.addStretch() # Center spacer left
        self.setup_buttons()
        self.btn_layout.addStretch() # Center spacer right
        self.layout.addLayout(self.btn_layout)

    def setup_header(self, sha):
        pass # To be overridden

    def setup_buttons(self):
        ok_btn = QPushButton("Ok")
        ok_btn.setMinimumWidth(100)
        ok_btn.setProperty("class", "dialog-btn")
        ok_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.setProperty("class", "dialog-btn")
        cancel_btn.clicked.connect(self.reject)

        self.btn_layout.addWidget(ok_btn)
        self.btn_layout.addWidget(cancel_btn)
