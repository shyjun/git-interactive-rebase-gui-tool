import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.git_helpers import _parse_reflog_records


class TestParseReflogRecords(unittest.TestCase):

    def test_parses_normal_entry(self):
        records = _parse_reflog_records("c9bbbc4|HEAD@{0}|commit: Fix bug\n")
        self.assertEqual(len(records), 1)
        entry = records[0]
        self.assertEqual(entry["sha"], "c9bbbc4")
        self.assertEqual(entry["selector"], "HEAD@{0}")
        self.assertEqual(entry["message"], "commit: Fix bug")
        self.assertEqual(entry["raw_text"], "c9bbbc4 HEAD@{0}: commit: Fix bug")

    def test_parses_multiple_entries(self):
        stdout = (
            "c9bbbc4|HEAD@{0}|commit: Fix bug\n"
            "fe111ec|HEAD@{1}|reset: moving to HEAD~2\n"
            "5713e66|HEAD@{2}|rebase (finish): returning to refs/heads/master\n"
        )
        records = _parse_reflog_records(stdout)
        self.assertEqual(len(records), 3)
        self.assertEqual([r["selector"] for r in records],
                         ["HEAD@{0}", "HEAD@{1}", "HEAD@{2}"])

    def test_selector_with_braces_is_kept(self):
        records = _parse_reflog_records("a1b2c3d|HEAD@{0}|commit: X\n")
        self.assertEqual(records[0]["selector"], "HEAD@{0}")
        self.assertTrue(records[0]["raw_text"].startswith("a1b2c3d HEAD@{0}:"))

    def test_subject_containing_colons(self):
        records = _parse_reflog_records("a1b2c3d|HEAD@{0}|commit: add: feature: part 1\n")
        self.assertEqual(records[0]["message"], "commit: add: feature: part 1")
        self.assertEqual(records[0]["raw_text"], "a1b2c3d HEAD@{0}: commit: add: feature: part 1")

    def test_empty_input(self):
        self.assertEqual(_parse_reflog_records(""), [])

    def test_blank_lines_ignored(self):
        stdout = "\nc9bbbc4|HEAD@{0}|commit: Fix bug\n\n"
        records = _parse_reflog_records(stdout)
        self.assertEqual(len(records), 1)

    def test_malformed_line_skipped(self):
        stdout = "c9bbbc4|HEAD@{0}|commit: Fix bug\ngarbage-without-pipes\n"
        records = _parse_reflog_records(stdout)
        self.assertEqual(len(records), 1)

    def test_sha_is_first_token_for_diff_lookup(self):
        records = _parse_reflog_records("c9bbbc4|HEAD@{0}|commit: Fix bug\n")
        sha = records[0]["raw_text"].split()[0]
        self.assertEqual(sha, "c9bbbc4")


if __name__ == "__main__":
    unittest.main()