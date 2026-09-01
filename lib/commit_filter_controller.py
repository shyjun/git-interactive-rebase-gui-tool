import re
import subprocess
import threading

from PySide6.QtCore import QMetaObject, QObject, Qt, QTimer, Slot
from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit, QListWidget, QWidget


class CommitFilterController(QObject):
    """Owns the commit-list search/filter logic.  Operates on plain Python data
    and injected Qt widget references so the caller (GitInteractiveRebaseApp)
    is decoupled from the filtering details."""

    def __init__(self, parent, list_widget, commit_cache, repo_path,
                 search_edit, filter_by_files_cb, filter_by_diff_cb,
                 filter_by_author_cb, diff_status_label,
                 showing_commits_label, sep_merge, merge_commits_label,
                 MATCH_ROLE, diff_search_matches_func,
                 get_commit_files_with_status_func,
                 get_commit_diff_func,
                 settings, sk_func):
        super().__init__(parent)
        self._list_widget = list_widget
        self._commit_cache = commit_cache
        self._repo_path = repo_path
        self._search_edit = search_edit
        self._filter_by_files_cb = filter_by_files_cb
        self._filter_by_diff_cb = filter_by_diff_cb
        self._filter_by_author_cb = filter_by_author_cb
        self._diff_status_label = diff_status_label
        self._showing_commits_label = showing_commits_label
        self._sep_merge = sep_merge
        self._merge_commits_label = merge_commits_label
        self._MATCH_ROLE = MATCH_ROLE
        self._diff_search_matches = diff_search_matches_func
        self._get_commit_files_with_status = get_commit_files_with_status_func
        self._get_commit_diff = get_commit_diff_func
        self._settings = settings
        self._sk = sk_func

        self.search_match_case = False
        self.search_whole_word = False
        self.search_display_only = False
        self._search_norm_memo = None
        self._diff_search_gen = 0
        self._diff_search_queue = []
        self._DIFF_NEUTRAL_STYLE = "color: gray; font-style: italic; font-size: 10pt;"
        self._DIFF_HINT_STYLE = "color: #d73a49; font-weight: bold; font-size: 10pt;"

        self._diff_search_timer = QTimer(self)
        self._diff_search_timer.setSingleShot(True)
        self._diff_search_timer.setInterval(300)
        self._diff_search_timer.timeout.connect(self._run_filter_with_diff)

        self._diff_status_label.setStyleSheet(self._DIFF_NEUTRAL_STYLE)

    def set_search_options(self, match_case, whole_word, display_only):
        """Set the three search-option flags without triggering a re-filter."""
        self.search_match_case = match_case
        self.search_whole_word = whole_word
        self.search_display_only = display_only

    def filter_commits(self, text):
        """Live-filters commits. Diff search is debounced; msg/filename filtering is instant."""
        self._diff_search_gen += 1
        search_term = self._normalize_search_term(text.strip())
        by_diff = self._filter_by_diff_cb.isChecked()

        self._run_filter_no_diff(search_term)

        if by_diff and len(search_term) >= 3:
            self._diff_status_label.setStyleSheet(self._DIFF_NEUTRAL_STYLE)
            self._diff_status_label.setText("Searching diffs...")
            self._diff_status_label.setVisible(True)
            self._diff_search_timer.start()
        elif by_diff and search_term:
            self._diff_search_timer.stop()
            self._diff_status_label.setStyleSheet(self._DIFF_HINT_STYLE)
            self._diff_status_label.setText("Diff search needs ≥ 3 characters")
            self._diff_status_label.setVisible(True)
        else:
            self._diff_search_timer.stop()
            self._diff_status_label.setVisible(False)

    def _normalize_search_term(self, term):
        """Resolve any 4-40 hex SHA prefix to the exact short form git displays."""
        if self._search_norm_memo is not None and self._search_norm_memo[0] == term:
            return self._search_norm_memo[1]
        normalized = term
        if re.fullmatch(r"[0-9a-fA-F]{4,40}", term):
            try:
                res = subprocess.run(["git", "rev-parse", "--short", term],
                                     cwd=self._repo_path, capture_output=True, text=True,
                                     check=True, encoding='utf-8', errors='replace')
                normalized = res.stdout.strip() or term
            except Exception:
                pass
        self._search_norm_memo = (term, normalized)
        return normalized

    def _search_matches(self, haystack, term):
        return self._diff_search_matches(
            haystack, term, self.search_match_case, self.search_whole_word)

    def _run_filter_no_diff(self, search_term=None):
        """Instant filtering by commit message, filenames, and author."""
        search_term = self._normalize_search_term(
            search_term if search_term is not None else self._search_edit.text().strip())

        by_msg = True
        by_files = self._filter_by_files_cb.isChecked()
        by_diff = self._filter_by_diff_cb.isChecked()
        by_author = self._filter_by_author_cb.isChecked()

        if not search_term or (not by_msg and not by_files and not by_diff and not by_author):
            for i in range(self._list_widget.count()):
                item = self._list_widget.item(i)
                item.setHidden(False)
                item.setData(self._MATCH_ROLE, False)
            self._update_commit_counts()
            self._list_widget.viewport().update()
            return

        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            item_text = item.text()
            sha = item.text().split()[0]

            matched = False

            if by_msg and (self._search_matches(item_text, search_term) or self._search_matches(item.data(Qt.UserRole + 6) or "", search_term)):
                matched = True

            if not matched and by_files:
                cache_entry = self._commit_cache.get(sha, {})
                if 'files' not in cache_entry:
                    try:
                        cache_entry['files'] = self._get_commit_files_with_status(self._repo_path, sha)
                        self._commit_cache[sha] = cache_entry
                    except Exception:
                        cache_entry['files'] = []
                        self._commit_cache[sha] = cache_entry
                file_entries = cache_entry.get('files', [])
                for _status, path1, path2 in file_entries:
                    display = f"{path1} => {path2}" if _status == 'R' else path1
                    if self._search_matches(display, search_term):
                        matched = True
                        break

            if not matched and by_author:
                author = item.data(Qt.UserRole + 4) or ""
                if self._search_matches(author, search_term):
                    matched = True

            if not matched and by_diff and self.search_display_only:
                matched = True

            item.setData(self._MATCH_ROLE, matched)
            if self.search_display_only:
                item.setHidden(not matched)
            else:
                item.setHidden(False)

        self._update_commit_counts()
        self._list_widget.viewport().update()

    def _run_filter_with_diff(self):
        """Debounced diff search."""
        search_term = self._normalize_search_term(self._search_edit.text().strip())
        if len(search_term) < 3 or not self._filter_by_diff_cb.isChecked():
            self._diff_status_label.setVisible(False)
            return

        gen = self._diff_search_gen
        by_msg = True
        by_files = self._filter_by_files_cb.isChecked()
        by_author = self._filter_by_author_cb.isChecked()
        display_only = self.search_display_only
        match_case = self.search_match_case
        whole_word = self.search_whole_word

        snapshot = []
        sha_to_item = {}
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item.isHidden():
                continue
            sha = item.text().split()[0]
            cache_entry = self._commit_cache.get(sha, {})
            snapshot.append({
                "sha": sha,
                "text": item.text(),
                "msg": item.data(Qt.UserRole + 6) or "",
                "author": item.data(Qt.UserRole + 4) or "",
                "files": cache_entry.get('files', []),
                "diff": cache_entry.get('diff'),
            })
            sha_to_item[sha] = i

        repo_path = self._repo_path
        ds_matches = self._diff_search_matches
        get_commit_diff_func = self._get_commit_diff
        queue = self._diff_search_queue

        def worker():
            results = []
            new_diffs = {}
            error = None
            try:
                for entry in snapshot:
                    sha = entry["sha"]
                    already_matched = (by_msg and (
                        ds_matches(entry["text"], search_term, match_case, whole_word)
                        or ds_matches(entry["msg"], search_term, match_case, whole_word)))
                    if not already_matched and by_files:
                        for _status, path1, path2 in entry["files"]:
                            display = f"{path1} => {path2}" if _status == 'R' else path1
                            if ds_matches(display, search_term, match_case, whole_word):
                                already_matched = True
                                break
                    if not already_matched and by_author:
                        already_matched = ds_matches(entry["author"], search_term, match_case, whole_word)

                    if already_matched:
                        results.append({"sha": sha, "match_role": False, "hide": False})
                        continue

                    diff_text = entry["diff"]
                    if diff_text is None:
                        try:
                            diff_text = get_commit_diff_func(repo_path, sha)
                        except Exception:
                            diff_text = ''
                        new_diffs[sha] = diff_text

                    diff_matched = ds_matches(diff_text, search_term, match_case, whole_word)
                    results.append({
                        "sha": sha,
                        "match_role": diff_matched and not display_only,
                        "hide": (not diff_matched) and display_only,
                    })
            except Exception as exc:
                error = exc
            queue.append((gen, results, new_diffs, error, sha_to_item))
            QMetaObject.invokeMethod(self, "_diff_search_finished", Qt.QueuedConnection)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    @Slot()
    def _diff_search_finished(self):
        """Applies an async diff-search result on the GUI thread."""
        while self._diff_search_queue:
            gen, results, new_diffs, error, sha_to_item = self._diff_search_queue.pop(0)

            if new_diffs:
                for sha, diff_text in new_diffs.items():
                    entry = self._commit_cache.setdefault(sha, {})
                    if 'diff' not in entry:
                        entry['diff'] = diff_text

            if gen != self._diff_search_gen:
                continue

            if error is not None:
                print(f"[app_window] diff search failed: {error}")
                self._diff_status_label.setVisible(False)
                return

            display_only = self.search_display_only
            for entry in results:
                idx = sha_to_item.get(entry["sha"])
                if idx is None:
                    continue
                item = self._list_widget.item(idx)
                if entry["hide"]:
                    item.setHidden(True)
                elif entry["match_role"] and not display_only:
                    item.setData(self._MATCH_ROLE, True)

            self._diff_status_label.setVisible(False)
            self._update_commit_counts()
            self._list_widget.viewport().update()

    def _update_commit_counts(self):
        total = self._list_widget.count()
        showing = 0
        merge_showing = 0
        for i in range(total):
            item = self._list_widget.item(i)
            if not item.isHidden():
                # Skip non-commit items like "Load 100 more..."
                if item.data(Qt.UserRole + 9) == "load_more":
                    continue
                showing += 1
                if item.data(Qt.UserRole + 5):
                    merge_showing += 1
        self._showing_commits_label.setText(f"Showing: {showing}")
        has_merges = merge_showing > 0
        self._sep_merge.setVisible(has_merges)
        self._merge_commits_label.setVisible(has_merges)
        if has_merges:
            self._merge_commits_label.setText(f"Merge: {merge_showing}")
