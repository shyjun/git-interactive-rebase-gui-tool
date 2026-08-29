import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog, QDialog
from lib.git_helpers import (
    get_current_branch, branch_exists, commit_exists,
    normalize_branch_ref, get_merge_base, get_commit_subject,
    stash_apply, stash_drop, get_stash_history, get_tags_history,
)
from lib.dialogs import (
    BrowseBranchDialog, BrowseCommitLogDialog, BrowseFileLogDialog,
    MergeBaseDialog, MergeBaseResultDialog, StashNoticeDialog,
    OpenFileAtRefDialog,
)

# Lazy import to avoid circular dependency - GitInteractiveRebaseApp
# is defined in the module that uses this mixin.
_GitInteractiveRebaseApp = None


def _get_app_class():
    global _GitInteractiveRebaseApp
    if _GitInteractiveRebaseApp is None:
        from lib.app_window import GitInteractiveRebaseApp
        _GitInteractiveRebaseApp = GitInteractiveRebaseApp
    return _GitInteractiveRebaseApp


class BrowseMixin:
    def handle_browse_branch(self):
        """Opens a read-only viewer window showing another branch's recent history.
        Prompts for the branch name and the number of commits to load."""
        dialog = BrowseBranchDialog(self.repo_path, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        branch_name = dialog.branch_name
        commit_limit = dialog.commit_limit
        if not branch_name:
            QMessageBox.warning(self, "No branch name",
                                "Please enter a branch name to browse.")
            return
        if not branch_exists(self.repo_path, branch_name):
            QMessageBox.critical(self, "Branch does not exist",
                                 f"The branch '{branch_name}' does not exist.")
            return

        # Normalise so remote-only branches (e.g. 'feature' living only at
        # 'origin/feature') are loaded explicitly instead of by DWIM guess.
        browse_ref = normalize_branch_ref(self.repo_path, branch_name)
        print(f"[browse] Opening branch: '{branch_name}' → ref='{browse_ref}', limit={commit_limit}")

        AppClass = _get_app_class()
        viewer = AppClass(
            self.repo_path, self.commit_sha, self.app_start_time,
            viewer_mode=True, browse_branch=browse_ref, parent=self,
            browse_limit=commit_limit,
        )
        # The browse viewer inherits the main window's current zoom and theme.
        viewer.current_font_size = self.current_font_size
        viewer.update_font()
        if viewer.is_dark_theme != self.is_dark_theme:
            viewer.is_dark_theme = self.is_dark_theme
            viewer.apply_theme("dark" if self.is_dark_theme else "light")
        self.browse_windows.append(viewer)
        viewer.show()
        print(f"[browse] Branch viewer shown ({len(self.browse_windows)} browse windows open)")

    def handle_browse_commit_log(self):
        """Opens a read-only viewer window showing a commit's recent history.
        Prompts for a commit SHA (or ref) and the number of commits to load,
        validating that the commit exists."""
        dialog = BrowseCommitLogDialog(self.repo_path, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        commit_id = dialog.commit_id
        commit_limit = dialog.commit_limit
        if not commit_id:
            QMessageBox.warning(self, "No commit",
                                "Please enter a commit SHA or ref to browse.")
            return
        if not commit_exists(self.repo_path, commit_id):
            QMessageBox.critical(self, "Commit does not exist",
                                 f"'{commit_id}' does not resolve to a commit.")

        print(f"[browse] Opening commit log: '{commit_id}', limit={commit_limit}")
        AppClass = _get_app_class()
        viewer = AppClass(
            self.repo_path, self.commit_sha, self.app_start_time,
            viewer_mode=True, browse_branch=commit_id, parent=self,
            browse_limit=commit_limit,
        )
        # The browse viewer inherits the main window's current zoom and theme.
        viewer.current_font_size = self.current_font_size
        viewer.update_font()
        if viewer.is_dark_theme != self.is_dark_theme:
            viewer.is_dark_theme = self.is_dark_theme
            viewer.apply_theme("dark" if self.is_dark_theme else "light")
        self.browse_windows.append(viewer)
        viewer.show()
        print(f"[browse] Commit log viewer shown ({len(self.browse_windows)} browse windows open)")

    def handle_browse_reflog(self):
        """Opens a read-only viewer window showing the repository's HEAD reflog
        (most recent entries first), with the diff pane hidden and a minimal
        copy-SHA / show-log toolbar."""
        print("[browse] Opening reflog viewer, limit=50")
        AppClass = _get_app_class()
        viewer = AppClass(
            self.repo_path, self.commit_sha, self.app_start_time,
            viewer_mode=True, browse_reflog=True, parent=self,
            browse_limit=50,
        )
        # The browse viewer inherits the main window's current zoom and theme.
        viewer.current_font_size = self.current_font_size
        viewer.update_font()
        if viewer.is_dark_theme != self.is_dark_theme:
            viewer.is_dark_theme = self.is_dark_theme
            viewer.apply_theme("dark" if self.is_dark_theme else "light")
        self.browse_windows.append(viewer)
        viewer.show()
        print(f"[browse] Reflog viewer shown ({len(self.browse_windows)} browse windows open)")

    def handle_browse_tags(self):
        """Opens a read-only viewer window showing all tags in the repository
        (most recent first), with the diff pane hidden and a minimal
        copy-SHA / show-log toolbar."""
        print("[browse] Opening tags browser, limit=50")
        AppClass = _get_app_class()
        viewer = AppClass(
            self.repo_path, self.commit_sha, self.app_start_time,
            viewer_mode=True, browse_tags=True, parent=self,
            browse_limit=50,
        )
        viewer.current_font_size = self.current_font_size
        viewer.update_font()
        if viewer.is_dark_theme != self.is_dark_theme:
            viewer.is_dark_theme = self.is_dark_theme
            viewer.apply_theme("dark" if self.is_dark_theme else "light")
        self.browse_windows.append(viewer)
        viewer.show()
        print(f"[browse] Tags browser shown ({len(self.browse_windows)} browse windows open)")

    def handle_browse_stash(self):
        """Opens a read-only viewer window showing the repository's stash list
        (most recent first), with the diff pane always visible."""
        print("[browse] Opening stash browser, limit=50")
        AppClass = _get_app_class()
        viewer = AppClass(
            self.repo_path, self.commit_sha, self.app_start_time,
            viewer_mode=True, browse_stash=True, parent=self,
            browse_limit=50,
        )
        # The browse viewer inherits the main window's current zoom and theme.
        viewer.current_font_size = self.current_font_size
        viewer.update_font()
        if viewer.is_dark_theme != self.is_dark_theme:
            viewer.is_dark_theme = self.is_dark_theme
            viewer.apply_theme("dark" if self.is_dark_theme else "light")
        self.browse_windows.append(viewer)
        viewer.show()
        print(f"[browse] Stash browser shown ({len(self.browse_windows)} browse windows open)")

    def handle_browse_commit_log(self):
        """Opens a read-only viewer window showing a commit's recent history.
        Prompts for a commit SHA (or ref) and the number of commits to load,
        validating that the commit exists."""
        dialog = BrowseCommitLogDialog(self.repo_path, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        commit_id = dialog.commit_id
        commit_limit = dialog.commit_limit
        if not commit_id:
            QMessageBox.warning(self, "No commit",
                                "Please enter a commit SHA or ref to browse.")
            return
        if not commit_exists(self.repo_path, commit_id):
            QMessageBox.critical(self, "Commit does not exist",
                                 f"'{commit_id}' does not resolve to a commit.")
            return

        AppClass = _get_app_class()
        viewer = AppClass(
            self.repo_path, self.commit_sha, self.app_start_time,
            viewer_mode=True, browse_branch=commit_id, parent=self,
            browse_limit=commit_limit,
        )
        # The browse viewer inherits the main window's current zoom and theme.
        viewer.current_font_size = self.current_font_size
        viewer.update_font()
        if viewer.is_dark_theme != self.is_dark_theme:
            viewer.is_dark_theme = self.is_dark_theme
            viewer.apply_theme("dark" if self.is_dark_theme else "light")
        self.browse_windows.append(viewer)
        viewer.show()

    def handle_browse_reflog(self):
        """Opens a read-only viewer window showing the repository's HEAD reflog
        (most recent entries first), with the diff pane hidden and a minimal
        copy-SHA / show-log toolbar."""
        AppClass = _get_app_class()
        viewer = AppClass(
            self.repo_path, self.commit_sha, self.app_start_time,
            viewer_mode=True, browse_reflog=True, parent=self,
            browse_limit=50,
        )
        # The browse viewer inherits the main window's current zoom and theme.
        viewer.current_font_size = self.current_font_size
        viewer.update_font()
        if viewer.is_dark_theme != self.is_dark_theme:
            viewer.is_dark_theme = self.is_dark_theme
            viewer.apply_theme("dark" if self.is_dark_theme else "light")
        self.browse_windows.append(viewer)
        viewer.show()

    def handle_browse_tags(self):
        """Opens a read-only viewer window showing all tags in the repository
        (most recent first), with the diff pane hidden and a minimal
        copy-SHA / show-log toolbar."""
        try:
            tags = get_tags_history(self.repo_path, limit=1)
        except Exception:
            tags = []
        if not tags:
            QMessageBox.information(self, "No tags", "There are no tags in this repository.")
            return
        AppClass = _get_app_class()
        viewer = AppClass(
            self.repo_path, self.commit_sha, self.app_start_time,
            viewer_mode=True, browse_tags=True, parent=self,
            browse_limit=50,
        )
        viewer.current_font_size = self.current_font_size
        viewer.update_font()
        if viewer.is_dark_theme != self.is_dark_theme:
            viewer.is_dark_theme = self.is_dark_theme
            viewer.apply_theme("dark" if self.is_dark_theme else "light")
        self.browse_windows.append(viewer)
        viewer.show()

    def handle_browse_stash(self):
        """Opens a read-only viewer window showing the repository's stash list
        (most recent first), with the diff pane always visible."""
        try:
            stashes = get_stash_history(self.repo_path, limit=1)
        except Exception:
            stashes = []
        if not stashes:
            QMessageBox.information(self, "No stashes", "There are no stashes in this repository.")
            return
        AppClass = _get_app_class()
        viewer = AppClass(
            self.repo_path, self.commit_sha, self.app_start_time,
            viewer_mode=True, browse_stash=True, parent=self,
            browse_limit=50,
        )
        # The browse viewer inherits the main window's current zoom and theme.
        viewer.current_font_size = self.current_font_size
        viewer.update_font()
        if viewer.is_dark_theme != self.is_dark_theme:
            viewer.is_dark_theme = self.is_dark_theme
            viewer.apply_theme("dark" if self.is_dark_theme else "light")
        self.browse_windows.append(viewer)
        viewer.show()

    def handle_reflog_copy_sha(self):
        """Copies the selected reflog entry's SHA to the clipboard."""
        item = self.list_widget.currentItem()
        if item:
            self.handle_copy_sha(item)

    def handle_reflog_show_log(self):
        """Opens a read-only history viewer for the selected reflog entry's commit."""
        item = self.list_widget.currentItem()
        if item:
            self.handle_reflog_show_log_item(item)

    def handle_reflog_show_log_item(self, item):
        """Opens a read-only history viewer for a given reflog entry's commit SHA,
        reusing the browse-branch viewer (git log accepts a commit SHA directly).

        Prompts for how many commits to load (default 50); cancelling the prompt
        aborts the viewer."""
        if not item:
            return
        commit_limit, ok = QInputDialog.getInt(
            self, "Show log",
            "Number of commits to show:",
            value=50, minValue=1, maxValue=1000000, step=1
        )
        if not ok:
            return
        sha = item.text().split()[0]
        print(f"[browse] Reflog show-log: SHA={sha[:10]}, limit={commit_limit}")
        AppClass = _get_app_class()
        viewer = AppClass(
            self.repo_path, self.commit_sha, self.app_start_time,
            viewer_mode=True, browse_branch=sha, parent=self,
            browse_limit=commit_limit, browse_tag=self.browse_tags,
        )
        # The browse viewer inherits the main window's current zoom and theme.
        viewer.current_font_size = self.current_font_size
        viewer.update_font()
        if viewer.is_dark_theme != self.is_dark_theme:
            viewer.is_dark_theme = self.is_dark_theme
            viewer.apply_theme("dark" if self.is_dark_theme else "light")
        self.browse_windows.append(viewer)
        viewer.show()

    def _reload_stash_list(self):
        """Refreshes the stash browser's list after a stash operation so the
        shown entries match the actual stash list."""
        if self.browse_stash:
            self.load_browse_history_async()

    def _current_stash_item(self):
        """Returns the currently selected list item, or None."""
        return self.list_widget.currentItem()

    def handle_stash_copy_sha(self):
        """Copies the selected stash's SHA to the clipboard."""
        item = self._current_stash_item()
        if item:
            self.handle_copy_sha(item)

    def handle_stash_apply_keep_btn(self):
        """Applies the selected stash (keeping it), via the context-menu handler."""
        item = self._current_stash_item()
        if item:
            self.handle_stash_apply(item, drop_after=False)

    def handle_stash_apply_drop_btn(self):
        """Applies the selected stash and drops it after success."""
        item = self._current_stash_item()
        if item:
            self.handle_stash_apply(item, drop_after=True)

    def handle_stash_drop_btn(self):
        """Drops the selected stash after confirmation."""
        item = self._current_stash_item()
        if item:
            self.handle_stash_drop(item)

    def handle_stash_apply(self, item, drop_after=False):
        """Applies the selected stash. If drop_after is True and the apply
        succeeds, the stash is then dropped. On apply failure the stash is
        never dropped, and the user is told so explicitly."""
        if not item:
            return
        sha = item.text().split()[0]
        print(f"[browse] Stash apply: SHA={sha[:10]}, drop_after={drop_after}")
        confirm = QMessageBox.question(
            self, "Apply Stash",
            f"Apply stash {sha[:8]}?\n\n"
            + ("The stash WILL be dropped after a successful apply."
               if drop_after
               else "The stash will be KEPT after the apply."),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            print("[browse] Stash apply cancelled")
            return
        success, err = stash_apply(self.repo_path, sha)
        if not success:
            print(f"[browse] Stash apply FAILED: {err}")
            QMessageBox.critical(
                self, "Apply Failed",
                f"Failed to apply stash {sha[:8]}.\n\n"
                f"Details: {err}\n\n"
                "The stash has NOT been dropped.")
            self._reload_stash_list()
            return

        dropped = False
        if drop_after:
            dropped = stash_drop(self.repo_path, sha)
            print(f"[browse] Stash drop after apply: success={dropped}")

        msg = ("Apply success. Use 'Rescan Repo' to handle the unstaged changes.")
        if drop_after:
            msg += "\n\n" + ("The stash was dropped." if dropped
                             else "The stash could NOT be dropped.")
        QMessageBox.information(self, "Stash Applied", msg)
        self._reload_stash_list()

    def handle_stash_drop(self, item):
        """Drops the selected stash after user confirmation."""
        if not item:
            return
        sha = item.text().split()[0]
        print(f"[browse] Stash drop: SHA={sha[:10]}")
        confirm = QMessageBox.question(
            self, "Drop Stash",
            f"Drop stash {sha[:8]}? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            print("[browse] Stash drop cancelled")
            return
        dropped = stash_drop(self.repo_path, sha)
        if dropped:
            print("[browse] Stash dropped successfully")
            QMessageBox.information(self, "Stash Dropped",
                                    f"Stash {sha[:8]} was dropped.")
        else:
            print("[browse] Stash drop FAILED")
            QMessageBox.critical(self, "Drop Failed",
                                 f"Failed to drop stash {sha[:8]}.")
        self._reload_stash_list()

    def handle_find_merge_base(self):
        """Finds the merge-base of the current branch and a user-chosen branch,
        then shows the SHA in a dialog with a copy-to-clipboard option."""
        dialog = MergeBaseDialog(self.repo_path, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        other_branch = dialog.branch_name
        if not other_branch:
            QMessageBox.warning(self, "No branch selected",
                                "Please choose a branch to compare against.")
            return
        current_branch = get_current_branch(self.repo_path) or "HEAD (detached)"
        print(f"[browse] Finding merge-base: current='{current_branch}' vs '{other_branch}'")
        if not branch_exists(self.repo_path, other_branch):
            QMessageBox.critical(self, "Branch does not exist",
                                 f"The branch '{other_branch}' does not exist.")
            return

        ref = normalize_branch_ref(self.repo_path, other_branch)
        try:
            base_sha = get_merge_base(self.repo_path, ref)
        except Exception as e:
            print(f"[browse] Merge-base error: {e}")
            QMessageBox.critical(self, "Merge Base Error", f"Could not find the merge base.\n\nError: {e}")
            return
        if not base_sha:
            print("[browse] No common ancestor found")
            QMessageBox.warning(
                self, "No common ancestor",
                f"No merge-base found between '{current_branch}' and '{other_branch}'.\n\n"
                "The two branches may be unrelated histories.")
            return

        short_sha = base_sha[:8]
        subject = get_commit_subject(self.repo_path, base_sha) or ""
        print(f"[browse] Merge-base found: {short_sha} — {subject}")
        text = (f"Merge-base of <b>{current_branch}</b> and <b>{other_branch}</b>:\n\n"
                f"{base_sha}\n({short_sha}) {subject}\n\n"
                "Copy the SHA to the clipboard, or click OK to close.")
        MergeBaseResultDialog(text, base_sha, parent=self).exec()

    def handle_browse_file_log(self):
        """Opens a read-only viewer showing the history of a single file.
        Prompts for a repo-relative file path and the number of commits to load."""
        dialog = BrowseFileLogDialog(self.repo_path, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        file_path = dialog.file_path
        commit_limit = dialog.commit_limit
        if not file_path:
            QMessageBox.warning(self, "No file path",
                                "Please enter a file path to browse.")
            return
        full_path = os.path.join(self.repo_path, file_path)
        if not os.path.isfile(full_path):
            QMessageBox.critical(self, "File does not exist",
                                 f"The file '{file_path}' does not exist.")
            return
        print(f"[browse] Opening file log: '{file_path}', limit={commit_limit}")
        self._open_file_log_viewer(file_path, commit_limit)

    def open_file_log_for(self, file_path, commit_limit=None):
        """Opens a read-only file-log viewer for an existing repo-relative path
        without prompting (used by file-wise context menus)."""
        if commit_limit is None:
            commit_limit = self.browse_limit
        print(f"[browse] File log for: '{file_path}', limit={commit_limit}")
        self._open_file_log_viewer(file_path, commit_limit)

    def _open_file_log_viewer(self, file_path, commit_limit):
        file_ref = self.browse_branch if self.browse_branch else None
        print(f"[browse] Creating file-log viewer: '{file_path}', ref={file_ref}, limit={commit_limit}")
        AppClass = _get_app_class()
        viewer = AppClass(
            self.repo_path, self.commit_sha, self.app_start_time,
            viewer_mode=True, browse_file=file_path, parent=self,
            browse_limit=commit_limit, browse_file_ref=file_ref,
        )
        # The browse viewer inherits the main window's current zoom and theme.
        viewer.current_font_size = self.current_font_size
        viewer.update_font()
        if viewer.is_dark_theme != self.is_dark_theme:
            viewer.is_dark_theme = self.is_dark_theme
            viewer.apply_theme("dark" if self.is_dark_theme else "light")
        self.browse_windows.append(viewer)
        viewer.show()

    def handle_open_file_at_ref(self):
        """Open a file at a specific commit/branch/tag using the system default app.
        Shows a dialog to pick the ref and file, then extracts and opens it."""
        dialog = OpenFileAtRefDialog(self.repo_path, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        filepath = dialog.selected_file
        sha = dialog.resolved_sha
        if not filepath or not sha:
            return

        print(f"[browse] Open file at ref: '{filepath}' at {sha[:8]}")

        try:
            import subprocess
            import tempfile
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices

            result = subprocess.run(
                ["git", "show", f"{sha}:{filepath}"],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding='utf-8', errors='replace'
            )
            if result.returncode != 0:
                QMessageBox.critical(self, "Open Failed",
                                     f"Could not extract '{filepath}' from {sha[:8]}.\n\n{result.stderr}")
                return

            basename = os.path.basename(filepath)
            tmp_dir = tempfile.mkdtemp(prefix="git-open-")
            tmp_path = os.path.join(tmp_dir, basename)
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write(result.stdout)
            QDesktopServices.openUrl(QUrl.fromLocalFile(tmp_path))
            print(f"[browse] Opened '{filepath}' from {sha[:8]} via {tmp_path}")
        except Exception as e:
            QMessageBox.critical(self, "Open Failed", f"Could not open file: {e}")

    def handle_diff_file_at_ref(self, filepath, current_sha):
        """Diff a file against a different version using difftool."""
        from lib.dialogs.history_branch_dialogs import DiffFileAtRefDialog
        dialog = DiffFileAtRefDialog(self.repo_path, filepath, current_sha, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        ref_sha = dialog.resolved_sha
        target_file = dialog.selected_file
        if not ref_sha or not target_file:
            return
        print(f"[diff] Difftool '{target_file}' between {ref_sha[:8]} and {current_sha[:8]}")
        try:
            import subprocess
            subprocess.Popen(
                ["git", "difftool", ref_sha, current_sha, "--", target_file],
                cwd=self.repo_path
            )
        except Exception as e:
            QMessageBox.critical(self, "Difftool Failed", f"Could not run difftool: {e}")
