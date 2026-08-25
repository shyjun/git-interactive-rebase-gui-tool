from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QListWidgetItem, QMessageBox, QMenu
import os
from lib.git_helpers import (
    get_commit_metadata_and_message, get_commit_diff,
    get_file_diff_only_in_commit, get_commit_files_with_status,
    get_commit_file_stats, get_rename_diff_in_commit,
)
from lib.widgets import FILE_ENTRY_ROLE
from lib.dialogs import open_blame_window
from lib.app_window.helpers import add_open_with_system_default_action


class DiffMixin:
    def show_search_bar(self):
        if not self.right_panel.isVisible():
            return
        if self.diff_tab_widget.currentIndex() == 0:
            self.plain_diff_search.show_and_focus()
        elif self.diff_tab_widget.currentIndex() == 1:
            self.filewise_diff_search.show_and_focus()

    def on_selection_changed(self):
        """Triggered when list selection changes. Debounces the update."""
        self.update_diff_timer.start(50) # 50ms debounce

    def update_side_diff(self):
        """Synchronous version for immediate updates when needed."""
        self._do_update_side_diff()

    def _do_update_side_diff(self):
        if self.browse_reflog or self.browse_tags:
            return
        item = self.list_widget.currentItem()
        if not item:
            if hasattr(self, 'side_commit_label'):
                self.side_commit_label.setText("Select a commit to view details")
                self.side_commit_msg.clear()
            self.side_diff_view.clear()
            if hasattr(self, 'filewise_file_list'):
                self.filewise_file_list.clear()
                self.filewise_diff_view.clear()
            return

        sha = item.text().split()[0]

        # Check cache
        cache_entry = self.commit_cache.get(sha, {})

        try:
            if 'meta' not in cache_entry:
                meta, msg = get_commit_metadata_and_message(self.repo_path, sha)
                cache_entry['meta'] = meta
                cache_entry['msg'] = msg
                self.commit_cache[sha] = cache_entry

            meta = cache_entry['meta']
            msg = cache_entry['msg']

            self.side_commit_label.setText(f"Commit: <b>{sha}</b>  <span style='color:gray;'>({meta})</span>")
            self.side_commit_msg.setPlainText(msg)

            if self.diff_tab_widget.currentIndex() == 0:
                if self.browse_file:
                    diff_key = f'file_diff:{self.browse_file}'
                    if diff_key not in cache_entry:
                        cache_entry[diff_key] = get_file_diff_only_in_commit(
                            self.repo_path, sha, self.browse_file)
                        self.commit_cache[sha] = cache_entry
                    diff_text = cache_entry[diff_key]
                else:
                    if 'diff' not in cache_entry:
                        cache_entry['diff'] = get_commit_diff(self.repo_path, sha)
                        self.commit_cache[sha] = cache_entry
                    diff_text = cache_entry['diff']
                self.side_diff_view.setPlainText(diff_text)
                self.side_diff_view.set_separator_color(self.current_theme_colors.get("separator", "#444444"))
                # Re-evaluate search if the search bar is visible
                if self.plain_diff_search.isVisible():
                    self.plain_diff_search._perform_search()
            else:
                self.side_diff_view.clear()
                if 'files' not in cache_entry:
                    cache_entry['files'] = get_commit_files_with_status(self.repo_path, sha, stash=self.browse_stash)
                    self.commit_cache[sha] = cache_entry

                file_entries = cache_entry['files']
                # Fetch per-file stats (cached separately)
                if 'file_stats' not in cache_entry:
                    try:
                        cache_entry['file_stats'] = get_commit_file_stats(self.repo_path, sha)
                    except:
                        cache_entry['file_stats'] = {}
                    self.commit_cache[sha] = cache_entry
                file_stats = cache_entry.get('file_stats', {})

                # Temporarily block signals to avoid triggering on_filewise_file_selected prematurely
                self.filewise_file_list.blockSignals(True)
                self.filewise_file_list.clear()
                for entry in file_entries:
                    status, path1, path2 = entry
                    if status == 'R':
                        display = f"{path1} => {path2}"
                    else:
                        display = path1
                    item = QListWidgetItem(display)
                    item.setData(Qt.UserRole, file_stats.get(display))
                    item.setData(FILE_ENTRY_ROLE, entry)
                    self.filewise_file_list.addItem(item)
                self.filewise_file_list.blockSignals(False)

                if file_entries:
                    self.filewise_file_list.setCurrentRow(0)
                else:
                    self.filewise_diff_view.clear()
        except Exception as e:
            self.side_diff_view.setPlainText(f"Error loading diff: {e}")
            if hasattr(self, 'side_commit_msg'):
                self.side_commit_msg.clear()
                self.side_commit_label.setText("Error")
            if hasattr(self, 'filewise_diff_view'):
                self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def on_diff_tab_changed(self, index):
        self.settings.setValue(self._sk("diff_tab_index"), index)
        self.update_side_diff()

    def show_filewise_context_menu(self, pos):
        item = self.filewise_file_list.itemAt(pos)
        if not item:
            return
        entry = item.data(FILE_ENTRY_ROLE)
        target_path = entry[2] if entry and entry[0] == 'R' else item.text()
        menu = QMenu(self)
        commit_sha = None
        list_item = self.list_widget.currentItem()
        if list_item:
            commit_sha = list_item.text().split()[0]
        is_head = commit_sha and commit_sha == self.get_head_sha()
        add_open_with_system_default_action(menu, target_path, self, sha=commit_sha, is_head=is_head)
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=target_path: open_blame_window(self, text))
        menu.addAction(blame_action)

        copy_action = QAction("Copy filename to clipboard", self)
        copy_action.triggered.connect(lambda checked=False, text=target_path: self.copy_filename_to_clipboard(text))
        menu.addAction(copy_action)

        copy_fullpath_action = QAction("Copy fullpath to clipboard", self)
        copy_fullpath_action.triggered.connect(lambda checked=False, text=target_path: self.copy_fullpath_to_clipboard(text))
        menu.addAction(copy_fullpath_action)

        if not self.browse_mode and not self.viewer_mode:
            is_only_file = self.filewise_file_list.count() <= 1

            move_action = QAction("Move file changes out of this commit", self)
            move_action.triggered.connect(lambda checked=False, text=target_path: self.handle_context_move_file_out(text))
            move_action.setEnabled(not is_only_file)
            menu.addAction(move_action)

            drop_action = QAction("Drop file changes from this commit", self)
            drop_action.triggered.connect(lambda checked=False, text=target_path: self.handle_context_drop_file(text))
            drop_action.setEnabled(not is_only_file)
            menu.addAction(drop_action)

            remove_onwards_action = QAction("Remove file from this commit onwards", self)
            remove_onwards_action.triggered.connect(lambda checked=False, text=target_path: self.handle_context_remove_file_onwards(text))
            menu.addAction(remove_onwards_action)

            menu.addSeparator()
            refine_action = QAction("Refine/Edit changes in selected file", self)
            refine_action.triggered.connect(lambda checked=False, text=target_path: self.handle_context_refine_changes(text))
            menu.addAction(refine_action)

        menu.addSeparator()

        browse_log_action = QAction("Browse file log", self)
        browse_log_action.setToolTip("Open a read-only viewer of this file's history.")
        browse_log_action.triggered.connect(lambda checked=False, text=target_path: self.open_file_log_for(text))
        menu.addAction(browse_log_action)

        menu.exec(self.filewise_file_list.mapToGlobal(pos))

    def handle_context_move_file_out(self, filepath):
        current_commit_item = self.list_widget.currentItem()
        if not current_commit_item:
            return
        sha = current_commit_item.text().split()[0]
        self.perform_move_file_out(sha, filepath)

    def handle_context_drop_file(self, filepath):
        current_commit_item = self.list_widget.currentItem()
        if not current_commit_item:
            return
        sha = current_commit_item.text().split()[0]
        self.perform_drop_file_from_commit(sha, filepath)

    def handle_context_remove_file_onwards(self, filepath):
        current_commit_item = self.list_widget.currentItem()
        if not current_commit_item:
            return
        sha = current_commit_item.text().split()[0]
        self.perform_remove_file_from_commit_onwards(sha, filepath)

    def handle_context_refine_changes(self, filepath):
        current_commit_item = self.list_widget.currentItem()
        if not current_commit_item:
            return
        sha = current_commit_item.text().split()[0]
        self.perform_refine_changes(sha, filepath)

    def copy_filename_to_clipboard(self, filename):
        QApplication.clipboard().setText(filename)
        QMessageBox.information(self, "Copied", f"Copied '{filename}' to clipboard.")

    def copy_fullpath_to_clipboard(self, filename):
        fullpath = os.path.join(self.repo_path, filename)
        QApplication.clipboard().setText(fullpath)
        QMessageBox.information(self, "Copied", f"Copied '{fullpath}' to clipboard.")

    def on_filewise_file_selected(self, filepath):
        if not filepath:
            self.filewise_diff_view.clear()
            return
        item = self.list_widget.currentItem()
        if not item:
            return
        sha = item.text().split()[0]
        fw_item = self.filewise_file_list.currentItem()
        try:
            entry = fw_item.data(FILE_ENTRY_ROLE) if fw_item else None
            if entry and entry[0] == 'R':
                diff = get_rename_diff_in_commit(self.repo_path, sha, entry[1], entry[2])
            elif entry:
                diff = get_file_diff_only_in_commit(self.repo_path, sha, entry[1])
            else:
                diff = get_file_diff_only_in_commit(self.repo_path, sha, filepath)
            self.filewise_diff_view.setPlainText(diff)
            self.filewise_diff_view.set_separator_color(self.current_theme_colors.get("separator", "#444444"))
            self.filewise_diff_search._perform_search()
        except Exception as e:
            self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def handle_slash_shortcut(self):
        """Focus search bar when / is pressed."""
        if not self.search_edit.hasFocus():
            self.search_edit.setFocus()
            self.search_edit.selectAll()

    def handle_esc_shortcut(self):
        """Clear filter and focus when Esc is pressed."""
        # 1. Try to clear plain diff search if active and has content/focus
        if self.diff_tab_widget.currentIndex() == 0 and (self.plain_diff_search.search_input.text() or self.plain_diff_search.search_input.hasFocus()):
            self.plain_diff_search.escape_pressed()
            return

        # 2. Try to clear filewise diff search if active and has content/focus
        if self.diff_tab_widget.currentIndex() == 1 and hasattr(self, 'filewise_diff_search') and (self.filewise_diff_search.search_input.text() or self.filewise_diff_search.search_input.hasFocus()):
            self.filewise_diff_search.escape_pressed()
            return

        # 3. Fallback to commit history search filter
        if self.search_edit.text() or self.search_edit.hasFocus():
            self.search_edit.clear()
            self.search_edit.clearFocus()
            self.list_widget.setFocus()

    def _on_search_option_changed(self):
        """Persist the three search options and immediately re-run the active search."""
        mc = self.search_match_case_action.isChecked()
        ww = self.search_whole_word_action.isChecked()
        do = self.search_display_only_action.isChecked()
        self._filter_controller.set_search_options(mc, ww, do)
        self.settings.setValue(self._sk("search_match_case"), mc)
        self.settings.setValue(self._sk("search_display_only"), do)
        self._filter_controller.filter_commits(self.search_edit.text())

    def filter_commits(self, text):
        """Live-filters commits.  Delegates to CommitFilterController."""
        self._filter_controller.filter_commits(text)
