import math
from PySide6.QtCore import Qt, QSize, QPoint
from PySide6.QtGui import QColor, QPainter, QPixmap, QPen, QPainterPath, QBrush, QPalette, QIcon


class ToolbarMixin:
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

    def _set_rescan_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_rescan)

    def _set_pop_stash_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_pop_stash)

    def _set_undo_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_undo)

    def _set_refresh_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_refresh)

    def _set_exit_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_exit, QColor("red"))

    def _set_exit_viewer_mode_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_edit)

    def _set_configure_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_gear)

    def _set_repo_icon(self, button):
        self._apply_toolbar_icon(button, self._draw_repo)

    def _refresh_toolbar_icons(self):
        self._set_theme_icon(self.theme_menu_btn)
        self._set_rescan_icon(self.rescan_btn)
        self._set_undo_icon(self.undo_btn)
        self._set_refresh_icon(self.refresh_btn)
        self._set_exit_icon(self.exit_btn)
        self._set_exit_viewer_mode_icon(self.exit_viewer_mode_btn)
        self._set_pop_stash_icon(self.pop_stash_btn)
        self._set_repo_icon(self.repo_btn)
        self._set_configure_icon(self.configure_btn)

    def _draw_rescan(self, painter, color):
        pen = QPen(color, 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        painter.drawEllipse(2.0, 2.0, 8.8, 8.8)
        painter.drawLine(9.4, 9.4, 14.0, 14.0)

    def _draw_pop_stash(self, painter, color):
        pen = QPen(color, 1.7)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        painter.drawLine(8.0, 10.5, 8.0, 4.5)
        painter.drawLine(5.0, 7.5, 8.0, 4.5)
        painter.drawLine(11.0, 7.5, 8.0, 4.5)
        painter.drawRoundedRect(3.0, 10.5, 10.0, 3.0, 1.0, 1.0)

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

    def _draw_edit(self, painter, color):
        pen = QPen(color, 1.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        painter.drawLine(12, 2, 7, 7)
        painter.drawLine(14, 4, 9, 9)
        painter.drawLine(12, 2, 14, 4)
        painter.drawLine(7, 7, 3, 11)
        painter.drawLine(9, 9, 3, 11)
        painter.drawLine(11, 3, 13, 5)

    def _draw_gear(self, painter, color):
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        cos_45 = (1, .707, 0, -.707, -1, -.707, 0, .707)
        sin_45 = (0, .707, 1, .707, 0, -.707, -1, -.707)
        for i in range(8):
            dx, dy = cos_45[i], sin_45[i]
            painter.drawLine(QPoint(8 + dx * 5.4, 8 + dy * 5.4),
                             QPoint(8 + dx * 7.0, 8 + dy * 7.0))

        painter.drawEllipse(QPoint(8, 8), 4.0, 4.0)
        painter.setBrush(color)
        painter.drawEllipse(QPoint(8, 8), 1.8, 1.8)

    def _draw_repo(self, painter, color):
        pen = QPen(color, 1.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        # Folder with tab
        painter.drawRoundedRect(1.5, 5.5, 13, 8, 1.5, 1.5)
        painter.drawLine(2, 5.5, 5.5, 5.5)
        painter.drawLine(5.5, 5.5, 6.5, 7.5)
        painter.drawLine(6.5, 7.5, 14.5, 7.5)
        painter.drawLine(3.5, 10.5, 9.5, 10.5)
