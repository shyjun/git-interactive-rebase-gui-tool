
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

import subprocess
import os
import webbrowser
import tempfile
import stat
import time

# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QListWidget, QVBoxLayout,
    QWidget, QMessageBox, QListWidgetItem, QMenu, QDialog,
    QTextEdit, QPlainTextEdit, QPushButton, QHBoxLayout, QLabel, QRadioButton,
    QLineEdit, QSplitter, QInputDialog, QGroupBox, QSizePolicy, QCheckBox,
    QStyledItemDelegate, QStyle, QStyleOptionViewItem, QTabWidget, QWidgetAction,
    QStatusBar
)
# pyrefly: ignore [missing-import]
from PySide6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor, QAction, QShortcut, QKeySequence, QIcon, QBrush, QPainter, QPainterPath, QPen, QPixmap, QPalette
# pyrefly: ignore [missing-import]
from PySide6.QtCore import Qt, QSize, QSettings, QThread, Signal, QRect, QTimer, Slot

from lib.git_helpers import (
    get_git_history, get_head_sha, get_full_head_sha, get_current_branch, get_commit_diff,
    get_full_commit_message, get_commit_metadata, get_commit_files,
    has_uncommitted_changes, branch_exists, get_local_branches_map, get_remote_head_sha,
    get_file_diff_only_in_commit, get_revert_commit_message, get_commit_metadata_and_message,
    get_commit_file_stats,     get_unstaged_files, stash_changes, commit_file, bulk_commit_all, amend_with_head
)
from lib.dialogs import (
    DiffHighlighter, DiffViewerDialog, SplitCommitDialog, ViewCommitDialog,
    DropDialog, RephraseDialog, RevertCommitDialog, SquashDialog, FileWiseViewDialog,
    MultiSquashDialog, ProgressDialog, DropFileFromCommitDialog, ConfirmDropFileDialog,
    ConfirmMoveFileDialog, ConfirmRemoveFileOnwardsDialog, AggressiveRemoveConfirmationDialog,
    RefineFileSelectDialog, RefineChangesDialog, NewCommitMessageDialog,
    DiffView, StatsItemDelegate, DiffSearchBar, UnstagedChangesDialog
)
from lib.utils import get_assets_path

class GitWorker(QThread):
    """Generic worker for running git commands in a separate thread."""
    finished = Signal(bool, str, str)  # (success, stdout, stderr)

    def __init__(self, command, cwd):
        super().__init__()
        self.command = command
        self.cwd = cwd

    def run(self):
        try:
            result = subprocess.run(self.command, cwd=self.cwd, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
            self.finished.emit(True, result.stdout, "")
        except subprocess.CalledProcessError as e:
            self.finished.emit(False, "", e.stderr)
        except Exception as e:
            self.finished.emit(False, "", str(e))


class SplitWorker(QThread):
    """Worker for running the split rebase in a background thread. Emits (returncode, stdout, stderr)."""
    finished = Signal(int, str, str)

    def __init__(self, cmd, cwd, env=None):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd
        self.env = env

    def run(self):
        try:
            result = subprocess.run(self.cmd, cwd=self.cwd, env=self.env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.finished.emit(result.returncode, result.stdout, result.stderr)
        except Exception as e:
            self.finished.emit(-1, "", str(e))


class HelpDialog(QDialog):
    """Simple Help dialog with links to Video Demo, Readme, and Mail to Author."""

    YOUTUBE_URL = "https://www.youtube.com/watch?v=JlV4O1C3uPU"
    README_URL = "https://github.com/shyjun/git-interactive-rebase-gui-tool/blob/master/README.md"
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

class CommitItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        main_text = opt.text
        opt.text = ""  # Hide text so super() doesn't draw it

        widget = option.widget
        main_win = widget.window() if widget else None
        sha = index.data(Qt.DisplayRole).split()[0] if index.data(Qt.DisplayRole) else ""
        is_marked = main_win and getattr(main_win, 'marked_shas', None) and sha in main_win.marked_shas

        painter.save()
        if is_marked and not (opt.state & QStyle.State_Selected):
            is_dark = getattr(main_win, 'is_dark_theme', True) if main_win else True
            marked_bg = QColor("#000000") if is_dark else QColor("#e0e0e0")
            painter.fillRect(option.rect, marked_bg)
        painter.restore()

        style = widget.style() if widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)

        # Draw commit graph node (circle + connecting line) - skip during multi-select mode
        GRAPH_WIDTH = 22
        is_multi = main_win and getattr(main_win, 'multi_select_mode', False)
        if not is_multi:
            is_dark = getattr(main_win, 'is_dark_theme', True) if main_win else True
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            center_x = option.rect.left() + GRAPH_WIDTH // 2
            center_y = option.rect.center().y()
            rad = 5
            total = self.parent().count() if hasattr(self, 'parent') and self.parent() else 0
            if index.row() > 0:
                painter.setPen(QPen(QColor("#555555" if is_dark else "#aaaaaa"), 1.5))
                painter.drawLine(center_x, option.rect.top(), center_x, center_y - rad)
            if index.row() < total - 1:
                painter.setPen(QPen(QColor("#555555" if is_dark else "#aaaaaa"), 1.5))
                painter.drawLine(center_x, center_y + rad, center_x, option.rect.bottom())
            node_color = QColor("#ffd700") if index.row() == 0 else (QColor("#4fc3f7") if is_dark else QColor("#1565c0"))
            painter.setBrush(node_color)
            painter.setPen(QPen(node_color.darker(130), 1))
            painter.drawEllipse(center_x - rad, center_y - rad, rad * 2, rad * 2)
            is_merge = index.data(Qt.UserRole + 5)
            if is_merge:
                painter.setPen(QPen(Qt.white, 1.5))
                painter.drawText(QRect(center_x - rad, center_y - rad, rad * 2, rad * 2),
                                 Qt.AlignCenter, "M")
            painter.restore()

        show_branches = getattr(main_win, "show_local_branches", False)

        branch_text = index.data(Qt.UserRole + 1) if show_branches else None
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget)
        if not is_multi:
            text_rect = text_rect.adjusted(GRAPH_WIDTH, 0, 0, 0)

        painter.save()
        if opt.state & QStyle.State_Selected:
            painter.setPen(opt.palette.highlightedText().color())
        else:
            painter.setPen(opt.palette.text().color())

        if branch_text:
            branches = branch_text.split(", ")
            current_x = text_rect.left()
            is_dark = getattr(main_win, 'is_dark_theme', True) if main_win else True

            # Setup bold font lazily and cache it
            if not hasattr(self, '_bold_font') or getattr(self, '_base_font', None) != opt.font:
                self._base_font = QFont(opt.font)
                self._bold_font = QFont(opt.font)
                self._bold_font.setBold(True)
                # fm_bold will be recreated dynamically when painter.setFont is called

            painter.setFont(self._bold_font)
            fm_bold = painter.fontMetrics()

            for br in branches:
                is_remote = br.startswith("origin/")

                # Determine colors based on branch type and theme
                if is_remote:
                    color = QColor("#ffb74d") if is_dark else QColor("#e65100") # Amber/Orange
                else:
                    color = QColor("#81c784") if is_dark else QColor("#2e7d32") # Green

                # If selected, use highlighted text color to ensure readability
                if opt.state & QStyle.State_Selected:
                    color = opt.palette.highlightedText().color()

                painter.setPen(color)
                br_box = f"[{br}] "
                painter.drawText(QRect(current_x, text_rect.top(), text_rect.width() - (current_x - text_rect.left()), text_rect.height()),
                                 Qt.AlignLeft | Qt.AlignVCenter, br_box)

                current_x += fm_bold.horizontalAdvance(br_box)
        else:
            current_x = text_rect.left()

        # Configure rest of text styling correctly
        painter.setFont(opt.font)
        fm_normal = painter.fontMetrics()

        show_stats = getattr(main_win, "show_stats", True)
        show_date = getattr(main_win, "show_date", True)
        date_str = index.data(Qt.UserRole + 2)
        stats = index.data(Qt.UserRole + 3)
        right_boundary = text_rect.right()

        if show_date and date_str:
            date_w = fm_normal.horizontalAdvance(date_str)
            date_rect = QRect(right_boundary - date_w, text_rect.top(), date_w, text_rect.height())
            painter.save()
            painter.setPen(QColor("#888888") if not (opt.state & QStyle.State_Selected) else opt.palette.highlightedText().color())
            painter.drawText(date_rect, Qt.AlignRight | Qt.AlignVCenter, date_str)
            painter.restore()
            right_boundary -= (date_w + 8)

        if show_stats and stats and isinstance(stats, tuple) and len(stats) == 2:
            added, deleted = stats
            added_str = f"+{added}"
            deleted_str = f" -{deleted}"
            deleted_w = fm_normal.horizontalAdvance(deleted_str)
            added_w = fm_normal.horizontalAdvance(added_str)

            painter.save()
            is_dark = getattr(main_win, 'is_dark_theme', True) if main_win else True
            green_col = QColor("#81c784") if is_dark else QColor("#22863a")
            red_col = QColor("#e57373") if is_dark else QColor("#cb2431")

            painter.setPen(QColor("white") if (opt.state & QStyle.State_Selected) else red_col)
            painter.drawText(QRect(right_boundary - deleted_w, text_rect.top(), deleted_w, text_rect.height()), Qt.AlignLeft | Qt.AlignVCenter, deleted_str)
            right_boundary -= deleted_w

            painter.setPen(QColor("white") if (opt.state & QStyle.State_Selected) else green_col)
            painter.drawText(QRect(right_boundary - added_w, text_rect.top(), added_w, text_rect.height()), Qt.AlignLeft | Qt.AlignVCenter, added_str)
            right_boundary -= (added_w + 8)
            painter.restore()

        left_boundary = current_x
        painter.save()
        if opt.state & QStyle.State_Selected:
            painter.setPen(opt.palette.highlightedText().color())
        else:
            painter.setPen(opt.palette.text().color())

        main_rect = text_rect.adjusted(left_boundary - text_rect.left(), 0, right_boundary - text_rect.right() - 8, 0)
        elided_main = fm_normal.elidedText(main_text, Qt.ElideRight, main_rect.width())
        painter.drawText(main_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_main)
        painter.restore()

        painter.restore()

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
        self.setUniformItemSizes(True)

    def dropEvent(self, event):
        try:
            # Identify which item is being dragged
            dragged_item = self.currentItem()
            if not dragged_item:
                super().dropEvent(event)
                return

            sha = dragged_item.text().split()[0]

            # Identify the target location to give a more descriptive message
            # event.position() returns QPointF, indexAt() needs QPoint
            target_index = self.indexAt(event.position().toPoint())
            target_row = target_index.row()
            if target_row == -1:
                target_msg = "to the end of the list"
            else:
                target_item = self.item(target_row)
                target_sha = target_item.text().split()[0] if target_item else "N/A"
                target_msg = f"near commit <b>{target_sha}</b>"

            # Ask for confirmation BEFORE any visual change in the list
            reply = QMessageBox.question(
                self,
                "Confirm Reorder",
                f"Do you want to move commit <b>{sha}</b> {target_msg}?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                # Capture the original order BEFORE the move
                original_shas = [self.item(i).text().split()[0] for i in range(self.count())]

                # Now perform the visual move
                super().dropEvent(event)

                # Capture the new order and perform rebase
                new_shas = [self.item(i).text().split()[0] for i in range(self.count())]
                self.main_window.perform_move(new_shas, original_shas)
            else:
                print(f"Cancelled reorder of {sha}.")
                # If No, ignore the drop event completely so the list does not change
                event.ignore()
        except Exception as e:
            print(f"[DRAG-DROP ERROR] {e}")
            import traceback
            traceback.print_exc()

def get_theme_stylesheet(theme_name):
    """Return the QSS stylesheet for the given theme name (\"dark\" or \"light\")."""
    if theme_name == "dark":
        return """
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
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666666;
                border: 1px solid #444444;
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
                color: #cccccc;
            }
            QDialog, QMenu {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
            QStatusBar {
                background-color: #1e1e1e;
                border-top: 1px solid #3c3c3c;
            }
            QStatusBar::item {
                border: none;
            }
            QMenu::item:selected {
                background-color: #007acc;
                color: white;
            }
            QMenu::item:disabled {
                color: #666666;
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
        return """
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
            QPushButton:disabled {
                background-color: #f0f0f0;
                color: #aaaaaa;
                border: 1px solid #e0e0e0;
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
            QDialog, QMenu {
                background-color: #f5f5f7;
                color: #333;
                border: 1px solid #ccc;
            }
            QStatusBar {
                background-color: #f5f5f7;
                border-top: 1px solid #ccc;
            }
            QStatusBar::item {
                border: none;
            }
            QMenu::item:selected {
                background-color: #007aff;
                color: white;
            }
            QMenu::item:disabled {
                color: #aaaaaa;
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


class GitInteractiveRebaseApp(QMainWindow):
    def __init__(self, repo_path, commit_sha, app_start_time, base_branch=None):
        super().__init__()
        self.repo_path = repo_path
        self.commit_sha = commit_sha
        self.app_start_time = app_start_time
        self.base_branch = base_branch  # set only when auto-detected; None when SHA provided manually
        self.start_time_full_head = get_full_head_sha(self.repo_path)
        self.start_time_head = get_head_sha(self.repo_path)
        self.cached_current_head_full_sha = self.start_time_full_head
        self.cached_has_uncommitted = False
        self.last_head = None
        self.best_commit_sha = None
        self.marked_shas = set()

        # Global application icon is handled in the main entry point

        # Persistence
        self.settings = QSettings("shyjun", "GitInteractiveRebase")
        self.current_font_size = int(self.settings.value("font_size", 10))
        self.show_diffs = self.settings.value("show_diffs", False, type=bool)
        self.show_origin_options = self.settings.value("show_origin_options", False, type=bool)
        self.show_rebase_options = self.settings.value("show_rebase_options", False, type=bool)
        self.show_squash_options = self.settings.value("show_squash_options", True, type=bool)
        self.show_local_branches = self.settings.value("show_local_branches", False, type=bool)
        self.show_stats = self.settings.value("show_stats", True, type=bool)
        self.show_date = self.settings.value("show_date", True, type=bool)

        self.setWindowTitle(f"git-interactive-rebase-gui-tool : branch=..., HEAD=..., path={self.repo_path}") # Temporary name until load_history updates it
        self.resize(1100, 800)
        self.setMinimumWidth(1100)

        self.setup_ui()
        self.restore_visibility_settings()
        self.load_settings()

        # Performance Cache
        self.commit_cache = {} # sha -> {'meta': str, 'msg': str, 'diff': str, 'files': list}

        # Debounce timer for side diff updates
        self.update_diff_timer = QTimer(self)
        self.update_diff_timer.setSingleShot(True)
        self.update_diff_timer.timeout.connect(self._do_update_side_diff)

        self.load_history()
        self.update_rebase_buttons()
        self.list_widget.setFocus()

    def load_settings(self):
        """Loads persistent user settings like font size and theme."""
        # Diff Tab
        diff_tab_index = self.settings.value("diff_tab_index", 0, type=int)
        if hasattr(self, 'diff_tab_widget'):
            self.diff_tab_widget.setCurrentIndex(diff_tab_index)

        # Font Size
        size = self.settings.value("font_size", 10, type=int)
        self.current_font_size = size
        self.update_font()

        # Theme
        theme = self.settings.value("theme", "light", type=str)
        self.is_dark_theme = (theme == "dark")
        if self.is_dark_theme:
            self.dark_radio.setChecked(True)
        else:
            self.light_radio.setChecked(True)
        self.apply_theme(theme)

        # Window Geometry and State
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        window_state = self.settings.value("windowState")
        if window_state:
            self.restoreState(window_state)

        is_maximized = self.settings.value("isMaximized", False, type=bool)
        if is_maximized:
            self.showMaximized()

    def closeEvent(self, event):
        """Save settings before exiting."""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("isMaximized", self.isMaximized())
        self.settings.setValue("show_stats", self.show_stats)
        self.settings.setValue("show_date", self.show_date)
        super().closeEvent(event)
    def update_window_title(self):
        """Updates window title with branch, HEAD, and path."""
        branch = get_current_branch(self.repo_path)
        app_time = self.app_start_time if self.app_start_time else "N/A"
        title = f"git-interactive-rebase-gui-tool : branch={branch}, path={self.repo_path}, app_start_time={app_time}"
        self.setWindowTitle(title)

    def get_head_sha(self):
        """Returns the current HEAD SHA of the repository."""
        try:
            return subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                          cwd=self.repo_path).decode().strip()
        except:
            return "unknown"

    def log_action(self, sha, action, old_head, new_head):
        """Prints a standardized, user-friendly log message for an action."""
        # Shorten SHAs for readability
        s_sha = sha[:8] if sha and len(sha) > 8 else (sha or "N/A")
        s_old = old_head[:8] if len(old_head) > 8 else old_head
        s_new = new_head[:8] if len(new_head) > 8 else new_head

        print(f"[{time.strftime('%H:%M:%S')}] {s_sha} {action}, HEAD before={s_old}, HEAD after={s_new}")

    def restore_visibility_settings(self):
        """Restores visibility and checkbox states for optional groups."""
        # Origin Options Visibility
        self.show_origin_cb.setChecked(self.show_origin_options)
        self.origin_group.setVisible(self.show_origin_options)

        # Rebase Options Visibility
        self.show_rebase_cb.setChecked(self.show_rebase_options)
        self.rebase_group.setVisible(self.show_rebase_options)

        # Squash Options Visibility
        self.show_squash_cb.setChecked(self.show_squash_options)
        self.squash_group.setVisible(self.show_squash_options)

        # Local Branches Visibility
        self.show_local_branches_cb.setChecked(self.show_local_branches)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Use our custom list widget
        self.list_widget = CommitListWidget(self)
        self.list_widget.setItemDelegate(CommitItemDelegate(self.list_widget))
        self.update_font()
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)

        # Search / Filter Bar row
        search_row_widget = QWidget()
        search_row_layout = QHBoxLayout(search_row_widget)
        search_row_layout.setContentsMargins(0, 0, 0, 0)
        search_row_layout.setSpacing(4)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search commits (SHA or Message)...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.filter_commits)
        search_row_layout.addWidget(self.search_edit, 1)  # stretch to fill

        # Compact filter controls: "Filter:" label + three checkboxes
        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("font-size: 11px; color: gray;")
        search_row_layout.addWidget(filter_label)

        self.filter_by_msg_cb = QCheckBox("Commit Msgs")
        self.filter_by_msg_cb.setChecked(True)
        self.filter_by_msg_cb.setToolTip("Filter commits by commit message text")
        self.filter_by_msg_cb.stateChanged.connect(lambda: self.filter_commits(self.search_edit.text()))
        search_row_layout.addWidget(self.filter_by_msg_cb)

        self.filter_by_files_cb = QCheckBox("Filenames")
        self.filter_by_files_cb.setChecked(False)
        self.filter_by_files_cb.setToolTip("Filter commits by modified filenames")
        self.filter_by_files_cb.stateChanged.connect(lambda: self.filter_commits(self.search_edit.text()))
        search_row_layout.addWidget(self.filter_by_files_cb)

        self.filter_by_diff_cb = QCheckBox("Diff")
        self.filter_by_diff_cb.setChecked(False)
        self.filter_by_diff_cb.setToolTip("Filter commits by diff content (min 3 chars, debounced)")
        self.filter_by_diff_cb.stateChanged.connect(lambda: self.filter_commits(self.search_edit.text()))
        search_row_layout.addWidget(self.filter_by_diff_cb)

        self.filter_by_author_cb = QCheckBox("Author")
        self.filter_by_author_cb.setChecked(False)
        self.filter_by_author_cb.setToolTip("Filter commits by author name or email")
        self.filter_by_author_cb.stateChanged.connect(lambda: self.filter_commits(self.search_edit.text()))
        search_row_layout.addWidget(self.filter_by_author_cb)

        # Debounce timer for diff search (expensive)
        self._diff_search_timer = QTimer(self)
        self._diff_search_timer.setSingleShot(True)
        self._diff_search_timer.setInterval(300)
        self._diff_search_timer.timeout.connect(self._run_filter_with_diff)

        # Inline status label shown during diff search
        self._diff_status_label = QLabel("Searching diffs...")
        self._diff_status_label.setStyleSheet("color: gray; font-style: italic; font-size: 10pt;")
        self._diff_status_label.setVisible(False)
        search_row_layout.addWidget(self._diff_status_label)

        layout.addWidget(search_row_widget)

        # Main Splitter
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.list_widget.setMinimumWidth(150)

        # Insert Left Panel logic embedding explicit Checkboxes
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self.list_widget, 1)

        self.main_splitter.addWidget(left_panel)

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
        self.side_commit_msg.setMinimumHeight(60)
        right_top_layout.addWidget(self.side_commit_msg)

        self.right_splitter.addWidget(self.right_top_widget)

        # Bottom half: Diff Tab Widget
        self.diff_tab_widget = QTabWidget()
        self.diff_tab_widget.setMinimumHeight(150)

        # Page 0: Plain Diff
        plain_diff_widget = QWidget()
        plain_diff_layout = QVBoxLayout(plain_diff_widget)
        plain_diff_layout.setContentsMargins(0, 0, 0, 0)
        plain_diff_layout.setSpacing(0)

        self.side_diff_view = DiffView()
        self.side_diff_view.setReadOnly(True)

        self.plain_diff_search = DiffSearchBar(target_view=self.side_diff_view, parent=plain_diff_widget)
        # Search bar is visible by default now as requested

        plain_diff_layout.addWidget(self.plain_diff_search)
        plain_diff_layout.addWidget(self.side_diff_view)

        self.diff_tab_widget.addTab(plain_diff_widget, "Plain Diff")

        # Page 1: Filewise Diff
        filewise_widget = QWidget()
        filewise_layout = QVBoxLayout(filewise_widget)
        filewise_layout.setContentsMargins(0, 0, 0, 0)

        self.filewise_splitter = QSplitter(Qt.Vertical)

        # File list
        self.filewise_file_list = QListWidget()
        self.filewise_file_list.setMinimumHeight(60)
        self.filewise_file_list.currentTextChanged.connect(self.on_filewise_file_selected)
        self.filewise_file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.filewise_file_list.customContextMenuRequested.connect(self.show_filewise_context_menu)
        # Install stats delegate (colors updated when theme changes)
        colors = self.current_theme_colors if hasattr(self, 'current_theme_colors') else {"added": "#22863a", "removed": "#cb2431"}
        self.filewise_stats_delegate = StatsItemDelegate(
            added_color=colors.get("added", "#22863a"),
            removed_color=colors.get("removed", "#cb2431"),
            parent=self.filewise_file_list
        )
        self.filewise_file_list.setItemDelegate(self.filewise_stats_delegate)

        # File diff
        self.filewise_diff_view = DiffView()
        self.filewise_diff_view.setReadOnly(True)
        self.filewise_diff_view.setMinimumHeight(100)

        # Apply highlighter
        self.filewise_highlighter = DiffHighlighter(self.filewise_diff_view.document())

        filewise_right_widget = QWidget()
        filewise_right_layout = QVBoxLayout(filewise_right_widget)
        filewise_right_layout.setContentsMargins(0, 0, 0, 0)
        filewise_right_layout.setSpacing(0)

        self.filewise_diff_search = DiffSearchBar(target_view=self.filewise_diff_view, parent=filewise_right_widget)

        filewise_right_layout.addWidget(self.filewise_diff_search)
        filewise_right_layout.addWidget(self.filewise_diff_view)

        self.filewise_splitter.addWidget(self.filewise_file_list)
        self.filewise_splitter.addWidget(filewise_right_widget)
        self.filewise_splitter.setCollapsible(0, False)
        self.filewise_splitter.setCollapsible(1, False)
        self.filewise_splitter.setSizes([100, 300]) # default split

        filewise_layout.addWidget(self.filewise_splitter)
        self.diff_tab_widget.addTab(filewise_widget, "File-wise Diff")

        self.right_splitter.addWidget(self.diff_tab_widget)

        # Determine highlighting colors and initialize highlighter
        colors = self.current_theme_colors if hasattr(self, 'current_theme_colors') else {"added": "#a6e22e", "removed": "#f92672", "header": "#66d9ef", "separator": "#444444"}
        self.side_diff_highlighter = DiffHighlighter(self.side_diff_view.document(),
                                                   added_color=colors["added"],
                                                   removed_color=colors["removed"],
                                                   header_color=colors["header"])
        self.side_diff_view.set_separator_color(colors["separator"])

        # Add the vertical splitter to the right panel's layout
        right_layout.addWidget(self.right_splitter)

        # Set initial split sizes for top (message) and bottom (diff)
        self.right_splitter.setCollapsible(0, False)
        self.right_splitter.setCollapsible(1, False)
        self.right_splitter.setSizes([150, 650])

        self.right_panel.setMinimumWidth(150)

        self.right_panel.setVisible(self.show_diffs)

        self.main_splitter.addWidget(self.right_panel)
        # default split ratio: history 60%, diff 40%
        self.main_splitter.setSizes([600, 400])

        layout.addWidget(self.main_splitter, 1)

        self.list_widget.itemDoubleClicked.connect(self.view_commit)
        self.list_widget.itemSelectionChanged.connect(self.on_selection_changed)

        self.diff_tab_widget.currentChanged.connect(self.on_diff_tab_changed)

        self.update_window_title()

        # Top Control Bar (single row of buttons)
        controls_layout = QHBoxLayout()
        controls_layout.setAlignment(Qt.AlignTop)

        # Theme dropdown menu button
        self.theme_menu_btn = QPushButton("Theme")
        self._set_theme_icon(self.theme_menu_btn)
        theme_menu = QMenu(self.theme_menu_btn)
        self.dark_radio = QRadioButton("Dark Theme")
        self.light_radio = QRadioButton("Light Theme")
        self.dark_radio.toggled.connect(lambda: self.on_theme_toggled())
        self.light_radio.toggled.connect(lambda: self.on_theme_toggled())
        dark_action = QWidgetAction(theme_menu)
        dark_action.setDefaultWidget(self.dark_radio)
        light_action = QWidgetAction(theme_menu)
        light_action.setDefaultWidget(self.light_radio)
        theme_menu.addAction(dark_action)
        theme_menu.addAction(light_action)
        self.theme_menu_btn.setMenu(theme_menu)

        self.toggle_diff_btn = QPushButton("Hide Diffs" if self.show_diffs else "Show Diffs")
        self._set_toggle_diff_icon(self.toggle_diff_btn)
        self.help_btn = QPushButton("Help")
        self._set_help_icon(self.help_btn)
        self.rescan_btn = QPushButton("Rescan Repo")
        self._set_rescan_icon(self.rescan_btn)
        self.undo_btn = QPushButton("Undo")
        self._set_undo_icon(self.undo_btn)
        self.undo_btn.setEnabled(False)
        self.check_update_btn = QPushButton("Check Updates")
        self._set_check_update_icon(self.check_update_btn)
        self.refresh_btn = QPushButton("Refresh")
        self._set_refresh_icon(self.refresh_btn)
        self.exit_btn = QPushButton("Exit")
        self._set_exit_icon(self.exit_btn)
        self.exit_btn.setStyleSheet("color: red; font-weight: bold;")

        self.failsafe_btn = QPushButton("")
        self.best_commit_btn = QPushButton("Reset Hard to BEST_COMMITID (Not Set)")
        self.best_commit_btn.setEnabled(False)
        self.custom_reset_btn = QPushButton("Enter commit id to reset hard to")

        for btn in [self.toggle_diff_btn, self.help_btn, self.rescan_btn, self.check_update_btn, self.undo_btn, self.refresh_btn, self.exit_btn, self.theme_menu_btn]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(100)
        self.failsafe_btn.setMinimumHeight(40)
        self.best_commit_btn.setMinimumHeight(40)
        self.custom_reset_btn.setMinimumHeight(40)

        self.toggle_diff_btn.clicked.connect(self.toggle_side_diff_visibility)
        self.help_btn.clicked.connect(self._show_help_dialog)
        self.rescan_btn.clicked.connect(self.handle_rescan_repo)
        self.undo_btn.clicked.connect(self.handle_undo)
        self.check_update_btn.clicked.connect(self.handle_check_for_updates)
        self.refresh_btn.clicked.connect(self.handle_manual_refresh)
        self.failsafe_btn.clicked.connect(self.handle_failsafe_reset)
        self.best_commit_btn.clicked.connect(self.handle_best_commit_reset)
        self.custom_reset_btn.clicked.connect(self.handle_custom_reset)
        self.exit_btn.clicked.connect(self.close)

        # Single row of main buttons
        controls_layout.addWidget(self.theme_menu_btn)
        controls_layout.addWidget(self.toggle_diff_btn)
        controls_layout.addWidget(self.help_btn)
        controls_layout.addWidget(self.check_update_btn)
        controls_layout.addStretch()
        controls_layout.addWidget(self.rescan_btn)
        controls_layout.addWidget(self.undo_btn)
        controls_layout.addWidget(self.refresh_btn)
        controls_layout.addWidget(self.exit_btn)

        layout.addLayout(controls_layout)

        # Add failsafe options as a distinct row below the other controls
        failsafe_group = QGroupBox("Fail-safe")
        failsafe_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        failsafe_layout = QHBoxLayout()
        failsafe_layout.addWidget(self.failsafe_btn)
        failsafe_layout.addWidget(self.best_commit_btn)
        failsafe_layout.addWidget(self.custom_reset_btn)
        failsafe_group.setLayout(failsafe_layout)
        layout.addWidget(failsafe_group)

        # Squash multiple commits group
        self.multi_select_mode = False
        self.squash_group = QGroupBox("Squash multiple commits")
        self.squash_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        squash_layout = QHBoxLayout()
        self.multi_select_btn = QPushButton("Select multiple commits to squash")
        self.squash_selected_btn = QPushButton("Squash selected commits")
        self.cancel_multi_btn = QPushButton("Cancel multi selection")
        self.squash_selected_btn.setEnabled(False)
        self.cancel_multi_btn.setEnabled(False)
        for btn in [self.multi_select_btn, self.squash_selected_btn, self.cancel_multi_btn]:
            btn.setMinimumHeight(40)
        self.multi_select_btn.clicked.connect(self.enter_multi_select_mode)
        self.squash_selected_btn.clicked.connect(self.handle_squash_selected)
        self.cancel_multi_btn.clicked.connect(self.handle_cancel_multi_select)
        squash_layout.addWidget(self.multi_select_btn)
        squash_layout.addWidget(self.squash_selected_btn)
        squash_layout.addWidget(self.cancel_multi_btn)
        self.squash_group.setLayout(squash_layout)
        layout.addWidget(self.squash_group)

        # Origin group box
        self.origin_group = QGroupBox("Origin")
        self.origin_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        origin_layout = QHBoxLayout()
        self.fetch_btn = QPushButton("git fetch")
        self.reset_origin_btn = QPushButton("git reset --hard origin")
        self.push_force_btn = QPushButton("git push --force")
        for btn in [self.fetch_btn, self.reset_origin_btn, self.push_force_btn]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)
        self.fetch_btn.clicked.connect(self.handle_git_fetch)
        self.reset_origin_btn.clicked.connect(self.handle_git_reset_hard_origin)
        self.push_force_btn.clicked.connect(self.handle_git_push_force)
        origin_layout.addWidget(self.fetch_btn)
        origin_layout.addWidget(self.reset_origin_btn)
        origin_layout.addWidget(self.push_force_btn)
        self.origin_group.setLayout(origin_layout)
        layout.addWidget(self.origin_group)

        # Rebase group box
        self.rebase_group = QGroupBox("Rebase")
        self.rebase_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        rebase_layout = QHBoxLayout()
        self.rebase_master_btn = QPushButton("git rebase master")
        self.rebase_main_btn = QPushButton("git rebase main")
        self.rebase_custom_btn = QPushButton("Enter branch/sha to rebase on top of")
        for btn in [self.rebase_master_btn, self.rebase_main_btn, self.rebase_custom_btn]:
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)
        self.rebase_master_btn.clicked.connect(self.handle_git_rebase_master)
        self.rebase_main_btn.clicked.connect(self.handle_git_rebase_main)
        self.rebase_custom_btn.clicked.connect(self.handle_git_rebase_custom)
        rebase_layout.addWidget(self.rebase_master_btn)
        rebase_layout.addWidget(self.rebase_main_btn)
        rebase_layout.addWidget(self.rebase_custom_btn)
        self.rebase_group.setLayout(rebase_layout)
        layout.addWidget(self.rebase_group)

        # ── Status Bar ──
        status_bar = self.statusBar()
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(4, 0, 4, 0)
        status_layout.setSpacing(6)

        # Zoom controls
        zoom_label = QLabel("Zoom:")
        self.sb_zoom_out_btn = QPushButton("–")
        self.sb_zoom_out_btn.setFixedSize(26, 22)
        self.sb_zoom_out_btn.setStyleSheet("padding: 0px;")
        self.zoom_percent_label = QLabel("100%")
        self.zoom_percent_label.setFixedWidth(40)
        self.zoom_percent_label.setAlignment(Qt.AlignCenter)
        self.sb_zoom_in_btn = QPushButton("+")
        self.sb_zoom_in_btn.setFixedSize(26, 22)
        self.sb_zoom_in_btn.setStyleSheet("padding: 0px;")
        self.sb_zoom_in_btn.clicked.connect(self.handle_zoom_in)
        self.sb_zoom_out_btn.clicked.connect(self.handle_zoom_out)

        status_layout.addWidget(zoom_label)
        status_layout.addWidget(self.sb_zoom_out_btn)
        status_layout.addWidget(self.zoom_percent_label)
        status_layout.addWidget(self.sb_zoom_in_btn)

        sep1 = QLabel("|")
        sep1.setStyleSheet("color: gray;")
        status_layout.addWidget(sep1)

        # Visibility checkboxes
        self.show_origin_cb = QCheckBox("Show Origin")
        self.show_rebase_cb = QCheckBox("Show Rebase")
        self.show_squash_cb = QCheckBox("Show Squash")
        self.show_local_branches_cb = QCheckBox("Show Local Branches")

        self.show_origin_cb.toggled.connect(self.on_origin_visibility_toggled)
        self.show_rebase_cb.toggled.connect(self.on_rebase_visibility_toggled)
        self.show_squash_cb.toggled.connect(self.on_squash_visibility_toggled)
        self.show_local_branches_cb.toggled.connect(self.on_local_branches_visibility_toggled)

        status_layout.addWidget(self.show_origin_cb)
        status_layout.addWidget(self.show_rebase_cb)
        status_layout.addWidget(self.show_squash_cb)
        status_layout.addWidget(self.show_local_branches_cb)

        sep2 = QLabel("|")
        sep2.setStyleSheet("color: gray;")
        status_layout.addWidget(sep2)

        self.show_stats_cb = QCheckBox("show stats")
        self.show_date_cb = QCheckBox("show date")

        self.show_stats_cb.setChecked(self.show_stats)
        self.show_date_cb.setChecked(self.show_date)

        self.show_stats_cb.toggled.connect(lambda ctx: self._on_stats_toggled())
        self.show_date_cb.toggled.connect(lambda ctx: self._on_date_toggled())

        status_layout.addWidget(self.show_stats_cb)
        status_layout.addWidget(self.show_date_cb)

        sep_date = QLabel("|")
        sep_date.setStyleSheet("color: gray;")
        status_layout.addWidget(sep_date)

        self.always_on_top_cb = QCheckBox("Always On Top")
        self.always_on_top_cb.toggled.connect(self._on_always_on_top_toggled)
        status_layout.addWidget(self.always_on_top_cb)

        sep_ontop = QLabel("|")
        sep_ontop.setStyleSheet("color: gray;")
        status_layout.addWidget(sep_ontop)

        status_layout.addStretch()

        sep3 = QLabel("|")
        sep3.setStyleSheet("color: gray;")
        status_layout.addWidget(sep3)

        self.total_commits_label = QLabel("Total: 0")
        self.total_commits_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.total_commits_label)

        sep4 = QLabel("|")
        sep4.setStyleSheet("color: gray;")
        status_layout.addWidget(sep4)

        self.showing_commits_label = QLabel("Showing: 0")
        self.showing_commits_label.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.showing_commits_label)

        self.sep_merge = QLabel("|")
        self.sep_merge.setStyleSheet("color: gray;")
        self.sep_merge.setVisible(False)
        status_layout.addWidget(self.sep_merge)

        self.merge_commits_label = QLabel("Merge: 0")
        self.merge_commits_label.setStyleSheet("font-weight: bold;")
        self.merge_commits_label.setVisible(False)
        status_layout.addWidget(self.merge_commits_label)

        status_bar.addPermanentWidget(status_widget, 1)


        # Keyboard Shortcuts
        self.slash_shortcut = QShortcut(QKeySequence("/"), self)
        self.slash_shortcut.activated.connect(self.handle_slash_shortcut)

        self.esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.esc_shortcut.activated.connect(self.handle_esc_shortcut)

        self.f5_shortcut = QShortcut(QKeySequence("F5"), self)
        self.f5_shortcut.activated.connect(self.handle_manual_refresh)

        self.ctrl_f_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.ctrl_f_shortcut.activated.connect(self.show_search_bar)

        self.ctrl_q_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.ctrl_q_shortcut.activated.connect(self.close)

    def show_search_bar(self):
        if not self.right_panel.isVisible():
            return
        if self.diff_tab_widget.currentIndex() == 0:
            self.plain_diff_search.show_and_focus()
        elif self.diff_tab_widget.currentIndex() == 1:
            self.filewise_diff_search.show_and_focus()

    def on_selection_changed(self):
        """Triggered when list selection changes. Debounces the update."""
        self.update_diff_timer.start(50) # 50ms debounce

    def update_side_diff(self):
        """Synchronous version for immediate updates when needed."""
        self._do_update_side_diff()

    def _do_update_side_diff(self):
        item = self.list_widget.currentItem()
        if not item:
            if hasattr(self, 'side_commit_label'):
                self.side_commit_label.setText("Select a commit to view details")
                self.side_commit_msg.clear()
            self.side_diff_view.clear()
            if hasattr(self, 'filewise_file_list'):
                self.filewise_file_list.clear()
                self.filewise_diff_view.clear()
            return

        sha = item.text().split()[0]

        # Check cache
        cache_entry = self.commit_cache.get(sha, {})

        try:
            if 'meta' not in cache_entry:
                meta, msg = get_commit_metadata_and_message(self.repo_path, sha)
                cache_entry['meta'] = meta
                cache_entry['msg'] = msg
                self.commit_cache[sha] = cache_entry

            meta = cache_entry['meta']
            msg = cache_entry['msg']

            self.side_commit_label.setText(f"Commit: <b>{sha}</b>  <span style='color:gray;'>({meta})</span>")
            self.side_commit_msg.setPlainText(msg)

            if self.diff_tab_widget.currentIndex() == 0:
                if 'diff' not in cache_entry:
                    cache_entry['diff'] = get_commit_diff(self.repo_path, sha)
                    self.commit_cache[sha] = cache_entry
                self.side_diff_view.setPlainText(cache_entry['diff'])
                self.side_diff_view.set_separator_color(self.current_theme_colors.get("separator", "#444444"))
                # Re-evaluate search if the search bar is visible
                if self.plain_diff_search.isVisible():
                    self.plain_diff_search._perform_search()
            else:
                self.side_diff_view.clear()
                if 'files' not in cache_entry:
                    cache_entry['files'] = get_commit_files(self.repo_path, sha)
                    self.commit_cache[sha] = cache_entry

                files = cache_entry['files']
                # Fetch per-file stats (cached separately)
                if 'file_stats' not in cache_entry:
                    try:
                        cache_entry['file_stats'] = get_commit_file_stats(self.repo_path, sha)
                    except:
                        cache_entry['file_stats'] = {}
                    self.commit_cache[sha] = cache_entry
                file_stats = cache_entry.get('file_stats', {})

                # Temporarily block signals to avoid triggering on_filewise_file_selected prematurely
                self.filewise_file_list.blockSignals(True)
                self.filewise_file_list.clear()
                for f in files:
                    item = QListWidgetItem(f)
                    item.setData(Qt.UserRole, file_stats.get(f))
                    self.filewise_file_list.addItem(item)
                self.filewise_file_list.blockSignals(False)

                if files:
                    self.filewise_file_list.setCurrentRow(0)
                else:
                    self.filewise_diff_view.clear()
        except Exception as e:
            self.side_diff_view.setPlainText(f"Error loading diff: {e}")
            if hasattr(self, 'side_commit_msg'):
                self.side_commit_msg.clear()
                self.side_commit_label.setText("Error")
            if hasattr(self, 'filewise_diff_view'):
                self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def on_diff_tab_changed(self, index):
        self.settings.setValue("diff_tab_index", index)
        self.update_side_diff()

    def show_filewise_context_menu(self, pos):
        item = self.filewise_file_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=item.text(): self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        is_only_file = self.filewise_file_list.count() <= 1

        move_action = QAction("Move file changes out of this commit", self)
        move_action.triggered.connect(lambda checked=False, text=item.text(): self.handle_context_move_file_out(text))
        move_action.setEnabled(not is_only_file)
        menu.addAction(move_action)

        drop_action = QAction("Drop file changes from this commit", self)
        drop_action.triggered.connect(lambda checked=False, text=item.text(): self.handle_context_drop_file(text))
        drop_action.setEnabled(not is_only_file)
        menu.addAction(drop_action)

        remove_onwards_action = QAction("Remove file from this commit onwards", self)
        remove_onwards_action.triggered.connect(lambda checked=False, text=item.text(): self.handle_context_remove_file_onwards(text))
        menu.addAction(remove_onwards_action)

        menu.addSeparator()
        refine_action = QAction("Refine/Edit changes in selected file", self)
        refine_action.triggered.connect(lambda checked=False, text=item.text(): self.handle_context_refine_changes(text))
        menu.addAction(refine_action)

        menu.exec(self.filewise_file_list.mapToGlobal(pos))

    def handle_context_move_file_out(self, filepath):
        current_commit_item = self.list_widget.currentItem()
        if not current_commit_item:
            return
        sha = current_commit_item.text().split()[0]
        self.perform_move_file_out(sha, filepath)

    def handle_context_drop_file(self, filepath):
        current_commit_item = self.list_widget.currentItem()
        if not current_commit_item:
            return
        sha = current_commit_item.text().split()[0]
        self.perform_drop_file_from_commit(sha, filepath)

    def handle_context_remove_file_onwards(self, filepath):
        current_commit_item = self.list_widget.currentItem()
        if not current_commit_item:
            return
        sha = current_commit_item.text().split()[0]
        self.perform_remove_file_from_commit_onwards(sha, filepath)

    def handle_context_refine_changes(self, filepath):
        current_commit_item = self.list_widget.currentItem()
        if not current_commit_item:
            return
        sha = current_commit_item.text().split()[0]
        self.perform_refine_changes(sha, filepath)

    def copy_filename_to_clipboard(self, filename):
        QApplication.clipboard().setText(filename)
        QMessageBox.information(self, "Copied", f"Copied '{filename}' to clipboard.")

    def on_filewise_file_selected(self, filepath):
        if not filepath:
            self.filewise_diff_view.clear()
            return
        item = self.list_widget.currentItem()
        if not item:
            return
        sha = item.text().split()[0]
        try:
            diff = get_file_diff_only_in_commit(self.repo_path, sha, filepath)
            self.filewise_diff_view.setPlainText(diff)
            self.filewise_diff_view.set_separator_color(self.current_theme_colors.get("separator", "#444444"))
            self.filewise_diff_search._perform_search()
        except Exception as e:
            self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def toggle_side_diff_visibility(self):
        new_visibility = not self.right_panel.isVisible()
        self.right_panel.setVisible(new_visibility)
        self.show_diffs = new_visibility
        self.settings.setValue("show_diffs", self.show_diffs)
        self.toggle_diff_btn.setText("Hide Diffs" if new_visibility else "Show Diffs")

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
        # 1. Try to clear plain diff search if active and has content/focus
        if self.diff_tab_widget.currentIndex() == 0 and (self.plain_diff_search.search_input.text() or self.plain_diff_search.search_input.hasFocus()):
            self.plain_diff_search.escape_pressed()
            return

        # 2. Try to clear filewise diff search if active and has content/focus
        if self.diff_tab_widget.currentIndex() == 1 and hasattr(self, 'filewise_diff_search') and (self.filewise_diff_search.search_input.text() or self.filewise_diff_search.search_input.hasFocus()):
            self.filewise_diff_search.escape_pressed()
            return

        # 3. Fallback to commit history search filter
        if self.search_edit.text() or self.search_edit.hasFocus():
            self.search_edit.clear()
            self.search_edit.clearFocus()
            self.list_widget.setFocus()


    def filter_commits(self, text):
        """Live-filters commits. Diff search is debounced; msg/filename filtering is instant."""
        search_term = text.strip().lower()
        by_diff = self.filter_by_diff_cb.isChecked()

        # Always run instant filters (msg + filenames) immediately
        self._run_filter_no_diff(search_term)

        # Trigger debounced diff search only when needed
        if by_diff and len(search_term) >= 3:
            self._diff_status_label.setVisible(True)
            self._diff_search_timer.start()  # restarts 300ms window each keystroke
        else:
            self._diff_search_timer.stop()
            self._diff_status_label.setVisible(False)

    def _run_filter_no_diff(self, search_term=None):
        """Instant filtering by commit message, filenames, and author."""
        if search_term is None:
            search_term = self.search_edit.text().strip().lower()

        by_msg = self.filter_by_msg_cb.isChecked()
        by_files = self.filter_by_files_cb.isChecked()
        by_diff = self.filter_by_diff_cb.isChecked()
        by_author = self.filter_by_author_cb.isChecked()

        # If no text or all disabled → show all and clear any diff-pending markers
        if not search_term or (not by_msg and not by_files and not by_diff and not by_author):
            for i in range(self.list_widget.count()):
                self.list_widget.item(i).setHidden(False)
            self._update_commit_counts()
            return

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item_text = item.text().lower()
            sha = item.text().split()[0]

            matched = False

            # Commit message / SHA match
            if by_msg and search_term in item_text:
                matched = True

            # Filename match — lazy-load via existing commit_cache
            if not matched and by_files:
                cache_entry = self.commit_cache.get(sha, {})
                if 'files' not in cache_entry:
                    try:
                        cache_entry['files'] = get_commit_files(self.repo_path, sha)
                        self.commit_cache[sha] = cache_entry
                    except Exception:
                        cache_entry['files'] = []
                        self.commit_cache[sha] = cache_entry
                files = cache_entry.get('files', [])
                if any(search_term in f.lower() for f in files):
                    matched = True

            # Author match (name or email) — stored at init, instant
            if not matched and by_author:
                author = item.data(Qt.UserRole + 4) or ""
                if search_term in author.lower():
                    matched = True

            # When diff search is enabled keep items visible for now (diff pass will correct)
            if not matched and by_diff and len(search_term) >= 3:
                matched = True  # tentatively show — diff pass will hide non-matching ones

            item.setHidden(not matched)

        self._update_commit_counts()

    def _run_filter_with_diff(self):
        """Debounced diff search: hides commits already shown that do NOT match diff text."""
        search_term = self.search_edit.text().strip().lower()
        if len(search_term) < 3 or not self.filter_by_diff_cb.isChecked():
            return

        by_msg = self.filter_by_msg_cb.isChecked()
        by_files = self.filter_by_files_cb.isChecked()

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.isHidden():
                continue  # already filtered out by faster passes

            sha = item.text().split()[0]
            item_text = item.text().lower()

            # If already matched by msg or files, no need to check diff
            already_matched = (by_msg and search_term in item_text)
            if not already_matched and by_files:
                cache_entry = self.commit_cache.get(sha, {})
                files = cache_entry.get('files', [])
                already_matched = any(search_term in f.lower() for f in files)

            if already_matched:
                continue

            # Diff match — lazy-load and cache
            cache_entry = self.commit_cache.get(sha, {})
            if 'diff' not in cache_entry:
                try:
                    cache_entry['diff'] = get_commit_diff(self.repo_path, sha)
                    self.commit_cache[sha] = cache_entry
                except Exception:
                    cache_entry['diff'] = ''
                    self.commit_cache[sha] = cache_entry

            diff_text = cache_entry.get('diff', '')
            if search_term not in diff_text.lower():
                item.setHidden(True)

        self._diff_status_label.setVisible(False)
        self._update_commit_counts()

    def _update_commit_counts(self):
        total = self.list_widget.count()
        showing = 0
        merge_showing = 0
        for i in range(total):
            item = self.list_widget.item(i)
            if not item.isHidden():
                showing += 1
                if item.data(Qt.UserRole + 5):
                    merge_showing += 1
        self.showing_commits_label.setText(f"Showing: {showing}")
        has_merges = merge_showing > 0
        self.sep_merge.setVisible(has_merges)
        self.merge_commits_label.setVisible(has_merges)
        if has_merges:
            self.merge_commits_label.setText(f"Merge: {merge_showing}")

    def _count_total_commits_async(self):
        """Count total commits in repo in background thread to avoid blocking startup."""
        import threading
        def worker():
            try:
                total = subprocess.check_output(
                    ["git", "rev-list", "--count", "HEAD"],
                    cwd=self.repo_path, encoding='utf-8', errors='replace'
                ).strip()
                from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                print(f"Total commits in repo: {total}")
                QMetaObject.invokeMethod(
                    self, "_set_total_commit_count",
                    Qt.QueuedConnection,
                    Q_ARG(str, total)
                )
            except Exception:
                from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(
                    self, "_set_total_commit_count",
                    Qt.QueuedConnection,
                    Q_ARG(str, "?")
                )
        print("Trying to find out total commit count ...")
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    @Slot(str)
    def _set_total_commit_count(self, count_str):
        self.total_commits_label.setText(f"Total commits in repo: {count_str}")

    def _set_icon(self, button, fallback_icon, theme_name=None):
        if theme_name:
            icon = QIcon.fromTheme(theme_name)
            if not icon.isNull():
                button.setIcon(icon)
                button.setIconSize(QSize(16, 16))
                return
        icon = self.style().standardIcon(fallback_icon)
        button.setIcon(icon)
        button.setIconSize(QSize(16, 16))

    def _set_theme_icon(self, button):
        import math
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().color(QPalette.ButtonText)
        pen = QPen(color, 1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        # Artist palette body with thumb hole cutout
        body = QPainterPath()
        body.addEllipse(1.5, 3, 11, 9)
        hole = QPainterPath()
        hole.addEllipse(9, 8, 4, 4)
        palette_path = body.subtracted(hole)
        painter.drawPath(palette_path)

        # Paint blobs
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(4, 4.5, 2.0, 2.0)
        painter.drawEllipse(7, 4.0, 2.0, 2.0)
        painter.drawEllipse(5.5, 7.5, 2.0, 2.0)

        painter.end()
        button.setIcon(QIcon(pixmap))
        button.setIconSize(QSize(16, 16))

    def _make_icon_pixmap(self, draw_func):
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_func(painter)
        painter.end()
        return QIcon(pixmap)

    def _toolbar_icon_color(self, color=None):
        return color if color is not None else self.palette().color(QPalette.ButtonText)

    def _apply_toolbar_icon(self, button, draw_func, color=None):
        icon_color = self._toolbar_icon_color(color)
        button.setIcon(self._make_icon_pixmap(lambda painter: draw_func(painter, icon_color)))
        button.setIconSize(QSize(16, 16))

    def _set_toggle_diff_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_eye_slash)

    def _set_help_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_help)

    def _set_rescan_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_rescan)

    def _set_undo_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_undo)

    def _set_check_update_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_cloud_download)

    def _set_refresh_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_refresh)

    def _set_exit_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_exit, QColor("red"))

    def _refresh_toolbar_icons(self):
        self._set_theme_icon(self.theme_menu_btn)
        self._set_toggle_diff_icon(self.toggle_diff_btn)
        self._set_help_icon(self.help_btn)
        self._set_rescan_icon(self.rescan_btn)
        self._set_undo_icon(self.undo_btn)
        self._set_check_update_icon(self.check_update_btn)
        self._set_refresh_icon(self.refresh_btn)
        self._set_exit_icon(self.exit_btn)

    def _draw_eye_slash(self, painter, color):
        pen = QPen(color, 1.7)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        eye = QPainterPath()
        eye.moveTo(1.5, 8)
        eye.cubicTo(4.0, 3.8, 12.0, 3.8, 14.5, 8)
        eye.cubicTo(12.0, 12.2, 4.0, 12.2, 1.5, 8)
        painter.drawPath(eye)
        painter.drawEllipse(6.0, 6.0, 4.0, 4.0)
        painter.drawLine(2.0, 14.0, 14.0, 2.0)

    def _draw_help(self, painter, color):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(2.0, 2.0, 12.0, 12.0)

        painter.setPen(QPen(Qt.white, 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        question = QPainterPath()
        question.moveTo(5.8, 6.0)
        question.cubicTo(5.9, 4.6, 7.0, 4.0, 8.1, 4.0)
        question.cubicTo(9.5, 4.0, 10.3, 4.8, 10.3, 5.9)
        question.cubicTo(10.3, 7.0, 9.4, 7.5, 8.6, 8.0)
        question.cubicTo(8.0, 8.4, 7.8, 8.8, 7.8, 9.6)
        painter.drawPath(question)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(Qt.white))
        painter.drawEllipse(7.25, 11.1, 1.5, 1.5)

    def _draw_cloud_download(self, painter, color):
        pen = QPen(color, 1.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        cloud = QPainterPath()
        cloud.moveTo(5.1, 12.0)
        cloud.lineTo(4.3, 12.0)
        cloud.cubicTo(2.4, 12.0, 1.3, 10.8, 1.3, 9.3)
        cloud.cubicTo(1.3, 7.9, 2.2, 6.9, 3.7, 6.6)
        cloud.cubicTo(4.0, 4.5, 5.6, 3.2, 7.6, 3.2)
        cloud.cubicTo(9.4, 3.2, 10.8, 4.2, 11.4, 5.8)
        cloud.cubicTo(13.3, 5.9, 14.7, 7.3, 14.7, 9.0)
        cloud.cubicTo(14.7, 10.8, 13.3, 12.0, 11.5, 12.0)
        cloud.lineTo(10.7, 12.0)
        painter.drawPath(cloud)
        painter.drawLine(8.0, 6.6, 8.0, 11.0)
        painter.drawLine(5.9, 8.9, 8.0, 11.0)
        painter.drawLine(10.1, 8.9, 8.0, 11.0)

    def _draw_rescan(self, painter, color):
        pen = QPen(color, 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        painter.drawEllipse(2.0, 2.0, 8.8, 8.8)
        painter.drawLine(9.4, 9.4, 14.0, 14.0)

    def _draw_undo(self, painter, color):
        pen = QPen(color, 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        painter.drawLine(6.6, 4.0, 2.8, 7.4)
        painter.drawLine(2.8, 7.4, 6.6, 10.8)
        path = QPainterPath()
        path.moveTo(3.2, 7.4)
        path.lineTo(9.4, 7.4)
        path.cubicTo(12.0, 7.4, 13.4, 8.9, 13.4, 11.5)
        painter.drawPath(path)

    def _draw_refresh(self, painter, color):
        pen = QPen(color, 2.2)
        pen.setCapStyle(Qt.FlatCap)
        pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        painter.drawArc(2.5, 2.4, 11.0, 11.0, 150 * 16, -120 * 16)
        painter.drawArc(2.5, 2.4, 11.0, 11.0, 330 * 16, -120 * 16)

        painter.drawLine(12.8, 3.4, 12.8, 6.7)
        painter.drawLine(12.8, 6.7, 9.6, 6.7)
        painter.drawLine(3.2, 12.6, 3.2, 9.3)
        painter.drawLine(3.2, 9.3, 6.4, 9.3)

    def _draw_exit(self, painter, color):
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        painter.drawRoundedRect(2.4, 3.0, 6.6, 10.0, 0.8, 0.8)
        painter.drawLine(9.8, 8.0, 14.0, 8.0)
        painter.drawLine(12.0, 5.9, 14.0, 8.0)
        painter.drawLine(12.0, 10.1, 14.0, 8.0)
        painter.drawLine(6.6, 5.0, 6.6, 11.0)

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
        else:
            print(f"Cancelled reset to BEST_COMMITID ({self.best_commit_sha[:8]}).")

    def handle_failsafe_reset(self):
        # We use cached values from load_history for performance.
        if self.cached_current_head_full_sha == self.start_time_full_head and not self.cached_has_uncommitted:
            QMessageBox.warning(self, "No Changes", "HEAD is already at START_TIME_HEAD and there are no uncommitted changes.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Failsafe Reset",
            f"Are you sure you want to <b>reset --hard</b> to START_TIME_HEAD (<b>{self.start_time_head[:8]}</b>)?<br><br>"
            "This will discard all uncommitted changes and move your branch to this state.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.save_undo_state()
            self.perform_reset(self.start_time_head)
        else:
            print(f"Cancelled failsafe reset to {self.start_time_head[:8]}.")

    def save_undo_state(self):
        """Saves current HEAD to last_head and enables Undo button."""
        self.last_head = get_full_head_sha(self.repo_path)
        self.undo_btn.setEnabled(True)

    def handle_undo(self):
        """Handles the Undo action by resetting hard to last_head."""
        if not self.last_head:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Undo",
            f"Are you sure you want to <b>reset --hard</b> to the state before the last operation (<b>{self.last_head[:8]}</b>)?<br><br>"
            "This will discard all uncommitted changes and move your branch to this state.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            old_head = self.get_head_sha()

            self.progress_dialog = ProgressDialog("Undoing", f"Resetting hard to {self.last_head[:8]}...", self)
            self.worker = GitWorker(["git", "reset", "--hard", self.last_head], self.repo_path)

            def on_undo_finished(success, stdout, stderr):
                if hasattr(self, 'progress_dialog'):
                    self.progress_dialog.close()

                if success:
                    self.load_history()
                    new_head = self.get_head_sha()
                    self.log_action(self.last_head, "undid last operation (reset hard to)", old_head, new_head)
                    QMessageBox.information(self, "Success", f"Successfully undid the last operation (reset to {self.last_head[:8]}).")
                    self.last_head = None
                    self.undo_btn.setEnabled(False)
                else:
                    QMessageBox.critical(self, "Undo Failed", f"Could not perform undo.\n\nError: {stderr}")
                    self.load_history()

            self.worker.finished.connect(on_undo_finished)
            self.worker.start()
            self.progress_dialog.exec()
        else:
            print(f"Cancelled undo (reset to {self.last_head[:8]}).")

    def handle_check_for_updates(self):
        """Checks for updates from the remote repository."""
        REPO_URL = "https://github.com/shyjun/git-interactive-rebase-gui-tool.git"
        UPDATE_URL = "https://github.com/shyjun/git-interactive-rebase-gui-tool?tab=readme-ov-file#-staying-updated"

        # 1. Find the tool's own directory
        tool_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        local_sha = "Unknown"
        is_git_install = os.path.exists(os.path.join(tool_dir, ".git"))

        # 2. Extract local SHA
        if is_git_install:
            try:
                res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tool_dir, capture_output=True, text=True, encoding='utf-8', errors='replace')
                if res.returncode == 0:
                    local_sha = res.stdout.strip()
            except:
                pass
        else:
            # Check for app_version.json (pip install case)
            try:
                from lib.utils import get_assets_path
                import json

                assets_dir = get_assets_path()
                json_path = os.path.join(assets_dir, "app_version.json")

                if os.path.exists(json_path):
                    with open(json_path, "r", encoding='utf-8') as f:
                        data = json.load(f)
                        local_sha = data.get("sha", "Unknown")
            except Exception:
                pass

        # 3. If no version info found, show manual update help
        if local_sha == "Unknown":
            msg = (
                "<b>Version Check Unavailable</b><br><br>"
                "Could not determine your current version (missing .git folder and app_version.json).<br><br>"
                f"Please check the <a href='{UPDATE_URL}'>Staying Updated</a> section in README for update instructions."
            )
            box = QMessageBox(self)
            box.setWindowTitle("Check for Updates")
            box.setText(msg)
            box.setTextFormat(Qt.RichText)
            box.setIcon(QMessageBox.Information)
            box.setStandardButtons(QMessageBox.Ok)
            box.exec()
            return

        # 4. Proceed with Remote check
        self.progress_dialog = ProgressDialog("Checking for Updates", "Connecting to GitHub...", self)

        self.worker = GitWorker(["git", "ls-remote", REPO_URL, "HEAD"], self.repo_path)

        def on_check_finished(success, stdout, stderr):
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.close()

            if not success or not stdout.strip():
                QMessageBox.warning(self, "Check Failed", "Could not check for updates. Please check your internet connection.")
                return

            remote_sha = stdout.split()[0]

            # Debug prints
            pass

            if remote_sha == local_sha:
                QMessageBox.information(self, "No Updates", "You are already using the latest version.")
            else:
                msg = (
                    "<b>Update Available!</b><br><br>"
                    "A newer version of the tool is available on GitHub.<br><br>"
                    f"Check out the <a href='{UPDATE_URL}'>Staying Updated</a> section in README for instructions."
                )
                box = QMessageBox(self)
                box.setWindowTitle("Update Available")
                box.setText(msg)
                box.setTextFormat(Qt.RichText)
                box.setIcon(QMessageBox.Information)
                box.setStandardButtons(QMessageBox.Ok)
                box.exec()

        self.worker.finished.connect(on_check_finished)
        self.worker.start()
        self.progress_dialog.exec()

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
            else:
                print(f"Cancelled custom reset to {sha}.")

    def handle_git_fetch(self):
        """Runs git fetch."""
        print("Running git fetch...")
        self.progress_dialog = ProgressDialog("Git Fetching", "git fetch in progress...", self)

        self.worker = GitWorker(["git", "fetch"], self.repo_path)
        self.worker.finished.connect(self.on_fetch_finished)
        self.worker.start()

        self.progress_dialog.exec()

    def on_fetch_finished(self, success, stdout, stderr):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()

        if success:
            QMessageBox.information(self, "Success", "Successfully ran 'git fetch'.")
            self.load_history()
        else:
            QMessageBox.critical(self, "Fetch Failed", f"Could not perform git fetch.\n\nError: {stderr}")


    def handle_git_reset_hard_origin(self):
        """Runs git reset --hard origin/<current_branch>."""
        branch = get_current_branch(self.repo_path)
        origin_ref = f"origin/{branch}"

        # Check if HEAD is already at origin_ref
        try:
            head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo_path).decode('utf-8').strip()
            origin_sha = subprocess.check_output(["git", "rev-parse", origin_ref], cwd=self.repo_path).decode('utf-8').strip()
            if head_sha == origin_sha:
                QMessageBox.information(self, "Nothing to do", f"Current HEAD is same as {origin_ref} HEAD. Nothing to do.")
                return
        except Exception:
            pass # Probably origin_ref doesn't exist, proceed to confirmation which will fail naturally if so

        reply = QMessageBox.question(
            self,
            "Confirm Reset to Origin",
            f"Are you sure you want to <b>reset --hard {origin_ref}</b>?<br><br>"
            f"This will discard all uncommitted changes and move your branch to '{origin_ref}'.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.save_undo_state()
            print(f"Resetting hard to {origin_ref}...")

            self.progress_dialog = ProgressDialog("Resetting", f"Resetting hard to {origin_ref}...", self)
            self.worker = GitWorker(["git", "reset", "--hard", origin_ref], self.repo_path)

            def on_origin_reset_finished(success, stdout, stderr):
                if hasattr(self, 'progress_dialog'):
                    self.progress_dialog.close()

                if success:
                    QMessageBox.information(self, "Success", f"Successfully reset --hard to {origin_ref}.")
                else:
                    QMessageBox.critical(self, "Reset Failed", f"Could not perform reset to {origin_ref}.\n\nError: {stderr}")

                self.load_history()

            self.worker.finished.connect(on_origin_reset_finished)
            self.worker.start()
            self.progress_dialog.exec()
        else:
            print(f"Cancelled reset hard to {origin_ref}.")

    def handle_git_push_force(self):
        """Runs git push --force."""
        reply = QMessageBox.question(
            self,
            "Confirm Force Push",
            "Are you sure you want to <b>push --force</b>?<br><br>"
            "This can overwrite history on the remote repository. Proceed with caution.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            print("Performing git push --force...")
            self.progress_dialog = ProgressDialog("Git Pushing", "git push --force in progress...", self)

            self.worker = GitWorker(["git", "push", "--force"], self.repo_path)
            self.worker.finished.connect(self.on_push_finished)
            self.worker.start()

            self.progress_dialog.exec()
        else:
            print("Cancelled force push.")

    def on_push_finished(self, success, stdout, stderr):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()

        if success:
            QMessageBox.information(self, "Success", "Successfully ran 'git push --force'.")
        else:
            QMessageBox.critical(self, "Push Failed", f"Could not perform git push --force.\n\nError: {stderr}")


    def update_rebase_buttons(self):
        """Updates the enabled state of rebase buttons based on branch existence."""
        has_master = branch_exists(self.repo_path, "master")
        has_main = branch_exists(self.repo_path, "main")

        self.rebase_master_btn.setEnabled(has_master)
        self.rebase_master_btn.setText("git rebase master" if has_master else "git rebase master (NA)")

        self.rebase_main_btn.setEnabled(has_main)
        self.rebase_main_btn.setText("git rebase main" if has_main else "git rebase main (NA)")

    def handle_git_rebase_master(self):
        self.perform_rebase("master")

    def handle_git_rebase_main(self):
        self.perform_rebase("main")

    def handle_git_rebase_custom(self):
        target, ok = QInputDialog.getText(self, 'Rebase', 'Enter branch or commit SHA to rebase on top of:')
        if ok and target.strip():
            self.perform_rebase(target.strip())

    def perform_rebase(self, target):
        """Performs git rebase <target> with confirmation."""
        reply = QMessageBox.question(
            self,
            "Confirm Rebase",
            f"Are you sure you want to <b>rebase</b> current branch on top of <b>{target}</b>?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.save_undo_state()
            old_head = self.get_head_sha()
            print(f"Rebasing onto {target}...")
            try:
                subprocess.run(["git", "rebase", target], cwd=self.repo_path, check=True, capture_output=True, text=True)
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(target, f"rebased onto {target}", old_head, new_head)
                QMessageBox.information(self, "Success", f"Successfully rebased onto {target}.")
            except subprocess.CalledProcessError as e:
                QMessageBox.critical(self, "Rebase Failed", f"Could not perform rebase onto {target}.\n\nError: {e.stderr}")

    def handle_zoom_in(self):
        self.current_font_size += 1
        self.update_font()

    def handle_zoom_out(self):
        if self.current_font_size > 6:
            self.current_font_size -= 1
            self.update_font()

    def on_theme_toggled(self):
        theme = "dark" if self.dark_radio.isChecked() else "light"
        self.is_dark_theme = (theme == "dark")
        self.apply_theme(theme)
        self.settings.setValue("theme", theme)
        self._refresh_toolbar_icons()
        if self.theme_menu_btn.menu():
            self.theme_menu_btn.menu().close()

    def on_origin_visibility_toggled(self):
        visible = self.show_origin_cb.isChecked()
        self.origin_group.setVisible(visible)
        self.settings.setValue("show_origin_options", visible)
        self.force_window_resize()

    def on_rebase_visibility_toggled(self):
        visible = self.show_rebase_cb.isChecked()
        self.rebase_group.setVisible(visible)
        self.settings.setValue("show_rebase_options", visible)
        self.force_window_resize()

    def on_squash_visibility_toggled(self):
        visible = self.show_squash_cb.isChecked()
        self.squash_group.setVisible(visible)
        self.settings.setValue("show_squash_options", visible)
        self.force_window_resize()

    def on_local_branches_visibility_toggled(self):
        self.show_local_branches = self.show_local_branches_cb.isChecked()
        self.settings.setValue("show_local_branches", self.show_local_branches)
        self.list_widget.viewport().update()

    def _on_stats_toggled(self):
        self.show_stats = self.show_stats_cb.isChecked()
        self.settings.setValue("show_stats", self.show_stats)
        self.list_widget.viewport().update()

    def _on_date_toggled(self):
        self.show_date = self.show_date_cb.isChecked()
        self.settings.setValue("show_date", self.show_date)
        self.list_widget.viewport().update()

    def _on_always_on_top_toggled(self, checked):
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

    def force_window_resize(self):
        """Forces the window to shrink to its minimum size hint if not maximized."""
        if self.isMaximized():
            # If maximized, resizing doesn't make sense and can cause glitches.
            # Just force the layout to re-evaluate and update visually.
            if self.centralWidget() and self.centralWidget().layout():
                self.centralWidget().layout().activate()
            self.update()
            return

        # A common trick to force a window to shrink in Qt is to
        # resize it to a very small height and then call adjustSize()
        self.resize(self.width(), 1)
        self.adjustSize()

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
                "accent": "#007acc",  # VS Code accent blue
                "separator": "#CCCCCC" # Neutral Slate Gray
            }
        else:
            self.current_theme_colors = {
                "added": "#228b22",  # Darker green for light bg
                "removed": "#b22222", # Darker red for light bg
                "header": "#00008b", # Darker blue for light bg
                "bg": "#f5f5f7",
                "fg": "#333333",
                "accent": "#007aff",
                "separator": "#CCCCCC" # Neutral Slate Gray
            }

        QApplication.instance().setStyleSheet(get_theme_stylesheet(theme_name))

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

        if hasattr(self, 'filewise_diff_view'):
            if hasattr(self, 'filewise_highlighter') and self.filewise_highlighter is not None:
                self.filewise_highlighter.setDocument(None)
            self.filewise_highlighter = DiffHighlighter(
                self.filewise_diff_view.document(),
                added_color=self.current_theme_colors["added"],
                removed_color=self.current_theme_colors["removed"],
                header_color=self.current_theme_colors["header"]
            )

        self.update_font()

    def update_font(self):
        font = QFont("Monospace", self.current_font_size)
        self.list_widget.setFont(font)
        if hasattr(self, 'side_diff_view'):
            self.side_diff_view.setFont(font)
        if hasattr(self, 'side_commit_msg'):
            self.side_commit_msg.setFont(font)
        if hasattr(self, 'filewise_diff_view'):
            self.filewise_diff_view.setFont(font)
        if hasattr(self, 'filewise_file_list'):
            self.filewise_file_list.setFont(font)
        # Save persistence
        self.settings.setValue("font_size", self.current_font_size)
        # Update status bar zoom label
        if hasattr(self, 'zoom_percent_label'):
            default_size = 10
            pct = int(self.current_font_size / default_size * 100)
            self.zoom_percent_label.setText(f"{pct}%")

    def show_context_menu(self, position):
        # Allow context menu in multi-select mode, but we will restrict it later
        pass

        item = self.list_widget.itemAt(position)
        if not item:
            return

        sha = item.text().split()[0]
        menu = QMenu()
        menu_font = QFont("Monospace", max(8, self.current_font_size - 2))
        menu.setFont(menu_font)

        mark_action = QAction(f"Mark / Unmark commit {sha}", self)
        view_action = QAction(f"Show / View commit {sha}", self)
        reset_action = QAction(f"Reset Hard to {sha}", self)
        set_best_action = QAction("set as BEST_COMMITID", self)
        drop_action = QAction("Drop", self)
        rephrase_action = QAction("Rephrase", self)
        revert_action = QAction("Revert", self)

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
            label = f"squash with above commit ({format_squash_label(above_item)})"
            squash_above_action = QAction(label, self)
            squash_above_action.triggered.connect(lambda: self.handle_squash_above(item))
        else:
            squash_above_action = QAction("squash with above commit (N/A)", self)
            squash_above_action.setEnabled(False)

        squash_below_action = None
        if index < count - 1:
            below_item = self.list_widget.item(index + 1)
            label = f"squash with below commit ({format_squash_label(below_item)})"
            squash_below_action = QAction(label, self)
            squash_below_action.triggered.connect(lambda: self.handle_squash_below(item))
        else:
            squash_below_action = QAction("squash with below commit (N/A)", self)
            squash_below_action.setEnabled(False)

        mark_action.triggered.connect(lambda: self.toggle_mark_commit(item))
        view_action.triggered.connect(lambda: self.view_commit(item))
        view_filewise_action = QAction(f"Show / View commit {sha} -- file-wise", self)
        view_filewise_action.triggered.connect(lambda: self.handle_view_commit_file_wise(item))
        reset_action.triggered.connect(lambda: self.handle_reset(item))
        set_best_action.triggered.connect(lambda: self.handle_set_best_commit(item))
        drop_action.triggered.connect(lambda: self.handle_drop(item))
        rephrase_action.triggered.connect(lambda: self.handle_rephrase(item))
        revert_action.triggered.connect(lambda: self.handle_revert_commit(item))
        copy_sha_action.triggered.connect(lambda: self.handle_copy_sha(item))
        copy_msg_action.triggered.connect(lambda: self.handle_copy_message(item))
        copy_sha_msg_action.triggered.connect(lambda: self.handle_copy_sha_and_message(item))

        # Disable most actions if in multi-select mode
        if self.multi_select_mode:
            mark_action.setEnabled(False)
            view_action.setEnabled(False)
            view_filewise_action.setEnabled(False)
            reset_action.setEnabled(False)
            set_best_action.setEnabled(False)
            drop_action.setEnabled(False)
            rephrase_action.setEnabled(False)
            revert_action.setEnabled(False)
            move_menu.setEnabled(False)
            copy_sha_action.setEnabled(False)
            copy_msg_action.setEnabled(False)
            copy_sha_msg_action.setEnabled(False)
            if squash_above_action: squash_above_action.setEnabled(False)
            if squash_below_action: squash_below_action.setEnabled(False)
        # Construct the menu

        menu.addAction(mark_action)
        menu.addSeparator()
        menu.addAction(view_action)
        menu.addAction(view_filewise_action)
        menu.addSeparator()
        menu.addAction(reset_action)
        menu.addAction(set_best_action)
        menu.addSeparator()
        menu.addAction(rephrase_action)
        menu.addAction(drop_action)
        menu.addAction(revert_action)
        menu.addSeparator()

        # Squash commits submenu
        squash_menu = menu.addMenu("Squash commits")
        squash_menu.setFont(menu_font)

        # Move individual squash actions here
        if squash_above_action:
            squash_menu.addAction(squash_above_action)
        if squash_below_action:
            squash_menu.addAction(squash_below_action)

        squash_menu.addSeparator()

        select_multi_action = QAction("Select commits to squash", self)
        select_multi_action.setEnabled(not self.multi_select_mode)
        select_multi_action.triggered.connect(self.enter_multi_select_mode)

        squash_selected_action = QAction("Squash selected commits", self)
        checked_count = 0
        if self.multi_select_mode:
            checked_count = sum(1 for i in range(self.list_widget.count())
                                if self.list_widget.item(i).checkState() == Qt.Checked)
        squash_selected_action.setEnabled(self.multi_select_mode and checked_count >= 2)
        squash_selected_action.triggered.connect(self.handle_squash_selected)

        cancel_multi_action = QAction("Cancel multi selection", self)
        cancel_multi_action.setEnabled(self.multi_select_mode)
        cancel_multi_action.triggered.connect(self.handle_cancel_multi_select)

        squash_menu.addAction(select_multi_action)
        squash_menu.addAction(squash_selected_action)
        squash_menu.addAction(cancel_multi_action)

        # Move Commit submenu
        move_menu = menu.addMenu("Move Commit")
        move_menu.setFont(menu_font)

        move_up_action = QAction("Move Up (Swap with Next/Above commit)", self)
        move_up_action.setEnabled(index > 0 and not self.multi_select_mode)
        move_up_action.triggered.connect(lambda: self.handle_move_up(item))

        move_down_action = QAction("Move Down (Swap with Previous/Below commit)", self)
        move_down_action.setEnabled(index < count - 1 and not self.multi_select_mode)
        move_down_action.triggered.connect(lambda: self.handle_move_down(item))

        drag_info_action = QAction("Drag to Reorder", self)
        drag_info_action.setEnabled(not self.multi_select_mode)
        drag_info_action.triggered.connect(lambda: self.handle_move_info(item))

        move_menu.addAction(move_up_action)
        move_menu.addAction(move_down_action)
        move_menu.addSeparator()
        move_menu.addAction(drag_info_action)

        # Split Commit submenu
        split_menu = menu.addMenu("Split Commit")
        split_menu.setFont(menu_font)

        try:
            files_changed = get_commit_files(self.repo_path, sha)
            has_multiple_files = len(files_changed) > 1
        except Exception:
            has_multiple_files = False

        split_drop_file_action = QAction("drop changes from one file from this commit", self)
        split_drop_file_action.triggered.connect(lambda: self.handle_split_drop_file(item))
        split_drop_file_action.setEnabled(has_multiple_files)
        split_menu.addAction(split_drop_file_action)

        split_move_out_action = QAction("move one file changes out of this commit", self)
        split_move_out_action.triggered.connect(lambda: self.handle_split_commit(item))
        split_menu.addAction(split_move_out_action)

        split_all_action = QAction("split all changes to separate commits", self)
        split_all_action.triggered.connect(lambda: self.handle_split_all_commits(item))
        split_menu.addAction(split_all_action)

        split_per_file_action = QAction("split each file changes to separate commit", self)
        split_per_file_action.triggered.connect(lambda: self.handle_split_per_file(item))
        split_menu.addAction(split_per_file_action)

        split_menu.addSeparator()
        split_refine_action = QAction("Refine/Edit changes in selected file", self)
        split_refine_action.triggered.connect(lambda: self.handle_refine_changes(item))
        split_menu.addAction(split_refine_action)

        menu.addSeparator()
        menu.addAction(copy_sha_action)
        menu.addAction(copy_msg_action)
        menu.addAction(copy_sha_msg_action)
        menu.exec(self.list_widget.mapToGlobal(position))

    def handle_move_info(self, item):
        QMessageBox.information(
            self,
            "Move Commit",
            "Any commit can be dragged and dropped to a new position to reorder.\n\n"
            "Simply click and hold a commit, then drag it to where you want it."
        )

    def handle_move_up(self, item):
        """Swaps the selected commit with the one above it (Towards HEAD)."""
        idx = self.list_widget.row(item)
        if idx <= 0:
            return

        sha = item.text().split()[0]

        reply = QMessageBox.question(
            self,
            "Confirm Move Up",
            f"Are you sure you want to move commit <b>{sha}</b> up?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        old_head = self.get_head_sha()
        current_shas = [self.list_widget.item(i).text().split()[0] for i in range(self.list_widget.count())]
        # Swap with older (idx-1)
        current_shas[idx], current_shas[idx-1] = current_shas[idx-1], current_shas[idx]

        if self.run_interactive_rebase(current_shas, progress_title="Moving Commit", progress_text=f"Moving commit {sha} up..."):
            self.load_history()
            # Select the moved commit at its new index (idx - 1)
            target_idx = max(0, idx - 1)
            self.list_widget.setCurrentRow(target_idx)

            new_head = self.get_head_sha()
            self.log_action(sha, "moved up", old_head, new_head)
            QMessageBox.information(self, "Success", "Commit moved successfully.")

    def handle_move_down(self, item):
        """Swaps the selected commit with the one below it (Away from HEAD)."""
        idx = self.list_widget.row(item)
        if idx >= self.list_widget.count() - 1:
            return

        sha = item.text().split()[0]

        reply = QMessageBox.question(
            self,
            "Confirm Move Down",
            f"Are you sure you want to move commit <b>{sha}</b> down?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        old_head = self.get_head_sha()
        current_shas = [self.list_widget.item(i).text().split()[0] for i in range(self.list_widget.count())]
        # Swap with newer (idx+1)
        current_shas[idx], current_shas[idx+1] = current_shas[idx+1], current_shas[idx]

        if self.run_interactive_rebase(current_shas, progress_title="Moving Commit", progress_text=f"Moving commit {sha} down..."):
            self.load_history()
            # Select the moved commit at its new index (idx + 1)
            target_idx = min(self.list_widget.count() - 1, idx + 1)
            self.list_widget.setCurrentRow(target_idx)

            new_head = self.get_head_sha()
            self.log_action(sha, "moved down", old_head, new_head)
            QMessageBox.information(self, "Success", "Commit moved successfully.")

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
            else:
                print(f"Cancelled rephrase {sha}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch commit message: {str(e)}")

    def perform_rephrase(self, sha, new_message):
        """Executes the rephrase using unified rebase logic."""
        old_head = self.get_head_sha()
        try:
            # Current list of SHAs in UI
            current_shas = []
            for i in range(self.list_widget.count()):
                current_shas.append(self.list_widget.item(i).text().split()[0])

            if self.run_interactive_rebase(current_shas, rephrase_map={sha: new_message}, progress_title="Rephrasing Commit", progress_text=f"Rephrasing commit {sha}. Please wait..."):
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha, "rephrased", old_head, new_head)
                QMessageBox.information(self, "Success", f"Commit {sha} rephrased successfully.")
                return

            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while rephrasing: {str(e)}")
            self.load_history()

    def handle_revert_commit(self, item):
        """Handles the 'Revert this commit' context menu action."""
        sha = item.text().split()[0]
        print(f"Preparing to revert {sha}...")
        try:
            default_message = get_revert_commit_message(self.repo_path, sha)
            dialog = RevertCommitDialog(sha, default_message, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                revert_message = dialog.get_message()
                self.perform_revert_commit(sha, revert_message)
            else:
                print(f"Cancelled revert {sha}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not prepare revert: {str(e)}")

    def perform_revert_commit(self, sha, revert_message):
        """Executes git revert --no-commit then commits with the edited message."""
        self.save_undo_state()
        old_head = self.get_head_sha()
        progress = ProgressDialog("Reverting Commit", f"Reverting {sha}...", self)
        progress.show()
        QApplication.processEvents()
        try:
            # Revert without auto-committing so we can supply our own message
            subprocess.run(
                ["git", "revert", "--no-commit", sha],
                cwd=self.repo_path, check=True, capture_output=True, text=True
            )
            # Commit with the (possibly edited) revert message
            progress.label.setText("Committing revert...")
            QApplication.processEvents()
            subprocess.run(
                ["git", "commit", "-m", revert_message],
                cwd=self.repo_path, check=True, capture_output=True, text=True
            )
            progress.close()
            self.load_history()
            new_head = self.get_head_sha()
            self.log_action(sha, "reverted", old_head, new_head)
            QMessageBox.information(self, "Success", f"Commit {sha} reverted successfully.")
        except subprocess.CalledProcessError as e:
            progress.close()
            # Abort any lingering revert state so the repo stays clean
            subprocess.run(["git", "revert", "--abort"], cwd=self.repo_path, capture_output=True)
            QMessageBox.critical(self, "Revert Failed",
                                 f"Could not revert commit {sha}.\n\nError: {e.stderr}")
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

    def toggle_mark_commit(self, item):
        sha = item.text().split()[0]

        if sha in self.marked_shas:
            self.marked_shas.remove(sha)
        else:
            self.marked_shas.add(sha)

        # Repaint to immediately apply the delegate's background fill
        self.list_widget.viewport().update()

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
        else:
            print(f"Cancelled reset to {sha}.")

    def perform_reset(self, sha):
        old_head = self.get_head_sha()
        print(f"Resetting hard to {sha}...")
        self.save_undo_state()

        self.progress_dialog = ProgressDialog("Resetting", f"Resetting hard to {sha[:10]}...", self)

        self.worker = GitWorker(["git", "reset", "--hard", sha], self.repo_path)

        def on_reset_finished(success, stdout, stderr):
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.close()

            if success:
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha, "reset hard to", old_head, new_head)
                QMessageBox.information(self, "Success", f"Successfully reset --hard to {sha[:10]}.")
            else:
                QMessageBox.critical(self, "Reset Failed", f"Could not perform reset.\n\nError: {stderr}")

        self.worker.finished.connect(on_reset_finished)
        self.worker.start()
        self.progress_dialog.exec()

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
            else:
                print(f"Cancelled squash {sha_above} into {sha_current}.")
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
            else:
                print(f"Cancelled squash {sha_current} into {sha_below}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not prepare squash: {str(e)}")

    def perform_squash(self, sha_to_squash, final_msg):
        """Executes the squash using unified rebase logic."""
        old_head = self.get_head_sha()
        try:
            # Current list of SHAs in UI
            current_shas = []
            for i in range(self.list_widget.count()):
                current_shas.append(self.list_widget.item(i).text().split()[0])

            # Use final_msg for the rebase - we associate it with the SHA being squashed
            # so the amend happens right after the squash command in the todo list.
            if self.run_interactive_rebase(current_shas, squash_shas=[sha_to_squash],
                                          rephrase_map={sha_to_squash: final_msg}):
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha_to_squash, "squashed", old_head, new_head)
                QMessageBox.information(self, "Success", "Commits squashed successfully.")
                return

            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while squashing: {str(e)}")
            self.load_history()

    # ---- Multi-select / Squash mode ----

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
        self.squash_selected_btn.setEnabled(False)
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
        self.squash_selected_btn.setEnabled(False)
        self.cancel_multi_btn.setEnabled(False)

    def on_multi_select_changed(self, changed_item):
        """Enables 'Squash selected commits' only when ≥ 2 commits are checked."""
        if not self.multi_select_mode:
            return
        checked_count = sum(
            1 for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == Qt.Checked
        )
        self.squash_selected_btn.setEnabled(checked_count >= 2)

    def handle_cancel_multi_select(self):
        """Cancels multi-select mode without merging."""
        self.exit_multi_select_mode()

    def handle_squash_selected(self):
        """Collects checked commits, validates contiguity, confirms, then squashes."""
        # Collect selected indices and SHAs in list order (newest → oldest)
        selected_indices = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                selected_indices.append(i)

        if len(selected_indices) < 2:
            QMessageBox.warning(self, "Not Enough Selected", "Please select at least 2 commits to squash.")
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

            # The oldest item (last in our list) is the "pick" target; rest become squash
            # List is newest -> oldest
            base_sha = selected_shas[-1]
            squash_shas = selected_shas[:-1]
            # Use the newest commit in the group to apply the final message via --amend
            rephrase_sha = selected_shas[0]

            # Open the N-option message selection dialog directly
            dialog = MultiSquashDialog(sha_msg_pairs, self.current_font_size, self)
            if dialog.exec() != QDialog.Accepted:
                return  # finally block handles cleanup

            final_msg = dialog.get_message()

            # Build all SHAs list from current view
            all_shas = [self.list_widget.item(i).text().split()[0] for i in range(self.list_widget.count())]

            if self.run_interactive_rebase(all_shas, squash_shas=squash_shas, rephrase_map={rephrase_sha: final_msg}, progress_title="Squashing Commits", progress_text="Squashing selected commits together. Please wait..."):
                self.load_history()
                QMessageBox.information(self, "Success", f"Successfully squashed {len(selected_shas)} commits.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while merging: {str(e)}")
        finally:
            self.exit_multi_select_mode()
            self.load_history()

    def handle_drop(self, item):
        sha = item.text().split()[0]
        print(f"Preparing to drop {sha}...")

        # Guard: if this is the only commit in the list and we're in branch-detection
        # mode, dropping it is equivalent to a hard-reset to the base — not supported.
        if self.list_widget.count() == 1 and self.base_branch:
            base_sha_short = self.commit_sha[:8] if self.commit_sha else "<base>"
            QMessageBox.information(
                self,
                "Drop",
                f"This is the only unique commit in your branch.\n"
                f"If you do this, it's as good as resetting hard to "
                f"branch: {self.base_branch} or {base_sha_short}\n\n"
                "App doesn't support doing this when run in unique-changes branch mode.\n"
                "To drop this commit, run the app with an explicit number of commits as argument."
            )
            return

        try:
            diff_text = get_commit_diff(self.repo_path, sha)
            dialog = DropDialog(sha, diff_text, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                self.perform_drop(sha)
            else:
                print(f"Cancelled drop {sha}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def perform_drop(self, sha):
        """Drops a commit using our unified rebase logic."""
        old_head = self.get_head_sha()
        try:
            # Current list of SHAs in UI
            current_shas = []
            for i in range(self.list_widget.count()):
                current_shas.append(self.list_widget.item(i).text().split()[0])

            # New list without the dropped SHA
            new_shas = [s for s in current_shas if s != sha]

            if self.run_interactive_rebase(new_shas, progress_title="Dropping Commit", progress_text=f"Dropping commit {sha}. Please wait..."):
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha, "dropped", old_head, new_head)
                QMessageBox.information(self, "Success", f"Commit {sha} dropped successfully.")
                return

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
            else:
                print(f"Cancelled split/move file from {sha}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open split dialog: {str(e)}")

    # ─────────────────────────────────────────────────────────────────
    #  Refine Changes in Selected File
    # ─────────────────────────────────────────────────────────────────

    def handle_refine_changes(self, item):
        """Opens RefineFileSelectDialog to let user pick a file to refine."""
        sha = item.text().split()[0]
        try:
            files = get_commit_files(self.repo_path, sha)
            if not files:
                QMessageBox.information(self, "No Files",
                                        f"Commit {sha} has no file changes.")
                return

            dialog = RefineFileSelectDialog(self.repo_path, sha, files,
                                            self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                selected_file = dialog.get_selected_file()
                if selected_file:
                    self.perform_refine_changes(sha, selected_file)
            else:
                print(f"Cancelled refine {sha}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open refine dialog: {str(e)}")

    @staticmethod
    def _parse_hunks(diff_text):
        """
        Parse a unified diff (for one file) into a list of (header_line, body_text) tuples.
        header_line: the '@@ … @@' line (stripped)
        body_text:   the context/+/- lines that follow, as a single string
        """
        hunks = []
        current_header = None
        current_body_lines = []
        for line in diff_text.splitlines():
            if line.startswith("@@"):
                if current_header is not None:
                    hunks.append((current_header, "\n".join(current_body_lines)))
                current_header = line
                current_body_lines = []
            elif current_header is not None:
                current_body_lines.append(line)
        if current_header is not None:
            hunks.append((current_header, "\n".join(current_body_lines)))
        return hunks

    @staticmethod
    def _rebuild_patch(diff_header_text, all_hunks, kept_indices):
        """
        Build a minimal unified-diff patch string that contains only the kept hunks.
        Recalculates the +line offsets so 'git apply' accepts the patch cleanly.

        diff_header_text: the part of the diff before the first @@ (diff --git / --- / +++)
        all_hunks:        list of (header_line, body_text) for ALL hunks
        kept_indices:     indices into all_hunks that should appear in the result
        """
        if not kept_indices:
            return ""

        # Parse the original @@ -a,b +c,d @@ tails
        import re

        patch_parts = [diff_header_text]
        cumulative_offset = 0
        for idx in kept_indices:
            orig_hdr, body = all_hunks[idx]
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", orig_hdr)
            if not m:
                patch_parts.append(orig_hdr)
                patch_parts.append(body)
                continue

            minus_start = int(m.group(1))
            plus_start  = int(m.group(3))
            orig_plus_count = int(m.group(4)) if m.group(4) is not None else 1
            tail        = m.group(5)

            new_plus_start = plus_start + cumulative_offset

            # Count lines from body (splitlines preserves empty lines at end if keepends=False + trailing check)
            body_lines = body.split("\n")
            # Remove a single trailing empty string caused by a trailing \n
            if body_lines and body_lines[-1] == "":
                body_lines = body_lines[:-1]

            real_plus_count = sum(1 for l in body_lines if not l.startswith('-'))
            real_minus_count = sum(1 for l in body_lines if not l.startswith('+'))

            new_hdr = f"@@ -{minus_start},{real_minus_count} +{new_plus_start},{real_plus_count} @@{tail}"
            # Reconstruct body ensuring each line ends with \n
            body_text = "\n".join(body_lines) + "\n"

            patch_parts.append(new_hdr)
            patch_parts.append(body_text)

            # Update cumulative offset for subsequent hunks
            cumulative_offset += (real_plus_count - orig_plus_count)

        return "".join(f"{p}\n" if not p.endswith("\n") else p for p in patch_parts)

    def perform_refine_changes(self, sha, filepath):
        """
        Opens the hunk-selection dialog and, on acceptance, rewrites the commit
        so that only the selected hunks of `filepath` are kept.
        Keeps the dialog open and refreshes it until the user cancels.
        """
        while True:
            try:
                raw_diff = get_file_diff_only_in_commit(self.repo_path, sha, filepath)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not load diff for {filepath}: {e}")
                break

            hunks = self._parse_hunks(raw_diff)
            if not hunks:
                QMessageBox.information(self, "No Hunks",
                                        f"No individual hunks found for {filepath} in commit {sha}.")
                break


            try:
                commit_msg = get_full_commit_message(self.repo_path, sha)
            except Exception:
                commit_msg = ""

            try:
                all_files = get_commit_files(self.repo_path, sha)
            except:
                all_files = [filepath]
            is_only_file = len(all_files) == 1

            dialog = RefineChangesDialog(sha, filepath, commit_msg,
                                         hunks, self.current_font_size, self, is_only_file=is_only_file)

            # When user clicks "Apply modification" in a hunk menu, treat it as a final "Keep Selected" action
            dialog.apply_hunk_modification.connect(dialog._on_keep)
            dialog.drop_hunk.connect(dialog._on_keep)

            if dialog.exec() != QDialog.Accepted:
                break

            result_action = getattr(dialog, 'result_action', 'keep')
            all_hunks = dialog.get_hunk_data() if hasattr(dialog, 'get_hunk_data') else hunks
            kept_indices = dialog.kept_indices
            moved_indices = getattr(dialog, 'moved_indices', [])

            # Bug fix: if it's the only file and we result in an empty commit, warn user
            # (is_only_file already computed above)

            if not kept_indices:
                if is_only_file:
                    action_name = "Drop" if result_action != "move" else "Move All"
                    feature_name = "Drop Commit" if result_action != "move" else "Move file changes out of this commit"
                    QMessageBox.information(
                        self, "Empty Commit",
                        f"You have selected to {action_name} all changes from the only file in this commit.\n\n"
                        f"This would result in an empty commit. Please use the dedicated '{feature_name}' feature instead."
                    )
                    break
                else:
                    # If there are other files, it's okay to drop all hunks from this one.
                    pass

            move_msg = ""
            if result_action == "move":
                default_msg = f"Change hunk from {sha[:8]} in {filepath}"
                dialog = NewCommitMessageDialog(
                    "New Commit Message",
                    "Enter commit message for the new commit (containing moved hunks):",
                    default_msg,
                    self.current_font_size,
                    self
                )
                if dialog.exec() != QDialog.Accepted:
                    break
                move_msg = dialog.get_message()

            self.save_undo_state()
            old_head = self.get_head_sha()

            # Build the partial patch (or empty string for full-drop)
            # Extract the diff header lines (up to first @@)
            header_lines = []
            for line in raw_diff.splitlines():
                if line.startswith("@@"):
                    break
                header_lines.append(line)
            diff_header_text = "\n".join(header_lines)

            partial_patch = self._rebuild_patch(diff_header_text, all_hunks, kept_indices)
            # DEBUG: partial_patch prints removed
            move_patch = ""
            if result_action == "move":
                move_patch = self._rebuild_patch(diff_header_text, all_hunks, moved_indices)

            action_script_content = f"""#!/usr/bin/env python3
import subprocess, os, tempfile, sys

sha = {repr(sha)}
filepath = {repr(filepath)}
commit_msg = {repr(commit_msg)}
partial_patch = {repr(partial_patch)}
move_patch = {repr(move_patch)}
move_msg = {repr(move_msg)}
result_action = {repr(result_action)}

# 1. Soft-reset so the commit's changes go back into the staging area
subprocess.check_call(['git', 'reset', '--soft', 'HEAD~1'])

# 2. Restore this file to the state it had BEFORE the commit (parent's version)
subprocess.check_call(['git', 'checkout', 'HEAD', '--', filepath])

# 3. Apply the 'keep' patch (the ones that stay in original commit)
if partial_patch.strip():
    patch_fd, patch_path = tempfile.mkstemp(prefix='git_refine_keep_', suffix='.patch', text=True)
    with os.fdopen(patch_fd, 'w', encoding='utf-8') as pf:
        pf.write(partial_patch)
    try:
        subprocess.check_call(['git', 'apply', '--ignore-whitespace', patch_path])
        subprocess.check_call(['git', 'add', '--', filepath])
    except subprocess.CalledProcessError as e:
        print(f"FAILED to apply refinement patch for {{filepath}} in {{sha}}")
        print(f"Error: {{e}}")
        sys.exit(1)
    finally:
        try:
            os.unlink(patch_path)
        except:
            pass

# 4. Commit original changes (the ones we kept)
#    Use --allow-empty as a safety safeguard.
msg_fd, msg_path = tempfile.mkstemp(prefix='git_msg_orig_', text=True)
with os.fdopen(msg_fd, 'w', encoding='utf-8') as f:
    f.write(commit_msg)
try:
    subprocess.check_call(['git', 'commit', '--allow-empty', '-F', msg_path])
finally:
    try:
        os.unlink(msg_path)
    except:
        pass

# 5. If we are moving, apply the 'move' patch and commit again
if result_action == "move" and move_patch.strip():
    patch_fd, patch_path = tempfile.mkstemp(prefix='git_refine_move_', suffix='.patch', text=True)
    with os.fdopen(patch_fd, 'w', encoding='utf-8') as pf:
        pf.write(move_patch)
    try:
        subprocess.check_call(['git', 'apply', '--ignore-whitespace', patch_path])
        subprocess.check_call(['git', 'add', '--', filepath])
    except subprocess.CalledProcessError as e:
        print(f"FAILED to apply move patch for {{filepath}} in {{sha}}")
        print(f"Error: {{e}}")
        sys.exit(1)
    finally:
        try:
            os.unlink(patch_path)
        except:
            pass

    msg_fd, msg_path = tempfile.mkstemp(prefix='git_msg_move_', text=True)
    with os.fdopen(msg_fd, 'w', encoding='utf-8') as f:
        f.write(move_msg)
    try:
        subprocess.check_call(['git', 'commit', '--allow-empty', '-F', msg_path])
    finally:
        try:
            os.unlink(msg_path)
        except:
            pass
"""
            action_fd, action_path = tempfile.mkstemp(prefix='git_refine_exec_', suffix='.py', text=True)
            with os.fdopen(action_fd, 'w', encoding='utf-8') as f:
                f.write(action_script_content)
            os.chmod(action_path, os.stat(action_path).st_mode | stat.S_IEXEC)

            single_exec = f"exec python3 {action_path}"

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
                f.write("    stripped = line.strip()\n")
                f.write("    parts = stripped.split()\n")
                f.write("    # Match pick/reword/edit etc. followed by SHA\n")
                f.write("    if not stripped.startswith('#') and len(parts) >= 2 and len(parts[1]) >= 4:\n")
                f.write("        todo_sha = parts[1]\n")
                f.write(f"        if {repr(sha)}.startswith(todo_sha) or todo_sha.startswith({repr(sha[:4])}):\n")
                f.write("             output.append('pick ' + stripped.split(None, 1)[1] + '\\n')\n")
                f.write("             output.append(single_exec + '\\n')\n")
                f.write("             continue\n")
                f.write("    output.append(line)\n")
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
                if not has_parent:
                    QMessageBox.critical(self, "Cannot Refine",
                                         "Cannot refine the oldest commit (no parent).\n"
                                         "This operation only works when the commit has a parent.")
                    break
                upstream = f"{sha}^"
            else:
                upstream = current_shas[sha_idx + 1]

            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = editor_script
            env["GIT_EDITOR"] = "true"

            progress = ProgressDialog(
                f"Applying refinement to {sha[:8]}...",
                f"Processing changes in {filepath}. Please wait...",
                self
            )
            progress.show()
            # Force visibility and add a small delay for human perception
            for _ in range(5):
                QApplication.processEvents()
                time.sleep(0.02)

            cmd = ["git", "rebase", "-i", upstream]
            result = subprocess.run(cmd, cwd=self.repo_path, env=env,
                                    capture_output=True, text=True)

            # Ensure the user sees the progress before it closes
            for _ in range(5):
                QApplication.processEvents()
                time.sleep(0.02)
            progress.close()

            try:
                os.unlink(editor_script)
                os.unlink(action_path)
            except Exception:
                pass

            if result.returncode == 0:
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha, f"refined {filepath}", old_head, new_head)
                # Find the new SHA at the same position to allow refreshing the dialog
                new_shas = [self.list_widget.item(i).text().split()[0]
                            for i in range(self.list_widget.count())]
                if sha_idx >= 0 and sha_idx < len(new_shas):
                    sha = new_shas[sha_idx]

                QMessageBox.information(self, "Success",
                                        f"Successfully refined changes for '{filepath}' in commit {sha[:8]}.\n\n"
                                        "The Refine/Edit window will now refresh.")
            else:
                print(f"Refine Changes: FAILED. {result.stderr}")
                subprocess.run(["git", "rebase", "--abort"],
                               cwd=self.repo_path, capture_output=True)
                QMessageBox.critical(
                    self,
                    "Refine Failed",
                    f"Could not apply refined changes.\n\n"
                    f"Patch failed to apply during rebase.\n\n"
                    f"Error:\n{result.stderr}\n\n"
                    f"If needed, resolve the issue manually and run:\n\n"
                    f"git rebase --continue"
                )
                self.load_history()
                break

    def perform_move_file_out(self, sha, filepath):
        """
        Moves a single file's changes out of a commit into a new commit after it.
        """
        old_head = self.get_head_sha()
        self.save_undo_state()
        try:
            all_files = get_commit_files(self.repo_path, sha)
            other_files = [f for f in all_files if f != filepath]
            short_sha = sha[:8]

            if not other_files:
                QMessageBox.information(self, "Info", f"File '{filepath}' is the only modified file in this commit. Nothing to split.")
                return

            # Show confirmation dialog with file diff
            try:
                diff_text = get_file_diff_only_in_commit(self.repo_path, sha, filepath)
            except Exception:
                diff_text = "Could not load diff for this file."

            confirm_dialog = ConfirmMoveFileDialog(sha, filepath, diff_text, self.current_font_size, self)
            if confirm_dialog.exec() != QDialog.Accepted:
                return

            original_msg = get_full_commit_message(self.repo_path, sha)
            new_msg = f"{filepath} changes separated out from {short_sha}\n\n{original_msg}"

            # Action script content
            action_script_content = f"""#!/usr/bin/env python3
import subprocess, os, tempfile, sys

sha = {repr(sha)}
filepath = {repr(filepath)}
new_msg = {repr(new_msg)}

# 1. Soft-reset to unstage the commit
subprocess.check_call(['git', 'reset', '--soft', 'HEAD~1'])
# 2. Un-stage the target file from the index
subprocess.check_call(['git', 'reset', 'HEAD', '--', filepath])
# 3. Re-commit the remaining files with the original commit message
subprocess.check_call(['git', 'commit', '-C', sha])
# 4. Stage the target file
subprocess.check_call(['git', 'add', '--all', '--', filepath])
# 5. Commit the target file with the new descriptive message
msg_fd, msg_path = tempfile.mkstemp(prefix='git_msg_', text=True)
with os.fdopen(msg_fd, 'w', encoding='utf-8') as f:
    f.write(new_msg)
try:
    subprocess.check_call(['git', 'commit', '-F', msg_path])
finally:
    try:
        os.unlink(msg_path)
    except:
        pass
"""
            action_fd, action_path = tempfile.mkstemp(prefix='git_split_action_', suffix='.py', text=True)
            with os.fdopen(action_fd, 'w', encoding='utf-8') as f:
                f.write(action_script_content)
            os.chmod(action_path, os.stat(action_path).st_mode | stat.S_IEXEC)

            single_exec = f"exec python3 {action_path}"

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

            progress = ProgressDialog("Moving File Out", f"Moving '{filepath}' out of commit {short_sha}...", self)
            self.split_worker = SplitWorker(cmd, self.repo_path, env)

            def on_split_finished(returncode, stdout, stderr):
                try:
                    if progress.isVisible():
                        progress.close()
                    try:
                        os.unlink(editor_script)
                        os.unlink(action_path)
                    except:
                        pass

                    if returncode == 0:
                        self.load_history()
                        new_head = self.get_head_sha()
                        self.log_action(sha, f"moved {filepath} out of", old_head, new_head)
                        QMessageBox.information(self, "Success",
                            f"File '{filepath}' has been moved out of commit {short_sha}.\n\n"
                            f"A new commit was created with message: \"{filepath} changes separated out from {short_sha}\"")
                    else:
                        subprocess.run(["git", "rebase", "--abort"],
                                       cwd=self.repo_path, capture_output=True)
                        QMessageBox.critical(self, "Split Failed",
                            f"The split operation failed and has been aborted.\n\n"
                            f"Error: {stderr}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
                finally:
                    self.load_history()

            self.split_worker.finished.connect(on_split_finished)
            self.split_worker.start()
            progress.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
            self.load_history()

    def handle_split_drop_file(self, item):
        """Opens DropFileFromCommitDialog to allow dropping a file from a commit."""
        sha = item.text().split()[0]
        try:
            files = get_commit_files(self.repo_path, sha)
            if not files:
                QMessageBox.information(self, "No Files", f"Commit {sha} has no file changes to drop.")
                return
            if len(files) == 1:
                QMessageBox.warning(self, "Warning", "This commit has changes only in 1 file.")
                return

            dialog = DropFileFromCommitDialog(self.repo_path, sha, files, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                selected_file = dialog.get_selected_file()
                if selected_file:
                    self.perform_drop_file_from_commit(sha, selected_file)
            else:
                print(f"Cancelled drop file from {sha}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open drop file dialog: {str(e)}")

    def perform_drop_file_from_commit(self, sha, filepath):
        """
        Drops a single file's changes from a commit without moving it to a new one.
        """
        old_head = self.get_head_sha()
        self.save_undo_state()
        try:
            all_files = get_commit_files(self.repo_path, sha)
            other_files = [f for f in all_files if f != filepath]
            short_sha = sha[:8]

            if not other_files:
                QMessageBox.information(self, "Info", f"File '{filepath}' is the only modified file in this commit. Dropping it means dropping the commit completely. Use Drop action instead.")
                return

            # Show confirmation dialog with file diff
            try:
                diff_text = get_file_diff_only_in_commit(self.repo_path, sha, filepath)
            except Exception:
                diff_text = "Could not load diff for this file."

            confirm_dialog = ConfirmDropFileDialog(sha, filepath, diff_text, self.current_font_size, self)
            if confirm_dialog.exec() != QDialog.Accepted:
                return

            # Action script content for dropping
            action_script_content = f"""#!/usr/bin/env python3
import subprocess, sys

sha = {repr(sha)}
filepath = {repr(filepath)}

# 1. Soft-reset to unstage the commit
subprocess.check_call(['git', 'reset', '--soft', 'HEAD~1'])
# 2. Un-stage the target file from the index so it won't be committed
subprocess.check_call(['git', 'reset', 'HEAD', '--', filepath])
# 3. Commit the remaining files with the original commit message
subprocess.check_call(['git', 'commit', '-C', sha])
# 4. Discard the unstaged changes to drop them
subprocess.check_call(['git', 'reset', '--hard', 'HEAD'])
# 5. Clean untracked files (in case the dropped change was a new file)
subprocess.check_call(['git', 'clean', '-fd', '--', filepath])
"""
            import tempfile, os, stat
            action_fd, action_path = tempfile.mkstemp(prefix='git_drop_action_', suffix='.py', text=True)
            with os.fdopen(action_fd, 'w', encoding='utf-8') as f:
                f.write(action_script_content)
            os.chmod(action_path, os.stat(action_path).st_mode | stat.S_IEXEC)

            single_exec = f"exec python3 {action_path}"

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

            try:
                os.unlink(editor_script)
                os.unlink(action_path)
            except:
                pass

            if result.returncode == 0:
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha, f"dropped {filepath} from", old_head, new_head)
                QMessageBox.information(self, "Success",
                    f"File '{filepath}' changes have been dropped from commit {short_sha}.")
            else:
                subprocess.run(["git", "rebase", "--abort"],
                               cwd=self.repo_path, capture_output=True)
                QMessageBox.critical(self, "Drop Failed",
                    f"The drop operation failed and has been aborted.\n\n"
                    f"Error: {result.stderr}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred during drop: {str(e)}")
        finally:
            self.load_history()

    def perform_remove_file_from_commit_onwards(self, sha, filepath):
        """
        Removes a file from the selected commit and ensures it stays removed
        in all subsequent commits. Useful for cleaning accidentally committed files.
        """
        print(f"[{time.strftime('%H:%M:%S')}] Remove file onwards: starting for file='{filepath}' commit={sha}")
        old_head = self.get_head_sha()
        print(f"[{time.strftime('%H:%M:%S')}] Remove file onwards: starting SHA={self.commit_sha}, selected commit={sha}, HEAD before={old_head}")
        self.save_undo_state()
        try:
            short_sha = sha[:8]

            current_shas = [self.list_widget.item(i).text().split()[0]
                            for i in range(self.list_widget.count())]
            sha_idx = current_shas.index(sha) if sha in current_shas else -1

            commits_to_drop = []
            if sha_idx >= 0:
                # Items before sha_idx are newer commits (since list is newest-first)
                # This naturally processes commits chronologically backward (newest to oldest)
                for i in range(sha_idx + 1):
                    c_sha = current_shas[i]
                    try:
                        c_files = get_commit_files(self.repo_path, c_sha)
                        if filepath in c_files:
                            c_msg = get_full_commit_message(self.repo_path, c_sha)
                            will_be_empty = (len(c_files) == 1)
                            commits_to_drop.append((c_sha, c_msg, will_be_empty))
                    except Exception:
                        pass
            else:
                QMessageBox.warning(self, "Error", "Commit not found in list.")
                return

            later_modifications_detected = len(commits_to_drop) > 1
            has_empty_commits = any(w for _, _, w in commits_to_drop)

            # Show file diff for context
            try:
                diff_text = get_file_diff_only_in_commit(self.repo_path, sha, filepath)
            except Exception:
                diff_text = "Could not load diff for this file."

            confirm_dialog = ConfirmRemoveFileOnwardsDialog(
                sha, filepath, diff_text,
                later_modifications_detected=later_modifications_detected,
                font_size=self.current_font_size, parent=self
            )
            if confirm_dialog.exec() != QDialog.Accepted:
                return

            drop_empty_commits = False

            if later_modifications_detected:
                future_commits = [(s, m) for s, m, _ in commits_to_drop if s != sha]
                agg_dialog = AggressiveRemoveConfirmationDialog(
                    filepath, future_commits, has_empty_commits=has_empty_commits, font_size=self.current_font_size, parent=self
                )
                if agg_dialog.exec() != QDialog.Accepted:
                    return
                drop_empty_commits = agg_dialog.drop_empty_checkbox.isChecked() if has_empty_commits else False

            progress = ProgressDialog(
                f"Removing {filepath}",
                "Preparing history rewrite...",
                self
            )
            progress.show()
            for _ in range(5):
                QApplication.processEvents()
                time.sleep(0.02)

            empty_commits_dropped_count = 0

            for index, (drop_sha, msg, will_be_empty) in enumerate(commits_to_drop):
                progress.label.setText(f"Rewriting commit {index+1}/{len(commits_to_drop)}...\n({drop_sha[:8]})")
                for _ in range(3):
                    QApplication.processEvents()

                # drop_sha is correctly the original SHA because we are rebasing backward
                has_parent = False
                try:
                    subprocess.run(["git", "rev-parse", f"{drop_sha}^"], cwd=self.repo_path, check=True, capture_output=True)
                    has_parent = True
                except:
                    pass
                upstream = f"{drop_sha}^" if has_parent else "--root"

                # Setup skip variables logic
                should_drop_entirely = drop_empty_commits and will_be_empty
                if should_drop_entirely:
                    empty_commits_dropped_count += 1

                action_script_content = f"""#!/usr/bin/env python3
import subprocess, sys

filepath = {repr(filepath)}
drop_sha = {repr(drop_sha)}

try:
    if subprocess.run(['git', 'rev-parse', 'HEAD~1'], capture_output=True).returncode != 0:
        subprocess.check_call(['git', 'rm', '-f', '--ignore-unmatch', '--', filepath])
        subprocess.check_call(['git', 'commit', '--amend', '--allow-empty', '-C', drop_sha])
    else:
        subprocess.check_call(['git', 'reset', '--soft', 'HEAD~1'])
        subprocess.check_call(['git', 'reset', 'HEAD', '--', filepath])
        subprocess.check_call(['git', 'commit', '--allow-empty', '-C', drop_sha])
        subprocess.check_call(['git', 'reset', '--hard', 'HEAD'])
        subprocess.check_call(['git', 'clean', '-fd', '--', filepath])
except Exception as e:
    print("FAILED to replace commit:", e)
    sys.exit(1)
"""
                import tempfile, os, stat
                action_fd, action_path = tempfile.mkstemp(prefix='git_remove_action_', suffix='.py', text=True)
                with os.fdopen(action_fd, 'w', encoding='utf-8') as f:
                    f.write(action_script_content)
                os.chmod(action_path, os.stat(action_path).st_mode | stat.S_IEXEC)

                single_exec = f"exec python3 {action_path}"

                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
                    f.write("#!/usr/bin/env python3\n")
                    f.write("import sys\n")
                    f.write(f"target_sha = {repr(drop_sha)}\n")
                    f.write(f"should_drop_entirely = {repr(should_drop_entirely)}\n")
                    f.write(f"single_exec = {repr(single_exec)}\n")
                    f.write("todo_path = sys.argv[1]\n")
                    f.write("with open(todo_path, 'r') as tf:\n")
                    f.write("    lines = tf.readlines()\n")
                    f.write("output = []\n")
                    f.write("for line in lines:\n")
                    f.write("    stripped = line.strip()\n")
                    f.write("    is_target = not stripped.startswith('#') and len(stripped.split()) >= 2 and stripped.split()[1].startswith(target_sha)\n")
                    f.write("    if is_target and should_drop_entirely:\n")
                    f.write("        continue\n")
                    f.write("    output.append(line)\n")
                    f.write("    if is_target and not should_drop_entirely:\n")
                    f.write("        output.append(single_exec + '\\n')\n")
                    f.write("with open(todo_path, 'w') as tf:\n")
                    f.write("    tf.writelines(output)\n")
                    editor_script = f.name
                os.chmod(editor_script, os.stat(editor_script).st_mode | stat.S_IEXEC)

                env = os.environ.copy()
                env["GIT_SEQUENCE_EDITOR"] = editor_script
                env["GIT_EDITOR"] = "true"

                cmd = ["git", "rebase", "-i", upstream] if upstream != "--root" else ["git", "rebase", "-i", "--root"]
                result = subprocess.run(cmd, cwd=self.repo_path, env=env, capture_output=True, text=True)

                try:
                    os.unlink(editor_script)
                    os.unlink(action_path)
                except:
                    pass

                if result.returncode != 0:
                    subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, capture_output=True)
                    progress.close()
                    QMessageBox.critical(self, "Failed", f"Failed while processing {drop_sha[:8]}. Aborted.\\n\\n{result.stderr}")
                    self.load_history()
                    return

            progress.close()
            self.load_history()
            new_head = self.get_head_sha()
            self.log_action(sha, f"removed {filepath} onwards completely", old_head, new_head)

            success_msg = f"File '{filepath}' has been perfectly removed from history from {short_sha} onwards."
            if empty_commits_dropped_count > 0:
                success_msg += f"\n\n{empty_commits_dropped_count} empty commit(s) were automatically dropped."

            QMessageBox.information(self, "Success", success_msg)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
        finally:
            self.load_history()

    def handle_split_all_commits(self, item):
        sha = item.text().split()[0]
        try:
            files = get_commit_files(self.repo_path, sha)
            if len(files) != 1:
                QMessageBox.critical(
                    self,
                    "Cannot Split All Commits",
                    "This commit contains multiple files.\n\n"
                    "To split this commit:\n"
                    "1. First move a file changes out of this commit and then split all changes in this file to separate commits.\n\n"
                    "2. Split each file changes to separate commits, and then select the file and split its changes to separate commits."
                )
                return
            filepath = files[0]
            # Count hunks for the confirmation dialog
            diff_text = subprocess.check_output(
                ["git", "log", "-p", "-1", sha, "--", filepath],
                cwd=self.repo_path, encoding='utf-8', errors='replace'
            )
            n_hunks = sum(1 for line in diff_text.split('\n') if line.startswith('@@'))
            reply = QMessageBox.question(
                self,
                "Confirm Split All Changes",
                f"File <b>{filepath}</b> in commit <b>{sha}</b> has <b>{n_hunks}</b> hunk(s).<br><br>"
                f"This will split it into <b>{n_hunks}</b> separate commits (one per hunk).<br><br>"
                "Proceed?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            self.perform_split_all_commits(sha, filepath)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not check commit files: {str(e)}")

    def perform_split_all_commits(self, sha, filepath):
        old_head = self.get_head_sha()
        self.save_undo_state()
        try:
            short_sha = sha[:8]
            original_msg = get_full_commit_message(self.repo_path, sha)

            # The script will be executed when the sequence editor sees 'exec python3 <script>'
            split_script_content = f"""#!/usr/bin/env python3
import sys, subprocess, os, tempfile

target_sha = {repr(sha)}
filepath = {repr(filepath)}
original_msg = {repr(original_msg)}

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

    new_msg = f"change-{{i+1}} of {{target_sha[:8]}}\\n\\n{{original_msg}}"

    # Use temp file for multiline message
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as mf:
        mf.write(new_msg)
        mf_path = mf.name
    try:
        subprocess.check_call(['git', 'commit', '-F', mf_path])
    finally:
        if os.path.exists(mf_path):
            os.unlink(mf_path)

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
                f.write("    output.append(line)\n")
                f.write("    stripped = line.strip()\n")
                f.write("    if not stripped.startswith('#') and len(stripped.split()) >= 2 and stripped.split()[1].startswith(target_sha):\n")
                f.write("        # Add our exec script AFTER the pick line\n")
                f.write("        output.append(single_exec + '\\n')\n")
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

            progress = ProgressDialog("Splitting Changes", f"Splitting commit {short_sha} into separate commits...", self)
            self.split_worker = SplitWorker(cmd, self.repo_path, env)

            def on_split_finished(returncode, stdout, stderr):
                try:
                    if progress.isVisible():
                        progress.close()
                    try:
                        os.unlink(editor_script)
                        os.unlink(split_action_script)
                    except:
                        pass

                    if returncode == 0:
                        self.load_history()
                        new_head = self.get_head_sha()
                        self.log_action(sha, f"split {filepath} in", old_head, new_head)
                        QMessageBox.information(self, "Success",
                            f"Commit {short_sha} has been split into multiple commits for file '{filepath}'.")
                    else:
                        subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, capture_output=True)
                        QMessageBox.critical(self, "Split Failed",
                            f"The split operation failed and has been aborted.\n\nError: {stderr}\nOutput: {stdout}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
                finally:
                    self.load_history()

            self.split_worker.finished.connect(on_split_finished)
            self.split_worker.start()
            progress.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
            self.load_history()

    def handle_split_per_file(self, item):
        """Splits each file in a commit into its own separate commit."""
        sha = item.text().split()[0]
        try:
            files = get_commit_files(self.repo_path, sha)
            if not files:
                QMessageBox.information(self, "No Files", f"Commit {sha} has no file changes to split.")
                return
            if len(files) == 1:
                QMessageBox.information(self, "Info", "This commit only has 1 file changed. Nothing to split.")
                return

            n = len(files)
            reply = QMessageBox.question(
                self,
                "Confirm Split Per File",
                f"Commit <b>{sha}</b> has <b>{n}</b> file(s) changed.<br><br>"
                f"This will split it into <b>{n}</b> separate commits (one per file).<br><br>"
                "Proceed?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

            self.perform_split_per_file(sha, files)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not check commit files: {str(e)}")

    def perform_split_per_file(self, sha, files):
        """
        Splits each file in a commit into its own separate commit.
        """
        old_head = self.get_head_sha()
        self.save_undo_state()
        """Executes splitting each file into its own commit using rebase exec."""
        self.save_undo_state()
        try:
            short_sha = sha[:8]
            original_msg = get_full_commit_message(self.repo_path, sha)

            # Action script content for splitting each file
            action_script_content = f"""#!/usr/bin/env python3
import subprocess, os, tempfile, sys

sha = {repr(sha)}
files = {repr(files)}
short_sha = {repr(short_sha)}
original_msg = {repr(original_msg)}

# This script is executed *after* the 'pick' line, so HEAD is already at target_sha.
# We need to reset to its parent to re-apply changes.
subprocess.check_call(['git', 'reset', '--hard', 'HEAD~1'])

for i, filename in enumerate(files):
    # checkout file from original commit to stage it
    subprocess.check_call(['git', 'checkout', sha, '--', filename])

    if i == 0:
        # First file gets original commit message
        subprocess.check_call(['git', 'commit', '-C', sha])
    else:
        # Others get "filename changes separated out from short_sha" + original_msg
        msg = f"{{filename}} changes separated out from {{short_sha}}\\n\\n{{original_msg}}"

        # Use temp file for multiline message
        msg_fd, msg_path = tempfile.mkstemp(prefix='git_msg_split_', text=True)
        with os.fdopen(msg_fd, 'w', encoding='utf-8') as f:
            f.write(msg)
        try:
            subprocess.check_call(['git', 'commit', '-F', msg_path, '--no-verify'])
        finally:
            try:
                os.unlink(msg_path)
            except:
                pass
"""
            action_fd, action_path = tempfile.mkstemp(prefix='git_split_perfile_', suffix='.py', text=True)
            with os.fdopen(action_fd, 'w', encoding='utf-8') as f:
                f.write(action_script_content)
            os.chmod(action_path, os.stat(action_path).st_mode | stat.S_IEXEC)

            single_exec = f"exec python3 {action_path}"

            current_shas = [self.list_widget.item(i).text().split()[0]
                            for i in range(self.list_widget.count())]

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
                f.write("    output.append(line)\n")
                f.write("    stripped = line.strip()\n")
                f.write("    if not stripped.startswith('#') and len(stripped.split()) >= 2 and stripped.split()[1].startswith(target_sha):\n")
                f.write("        # Add our exec line AFTER the pick line\n")
                f.write("        output.append(single_exec + '\\n')\n")
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

            progress = ProgressDialog("Splitting Changes", f"Splitting commit {short_sha} into {len(files)} separate commits...", self)
            self.split_worker = SplitWorker(cmd, self.repo_path, env)

            def on_split_finished(returncode, stdout, stderr):
                try:
                    if progress.isVisible():
                        progress.close()
                    try:
                        os.unlink(editor_script)
                        os.unlink(action_path)
                    except:
                        pass

                    if returncode == 0:
                        self.load_history()
                        new_head = self.get_head_sha()
                        self.log_action(sha, f"split per-file", old_head, new_head)
                        QMessageBox.information(self, "Success",
                            f"Commit {short_sha} has been split into {len(files)} commits.")
                    else:
                        subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, capture_output=True)
                        QMessageBox.critical(self, "Split Failed",
                            f"The split operation failed and has been aborted.\n\nError: {stderr}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
                finally:
                    self.load_history()

            self.split_worker.finished.connect(on_split_finished)
            self.split_worker.start()
            progress.exec()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
            self.load_history()

    def perform_move(self, new_shas, original_shas=None):
        """Performs commit reordering using our unified rebase logic."""
        old_head = self.get_head_sha()
        print("Performing commit reorder...")
        if self.run_interactive_rebase(new_shas, original_shas=original_shas, progress_title="Moving Commits", progress_text="Reordering commits. Please wait..."):
            self.load_history()
            new_head = self.get_head_sha()
            self.log_action("N/A", "reordered commits", old_head, new_head)
            QMessageBox.information(self, "Success", "Commits reordered successfully!")
            return
        self.load_history()

    def run_interactive_rebase(self, new_shas, rephrase_map=None, squash_shas=None, original_shas=None, progress_title="Rebasing", progress_text="Executing interactive rebase. Please wait...\nThis might take a few moments."):
        """
        Unified handler for history rewriting using git rebase -i.
        original_shas: The pre-change SHA order (latest-first). If provided, used
                       for prefix comparison instead of reading list_widget (which
                       may already show the new order after a drag-drop).
        """
        self.save_undo_state()
        print("Starting interactive rebase...")
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
                # Check root status (self.commit_sha is the branch base / the last commit NOT shown)
                # We use self.commit_sha directly as upstream, NOT self.commit_sha^.
                # self.commit_sha is already the parent of the first local commit, so only
                # local commits fall in the rebase range. Using self.commit_sha^ would pull
                # the branch-base commit into the rebase range, causing it to be dropped or
                # squashed because it doesn't appear in the todo list.
                has_parent = False
                try:
                    subprocess.run(["git", "rev-parse", f"{self.commit_sha}^"],
                                   cwd=self.repo_path, check=True, capture_output=True)
                    has_parent = True
                except:
                    has_parent = False
                upstream = self.commit_sha if has_parent else "--root"
                todo_shas = proposed_order

            # Show progress dialog
            progress = ProgressDialog(progress_title, progress_text, self)
            progress.show()
            QApplication.processEvents()

            try:
                # Feature: Fast-track top-drops (reset --hard)
                if not todo_shas and common_count > 0:
                    print(f"Fast-tracking drop via reset --hard to {upstream}")
                    process = subprocess.Popen(["git", "reset", "--hard", upstream],
                                               cwd=self.repo_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    while process.poll() is None:
                        QApplication.processEvents()
                        time.sleep(0.05)

                    if process.returncode != 0:
                        stdout, stderr = process.communicate()
                        raise Exception(f"Fast-track reset failed: {stderr}")

                    # Small non-blocking delay to ensure the progress window is seen by the user
                    # and has a chance to paint correctly if the operation was near-instant.
                    for _ in range(10):
                        QApplication.processEvents()
                        time.sleep(0.05)
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


                process = subprocess.Popen(cmd, cwd=self.repo_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                while process.poll() is None:
                    QApplication.processEvents()
                    time.sleep(0.05)

                stdout, stderr = process.communicate()

                result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
                os.unlink(editor_script)
                # Clean up message temp files
                for mf_path in msg_files.values():
                    try:
                        os.unlink(mf_path)
                    except Exception:
                        pass

                if result.returncode == 0:
                    return True
                else:
                    subprocess.run(["git", "rebase", "--abort"], cwd=self.repo_path, capture_output=True)
                    QMessageBox.critical(self, "Rebase Failed",
                        f"Action failed (likely due to merge conflicts).\n"
                        f"The rebase has been aborted.\n\nError: {result.stderr}")
                    return False

            finally:
                progress.close()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred during rebase: {str(e)}")
            return False



    def handle_rescan_repo(self):
        """Safely rescan repository state, prompting user for unstaged changes identically to app startup if found."""
        unstaged_files = get_unstaged_files(self.repo_path, ignore_submodules=True)
        if unstaged_files:
            dialog = UnstagedChangesDialog(len(unstaged_files), parent=self)
            result = dialog.exec()

            if result == UnstagedChangesDialog.Accepted:
                created_stash_sha = stash_changes(self.repo_path)
                if created_stash_sha:
                    QMessageBox.information(self, "Stash Successful", f"Changes stashed successfully (SHA: {created_stash_sha[:7]}).")
                else:
                    QMessageBox.critical(self, "Error", "Failed to stash changes. Please stash or commit manually.")
                    return
            elif result == UnstagedChangesDialog.CommitEachResult:
                progress = ProgressDialog("Committing Changes", f"Committing {len(unstaged_files)} files individually...", self)
                progress.show()
                for _ in range(3): QApplication.processEvents()

                success_count = 0
                for i, f in enumerate(unstaged_files):
                    progress.label.setText(f"Committing ({i+1}/{len(unstaged_files)}): {f}")
                    for _ in range(2): QApplication.processEvents()
                    if commit_file(self.repo_path, f, f"changes in {f}"):
                        success_count += 1

                progress.close()
                QMessageBox.information(self, "Commit Successful", f"Successfully committed {success_count} isolated files.")
            elif result == UnstagedChangesDialog.BulkCommitResult:
                msg = f"bulk commit (Number of modified files: {len(unstaged_files)})"
                progress = ProgressDialog("Bulk Committing", f"Committing {len(unstaged_files)} files at once...", self)
                progress.show()
                for _ in range(3): QApplication.processEvents()

                success = bulk_commit_all(self.repo_path, msg)
                progress.close()

                if success:
                    QMessageBox.information(self, "Commit Successful", "Bulk commit successful.")
                else:
                    QMessageBox.critical(self, "Error", "Bulk commit failed.")
                    return
            elif result == UnstagedChangesDialog.AmendResult:
                progress = ProgressDialog("Amending", "Amending all changes into HEAD commit...", self)
                progress.show()
                for _ in range(3): QApplication.processEvents()

                success = amend_with_head(self.repo_path)
                progress.close()

                if success:
                    QMessageBox.information(self, "Amend Successful", "Changes amended into HEAD commit.")
                else:
                    QMessageBox.critical(self, "Error", "Amend failed.")
                    return
            else:
                # Cancel/Rejected: Just return successfully and quietly drop the window.
                return

        # Finally, we reload the tree to correctly align matching local state
        self.load_history()

    def handle_manual_refresh(self):
        """Shows a progress dialog during manual refresh."""
        progress = ProgressDialog("Refreshing", "Refreshing git history. Please wait...", self)
        progress.show()
        QApplication.processEvents()
        try:
            self.load_history()
        finally:
            progress.close()

    def load_history(self):
        """Fetches git history and populates the list widget."""
        # Invalidate cache as history might have changed
        self.commit_cache = {}

        # Clear search when reloading history
        self.update_window_title()

        current_branch = get_current_branch(self.repo_path)

        # Update origin reset button label with current branch
        if hasattr(self, 'reset_origin_btn'):
            self.reset_origin_btn.setText(f"git reset --hard origin/{current_branch}")

        # Save current row to restore selection
        old_row = self.list_widget.currentRow()

        self.list_widget.clear()
        self.list_widget.setUpdatesEnabled(False)
        self.list_widget.blockSignals(True)
        try:
            history = get_git_history(self.repo_path, self.commit_sha)
            branch_map = get_local_branches_map(self.repo_path, current_branch=current_branch)

            for entry in history:
                if isinstance(entry, dict):
                    line = entry["raw_text"]
                    sha = entry["sha"]
                    item = QListWidgetItem(line)
                    item.setData(Qt.UserRole + 2, entry.get("date", ""))
                    item.setData(Qt.UserRole + 3, (entry.get("added", 0), entry.get("deleted", 0)))
                    item.setData(Qt.UserRole + 4, entry.get("author", ""))
                    parents = entry.get("parents", "")
                    item.setData(Qt.UserRole + 5, " " in parents)
                else:
                    line = entry
                    sha = line.split()[0]
                    item = QListWidgetItem(line)

                if sha in branch_map:
                    branches_str = ", ".join(branch_map[sha])
                    item.setData(Qt.UserRole + 1, branches_str)

                self.list_widget.addItem(item)

            if self.list_widget.count() > 0:
                # If nothing was selected before (-1), default to topmost commit (0)
                # Otherwise, bound it to the new list size
                new_row = max(0, min(old_row if old_row >= 0 else 0, self.list_widget.count() - 1))
                self.list_widget.setCurrentRow(new_row)
            else:
                self.update_side_diff()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        finally:
            self.list_widget.setUpdatesEnabled(True)
            self.list_widget.blockSignals(False)
            self.update_side_diff()

        # Update Failsafe button state
        current_head = get_head_sha(self.repo_path)
        uncommitted = has_uncommitted_changes(self.repo_path)

        # Update cache
        self.cached_current_head_full_sha = get_full_head_sha(self.repo_path)
        self.cached_has_uncommitted = uncommitted

        self.total_commits_label.setText("Total: counting...")
        self._count_total_commits_async()
        self._update_commit_counts()

        if current_head == self.start_time_head[:8] and not uncommitted:
            self.failsafe_btn.setEnabled(False)
            self.failsafe_btn.setText(f"Reset Hard to START_TIME_HEAD (Already at {self.start_time_head[:8]})")
        else:
            self.failsafe_btn.setEnabled(True)
            self.failsafe_btn.setText(f"⚠ Reset Hard to START_TIME_HEAD ({self.start_time_head[:8]}) ⚠")
