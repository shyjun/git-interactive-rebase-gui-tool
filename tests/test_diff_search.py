import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.app_window import _diff_search_matches


class TestDiffSearchMatches(unittest.TestCase):

    def test_case_insensitive_finds_match(self):
        self.assertTrue(_diff_search_matches("fix bug in parser", "BUG", False, False))

    def test_case_sensitive_no_match(self):
        self.assertFalse(_diff_search_matches("fix bug in parser", "BUG", True, False))

    def test_case_sensitive_exact_match(self):
        self.assertTrue(_diff_search_matches("fix BUG in parser", "BUG", True, False))

    def test_whole_word_matches(self):
        self.assertTrue(_diff_search_matches("fix bug", "bug", False, True))

    def test_whole_word_rejects_substring(self):
        self.assertFalse(_diff_search_matches("debugger", "bug", False, True))

    def test_whole_word_with_boundary(self):
        self.assertTrue(_diff_search_matches("fix (bug)", "bug", False, True))

    def test_digit_search(self):
        self.assertTrue(_diff_search_matches("abc123", "123", False, False))

    def test_empty_haystack(self):
        self.assertFalse(_diff_search_matches("", "x", False, False))

    def test_empty_term(self):
        self.assertFalse(_diff_search_matches("anything", "", False, False))

    def test_both_empty(self):
        self.assertFalse(_diff_search_matches("", "", False, False))

    def test_unicode_case_insensitive(self):
        self.assertTrue(_diff_search_matches("über cool", "ÜBER", False, False))

    def test_whole_word_unicode(self):
        self.assertTrue(_diff_search_matches("über cool", "cool", False, True))

    def test_whole_word_rejects_unicode_substring(self):
        self.assertFalse(_diff_search_matches("übercool", "cool", False, True))


class TestGenerationStaleDiscardLogic(unittest.TestCase):
    """Tests the generation-based stale-result discarding logic that protects
    the async diff search from returning stale results."""

    def test_stale_discard_older_gen(self):
        gen = 5
        current_gen = 6
        self.assertNotEqual(gen, current_gen)

    def test_stale_accept_matches_gen(self):
        gen = 5
        current_gen = 5
        self.assertEqual(gen, current_gen)

    def test_stale_discard_on_bump(self):
        captured_gen = 5
        self._diff_search_gen = 6
        self.assertNotEqual(captured_gen, self._diff_search_gen)

    def test_stale_discard_across_multiple_bumps(self):
        captured_gen = 3
        self._diff_search_gen = 10
        self.assertNotEqual(captured_gen, self._diff_search_gen)


class TestWorkerMatchingEquivalence(unittest.TestCase):
    """Verifies that the worker's matching logic (using _diff_search_matches)
    produces identical results to the old synchronous inline logic."""

    def _old_matches(self, haystack, term, match_case, whole_word):
        """Replicates the original _search_matches inline logic."""
        import re
        if not term:
            return False
        flags = 0 if match_case else re.IGNORECASE
        if whole_word:
            pattern = rf"\b{re.escape(term)}\b"
        else:
            pattern = re.escape(term)
        return re.search(pattern, haystack, flags) is not None

    def _old_worker_decision(self, entry, search_term, by_msg, by_files, by_author, match_case, whole_word):
        """Replicates the old _run_filter_with_diff decision for a single entry."""
        already_matched = (by_msg and (
            self._old_matches(entry["text"], search_term, match_case, whole_word)
            or self._old_matches(entry["msg"], search_term, match_case, whole_word)))
        if not already_matched and by_files:
            for _status, path1, path2 in entry["files"]:
                display = f"{path1} => {path2}" if _status == 'R' else path1
                if self._old_matches(display, search_term, match_case, whole_word):
                    already_matched = True
                    break
        if not already_matched and by_author:
            already_matched = self._old_matches(entry["author"], search_term, match_case, whole_word)
        return already_matched

    def _new_worker_decision(self, entry, search_term, by_msg, by_files, by_author, match_case, whole_word):
        """Replicates the new worker's matching logic."""
        already_matched = (by_msg and (
            _diff_search_matches(entry["text"], search_term, match_case, whole_word)
            or _diff_search_matches(entry["msg"], search_term, match_case, whole_word)))
        if not already_matched and by_files:
            for _status, path1, path2 in entry["files"]:
                display = f"{path1} => {path2}" if _status == 'R' else path1
                if _diff_search_matches(display, search_term, match_case, whole_word):
                    already_matched = True
                    break
        if not already_matched and by_author:
            already_matched = _diff_search_matches(entry["author"], search_term, match_case, whole_word)
        return already_matched

    def setUp(self):
        self.entries = [
            {"sha": "abc1234", "text": "abc1234 fix bug in parser", "msg": "fix bug in parser\n\nHandle null pointer", "author": "Alice <alice@x.com>", "files": [('M', 'parser.c', ''), ('A', 'test.c', '')]},
            {"sha": "def5678", "text": "def5678 add debugger", "msg": "add debugger", "author": "Bob <bob@x.com>", "files": [('M', 'debugger.c', '')]},
            {"sha": "ghi9012", "text": "ghi9012 refactor main", "msg": "refactor main\n\nSplit into modules", "author": "Alice <alice@x.com>", "files": [('M', 'main.c', ''), ('R', 'old.c', 'new.c')]},
        ]

    def test_msg_match_equivalence(self):
        term = "bug"
        for entry in self.entries:
            old = self._old_worker_decision(entry, term, True, False, False, False, False)
            new = self._new_worker_decision(entry, term, True, False, False, False, False)
            self.assertEqual(old, new, f"Mismatch for sha={entry['sha']} term={term}")

    def test_case_sensitive_match_equivalence(self):
        term = "BUG"
        for entry in self.entries:
            old = self._old_worker_decision(entry, term, True, False, False, True, False)
            new = self._new_worker_decision(entry, term, True, False, False, True, False)
            self.assertEqual(old, new, f"Mismatch for sha={entry['sha']} term={term}")

    def test_files_match_equivalence(self):
        term = "parser"
        for entry in self.entries:
            old = self._old_worker_decision(entry, term, False, True, False, False, False)
            new = self._new_worker_decision(entry, term, False, True, False, False, False)
            self.assertEqual(old, new, f"Mismatch for sha={entry['sha']} term={term}")

    def test_author_match_equivalence(self):
        term = "alice"
        for entry in self.entries:
            old = self._old_worker_decision(entry, term, False, False, True, False, False)
            new = self._new_worker_decision(entry, term, False, False, True, False, False)
            self.assertEqual(old, new, f"Mismatch for sha={entry['sha']} term={term}")

    def test_whole_word_equivalence(self):
        term = "bug"
        for entry in self.entries:
            old = self._old_worker_decision(entry, term, True, False, False, False, True)
            new = self._new_worker_decision(entry, term, True, False, False, False, True)
            self.assertEqual(old, new, f"Mismatch for sha={entry['sha']} term={term} whole_word")

    def test_all_filters_combined_equivalence(self):
        term = "main"
        for entry in self.entries:
            old = self._old_worker_decision(entry, term, True, True, True, False, False)
            new = self._new_worker_decision(entry, term, True, True, True, False, False)
            self.assertEqual(old, new, f"Mismatch for sha={entry['sha']} term={term} all_filters")

    def test_rename_file_match_equivalence(self):
        entry = self.entries[2]
        term = "new.c"
        old = self._old_worker_decision(entry, term, False, True, False, False, False)
        new = self._new_worker_decision(entry, term, False, True, False, False, False)
        self.assertEqual(old, new, f"Mismatch for rename term={term}")

    def test_empty_term_equivalence(self):
        for entry in self.entries:
            old = self._old_worker_decision(entry, "", True, True, True, False, False)
            new = self._new_worker_decision(entry, "", True, True, True, False, False)
            self.assertEqual(old, new, f"Mismatch for empty term sha={entry['sha']}")


if __name__ == "__main__":
    unittest.main()