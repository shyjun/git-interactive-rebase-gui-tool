from PySide6.QtCore import (
    Qt,
    QTimer,
)
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QListWidget,
    QMessageBox,
)


class CommitListWidget(QListWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setSelectionMode(QListWidget.SingleSelection)
        if getattr(main_window, "browse_mode", False):
            self.setDragDropMode(QListWidget.NoDragDrop)
        else:
            self.setDragEnabled(True)
            self.setAcceptDrops(True)
            self.setDropIndicatorShown(True)
            self.setDragDropMode(QListWidget.InternalMove)
        self.setUniformItemSizes(True)
        # Column resize state
        self._resizing = False
        self._resize_col = None  # 'author', 'stats', 'date'
        self._resize_start_x = 0
        self._resize_start_width = 0

    def _get_column_boundaries(self):
        """Return list of (boundary_x, column_name) for resizable columns.

        Each entry is the x-coordinate of the LEFT edge of the column,
        which is also the draggable resize handle for that column.
        """
        viewport = self.viewport()
        right_edge = viewport.width() - 4
        boundaries = []
        mw = self.main_window

        # Date column (rightmost)
        if getattr(mw, 'show_date', True):
            date_w = getattr(mw, 'col_width_date', 100)
            right_edge -= date_w
            boundaries.append((right_edge, 'date'))
            right_edge -= 8  # gap

        # Stats column
        if getattr(mw, 'show_stats', True):
            stats_w = getattr(mw, 'col_width_stats', 80)
            right_edge -= stats_w
            boundaries.append((right_edge, 'stats'))
            right_edge -= 8  # gap

        # Author column
        if getattr(mw, 'show_author', True):
            author_w = getattr(mw, 'col_width_author', 120)
            right_edge -= author_w
            boundaries.append((right_edge, 'author'))

        return boundaries

    def _hit_test_resize(self, x):
        """Check if x is near a column boundary. Return column name or None."""
        for bx, col in self._get_column_boundaries():
            if abs(x - bx) <= 5:
                return col
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            col = self._hit_test_resize(int(event.position().x()))
            if col:
                self._resizing = True
                self._resize_col = col
                self._resize_start_x = int(event.position().x())
                mw = self.main_window
                if col == 'author':
                    self._resize_start_width = getattr(mw, 'col_width_author', 120)
                elif col == 'stats':
                    self._resize_start_width = getattr(mw, 'col_width_stats', 80)
                elif col == 'date':
                    self._resize_start_width = getattr(mw, 'col_width_date', 100)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            dx = int(event.position().x()) - self._resize_start_x
            mw = self.main_window
            # Cap total right-side columns to half viewport so subject always has space
            max_total = self.viewport().width() // 2
            if self._resize_col == 'author':
                new_w = max(60, self._resize_start_width - dx)
                other = getattr(mw, 'col_width_stats', 80) + getattr(mw, 'col_width_date', 100)
                mw.col_width_author = min(new_w, max_total - other)
            elif self._resize_col == 'stats':
                new_w = max(40, self._resize_start_width - dx)
                other = getattr(mw, 'col_width_author', 120) + getattr(mw, 'col_width_date', 100)
                mw.col_width_stats = min(new_w, max_total - other)
            elif self._resize_col == 'date':
                new_w = max(40, self._resize_start_width - dx)
                other = getattr(mw, 'col_width_author', 120) + getattr(mw, 'col_width_stats', 80)
                mw.col_width_date = min(new_w, max_total - other)
            self.viewport().update()
            event.accept()
            return
        # Resize cursor near boundaries
        col = self._hit_test_resize(int(event.position().x()))
        if col:
            self.setCursor(QCursor(Qt.SplitHCursor))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self._resize_col = None
            self.setCursor(QCursor(Qt.ArrowCursor))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def dropEvent(self, event):
        try:
            if getattr(self.main_window, "multi_select_mode", False):
                self._handle_multi_drag_drop(event)
                return

            dragged_item = self.currentItem()
            if not dragged_item:
                super().dropEvent(event)
                return

            sha = dragged_item.text().split()[0]

            target_index = self.indexAt(event.position().toPoint())
            target_row = target_index.row()
            if target_row == -1:
                target_msg = "to the end of the list"
            else:
                target_item = self.item(target_row)
                target_sha = target_item.text().split()[0] if target_item else "N/A"
                target_msg = f"near commit <b>{target_sha}</b>"

            reply = QMessageBox.question(
                self,
                "Confirm Reorder",
                f"Do you want to move commit <b>{sha}</b> {target_msg}?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                if not self.main_window._check_not_viewer_mode():
                    event.ignore()
                    return
                if not self.main_window._check_head_unchanged():
                    event.ignore()
                    return
                if not self.main_window._check_no_unstaged_changes():
                    event.ignore()
                    return

                original_shas = [self.item(i).text().split()[0] for i in range(self.count())]

                super().dropEvent(event)

                new_shas = [self.item(i).text().split()[0] for i in range(self.count())]
                self.main_window.perform_move(new_shas, original_shas)
            else:
                print(f"Cancelled reorder of {sha}.")
                event.ignore()
        except Exception as e:
            print(f"[DRAG-DROP ERROR] {e}")
            import traceback
            traceback.print_exc()

    def _handle_multi_drag_drop(self, event):
        checked = [i for i in range(self.count())
                   if self.item(i).checkState() == Qt.Checked]
        if not checked:
            event.ignore()
            return

        dragged_row = self.currentRow()
        if dragged_row not in checked:
            event.ignore()
            return

        for k in range(len(checked) - 1):
            if checked[k + 1] != checked[k] + 1:
                QMessageBox.critical(
                    self, "Non-Adjacent Commits",
                    "Only adjacent (contiguous) commits can be moved together.\n\n"
                    "Please check only neighbouring commits."
                )
                event.ignore()
                return

        start, end = checked[0], checked[-1]
        block_len = len(checked)
        count = self.count()
        block = list(range(start, end + 1))
        remaining = [i for i in range(count) if i < start or i > end]

        target_row = self.indexAt(event.position().toPoint()).row()
        if target_row == -1:
            insert_pos = len(remaining)
        elif start <= target_row <= end:
            insert_pos = None
        elif target_row < start:
            insert_pos = target_row
        else:
            insert_pos = target_row - block_len

        if insert_pos is None:
            event.ignore()
            return

        new_order = remaining[:insert_pos] + block + remaining[insert_pos:]
        if new_order == list(range(count)):
            event.ignore()
            return

        first_sha = self.item(start).text().split()[0]
        last_sha = self.item(end).text().split()[0]
        if target_row == -1:
            target_msg = "to the end of the list"
        else:
            target_item = self.item(target_row)
            target_sha = target_item.text().split()[0] if target_item else "N/A"
            target_msg = f"near commit <b>{target_sha}</b>"

        reply = QMessageBox.question(
            self,
            "Confirm Reorder",
            f"Do you want to move {block_len} commits "
            f"<b>{first_sha}</b>...<b>{last_sha}</b> {target_msg}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            event.ignore()
            return

        if not self.main_window._check_not_viewer_mode():
            event.ignore()
            return
        if not self.main_window._check_head_unchanged():
            event.ignore()
            return
        if not self.main_window._check_no_unstaged_changes():
            event.ignore()
            return

        # Build SHA map and identify affected range BEFORE the visual reorder.
        # Only the block + displaced commits need rebasing — not all 420.
        sha_map = {}
        for i in range(count):
            item = self.item(i)
            if item.data(Qt.UserRole + 9) != "load_more":
                token = item.text().split()[0]
                if token and len(token) >= 7 and all(c in "0123456789abcdefABCDEF" for c in token):
                    sha_map[i] = token

        affected_start = min(start, insert_pos)
        affected_end = max(end, insert_pos + block_len - 1)

        # Original SHAs for affected range (newest-first, same as list order)
        original_affected = [sha_map[i] for i in range(affected_start, affected_end + 1) if i in sha_map]

        # Upstream: first unaffected commit AFTER the affected range (= parent of oldest affected commit)
        upstream = None
        for i in range(affected_end + 1, count):
            if i in sha_map:
                upstream = sha_map[i]
                break
        if upstream is None:
            upstream = self.commit_sha

        # Do the visual reorder synchronously so the user sees it immediately.
        items = [self.takeItem(0) for _ in range(count)]
        self.blockSignals(True)
        for idx in new_order:
            self.addItem(items[idx])
        self.blockSignals(False)

        # Compute the new order of affected SHAs after the visual reorder.
        new_affected = [sha_map[idx] for idx in new_order if affected_start <= idx <= affected_end and idx in sha_map]

        # Defer perform_move + cleanup to the next event loop iteration.
        # Calling perform_move / load_history inside dropEvent prevents Qt
        # from repainting the viewport — the data is correct but the user
        # sees stale items until they press Refresh.
        def _deferred(new_s, orig_s, upstream_sha):
            self.main_window.perform_move(new_s, orig_s, upstream_override=upstream_sha)
            self.main_window.exit_multi_select_mode()

        QTimer.singleShot(0, lambda: _deferred(new_affected, original_affected, upstream))
        event.accept()
