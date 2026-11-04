from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from lib.dialogs import NewCommitMessageDialog, RemoveFileDialog
from lib.git_helpers import (
    amend_with_head,
    bulk_commit_all,
    get_full_commit_message,
    path_is_dirty,
    remove_file_path,
)
from lib.app_window.helpers import _log, highlight_button_temporarily


class RemoveFileMixin:
    """Repo menu: remove a tracked file or folder from the repository
    (git rm), then stage the deletion, commit it as a new commit, or amend
    it into HEAD."""

    def handle_remove_file(self):
        """Open the remove dialog and run the chosen action."""
        if not self._check_not_viewer_mode():
            return
        dialog = RemoveFileDialog(
            self.repo_path,
            font_size=self.current_font_size,
            font_family=self.current_font_family,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        path = dialog.path
        if dialog.action == RemoveFileDialog.StageAction:
            self._remove_file_stage(path)
        elif dialog.action == RemoveFileDialog.CommitAction:
            if not self._check_head_unchanged():
                return
            self._remove_file_commit(path)
        elif dialog.action == RemoveFileDialog.AmendAction:
            if not self._check_head_unchanged():
                return
            self._remove_file_amend(path)

    def _confirm_removal(self, path):
        """Yes/No confirmation shown before anything is deleted from disk.

        Returns (confirmed, force): *force* is True when the path has
        uncommitted changes that ``git rm -f`` would discard, which the
        warning spells out."""
        dirty = path_is_dirty(self.repo_path, path)
        text = (
            f"Remove <b>{path}</b> from the repository?\n\n"
            "The path is deleted from the working tree and staged as a "
            "deletion (<code>git rm</code>). It stays in git history and "
            "can be restored from any commit."
        )
        if dirty:
            text += (
                f"\n\n<b>Warning:</b> <b>{path}</b> has uncommitted "
                "changes — removing it discards them "
                "(<code>git rm -f</code>)."
            )
        reply = QMessageBox.question(
            self, "Remove from Repo", text,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return reply == QMessageBox.Yes, dirty

    def _remove_file_stage(self, path):
        """Remove the path; git rm stages the deletion itself — no history
        is created."""
        confirmed, force = self._confirm_removal(path)
        if not confirmed:
            _log("[remove] Staging cancelled before the removal.")
            return
        ok, detail = remove_file_path(self.repo_path, path, force=force)
        if not ok:
            QMessageBox.critical(
                self, "Removal Failed",
                f"Could not remove the path.\n\n{detail}")
            return
        _log(f"[remove] Staged removal: {path}")
        self.load_history()
        highlight_button_temporarily(self.repo_btn, blinks=5)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("Removed and Staged")
        box.setTextFormat(Qt.RichText)
        box.setText(
            f"Removed and staged.<br><br><b>{path}</b><br><br>"
            "Please go to<br><b>Repo → Handle Staged Changes</b><br><br>"
            "to handle the change."
        )
        box.exec()

    def _remove_file_commit(self, path):
        """Remove the path and commit the deletion as a new commit
        containing exactly this path (git commit --only)."""
        confirmed, force = self._confirm_removal(path)
        if not confirmed:
            _log("[remove] Commit cancelled before the removal.")
            return
        msg_dlg = NewCommitMessageDialog(
            "Commit Removal",
            f"Removing <b>{path}</b> as a new commit.",
            f"remove {path}", self.current_font_size,
            self.current_font_family, self,
        )
        if msg_dlg.exec() != QDialog.Accepted:
            _log("[remove] Commit cancelled before the removal.")
            return
        msg = msg_dlg.get_message()
        if not msg:
            return
        ok, detail = remove_file_path(self.repo_path, path, force=force)
        if not ok:
            QMessageBox.critical(
                self, "Removal Failed",
                f"Could not remove the path.\n\n{detail}")
            return
        self.save_undo_state()
        ok, detail = bulk_commit_all(self.repo_path, msg, [path])
        if ok:
            _log(f"[remove] Committed removal: {path}")
            self.load_history()
            QMessageBox.information(
                self, "Commit Successful",
                f"Done. Removal committed.\n\n{path}\n\nCommit ID:\n"
                f"{self.get_head_sha()[:8]}")
        else:
            # The removal already happened; the deletion sits staged.
            QMessageBox.critical(
                self, "Commit Failed",
                f"The path was removed and staged, but the commit failed.\n\n{detail}")

    def _remove_file_amend(self, path):
        """Remove the path and amend the deletion into HEAD with an
        editable message pre-filled from HEAD."""
        confirmed, force = self._confirm_removal(path)
        if not confirmed:
            _log("[remove] Amend cancelled before the removal.")
            return
        old_head = self.get_head_sha()
        default_msg = get_full_commit_message(
            self.repo_path, old_head) if old_head else ""
        msg_dlg = NewCommitMessageDialog(
            "Amend HEAD Commit",
            f"Removing <b>{path}</b> into the HEAD commit.\n"
            "Edit the message below or keep it unchanged to preserve the original.",
            default_msg, self.current_font_size, self.current_font_family, self,
        )
        if msg_dlg.exec() != QDialog.Accepted:
            _log("[remove] Amend cancelled before the removal.")
            return
        msg = msg_dlg.get_message()
        if not msg:
            return
        ok, detail = remove_file_path(self.repo_path, path, force=force)
        if not ok:
            QMessageBox.critical(
                self, "Removal Failed",
                f"Could not remove the path.\n\n{detail}")
            return
        self.save_undo_state()
        ok, detail = amend_with_head(self.repo_path, [path], msg)
        if ok:
            new_head = self.get_head_sha()
            _log(f"[remove] Amended removal: {path}")
            self.load_history()
            QMessageBox.information(
                self, "Amend Successful",
                f"Done. Removal amended into HEAD commit.\n\n{path}\n\n"
                f"OLD COMMIT: {old_head[:8]}\nNEW COMMIT: {new_head[:8]}")
        else:
            QMessageBox.critical(
                self, "Amend Failed",
                f"The path was removed and staged, but the amend failed.\n\n{detail}")
