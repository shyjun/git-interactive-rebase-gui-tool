from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from lib.dialogs import NewCommitMessageDialog, RenameMoveDialog
from lib.git_helpers import (
    amend_with_head,
    bulk_commit_all,
    get_full_commit_message,
    rename_move_path,
    stage_files,
)
from lib.app_window.helpers import _log, highlight_button_temporarily


class RenameMoveMixin:
    """Repo menu: rename/move a file or folder in the working tree, then
    stage it, commit it as a new commit, or amend it into HEAD."""

    def handle_rename_move(self):
        """Open the rename/move dialog and run the chosen action."""
        if not self._check_not_viewer_mode():
            return
        dialog = RenameMoveDialog(
            self.repo_path,
            font_size=self.current_font_size,
            font_family=self.current_font_family,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        src, dst = dialog.src_path, dialog.dst_path
        if dialog.action == RenameMoveDialog.StageAction:
            self._rename_move_stage(src, dst)
        elif dialog.action == RenameMoveDialog.CommitAction:
            if not self._check_head_unchanged():
                return
            self._rename_move_commit(src, dst)
        elif dialog.action == RenameMoveDialog.AmendAction:
            if not self._check_head_unchanged():
                return
            self._rename_move_amend(src, dst)

    def _rename_move_stage(self, src, dst):
        """Move the path and stage both sides; no history is created."""
        ok, detail = rename_move_path(self.repo_path, src, dst)
        if not ok:
            QMessageBox.critical(
                self, "Rename/Move Failed",
                f"Could not rename/move the path.\n\n{detail}")
            return
        if not stage_files(self.repo_path, [src, dst]):
            QMessageBox.critical(
                self, "Stage Failed",
                f"The path was renamed/moved, but staging it failed.\n\n"
                f"{src} -> {dst}")
            return
        _log(f"[rename-move] Staged: {src} -> {dst}")
        self.load_history()
        highlight_button_temporarily(self.repo_btn, blinks=5)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("Renamed/Moved and Staged")
        box.setTextFormat(Qt.RichText)
        box.setText(
            f"Renamed/moved and staged.<br><br>"
            f"<b>{src}</b><br>→ <b>{dst}</b><br><br>"
            "Please go to<br><b>Repo → Handle Staged Changes</b><br><br>"
            "to handle the change."
        )
        box.exec()

    def _rename_move_commit(self, src, dst):
        """Move the path and commit it as a new commit containing exactly
        these two paths (git commit --only: deletion + addition = rename)."""
        default_msg = f"rename/move {src} -> {dst}"
        msg_dlg = NewCommitMessageDialog(
            "Commit Rename/Move",
            f"Renaming/moving <b>{src}</b> to <b>{dst}</b> as a new commit.",
            default_msg, self.current_font_size, self.current_font_family, self,
        )
        if msg_dlg.exec() != QDialog.Accepted:
            _log("[rename-move] Commit cancelled before the move.")
            return
        msg = msg_dlg.get_message()
        if not msg:
            return
        ok, detail = rename_move_path(self.repo_path, src, dst)
        if not ok:
            QMessageBox.critical(
                self, "Rename/Move Failed",
                f"Could not rename/move the path.\n\n{detail}")
            return
        # Stage both sides first: git commit --only requires every pathspec to
        # be known to git, and the untracked destination otherwise fails.
        if not stage_files(self.repo_path, [src, dst]):
            QMessageBox.critical(
                self, "Stage Failed",
                f"The path was renamed/moved, but staging it failed.\n\n{detail}")
            return
        self.save_undo_state()
        ok, detail = bulk_commit_all(self.repo_path, msg, [src, dst])
        if ok:
            _log(f"[rename-move] Committed: {src} -> {dst}")
            self.load_history()
            QMessageBox.information(
                self, "Commit Successful",
                f"Done. Rename/move committed.\n\n"
                f"{src} -> {dst}\n\nCommit ID:\n{self.get_head_sha()[:8]}")
        else:
            # The move and staging already happened; the change sits staged.
            QMessageBox.critical(
                self, "Commit Failed",
                f"The path was renamed/moved and staged, but the commit failed.\n\n{detail}")

    def _rename_move_amend(self, src, dst):
        """Move the path and amend it into HEAD with an editable message
        pre-filled from HEAD (same dialog pattern as Amend-all)."""
        old_head = self.get_head_sha()
        default_msg = get_full_commit_message(
            self.repo_path, old_head) if old_head else ""
        msg_dlg = NewCommitMessageDialog(
            "Amend HEAD Commit",
            f"Renaming/moving <b>{src}</b> to <b>{dst}</b> into the HEAD commit.\n"
            "Edit the message below or keep it unchanged to preserve the original.",
            default_msg, self.current_font_size, self.current_font_family, self,
        )
        if msg_dlg.exec() != QDialog.Accepted:
            _log("[rename-move] Amend cancelled before the move.")
            return
        msg = msg_dlg.get_message()
        if not msg:
            return
        ok, detail = rename_move_path(self.repo_path, src, dst)
        if not ok:
            QMessageBox.critical(
                self, "Rename/Move Failed",
                f"Could not rename/move the path.\n\n{detail}")
            return
        # Stage both sides first: git commit --amend --only requires every
        # pathspec to be known to git, and the untracked destination
        # otherwise fails. Only these paths are amended in.
        if not stage_files(self.repo_path, [src, dst]):
            QMessageBox.critical(
                self, "Stage Failed",
                f"The path was renamed/moved, but staging it failed.\n\n{detail}")
            return
        self.save_undo_state()
        ok, detail = amend_with_head(self.repo_path, [src, dst], msg)
        if ok:
            new_head = self.get_head_sha()
            _log(f"[rename-move] Amended: {src} -> {dst}")
            self.load_history()
            QMessageBox.information(
                self, "Amend Successful",
                f"Done. Rename/moved amended into HEAD commit.\n\n"
                f"{src} -> {dst}\n\n"
                f"OLD COMMIT: {old_head[:8]}\nNEW COMMIT: {new_head[:8]}")
        else:
            QMessageBox.critical(
                self, "Amend Failed",
                f"The path was renamed/moved and staged, but the amend failed.\n\n{detail}")
