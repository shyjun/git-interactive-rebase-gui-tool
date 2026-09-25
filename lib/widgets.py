import weakref

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QRegularExpression,
    QRect,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QCursor,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QShortcut,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QVBoxLayout,
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

# Data role holding [(start, end)] match ranges of the active file filter,
# painted with a yellow background by the item delegates.
FILTER_MATCH_ROLE = Qt.UserRole + 2


def filter_match_ranges(text, term):
    """Case-insensitive ranges of *term* in *text* as [(start, end), ...]."""
    if not term or not text:
        return []
    ranges = []
    hay, needle = text.lower(), term.lower()
    start = hay.find(needle)
    while start != -1:
        ranges.append((start, start + len(needle)))
        start = hay.find(needle, start + len(needle))
    return ranges


def list_filter_hidden(texts, term):
    """One bool per text: True when the row should be hidden for *term*."""
    if not term:
        return [False] * len(texts)
    needle = term.lower()
    return [needle not in (t or "").lower() for t in texts]


def _path_ancestors(path):
    parts = path.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def tree_filter_sets(file_paths, term):
    """Given full file paths, return (visible_files, visible_folders).

    A file is visible when *term* matches its full path (case-insensitive);
    a folder is visible when at least one descendant file is visible.
    """
    if term:
        needle = term.lower()
        visible_files = {p for p in file_paths if needle in p.lower()}
    else:
        visible_files = set(file_paths)
    visible_folders = set()
    for p in visible_files:
        visible_folders.update(_path_ancestors(p))
    return visible_files, visible_folders


def _draw_magnifier(painter, color):
    """Pen-drawn magnifier, same style as the Rescan Repo toolbar icon."""
    pen = QPen(color, 1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    painter.drawEllipse(2.0, 2.0, 8.8, 8.8)
    painter.drawLine(9.4, 9.4, 14.0, 14.0)


def _magnifier_icon(color):
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _draw_magnifier(painter, color)
    painter.end()
    return QIcon(pixmap)


def _paint_matched_text(painter, text, rect, ranges, base_color, font):
    """Draw *text* into *rect*, giving each (start, end) range a yellow wash."""
    if not text or rect.isEmpty():
        return
    fm = QFontMetrics(font)
    painter.save()
    painter.setFont(font)
    painter.setClipRect(rect)
    x = rect.left()
    pos = 0
    for start, end in sorted(ranges or []):
        start = max(0, min(start, len(text)))
        end = max(0, min(end, len(text)))
        if end <= start:
            continue
        if start > pos:
            seg = text[pos:start]
            w = fm.horizontalAdvance(seg)
            painter.setPen(base_color)
            painter.drawText(QRect(x, rect.top(), int(w) + 2, rect.height()),
                             Qt.AlignLeft | Qt.AlignVCenter, seg)
            x += w
            pos = start
        seg = text[start:end]
        w = fm.horizontalAdvance(seg)
        painter.fillRect(QRect(x, rect.top(), int(w), rect.height()),
                         QColor(255, 235, 59, 220))
        painter.setPen(QColor("#000000"))
        painter.drawText(QRect(x, rect.top(), int(w) + 2, rect.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, seg)
        x += w
        pos = end
    if pos < len(text):
        seg = text[pos:]
        w = fm.horizontalAdvance(seg)
        painter.setPen(base_color)
        painter.drawText(QRect(x, rect.top(), int(w) + 2, rect.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, seg)
    painter.restore()


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
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
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

    def set_line_wrap_enabled(self, enabled):
        self.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth if enabled
            else QPlainTextEdit.LineWrapMode.NoWrap
        )

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
        self._search_capped = False

        # Debounce timer for search
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._do_perform_search)

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

        self.separator = QFrame()
        self.separator.setFrameShape(QFrame.VLine)
        self.separator.setFrameShadow(QFrame.Sunken)

        self.options_btn = QToolButton()
        self.options_btn.setText("\u2699")  # ⚙ gear
        self.options_btn.setToolTip("Search and diff view options")
        self.options_btn.setPopupMode(QToolButton.InstantPopup)
        self.options_btn.setFixedSize(28, 28)
        self.options_btn.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
        self.options_menu = QMenu(self)

        self.match_case_action = QAction("Match Case", self)
        self.match_case_action.setCheckable(True)
        self.match_case_action.setChecked(False)
        self.match_case_action.setToolTip("Make search case-sensitive.")
        self.whole_word_action = QAction("Whole Word", self)
        self.whole_word_action.setCheckable(True)
        self.whole_word_action.setChecked(False)
        self.whole_word_action.setToolTip("Match whole words only.")
        self.regex_action = QAction("Regular Expression", self)
        self.regex_action.setCheckable(True)
        self.regex_action.setChecked(False)
        self.regex_action.setToolTip("Use regular expression for search.")
        self.options_menu.addAction(self.match_case_action)
        self.options_menu.addAction(self.whole_word_action)
        self.options_menu.addAction(self.regex_action)
        self.options_menu.addSeparator()

        self.line_num_action = QAction("Line Numbers", self)
        self.line_num_action.setCheckable(True)
        self.line_num_action.setChecked(False)
        self.line_num_action.setToolTip("Highlight line numbers in the diff.")
        self.line_wrap_action = QAction("Line Wrap", self)
        self.line_wrap_action.setCheckable(True)
        self.line_wrap_action.setChecked(False)
        self.line_wrap_action.setToolTip("Wrap long lines to fit the view width.")
        self.options_menu.addAction(self.line_num_action)
        self.options_menu.addAction(self.line_wrap_action)
        self.options_btn.setMenu(self.options_menu)

        layout.addWidget(self.search_input)
        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.lbl_counter)
        layout.addWidget(self.separator)
        layout.addWidget(self.options_btn)

    def _connect_signals(self):
        self.search_input.textChanged.connect(self._perform_search)
        self.search_input.returnPressed.connect(self._trigger_search_now)
        self.match_case_action.toggled.connect(self._perform_search)
        self.whole_word_action.toggled.connect(self._perform_search)
        self.regex_action.toggled.connect(self._perform_search)
        self.line_num_action.toggled.connect(self.target_view.set_line_numbers_visible)
        self.line_wrap_action.toggled.connect(self.target_view.set_line_wrap_enabled)
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
        self._search_timer.start()

    def _trigger_search_now(self):
        self._search_timer.stop()
        self._do_perform_search()
        if self.matches:
            self.next_match()

    def _do_perform_search(self):
        query = self.search_input.text()
        if not query:
            self.clear_search()
            return

        doc = self.target_view.document()
        self.matches.clear()
        self.current_match_idx = -1
        self._search_capped = False

        cursor = QTextCursor(doc)

        _MAX_MATCHES = 5000

        # Check available version of flag for case sensitivity
        find_flag_case = getattr(QTextDocument, 'FindCaseSensitively', None)
        if find_flag_case is None and hasattr(QTextDocument, 'FindFlag'):
            find_flag_case = QTextDocument.FindFlag.FindCaseSensitively

        use_regex = self.regex_action.isChecked()

        while len(self.matches) < _MAX_MATCHES:
            if use_regex:
                pattern_options = QRegularExpression.NoPatternOption
                if not self.match_case_action.isChecked():
                    pattern_options = QRegularExpression.CaseInsensitiveOption
                regex = QRegularExpression(query, pattern_options)
                if not regex.isValid():
                    break
                flags = find_flag_case if (self.match_case_action.isChecked() and find_flag_case is not None) else QTextDocument.FindFlags(0)
                cursor = doc.find(regex, cursor, flags)
            else:
                if self.match_case_action.isChecked() and find_flag_case is not None:
                    cursor = doc.find(query, cursor, find_flag_case)
                else:
                    cursor = doc.find(query, cursor)

            if cursor.isNull():
                break

            # When whole-word is enabled, skip matches not on word boundaries
            if self.whole_word_action.isChecked():
                start = cursor.selectionStart()
                end = cursor.selectionEnd()
                before = doc.characterAt(start - 1) if start > 0 else None
                after = doc.characterAt(end)
                if before is not None and (before.isalnum() or before == '_'):
                    continue
                if after is not None and (after.isalnum() or after == '_'):
                    continue

            self.matches.append(QTextCursor(cursor))

        if len(self.matches) >= _MAX_MATCHES:
            self._search_capped = True

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
        display_count = "5000+" if self._search_capped else str(count)
        if count == 0:
            self.lbl_counter.setText("0/0")
            # Clear native text selection to avoid ghost highlights
            cursor = self.target_view.textCursor()
            if cursor.hasSelection():
                cursor.clearSelection()
                self.target_view.setTextCursor(cursor)
        else:
            idx = self.current_match_idx + 1 if self.current_match_idx >= 0 else 1
            self.lbl_counter.setText(f"{idx}/{display_count}")
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
        self._search_capped = False
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
        from PySide6.QtWidgets import (
            QApplication,
            QStyleOptionViewItem,
        )
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
            deleted_str = f" -{deleted}"
            deleted_w = fm.horizontalAdvance(deleted_str)
            added_w = fm.horizontalAdvance(added_str)
            stats_total_w = added_w + deleted_w + 4

            # Draw +N (green / white-on-select)
            painter.setPen(QColor("white") if is_selected else self.added_color)
            painter.drawText(
                QRect(rect.right() - stats_total_w, rect.top(), added_w, rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter, added_str)

            # Draw -M (red / white-on-select)
            painter.setPen(QColor("white") if is_selected else self.removed_color)
            painter.drawText(
                QRect(rect.right() - deleted_w, rect.top(), deleted_w, rect.height()),
                Qt.AlignLeft | Qt.AlignVCenter, deleted_str)

            filename_rect = QRect(rect.left(), rect.top(),
                                  rect.width() - stats_total_w - 8, rect.height())
        else:
            filename_rect = rect

        # Draw filename, elided if too long; file-filter matches get a
        # yellow wash on the matching substring (drawn unclipped-elided).
        painter.setPen(text_color)
        match_ranges = index.data(FILTER_MATCH_ROLE)
        if match_ranges:
            _paint_matched_text(painter, filename, filename_rect, match_ranges,
                                text_color, opt.font)
        else:
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
        from PySide6.QtWidgets import (
            QApplication,
            QStyleOptionViewItem,
        )
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
        elif stats_text:
            if stats_text.startswith("+"):
                painter.setPen(QColor("white") if is_selected else self.added_color)
            elif stats_text.startswith("-"):
                painter.setPen(QColor("white") if is_selected else self.removed_color)
            else:
                painter.setPen(QColor("white") if is_selected else option.palette.text().color())
            text_w = fm.horizontalAdvance(stats_text) + 4
            painter.drawText(
                QRect(rect.right() - text_w, rect.top(), text_w, rect.height()),
                Qt.AlignRight | Qt.AlignVCenter, stats_text)

        painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), max(hint.height(), 28))


class FileNameDelegate(QStyledItemDelegate):
    """Paints tree column 0 (file/folder names) with file-filter match highlights."""

    def paint(self, painter, option, index):
        from PySide6.QtWidgets import (
            QApplication,
            QStyleOptionViewItem,
        )
        from PySide6.QtWidgets import QStyle as _QStyle

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        style = opt.widget.style() if opt.widget else QApplication.style()
        opt.text = ""
        style.drawControl(_QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        text_rect = style.subElementRect(_QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)

        painter.save()
        painter.setFont(opt.font)

        is_selected = bool(option.state & _QStyle.State_Selected)
        text_color = QColor("white") if is_selected else option.palette.text().color()
        rect = text_rect.adjusted(0, 0, -4, 0) if not text_rect.isNull() else option.rect.adjusted(6, 0, -6, 0)
        filename = index.data(Qt.DisplayRole) or ""
        match_ranges = index.data(FILTER_MATCH_ROLE)

        if match_ranges:
            _paint_matched_text(painter, filename, rect, match_ranges,
                                text_color, opt.font)
        else:
            fm = QFontMetrics(opt.font)
            painter.setPen(text_color)
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter,
                             fm.elidedText(filename, Qt.ElideMiddle, rect.width()))

        painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), max(hint.height(), 28))


class _FilterSearchInput(QLineEdit):
    """Search input for FileListFilter: Esc closes, Enter/Shift+Enter navigate."""

    def __init__(self, owner):
        super().__init__()
        self._owner = owner

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._owner.close_bar()
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                self._owner.prev_match()
            else:
                self._owner.next_match()
            event.accept()
            return
        super().keyPressEvent(event)


# Strong references to live FileListFilter instances. Wrappers must outlive
# their Qt-side connections: if Python wrapper dies while the C++ object
# (parented to the widget) stays alive, later signal emissions look up bound
# methods on the deleted wrapper and segfault PySide6. Released when the
# attached widget is destroyed.
_FILE_FILTERS = set()


class FileListFilter(QObject):
    """Hover-revealed "Filter files" control for a file QListWidget / QTreeWidget.

    Mouse-only: a small magnifier button floats over the list while the mouse
    is over it; clicking it opens a filter bar **docked as a row above the
    list** (the list shrinks, so no file row is ever covered) that live-
    filters rows. Check states and selection on hidden rows are preserved.
    A model reset (list repopulation, e.g. on commit change) closes the bar
    and restores the full list."""

    DEBOUNCE_MS = 200

    def __init__(self, widget, parent=None):
        super().__init__(parent or widget)
        self.widget = widget
        self.viewport = widget.viewport()
        self._is_tree = isinstance(widget, QTreeWidget)
        self._hover = False
        self._tagged = []
        self._hidden_rows = []
        self._hidden_items = []
        self._matches = []
        self._current = -1
        # Set by _dock_bar on first open: the wrapper row [bar, widget]
        # inserted where the widget sits in its splitter/layout.
        self._container = None

        # The magnifier button is a child of the *widget* (not the viewport):
        # QAbstractScrollArea::scrollContentsBy moves viewport children with
        # the scroll, widget children stay pinned. The bar becomes a real
        # layout row above the list when opened (see _dock_bar) so it never
        # covers file rows; parentless widgets (standalone/test embeds) keep
        # it as a pinned overlay over the viewport top.
        self.button = QToolButton(widget)
        self.button.setToolTip("Filter files")
        self.button.setFixedSize(24, 24)
        self.button.setIcon(_magnifier_icon(
            widget.palette().color(QPalette.ButtonText)))
        self._style_hover_button()
        self.button.clicked.connect(self.open_bar)

        self.bar = QWidget(widget)
        self.bar.setObjectName("FileFilterBar")
        # Bar metrics and button construction mirror DiffSearchBar (the
        # "Search in diff" toolbar) so both bars look the same.
        bar_layout = QHBoxLayout(self.bar)
        bar_layout.setContentsMargins(5, 5, 5, 5)
        bar_layout.setSpacing(5)

        icon_label = QLabel()
        icon_label.setPixmap(_magnifier_icon(
            widget.palette().color(QPalette.ButtonText)).pixmap(14, 14))
        bar_layout.addWidget(icon_label)

        self.input = _FilterSearchInput(self)
        self.input.setPlaceholderText("Filter files...")
        self.input.setMinimumHeight(28)
        self.input.setClearButtonEnabled(True)
        self.input.textChanged.connect(self._schedule_apply)
        bar_layout.addWidget(self.input, 1)

        self.counter = QLabel("0/0")
        self.counter.setMinimumWidth(40)
        self.counter.setAlignment(Qt.AlignCenter)
        bar_layout.addWidget(self.counter)

        self.btn_prev = QToolButton()
        self.btn_prev.setText("<")
        self.btn_prev.setFixedSize(28, 28)
        self.btn_prev.setToolTip("Previous match")
        self.btn_prev.clicked.connect(self.prev_match)
        bar_layout.addWidget(self.btn_prev)

        self.btn_next = QToolButton()
        self.btn_next.setText(">")
        self.btn_next.setFixedSize(28, 28)
        self.btn_next.setToolTip("Next match")
        self.btn_next.clicked.connect(self.next_match)
        bar_layout.addWidget(self.btn_next)

        self.btn_close = QToolButton()
        self.btn_close.setText("\u2715")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setToolTip("Close filter")
        self.btn_close.clicked.connect(self.close_bar)
        bar_layout.addWidget(self.btn_close)

        # Weakref closures: modelAboutToBeReset and the debounce timer can
        # fire after this Python wrapper is gone (e.g. tests deleting the
        # wrapper early) — calling a bound method of a deleted wrapper
        # segfaults PySide6.
        self_ref = weakref.ref(self)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(self.DEBOUNCE_MS)

        def _on_timeout():
            obj = self_ref()
            if obj is not None:
                obj._apply()

        self._debounce.timeout.connect(_on_timeout)

        if self._is_tree:
            widget.setItemDelegateForColumn(0, FileNameDelegate(parent=widget))

        self.viewport.installEventFilter(self)

        def _on_model_reset():
            obj = self_ref()
            if obj is not None:
                obj.reset()

        widget.model().modelAboutToBeReset.connect(_on_model_reset)

        self.button.hide()
        self.bar.hide()

        _FILE_FILTERS.add(self)

        def _on_widget_destroyed(_obj=None):
            _FILE_FILTERS.discard(self)

        widget.destroyed.connect(_on_widget_destroyed)

    # --- hover button / bar positioning -----------------------------------

    def eventFilter(self, obj, event):
        try:
            if obj is self.viewport:
                etype = event.type()
                if etype == QEvent.Enter:
                    self._hover = True
                    if not self.bar.isVisible():
                        self._position_button()
                        self.button.show()
                elif etype == QEvent.Leave:
                    self._hover = False
                    if not self.bar.isVisible():
                        self._hide_button_if_cursor_away()
                elif etype == QEvent.Resize:
                    self._position_button()
                    if self._container is None:
                        self._position_bar()
                elif etype in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange):
                    self.button.setIcon(_magnifier_icon(
                        self.widget.palette().color(QPalette.ButtonText)))
                    self._style_hover_button()
                    if self._container is None:
                        self._style_bar()
        except (AttributeError, RuntimeError):
            # Half-torn-down state during widget destruction; ignore.
            return False
        return super().eventFilter(obj, event)

    def _vp_offset(self):
        return self.viewport.mapTo(self.widget, QPoint(0, 0))

    def _position_button(self):
        off = self._vp_offset()
        self.button.move(
            off.x() + self.viewport.width() - self.button.width() - 4,
            off.y() + 4)

    def _position_bar(self):
        """Overlay fallback (parentless widget): pin the bar over the
        viewport's top. Docked bars are positioned by their layout."""
        off = self._vp_offset()
        width = max(200, self.viewport.width() - 8)
        self.bar.setGeometry(off.x() + 4, off.y() + 4, width, 38)

    def _dock_bar(self):
        """Make the bar a real row above the list (lazy, idempotent).

        Wraps the list/tree in a container [bar, widget] and puts the
        container back where the widget sits in its splitter or layout, so
        opening the bar shrinks the list instead of covering its first rows;
        hiding the bar collapses the row again. Called on first open because
        attach points construct FileListFilter *before* inserting the list
        into its parent, so the parent is unknown at __init__ time.

        Returns False when the widget has no splitter/layout parent
        (standalone lists) — the caller keeps the pinned overlay instead.
        """
        if self._container is not None:
            return True
        widget = self.widget
        parent = widget.parentWidget()
        if parent is None:
            return False
        if isinstance(parent, QSplitter) and parent.indexOf(widget) >= 0:
            host, idx = parent, parent.indexOf(widget)
        else:
            layout = parent.layout()
            if not isinstance(layout, QBoxLayout) or layout.indexOf(widget) < 0:
                return False
            host, idx = layout, layout.indexOf(widget)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)
        container_layout.addWidget(self.bar)
        container_layout.addWidget(widget, 1)
        # The widget left its old slot above, so inserting at the captured
        # index puts the container exactly where the widget was.
        host.insertWidget(idx, container)
        self._container = container
        return True

    def _hide_button_if_cursor_away(self):
        pos = QCursor.pos()
        for child in (self.button, self.bar):
            if child.isVisible() and child.rect().contains(child.mapFromGlobal(pos)):
                return
        self.button.hide()

    def _style_hover_button(self):
        """Opaque palette-aware plate for the hover button.

        A fully transparent button let row text (stats, filenames) show
        through and made the icon hard to see, especially over the stats
        column. Use palette roles so it reads in both light and dark themes.
        """
        pal = self.widget.palette()
        bg = pal.color(QPalette.Button)
        border = pal.color(QPalette.Mid)
        light = bg.lightness() >= 128
        hover_bg = bg.darker(106) if light else bg.lighter(106)
        press_bg = bg.darker(115) if light else bg.lighter(115)
        self.button.setStyleSheet(
            "QToolButton { border: 1px solid %s; border-radius: 4px;"
            " background: %s; }"
            " QToolButton:hover { border: 1px solid %s; background: %s; }"
            " QToolButton:pressed { border: 1px solid %s; background: %s; }"
            % (border.name(), bg.name(),
               pal.color(QPalette.ButtonText).name(), hover_bg.name(),
               border.name(), press_bg.name()))

    def _style_bar(self):
        """Overlay fallback plate (see _position_bar); docked bars stay
        unstyled so they match the Search in diff toolbar."""
        pal = self.widget.palette()
        self.bar.setStyleSheet(
            "#FileFilterBar { background: %s; border: 1px solid %s;"
            " border-radius: 4px; }"
            % (pal.color(QPalette.Base).name(),
               pal.color(QPalette.Mid).name()))

    # --- open / close / reset ---------------------------------------------

    def open_bar(self):
        if self._dock_bar():
            # Docked row: the layout owns geometry; no chrome — the themed
            # pane background shows through like the Search in diff toolbar.
            self.bar.setStyleSheet("")
        else:
            # Parentless fallback: pinned overlay needs its own plate.
            self._style_bar()
            self._position_bar()
            self.bar.raise_()
        self.bar.show()
        self.button.hide()
        self.input.setFocus()
        self.input.selectAll()

    def close_bar(self):
        self._debounce.stop()
        try:
            self.input.blockSignals(True)
            self.input.clear()
            self.input.blockSignals(False)
        except RuntimeError:
            # Child widgets already deleted during teardown; nothing to restore.
            return
        self._clear_filter()
        self.bar.hide()
        if self._hover:
            self._position_button()
            self.button.show()
        else:
            self.button.hide()

    def reset(self):
        """Close the bar on a model reset (list repopulation, commit change).

        Never touches items: modelAboutToBeReset can fire again after the
        old items are already deleted, and row-hidden state does not survive
        a reset anyway (verified: the view clears it)."""
        try:
            self._debounce.stop()
            self.input.blockSignals(True)
            self.input.clear()
            self.input.blockSignals(False)
        except (AttributeError, RuntimeError):
            return
        self._tagged = []
        self._hidden_rows = []
        self._hidden_items = []
        self._matches = []
        self._current = -1
        try:
            self._update_counter()
            self._set_nav_enabled(False)
            self.bar.hide()
            if self._hover:
                self._position_button()
                self.button.show()
            else:
                self.button.hide()
        except (AttributeError, RuntimeError):
            return

    # --- filtering ---------------------------------------------------------

    def _clear_tagged(self):
        for item in self._tagged:
            if self._is_tree:
                item.setData(0, FILTER_MATCH_ROLE, None)
            else:
                item.setData(FILTER_MATCH_ROLE, None)
        self._tagged = []

    def _clear_filter(self):
        try:
            self._clear_tagged()
            if self._is_tree:
                for item in self._hidden_items:
                    item.setHidden(False)
                self._hidden_items = []
            else:
                for row in self._hidden_rows:
                    self.widget.setRowHidden(row, False)
                self._hidden_rows = []
        except RuntimeError:
            # Items already deleted (teardown) — just forget the references.
            self._tagged = []
            self._hidden_items = []
            self._hidden_rows = []
        self._matches = []
        self._current = -1
        self._update_counter()
        self._set_nav_enabled(False)
        self.viewport.update()

    def _schedule_apply(self, *_):
        self._debounce.start()

    def _apply(self):
        self._debounce.stop()
        term = self.input.text()
        if not term:
            self._clear_filter()
            return
        if self._is_tree:
            self._apply_tree(term)
        else:
            self._apply_list(term)
        if self._matches:
            self._current = 0
            self._select_current()
        else:
            self._current = -1
        self._update_counter()
        self._set_nav_enabled(bool(self._matches))
        self.viewport.update()

    def _apply_list(self, term):
        widget = self.widget
        self._clear_tagged()
        for row in self._hidden_rows:
            widget.setRowHidden(row, False)
        self._hidden_rows = []
        count = widget.count()
        texts = [widget.item(i).text() for i in range(count)]
        hidden = list_filter_hidden(texts, term)
        for row in range(count):
            item = widget.item(row)
            if hidden[row]:
                widget.setRowHidden(row, True)
                self._hidden_rows.append(row)
            else:
                item.setData(FILTER_MATCH_ROLE, filter_match_ranges(item.text(), term))
                self._tagged.append(item)
        self._matches = [widget.item(r) for r in range(count) if not hidden[r]]

    def _apply_tree(self, term):
        widget = self.widget
        self._clear_tagged()
        for item in self._hidden_items:
            item.setHidden(False)
        self._hidden_items = []

        files = []  # (item, full_path) in document order

        def collect(items, prefix):
            for item in items:
                name = item.text(0)
                path = f"{prefix}/{name}" if prefix else name
                if item.childCount() == 0:
                    files.append((item, path))
                else:
                    collect([item.child(i) for i in range(item.childCount())], path)

        collect(self._top_level_items(), "")
        visible_files, visible_folders = tree_filter_sets(
            [p for _, p in files], term)

        self._matches = []
        for item, path in files:
            if path in visible_files:
                leaf_ranges = []
                leaf_start = len(path) - len(item.text(0))
                for start, end in filter_match_ranges(path, term):
                    start = max(start, leaf_start) - leaf_start
                    end = min(end, len(path)) - leaf_start
                    if end > start:
                        leaf_ranges.append((start, end))
                item.setData(0, FILTER_MATCH_ROLE, leaf_ranges)
                self._tagged.append(item)
                self._matches.append(item)
            else:
                item.setHidden(True)
                self._hidden_items.append(item)

        def apply_folders(items, prefix):
            for item in items:
                name = item.text(0)
                path = f"{prefix}/{name}" if prefix else name
                if item.childCount() > 0:
                    if path in visible_folders:
                        item.setHidden(False)
                        item.setExpanded(True)
                        folder_ranges = filter_match_ranges(name, term)
                        item.setData(0, FILTER_MATCH_ROLE, folder_ranges)
                        if folder_ranges:
                            self._tagged.append(item)
                    else:
                        item.setHidden(True)
                        self._hidden_items.append(item)
                    apply_folders([item.child(i) for i in range(item.childCount())], path)

        apply_folders(self._top_level_items(), "")

    def _top_level_items(self):
        if self._is_tree:
            return [self.widget.topLevelItem(i)
                    for i in range(self.widget.topLevelItemCount())]
        return []

    # --- navigation --------------------------------------------------------

    def next_match(self):
        if not self._matches:
            return
        self._current = (self._current + 1) % len(self._matches)
        self._select_current()
        self._update_counter()

    def prev_match(self):
        if not self._matches:
            return
        self._current = (self._current - 1) % len(self._matches)
        self._select_current()
        self._update_counter()

    def _select_current(self):
        if not (0 <= self._current < len(self._matches)):
            return
        item = self._matches[self._current]
        if self._is_tree:
            self.widget.setCurrentItem(item)
            self.widget.scrollToItem(item)
        else:
            row = self.widget.row(item)
            self.widget.setCurrentRow(row)
            self.widget.scrollToItem(item)

    def _update_counter(self):
        if self._matches:
            self.counter.setText(f"{self._current + 1}/{len(self._matches)}")
        else:
            self.counter.setText("0/0")

    def _set_nav_enabled(self, enabled):
        self.btn_prev.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)
