import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.git_helpers import _parse_stash_records


class TestParseStashRecords(unittest.TestCase):

    def test_parses_normal_entry(self):
        records = _parse_stash_records("9705acdffbaa2148e4a2462140c7380d474b3b33|stash@{0}|On master: wip feature\n")
        self.assertEqual(len(records), 1)
        entry = records[0]
        self.assertEqual(entry["sha"], "9705acdffbaa2148e4a2462140c7380d474b3b33")
        self.assertEqual(entry["selector"], "stash@{0}")
        self.assertEqual(entry["message"], "On master: wip feature")
        self.assertEqual(entry["raw_text"],
                         "9705acdffbaa2148e4a2462140c7380d474b3b33 stash@{0}: On master: wip feature")

    def test_parses_multiple_entries(self):
        stdout = (
            "9705acdffbaa2148e4a2462140c7380d474b3b33|stash@{0}|On master: wip feature\n"
            "2222222222222222222222222222222222222222|stash@{1}|WIP on fix: 1\n"
            "3333333333333333333333333333333333333333|stash@{2}|WIP on feature: 2\n"
        )
        records = _parse_stash_records(stdout)
        self.assertEqual(len(records), 3)
        self.assertEqual([r["selector"] for r in records],
                         ["stash@{0}", "stash@{1}", "stash@{2}"])

    def test_selector_with_braces_is_kept(self):
        records = _parse_stash_records("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3|stash@{0}|WIP on X\n")
        self.assertEqual(records[0]["selector"], "stash@{0}")
        self.assertTrue(records[0]["raw_text"].startswith("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3 stash@{0}:"))

    def test_subject_containing_colons(self):
        records = _parse_stash_records("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3|stash@{0}|On master: fix: colon: part\n")
        self.assertEqual(records[0]["message"], "On master: fix: colon: part")
        self.assertEqual(records[0]["raw_text"],
                         "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3 stash@{0}: On master: fix: colon: part")

    def test_empty_input(self):
        self.assertEqual(_parse_stash_records(""), [])

    def test_blank_lines_ignored(self):
        stdout = "\n9705acdffbaa2148e4a2462140c7380d474b3b33|stash@{0}|On master: wip feature\n\n"
        records = _parse_stash_records(stdout)
        self.assertEqual(len(records), 1)

    def test_malformed_line_skipped(self):
        stdout = "9705acdffbaa2148e4a2462140c7380d474b3b33|stash@{0}|On master: wip feature\ngarbage-without-pipes\n"
        records = _parse_stash_records(stdout)
        self.assertEqual(len(records), 1)

    def test_sha_is_first_token_for_diff_lookup(self):
        records = _parse_stash_records("9705acdffbaa2148e4a2462140c7380d474b3b33|stash@{0}|On master: wip feature\n")
        sha = records[0]["raw_text"].split()[0]
        self.assertEqual(sha, "9705acdffbaa2148e4a2462140c7380d474b3b33")


if __name__ == "__main__":
    unittest.main()