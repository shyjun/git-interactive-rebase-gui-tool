from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from lib.git_helpers import get_full_head_sha
from lib.dialogs import ProgressDialog
from lib.app_window.workers import GitWorker


class UndoMixin:
    def handle_set_best_commit(self, item):
        sha = item.text().split()[0]
        self.best_commit_sha = sha
        self.best_commit_btn.setText(f"Reset Hard to BEST_COMMITID ({sha[:8]})")
        self.best_commit_btn.setEnabled(True)

    def handle_best_commit_reset(self):
        if not self.best_commit_sha:
            return
        print(f"[undo] Reset to BEST_COMMIT requested: {self.best_commit_sha[:10]}")
        reply = QMessageBox.question(
            self,
            "Confirm BEST_COMMITID Reset",
            f"Are you sure you want to <b>reset --hard</b> to BEST_COMMITID (<b>{self.best_commit_sha[:8]}</b>)?<br><br>"
            "This will discard all uncommitted changes and move your branch to this state.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            print("[undo] Reset to BEST_COMMIT confirmed")
            self.perform_reset(self.best_commit_sha)
        else:
            print(f"[undo] Cancelled reset to BEST_COMMITID ({self.best_commit_sha[:8]}).")

    def handle_failsafe_reset(self):
        # We use cached values from load_history for performance.
        if self.cached_current_head_full_sha == self.start_time_full_head and not self.cached_has_uncommitted:
            QMessageBox.warning(self, "No Changes", "HEAD is already at START_TIME_HEAD and there are no uncommitted changes.")
            return

        print(f"[undo] Failsafe reset requested: {self.start_time_head[:10]}")
        reply = QMessageBox.question(
            self,
            "Confirm Failsafe Reset",
            f"Are you sure you want to <b>reset --hard</b> to START_TIME_HEAD (<b>{self.start_time_head[:8]}</b>)?<br><br>"
            "This will discard all uncommitted changes and move your branch to this state.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            print("[undo] Failsafe reset confirmed")
            self.save_undo_state()
            self.perform_reset(self.start_time_head)
        else:
            print(f"[undo] Cancelled failsafe reset to {self.start_time_head[:8]}.")

    def save_undo_state(self):
        """Saves current HEAD to last_head and enables Undo button."""
        self.last_head = get_full_head_sha(self.repo_path)
        self.undo_btn.setEnabled(True)

    def handle_undo_shortcut(self):
        """Handles the Ctrl+Z shortcut for undoing the last operation.

        Defers to native text-editing undo when a text field has focus,
        and does nothing when there is no pending undoable operation.
        """
        if not self._undo_focus_guard():
            return  # let native text-edit undo take over
        if not self.last_head:
            return  # nothing to undo yet
        self.handle_undo()

    def _undo_focus_guard(self):
        """Return True only when no text-edit widget has focus, so Ctrl+Z
        performs app 'undo last operation' instead of native text editing undo."""
        focus = self.focusWidget()
        if focus is None:
            return True
        from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
        return not isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit))

    def handle_undo(self):
        """Handles the Undo action by resetting hard to last_head."""
        if not self._check_not_viewer_mode():
            return
        if not self.last_head:
            return

        print(f"[undo] Undo requested: reset to {self.last_head[:10]}")
        reply = QMessageBox.question(
            self,
            "Confirm Undo",
            f"Are you sure you want to <b>reset --hard</b> to the state before the last operation (<b>{self.last_head[:8]}</b>)?<br><br>"
            "This will discard all uncommitted changes and move your branch to this state.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            print("[undo] Undo confirmed")
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
