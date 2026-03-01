
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py")
    sys.exit(1)

import subprocess
import os
import webbrowser
import tempfile
import stat

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QListWidget, QVBoxLayout, 
    QWidget, QMessageBox, QListWidgetItem, QMenu, QDialog,
    QTextEdit, QPushButton, QHBoxLayout, QLabel, QRadioButton,
    QLineEdit, QSplitter, QInputDialog, QGroupBox, QSizePolicy
)
from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QAction, QShortcut, QKeySequence, QIcon
from PySide6.QtCore import Qt, QSize, QSettings

from lib.git_helpers import (
    get_git_history, get_head_sha, get_current_branch, get_commit_diff,
    get_full_commit_message, get_commit_metadata, get_commit_files,
    has_uncommitted_changes
)
from lib.dialogs import (
    DiffHighlighter, DiffViewerDialog, SplitCommitDialog, ViewCommitDialog,
    DropDialog, RephraseDialog, SquashDialog, FileWiseViewDialog, MultiSquashDialog
)

class HelpDialog(QDialog):
    """Simple Help dialog with links to Video Demo, Readme, and Mail to Author."""

    YOUTUBE_URL = "https://www.youtube.com"  # Placeholder – update when demo video is ready
    README_URL = "https://github.com/shyjun/git_interactive_rebase.py/blob/master/README.md"
    MAILTO = "mailto:n.shyju@gmail.com"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help")
        self.setMinimumWidth(450)
        self.setModal(True)

        # Style the dialog to match the proposal
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
            btn.setStyleSheet("QPushButton { padding-left: 60px; }") # Space for icon

            # Create an icon label and overlay it or use layout
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

        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))
        
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


class CommitListWidget(QListWidget):
    """Subclassed QListWidget to handle Drag & Drop move confirmation."""
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.InternalMove)

    def dropEvent(self, event):
        old_row = self.currentRow()
        # CRITICAL: Capture the original SHA order BEFORE the drop modifies the list
        original_shas = [self.item(i).text().split()[0] for i in range(self.count())]
        super().dropEvent(event)
        new_row = self.currentRow()
        
        if old_row != new_row:
            item = self.item(new_row)
            sha = item.text().split()[0]
            
            # Ask for confirmation
            reply = QMessageBox.question(
                self, 
                "Confirm Move",
                f"Do you want to move commit <b>{sha}</b> to this new position?",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # Capture all SHAs in NEW list order (after drop)
                new_shas = [self.item(i).text().split()[0] for i in range(self.count())]
                # Pass BOTH old and new order to perform_move
                self.main_window.perform_move(new_shas, original_shas)
            else:
                # If No, reload the original history to undo the visual move
                self.main_window.load_history()

class GitHistoryApp(QMainWindow):
    def __init__(self, repo_path, commit_sha):
        super().__init__()
        self.repo_path = repo_path
        self.commit_sha = commit_sha
        self.start_time_head = get_head_sha(self.repo_path)
        self.best_commit_sha = None
        
        # Set global application icon
        icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "app_icon.png"))
        if os.path.exists(icon_path):
            QApplication.setWindowIcon(QIcon(icon_path))
        
        # Persistence
        self.settings = QSettings("shyjun", "GitInteractiveRebase")
        self.current_font_size = int(self.settings.value("font_size", 10))
        self.show_diffs = self.settings.value("show_diffs", False, type=bool)
        
        self.setWindowTitle(f"git_interactive_rebase.py : branch=..., HEAD=..., path={self.repo_path}") # Temporary name until load_history updates it
        self.resize(1100, 800)
        self.setMinimumWidth(1100)

        self.setup_ui()
        self.load_settings()
        self.load_history()

    def load_settings(self):
        """Loads persistent user settings like font size and theme."""
        # Font Size
        size = self.settings.value("font_size", 10, type=int)
        self.current_font_size = size
        self.update_font()
        
        # Theme
        theme = self.settings.value("theme", "light", type=str)
        if theme == "dark":
            self.dark_radio.setChecked(True)
        else:
            self.light_radio.setChecked(True)
        self.apply_theme(theme)

    def update_window_title(self):
        """Updates window title with branch, HEAD, and path."""
        branch = get_current_branch(self.repo_path)
        head_sha = get_head_sha(self.repo_path)
        title = f"git_interactive_rebase.py : branch={branch}, HEAD={head_sha}, path={self.repo_path}"
        self.setWindowTitle(title)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Use our custom list widget
        self.list_widget = CommitListWidget(self)
        self.update_font()
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        
        # Search / Filter Bar
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search commits (SHA or Message)...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMinimumHeight(35)
        self.search_edit.textChanged.connect(self.filter_commits)
        layout.addWidget(self.search_edit)

        # Main Splitter
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.list_widget.setMinimumWidth(150)
        self.main_splitter.addWidget(self.list_widget)
        
        # Right Side Panel
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Right Side Splitter (Vertical)
        self.right_splitter = QSplitter(Qt.Vertical)
        
        # Top half: Header + Message
        self.right_top_widget = QWidget()
        right_top_layout = QVBoxLayout(self.right_top_widget)
        right_top_layout.setContentsMargins(0, 0, 0, 0)
        
        self.side_commit_label = QLabel("Select a commit to view details")
        self.side_commit_label.setTextFormat(Qt.RichText)
        right_top_layout.addWidget(self.side_commit_label)
        
        self.side_commit_msg = QTextEdit()
        self.side_commit_msg.setReadOnly(True)
        right_top_layout.addWidget(self.side_commit_msg)
        
        self.right_splitter.addWidget(self.right_top_widget)

        # Bottom half: Diff
        self.side_diff_view = QTextEdit()
        self.side_diff_view.setReadOnly(True)
        self.right_splitter.addWidget(self.side_diff_view)
        
        # Add the vertical splitter to the right panel's layout
        right_layout.addWidget(self.right_splitter)
        
        # Set initial split sizes for top (message) and bottom (diff)
        self.right_splitter.setSizes([150, 650])
        
        self.right_panel.setMinimumWidth(150)
        
        self.right_panel.setVisible(self.show_diffs)
        
        self.main_splitter.addWidget(self.right_panel)
        # default split ratio: history 60%, diff 40%
        self.main_splitter.setSizes([600, 400])
        
        layout.addWidget(self.main_splitter)
        
        self.list_widget.itemDoubleClicked.connect(self.view_commit)
        self.list_widget.itemSelectionChanged.connect(self.update_side_diff)
        
        self.update_window_title()

        # Bottom Control Bar
        controls_layout = QHBoxLayout()
        
        self.zoom_in_btn = QPushButton("Zoom In (+)")
        self.zoom_out_btn = QPushButton("Zoom Out (-)")
        self.toggle_diff_btn = QPushButton("Hide/Show diffs")
        self.help_btn = QPushButton("Help")
        self.refresh_btn = QPushButton("Refresh")

        # Zoom group box
        zoom_group = QGroupBox("Zoom")
        zoom_group.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(self.zoom_in_btn)
        zoom_layout.addWidget(self.zoom_out_btn)
        zoom_group.setLayout(zoom_layout)

        # Theme controls
        theme_group = QGroupBox("Theme")
        theme_layout = QHBoxLayout()
        self.dark_radio = QRadioButton("Dark Theme")
        self.light_radio = QRadioButton("Light Theme")
        self.dark_radio.toggled.connect(lambda: self.on_theme_toggled())
        self.light_radio.toggled.connect(lambda: self.on_theme_toggled())
        theme_layout.addWidget(self.dark_radio)
        theme_layout.addWidget(self.light_radio)
        theme_group.setLayout(theme_layout)
        
        controls_layout.addWidget(zoom_group)
        controls_layout.addWidget(theme_group)
        controls_layout.addSpacing(20)

        self.exit_btn = QPushButton("Exit")
        self.failsafe_btn = QPushButton("")
        self.best_commit_btn = QPushButton("Reset Hard to BEST_COMMITID (Not Set)")
        self.best_commit_btn.setEnabled(False)
        self.custom_reset_btn = QPushButton("Enter commit id to reset hard to")
        
        for btn in [self.zoom_in_btn, self.zoom_out_btn, self.toggle_diff_btn, self.help_btn, self.refresh_btn, self.exit_btn]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)
        self.failsafe_btn.setMinimumHeight(40)
        self.best_commit_btn.setMinimumHeight(40)
        self.custom_reset_btn.setMinimumHeight(40)

        self.zoom_in_btn.clicked.connect(self.handle_zoom_in)
        self.zoom_out_btn.clicked.connect(self.handle_zoom_out)
        self.toggle_diff_btn.clicked.connect(self.toggle_side_diff_visibility)
        self.help_btn.clicked.connect(self._show_help_dialog)
        self.refresh_btn.clicked.connect(self.load_history)
        self.failsafe_btn.clicked.connect(self.handle_failsafe_reset)
        self.best_commit_btn.clicked.connect(self.handle_best_commit_reset)
        self.custom_reset_btn.clicked.connect(self.handle_custom_reset)
        self.exit_btn.clicked.connect(self.close)

        controls_layout.addWidget(self.toggle_diff_btn)
        controls_layout.addWidget(self.help_btn)
        controls_layout.addStretch()
        controls_layout.addWidget(self.refresh_btn)
        controls_layout.addWidget(self.exit_btn)
        
        layout.addLayout(controls_layout)
        
        # Add failsafe options as a distinct row below the other controls
        failsafe_group = QGroupBox("fail-safe")
        failsafe_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        failsafe_layout = QHBoxLayout()
        failsafe_layout.addWidget(self.failsafe_btn)
        failsafe_layout.addWidget(self.best_commit_btn)
        failsafe_layout.addWidget(self.custom_reset_btn)
        failsafe_group.setLayout(failsafe_layout)
        layout.addWidget(failsafe_group)

        # Merge/Squash multiple commits group
        self.multi_select_mode = False
        merge_group = QGroupBox("Merge/Squash multiple commits")
        merge_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        merge_layout = QHBoxLayout()
        self.multi_select_btn = QPushButton("Select multiple commits to merge")
        self.merge_selected_btn = QPushButton("Merge selected commits")
        self.cancel_multi_btn = QPushButton("Cancel multi selection")
        self.merge_selected_btn.setEnabled(False)
        self.cancel_multi_btn.setEnabled(False)
        for btn in [self.multi_select_btn, self.merge_selected_btn, self.cancel_multi_btn]:
            btn.setMinimumHeight(40)
        self.multi_select_btn.clicked.connect(self.enter_multi_select_mode)
        self.merge_selected_btn.clicked.connect(self.handle_merge_selected)
        self.cancel_multi_btn.clicked.connect(self.handle_cancel_multi_select)
        merge_layout.addWidget(self.multi_select_btn)
        merge_layout.addWidget(self.merge_selected_btn)
        merge_layout.addWidget(self.cancel_multi_btn)
        merge_group.setLayout(merge_layout)
        layout.addWidget(merge_group)

        # Keyboard Shortcuts
        self.slash_shortcut = QShortcut(QKeySequence("/"), self)
        self.slash_shortcut.activated.connect(self.handle_slash_shortcut)
        
        self.esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.esc_shortcut.activated.connect(self.handle_esc_shortcut)

    def update_side_diff(self):
        item = self.list_widget.currentItem()
        if not item:
            if hasattr(self, 'side_commit_label'):
                self.side_commit_label.setText("Select a commit to view details")
                self.side_commit_msg.clear()
            self.side_diff_view.clear()
            return
        sha = item.text().split()[0]
        try:
            meta = get_commit_metadata(self.repo_path, sha)
            msg = get_full_commit_message(self.repo_path, sha)
            diff_text = get_commit_diff(self.repo_path, sha)
            
            self.side_commit_label.setText(f"Commit: <b>{sha}</b>  <span style='color:gray;'>({meta})</span>")
            self.side_commit_msg.setPlainText(msg)
            self.side_diff_view.setPlainText(diff_text)
        except Exception as e:
            self.side_diff_view.setPlainText(f"Error loading diff: {e}")
            if hasattr(self, 'side_commit_msg'):
                self.side_commit_msg.clear()
                self.side_commit_label.setText("Error")

    def toggle_side_diff_visibility(self):
        new_visibility = not self.right_panel.isVisible()
        self.right_panel.setVisible(new_visibility)
        self.show_diffs = new_visibility
        self.settings.setValue("show_diffs", self.show_diffs)

    def _show_help_dialog(self):
        """Opens the Help dialog."""
        dialog = HelpDialog(self)
        dialog.exec()

    def handle_slash_shortcut(self):
        """Focus search bar when / is pressed."""
        if not self.search_edit.hasFocus():
            self.search_edit.setFocus()
            self.search_edit.selectAll()

    def handle_esc_shortcut(self):
        """Clear filter and focus when Esc is pressed."""
        if self.search_edit.text() or self.search_edit.hasFocus():
            self.search_edit.clear()
            self.search_edit.clearFocus()
            self.list_widget.setFocus()


    def filter_commits(self, text):
        """Live-filters the commits in the list based on search text."""
        search_term = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            # Match against SHA or Message
            item_text = item.text().lower()
            if search_term in item_text:
                item.setHidden(False)
            else:
                item.setHidden(True)

    def handle_set_best_commit(self, item):
        sha = item.text().split()[0]
        self.best_commit_sha = sha
        self.best_commit_btn.setText(f"Reset Hard to BEST_COMMITID ({sha[:8]})")
        self.best_commit_btn.setEnabled(True)

    def handle_best_commit_reset(self):
        if not self.best_commit_sha:
            return
        reply = QMessageBox.question(
            self, 
            "Confirm BEST_COMMITID Reset",
            f"Are you sure you want to <b>reset --hard</b> to BEST_COMMITID (<b>{self.best_commit_sha[:8]}</b>)?<br><br>"
            "This will discard all uncommitted changes and move your branch to this state.",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.perform_reset(self.best_commit_sha)

    def handle_failsafe_reset(self):
        reply = QMessageBox.question(
            self, 
            "Confirm Failsafe Reset",
            f"Are you sure you want to <b>reset --hard</b> to START_TIME_HEAD (<b>{self.start_time_head[:8]}</b>)?<br><br>"
            "This will discard all uncommitted changes and move your branch to this state.",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.perform_reset(self.start_time_head)

    def handle_custom_reset(self):
        commit_id, ok = QInputDialog.getText(self, 'Input Dialog', 'Enter commit ID to reset hard to:')
        if ok and commit_id.strip():
            sha = commit_id.strip()
            reply = QMessageBox.question(
                self, 
                "Confirm Custom Reset",
                f"Are you sure you want to <b>reset --hard</b> to <b>{sha}</b>?<br><br>"
                "This will discard all uncommitted changes and move your branch to this state.",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.perform_reset(sha)

    def handle_zoom_in(self):
        self.current_font_size += 1
        self.update_font()

    def handle_zoom_out(self):
        if self.current_font_size > 6:
            self.current_font_size -= 1
            self.update_font()

    def on_theme_toggled(self):
        theme = "dark" if self.dark_radio.isChecked() else "light"
        self.apply_theme(theme)
        self.settings.setValue("theme", theme)

    def apply_theme(self, theme_name):
        """Applies a theme to the entire application globally."""
        if theme_name == "dark":
            # VS Code Dark+ inspired palette
            self.current_theme_colors = {
                "added": "#4ec9b0",   # Soft teal/green
                "removed": "#f48771", # Soft coral/red
                "header": "#569cd6",  # VS Code blue
                "bg": "#1e1e1e",      # Main background
                "fg": "#cccccc",      # Standard text
                "accent": "#007acc"   # VS Code accent blue
            }
            qss = """
                QMainWindow, QWidget {
                    background-color: #1e1e1e;
                    color: #cccccc;
                }
                QListWidget {
                    background-color: #252526;
                    border: 1px solid #3c3c3c;
                    border-radius: 8px;
                    padding: 5px;
                    color: #cccccc;
                }
                QListWidget::item { 
                    padding: 8px; 
                    border-bottom: 1px solid #333333; 
                }
                QListWidget::item:selected {
                    background-color: #37373d;
                    color: #ffffff;
                }
                QGroupBox {
                    border: 1px solid #3c3c3c;
                    border-radius: 5px;
                    margin-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    background-color: #333333;
                    color: #cccccc;
                    border: 1px solid #3c3c3c;
                    padding: 8px 15px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #444444;
                }
                QPushButton:pressed {
                    background-color: #007acc;
                    color: white;
                }
                QPushButton.dialog-btn {
                    background-color: #333333;
                    border: 1px solid #444444;
                }
                QPushButton.dialog-btn:hover {
                    background-color: #007acc;
                    color: white;
                }
                QLabel {
                    font-weight: bold;
                }
                QDialog {
                    background-color: #1e1e1e;
                }
                QTextEdit {
                    background-color: #1e1e1e;
                    color: #d4d4d4;
                    border: 1px solid #3c3c3c;
                    border-radius: 4px;
                }
                QScrollBar:vertical {
                    background: #1e1e1e;
                    width: 12px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background: #37373d;
                    min-height: 20px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #4f4f4f;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """
        else:
            self.current_theme_colors = {
                "added": "#228b22",  # Darker green for light bg
                "removed": "#b22222", # Darker red for light bg
                "header": "#00008b", # Darker blue for light bg
                "bg": "#f5f5f7",
                "fg": "#333333",
                "accent": "#007aff"
            }
            qss = """
                QMainWindow, QWidget {
                    background-color: #f5f5f7;
                    color: #333;
                }
                QListWidget {
                    background-color: #ffffff;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    padding: 5px;
                    color: #333;
                }
                QListWidget::item { 
                    padding: 8px; 
                    border-bottom: 1px solid #eee; 
                }
                QListWidget::item:selected {
                    background-color: #007aff;
                    color: white;
                }
                QGroupBox {
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    margin-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 3px 0 3px;
                }
                QPushButton {
                    background-color: #ffffff;
                    color: #333;
                    border: 1px solid #ccc;
                    padding: 8px 15px;
                    border-radius: 5px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #f0f0f0;
                }
                QPushButton:pressed {
                    background-color: #d0d0d0;
                }
                QPushButton.dialog-btn {
                    background-color: #e1e1e1;
                    border: 1px solid #bbb;
                }
                QPushButton.dialog-btn:hover {
                    background-color: #007aff;
                    color: white;
                }
                QLabel {
                    font-weight: bold;
                    color: #333;
                }
                QDialog {
                    background-color: #f5f5f7;
                }
                QTextEdit {
                    background-color: #ffffff;
                    color: #333;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                }
                QScrollBar:vertical {
                    background: #f5f5f7;
                    width: 12px;
                    margin: 0px;
                }
                QScrollBar::handle:vertical {
                    background: #ccc;
                    min-height: 20px;
                    border-radius: 6px;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """
        
        QApplication.instance().setStyleSheet(qss)
        
        # Update highlighter colors according to the theme
        if hasattr(self, 'side_diff_view'):
            if hasattr(self, 'side_highlighter') and self.side_highlighter is not None:
                self.side_highlighter.setDocument(None)
            self.side_highlighter = DiffHighlighter(
                self.side_diff_view.document(),
                added_color=self.current_theme_colors["added"],
                removed_color=self.current_theme_colors["removed"],
                header_color=self.current_theme_colors["header"]
            )
        
    def update_font(self):
        font = QFont("Monospace", self.current_font_size)
        self.list_widget.setFont(font)
        if hasattr(self, 'side_diff_view'):
            self.side_diff_view.setFont(font)
        if hasattr(self, 'side_commit_msg'):
            self.side_commit_msg.setFont(font)
        # Save persistence
        self.settings.setValue("font_size", self.current_font_size)

    def show_context_menu(self, position):
        if self.multi_select_mode:
            QMessageBox.warning(
                self,
                "Not Available",
                "Right-click options are not available in multi-select mode.\n\n"
                "Please finish or cancel the current selection first."
            )
            return

        item = self.list_widget.itemAt(position)
        if not item:
            return
            
        sha = item.text().split()[0]
        menu = QMenu()
        
        view_action = QAction(f"Show / View commit {sha}", self)
        move_action = QAction("Move (Drag item to reorder)", self)
        reset_action = QAction(f"Reset Hard to {sha}", self)
        set_best_action = QAction("set as BEST_COMMITID", self)
        drop_action = QAction("Drop", self)
        select_multi_merge_action = QAction("Select multiple commits to merge", self)
        rephrase_action = QAction("Rephrase", self)
        
        # Clipboard items
        copy_sha_action = QAction("Copy SHA to clipboard", self)
        copy_msg_action = QAction("Copy commit msg to clipboard", self)
        copy_sha_msg_action = QAction("Copy SHA and commit msg to clipboard", self)
        
        # Squash items
        index = self.list_widget.row(item)
        count = self.list_widget.count()
        
        def format_squash_label(neighbor_item):
            parts = neighbor_item.text().split(maxsplit=1)
            n_sha = parts[0]
            return f"{n_sha}"

        squash_above_action = None
        if index > 0:
            above_item = self.list_widget.item(index - 1)
            label = f"squash/merge with above commit ({format_squash_label(above_item)})"
            squash_above_action = QAction(label, self)
            squash_above_action.triggered.connect(lambda: self.handle_squash_above(item))
        else:
            squash_above_action = QAction("squash/merge with above commit (N/A)", self)
            squash_above_action.setEnabled(False)

        squash_below_action = None
        if index < count - 1:
            below_item = self.list_widget.item(index + 1)
            label = f"squash/merge with below commit ({format_squash_label(below_item)})"
            squash_below_action = QAction(label, self)
            squash_below_action.triggered.connect(lambda: self.handle_squash_below(item))
        else:
            squash_below_action = QAction("squash/merge with below commit (N/A)", self)
            squash_below_action.setEnabled(False)

        view_action.triggered.connect(lambda: self.view_commit(item))
        view_filewise_action = QAction(f"Show / View commit {sha} -- file-wise", self)
        view_filewise_action.triggered.connect(lambda: self.handle_view_commit_file_wise(item))
        # Move action is primarily via drag and drop, but we can make it focus the item
        move_action.triggered.connect(lambda: self.list_widget.setCurrentItem(item))
        reset_action.triggered.connect(lambda: self.handle_reset(item))
        set_best_action.triggered.connect(lambda: self.handle_set_best_commit(item))
        drop_action.triggered.connect(lambda: self.handle_drop(item))
        select_multi_merge_action.triggered.connect(self.enter_multi_select_mode)
        rephrase_action.triggered.connect(lambda: self.handle_rephrase(item))
        copy_sha_action.triggered.connect(lambda: self.handle_copy_sha(item))
        copy_msg_action.triggered.connect(lambda: self.handle_copy_message(item))
        copy_sha_msg_action.triggered.connect(lambda: self.handle_copy_sha_and_message(item))
        
        menu.addAction(view_action)
        menu.addAction(view_filewise_action)
        menu.addSeparator()
        menu.addAction(reset_action)
        menu.addAction(set_best_action)
        menu.addSeparator()
        menu.addAction(drop_action)
        menu.addAction(select_multi_merge_action)
        menu.addAction(rephrase_action)
        menu.addAction(move_action)
        
        # Split Commit submenu
        split_menu = menu.addMenu("Split Commit")
        split_move_out_action = QAction("move one file changes out of this commit", self)
        split_move_out_action.triggered.connect(lambda: self.handle_split_commit(item))
        split_menu.addAction(split_move_out_action)
        
        split_all_action = QAction("split all changes to separate commits", self)
        split_all_action.triggered.connect(lambda: self.handle_split_all_commits(item))
        split_menu.addAction(split_all_action)
        
        menu.addSeparator()
        menu.addAction(copy_sha_action)
        menu.addAction(copy_msg_action)
        menu.addAction(copy_sha_msg_action)
        menu.addSeparator()
        menu.addAction(squash_above_action)
        menu.addAction(squash_below_action)
        menu.exec(self.list_widget.mapToGlobal(position))

    def handle_rephrase(self, item):
        """Handles the rephrase action."""
        sha = item.text().split()[0]
        print(f"Preparing to rephrase {sha}...")
        try:
            current_message = get_full_commit_message(self.repo_path, sha)
            dialog = RephraseDialog(sha, current_message, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                new_message = dialog.get_message()
                if new_message != current_message:
                    self.perform_rephrase(sha, new_message)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch commit message: {str(e)}")

    def perform_rephrase(self, sha, new_message):
        """Executes the rephrase using unified rebase logic."""
        try:
            # Current list of SHAs in UI
            current_shas = []
            for i in range(self.list_widget.count()):
                current_shas.append(self.list_widget.item(i).text().split()[0])
            
            if self.run_interactive_rebase(current_shas, rephrase_map={sha: new_message}):
                print(f"Rephrased {sha}.")
                QMessageBox.information(self, "Success", f"Commit {sha} rephrased successfully.")
            
            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while rephrasing: {str(e)}")
            self.load_history()

    def handle_copy_sha(self, item):
        sha = item.text().split()[0]
        print(f"Copying SHA {sha} to clipboard...")
        QApplication.clipboard().setText(sha)
        QMessageBox.information(self, "Copied", f"Copied {sha} to clipboard.")

    def handle_copy_message(self, item):
        sha = item.text().split()[0]
        print(f"Copying message of {sha} to clipboard...")
        try:
            msg = get_full_commit_message(self.repo_path, sha)
            QApplication.clipboard().setText(msg)
            QMessageBox.information(self, "Copied", f"Copied commit message of {sha} to clipboard.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch message: {str(e)}")

    def handle_copy_sha_and_message(self, item):
        sha = item.text().split()[0]
        print(f"Copying SHA and message of {sha} to clipboard...")
        try:
            msg = get_full_commit_message(self.repo_path, sha)
            combined = f"{sha} {msg}"
            QApplication.clipboard().setText(combined)
            QMessageBox.information(self, "Copied", f"Copied SHA and commit message of {sha} to clipboard.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch message: {str(e)}")

    def view_commit(self, item):
        """Helper to open the diff viewer for a commit item."""
        if not item:
            return
        sha = item.text().split()[0]
        print(f"Viewing {sha}...")
        try:
            diff_text = get_commit_diff(self.repo_path, sha)
            commit_msg = get_full_commit_message(self.repo_path, sha)
            commit_meta = get_commit_metadata(self.repo_path, sha)
            dialog = ViewCommitDialog(sha, commit_msg, commit_meta, diff_text, self.current_font_size, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch commit diff: {str(e)}")

    def handle_view_commit_file_wise(self, item):
        if not item:
            return
        sha = item.text().split()[0]
        try:
            files = get_commit_files(self.repo_path, sha)
            if not files:
                QMessageBox.information(self, "No Files", f"Commit {sha} has no file changes to view.")
                return
            dialog = FileWiseViewDialog(self.repo_path, sha, files, self.current_font_size, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open file-wise view: {str(e)}")

    def handle_reset(self, item):
        sha = item.text().split()[0]
        reply = QMessageBox.question(
            self, 
            "Confirm Reset Hard",
            f"Are you sure you want to <b>reset --hard</b> to commit <b>{sha}</b>?<br><br>"
            "This will discard all uncommitted changes and move your branch to this state.",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.perform_reset(sha)

    def perform_reset(self, sha):
        print(f"Resetting hard to {sha}...")
        try:
            cmd = ["git", "reset", "--hard", sha]
            subprocess.run(cmd, cwd=self.repo_path, check=True, capture_output=True, text=True)
            QMessageBox.information(self, "Success", f"Successfully reset --hard to {sha}.")
            self.load_history()
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Reset Failed", f"Could not perform reset.\n\nError: {e.stderr}")

    def handle_squash_above(self, item):
        """Squashes the current commit with the one above it (newer)."""
        index = self.list_widget.row(item)
        if index <= 0: return
        
        above_item = self.list_widget.item(index - 1)
        sha_above = above_item.text().split()[0]
        sha_current = item.text().split()[0]
        
        try:
            msg_above = get_full_commit_message(self.repo_path, sha_above)
            msg_current = get_full_commit_message(self.repo_path, sha_current)
            
            dialog = SquashDialog(sha_above, msg_above, sha_current, msg_current, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                final_msg = dialog.get_message()
                print(f"Preparing to squash {sha_above} into {sha_current}...")
                self.perform_squash(sha_above, final_msg)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not prepare squash: {str(e)}")

    def handle_squash_below(self, item):
        """Squashes the current commit with the one below it (older)."""
        index = self.list_widget.row(item)
        if index >= self.list_widget.count() - 1: return
        
        sha_current = item.text().split()[0]
        below_item = self.list_widget.item(index + 1)
        sha_below = below_item.text().split()[0]
        
        try:
            msg_current = get_full_commit_message(self.repo_path, sha_current)
            msg_below = get_full_commit_message(self.repo_path, sha_below)
            
            dialog = SquashDialog(sha_current, msg_current, sha_below, msg_below, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                final_msg = dialog.get_message()
                print(f"Preparing to squash {sha_current} into {sha_below}...")
                self.perform_squash(sha_current, final_msg)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not prepare squash: {str(e)}")

    def perform_squash(self, sha_to_squash, final_msg):
        """Executes the squash using unified rebase logic."""
        try:
            # Current list of SHAs in UI
            current_shas = []
            for i in range(self.list_widget.count()):
                current_shas.append(self.list_widget.item(i).text().split()[0])
            
            # Use final_msg for the rebase - we associate it with the SHA being squashed
            # so the amend happens right after the squash command in the todo list.
            if self.run_interactive_rebase(current_shas, squash_shas=[sha_to_squash], 
                                          rephrase_map={sha_to_squash: final_msg}):
                print(f"Squashed {sha_to_squash}.")
                QMessageBox.information(self, "Success", "Commits squashed successfully.")
            
            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while squashing: {str(e)}")
            self.load_history()

    # ---- Multi-select / Merge mode ----

    def enter_multi_select_mode(self):
        """Enters checkbox multi-select mode on the commit list."""
        self.multi_select_mode = True
        # Block signals to prevent spurious itemChanged during setup
        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
        self.list_widget.blockSignals(False)
        self.list_widget.itemChanged.connect(self.on_multi_select_changed)
        self.multi_select_btn.setEnabled(False)
        self.merge_selected_btn.setEnabled(False)
        self.cancel_multi_btn.setEnabled(True)

    def exit_multi_select_mode(self):
        """Exits checkbox multi-select mode and restores normal list behaviour."""
        self.multi_select_mode = False
        try:
            self.list_widget.itemChanged.disconnect(self.on_multi_select_changed)
        except Exception: # Widened exception catch
            pass
        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            item.setData(Qt.CheckStateRole, None)
        self.list_widget.blockSignals(False)
        self.multi_select_btn.setEnabled(True)
        self.merge_selected_btn.setEnabled(False)
        self.cancel_multi_btn.setEnabled(False)

    def on_multi_select_changed(self, changed_item):
        """Enables 'Merge selected commits' only when ≥ 2 commits are checked."""
        if not self.multi_select_mode:
            return
        checked_count = sum(
            1 for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == Qt.Checked
        )
        self.merge_selected_btn.setEnabled(checked_count >= 2)

    def handle_cancel_multi_select(self):
        """Cancels multi-select mode without merging."""
        self.exit_multi_select_mode()

    def handle_merge_selected(self):
        """Collects checked commits, validates contiguity, confirms, then squashes."""
        # Collect selected indices and SHAs in list order (newest → oldest)
        selected_indices = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                selected_indices.append(i)

        if len(selected_indices) < 2:
            QMessageBox.warning(self, "Not Enough Selected", "Please select at least 2 commits to merge.")
            return

        # Contiguity check
        for k in range(len(selected_indices) - 1):
            if selected_indices[k + 1] != selected_indices[k] + 1:
                QMessageBox.critical(
                    self, "Non-Adjacent Commits",
                    "Selected commits must be adjacent (contiguous) in the log.\n\n"
                    "Please select only neighbouring commits."
                )
                return

        selected_shas = [self.list_widget.item(i).text().split()[0] for i in selected_indices]

        self.perform_multi_squash(selected_shas)

    def perform_multi_squash(self, selected_shas):
        """Squashes multiple adjacent commits into the topmost selected commit."""
        try:
            # Collect (sha, message) pairs preserving order
            sha_msg_pairs = [(sha, get_full_commit_message(self.repo_path, sha)) for sha in selected_shas]

            # The top item (index 0 = newest in list) is the "pick" target; rest become squash
            base_sha = selected_shas[0]
            squash_shas = selected_shas[1:]

            # Open the N-option message selection dialog directly
            dialog = MultiSquashDialog(sha_msg_pairs, self.current_font_size, self)
            if dialog.exec() != QDialog.Accepted:
                return  # finally block handles cleanup

            final_msg = dialog.get_message()

            # Build all SHAs list from current view
            all_shas = [self.list_widget.item(i).text().split()[0] for i in range(self.list_widget.count())]

            if self.run_interactive_rebase(all_shas, squash_shas=squash_shas, rephrase_map={base_sha: final_msg}):
                QMessageBox.information(self, "Success", f"Successfully squashed {len(selected_shas)} commits.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while merging: {str(e)}")
        finally:
            self.exit_multi_select_mode()
            self.load_history()

    def handle_drop(self, item):

        sha = item.text().split()[0]
        print(f"Preparing to drop {sha}...")
        try:
            diff_text = get_commit_diff(self.repo_path, sha)
            dialog = DropDialog(sha, diff_text, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                self.perform_drop(sha)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def perform_drop(self, sha):
        """Drops a commit using our unified rebase logic."""
        try:
            # Current list of SHAs in UI
            current_shas = []
            for i in range(self.list_widget.count()):
                current_shas.append(self.list_widget.item(i).text().split()[0])
            
            # New list without the dropped SHA
            new_shas = [s for s in current_shas if s != sha]
            
            if self.run_interactive_rebase(new_shas):
                print(f"Dropped {sha}.")
                QMessageBox.information(self, "Success", f"Commit {sha} dropped successfully.")
            
            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while dropping: {str(e)}")
            self.load_history()

    def handle_split_commit(self, item):
        """Opens SplitCommitDialog to allow moving a file out of a commit."""
        sha = item.text().split()[0]
        try:
            files = get_commit_files(self.repo_path, sha)
            if not files:
                QMessageBox.information(self, "No Files", f"Commit {sha} has no file changes to split.")
                return
            if len(files) == 1:
                QMessageBox.warning(self, "Warning", "This commit has changes only in 1 file.")
                return
                
            dialog = SplitCommitDialog(self.repo_path, sha, files, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                selected_file = dialog.get_selected_file()
                if selected_file:
                    self.perform_move_file_out(sha, selected_file)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open split dialog: {str(e)}")

    def perform_move_file_out(self, sha, filepath):
        """
        Moves a single file's changes out of a commit into a new commit after it.
        """
        try:
            all_files = get_commit_files(self.repo_path, sha)
            other_files = [f for f in all_files if f != filepath]
            short_sha = sha[:8]

            if not other_files:
                QMessageBox.information(self, "Info", f"File '{filepath}' is the only modified file in this commit. Nothing to split.")
                return

            def sq(s):
                return "'" + s.replace("'", "'\\''") + "'"

            exec_cmds = []
            exec_cmds.append("git reset --soft HEAD~1")
            exec_cmds.append(f"git reset HEAD -- {sq(filepath)}")
            exec_cmds.append(f"git commit -C {sha}")
            exec_cmds.append(f"git add --all -- {sq(filepath)}")
            new_msg = f"{filepath} changes moved out of below commit"
            exec_cmds.append(f"git commit -m {sq(new_msg)}")

            single_exec = "exec " + " && ".join(exec_cmds)

            current_shas = [self.list_widget.item(i).text().split()[0]
                            for i in range(self.list_widget.count())]

            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
                f.write("#!/usr/bin/env python3\n")
                f.write("import sys\n")
                f.write(f"target_sha = {repr(sha)}\n")
                f.write(f"single_exec = {repr(single_exec)}\n")
                f.write("todo_path = sys.argv[1]\n")
                f.write("with open(todo_path, 'r') as tf:\n")
                f.write("    lines = tf.readlines()\n")
                f.write("output = []\n")
                f.write("for line in lines:\n")
                f.write("    output.append(line)\n")
                f.write("    stripped = line.strip()\n")
                f.write("    if not stripped.startswith('#') and len(stripped.split()) >= 2 and stripped.split()[1].startswith(target_sha):\n")
                f.write("        output.append(single_exec + '\\n')\n")
                f.write("with open(todo_path, 'w') as tf:\n")
                f.write("    tf.writelines(output)\n")
                editor_script = f.name

            os.chmod(editor_script, os.stat(editor_script).st_mode | stat.S_IEXEC)

            sha_idx = current_shas.index(sha) if sha in current_shas else -1
            if sha_idx == len(current_shas) - 1:
                has_parent = False
                try:
                    subprocess.run(["git", "rev-parse", f"{sha}^"],
                                   cwd=self.repo_path, check=True, capture_output=True)
                    has_parent = True
                except Exception:
                    pass
                upstream = f"{sha}^" if has_parent else "--root"
            else:
                upstream = current_shas[sha_idx + 1]

            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = editor_script
            env["GIT_EDITOR"] = "true"

            if upstream == "--root":
                cmd = ["git", "rebase", "-i", "--root"]
            else:
                cmd = ["git", "rebase", "-i", upstream]

            result = subprocess.run(cmd, cwd=self.repo_path, env=env,
                                    capture_output=True, text=True)
            os.unlink(editor_script)

            if result.returncode == 0:
                QMessageBox.information(self, "Success",
                    f"File '{filepath}' has been moved out of commit {short_sha}.\n\n"
                    f"A new commit was created: \"{new_msg}\"")
            else:
                subprocess.run(["git", "rebase", "--abort"],
                               cwd=self.repo_path, capture_output=True)
                QMessageBox.critical(self, "Split Failed",
                    f"The split operation failed and has been aborted.\n\n"
                    f"Error: {result.stderr}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
        finally:
            self.load_history()

    def handle_split_all_commits(self, item):
        sha = item.text().split()[0]
        try:
            files = get_commit_files(self.repo_path, sha)
            if len(files) != 1:
                QMessageBox.critical(self, "Error", "This feature is only applicable if changes are in 1 single file")
                return
            self.perform_split_all_commits(sha, files[0])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not check commit files: {str(e)}")

    def perform_split_all_commits(self, sha, filepath):
        try:
            short_sha = sha[:8]
            
            # The script will be executed when the sequence editor sees 'exec python3 <script>'
            split_script_content = f"""#!/usr/bin/env python3
import sys, subprocess, os

target_sha = {repr(sha)}
filepath = {repr(filepath)}

# 1. Get the diff of the file in the commit
diff_text = subprocess.check_output(['git', 'log', '-p', '-1', target_sha, '--', filepath]).decode('utf-8')

# 2. Parse into header and hunks
lines = diff_text.split('\\n')
header = []
hunks = []
current_hunk = []
in_diff = False
in_hunks = False

for line in lines:
    if line.startswith('diff --git'):
        in_diff = True
        header = [line]
    elif in_diff and (line.startswith('index ') or line.startswith('--- ') or line.startswith('+++ ')):
        header.append(line)
    elif in_diff and line.startswith('@@'):
        in_hunks = True
        if current_hunk:
            hunks.append(current_hunk)
        current_hunk = [line]
    elif in_hunks:
        current_hunk.append(line)

if current_hunk:
    hunks.append(current_hunk)

if not hunks:
    print("No textual hunks found to split.")
    sys.exit(0)

# 3. Reset the working tree & index to parent commit state
subprocess.check_call(['git', 'reset', '--hard', 'HEAD~1'])

# 4. Apply each hunk as a separate patch and commit
for i, hunk in enumerate(hunks):
    patch_content = '\\n'.join(header) + '\\n' + '\\n'.join(hunk) + '\\n'
    with open('temp.patch', 'w', encoding='utf-8') as f:
        f.write(patch_content)
    
    # Apply patch. --no-backup-if-mismatch ignores minor offset issues.
    subprocess.check_call(['patch', '-p1', '-i', 'temp.patch', '--no-backup-if-mismatch'])
    subprocess.check_call(['git', 'add', filepath])
    subprocess.check_call(['git', 'commit', '-m', f'change-{{i+1}} of {{target_sha[:8]}}'])

if os.path.exists('temp.patch'):
    os.unlink('temp.patch')
"""
            
            # Write the action script
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py', encoding='utf-8') as sf:
                sf.write(split_script_content)
                split_action_script = sf.name
            os.chmod(split_action_script, os.stat(split_action_script).st_mode | stat.S_IEXEC)

            single_exec = f"exec python3 {split_action_script}"

            current_shas = [self.list_widget.item(i).text().split()[0] for i in range(self.list_widget.count())]

            # Write the sequence editor script
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py', encoding='utf-8') as f:
                f.write("#!/usr/bin/env python3\n")
                f.write("import sys\n")
                f.write(f"target_sha = {repr(sha)}\n")
                f.write(f"single_exec = {repr(single_exec)}\n")
                f.write("todo_path = sys.argv[1]\n")
                f.write("with open(todo_path, 'r') as tf:\n")
                f.write("    lines = tf.readlines()\n")
                f.write("output = []\n")
                f.write("for line in lines:\n")
                f.write("    stripped = line.strip()\n")
                f.write("    if not stripped.startswith('#') and len(stripped.split()) >= 2 and stripped.split()[1].startswith(target_sha):\n")
                f.write("        # Replace the 'pick' line with our exec script completely.\n")
                f.write("        output.append(single_exec + '\\n')\n")
                f.write("    else:\n")
                f.write("        output.append(line)\n")
                f.write("with open(todo_path, 'w') as tf:\n")
                f.write("    tf.writelines(output)\n")
                editor_script = f.name
            os.chmod(editor_script, os.stat(editor_script).st_mode | stat.S_IEXEC)

            # Upstream logic
            sha_idx = current_shas.index(sha) if sha in current_shas else -1
            if sha_idx == len(current_shas) - 1:
                has_parent = False
                try:
                    subprocess.run(["git", "rev-parse", f"{sha}^"], cwd=self.repo_path, check=True, capture_output=True)
                    has_parent = True
                except Exception:
                    pass
                upstream = f"{sha}^" if has_parent else "--root"
            else:
                upstream = current_shas[sha_idx + 1]

            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = editor_script
            env["GIT_EDITOR"] = "true"

            cmd = ["git", "rebase", "-i", upstream] if upstream != "--root" else ["git", "rebase", "-i", "--root"]

            result = subprocess.run(cmd, cwd=self.repo_path, env=env, capture_output=True, text=True)
            
            try:
                os.unlink(editor_script)
                os.unlink(split_action_script)
            except:
                pass

            if result.returncode == 0:
                QMessageBox.information(self, "Success",
                    f"Commit {short_sha} has been split into multiple commits for file '{filepath}'.")
            else:
                subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, capture_output=True)
                QMessageBox.critical(self, "Split Failed",
                    f"The split operation failed and has been aborted.\n\nError: {result.stderr}\nOutput: {result.stdout}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
        finally:
            self.load_history()

    def perform_move(self, new_shas, original_shas=None):
        """Performs commit reordering using our unified rebase logic."""
        print("Performing commit reorder...")
        if self.run_interactive_rebase(new_shas, original_shas=original_shas):
            QMessageBox.information(self, "Success", "Commits reordered successfully!")
        self.load_history()

    def run_interactive_rebase(self, new_shas, rephrase_map=None, squash_shas=None, original_shas=None):
        """
        Unified handler for history rewriting using git rebase -i.
        original_shas: The pre-change SHA order (latest-first). If provided, used
                       for prefix comparison instead of reading list_widget (which
                       may already show the new order after a drag-drop).
        """
        print("Executing optimized rebase...")
        try:
            # 1. Determine common prefix to minimize work
            # Use the explicitly passed original order when available (e.g., after a drag)
            if original_shas is not None:
                display_shas = original_shas
            else:
                display_shas = [self.list_widget.item(i).text().split()[0] for i in range(self.list_widget.count())]
            old_order = list(reversed(display_shas))
            proposed_order = list(reversed(new_shas))
            
            common_count = 0
            for old, new in zip(old_order, proposed_order):
                # A commit is only "common" if it's the same SHA AND not being modified
                if old == new and (not rephrase_map or old not in rephrase_map) and (not squash_shas or old not in squash_shas):
                    common_count += 1
                else:
                    break
            
            # Determine upstream and suffix to re-process
            if common_count > 0:
                upstream = old_order[common_count - 1]
                todo_shas = proposed_order[common_count:]
                
                # SQUASH FIX: If the first commit to reprocess is a squash,
                # we MUST include at least one commit before it (the pick target)
                if todo_shas and squash_shas and todo_shas[0] in squash_shas:
                    if common_count > 1:
                        common_count -= 1
                        upstream = old_order[common_count - 1]
                        todo_shas = proposed_order[common_count:]
                    else:
                        # We are squashing into the very first commit of our visible range
                        common_count = 0 # Fall back to full rebase logic below
            
            if common_count == 0:
                # Check root status
                has_parent = False
                try:
                    subprocess.run(["git", "rev-parse", f"{self.commit_sha}^"], 
                                   cwd=self.repo_path, check=True, capture_output=True)
                    has_parent = True
                except:
                    has_parent = False
                upstream = f"{self.commit_sha}^" if has_parent else "--root"
                todo_shas = proposed_order

            # Feature: Fast-track top-drops (reset --hard)
            if not todo_shas and common_count > 0:
                print(f"Fast-tracking drop via reset --hard to {upstream}")
                subprocess.run(["git", "reset", "--hard", upstream], cwd=self.repo_path, check=True)
                return True

            # 2. Proceed with rebase for non-trivial changes
            # Write each rephrase message to a temp file to handle multi-line messages safely
            msg_files = {}  # sha -> temp file path
            if rephrase_map:
                for sha, msg in rephrase_map.items():
                    if sha in todo_shas:
                        mf = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
                        mf.write(msg)
                        mf.close()
                        msg_files[sha] = mf.name

            # Build a sequence editor script that writes the rebase todo
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
                f.write("#!/usr/bin/env python3\n")
                f.write("import sys\n")
                f.write(f"new_order = {todo_shas}\n")
                f.write(f"msg_files = {repr(msg_files)}\n")
                f.write(f"squash_shas = {squash_shas or []}\n")
                f.write("todo_path = sys.argv[1]\n")
                f.write("with open(todo_path, 'w') as f:\n")
                f.write("    for sha in new_order:\n")
                f.write("        op = 'squash' if sha in squash_shas else 'pick'\n")
                f.write("        f.write(f'{op} {sha}\\n')\n")
                f.write("        if sha in msg_files:\n")
                f.write("            mf = msg_files[sha]\n")
                f.write("            f.write(f'exec git commit --amend -F {mf}\\n')\n")
                editor_script = f.name

            os.chmod(editor_script, os.stat(editor_script).st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = editor_script
            env["GIT_EDITOR"] = "true"

            if upstream == "--root":
                cmd = ["git", "rebase", "-i", "--autosquash", "--root"]
            else:
                cmd = ["git", "rebase", "-i", "--autosquash", upstream]

            result = subprocess.run(cmd, cwd=self.repo_path, env=env, capture_output=True, text=True)
            os.unlink(editor_script)
            # Clean up message temp files
            for mf_path in msg_files.values():
                try:
                    os.unlink(mf_path)
                except Exception:
                    pass

            if result.returncode == 0:
                # Update bottom anchor SHA
                if new_shas:
                    self.commit_sha = new_shas[-1]
                return True
            else:
                subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, capture_output=True)
                QMessageBox.critical(self, "Rebase Failed",
                    f"Action failed (likely due to merge conflicts).\n"
                    f"The rebase has been aborted.\n\nError: {result.stderr}")
                return False

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred during rebase: {str(e)}")
            return False



    def load_history(self):
        """Fetches git history and populates the list widget."""
        # Clear search when reloading history
        if hasattr(self, 'search_edit'):
            self.search_edit.blockSignals(True)
            self.search_edit.clear()
            self.search_edit.blockSignals(False)

        print("Refreshing...")
        self.update_window_title()
        self.list_widget.clear()
        try:
            history = get_git_history(self.repo_path, self.commit_sha)
            for line in history:
                self.list_widget.addItem(line)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            
        # Update Failsafe button state
        current_head = get_head_sha(self.repo_path)
        uncommitted = has_uncommitted_changes(self.repo_path)
        if current_head == self.start_time_head[:8] and not uncommitted:
            self.failsafe_btn.setEnabled(False)
            self.failsafe_btn.setText(f"Reset Hard to START_TIME_HEAD (Already at {self.start_time_head[:8]})")
        else:
            self.failsafe_btn.setEnabled(True)
            self.failsafe_btn.setText(f"⚠ Reset Hard to START_TIME_HEAD ({self.start_time_head[:8]}) ⚠")
