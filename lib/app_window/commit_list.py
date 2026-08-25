from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QMessageBox


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
            print("Cancelled multi-reorder.")
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

        original_shas = [self.item(i).text().split()[0] for i in range(count)]

        items = [self.takeItem(0) for _ in range(count)]
        self.blockSignals(True)
        for idx in new_order:
            self.addItem(items[idx])
        self.blockSignals(False)

        new_shas = [self.item(i).text().split()[0] for i in range(count)]
        self.main_window.perform_move(new_shas, original_shas)
        self.main_window.exit_multi_select_mode()
        event.accept()
