import subprocess
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QDialog
from lib.git_helpers import get_current_branch, branch_exists, get_full_head_sha, rebase_in_progress
from lib.dialogs import ProgressDialog
from lib.app_window.workers import GitWorker


class ResetMixin:
    def handle_git_fetch(self):
        """Runs git fetch."""
        print("Running git fetch...")
        self.progress_dialog = ProgressDialog("Git Fetching", "git fetch in progress...", self)

        self.worker = GitWorker(["git", "fetch"], self.repo_path)
        self.worker.finished.connect(self.on_fetch_finished)
        self.worker.start()

        self.progress_dialog.exec()

    def on_fetch_finished(self, success, stdout, stderr):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()

        if success:
            QMessageBox.information(self, "Success", "Successfully ran 'git fetch'.")
            self.load_history()
        else:
            QMessageBox.critical(self, "Fetch Failed", f"Could not perform git fetch.\n\nError: {stderr}")


    def handle_git_reset_hard_origin(self):
        """Runs git reset --hard origin/<current_branch>."""
        if not self._check_not_viewer_mode():
            return
        branch = get_current_branch(self.repo_path)
        origin_ref = f"origin/{branch}"

        # Check if HEAD is already at origin_ref
        try:
            head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo_path).decode('utf-8').strip()
            origin_sha = subprocess.check_output(["git", "rev-parse", origin_ref], cwd=self.repo_path).decode('utf-8').strip()
            if head_sha == origin_sha:
                QMessageBox.information(self, "Nothing to do", f"Current HEAD is same as {origin_ref} HEAD. Nothing to do.")
                return
        except Exception:
            pass # Probably origin_ref doesn't exist, proceed to confirmation which will fail naturally if so

        reply = QMessageBox.question(
            self,
            "Confirm Reset to Origin",
            f"Are you sure you want to <b>reset --hard {origin_ref}</b>?<br><br>"
            f"This will discard all uncommitted changes and move your branch to '{origin_ref}'.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.save_undo_state()
            print(f"Resetting hard to {origin_ref}...")

            self.progress_dialog = ProgressDialog("Resetting", f"Resetting hard to {origin_ref}...", self)
            self.worker = GitWorker(["git", "reset", "--hard", origin_ref], self.repo_path)

            def on_origin_reset_finished(success, stdout, stderr):
                if hasattr(self, 'progress_dialog'):
                    self.progress_dialog.close()

                if success:
                    QMessageBox.information(self, "Success", f"Successfully reset --hard to {origin_ref}.")
                else:
                    QMessageBox.critical(self, "Reset Failed", f"Could not perform reset to {origin_ref}.\n\nError: {stderr}")

                self.load_history()

            self.worker.finished.connect(on_origin_reset_finished)
            self.worker.start()
            self.progress_dialog.exec()
        else:
            print(f"Cancelled reset hard to {origin_ref}.")

    def handle_git_push_force(self):
        """Runs git push --force."""
        if not self._check_not_viewer_mode():
            return
        reply = QMessageBox.question(
            self,
            "Confirm Force Push",
            "Are you sure you want to <b>push --force</b>?<br><br>"
            "This can overwrite history on the remote repository. Proceed with caution.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            print("Performing git push --force...")
            self.progress_dialog = ProgressDialog("Git Pushing", "git push --force in progress...", self)

            self.worker = GitWorker(["git", "push", "--force"], self.repo_path)
            self.worker.finished.connect(self.on_push_finished)
            self.worker.start()

            self.progress_dialog.exec()
        else:
            print("Cancelled force push.")

    def on_push_finished(self, success, stdout, stderr):
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()

        if success:
            QMessageBox.information(self, "Success", "Successfully ran 'git push --force'.")
        else:
            QMessageBox.critical(self, "Push Failed", f"Could not perform git push --force.\n\nError: {stderr}")


    def update_rebase_buttons(self):
        """Updates the enabled state of rebase buttons based on branch existence."""
        has_master = branch_exists(self.repo_path, "master")
        has_main = branch_exists(self.repo_path, "main")

        self.rebase_master_btn.setEnabled(has_master)
        self.rebase_master_btn.setText("git rebase master" if has_master else "git rebase master (NA)")

        self.rebase_main_btn.setEnabled(has_main)
        self.rebase_main_btn.setText("git rebase main" if has_main else "git rebase main (NA)")

    def handle_git_rebase_master(self):
        self.perform_rebase("master")

    def handle_git_rebase_main(self):
        self.perform_rebase("main")

    def handle_git_rebase_custom(self):
        target, ok = QInputDialog.getText(self, 'Rebase', 'Enter branch or commit SHA to rebase on top of:')
        if ok and target.strip():
            self.perform_rebase(target.strip())

    def perform_rebase(self, target):
        """Performs git rebase <target> with confirmation."""
        reply = QMessageBox.question(
            self,
            "Confirm Rebase",
            f"Are you sure you want to <b>rebase</b> current branch on top of <b>{target}</b>?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if not self._check_head_unchanged():
                return
            if not self._check_no_unstaged_changes():
                return
            self.save_undo_state()
            old_head = self.get_head_sha()
            print(f"Rebasing onto {target}...")
            try:
                subprocess.run(["git", "rebase", target], cwd=self.repo_path, check=True, capture_output=True, text=True)
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(target, f"rebased onto {target}", old_head, new_head)
                QMessageBox.information(self, "Success", f"Successfully rebased onto {target}.")
            except subprocess.CalledProcessError as e:
                # A failed rebase may have stopped mid-way (e.g. conflicts).
                # Abort it and verify the repository is clean again, mirroring
                # the recovery behavior of the interactive-rebase operations.
                ok, detail = self._abort_rebase_safely()
                if not ok:
                    self._warn_rebase_abort_failure(detail)
                self._sync_cached_head()
                self.load_history()
                QMessageBox.critical(
                    self, "Rebase Failed",
                    f"Could not perform rebase onto {target}.\n\n"
                    f"Error: {e.stderr}\n\n"
                    f"The rebase was aborted and the repository restored."
                )

    def handle_reset(self, item):
        sha = item.text().split()[0]
        reply = QMessageBox.question(
            self,
            "Confirm Reset Hard",
            f"Are you sure you want to <b>reset --hard</b> to commit <b>{sha}</b>?<br><br>"
            "This will discard all uncommitted changes and move your branch to this state.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.perform_reset(sha)
        else:
            print(f"Cancelled reset to {sha}.")

    def perform_reset(self, sha):
        if not self._check_not_viewer_mode():
            return
        old_head = self.get_head_sha()
        print(f"Resetting hard to {sha}...")
        self.save_undo_state()

        self.progress_dialog = ProgressDialog("Resetting", f"Resetting hard to {sha[:10]}...", self)

        self.worker = GitWorker(["git", "reset", "--hard", sha], self.repo_path)

        def on_reset_finished(success, stdout, stderr):
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.close()

            if success:
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha, "reset hard to", old_head, new_head)
                QMessageBox.information(self, "Success", f"Successfully reset --hard to {sha[:10]}.")
            else:
                QMessageBox.critical(self, "Reset Failed", f"Could not perform reset.\n\nError: {stderr}")

        self.worker.finished.connect(on_reset_finished)
        self.worker.start()
        self.progress_dialog.exec()

    def handle_reset_to_here(self, item):
        """Resets HEAD (git reset --mixed) to a selected commit, keeping the
        changes of the removed commits as unstaged working-tree changes."""
        index = self.list_widget.row(item)
        sha = item.text().split()[0]

        # Standard safety validations used by all history-modifying operations.
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return

        # Edge case: the selected commit is already HEAD, nothing to remove.
        if index == 0:
            QMessageBox.information(
                self,
                "Already at HEAD",
                f"The selected commit ({sha[:8]}) is already HEAD.\n\n"
                "Nothing to reset.\n\n"
                "Tip: To unstage the HEAD commit's changes, right-click the "
                "commit below it (its parent, if any) and choose "
                "'Reset HEAD to Here'."
            )
            return

        next_item = self.list_widget.item(index - 1)
        next_short = next_item.text().split()[0][:8] if next_item else sha[:8]
        head_short = self.get_head_sha()[:8]

        # When the selected commit is HEAD^ (the parent of HEAD), only the
        # HEAD commit itself is removed, so name it directly.
        removed_part = (
            f"HEAD commit ({head_short})"
            if index == 1 else
            f"All commits after the selected commit ({next_short} .. {head_short})"
        )

        box = QMessageBox(self)
        box.setWindowTitle("Reset HEAD to Here")
        box.setText(
            f"This will move HEAD to the selected commit.\n\n"
            f"{removed_part} will be removed from the current branch, but the "
            f"changes will be preserved as unstaged changes in the working tree.\n\n"
            f"Do you want to continue?"
        )
        reset_btn = box.addButton("Yes, Reset", QMessageBox.AcceptRole)
        cancel_btn = box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.exec()

        if box.clickedButton() != reset_btn:
            print(f"Cancelled reset HEAD to here ({sha}).")
            return

        old_head = self.get_head_sha()
        self.save_undo_state()
        print(f"Resetting HEAD (mixed) to {sha}...")

        self.progress_dialog = ProgressDialog("Resetting", f"Resetting HEAD to {sha[:10]}...", self)
        self.worker = GitWorker(["git", "reset", "--mixed", sha], self.repo_path)

        def on_reset_here_finished(success, stdout, stderr):
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.close()

            if success:
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha, "reset HEAD to here (mixed)", old_head, new_head)
                QMessageBox.information(
                    self, "Success",
                    f"Successfully reset HEAD to {sha[:10]}. Changes kept as unstaged."
                )
            else:
                QMessageBox.critical(
                    self, "Reset Failed",
                    f"Could not perform reset.\n\nError: {stderr}"
                )

        self.worker.finished.connect(on_reset_here_finished)
        self.worker.start()
        self.progress_dialog.exec()

    def handle_custom_reset(self):
        commit_id, ok = QInputDialog.getText(self, 'Input Dialog', 'Enter commit ID to reset hard to:')
        if ok and commit_id.strip():
            sha = commit_id.strip()
            reply = QMessageBox.question(
                self,
                "Confirm Custom Reset",
                f"Are you sure you want to <b>reset --hard</b> to <b>{sha}</b>?<br><br>"
                "This will discard all uncommitted changes and move your branch to this state.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.perform_reset(sha)
            else:
                print(f"Cancelled custom reset to {sha}.")
