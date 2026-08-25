import os
import re
import subprocess
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QDialog
from lib.git_helpers import (
    get_full_commit_message, get_commit_files, get_commit_diff,
    get_commit_subject, resolve_ref, rebase_in_progress,
)
from lib.dialogs import (
    SquashDialog, MultiSquashDialog, DropDialog, SplitCommitDialog,
    ProgressDialog,
)
from lib.app_window.workers import SplitWorker


class SquashMixin:
    """Squash, multi-select, and drop operations."""

    def handle_squash_above(self, item):
        """Squashes the current commit with the one above it (newer)."""
        index = self.list_widget.row(item)
        if index <= 0: return

        above_item = self.list_widget.item(index - 1)
        sha_above = above_item.text().split()[0]
        sha_current = item.text().split()[0]

        try:
            msg_above = get_full_commit_message(self.repo_path, sha_above)
            msg_current = get_full_commit_message(self.repo_path, sha_current)

            dialog = SquashDialog(sha_above, msg_above, sha_current, msg_current, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                final_msg = dialog.get_message()
                print(f"Preparing to squash {sha_above} into {sha_current}...")
                self.perform_squash(sha_above, final_msg)
            else:
                print(f"Cancelled squash {sha_above} into {sha_current}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not prepare squash: {str(e)}")

    def handle_squash_below(self, item):
        """Squashes the current commit with the one below it (older)."""
        index = self.list_widget.row(item)
        if index >= self.list_widget.count() - 1: return

        sha_current = item.text().split()[0]
        below_item = self.list_widget.item(index + 1)
        sha_below = below_item.text().split()[0]

        try:
            msg_current = get_full_commit_message(self.repo_path, sha_current)
            msg_below = get_full_commit_message(self.repo_path, sha_below)

            dialog = SquashDialog(sha_current, msg_current, sha_below, msg_below, self.current_font_size, self, default_radio=2)
            if dialog.exec() == QDialog.Accepted:
                final_msg = dialog.get_message()
                print(f"Preparing to squash {sha_current} into {sha_below}...")
                self.perform_squash(sha_current, final_msg)
            else:
                print(f"Cancelled squash {sha_current} into {sha_below}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not prepare squash: {str(e)}")

    def perform_squash(self, sha_to_squash, final_msg):
        """Executes the squash using unified rebase logic."""
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

            # Use final_msg for the rebase - we associate it with the SHA being squashed
            # so the amend happens right after the squash command in the todo list.
            if self.run_interactive_rebase(current_shas, squash_shas=[sha_to_squash],
                                          rephrase_map={sha_to_squash: final_msg}):
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha_to_squash, "squashed", old_head, new_head)
                QMessageBox.information(self, "Success", "Commits squashed successfully.")
                return

            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while squashing: {str(e)}")
            self.load_history()

    # ---- Multi-select / Squash mode ----

    def enter_multi_select_mode(self):
        """Enters checkbox multi-select mode on the commit list."""
        print("[dbg] enter_multi_select_mode() called")
        self.multi_select_mode = True
        print(f"[dbg] multi_select_mode set to {self.multi_select_mode}")
        self._apply_multi_select_flags()
        self.list_widget.itemChanged.connect(self.on_multi_select_changed)
        self.multi_select_btn.setEnabled(False)
        self.perform_action_btn.setEnabled(False)
        self.cancel_multi_btn.setEnabled(True)
        # Install event filter directly on the list widget to catch ESC
        self.list_widget.installEventFilter(self)
        # Give the commit list keyboard focus so Space toggles the current
        # item's checkbox instead of falling onto a toolbar button (e.g. zoom).
        self.list_widget.setFocus()
        print("[dbg] enter_multi_select_mode() complete")

    def _apply_multi_select_flags(self):
        """Adds checkable flags to the current list items and clears their checks.

        Used when entering multi-select mode and whenever the list is repopulated
        while multi-select mode is still active."""
        self.list_widget.blockSignals(True)
        saved_flags = {}
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            saved_flags[i] = item.flags()
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
        self._saved_item_flags = saved_flags
        self.list_widget.blockSignals(False)

    def exit_multi_select_mode(self):
        """Exits checkbox multi-select mode and restores normal list behaviour."""
        print("[dbg] exit_multi_select_mode() called")
        print(f"[dbg] multi_select_mode was: {getattr(self, 'multi_select_mode', 'NOT SET')}")
        self.multi_select_mode = False
        try:
            self.list_widget.itemChanged.disconnect(self.on_multi_select_changed)
        except Exception: # Widened exception catch
            pass
        saved_flags = getattr(self, '_saved_item_flags', {})
        self.list_widget.blockSignals(True)
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setFlags(saved_flags.get(i, item.flags() & ~Qt.ItemIsUserCheckable))
            item.setData(Qt.CheckStateRole, None)
        self.list_widget.blockSignals(False)
        self.multi_select_btn.setEnabled(True)
        self.perform_action_btn.setEnabled(False)
        self.cancel_multi_btn.setEnabled(False)
        print("[dbg] exit_multi_select_mode() complete")

    def on_multi_select_changed(self, changed_item):
        """Enables the 'Perform action' menu only when commits are checked."""
        if not self.multi_select_mode:
            return
        checked_count = sum(
            1 for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == Qt.Checked
        )
        self.perform_action_btn.setEnabled(checked_count >= 1)
        self.squash_selected_action.setEnabled(checked_count >= 2)
        self.mark_selected_action.setEnabled(checked_count >= 1)
        self.drop_selected_action.setEnabled(checked_count >= 1)
        self.move_selected_action.setEnabled(checked_count >= 1)

    def handle_cancel_multi_select(self):
        """Cancels multi-select mode without merging."""
        self.exit_multi_select_mode()

    def enter_browse_multi_select(self):
        """Enters checkbox multi-select mode in the browse window."""
        self.enter_multi_select_mode()
        self.browse_select_btn.setEnabled(False)
        self.browse_cancel_select_btn.setEnabled(True)
        # Give the commit list keyboard focus so Space toggles the current
        # item's checkbox instead of falling onto the newly-enabled Cancel
        # button (which would immediately exit selection mode).
        self.list_widget.setFocus()

    def exit_browse_multi_select(self):
        """Exits checkbox multi-select mode in the browse window."""
        self.exit_multi_select_mode()
        self.browse_select_btn.setEnabled(True)
        self.browse_cancel_select_btn.setEnabled(False)
        # 'multi_select_mode' is now False; force the commit-graph icons to be
        # redrawn for every row.
        self.list_widget.viewport().update()

    def handle_squash_selected(self):
        """Collects checked commits, validates contiguity, confirms, then squashes."""
        # Collect selected indices and SHAs in list order (newest → oldest)
        selected_indices = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                selected_indices.append(i)

        if len(selected_indices) < 2:
            QMessageBox.warning(self, "Not Enough Selected", "Please select at least 2 commits to squash.")
            return

        # Contiguity check
        for k in range(len(selected_indices) - 1):
            if selected_indices[k + 1] != selected_indices[k] + 1:
                QMessageBox.critical(
                    self, "Non-Adjacent Commits",
                    "Selected commits must be adjacent (contiguous) in the log.\n\n"
                    "Please select only neighbouring commits."
                )
                return

        selected_shas = [self.list_widget.item(i).text().split()[0] for i in selected_indices]

        self.perform_multi_squash(selected_shas)

    def handle_create_patch_selected(self, consolidated=False):
        """Creates patch files from selected commits.

        consolidated=True: all changes combined into one unified-diff file.
        consolidated=False: one format-patch file per commit."""
        selected_indices = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                selected_indices.append(i)

        if not selected_indices:
            QMessageBox.warning(self, "No Commits Selected",
                                "Please select at least one commit.")
            return

        shas = [self.list_widget.item(i).text().split()[0] for i in selected_indices]
        # List order is newest-first; reverse to chronological (oldest first)
        shas = list(reversed(shas))

        # Resolve short SHAs to full SHAs for git operations
        try:
            shas = [resolve_ref(self.repo_path, s) or s for s in shas]
        except Exception:
            pass

        if consolidated:
            if len(shas) < 2:
                QMessageBox.warning(self, "Not Enough Selected",
                                    "Select at least 2 commits for a consolidated patch.")
                return
            default = f"{shas[0][:8]}-to-{shas[-1][:8]}.patch"
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save Consolidated Patch", default,
                "Patch files (*.patch);;All files (*)")
            if not save_path:
                return
            try:
                patches = []
                for sha in shas:
                    r = subprocess.run(
                        ["git", "format-patch", "-1", sha, "--stdout"],
                        cwd=self.repo_path, capture_output=True, check=True,
                        text=True, encoding='utf-8', errors='replace')
                    patches.append(r.stdout)
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(patches))
            except subprocess.CalledProcessError as e:
                QMessageBox.critical(self, "Patch Failed",
                                     f"Could not create consolidated patch.\n\n{e.stderr}")
                return
            except OSError as e:
                QMessageBox.critical(self, "Patch Failed",
                                     f"Could not write patch file:\n{e}")
                return
            QMessageBox.information(
                self, "Patch Created",
                f"Consolidated patch saved to:\n{save_path}\n\n"
                f"Contains changes from {shas[0][:8]} to {shas[-1][:8]} "
                f"({len(shas)} commits).")
        else:
            folder = QFileDialog.getExistingDirectory(
                self, "Save Patches", self.repo_path)
            if not folder:
                return
            count = 0
            errors = []
            for sha in shas:
                try:
                    result = subprocess.run(
                        ["git", "format-patch", "-1", sha, "--stdout"],
                        cwd=self.repo_path, capture_output=True, check=True,
                        text=True, encoding='utf-8', errors='replace')
                    subject = get_commit_subject(self.repo_path, sha) or ""
                    slug = re.sub(r'[^A-Za-z0-9._-]+', '-', subject).strip('-').lower()[:40]
                    fname = f"{sha[:8]}-{slug}.patch" if slug else f"{sha[:8]}.patch"
                    fpath = os.path.join(folder, fname)
                    with open(fpath, 'w', encoding='utf-8') as f:
                        f.write(result.stdout)
                    count += 1
                except (subprocess.CalledProcessError, OSError) as e:
                    errors.append(f"{sha[:8]}: {e}")
            if errors:
                QMessageBox.warning(
                    self, "Patch Errors",
                    f"Patches saved: {count}\nFailed: {len(errors)}\n\n"
                    + "\n".join(errors))
            else:
                QMessageBox.information(
                    self, "Patches Created",
                    f"{count} patch(es) saved to:\n{folder}")

    def handle_mark_selected(self):
        """Marks each checked commit, then exits multi-select mode."""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                sha = item.text().split()[0]
                self.marked_shas.add(sha)
        self.exit_multi_select_mode()
        self.list_widget.viewport().update()

    def handle_drop_selected(self):
        """Drops the selected commits one by one, newest first.

        If a drop fails, a dialog offers recovery choices (copy the failed
        commit's id, skip it and continue, or stop)."""
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return

        selected_shas = [self.list_widget.item(i).text().split()[0]
                         for i in range(self.list_widget.count())
                         if self.list_widget.item(i).checkState() == Qt.Checked]
        if not selected_shas:
            QMessageBox.warning(self, "No Selection",
                                "Please select at least one commit to drop.")
            return

        def fmt(shas_list):
            lines = []
            for s in shas_list:
                try:
                    subject = get_commit_subject(self.repo_path, s)
                except Exception:
                    subject = ""
                if len(subject) > 80:
                    subject = subject[:80] + "..."
                lines.append(f"{s[:7]}: {subject}".rstrip())
            return "<br/>".join(lines) if lines else "<i>none</i>"

        dropped_shas = []
        stop = False

        progress = ProgressDialog("Dropping Commits", "", self)
        progress.show()
        QApplication.processEvents()

        for index, sha in enumerate(selected_shas):
            if stop:
                break
            progress.label.setText(f"Dropping commit {sha[:8]}... ({index + 1}/{len(selected_shas)})")
            for _ in range(3):
                QApplication.processEvents()
            if self._drop_single_commit(sha, progress_dialog=progress):
                dropped_shas.append(sha)
                continue

            # This drop failed. Offer recovery choices.
            remaining = selected_shas[index:]
            while True:
                box = self._make_resizable_message_box(self)
                box.setWindowTitle("Drop Failed")
                box.setTextFormat(Qt.RichText)
                box.setText(
                    f"<p>Dropping of <b>{sha[:10]}</b> failed. What to do?</p>"
                    f"<p>List of commits dropped:<br/>"
                    f"<span style='font-family:monospace'>{fmt(dropped_shas)}</span></p>"
                    f"<p>List of commits to be dropped:<br/>"
                    f"<span style='font-family:monospace'>{fmt(remaining)}</span></p>"
                )
                copy_btn = box.addButton("Copy current commit id to clipboard", QMessageBox.ActionRole)
                if index < len(selected_shas) - 1:
                    skip_btn = box.addButton("Skip this, and continue with next", QMessageBox.AcceptRole)
                stop_btn = box.addButton("Stop here", QMessageBox.RejectRole)
                box.exec()
                clicked = box.clickedButton()
                if clicked is copy_btn:
                    QApplication.clipboard().setText(sha)
                    continue  # re-show the dialog so the user can then skip/stop
                elif clicked is skip_btn:
                    break
                else:
                    stop = True
                    break

        progress.close()

        self.exit_multi_select_mode()

        if len(dropped_shas) == len(selected_shas):
            QMessageBox.information(self, "Success",
                                    f"Successfully dropped {len(dropped_shas)} commit(s).")
        elif dropped_shas:
            not_dropped = [s for s in selected_shas if s not in dropped_shas]
            box = self._make_resizable_message_box(self)
            box.setWindowTitle("Drop Result")
            box.setTextFormat(Qt.RichText)
            box.setText(
                f"<p>Drop partially succeeded.</p>"
                f"<p>Dropped:<br/>"
                f"<span style='font-family:monospace'>{fmt(dropped_shas)}</span></p>"
                f"<p>Not dropped:<br/>"
                f"<span style='font-family:monospace'>{fmt(not_dropped)}</span></p>"
            )
            box.addButton("OK", QMessageBox.AcceptRole)
            box.exec()
        else:
            QMessageBox.information(self, "Drop Result",
                                    "No commits were dropped.")

    def _drop_single_commit(self, sha, progress_dialog=None):
        """Drops a single commit using the unified rebase logic.
        Returns True on success, False on failure. Suppresses the default
        failure box so the caller can present recovery choices."""
        if not self._check_not_viewer_mode():
            return False
        if not self._check_head_unchanged():
            return False
        if not self._check_no_unstaged_changes():
            return False
        try:
            current_shas = [self.list_widget.item(i).text().split()[0]
                            for i in range(self.list_widget.count())]
            new_shas = [s for s in current_shas if s != sha]
            if self.run_interactive_rebase(
                    new_shas,
                    progress_title="Dropping Commit",
                    progress_text=f"Dropping commit {sha}. Please wait...",
                    suppress_failure_box=True,
                    progress_dialog=progress_dialog):
                self.load_history()
                self._sync_cached_head()
                return True
            self.load_history()
            return False
        except Exception as e:
            self.load_history()
            return False

    def perform_multi_squash(self, selected_shas):
        """Squashes multiple adjacent commits into the topmost selected commit."""
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return
        try:
            # Collect (sha, message) pairs preserving order
            sha_msg_pairs = [(sha, get_full_commit_message(self.repo_path, sha)) for sha in selected_shas]

            # The oldest item (last in our list) is the "pick" target; rest become squash
            # List is newest -> oldest
            base_sha = selected_shas[-1]
            squash_shas = selected_shas[:-1]
            # Use the newest commit in the group to apply the final message via --amend
            rephrase_sha = selected_shas[0]

            # Open the N-option message selection dialog directly
            dialog = MultiSquashDialog(sha_msg_pairs, self.current_font_size, self)
            if dialog.exec() != QDialog.Accepted:
                return  # finally block handles cleanup

            final_msg = dialog.get_message()

            # Build all SHAs list from current view
            all_shas = [self.list_widget.item(i).text().split()[0] for i in range(self.list_widget.count())]

            if self.run_interactive_rebase(all_shas, squash_shas=squash_shas, rephrase_map={rephrase_sha: final_msg}, progress_title="Squashing Commits", progress_text="Squashing selected commits together. Please wait..."):
                self.load_history()
                QMessageBox.information(self, "Success", f"Successfully squashed {len(selected_shas)} commits.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while merging: {str(e)}")
        finally:
            self.exit_multi_select_mode()
            self.load_history()

    def handle_drop(self, item):
        sha = item.text().split()[0]
        print(f"Preparing to drop {sha}...")

        # Guard: if this is the only commit in the list and we're in branch-detection
        # mode, dropping it is equivalent to a hard-reset to the base — not supported.
        if self.list_widget.count() == 1 and self.base_branch:
            base_sha_short = self.commit_sha[:8] if self.commit_sha else "<base>"
            QMessageBox.information(
                self,
                "Drop",
                f"This is the only unique commit in your branch.\n"
                f"If you do this, it's as good as resetting hard to "
                f"branch: {self.base_branch} or {base_sha_short}\n\n"
                "App doesn't support doing this when run in unique-changes branch mode.\n"
                "To drop this commit, run the app with an explicit number of commits as argument."
            )
            return

        try:
            diff_text = get_commit_diff(self.repo_path, sha)
            dialog = DropDialog(sha, diff_text, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                self.perform_drop(sha)
            else:
                print(f"Cancelled drop {sha}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def perform_drop(self, sha):
        """Drops a commit using our unified rebase logic."""
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

            # New list without the dropped SHA
            new_shas = [s for s in current_shas if s != sha]

            if self.run_interactive_rebase(new_shas, progress_title="Dropping Commit", progress_text=f"Dropping commit {sha}. Please wait..."):
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha, "dropped", old_head, new_head)
                QMessageBox.information(self, "Success", f"Commit {sha} dropped successfully.")
                return

            self.load_history()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while dropping: {str(e)}")
            self.load_history()
