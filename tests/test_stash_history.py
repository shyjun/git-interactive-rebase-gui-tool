import unittest
import sys
import os
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from lib.git_helpers import _parse_stash_records, get_commit_files_with_status


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


class TestStashFilesWithStatus(unittest.TestCase):
    """Verifies that get_commit_files_with_status can list a stash's files by
    diffing against its first parent (plain diff-tree returns nothing for a
    stash, which is a merge commit)."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self._git("init", "-q")
        self._git("config", "user.email", "t@t.com")
        self._git("config", "user.name", "t")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("a\nb\n")
        with open(os.path.join(self.repo, "g.txt"), "w") as f:
            f.write("x\n")
        self._git("add", ".")
        self._git("commit", "-qm", "first")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("a2\nb\n")
        with open(os.path.join(self.repo, "g.txt"), "w") as f:
            f.write("y\n")
        with open(os.path.join(self.repo, "h.txt"), "w") as f:
            f.write("new\n")
        self._git("add", "h.txt")
        self._git("stash", "push", "-qm", "wip both")
        self.stash_sha = self._git("stash", "list", "--format=%H").strip()

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def _git(self, *args):
        return subprocess.check_output(["git"] + list(args), cwd=self.repo,
                                       encoding="utf-8", errors="replace")

    def test_stash_flag_lists_all_changed_files(self):
        entries = get_commit_files_with_status(self.repo, self.stash_sha, stash=True)
        files = sorted(e[1] for e in entries)
        self.assertEqual(files, ["f.txt", "g.txt", "h.txt"])

    def test_stash_flag_includes_added_file(self):
        entries = get_commit_files_with_status(self.repo, self.stash_sha, stash=True)
        added = [e for e in entries if e[0] == 'A']
        self.assertEqual([e[1] for e in added], ["h.txt"])

    def test_without_stash_flag_returns_empty(self):
        # Plain diff-tree cannot see a stash's files (merge commit), which is
        # why the stash flag exists.
        entries = get_commit_files_with_status(self.repo, self.stash_sha)
        self.assertEqual(entries, [])


if __name__ == "__main__":
    unittest.main()