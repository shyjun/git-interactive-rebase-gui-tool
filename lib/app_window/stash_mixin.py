import subprocess
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from lib.git_helpers import (
    get_stash_status, get_stash_subject, stash_pop_can_apply,
    stash_pop, merge_into_stash, get_unstaged_files, get_untracked_files,
    get_unstaged_file_diff, get_unstaged_file_stats,
    stage_files, commit_staged, amend_staged, apply_patch_to_index,
    get_full_commit_message,
)
from lib.dialogs import (
    StashNoticeDialog, CommitSelectivelyDialog, SelectiveHunkDialog,
    NewCommitMessageDialog, ProgressDialog,
)
from lib.app_window.helpers import highlight_button_temporarily
from lib.app_window.split_utils import parse_hunks as _parse_hunks, rebuild_patch as _rebuild_patch


class StashMixin:
    """Stash management and selective commit operations."""

    def _update_stash_btn_visibility(self):
        """Show the 'Pop the app managed stash' button only while a managed stash exists."""
        self.pop_stash_btn.setVisible(bool(self.app_managed_stash_sha))

    def _flash_pop_stash_btn(self):
        """Briefly highlight the 'Pop the app managed stash' button after a stash is created."""
        highlight_button_temporarily(self.pop_stash_btn, blinks=5)

    def _show_managed_stash_missing_box(self, sha, not_at_head):
        """Show that the managed stash is missing or not at HEAD, offering to copy the SHA."""
        short_sha = sha[:8]
        if not_at_head:
            text = (f"The stash created by app ({short_sha}) is found in stash list, but not at HEAD position. "
                    f"Please investigate and stash pop manually.\n\n"
                    f"Please note down the sha: {short_sha}")
        else:
            text = (f"{short_sha} not found in stash list. "
                    f"Please investigate and stash pop manually.\n\n"
                    f"Please note down the sha: {short_sha}")
        dialog_result = StashNoticeDialog(text, sha, self).exec()
        if dialog_result == StashNoticeDialog.ManualPopResult:
            self.app_managed_stash_sha = None
            self._update_stash_btn_visibility()

    def handle_pop_managed_stash(self):
        """Pop the app-created managed stash after a confirmation showing stash details."""
        if not self.app_managed_stash_sha:
            return
        print(f"[stash] Pop managed stash: {self.app_managed_stash_sha[:10]}")
        status, _ = get_stash_status(self.repo_path, self.app_managed_stash_sha)
        if status == "ERROR":
            QMessageBox.critical(
                self, "Error",
                f"Could not verify the status of the app-created stash ({self.app_managed_stash_sha[:8]}). "
                f"Please investigate and stash pop manually."
            )
            return
        if status == "NOT_FOUND":
            self._show_managed_stash_missing_box(self.app_managed_stash_sha, not_at_head=False)
            return
        if status == "NOT_HEAD":
            self._show_managed_stash_missing_box(self.app_managed_stash_sha, not_at_head=True)
            return
        short_sha = self.app_managed_stash_sha[:8]
        subject = get_stash_subject(self.repo_path, self.app_managed_stash_sha)
        details = f"<b>SHA:</b> {short_sha}" + (f"<br><b>Message:</b> {subject}" if subject else "")
        box = QMessageBox(self)
        box.setWindowTitle("Pop Managed Stash")
        box.setTextFormat(Qt.RichText)
        box.setText(f"Pop the app-created stash and restore its changes?<br><br>{details}")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        answer = box.exec()
        if answer != QMessageBox.Yes:
            return
        can_apply, conflict_detail = stash_pop_can_apply(self.repo_path, self.app_managed_stash_sha)
        if not can_apply:
            QMessageBox.warning(
                self,
                "Cannot Pop Managed Stash",
                f"Popping this stash would create a merge conflict (HEAD has moved since it was created), "
                f"so it was not applied.\n\n"
                f"{conflict_detail}\n\n"
                "The stash was left untouched and will be offered again at exit."
            )
            return
        success, msg = stash_pop(self.repo_path, self.app_managed_stash_sha)
        if success:
            self.app_managed_stash_sha = None
            self._update_stash_btn_visibility()
            QMessageBox.information(self, "Pop Successful", f"Stash popped successfully.{(' (' + msg + ')') if msg else ''}")
        else:
            detail = f"\n\n{msg}" if msg else ""
            QMessageBox.critical(self, "Error", "Failed to pop the managed stash. Please resolve any conflict markers manually or try again." + detail)
            self._update_stash_btn_visibility()

    def _merge_into_managed_stash(self):
        """Merges the current unstaged changes into the existing app-created stash."""
        old_sha = self.app_managed_stash_sha
        if not old_sha:
            return
        print(f"[stash] Merging into managed stash: {old_sha[:10]}")
        progress = ProgressDialog("Merging Stash", "Merging changes into app-created stash...", self)
        progress.show()
        QApplication.processEvents()
        try:
            new_sha = merge_into_stash(self.repo_path, old_sha)
        finally:
            progress.close()

        if not new_sha:
            QMessageBox.critical(
                self, "Merge Failed",
                "Unable to merge the current unstaged changes into the existing app-created stash.\n\n"
                "The original app-created stash has not been modified.\n"
                "Your current unstaged changes have been restored.\n"
                "No changes have been lost."
            )
            return
        if new_sha == old_sha:
            QMessageBox.information(
                self, "No Changes to Merge",
                "There were no changes to merge into the app-created stash."
            )
            return

        self.app_managed_stash_sha = new_sha
        self._update_stash_btn_visibility()
        self._flash_pop_stash_btn()
        QMessageBox.information(
            self, "Merge Successful",
            f"Successfully merged the current unstaged changes into the app-created stash.\n\n"
            f"Old app-created stash:\n    {old_sha}\n\n"
            f"New app-created stash:\n    {new_sha}"
        )

    def _commit_selectively_from_dialog(self):
        """Opens the 'Commit Selectively' dialog where the user chooses which files
        to commit, then either commits those files whole or drills into 'git add -p'
        for hunk-level staging. Re-runs the same safety checks as every other
        history-modifying operation first."""
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return

        print("[stash] Opening selective commit dialog")
        try:
            unstaged_files = get_unstaged_files(self.repo_path, ignore_submodules=True)
            if not unstaged_files:
                QMessageBox.information(self, "Commit Selectively",
                                        "No unstaged changes to commit.")
                return
            file_stats = get_unstaged_file_stats(self.repo_path, ignore_submodules=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load unstaged changes: {e}")
            return

        dialog = CommitSelectivelyDialog(
            self.repo_path, unstaged_files, file_stats,
            self.current_font_size, self
        )
        result = dialog.exec()

        if result not in (CommitSelectivelyDialog.CommitSelectedResult,
                          CommitSelectivelyDialog.GitAddPResult,
                          CommitSelectivelyDialog.AmendSelectedResult):
            return  # Cancelled - nothing was committed

        checked = dialog.checked_files()
        if not checked:
            QMessageBox.information(self, "No Files Selected",
                                    "No files were selected. Nothing was committed.")
            return

        if result == CommitSelectivelyDialog.CommitSelectedResult:
            self._selective_commit_whole_files(checked)
        elif result == CommitSelectivelyDialog.AmendSelectedResult:
            self._selective_amend_files(checked)
        else:
            self._selective_commit_hunks(checked)

    @staticmethod
    def _selective_default_message(checked):
        """Default commit message: 'Changes in <file1>, <file2>' (short if many files)."""
        if len(checked) == 1:
            return f"Changes in {checked[0]}"
        return "Changes in " + ", ".join(checked[:3]) + ("..." if len(checked) > 3 else "")

    def _selective_commit_whole_files(self, checked):
        """Commit only the checked files, as a single commit."""
        msg_dlg = NewCommitMessageDialog(
            "Commit Selected Files",
            "Enter commit message for the selected files:",
            self._selective_default_message(checked),
            self.current_font_size,
            self
        )
        if msg_dlg.exec() != QDialog.Accepted:
            return  # Cancelled - nothing staged yet
        message = msg_dlg.get_message()

        progress = ProgressDialog("Committing Changes", "Staging selected files...", self)
        progress.show()
        QApplication.processEvents()
        try:
            if not stage_files(self.repo_path, checked):
                raise Exception("Failed to stage the selected files.")
            if not commit_staged(self.repo_path, message):
                raise Exception("Git commit failed.")
        except Exception as e:
            subprocess.run(["git", "reset", "-q"], cwd=self.repo_path)
            progress.close()
            QMessageBox.critical(self, "Error", f"Commit failed: {e}")
            return
        progress.close()

        self.save_undo_state()
        self.load_history()
        QMessageBox.information(
            self, "Commit Successful",
            f"Done. Successfully committed the selected file(s).\n\nCommit ID:\n{self.get_head_sha()[:8]}"
        )

    def _selective_amend_files(self, checked):
        """Amend only the checked files into the HEAD commit. The message dialog is
        pre-filled with the current HEAD message (editable)."""
        try:
            default_msg = get_full_commit_message(self.repo_path, "HEAD")
        except Exception:
            default_msg = ""
        msg_dlg = NewCommitMessageDialog(
            "Amend Selected Files",
            "Enter the new commit message for the amend:",
            default_msg,
            self.current_font_size,
            self
        )
        if msg_dlg.exec() != QDialog.Accepted:
            return  # Cancelled - nothing staged yet
        message = msg_dlg.get_message()

        progress = ProgressDialog("Amending Changes", "Staging selected files...", self)
        progress.show()
        QApplication.processEvents()
        try:
            if not stage_files(self.repo_path, checked):
                raise Exception("Failed to stage the selected files.")
            if not amend_staged(self.repo_path, message):
                raise Exception("Git commit --amend failed.")
        except Exception as e:
            subprocess.run(["git", "reset", "-q"], cwd=self.repo_path)
            progress.close()
            QMessageBox.critical(self, "Error", f"Amend failed: {e}")
            return
        progress.close()

        self.save_undo_state()
        self.load_history()
        QMessageBox.information(
            self, "Amend Successful",
            f"Done. Selected files were amended into the HEAD commit.\n\n"
            f"Commit ID:\n{self.get_head_sha()[:8]}"
        )

    def _selective_commit_hunks(self, checked):
        """Interactive 'git add -p': stage only the selected hunks of the checked
        files (git apply --cached), then commit or amend exactly those."""
        diff_by_file = {}
        hunks_by_file = {}
        try:
            for f in checked:
                diff_text = get_unstaged_file_diff(self.repo_path, f)
                diff_by_file[f] = diff_text
                hunks_by_file[f] = _parse_hunks(diff_text)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load diffs for hunk selection: {e}")
            return

        if not any(hunks_by_file.get(f) for f in checked):
            QMessageBox.information(
                self, "No Hunks",
                "None of the checked files contain individual diff hunks "
                "(they may be binary). No changes were staged."
            )
            return

        dialog = SelectiveHunkDialog(
            self.repo_path, checked, diff_by_file, hunks_by_file,
            self.current_font_size, self
        )
        result = dialog.exec()
        if result not in (SelectiveHunkDialog.CommitResult, SelectiveHunkDialog.AmendResult):
            return  # Cancelled - nothing staged

        kept_by_file = dialog.selected_indices_by_file()

        patch_by_file = {}
        for f in checked:
            hunks = hunks_by_file.get(f, [])
            kept = kept_by_file.get(f, [])
            if not kept:
                continue
            header_lines = []
            for line in diff_by_file[f].splitlines():
                if line.startswith("@@"):
                    break
                header_lines.append(line)
            patch_by_file[f] = _rebuild_patch("\n".join(header_lines), hunks, kept)

        # Checked files with no parseable hunks (e.g. binaries) are staged whole
        whole_files = [f for f in checked if not hunks_by_file.get(f)]

        if not patch_by_file and not whole_files:
            QMessageBox.information(self, "No Hunks Selected",
                                    "No hunks were selected. Nothing was staged.")
            return

        # Ask for the message here so that cancelling leaves nothing staged
        if result == SelectiveHunkDialog.CommitResult:
            default_msg = self._selective_default_message(checked)
            label = "Enter commit message for the selected hunks:"
        else:
            try:
                default_msg = get_full_commit_message(self.repo_path, "HEAD")
            except Exception:
                default_msg = ""
            label = "Enter the new commit message for the amend:"
        msg_dlg = NewCommitMessageDialog("Commit Message", label, default_msg,
                                        self.current_font_size, self)
        if msg_dlg.exec() != QDialog.Accepted:
            return  # Cancelled - nothing staged
        message = msg_dlg.get_message()

        progress = ProgressDialog("Staging Selected Hunks", "Staging selected hunks...", self)
        progress.show()
        QApplication.processEvents()
        try:
            for f, patch in patch_by_file.items():
                apply_patch_to_index(self.repo_path, patch)
            if whole_files:
                if not stage_files(self.repo_path, whole_files):
                    raise Exception("Failed to stage whole files (no-hunk files).")
            if result == SelectiveHunkDialog.CommitResult:
                if not commit_staged(self.repo_path, message):
                    raise Exception("Git commit failed.")
            else:
                if not amend_staged(self.repo_path, message):
                    raise Exception("Git commit --amend failed.")
        except Exception as e:
            subprocess.run(["git", "reset", "-q"], cwd=self.repo_path)
            progress.close()
            QMessageBox.critical(self, "Error",
                                 f"Staging/commit failed: {e}\n\nThe index was reset, "
                                 "so nothing was committed.")
            return
        progress.close()

        self.save_undo_state()
        self.load_history()
        kind = "Amended" if result == SelectiveHunkDialog.AmendResult else "Committed"
        QMessageBox.information(
            self, f"{kind} Successfully",
            f"Done. Selected hunks were staged and committed.\n\n"
            f"{kind} ID:\n{self.get_head_sha()[:8]}"
        )

    def handle_commit_staged(self):
        """Commit all currently staged changes."""
        from lib.git_helpers.status import get_staged_files
        staged = get_staged_files(self.repo_path)
        if not staged:
            QMessageBox.information(self, "No Staged Changes", "There are no staged changes to commit.")
            return

        from lib.dialogs.commit_message_dialogs import NewCommitMessageDialog
        dlg = NewCommitMessageDialog(
            "Commit Staged Changes",
            f"Committing {len(staged)} staged file(s):",
            font_size=self.current_font_size,
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        message = dlg.get_message()
        if not message:
            return

        from lib.git_helpers.commit_ops import commit_staged
        if commit_staged(self.repo_path, message):
            self.load_history()
            QMessageBox.information(self, "Committed", f"Committed {len(staged)} file(s).")
        else:
            QMessageBox.critical(self, "Commit Failed", "Failed to commit staged changes.")

    def handle_unstage_all(self):
        """Unstage all staged changes (git reset HEAD)."""
        from lib.git_helpers.status import get_staged_files
        staged = get_staged_files(self.repo_path)
        if not staged:
            QMessageBox.information(self, "No Staged Changes", "There are no staged changes to unstage.")
            return
        reply = QMessageBox.question(
            self, "Unstage All",
            f"Unstage all {len(staged)} staged file(s)?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        from lib.git_helpers.status import unstage_all
        if unstage_all(self.repo_path):
            self.load_history()
            QMessageBox.information(self, "Unstaged", f"Unstaged {len(staged)} file(s).")
        else:
            QMessageBox.critical(self, "Unstage Failed", "Failed to unstage changes.")

    def handle_view_staged_diff(self):
        """View diff of all staged changes."""
        from lib.git_helpers.status import get_staged_files
        staged = get_staged_files(self.repo_path)
        if not staged:
            QMessageBox.information(self, "No Staged Changes", "There are no staged changes to view.")
            return
        from lib.git_helpers import get_staged_diff
        diff = get_staged_diff(self.repo_path)
        if not diff.strip():
            QMessageBox.information(self, "No Diff", "No staged changes to display.")
            return
        from lib.dialogs.diff_dialogs import DiffViewerDialog
        dlg = DiffViewerDialog(
            f"Staged Changes ({len(staged)} file(s))", "STAGED", diff,
            font_size=self.current_font_size, parent=self,
        )
        dlg.exec()

    def handle_discard_staged(self):
        """Discard all staged changes (destructive!)."""
        from lib.git_helpers.status import get_staged_files
        staged = get_staged_files(self.repo_path)
        if not staged:
            QMessageBox.information(self, "No Staged Changes", "There are no staged changes to discard.")
            return
        reply = QMessageBox.warning(
            self, "Discard Staged Changes",
            f"This will permanently discard all staged changes ({len(staged)} file(s)).\n\n"
            "This action cannot be undone. Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        from lib.git_helpers.status import discard_staged
        if discard_staged(self.repo_path):
            self.load_history()
            QMessageBox.information(self, "Discarded", f"Discarded {len(staged)} staged file(s).")
        else:
            QMessageBox.critical(self, "Discard Failed", "Failed to discard staged changes.")

    def handle_amend_staged(self):
        """Amend the last commit with staged changes."""
        from lib.git_helpers.status import get_staged_files
        staged = get_staged_files(self.repo_path)
        if not staged:
            QMessageBox.information(self, "No Staged Changes", "There are no staged changes to amend.")
            return
        from lib.dialogs.commit_message_dialogs import NewCommitMessageDialog
        dlg = NewCommitMessageDialog(
            "Amend Last Commit",
            f"Amending {len(staged)} staged file(s) into the last commit.\n"
            "Leave the message unchanged to keep the original commit message.",
            font_size=self.current_font_size,
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        message = dlg.get_message()
        if not message:
            return
        from lib.git_helpers.commit_ops import amend_staged
        if amend_staged(self.repo_path, message):
            self.load_history()
            QMessageBox.information(self, "Amended", f"Amended last commit with {len(staged)} file(s).")
        else:
            QMessageBox.critical(self, "Amend Failed", "Failed to amend last commit.")

    def handle_stage_files(self):
        """Open a dialog to select unstaged/untracked files to stage (git add)."""
        unstaged_files = get_unstaged_files(self.repo_path, ignore_submodules=True)
        untracked_files = get_untracked_files(self.repo_path, ignore_submodules=True)
        all_files = unstaged_files + untracked_files
        if not all_files:
            QMessageBox.information(self, "No Files to Stage", "There are no unstaged or untracked files to stage.")
            return
        file_stats = get_unstaged_file_stats(self.repo_path, ignore_submodules=True)
        from lib.dialogs import StageFilesDialog
        dialog = StageFilesDialog(
            self.repo_path, all_files, file_stats,
            font_size=self.current_font_size, parent=self,
        )
        if dialog.exec() == QDialog.Accepted:
            self.load_history()
            QMessageBox.information(
                self, "Files Staged",
                f"Successfully staged {len(dialog.selected_files)} file(s)."
            )
