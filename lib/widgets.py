from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QKeySequence,
    QPainter,
    QShortcut,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QTextEdit,
    QToolButton,
    QWidget,
)


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


# Data role on file-wise list items holding the (status, path1, path2) entry.
# Qt.UserRole holds the display stats tuple.
FILE_ENTRY_ROLE = Qt.UserRole + 1


class DiffHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None, added_color="#a6e22e", removed_color="#f92672", header_color="#66d9ef"):
        super().__init__(parent)
        self.added_format = QTextCharFormat()
        self.added_format.setForeground(QColor(added_color))

        self.removed_format = QTextCharFormat()
        self.removed_format.setForeground(QColor(removed_color))

        self.header_format = QTextCharFormat()
        self.header_format.setForeground(QColor(header_color))

    def highlightBlock(self, text):
        if text.startswith('+') and not text.startswith('+++'):
            self.setFormat(0, len(text), self.added_format)
        elif text.startswith('-') and not text.startswith('---'):
            self.setFormat(0, len(text), self.removed_format)
        elif text.startswith('commit') or text.startswith('diff') or text.startswith('index'):
            self.setFormat(0, len(text), self.header_format)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return QSize(self.code_editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)


class DiffView(QPlainTextEdit):
    """A QPlainTextEdit that draws subtle 1px separators before file diffs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.separator_color = QColor("#CCCCCC")
        self.draw_separators = True

        self.line_number_area = LineNumberArea(self)
        self.show_line_numbers = False

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.update_line_number_area_width(0)

    def set_line_numbers_visible(self, visible):
        self.show_line_numbers = visible
        self.update_line_number_area_width(self.blockCount())

    def line_number_area_width(self):
        if not self.show_line_numbers:
            return 0
        digits = 1
        max_val = max(1, self.blockCount())
        while max_val >= 10:
            max_val //= 10
            digits += 1
        fm = self.fontMetrics()
        space = 3 + fm.horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        w = self.line_number_area_width()
        self.setViewportMargins(w, 0, 0, 0)
        if self.show_line_numbers:
            self.line_number_area.show()
        else:
            self.line_number_area.hide()

    def update_line_number_area(self, rect, dy):
        if not self.show_line_numbers:
            return
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def event(self, event):
        if event.type() == QEvent.FontChange and self.show_line_numbers:
            self.update_line_number_area_width(0)
        return super().event(event)

    def wheelEvent(self, event):
        super().wheelEvent(event)
        if event.modifiers() & Qt.ControlModifier and self.show_line_numbers:
            self.update_line_number_area_width(0)

    def line_number_area_paint_event(self, event):
        if not self.show_line_numbers:
            return
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#f0f0f0"))
        painter.setFont(self.font())

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(Qt.gray)
                painter.drawText(0, top, self.line_number_area.width() - 2, self.fontMetrics().height(),
                                 Qt.AlignRight, number)

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def set_separator_color(self, color):
        self.separator_color = QColor(color)
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.draw_separators:
            return

        painter = QPainter(self.viewport())
        # Disable antialiasing for sharp 1px lines
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.Antialiasing, False)

        block = self.firstVisibleBlock()
        # Find the top of the first visible block in viewport coordinates
        offset = self.contentOffset()
        top = int(offset.y())

        while block.isValid():
            # If the block is below the visible area, we're done
            if top > self.viewport().rect().bottom():
                break

            block_height = int(self.blockBoundingRect(block).height())
            bottom = top + block_height

            # If the block is at least partially visible
            if bottom >= 0:
                text = block.text().strip()
                # Detection: An empty block followed by a 'diff --git' block
                # was injected by git_helpers.py specifically for our separator.
                if text == "" and block.next().isValid():
                    next_text = block.next().text().strip()
                    if next_text.startswith('diff --git '):
                        # Center the line in this empty block height
                        # Use 2px thickness for better visibility
                        y = int(top + (block_height - 2) / 2)
                        painter.fillRect(0, y, self.viewport().width(), 2, self.separator_color)

            # Move to the top of the next block
            top = bottom
            block = block.next()


class DiffSearchBar(QWidget):
    """A lightweight search toolbar for QPlainTextEdit with live highlighting."""
    def __init__(self, target_view: QPlainTextEdit, parent=None):
        super().__init__(parent)
        self.target_view = target_view
        self.matches = []
        self.current_match_idx = -1

        # Colors for highlighting
        self.highlight_color = QColor("#ffeb3b") # yellow
        self.highlight_color.setAlpha(100)
        self.active_highlight_color = QColor("#ff9800") # orange
        self.active_highlight_color.setAlpha(150)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        # Prevent vertical stretching
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search in diff (Ctrl+F)...")
        self.search_input.setToolTip("Search in the diff (Ctrl+F).")
        self.search_input.setMinimumHeight(28)
        self.search_input.setClearButtonEnabled(True)

        self.match_case_cb = QCheckBox("Match Case")
        self.match_case_cb.setToolTip("Match case.")

        self.btn_prev = QToolButton()
        self.btn_prev.setText("<")
        self.btn_next = QToolButton()
        self.btn_next.setText(">")
        # Ensure buttons are square and compact
        self.btn_prev.setFixedSize(28, 28)
        self.btn_next.setFixedSize(28, 28)
        self.btn_prev.setToolTip("Previous match (Up)")
        self.btn_next.setToolTip("Next match (Down)")

        self.lbl_counter = QLabel("0/0")
        self.lbl_counter.setMinimumWidth(40)
        self.lbl_counter.setAlignment(Qt.AlignCenter)

        self.whole_word_cb = QCheckBox("Whole word")
        self.whole_word_cb.setToolTip("Match whole words only.")

        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.VLine)
        self.separator.setFrameShadow(QFrame.Sunken)

        self.line_num_cb = QCheckBox("Line-Num")
        self.line_num_cb.setToolTip("Highlight line numbers.")

        layout.addWidget(self.search_input)
        layout.addWidget(self.match_case_cb)
        layout.addWidget(self.whole_word_cb)
        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.lbl_counter)
        layout.addWidget(self.separator)
        layout.addWidget(self.line_num_cb)

    def _connect_signals(self):
        self.search_input.textChanged.connect(self._perform_search)
        self.search_input.returnPressed.connect(self.next_match)
        self.match_case_cb.toggled.connect(self._perform_search)
        self.whole_word_cb.toggled.connect(self._perform_search)
        self.line_num_cb.toggled.connect(self.target_view.set_line_numbers_visible)
        self.btn_next.clicked.connect(self.next_match)
        self.btn_prev.clicked.connect(self.prev_match)

        # Keyboard shortcuts when focused
        self.shortcut_up = QShortcut(QKeySequence(Qt.Key_Up), self)
        self.shortcut_up.setContext(Qt.WidgetWithChildrenShortcut)
        self.shortcut_up.activated.connect(self.prev_match)

        self.shortcut_down = QShortcut(QKeySequence(Qt.Key_Down), self)
        self.shortcut_down.setContext(Qt.WidgetWithChildrenShortcut)
        self.shortcut_down.activated.connect(self.next_match)

        # Use robust EventFilters instead of QShortcut for Esc
        for widget in (self.search_input, self.btn_prev, self.btn_next, self.target_view):
            widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            if obj in (self.search_input, self.btn_prev, self.btn_next, self.target_view):
                if self.search_input.text() or self.search_input.hasFocus():
                    self.escape_pressed()
                    return True
        return super().eventFilter(obj, event)

    def escape_pressed(self):
        self.search_input.clear()
        self.clear_search()
        self.target_view.setFocus()

    def _perform_search(self):
        query = self.search_input.text()
        if not query:
            self.clear_search()
            return

        doc = self.target_view.document()
        self.matches.clear()
        self.current_match_idx = -1

        cursor = QTextCursor(doc)

        # Check available version of flag for case sensitivity
        find_flag_case = getattr(QTextDocument, 'FindCaseSensitively', None)
        if find_flag_case is None and hasattr(QTextDocument, 'FindFlag'):
            find_flag_case = QTextDocument.FindFlag.FindCaseSensitively

        while True:
            # doc.find default flags are case insensitive
            if self.match_case_cb.isChecked() and find_flag_case is not None:
                cursor = doc.find(query, cursor, find_flag_case)
            else:
                cursor = doc.find(query, cursor)

            if cursor.isNull():
                break

            # When whole-word is enabled, skip matches not on word boundaries
            if self.whole_word_cb.isChecked():
                start = cursor.selectionStart()
                end = cursor.selectionEnd()
                before = doc.characterAt(start - 1) if start > 0 else None
                after = doc.characterAt(end)
                if before is not None and (before.isalnum() or before == '_'):
                    continue
                if after is not None and (after.isalnum() or after == '_'):
                    continue

            self.matches.append(QTextCursor(cursor))

        self.update_highlights()

    def update_highlights(self):
        selections = []

        for i, cursor in enumerate(self.matches):
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format.setBackground(self.active_highlight_color if i == self.current_match_idx else self.highlight_color)
            selections.append(sel)

        self.target_view.setExtraSelections(selections)

        count = len(self.matches)
        if count == 0:
            self.lbl_counter.setText("0/0")
            # Clear native text selection to avoid ghost highlights
            cursor = self.target_view.textCursor()
            if cursor.hasSelection():
                cursor.clearSelection()
                self.target_view.setTextCursor(cursor)
        else:
            idx = self.current_match_idx + 1 if self.current_match_idx >= 0 else 1
            self.lbl_counter.setText(f"{idx}/{count}")
            # If no current match is selected but we have matches, auto-scroll to first
            if self.current_match_idx == -1 and count > 0:
                self.current_match_idx = 0
                self.target_view.setTextCursor(self.matches[0])

    def next_match(self):
        if not self.matches:
            return
        self.current_match_idx = (self.current_match_idx + 1) % len(self.matches)
        self.target_view.setTextCursor(self.matches[self.current_match_idx])
        self.update_highlights()

    def prev_match(self):
        if not self.matches:
            return
        if self.current_match_idx <= 0:
            self.current_match_idx = len(self.matches) - 1
        else:
            self.current_match_idx -= 1
        self.target_view.setTextCursor(self.matches[self.current_match_idx])
        self.update_highlights()

    def clear_search(self):
        self.matches.clear()
        self.current_match_idx = -1
        self.target_view.setExtraSelections([])
        self.lbl_counter.setText("0/0")

        # Hand-in-hand with updating highlights: clear selection
        cursor = self.target_view.textCursor()
        if cursor.hasSelection():
            cursor.clearSelection()
            self.target_view.setTextCursor(cursor)

    def show_and_focus(self):
        self.show()
        self.search_input.setFocus()
        self.search_input.selectAll()
        if self.search_input.text():
            self._perform_search()


class StatsItemDelegate(QStyledItemDelegate):
    """Custom delegate: filename left-aligned, +N -M stats right-aligned."""
    def __init__(self, added_color="#22863a", removed_color="#cb2431", parent=None):
        super().__init__(parent)
        self.added_color = QColor(added_color)
        self.removed_color = QColor(removed_color)

    def paint(self, painter, option, index):
        # pyrefly: ignore [missing-import]
        from PySide6.QtWidgets import QStyleOptionViewItem, QApplication
        # pyrefly: ignore [missing-import]
        from PySide6.QtWidgets import QStyle as _QStyle
        # Step 1: Build a full style option (needed for correct highlight colour)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # Step 2: Draw the whole item skeleton natively (panel, hover, selection
        # AND the check indicator for Qt.ItemIsUserCheckable items) the same way
        # the main commit list does, so checkboxes render and hit-test properly.
        # opt.text is blanked so the style does not draw text on top of ours.
        style = opt.widget.style() if opt.widget else QApplication.style()
        opt.text = ""
        style.drawControl(_QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        text_rect = style.subElementRect(_QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)

        # Step 3: Everything else is drawn by us
        painter.save()
        painter.setFont(opt.font)

        is_selected = bool(option.state & QStyle.State_Selected)
        text_color = QColor("white") if is_selected else option.palette.text().color()
        rect = text_rect.adjusted(0, 0, -4, 0) if not text_rect.isNull() else option.rect.adjusted(6, 0, -6, 0)
        fm = QFontMetrics(opt.font)

        stats = index.data(Qt.UserRole)
        filename = index.data(Qt.DisplayRole) or ""

        # Measure stats width so we can clip the filename safely
        is_binary = False
        old_size = new_size = 0
        added = deleted = 0
        if stats and isinstance(stats, tuple):
            if len(stats) == 4:
                added, deleted, old_size, new_size = stats
                is_binary = (old_size != 0 or new_size != 0) and added == 0 and deleted == 0
            elif len(stats) == 2:
                added, deleted = stats

        if is_binary:
            from lib.git_helpers import format_binary_size
            if old_size >= 0 and new_size >= 0 and old_size != new_size:
                stats_text = f"size: {format_binary_size(old_size)} -> {format_binary_size(new_size)}"
            elif new_size >= 0:
                stats_text = f"size: {format_binary_size(new_size)}"
            elif old_size >= 0:
                stats_text = f"size: {format_binary_size(old_size)}"
            else:
                stats_text = ""
            stats_w = fm.horizontalAdvance(stats_text) + 4
            painter.setPen(QColor("white") if is_selected else option.palette.text().color())
            painter.drawText(
                QRect(rect.right() - stats_w, rect.top(), stats_w, rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter, stats_text)
            filename_rect = QRect(rect.left(), rect.top(),
                                  rect.width() - stats_w - 8, rect.height())
        elif added or deleted:
            added_str = f"+{added}"
            deleted_str = f" -{deleted}" if deleted else ""
            deleted_w = fm.horizontalAdvance(deleted_str)
            added_w = fm.horizontalAdvance(added_str)
            stats_total_w = added_w + deleted_w + 4

            # Draw +N (green / white-on-select)
            painter.setPen(QColor("white") if is_selected else self.added_color)
            painter.drawText(
                QRect(rect.right() - stats_total_w, rect.top(), added_w, rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter, added_str)

            # Draw -M (red / white-on-select)
            if deleted:
                painter.setPen(QColor("white") if is_selected else self.removed_color)
                painter.drawText(
                    QRect(rect.right() - deleted_w, rect.top(), deleted_w, rect.height()),
                    Qt.AlignLeft | Qt.AlignVCenter, deleted_str)

            filename_rect = QRect(rect.left(), rect.top(),
                                  rect.width() - stats_total_w - 8, rect.height())
        else:
            filename_rect = rect

        # Draw filename, elided if too long
        painter.setPen(text_color)
        painter.drawText(filename_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         fm.elidedText(filename, Qt.ElideMiddle, filename_rect.width()))

        painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), max(hint.height(), 28))


class TreeStatsDelegate(QStyledItemDelegate):
    """Custom delegate for tree widget stats column (column 1) with colored +N/-M."""
    def __init__(self, added_color="#22863a", removed_color="#cb2431", parent=None):
        super().__init__(parent)
        self.added_color = QColor(added_color)
        self.removed_color = QColor(removed_color)

    def paint(self, painter, option, index):
        from PySide6.QtWidgets import QStyleOptionViewItem, QApplication
        from PySide6.QtWidgets import QStyle as _QStyle

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        style = opt.widget.style() if opt.widget else QApplication.style()
        opt.text = ""
        style.drawControl(_QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        text_rect = style.subElementRect(_QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)

        painter.save()
        painter.setFont(opt.font)

        is_selected = bool(option.state & QStyle.State_Selected)
        rect = text_rect.adjusted(0, 0, -4, 0) if not text_rect.isNull() else option.rect.adjusted(6, 0, -6, 0)
        fm = QFontMetrics(opt.font)

        stats_text = index.data(Qt.DisplayRole) or ""
        if stats_text and "/" in stats_text:
            parts = stats_text.split("/")
            added_str = parts[0].strip()
            deleted_str = parts[1].strip() if len(parts) > 1 else ""
            added_w = fm.horizontalAdvance(added_str)
            deleted_w = fm.horizontalAdvance(deleted_str)
            gap = fm.horizontalAdvance(" ")
            total_w = added_w + deleted_w + gap

            # Draw +N (green / white-on-select) right-aligned
            painter.setPen(QColor("white") if is_selected else self.added_color)
            painter.drawText(
                QRect(rect.right() - total_w, rect.top(), added_w, rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter, added_str)

            # Draw -M (red / white-on-select)
            painter.setPen(QColor("white") if is_selected else self.removed_color)
            painter.drawText(
                QRect(rect.right() - deleted_w, rect.top(), deleted_w, rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter, deleted_str)

        painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), max(hint.height(), 28))
