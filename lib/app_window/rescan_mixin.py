import subprocess
import threading
from datetime import datetime
from PySide6.QtCore import Qt, QTimer, Slot, Q_ARG, QMetaObject
from PySide6.QtWidgets import QApplication, QMessageBox, QListWidgetItem, QInputDialog, QDialog
from lib.git_helpers import (
    get_git_history, get_git_history_fast, get_commit_stats,
    get_branch_history, get_file_history,
    get_reflog_history, get_stash_history, get_tags_history,
    get_head_sha, get_full_head_sha, get_current_branch,
    get_local_branches_map,
    has_uncommitted_changes, stash_changes, STASH_NOTHING_STASHED,
    commit_file, bulk_commit_all, amend_with_head, discard_changes,
    get_unstaged_files, get_diff_between, get_files_between,
    get_file_stats_between, get_merge_base, resolve_ref,
)
from lib.dialogs import (
    UnstagedChangesDialog, BranchDiffDialog, ProgressDialog,
)
from lib.commit_filter_controller import CommitFilterController
from lib.app_window.helpers import PR_DIFF_SIZE_WARN_THRESHOLD


class RescanMixin:
    """Repository rescan, history loading, diff display, and browse operations."""

    def handle_rescan_repo(self):
        """Safely rescan repository state, prompting user for unstaged changes identically to app startup if found."""
        print(f"[rescan] Rescanning repository...")
        unstaged_files = get_unstaged_files(self.repo_path, ignore_submodules=True)
        print(f"[rescan] Found {len(unstaged_files)} unstaged files")
        if unstaged_files:
            dialog = UnstagedChangesDialog(len(unstaged_files), parent=self, from_rescan=True,
                                           repo_path=self.repo_path, unstaged_files=unstaged_files,
                                           font_size=self.current_font_size,
                                           managed_stash_sha=self.app_managed_stash_sha,
                                           viewer_mode=self.viewer_mode)
            result = dialog.exec()

            if self.viewer_mode and result in (
                UnstagedChangesDialog.Accepted,
                UnstagedChangesDialog.CommitEachResult,
                UnstagedChangesDialog.BulkCommitResult,
                UnstagedChangesDialog.AmendResult,
                UnstagedChangesDialog.SelectiveCommitResult,
            ):
                QMessageBox.warning(self, "Viewer Mode", "This operation is not allowed in Viewer Mode.")
                return

            if result == UnstagedChangesDialog.MergeResult:
                self._merge_into_managed_stash()
            elif result == UnstagedChangesDialog.SelectiveCommitResult:
                self._commit_selectively_from_dialog()
            elif result == UnstagedChangesDialog.Accepted:
                created_stash_sha, stash_err = stash_changes(
                    self.repo_path,
                    message=f"git-interactive-rebase-gui-tool: Rescan stash ({datetime.now().strftime('%H:%M:%S %Y-%m-%d')})")
                if created_stash_sha is not None and created_stash_sha is not STASH_NOTHING_STASHED:
                    self.app_managed_stash_sha = created_stash_sha
                    self._update_stash_btn_visibility()
                    self._flash_pop_stash_btn()
                    QMessageBox.information(self, "Stash Successful", f"Changes stashed successfully (SHA: {created_stash_sha[:8]}).")
                elif created_stash_sha is STASH_NOTHING_STASHED:
                    QMessageBox.information(self, "No Changes Stashed",
                                            "There was nothing to stash (e.g. changes are in untracked files). "
                                            "Please handle them manually.")
                else:
                    detail = f"\n\n{stash_err}" if stash_err else ""
                    QMessageBox.critical(self, "Error", f"Failed to stash changes. Please stash or commit manually.{detail}")
                    return
            elif result == UnstagedChangesDialog.CommitEachResult:
                progress = ProgressDialog("Committing Changes", f"Committing {len(unstaged_files)} files individually...", self)
                progress.show()
                for _ in range(3): QApplication.processEvents()

                success_count = 0
                committed_shas = []
                failed_files = []
                for i, f in enumerate(unstaged_files):
                    progress.label.setText(f"Committing ({i+1}/{len(unstaged_files)}): {f}")
                    for _ in range(2): QApplication.processEvents()
                    ok, err = commit_file(self.repo_path, f, f"changes in {f}")
                    if ok:
                        committed_shas.append(self.get_head_sha()[:8])
                        success_count += 1
                    else:
                        failed_files.append((f, err))

                progress.close()
                if committed_shas:
                    ids = "\n".join(committed_shas)
                    QMessageBox.information(
                        self, "Commit Successful",
                        f"Done. Successfully committed {success_count} file(s) individually.\n\n"
                        f"Commit IDs:\n{ids}"
                    )
                if failed_files:
                    fail_lines = "\n".join(f"  {name}: {err}".rstrip() for name, err in failed_files)
                    QMessageBox.critical(
                        self, "Some Commits Failed",
                        f"Failed to commit {len(failed_files)} of {len(unstaged_files)} file(s):\n\n{fail_lines}"
                    )
            elif result == UnstagedChangesDialog.BulkCommitResult:
                msg = f"bulk commit (Number of modified files: {len(unstaged_files)})"

                success, detail = bulk_commit_all(self.repo_path, msg)

                if success:
                    QMessageBox.information(
                        self, "Bulk Commit Successful",
                        f"Done. Bulk commit successful.\n\nCommit ID:\n{self.get_head_sha()[:8]}"
                    )
                else:
                    QMessageBox.critical(self, "Error", f"Bulk commit failed.\n\n{detail}")
                    return
            elif result == UnstagedChangesDialog.AmendResult:
                old_head = self.get_head_sha()
                success, detail = amend_with_head(self.repo_path)

                if success:
                    QMessageBox.information(
                        self, "Amend Successful",
                        f"Done. Changes amended into HEAD commit.\n\n"
                        f"OLD COMMIT: {old_head[:8]}\nNEW COMMIT: {self.get_head_sha()[:8]}"
                    )
                else:
                    QMessageBox.critical(self, "Error", f"Amend failed.\n\n{detail}")
                    return
            elif result == UnstagedChangesDialog.DiscardResult:
                success, detail = discard_changes(self.repo_path)

                if success:
                    QMessageBox.information(self, "Discard Successful", "Done. Unstaged changes discarded (git checkout .).")
                else:
                    QMessageBox.critical(self, "Error", f"Discard failed.\n\n{detail}")
                    return
            elif result == UnstagedChangesDialog.ViewerModeResult:
                self.viewer_mode = True
                self.exit_viewer_mode_btn.setVisible(True)
                self.update_window_title()
                self._notify_viewer_mode()
            else:
                # Cancel/Rejected: Just return successfully and quietly drop the window.
                return

        # Finally, we reload the tree to correctly align matching local state
        if self.browse_mode:
            self.load_browse_history_async()
        else:
            self.load_history()

    def show_consolidated_diff(self, start_sha, end_sha, title=None, description=None):
        """Displays the consolidated diff between *start_sha* and *end_sha* using the shared diff dialog."""
        try:
            if not start_sha or not end_sha:
                return
            if start_sha[:8].lower() == end_sha[:8].lower():
                QMessageBox.information(
                    self, "Consolidated Diff",
                    "The start and end commits are the same, so there is nothing to compare.\n\n"
                    f"Commit: {start_sha[:8]}"
                )
                return
            progress = ProgressDialog(title or "Consolidated Diff", "Computing diff...", self)
            progress.show()
            QApplication.processEvents()
            try:
                diff_text = get_diff_between(self.repo_path, start_sha, end_sha)
                files = get_files_between(self.repo_path, start_sha, end_sha)
                file_stats = get_file_stats_between(self.repo_path, start_sha, end_sha)
                num_commits = len(get_git_history(self.repo_path, start_sha, end_sha)[0])
            finally:
                progress.close()

            if len(diff_text) > PR_DIFF_SIZE_WARN_THRESHOLD:
                answer = QMessageBox.warning(
                    self, "Large Consolidated Diff",
                    f"This consolidated diff is large (~{len(diff_text)/1024:.0f} KB) and may be slow or hard to digest.\n\n"
                    "Do you want to open it anyway?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if answer != QMessageBox.Yes:
                    return

            dialog = BranchDiffDialog(self.repo_path, start_sha, end_sha, num_commits, diff_text, files,
                                      file_stats, self.current_font_size, self, title=title, description=description)
            self._open_viewer(dialog)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch consolidated diff: {str(e)}")

    def _set_consolidated_diff_start(self, sha):
        """Stores the selected commit as the start point for a consolidated diff."""
        self.consolidated_diff_start_sha = sha
        # Repaint so the left accent bar moves to the newly selected start commit
        self.list_widget.viewport().update()

    def handle_view_branch_diff(self):
        """Opens a PR preview dialog showing the combined branch diff vs its base."""
        try:
            # Resolve the base: fresh merge-base with the detected upstream, else ask the user
            base_sha = None
            if self.base_branch:
                base_sha = get_merge_base(self.repo_path, self.base_branch)

            if not base_sha:
                if self.base_branch is None:
                    # No parent branch detected (e.g. viewer/gitk mode): ask the user for a base ref
                    text, ok = QInputDialog.getText(
                        self, "PR Preview - Base Commit",
                        "No parent branch was detected.\n\n"
                        "Enter a base commit/ref to diff against (e.g. a SHA, 'HEAD~5', 'origin/main'):",
                        text=str(self.commit_sha or ""),
                    )
                    if not ok or not text.strip():
                        return  # user cancelled
                    base_sha = resolve_ref(self.repo_path, text.strip())
                    if not base_sha:
                        QMessageBox.warning(self, "PR Preview", f"Could not resolve base ref: '{text.strip()}'")
                        return
                else:
                    # base_branch set but merge-base failed
                    base_sha = self.commit_sha

            if not base_sha:
                QMessageBox.information(self, "PR Preview", "Could not determine the base commit to diff against.")
                return
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not fetch branch diff: {str(e)}")
            return

        branch = get_current_branch(self.repo_path) or "HEAD"
        self.show_consolidated_diff(base_sha, self.get_head_sha(), title="PR Preview", description=branch)

    def handle_manual_refresh(self):
        """Shows a progress dialog during manual refresh."""
        if self.browse_mode:
            print(f"[rescan] Manual refresh in browse mode — reloading browse history")
            self.load_browse_history_async()
            return
        print(f"[rescan] Manual refresh — full history reload")
        progress = ProgressDialog("Refreshing", "Refreshing git history. Please wait...", self)
        progress.show()
        QApplication.processEvents()
        try:
            self.load_history()
        finally:
            progress.close()

    def load_history(self):
        """Fetches git history and populates the list widget."""
        # In browse mode, always reload via the async, limit-bounded loader so we
        # never block the GUI thread on an unlimited full-history scan (which hangs
        # on large repos like vim).
        if self.browse_mode or self.browse_branch:
            self.load_browse_history_async()
            return

        print(f"[rescan] Loading full history (browse_branch={self.browse_branch})")
        # Invalidate cache as history might have changed
        self.commit_cache.clear()

        # Clear search when reloading history
        self.update_window_title()

        current_branch = get_current_branch(self.repo_path)

        # Update origin reset button label with current branch
        if hasattr(self, 'reset_origin_btn'):
            self.reset_origin_btn.setText(f"git reset --hard origin/{current_branch}")

        # Save current row to restore selection
        old_row = self.list_widget.currentRow()

        self.list_widget.clear()
        self.list_widget.setUpdatesEnabled(False)
        self.list_widget.blockSignals(True)
        try:
            if self.browse_branch:
                history, tag_map = get_branch_history(self.repo_path, self.browse_branch)
                self._stats_range = None
            else:
                # Fast path: load commits without --shortstat (~0.1s vs ~1s)
                history, tag_map = get_git_history_fast(self.repo_path, self.commit_sha, self.get_head_sha())
                self._stats_range = (self.commit_sha, self.get_head_sha())
            branch_map = get_local_branches_map(
                self.repo_path,
                current_branch=current_branch,
                extra_remotes=[self.browse_branch] if self.browse_branch else None,
            )

            print(f"[rescan] Loaded {len(history)} commits, {len(branch_map)} branches, {len(tag_map)} tags")
            self._populate_list_widget(history, branch_map, tag_map, old_row)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        finally:
            self.list_widget.setUpdatesEnabled(True)
            self.list_widget.blockSignals(False)
            # Defer side diff so the window appears immediately
            QTimer.singleShot(0, self.update_side_diff)

        self._refresh_history_load()

        # Load stats (added/deleted) in background if we used the fast path
        if self._stats_range:
            self._load_stats_async()

    def _populate_list_widget(self, history, branch_map, tag_map, old_row):
        """Builds QListWidgetItems from fetched history (main thread only)."""
        for entry in history:
            if isinstance(entry, dict):
                line = entry["raw_text"]
                sha = entry["sha"]
                item = QListWidgetItem(line)
                item.setData(Qt.UserRole + 2, entry.get("date", ""))
                item.setData(Qt.UserRole + 3, (entry.get("added", 0), entry.get("deleted", 0)))
                item.setData(Qt.UserRole + 4, entry.get("author", ""))
                item.setData(Qt.UserRole + 6, entry.get("message", ""))
                parents = entry.get("parents", "")
                item.setData(Qt.UserRole + 5, " " in parents)
            else:
                line = entry
                sha = line.split()[0]
                item = QListWidgetItem(line)

            if sha in branch_map:
                branches_str = ", ".join(branch_map[sha])
                item.setData(Qt.UserRole + 1, branches_str)

            if sha in tag_map:
                tags_str = ", ".join(tag_map[sha])
                item.setData(Qt.UserRole + 8, tags_str)

            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            # If nothing was selected before (-1), default to topmost commit (0)
            # Otherwise, bound it to the new list size
            new_row = max(0, min(old_row if old_row >= 0 else 0, self.list_widget.count() - 1))
            self.list_widget.setCurrentRow(new_row)

        # If the list was rebuilt while multi-select mode is active, re-apply the
        # checkable flags so the UI stays consistent (tick boxes visible, etc.).
        if self.multi_select_mode:
            self._apply_multi_select_flags()

    def _load_stats_async(self):
        """Load commit stats (added/deleted) in background thread after commits are shown."""
        start_sha, end_sha = self._stats_range
        repo_path = self.repo_path
        self._stats_done = False
        self._stats_result = None

        def worker():
            try:
                # No limit — load stats for all commits shown
                stats = get_commit_stats(repo_path, start_sha, end_sha)
                self._stats_result = stats
                self._stats_done = True
            except Exception as e:
                print(f"[stats] Error loading stats: {e}")
                self._stats_done = True

        print("[stats] Loading commit stats in background...")
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(50)
        self._stats_timer.timeout.connect(self._poll_stats)
        self._stats_timer.start()

    def _poll_stats(self):
        """Poll for stats completion."""
        if not self._stats_done:
            return
        self._stats_timer.stop()
        stats = self._stats_result
        if stats:
            count = 0
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                sha = item.text().split()[0]
                if sha in stats:
                    added, deleted = stats[sha]
                    item.setData(Qt.UserRole + 3, (added, deleted))
                    count += 1
            print(f"[stats] Applied stats to {count} commits")
        self._stats_result = None

    def _refresh_history_load(self):
        """Post-load updates shared by sync and async history loading."""
        # Update Failsafe button state
        current_head = get_head_sha(self.repo_path)
        uncommitted = has_uncommitted_changes(self.repo_path)

        # Update cache
        self.cached_current_head_full_sha = get_full_head_sha(self.repo_path)
        self.cached_has_uncommitted = uncommitted

        self.total_commits_label.setText("Total: counting...")
        self._count_total_commits_async()
        self._filter_controller._update_commit_counts()

        # Re-apply the active search/filter so it isn't silently dropped after a reload
        if hasattr(self, 'search_edit'):
            self.filter_commits(self.search_edit.text())

        if current_head == self.start_time_head[:8] and not uncommitted:
            self.failsafe_btn.setEnabled(False)
            self.failsafe_btn.setText(f"Reset Hard to START_TIME_HEAD (Already at {self.start_time_head[:8]})")
        else:
            self.failsafe_btn.setEnabled(True)
            self.failsafe_btn.setText(f"⚠ Reset Hard to START_TIME_HEAD ({self.start_time_head[:8]}) ⚠")

    def load_browse_history_async(self):
        """Loads a browse window's full branch history in a background thread so the
        GUI stays responsive even for repos with tens of thousands of commits.

        Results are passed to the main thread via a polling timer (no cross-thread
        signal marshalling), which is reliable in every PySide6 environment.
        """
        self.list_widget.clear()
        self.total_commits_label.setText("Total: counting...")
        self._browse_load_done = False
        self._browse_load_result = None

        repo_path = self.repo_path
        branch = self.browse_branch
        filepath = self.browse_file
        file_ref = self.browse_file_ref
        reflog = self.browse_reflog
        stash = self.browse_stash
        tags = self.browse_tags
        browse_limit = self.browse_limit

        mode = "file" if filepath else "stash" if stash else "reflog" if reflog else "tags" if tags else "branch"
        print(f"[browse] Async load started: mode={mode}, branch='{branch}', file='{filepath}', limit={browse_limit}")

        def worker():
            try:
                if filepath:
                    history, tag_map = get_file_history(repo_path, filepath, limit=browse_limit, ref=file_ref)
                elif stash:
                    history = get_stash_history(repo_path, limit=browse_limit)
                    self._browse_load_result = (True, history, {}, {})
                    return
                elif reflog:
                    history = get_reflog_history(repo_path, limit=browse_limit)
                    self._browse_load_result = (True, history, {}, {})
                    return
                elif tags:
                    history = get_tags_history(repo_path, limit=browse_limit)
                    self._browse_load_result = (True, history, {}, {})
                    return
                else:
                    history, tag_map = get_branch_history(repo_path, branch, limit=browse_limit)
                branch_map = get_local_branches_map(
                    repo_path,
                    extra_remotes=[branch] if branch else None,
                )
                self._browse_load_result = (True, history, branch_map, tag_map)
            except Exception as e:
                print(f"[browse] Async load FAILED: {e}")
                self._browse_load_result = (False, [], str(e), {})
            finally:
                self._browse_load_done = True

        import threading
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        self._start_browse_load_poll()

    def _start_browse_load_poll(self):
        """Polls for the background browse load to finish, then populates on the main thread."""
        if not self._browse_load_done:
            QTimer.singleShot(50, self._start_browse_load_poll)
            return
        success, history, branch_map_or_error, tag_map = self._browse_load_result
        if not success:
            print(f"[browse] Async load failed: {branch_map_or_error}")
            QMessageBox.critical(self, "Error", branch_map_or_error)
            return
        print(f"[browse] Async load complete: {len(history)} entries loaded")
        self.list_widget.setUpdatesEnabled(False)
        self.list_widget.blockSignals(True)
        try:
            self._populate_list_widget(history, branch_map_or_error, tag_map, -1)
        finally:
            self.list_widget.setUpdatesEnabled(True)
            self.list_widget.blockSignals(False)
            self.update_side_diff()
        self._refresh_history_load()

    def _detect_base_async(self):
        """Detect branch base in background thread, then reload if range <= 200."""
        import threading
        repo_path = self.repo_path

        def worker():
            try:
                from lib.git_helpers import get_branch_base_info
                base_sha, branch_name = get_branch_base_info(repo_path)
                if not base_sha:
                    print("[detect_base] No base detected, keeping fallback range")
                    from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                    QMetaObject.invokeMethod(
                        self, "_apply_detected_base",
                        Qt.QueuedConnection,
                        Q_ARG(str, ""), Q_ARG(str, ""), Q_ARG(int, 0)
                    )
                    return
                # Count commits in the detected range
                import subprocess
                count_out = subprocess.check_output(
                    ["git", "rev-list", "--count", f"{base_sha}..HEAD"],
                    cwd=repo_path, encoding='utf-8', errors='replace'
                ).strip()
                count = int(count_out)
                print(f"[detect_base] Detected base: {base_sha[:8]} (branch={branch_name}, {count} commits)")
                from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(
                    self, "_apply_detected_base",
                    Qt.QueuedConnection,
                    Q_ARG(str, base_sha), Q_ARG(str, branch_name), Q_ARG(int, count)
                )
            except Exception as e:
                print(f"[detect_base] Error: {e}")

        print("[detect_base] Starting async branch-base detection...")
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    @Slot(str, str, int)
    def _apply_detected_base(self, base_sha, branch_name, commit_count):
        """Apply the detected branch base only if range <= 200 commits."""
        if not base_sha or commit_count > 200:
            if base_sha:
                print(f"[detect_base] Range too large ({commit_count} > 200), keeping 200 fallback")
                self.total_commits_label.setText(
                    f"Branch '{branch_name}' has {commit_count} commits, showing 200"
                )
            return
        self.commit_sha = base_sha
        self.base_branch = branch_name
        print(f"[detect_base] Reloading history with base: {base_sha[:8]} (branch={branch_name})")
        self.load_history()

    def _count_total_commits_async(self):
        """Count total commits in repo in background thread to avoid blocking startup."""
        import threading
        repo_path = self.repo_path
        filepath = self.browse_file
        stash = self.browse_stash

        def worker():
            try:
                if stash:
                    cmd = ["git", "stash", "list"]
                else:
                    cmd = ["git", "rev-list", "--count", "HEAD"]
                    if filepath:
                        cmd += ["--", filepath]
                total = subprocess.check_output(
                    cmd,
                    cwd=repo_path, encoding='utf-8', errors='replace'
                ).strip()
                if stash:
                    total = str(len([l for l in total.split('\n') if l.strip()]))
                from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                print(f"Total commits in repo: {total}")
                QMetaObject.invokeMethod(
                    self, "_set_total_commit_count",
                    Qt.QueuedConnection,
                    Q_ARG(str, total)
                )
            except Exception:
                from PySide6.QtCore import QMetaObject, Qt, Q_ARG
                QMetaObject.invokeMethod(
                    self, "_set_total_commit_count",
                    Qt.QueuedConnection,
                    Q_ARG(str, "?")
                )
        print("Trying to find out total commit count ...")
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    @Slot(str)
    def _set_total_commit_count(self, count_str):
        if self.browse_stash:
            self.total_commits_label.setText(f"Total stashes: {count_str}")
        elif self.browse_file:
            self.total_commits_label.setText(f"Total commits touching file: {count_str}")
        else:
            self.total_commits_label.setText(f"Total commits in repo: {count_str}")
