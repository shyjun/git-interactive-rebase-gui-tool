import os
import re
import subprocess
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QDialog, QFileDialog
from lib.git_helpers import (
    get_full_commit_message, get_revert_commit_message,
    get_commit_subject, resolve_ref, get_commit_files_with_status,
    apply_patch_file,
)
from lib.dialogs import (
    RephraseDialog, RevertCommitDialog, SingleCommitViewDialog,
    ApplyPatchDialog, ProgressDialog, TagCommitDialog,
)
from lib.app_window.help_dialog import HelpDialog


class CommitOpsMixin:
    def handle_apply_patch(self):
        """Applies a patch file to the repository, optionally committing the
        changes using the patch's own commit message."""
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return

        dialog = ApplyPatchDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return

        patch_path = dialog.patch_path
        commit_wanted = dialog.commit_wanted
        if not patch_path:
            QMessageBox.warning(self, "No patch file",
                                "Please select a patch file to apply.")
            return
        if not os.path.isfile(patch_path):
            QMessageBox.critical(self, "Patch file does not exist",
                                 f"The file '{patch_path}' does not exist.")
            return

        print(f"[commit] Applying patch: '{patch_path}', commit={commit_wanted}")
        progress = ProgressDialog("Apply Patch", "Applying patch...", self)
        progress.show()
        QApplication.processEvents()
        try:
            ok, detail = apply_patch_file(self.repo_path, patch_path, commit_wanted)
        finally:
            progress.close()

        if not ok:
            print(f"[commit] Patch apply FAILED: {detail}")
            QMessageBox.critical(
                self, "Apply Patch Failed",
                f"Patch could not be applied.\n\n{detail}\n\n"
                f"The repository was left unchanged."
            )
            return

        print("[commit] Patch applied successfully")
        self.load_history()
        QMessageBox.information(
            self, "Patch Applied",
            f"Patch applied successfully.\n\n{detail}\n\n"
            f"Click 'Rescan Repo' to handle the new changes."
        )
        self.handle_rescan_repo()

    def handle_rephrase(self, item):
        """Handles the rephrase action."""
        sha = item.text().split()[0]
        print(f"Preparing to rephrase {sha}...")
        try:
            current_message = get_full_commit_message(self.repo_path, sha)
            dialog = RephraseDialog(sha, current_message, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                new_message = dialog.get_message()
                if new_message != current_message:
                    self.perform_rephrase(sha, new_message)
            else:
                print(f"Cancelled rephrase {sha}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch commit message: {str(e)}")

    def perform_rephrase(self, sha, new_message):
        """Executes the rephrase using unified rebase logic."""
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return
        old_head = self.get_head_sha()
        try:
            # Current list of SHAs in UI
            current_shas = []
            for i in range(self.list_widget.count()):
                current_shas.append(self.list_widget.item(i).text().split()[0])

            if self.run_interactive_rebase(current_shas, rephrase_map={sha: new_message}, progress_title="Rephrasing Commit", progress_text=f"Rephrasing commit {sha}. Please wait..."):
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha, "rephrased", old_head, new_head)
                QMessageBox.information(self, "Success", f"Commit {sha} rephrased successfully.")
                return

            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while rephrasing: {str(e)}")
            self.load_history()

    def handle_revert_commit(self, item):
        """Handles the 'Revert this commit' context menu action."""
        sha = item.text().split()[0]
        print(f"[commit] Preparing to revert {sha[:10]}...")
        try:
            default_message = get_revert_commit_message(self.repo_path, sha)
            dialog = RevertCommitDialog(sha, default_message, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                revert_message = dialog.get_message()
                self.perform_revert_commit(sha, revert_message)
            else:
                print(f"[commit] Cancelled revert {sha[:10]}.")
        except Exception as e:
            print(f"[commit] Revert prepare FAILED: {e}")
            QMessageBox.critical(self, "Error", f"Could not prepare revert: {str(e)}")

    def perform_revert_commit(self, sha, revert_message):
        """Executes git revert --no-commit then commits with the edited message."""
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return
        self.save_undo_state()
        old_head = self.get_head_sha()
        progress = ProgressDialog("Reverting Commit", f"Reverting {sha}...", self)
        progress.show()
        QApplication.processEvents()
        try:
            # Revert without auto-committing so we can supply our own message
            subprocess.run(
                ["git", "revert", "--no-commit", sha],
                cwd=self.repo_path, check=True, capture_output=True, text=True
            )
            # Commit with the (possibly edited) revert message
            progress.label.setText("Committing revert...")
            QApplication.processEvents()
            subprocess.run(
                ["git", "commit", "-m", revert_message],
                cwd=self.repo_path, check=True, capture_output=True, text=True
            )
            progress.close()
            self.load_history()
            new_head = self.get_head_sha()
            self.log_action(sha, "reverted", old_head, new_head)
            QMessageBox.information(self, "Success", f"Commit {sha} reverted successfully.")
        except subprocess.CalledProcessError as e:
            progress.close()
            # Abort any lingering revert state so the repo stays clean
            subprocess.run(["git", "revert", "--abort"], cwd=self.repo_path, capture_output=True)
            QMessageBox.critical(self, "Revert Failed",
                                 f"Could not revert commit {sha}.\n\nError: {e.stderr}")
            self.load_history()

    def handle_copy_sha(self, item):
        sha = item.text().split()[0]
        print(f"Copying SHA {sha} to clipboard...")
        QApplication.clipboard().setText(sha)
        QMessageBox.information(self, "Copied", f"Copied {sha} to clipboard.")

    def handle_copy_message(self, item):
        sha = item.text().split()[0]
        print(f"Copying message of {sha} to clipboard...")
        try:
            msg = get_full_commit_message(self.repo_path, sha)
            QApplication.clipboard().setText(msg)
            QMessageBox.information(self, "Copied", f"Copied commit message of {sha} to clipboard.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch message: {str(e)}")

    def handle_copy_sha_and_message(self, item):
        sha = item.text().split()[0]
        print(f"Copying SHA and message of {sha} to clipboard...")
        try:
            msg = get_full_commit_message(self.repo_path, sha)
            combined = f"{sha} {msg}"
            QApplication.clipboard().setText(combined)
            QMessageBox.information(self, "Copied", f"Copied SHA and commit message of {sha} to clipboard.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch message: {str(e)}")

    def _open_viewer(self, dialog):
        """Shows a read-only viewer dialog non-modally so the main window stays usable while it is open."""
        # Turn the Dialog into a normal Window so the window manager doesn't
        # keep it permanently above the main window (transient-dialog behavior).
        flags = (dialog.windowFlags() & ~Qt.Dialog) | Qt.Window
        dialog.setWindowFlags(flags)
        self.viewer_windows.append(dialog)
        dialog.finished.connect(lambda: self._discard_viewer(dialog))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _discard_viewer(self, dialog):
        try:
            self.viewer_windows.remove(dialog)
        except ValueError:
            pass

    def view_commit(self, item):
        """Helper to open the tabbed diff viewer for a commit item.
        The commit is from the current list/branch, so edit operations are allowed."""
        if not item:
            return
        sha = item.text().split()[0]
        print(f"[commit] Viewing commit: {sha[:10]}")
        try:
            dialog = SingleCommitViewDialog(self.repo_path, sha, self.current_font_size, self, editable=True)
            self._open_viewer(dialog)
        except Exception as e:
            print(f"[commit] View commit FAILED: {e}")
            QMessageBox.critical(self, "Error", f"Could not fetch commit diff: {str(e)}")

    def handle_create_patch(self, item):
        """Saves the selected commit as a format-patch file chosen by the user.
        The patch carries the commit's own message, so it can be re-applied via
        Repo → Apply Patch… (including as a commit)."""
        if not item:
            return
        sha = item.text().split()[0]
        print(f"[commit] Creating patch for {sha[:10]}")
        subject = get_commit_subject(self.repo_path, sha) or ""
        slug = re.sub(r'[^A-Za-z0-9._-]+', '-', subject).strip('-').lower()[:40]
        default_name = f"{sha[:8]}-{slug}.patch" if slug else f"{sha[:8]}.patch"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Create Patch", default_name,
            "Patch files (*.patch);;All files (*)")
        if not save_path:
            print("[commit] Patch creation cancelled")
            return

        try:
            result = subprocess.run(
                ["git", "format-patch", "-1", sha, "--stdout"],
                cwd=self.repo_path, capture_output=True, check=True,
                text=True, encoding='utf-8', errors='replace')
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(
                self, "Create Patch Failed",
                f"Could not create a patch for commit {sha[:8]}.\n\n"
                f"{e.stderr or str(e)}")
            return
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not create patch: {str(e)}")
            return

        try:
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(result.stdout)
        except OSError as e:
            QMessageBox.critical(self, "Create Patch Failed",
                                 f"Could not write patch file:\n{e}")
            return

        QMessageBox.information(
            self, "Patch Created",
            f"Patch saved to:\n{save_path}\n\n"
            f"It can be re-applied via Repo → Apply Patch….")

    def handle_tag_commit(self, item):
        """Opens a dialog to create a git tag (lightweight or annotated) on the selected commit."""
        if not item:
            return
        sha = item.text().split()[0]
        print(f"[commit] Tagging commit: {sha[:10]}")
        dlg = TagCommitDialog(sha, self)
        if dlg.exec() != QDialog.Accepted:
            print("[commit] Tag creation cancelled")
            return
        tag_name = dlg.tag_name
        if not tag_name:
            QMessageBox.warning(self, "Tag", "Tag name cannot be empty.")
            return
        cmd = ["git", "tag"]
        if dlg.annotated:
            msg = dlg.message
            if not msg:
                QMessageBox.warning(self, "Tag", "Annotation message cannot be empty.")
                return
            cmd += ["-a", tag_name, "-m", msg]
        else:
            cmd.append(tag_name)
        cmd.append(sha)
        try:
            subprocess.run(cmd, cwd=self.repo_path, capture_output=True, check=True,
                           text=True, encoding='utf-8', errors='replace')
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Tag Failed",
                                 f"Could not create tag '{tag_name}' on {sha[:8]}.\n\n"
                                 f"{e.stderr or str(e)}")
            return
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not create tag: {str(e)}")
            return
        QMessageBox.information(self, "Tag Created",
                                f"Tag '{tag_name}' created on commit {sha[:8]}.")
        self.load_history()

    def handle_view_commit_by_sha(self):
        """Opens the file-wise view of any commit entered by the user.
        Validates the SHA/ref exists in the repository before opening."""
        text, ok = QInputDialog.getText(self, "View a Commit", "Enter the commit SHA:")
        if not ok:
            return
        ref = text.strip()
        if not ref:
            QMessageBox.warning(self, "No SHA", "Please enter a commit SHA to view.")
            return
        sha = resolve_ref(self.repo_path, ref)
        if not sha:
            QMessageBox.critical(self, "Commit not found", f"'{ref}' is not a valid SHA or ref in this repository.")
            return
        print(f"[commit] Viewing commit by SHA: {ref} → {sha[:10]}")
        try:
            files = get_commit_files_with_status(self.repo_path, sha)
            if not files:
                QMessageBox.information(self, "No Files", f"Commit {sha[:10]} has no file changes to view.")
                return
            dialog = SingleCommitViewDialog(self.repo_path, sha, self.current_font_size, self)
            self._open_viewer(dialog)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open file-wise view: {str(e)}")

    def toggle_mark_commit(self, item):
        sha = item.text().split()[0]

        if sha in self.marked_shas:
            self.marked_shas.remove(sha)
        else:
            self.marked_shas.add(sha)

        # Repaint to immediately apply the delegate's background fill
        self.list_widget.viewport().update()

    def _show_help_dialog(self):
        """Opens the Help dialog."""
        dialog = HelpDialog(self)
        dialog.exec()
