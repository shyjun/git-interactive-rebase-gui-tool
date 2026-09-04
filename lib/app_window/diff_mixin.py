from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QListWidgetItem, QMessageBox, QMenu, QTreeWidgetItem
import os
from lib.git_helpers import (
    get_commit_metadata_and_message, get_commit_diff,
    get_file_diff_only_in_commit, get_commit_files_with_status,
    get_commit_file_stats, get_rename_diff_in_commit, build_file_tree,
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
        elif self.diff_tab_widget.currentIndex() == 2:
            self.treewise_diff_search.show_and_focus()

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

        # Skip if the "Load 100 more" item is selected
        if item.data(Qt.UserRole + 9) == "load_more":
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

            # Always populate file-wise and tree-wise tabs
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

            # Temporarily block signals to avoid triggering _on_filewise_item_changed prematurely
            self.filewise_file_list.blockSignals(True)
            self.filewise_file_list.clear()
            for entry in file_entries:
                status, path1, path2 = entry
                if status == 'R':
                    display = f"{path1} => {path2}"
                elif status == 'D':
                    display = f"{path1} (Deleted)"
                elif status == 'A':
                    display = f"{path1} (Added new file)"
                else:
                    display = path1
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, file_stats.get(path1))
                item.setData(FILE_ENTRY_ROLE, entry)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.filewise_file_list.addItem(item)
            self.filewise_file_list.blockSignals(False)

            # Also populate the tree-wise tab
            self._populate_treewise_tree(file_entries, file_stats)

            self._update_filewise_counter()

            # Refresh the active diff pane to show checked files
            tab_idx = self.diff_tab_widget.currentIndex()
            if tab_idx == 1:
                self._refresh_filewise_diff()
            elif tab_idx == 2:
                self._refresh_treewise_diff()
        except Exception as e:
            self.side_diff_view.setPlainText(f"Error loading diff: {e}")
            if hasattr(self, 'side_commit_msg'):
                self.side_commit_msg.clear()
                self.side_commit_label.setText("Error")
            if hasattr(self, 'filewise_diff_view'):
                self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def on_diff_tab_changed(self, index):
        self.settings.setValue(self._sk("diff_tab_index"), index)
        if index == 0:
            # Load plain diff if not cached yet
            item = self.list_widget.currentItem()
            if item and item.data(Qt.UserRole + 9) != "load_more":
                sha = item.text().split()[0]
                cache_entry = self.commit_cache.get(sha, {})
                if 'diff' not in cache_entry:
                    try:
                        if self.browse_file:
                            cache_entry['diff'] = get_file_diff_only_in_commit(
                                self.repo_path, sha, self.browse_file)
                        else:
                            cache_entry['diff'] = get_commit_diff(self.repo_path, sha)
                        self.commit_cache[sha] = cache_entry
                    except Exception:
                        pass
                if 'diff' in cache_entry:
                    self.side_diff_view.setPlainText(cache_entry['diff'])
                    self.side_diff_view.set_separator_color(self.current_theme_colors.get("separator", "#444444"))
                    if self.plain_diff_search.isVisible():
                        self.plain_diff_search._perform_search()
        elif index == 1:
            self._refresh_filewise_diff()
        elif index == 2:
            self._refresh_treewise_diff()

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
        head_sha = self.get_head_sha()
        is_head = bool(commit_sha) and (commit_sha == head_sha or head_sha.startswith(commit_sha))
        add_open_with_system_default_action(menu, target_path, self, sha=commit_sha, is_head=is_head)
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=target_path: open_blame_window(self, text, branch=commit_sha))
        menu.addAction(blame_action)

        if commit_sha:
            diff_ref_action = QAction("Diff against a different version of this file", self)
            diff_ref_action.triggered.connect(lambda checked=False, text=target_path, sha=commit_sha: self.handle_diff_file_at_ref(text, sha))
            menu.addAction(diff_ref_action)

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

    def _get_file_diff(self, filepath):
        """Get diff for a single file in the current commit."""
        list_item = self.list_widget.currentItem()
        if not list_item:
            return ""
        sha = list_item.text().split()[0]
        try:
            item = None
            for i in range(self.filewise_file_list.count()):
                li = self.filewise_file_list.item(i)
                if li.text() == filepath:
                    item = li
                    break
            entry = item.data(FILE_ENTRY_ROLE) if item else None
            if entry and entry[0] == 'R':
                return get_rename_diff_in_commit(self.repo_path, sha, entry[1], entry[2])
            elif entry:
                return get_file_diff_only_in_commit(self.repo_path, sha, entry[1])
            else:
                return get_file_diff_only_in_commit(self.repo_path, sha, filepath)
        except Exception as e:
            return f"Error loading diff: {e}"

    def _on_filewise_item_changed(self, item):
        """Handle checkbox change in filewise list: sync to tree and refresh diff."""
        checked = item.checkState() == Qt.Checked
        filepath = item.text()
        for i in range(self.treewise_tree.topLevelItemCount()):
            self._sync_file_to_tree(self.treewise_tree.topLevelItem(i), filepath, checked)
        self._update_filewise_counter()
        self._refresh_filewise_diff()
        self._refresh_treewise_diff()

    def _sync_file_to_tree(self, parent_item, filepath, checked):
        """Recursively find and sync a file's check state in the tree."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child_data = child.data(0, Qt.UserRole + 10)
            if not child_data:
                continue
            if child_data["type"] == "folder":
                self._sync_file_to_tree(child, filepath, checked)
            elif child_data.get("entry"):
                entry = child_data["entry"]
                child_path = entry[2] if entry[0] == 'R' else entry[1]
                if child_path == filepath:
                    self.treewise_tree.blockSignals(True)
                    child.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                    self.treewise_tree.blockSignals(False)
                    parent = child.parent()
                    if parent:
                        self._update_folder_check_state(parent)
                    return

    def _on_treewise_item_changed(self, item, column):
        """Handle checkbox change in tree: sync to file list and refresh diff."""
        item_data = item.data(0, Qt.UserRole + 10)
        if not item_data:
            return
        checked = item.checkState(0) == Qt.Checked
        if item_data["type"] == "folder":
            self._set_tree_children_checked(item, checked)
        else:
            entry = item_data.get("entry")
            if entry:
                filepath = entry[2] if entry[0] == 'R' else entry[1]
                for i in range(self.filewise_file_list.count()):
                    list_item = self.filewise_file_list.item(i)
                    if list_item.text() == filepath:
                        self.filewise_file_list.blockSignals(True)
                        list_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                        self.filewise_file_list.blockSignals(False)
                        break
            parent = item.parent()
            if parent:
                self._update_folder_check_state(parent)
        self._update_filewise_counter()
        self._refresh_treewise_diff()
        self._refresh_filewise_diff()

    def _set_tree_children_checked(self, item, checked):
        """Recursively set check state for all children."""
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
            child_data = child.data(0, Qt.UserRole + 10)
            if child_data and child_data["type"] == "folder":
                self._set_tree_children_checked(child, checked)

    def _update_folder_check_state(self, folder_item):
        """Update folder checkbox based on children check states."""
        if folder_item.childCount() == 0:
            return
        all_checked = True
        has_checked = False
        for i in range(folder_item.childCount()):
            child = folder_item.child(i)
            child_data = child.data(0, Qt.UserRole + 10)
            if child_data and child_data["type"] == "folder":
                self._update_folder_check_state(child)
                if child.checkState(0) == Qt.Checked:
                    has_checked = True
                else:
                    all_checked = False
            else:
                if child.checkState(0) == Qt.Checked:
                    has_checked = True
                else:
                    all_checked = False
        self.treewise_tree.blockSignals(True)
        if all_checked:
            folder_item.setCheckState(0, Qt.Checked)
        elif has_checked:
            folder_item.setCheckState(0, Qt.PartiallyChecked)
        else:
            folder_item.setCheckState(0, Qt.Unchecked)
        self.treewise_tree.blockSignals(False)
        parent = folder_item.parent()
        if parent:
            self._update_folder_check_state(parent)

    def _update_filewise_counter(self):
        """Update the counter label showing checked/total files."""
        checked = self._checked_filewise_files()
        total = self.filewise_file_list.count()
        self.filewise_counter_label.setText(
            f"<b>{len(checked)}</b> / {total} files selected"
        )

    def _checked_filewise_files(self):
        """Return list of checked file paths in the filewise list."""
        return [self.filewise_file_list.item(i).text()
                for i in range(self.filewise_file_list.count())
                if self.filewise_file_list.item(i).checkState() == Qt.Checked]

    def _set_all_filewise(self, state):
        """Select/deselect all files in filewise list + tree."""
        self.filewise_file_list.blockSignals(True)
        for i in range(self.filewise_file_list.count()):
            self.filewise_file_list.item(i).setCheckState(Qt.Checked if state else Qt.Unchecked)
        self.filewise_file_list.blockSignals(False)
        self.treewise_tree.blockSignals(True)
        for i in range(self.treewise_tree.topLevelItemCount()):
            item = self.treewise_tree.topLevelItem(i)
            item.setCheckState(0, Qt.Checked if state else Qt.Unchecked)
            self._set_tree_children_checked(item, state)
        self.treewise_tree.blockSignals(False)
        self._update_filewise_counter()
        self._refresh_filewise_diff()
        self._refresh_treewise_diff()

    def _refresh_filewise_diff(self):
        """Show combined diff of all checked files in the filewise diff pane."""
        checked = self._checked_filewise_files()
        if not checked:
            self.filewise_diff_view.clear()
            return
        try:
            parts = []
            for f in checked:
                d = self._get_file_diff(f).rstrip("\n")
                if d:
                    parts.append(d)
            text = "\n\n".join(parts) + ("\n" if parts else "")
            self.filewise_diff_view.setPlainText(text)
            self.filewise_diff_view.set_separator_color(self.current_theme_colors.get("separator", "#444444"))
            self.filewise_diff_search._perform_search()
        except Exception as e:
            self.filewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def _refresh_treewise_diff(self):
        """Show combined diff of all checked tree items."""
        checked = self._checked_treewise_files()
        if not checked:
            self.treewise_diff_view.clear()
            return
        try:
            parts = []
            for f in checked:
                d = self._get_file_diff(f).rstrip("\n")
                if d:
                    parts.append(d)
            text = "\n\n".join(parts) + ("\n" if parts else "")
            self.treewise_diff_view.setPlainText(text)
            self.treewise_diff_view.set_separator_color(self.current_theme_colors.get("separator", "#444444"))
            self.treewise_diff_search._perform_search()
        except Exception as e:
            self.treewise_diff_view.setPlainText(f"Error loading diff: {e}")

    def _checked_treewise_files(self):
        """Return list of checked file paths from the tree widget."""
        files = []
        self._collect_checked_tree_files(self.treewise_tree.invisibleRootItem(), files)
        return files

    def _collect_checked_tree_files(self, parent_item, files):
        """Recursively collect checked file paths from tree."""
        for i in range(parent_item.childCount()):
            item = parent_item.child(i)
            if item.checkState(0) != Qt.Checked:
                continue
            item_data = item.data(0, Qt.UserRole + 10)
            if not item_data:
                continue
            if item_data["type"] == "folder":
                self._collect_checked_tree_files(item, files)
            else:
                entry = item_data.get("entry")
                if entry:
                    filepath = entry[2] if entry[0] == 'R' else entry[1]
                    if filepath and filepath not in files:
                        files.append(filepath)

    def _populate_treewise_tree(self, file_entries, file_stats):
        """Build and display the tree-wise file tree from commit file entries."""
        self.treewise_tree.blockSignals(True)
        self.treewise_tree.clear()

        if not file_entries:
            self.treewise_tree.blockSignals(False)
            return

        tree = build_file_tree(file_entries, file_stats)
        self._add_tree_children(None, tree["children"])
        self.treewise_tree.blockSignals(False)

        # Expand top-level items
        for i in range(self.treewise_tree.topLevelItemCount()):
            self.treewise_tree.topLevelItem(i).setExpanded(True)

    def _set_stats_column(self, item, added, deleted, added_color, removed_color):
        """Set colored stats text in column 1 of a tree widget item."""
        stats_parts = []
        if added:
            stats_parts.append(f"+{added}")
        if deleted:
            stats_parts.append(f"-{deleted}")
        item.setText(1, " / ".join(stats_parts))
        item.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)

    def _add_tree_children(self, parent_item, children_dict):
        """Recursively add folder/file nodes to the QTreeWidget."""
        # Sort: folders first, then files, alphabetically within each group
        folders = sorted(((k, v) for k, v in children_dict.items() if v["children"]),
                         key=lambda x: x[0].lower())
        files = sorted(((k, v) for k, v in children_dict.items() if not v["children"]),
                       key=lambda x: x[0].lower())

        added_color = self.current_theme_colors.get("added", "#22863a") if hasattr(self, 'current_theme_colors') else "#22863a"
        removed_color = self.current_theme_colors.get("removed", "#cb2431") if hasattr(self, 'current_theme_colors') else "#cb2431"

        for name, node in folders + files:
            item = QTreeWidgetItem()

            if node["children"]:
                # Folder node
                item.setText(0, f"\U0001f4c1 {name}")
                item.setData(0, Qt.UserRole + 10, {"type": "folder", "node": node})
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Unchecked)
                if node["added"] or node["deleted"]:
                    self._set_stats_column(item, node['added'], node['deleted'], added_color, removed_color)
                if parent_item:
                    parent_item.addChild(item)
                else:
                    self.treewise_tree.addTopLevelItem(item)
                self._add_tree_children(item, node["children"])
            else:
                # File node
                entry = node["entries"][0] if node["entries"] else None
                status = entry[0] if entry else ''
                if status == 'R':
                    display = f"{entry[1]} => {entry[2]}"
                elif status == 'D':
                    display = f"{name} (Deleted)"
                elif status == 'A':
                    display = f"{name} (Added new file)"
                else:
                    display = name
                item.setText(0, display)
                item.setData(0, Qt.UserRole + 10, {"type": "file", "entry": entry})
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Unchecked)
                if node["added"] or node["deleted"]:
                    self._set_stats_column(item, node['added'], node['deleted'], added_color, removed_color)
                if parent_item:
                    parent_item.addChild(item)
                else:
                    self.treewise_tree.addTopLevelItem(item)

    def _collect_folder_diffs(self, node, sha, diffs):
        """Recursively collect diffs for all leaf files under a folder node."""
        for child in node["children"].values():
            if child["children"]:
                self._collect_folder_diffs(child, sha, diffs)
            else:
                for entry in child["entries"]:
                    try:
                        if entry[0] == 'R':
                            diffs.append(get_rename_diff_in_commit(self.repo_path, sha, entry[1], entry[2]))
                        else:
                            diffs.append(get_file_diff_only_in_commit(self.repo_path, sha, entry[1]))
                    except Exception:
                        pass

    def show_treewise_context_menu(self, pos):
        """Context menu for tree-wise file items — reuses the file-wise context menu."""
        item = self.treewise_tree.itemAt(pos)
        if not item:
            return
        item_data = item.data(0, Qt.UserRole + 10)
        if not item_data or item_data["type"] != "file":
            return
        entry = item_data.get("entry")
        target_path = entry[2] if entry and entry[0] == 'R' else (entry[1] if entry else "")
        if not target_path:
            return

        list_item = self.list_widget.currentItem()
        if not list_item:
            return
        commit_sha = list_item.text().split()[0]

        menu = QMenu(self)
        head_sha = self.get_head_sha()
        is_head = bool(commit_sha) and (commit_sha == head_sha or head_sha.startswith(commit_sha))
        add_open_with_system_default_action(menu, target_path, self, sha=commit_sha, is_head=is_head)
        blame_action = QAction("Blame file", self)
        blame_action.triggered.connect(lambda checked=False, text=target_path: open_blame_window(self, text, branch=commit_sha))
        menu.addAction(blame_action)

        if commit_sha:
            diff_ref_action = QAction("Diff against a different version of this file", self)
            diff_ref_action.triggered.connect(lambda checked=False, text=target_path, sha=commit_sha: self.handle_diff_file_at_ref(text, sha))
            menu.addAction(diff_ref_action)

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

        menu.exec(self.treewise_tree.mapToGlobal(pos))

    def handle_slash_shortcut(self):
        """Focus search bar when / is pressed."""
        if not self.search_edit.hasFocus():
            self.search_edit.setFocus()
            self.search_edit.selectAll()

    def handle_esc_shortcut(self):
        """Clear filter and focus when Esc is pressed."""
        # 0. Exit multi-select mode if active
        if getattr(self, 'multi_select_mode', False):
            self.exit_multi_select_mode()
            return

        # 1. Try to clear plain diff search if active and has content/focus
        if self.diff_tab_widget.currentIndex() == 0 and (self.plain_diff_search.search_input.text() or self.plain_diff_search.search_input.hasFocus()):
            self.plain_diff_search.escape_pressed()
            return

        # 2. Try to clear filewise diff search if active and has content/focus
        if self.diff_tab_widget.currentIndex() == 1 and hasattr(self, 'filewise_diff_search') and (self.filewise_diff_search.search_input.text() or self.filewise_diff_search.search_input.hasFocus()):
            self.filewise_diff_search.escape_pressed()
            return

        # 2b. Try to clear treewise diff search if active and has content/focus
        if self.diff_tab_widget.currentIndex() == 2 and hasattr(self, 'treewise_diff_search') and (self.treewise_diff_search.search_input.text() or self.treewise_diff_search.search_input.hasFocus()):
            self.treewise_diff_search.escape_pressed()
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
