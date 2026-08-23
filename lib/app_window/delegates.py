from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QApplication, QStyledItemDelegate, QStyle, QStyleOptionViewItem,
)
from lib.app_window.helpers import MATCH_ROLE


class CommitItemDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        main_text = opt.text
        opt.text = ""

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

        is_diff_start = (main_win and getattr(main_win, 'consolidated_diff_start_sha', None)
                         and sha == main_win.consolidated_diff_start_sha)
        if is_diff_start:
            painter.save()
            painter.fillRect(option.rect.left(), option.rect.top(), 4, option.rect.height(), QColor("#ff9800"))
            painter.restore()

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
        show_tags = getattr(main_win, "show_tags", False)

        branch_text = index.data(Qt.UserRole + 1) if show_branches else None
        tag_text = index.data(Qt.UserRole + 8) if show_tags else None
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, widget)
        if not is_multi:
            text_rect = text_rect.adjusted(GRAPH_WIDTH, 0, 0, 0)

        painter.save()
        if opt.state & QStyle.State_Selected:
            painter.setPen(opt.palette.highlightedText().color())
        else:
            painter.setPen(opt.palette.text().color())

        is_dark = getattr(main_win, 'is_dark_theme', True) if main_win else True

        if not hasattr(self, '_bold_font') or getattr(self, '_base_font', None) != opt.font:
            self._base_font = QFont(opt.font)
            self._bold_font = QFont(opt.font)
            self._bold_font.setBold(True)

        painter.setFont(self._bold_font)
        fm_bold = painter.fontMetrics()

        current_x = text_rect.left()

        if branch_text:
            branches = branch_text.split(", ")
            for br in branches:
                is_remote = br.startswith("origin/")
                if is_remote:
                    color = QColor("#ffb74d") if is_dark else QColor("#e65100")
                else:
                    color = QColor("#81c784") if is_dark else QColor("#2e7d32")
                if opt.state & QStyle.State_Selected:
                    color = opt.palette.highlightedText().color()
                painter.setPen(color)
                br_box = f"[{br}] "
                painter.drawText(QRect(current_x, text_rect.top(), text_rect.width() - (current_x - text_rect.left()), text_rect.height()),
                                 Qt.AlignLeft | Qt.AlignVCenter, br_box)
                current_x += fm_bold.horizontalAdvance(br_box)

        if tag_text:
            tags = tag_text.split(", ")
            for tg in tags:
                color = QColor("#ce93d8") if is_dark else QColor("#7b1fa2")
                if opt.state & QStyle.State_Selected:
                    color = opt.palette.highlightedText().color()
                painter.setPen(color)
                tg_box = f"{{{tg}}} "
                painter.drawText(QRect(current_x, text_rect.top(), text_rect.width() - (current_x - text_rect.left()), text_rect.height()),
                                 Qt.AlignLeft | Qt.AlignVCenter, tg_box)
                current_x += fm_bold.horizontalAdvance(tg_box)

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

        use_bold = bool(index.data(MATCH_ROLE)) and main_win is not None and not getattr(main_win, 'search_display_only', False)
        if use_bold:
            if not hasattr(self, '_bold_font') or getattr(self, '_base_font', None) != opt.font:
                self._base_font = QFont(opt.font)
                self._bold_font = QFont(opt.font)
                self._bold_font.setBold(True)
            painter.setFont(self._bold_font)

        main_rect = text_rect.adjusted(left_boundary - text_rect.left(), 0, right_boundary - text_rect.right() - 8, 0)
        elided_main = painter.fontMetrics().elidedText(main_text, Qt.ElideRight, main_rect.width())
        painter.drawText(main_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_main)
        painter.restore()

        painter.restore()
