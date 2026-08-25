from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont, QAction
from PySide6.QtWidgets import QApplication, QMessageBox, QMenu
from lib.git_helpers import get_commit_files
from lib.app_window.helpers import MATCH_ROLE


class MenusMixin:
    """Context menus, configure/repo menus, and move operations."""

    def _build_configure_menu(self):
        """Builds the status-bar configure menu: a 'Show/Hide' submenu with
        checkable actions controlling which markers/columns are visible."""
        menu = QMenu(self)

        self.show_origin_action = QAction("Show Origin", self)
        self.show_origin_action.setCheckable(True)
        self.show_origin_action.setChecked(self.show_origin_options)
        self.show_origin_action.setToolTip("Show origin markers.")
        self.show_origin_action.toggled.connect(self.on_origin_visibility_toggled)

        self.show_rebase_action = QAction("Show Rebase", self)
        self.show_rebase_action.setCheckable(True)
        self.show_rebase_action.setChecked(self.show_rebase_options)
        self.show_rebase_action.setToolTip("Show rebase markers.")
        self.show_rebase_action.toggled.connect(self.on_rebase_visibility_toggled)

        self.show_squash_action = QAction("Show Squash", self)
        self.show_squash_action.setCheckable(True)
        self.show_squash_action.setChecked(self.show_squash_options)
        self.show_squash_action.setToolTip("Show squash markers.")
        self.show_squash_action.toggled.connect(self.on_squash_visibility_toggled)

        self.show_local_branches_action = QAction("Show Local Branches", self)
        self.show_local_branches_action.setCheckable(True)
        self.show_local_branches_action.setChecked(self.show_local_branches)
        self.show_local_branches_action.setToolTip("Show local branch markers.")
        self.show_local_branches_action.toggled.connect(self.on_local_branches_visibility_toggled)

        self.show_tags_action = QAction("Show Tags", self)
        self.show_tags_action.setCheckable(True)
        self.show_tags_action.setChecked(self.show_tags)
        self.show_tags_action.setToolTip("Show tag markers.")
        self.show_tags_action.toggled.connect(self.on_tags_visibility_toggled)

        self.show_stats_action = QAction("Show Stats", self)
        self.show_stats_action.setCheckable(True)
        self.show_stats_action.setChecked(self.show_stats)
        self.show_stats_action.setToolTip("Show per-commit line stats.")
        self.show_stats_action.toggled.connect(self._on_stats_toggled)

        self.show_date_action = QAction("Show Date", self)
        self.show_date_action.setCheckable(True)
        self.show_date_action.setChecked(self.show_date)
        self.show_date_action.setToolTip("Show commit dates.")
        self.show_date_action.toggled.connect(self._on_date_toggled)

        self.show_diffs_action = QAction("Show Diffs", self)
        self.show_diffs_action.setCheckable(True)
        self.show_diffs_action.setChecked(self.show_diffs)
        self.show_diffs_action.setToolTip("Show or hide the right-side diff panel.")
        self.show_diffs_action.toggled.connect(self.on_diffs_visibility_toggled)

        show_hide = menu.addMenu("Show/Hide")
        show_hide.addAction(self.show_origin_action)
        show_hide.addAction(self.show_rebase_action)
        show_hide.addAction(self.show_squash_action)
        show_hide.addAction(self.show_local_branches_action)
        show_hide.addAction(self.show_tags_action)
        show_hide.addSeparator()
        show_hide.addAction(self.show_stats_action)
        show_hide.addAction(self.show_date_action)
        show_hide.addSeparator()
        show_hide.addAction(self.show_diffs_action)

        menu.addSeparator()

        self.external_tools_action = QAction("External tools", self)
        self.external_tools_action.setToolTip("Configure external tool integrations.")
        self.external_tools_action.triggered.connect(lambda *_: QMessageBox.information(self, "External tools", "Not implemented yet."))

        self.help_action = QAction("Help", self)
        self.help_action.setToolTip("Show usage help.")
        self.help_action.triggered.connect(lambda *_: self._show_help_dialog())

        self.check_updates_action = QAction("Check Updates", self)
        self.check_updates_action.setToolTip("Check for a newer version online.")
        self.check_updates_action.triggered.connect(lambda *_: self.handle_check_for_updates())

        menu.addAction(self.external_tools_action)
        menu.addAction(self.help_action)
        menu.addAction(self.check_updates_action)

        return menu

    def _show_configure_menu(self):
        """Pops up the configure menu under the status-bar Configure button."""
        self.configure_menu.popup(
            self.configure_btn.mapToGlobal(QPoint(0, self.configure_btn.height())))

    def _build_repo_menu(self):
        """Builds the Repo button's menu: View PR Diff / View a Commit /
        Cherry-pick 1 Commit / Browse Branch / Browse File Log / Find Merge-base
        (previously separate toolbar buttons)."""
        menu = QMenu(self)

        pr_diff_action = QAction("View PR Diff", self)
        pr_diff_action.setToolTip("View the branch diff vs its base.")
        pr_diff_action.triggered.connect(lambda *_: self.handle_view_branch_diff())

        view_commit_action = QAction("View a Commit…", self)
        view_commit_action.setToolTip("Open any commit by SHA in a read-only tabbed viewer (Plain / File-wise diff).")
        view_commit_action.triggered.connect(lambda *_: self.handle_view_commit_by_sha())

        cherry_pick_action = QAction("Cherry-pick 1 Commit", self)
        cherry_pick_action.setToolTip("Cherry-pick a single commit by SHA.")
        cherry_pick_action.triggered.connect(lambda *_: self.handle_cherry_pick())

        apply_patch_action = QAction("Apply Patch…", self)
        apply_patch_action.setToolTip("Apply a patch file to the repository, committing the changes or leaving them unstaged.")
        apply_patch_action.triggered.connect(lambda *_: self.handle_apply_patch())

        browse_action = QAction("Browse Branch", self)
        browse_action.setToolTip("Open a read-only viewer of another branch's full history.")
        browse_action.triggered.connect(lambda *_: self.handle_browse_branch())

        browse_file_action = QAction("Browse File Log", self)
        browse_file_action.setToolTip("Open a read-only viewer of a single file's history.")
        browse_file_action.triggered.connect(lambda *_: self.handle_browse_file_log())

        browse_commit_log_action = QAction("Browse Log of a Commit", self)
        browse_commit_log_action.setToolTip("Open a read-only viewer of a commit's history.")
        browse_commit_log_action.triggered.connect(lambda *_: self.handle_browse_commit_log())

        browse_reflog_action = QAction("Browse Reflog", self)
        browse_reflog_action.setToolTip("Open a read-only viewer of the repository's HEAD reflog.")
        browse_reflog_action.triggered.connect(lambda *_: self.handle_browse_reflog())

        browse_tags_action = QAction("Browse Tags", self)
        browse_tags_action.setToolTip("Open a read-only viewer of all tags in the repository.")
        browse_tags_action.triggered.connect(lambda *_: self.handle_browse_tags())

        browse_stash_action = QAction("Browse Stashes", self)
        browse_stash_action.setToolTip("Open a read-only viewer of the repository's stash list.")
        browse_stash_action.triggered.connect(lambda *_: self.handle_browse_stash())

        open_file_ref_action = QAction("Open File at Commit…", self)
        open_file_ref_action.setToolTip("Browse and open a file at any commit, branch, or tag with the system default app.")
        open_file_ref_action.triggered.connect(lambda *_: self.handle_open_file_at_ref())

        merge_base_action = QAction("Find Merge-base…", self)
        merge_base_action.setToolTip("Find the merge-base of the current branch and another branch.")
        merge_base_action.triggered.connect(lambda *_: self.handle_find_merge_base())

        menu.addAction(pr_diff_action)
        menu.addAction(view_commit_action)
        menu.addAction(cherry_pick_action)
        menu.addAction(apply_patch_action)
        menu.addAction(browse_action)
        menu.addAction(browse_file_action)
        menu.addAction(browse_commit_log_action)
        menu.addAction(browse_reflog_action)
        menu.addAction(browse_tags_action)
        menu.addAction(browse_stash_action)
        menu.addAction(open_file_ref_action)
        menu.addAction(merge_base_action)
        return menu

    def _on_always_on_top_toggled(self, checked):
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()

    def force_window_resize(self):
        """Forces the window to shrink to its minimum size hint if not maximized."""
        if self.isMaximized():
            # If maximized, resizing doesn't make sense and can cause glitches.
            # Just force the layout to re-evaluate and update visually.
            if self.centralWidget() and self.centralWidget().layout():
                self.centralWidget().layout().activate()
            self.update()
            return

        # A common trick to force a window to shrink in Qt is to
        # resize it to a very small height and then call adjustSize()
        self.resize(self.width(), 1)
        self.adjustSize()

    def show_browse_context_menu(self, position):
        """Read-only context menu for branch/file-log browsers: copy-only actions."""
        item = self.list_widget.itemAt(position)
        if not item:
            return

        menu = QMenu()
        menu.setFont(QFont("Monospace", max(8, self.current_font_size - 2)))

        copy_sha_action = QAction("Copy SHA to clipboard", self)
        copy_msg_action = QAction("Copy commit msg to clipboard", self)
        copy_sha_msg_action = QAction("Copy SHA and commit msg to clipboard", self)
        copy_sha_action.triggered.connect(lambda: self.handle_copy_sha(item))
        copy_msg_action.triggered.connect(lambda: self.handle_copy_message(item))
        copy_sha_msg_action.triggered.connect(lambda: self.handle_copy_sha_and_message(item))

        menu.addAction(copy_sha_action)
        menu.addAction(copy_msg_action)
        menu.addAction(copy_sha_msg_action)
        menu.exec(self.list_widget.mapToGlobal(position))

    def show_reflog_context_menu(self, position):
        """Read-only context menu for the reflog browser: copy SHA / show log."""
        item = self.list_widget.itemAt(position)
        if not item:
            return

        menu = QMenu()
        menu.setFont(QFont("Monospace", max(8, self.current_font_size - 2)))

        copy_sha_action = QAction("Copy SHA to clipboard", self)
        show_log_action = QAction("Show log", self)
        copy_sha_action.triggered.connect(lambda: self.handle_copy_sha(item))
        show_log_action.triggered.connect(lambda: self.handle_reflog_show_log_item(item))

        menu.addAction(show_log_action)
        menu.addAction(copy_sha_action)
        menu.exec(self.list_widget.mapToGlobal(position))

    def show_stash_context_menu(self, position):
        """Read-only context menu for the stash browser: copy SHA plus
        apply / drop operations. Stash subjects (e.g. 'WIP on master') are not
        commit messages, so the message-copy actions are intentionally omitted."""
        item = self.list_widget.itemAt(position)
        if not item:
            return

        menu = QMenu()
        menu.setFont(QFont("Monospace", max(8, self.current_font_size - 2)))

        copy_sha_action = QAction("Copy SHA to clipboard", self)
        copy_sha_action.triggered.connect(lambda: self.handle_copy_sha(item))
        apply_keep_action = QAction("Apply + keep stash", self)
        apply_keep_action.triggered.connect(lambda: self.handle_stash_apply(item, drop_after=False))
        apply_drop_action = QAction("Apply + drop stash", self)
        apply_drop_action.triggered.connect(lambda: self.handle_stash_apply(item, drop_after=True))
        drop_action = QAction("Drop stash", self)
        drop_action.triggered.connect(lambda: self.handle_stash_drop(item))

        menu.addAction(copy_sha_action)
        menu.addSeparator()
        menu.addAction(apply_keep_action)
        menu.addAction(apply_drop_action)
        menu.addAction(drop_action)
        menu.exec(self.list_widget.mapToGlobal(position))

    def show_context_menu(self, position):
        # Allow context menu in multi-select mode, but we will restrict it later
        pass

        item = self.list_widget.itemAt(position)
        if not item:
            return

        sha = item.text().split()[0]
        menu = QMenu()
        menu_font = QFont("Monospace", max(8, self.current_font_size - 2))
        menu.setFont(menu_font)

        mark_action = QAction(f"Mark / Unmark commit {sha}", self)
        view_action = QAction(f"Show / View commit {sha}", self)
        create_patch_action = QAction("Create Patch", self)
        create_patch_action.setToolTip("Save this commit as a patch file (re-appliable via Repo → Apply Patch…).")
        tag_action = QAction("Tag", self)
        tag_action.setToolTip("Create a git tag (lightweight or annotated) on this commit.")
        reset_action = QAction(f"Reset Hard to {sha}", self)
        reset_here_action = QAction("Reset HEAD to Here (Keep Changes as Unstaged)", self)
        set_best_action = QAction("set as BEST_COMMITID", self)
        drop_action = QAction("Drop", self)
        rephrase_action = QAction("Rephrase", self)
        revert_action = QAction("Revert", self)

        # Clipboard items
        copy_sha_action = QAction("Copy SHA to clipboard", self)
        copy_msg_action = QAction("Copy commit msg to clipboard", self)
        copy_sha_msg_action = QAction("Copy SHA and commit msg to clipboard", self)

        # Squash items
        index = self.list_widget.row(item)
        count = self.list_widget.count()

        def format_squash_label(neighbor_item):
            parts = neighbor_item.text().split(maxsplit=1)
            n_sha = parts[0]
            return f"{n_sha}"

        squash_above_action = None
        if index > 0:
            above_item = self.list_widget.item(index - 1)
            label = f"squash with above commit ({format_squash_label(above_item)})"
            squash_above_action = QAction(label, self)
            squash_above_action.triggered.connect(lambda: self.handle_squash_above(item))
        else:
            squash_above_action = QAction("squash with above commit (N/A)", self)
            squash_above_action.setEnabled(False)

        squash_below_action = None
        if index < count - 1:
            below_item = self.list_widget.item(index + 1)
            label = f"squash with below commit ({format_squash_label(below_item)})"
            squash_below_action = QAction(label, self)
            squash_below_action.triggered.connect(lambda: self.handle_squash_below(item))
        else:
            squash_below_action = QAction("squash with below commit (N/A)", self)
            squash_below_action.setEnabled(False)

        mark_action.triggered.connect(lambda: self.toggle_mark_commit(item))
        view_action.triggered.connect(lambda: self.view_commit(item))
        create_patch_action.triggered.connect(lambda: self.handle_create_patch(item))
        tag_action.triggered.connect(lambda: self.handle_tag_commit(item))
        reset_action.triggered.connect(lambda: self.handle_reset(item))
        reset_here_action.triggered.connect(lambda: self.handle_reset_to_here(item))
        set_best_action.triggered.connect(lambda: self.handle_set_best_commit(item))
        drop_action.triggered.connect(lambda: self.handle_drop(item))
        rephrase_action.triggered.connect(lambda: self.handle_rephrase(item))
        revert_action.triggered.connect(lambda: self.handle_revert_commit(item))
        copy_sha_action.triggered.connect(lambda: self.handle_copy_sha(item))
        copy_msg_action.triggered.connect(lambda: self.handle_copy_message(item))
        copy_sha_msg_action.triggered.connect(lambda: self.handle_copy_sha_and_message(item))

        # Disable most actions if in multi-select mode
        if self.multi_select_mode:
            mark_action.setEnabled(False)
            view_action.setEnabled(False)
            create_patch_action.setEnabled(False)
            reset_action.setEnabled(False)
            reset_here_action.setEnabled(False)
            set_best_action.setEnabled(False)
            drop_action.setEnabled(False)
            rephrase_action.setEnabled(False)
            revert_action.setEnabled(False)
            copy_sha_action.setEnabled(False)
            copy_msg_action.setEnabled(False)
            copy_sha_msg_action.setEnabled(False)
            if squash_above_action: squash_above_action.setEnabled(False)
            if squash_below_action: squash_below_action.setEnabled(False)
        # Construct the menu

        menu.addAction(mark_action)
        menu.addSeparator()
        menu.addAction(view_action)
        menu.addAction(create_patch_action)
        menu.addAction(tag_action)
        menu.addSeparator()
        menu.addAction(reset_action)
        menu.addAction(reset_here_action)
        menu.addAction(set_best_action)
        menu.addSeparator()
        menu.addAction(rephrase_action)
        menu.addAction(drop_action)
        menu.addAction(revert_action)
        menu.addSeparator()

        # Squash commits submenu
        squash_menu = menu.addMenu("Squash commits")
        squash_menu.setFont(menu_font)

        # Move individual squash actions here
        if squash_above_action:
            squash_menu.addAction(squash_above_action)
        if squash_below_action:
            squash_menu.addAction(squash_below_action)

        squash_menu.addSeparator()

        select_multi_action = QAction("Select commits to squash", self)
        select_multi_action.setEnabled(not self.multi_select_mode)
        select_multi_action.triggered.connect(self.enter_multi_select_mode)

        squash_selected_action = QAction("Squash selected commits", self)
        checked_count = 0
        if self.multi_select_mode:
            checked_count = sum(1 for i in range(self.list_widget.count())
                                if self.list_widget.item(i).checkState() == Qt.Checked)
        squash_selected_action.setEnabled(self.multi_select_mode and checked_count >= 2)
        squash_selected_action.triggered.connect(self.handle_squash_selected)

        cancel_multi_action = QAction("Cancel multi selection", self)
        cancel_multi_action.setEnabled(self.multi_select_mode)
        cancel_multi_action.triggered.connect(self.handle_cancel_multi_select)

        squash_menu.addAction(select_multi_action)
        squash_menu.addAction(squash_selected_action)
        squash_menu.addAction(cancel_multi_action)

        # Move Commit submenu
        move_menu = menu.addMenu("Move Commit")
        move_menu.setFont(menu_font)

        move_up_action = QAction("Move Up (Swap with Next/Above commit)", self)
        move_up_action.setEnabled(index > 0 and not self.multi_select_mode)
        move_up_action.triggered.connect(lambda: self.handle_move_up(item))

        move_down_action = QAction("Move Down (Swap with Previous/Below commit)", self)
        move_down_action.setEnabled(index < count - 1 and not self.multi_select_mode)
        move_down_action.triggered.connect(lambda: self.handle_move_down(item))

        drag_info_action = QAction("Drag to Reorder", self)
        drag_info_action.setEnabled(not self.multi_select_mode)
        drag_info_action.triggered.connect(lambda: self.handle_move_info(item))

        move_menu.addAction(move_up_action)
        move_menu.addAction(move_down_action)
        move_menu.addSeparator()
        move_menu.addAction(drag_info_action)

        # Split Commit submenu
        split_menu = menu.addMenu("Split Commit")
        split_menu.setFont(menu_font)

        try:
            files_changed = get_commit_files(self.repo_path, sha)
            has_multiple_files = len(files_changed) > 1
        except Exception:
            has_multiple_files = False

        split_drop_file_action = QAction("drop changes from one file from this commit", self)
        split_drop_file_action.triggered.connect(lambda: self.handle_split_drop_file(item))
        split_drop_file_action.setEnabled(has_multiple_files)
        split_menu.addAction(split_drop_file_action)

        split_move_out_action = QAction("move one file changes out of this commit", self)
        split_move_out_action.triggered.connect(lambda: self.handle_split_commit(item))
        split_menu.addAction(split_move_out_action)

        split_all_action = QAction("split all changes to separate commits", self)
        split_all_action.triggered.connect(lambda: self.handle_split_all_commits(item))
        split_menu.addAction(split_all_action)

        split_per_file_action = QAction("split each file changes to separate commit", self)
        split_per_file_action.triggered.connect(lambda: self.handle_split_per_file(item))
        split_menu.addAction(split_per_file_action)

        split_menu.addSeparator()
        split_refine_action = QAction("Refine/Edit changes in selected file", self)
        split_refine_action.triggered.connect(lambda: self.handle_refine_changes(item))
        split_menu.addAction(split_refine_action)

        if self.multi_select_mode:
            split_menu.setEnabled(False)

        # Consolidated Diff submenu
        consolidated_menu = menu.addMenu("Consolidated Diff")
        consolidated_menu.setFont(menu_font)

        if self.consolidated_diff_start_sha:
            start_short = self.consolidated_diff_start_sha[:8]
            set_start_action = QAction("Set Start Commit", self)
            diff_here_action = QAction(f"Diff from {start_short} to Here", self)
        else:
            set_start_action = QAction("Set Start Commit", self)
            diff_here_action = QAction("Show Diff to Here", self)
            diff_here_action.setEnabled(False)

        head_to_here_action = QAction("From HEAD Till Here", self)

        set_start_action.triggered.connect(lambda: self._set_consolidated_diff_start(sha))
        diff_here_action.triggered.connect(
            lambda: self.show_consolidated_diff(self.consolidated_diff_start_sha, sha, title="Consolidated Diff"))
        head_to_here_action.triggered.connect(
            lambda: self.show_consolidated_diff(self.get_head_sha(), sha, title="Consolidated Diff"))

        if self.multi_select_mode:
            set_start_action.setEnabled(False)
            diff_here_action.setEnabled(False)
            head_to_here_action.setEnabled(False)

        consolidated_menu.addAction(set_start_action)
        consolidated_menu.addAction(diff_here_action)
        consolidated_menu.addAction(head_to_here_action)

        menu.addSeparator()
        menu.addAction(copy_sha_action)
        menu.addAction(copy_msg_action)
        menu.addAction(copy_sha_msg_action)
        menu.exec(self.list_widget.mapToGlobal(position))

    def handle_move_info(self, item):
        QMessageBox.information(
            self,
            "Move Commit",
            "Any commit can be dragged and dropped to a new position to reorder.\n\n"
            "Simply click and hold a commit, then drag it to where you want it."
        )

    def handle_move_selected_info(self):
        QMessageBox.information(
            self,
            "Move Selected Commits",
            "Checked commits that are adjacent (contiguous) can be dragged and dropped "
            "to a new position to reorder them together.\n\n"
            "Click and hold any one of the checked commits, then drag the whole block "
            "to where you want it. A confirmation dialog shows the range being moved."
        )

    def handle_move_up(self, item):
        """Swaps the selected commit with the one above it (Towards HEAD)."""
        idx = self.list_widget.row(item)
        if idx <= 0:
            return

        sha = item.text().split()[0]

        reply = QMessageBox.question(
            self,
            "Confirm Move Up",
            f"Are you sure you want to move commit <b>{sha}</b> up?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return

        old_head = self.get_head_sha()
        current_shas = [self.list_widget.item(i).text().split()[0] for i in range(self.list_widget.count())]
        # Swap with older (idx-1)
        current_shas[idx], current_shas[idx-1] = current_shas[idx-1], current_shas[idx]

        if self.run_interactive_rebase(current_shas, progress_title="Moving Commit", progress_text=f"Moving commit {sha} up..."):
            self.load_history()
            # Select the moved commit at its new index (idx - 1)
            target_idx = max(0, idx - 1)
            self.list_widget.setCurrentRow(target_idx)

            new_head = self.get_head_sha()
            self.log_action(sha, "moved up", old_head, new_head)
            QMessageBox.information(self, "Success", "Commit moved successfully.")

    def handle_move_down(self, item):
        """Swaps the selected commit with the one below it (Away from HEAD)."""
        idx = self.list_widget.row(item)
        if idx >= self.list_widget.count() - 1:
            return

        sha = item.text().split()[0]

        reply = QMessageBox.question(
            self,
            "Confirm Move Down",
            f"Are you sure you want to move commit <b>{sha}</b> down?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return

        old_head = self.get_head_sha()
        current_shas = [self.list_widget.item(i).text().split()[0] for i in range(self.list_widget.count())]
        # Swap with newer (idx+1)
        current_shas[idx], current_shas[idx+1] = current_shas[idx+1], current_shas[idx]

        if self.run_interactive_rebase(current_shas, progress_title="Moving Commit", progress_text=f"Moving commit {sha} down..."):
            self.load_history()
            # Select the moved commit at its new index (idx + 1)
            target_idx = min(self.list_widget.count() - 1, idx + 1)
            self.list_widget.setCurrentRow(target_idx)

            new_head = self.get_head_sha()
            self.log_action(sha, "moved down", old_head, new_head)
            QMessageBox.information(self, "Success", "Commit moved successfully.")
