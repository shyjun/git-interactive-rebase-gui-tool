"""Rename stats: `--numstat -z` parsing, UI contract keys, tree lookups.

Covers Group C of the rename-stats work:

- git reports renames in --numstat as abbreviated keys
  (``docs/{same.md => renamed.md}``, ``{docs => guides}/c.md``,
  ``src/{ => lib}/u.py``) that no UI code reads.  Both stat functions now
  parse ``--numstat -z``, where renames are unambiguous NUL-separated
  old/new pairs, and key the dict the way the UI reads it: the
  ``"old => new"`` contract key AND the new path.
- ``build_file_tree`` used to look stats up by the OLD path, so the
  treewise view showed 0/0 for renamed files at all call sites.

The fixture covers all six git abbreviation shapes plus modify/delete/add,
a binary file, a binary rename, and a rename+chmod (mode changes must land
on both rename keys).
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Import lib.app_window first (package-init cycle; see test_remove_file.py).
import lib.app_window.helpers  # noqa: F401
from lib.git_helpers import (
    build_file_tree,
    get_commit_file_stats,
    get_file_stats_between,
)
from lib.git_helpers.commits import get_commit_files_with_status
from lib.git_helpers.core import _parse_numstat_z


def _git(cwd, *args):
    return subprocess.run(["git"] + list(args), cwd=cwd, check=True,
                          capture_output=True, text=True)


def _write(repo, rel, text, binary=False):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if binary else "w"
    with open(path, mode) as f:
        f.write(text)


# (old, new, expected (added, deleted)) for the six git abbreviation shapes
# plus the binary and chmod renames.
RENAMES = [
    # same directory: docs/{same.md => renamed.md}
    ("docs/same.md", "docs/renamed.md", (1, 0)),
    # no common component: full "old => new"
    ("toproot.md", "sub/toproot.md", (0, 0)),
    # common directory component: {docs => guides}/cross.md
    ("docs/cross.md", "guides/cross.md", (0, 0)),
    # shared prefix AND suffix: src/{ => lib}/util.py (single-char change so
    # git's similarity stays above the 50% rename threshold)
    ("src/util.py", "src/lib/util.py", (1, 1)),
    # shared suffix only: {data => store}/report.csv
    ("data/report.csv", "store/report.csv", (0, 0)),
    # deep shared prefix + suffix: a/b/{c => d}/f.txt
    ("a/b/c/f.txt", "a/b/d/f.txt", (1, 0)),
    # rename with a mode change (chmod +x)
    ("chmodme.md", "chmd.md", (0, 0)),
    # binary rename (reported as "-\t-\t")
    ("blob.bin", "blob2.bin", (0, 0)),
]


class RenameStatsFixture(unittest.TestCase):
    """Two-commit repo exercising every rename shape + plain file changes."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "main")
        os.makedirs(self.repo)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t.com")
        _git(self.repo, "config", "user.name", "t")
        # Opt OUT of git's default rename detection so only the explicit -M
        # flags on numstat/raw keep renames paired — proves the stat
        # functions don't silently depend on the caller's git config.
        _git(self.repo, "config", "diff.renames", "false")

        # --- base commit ---
        _write(self.repo, "docs/same.md", "AAA\nBBB\nCCC\n")
        _write(self.repo, "toproot.md", "RRR\nSSS\nTTT\n")
        _write(self.repo, "docs/cross.md", "XXX\nYYY\nZZZ\n")
        _write(self.repo, "src/util.py", "def f():\n    pass\n    return 1\n")
        _write(self.repo, "data/report.csv", "row1\nrow2\nrow3\n")
        _write(self.repo, "a/b/c/f.txt", "DEEP1\nDEEP2\nDEEP3\n")
        _write(self.repo, "chmodme.md", "chmod content\n")
        _write(self.repo, "keep.md", "keep\n")
        _write(self.repo, "todelete.md", "del1\ndel2\n")
        _write(self.repo, "bin.dat",
               b"\x00\x01\x02\x03binary", binary=True)   # 10 bytes
        _write(self.repo, "blob.bin",
               b"\x00\x01\x02\x03BINARYBLOB", binary=True)  # 14 bytes
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "base")
        self.base_sha = _git(self.repo, "rev-parse", "HEAD").stdout.strip()

        # --- rename commit ---
        # content changes (also drive the non-zero rename counts)
        _write(self.repo, "docs/same.md", "AAA\nBBB\nCCC\nDDD\n")
        _write(self.repo, "src/util.py", "def f():\n    pass\n    return 2\n")
        _write(self.repo, "a/b/c/f.txt", "DEEP1\nDEEP2\nDEEP3\nDEEP4\n")
        _write(self.repo, "keep.md", "keep\nmore\n")
        _write(self.repo, "bin.dat", b"\x00\x01\x02\x03\x04binary",
               binary=True)                              # 11 bytes
        # delete + add
        os.remove(os.path.join(self.repo, "todelete.md"))
        _write(self.repo, "added.md", "n1\nn2\nn3\n")
        # renames (destination dirs first)
        for dest in ("sub", "guides", "store", "src/lib", "a/b/d"):
            os.makedirs(os.path.join(self.repo, dest), exist_ok=True)
        _git(self.repo, "mv", "docs/same.md", "docs/renamed.md")
        _git(self.repo, "mv", "toproot.md", "sub/toproot.md")
        _git(self.repo, "mv", "docs/cross.md", "guides/cross.md")
        _git(self.repo, "mv", "src/util.py", "src/lib/util.py")
        _git(self.repo, "mv", "data/report.csv", "store/report.csv")
        _git(self.repo, "mv", "a/b/c/f.txt", "a/b/d/f.txt")
        _git(self.repo, "mv", "chmodme.md", "chmd.md")
        _git(self.repo, "mv", "blob.bin", "blob2.bin")
        os.chmod(os.path.join(self.repo, "chmd.md"), 0o755)
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "renames")
        self.sha = _git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- expected full dict ------------------------------------------------

    def _expected(self):
        expected = {}
        for old, new, counts in RENAMES:
            if (old, new) == ("blob.bin", "blob2.bin"):
                value = (0, 0, 14, 14)
            elif (old, new) == ("chmodme.md", "chmd.md"):
                value = (0, 0, 0, 0, "100644", "100755")
            else:
                value = (counts[0], counts[1], 0, 0)
            expected[f"{old} => {new}"] = value
            expected[new] = value
        expected["keep.md"] = (1, 0, 0, 0)
        expected["todelete.md"] = (0, 2, 0, 0)
        expected["added.md"] = (3, 0, 0, 0)
        expected["bin.dat"] = (0, 0, 10, 11)
        return expected

    # ---- get_commit_file_stats --------------------------------------------

    def test_commit_stats_match_expected_exactly(self):
        """Exact dict: contract keys + new paths, no git-abbreviated keys."""
        stats = get_commit_file_stats(self.repo, self.sha)
        self.assertEqual(stats, self._expected())

    def test_commit_stats_no_git_abbreviated_keys(self):
        """The "dir/{old => new}" keys git prints must not leak into stats."""
        stats = get_commit_file_stats(self.repo, self.sha)
        for key in stats:
            self.assertNotIn("{", key, f"git-abbreviated key leaked: {key!r}")
            self.assertNotIn("}", key, f"git-abbreviated key leaked: {key!r}")

    # ---- get_file_stats_between -------------------------------------------

    def test_file_stats_between_match_expected_exactly(self):
        stats = get_file_stats_between(self.repo, self.base_sha, self.sha)
        self.assertEqual(stats, self._expected())

    # ---- the exact UI lookup (af01cd0 contract) ---------------------------

    def test_ui_lookup_resolves_for_every_commit_entry(self):
        stats = get_commit_file_stats(self.repo, self.sha)
        entries = get_commit_files_with_status(self.repo, self.sha)
        self.assertTrue(entries, "fixture must produce file entries")
        for status, path1, path2 in entries:
            if status == 'R':
                key = f"{path1} => {path2}"
                self.assertIsNotNone(
                    stats.get(key),
                    f"UI lookup {key!r} must resolve for renames",
                )
            else:
                self.assertIsNotNone(
                    stats.get(path1),
                    f"UI lookup {path1!r} must resolve (status {status})",
                )

    # ---- build_file_tree (treewise regression) ----------------------------

    def test_build_file_tree_uses_rename_stats(self):
        stats = get_commit_file_stats(self.repo, self.sha)
        entries = get_commit_files_with_status(self.repo, self.sha)
        tree = build_file_tree(entries, stats)

        # nodes are placed at the NEW path and must carry the rename counts
        renamed = tree["children"]["docs"]["children"]["renamed.md"]
        self.assertEqual((renamed["added"], renamed["deleted"]), (1, 0))

        util = tree["children"]["src"]["children"]["lib"]["children"]["util.py"]
        self.assertEqual((util["added"], util["deleted"]), (1, 1))

        deep = (tree["children"]["a"]["children"]["b"]
                ["children"]["d"]["children"]["f.txt"])
        self.assertEqual((deep["added"], deep["deleted"]), (1, 0))

        # folder totals must include rename contributions (pre-fix: 0)
        self.assertEqual(tree["children"]["docs"]["added"], 1)
        self.assertEqual(tree["children"]["docs"]["deleted"], 0)
        self.assertEqual(tree["children"]["src"]["added"], 1)
        self.assertEqual(tree["children"]["src"]["deleted"], 1)

        # plain files still work
        self.assertEqual(tree["children"]["keep.md"]["added"], 1)
        self.assertEqual(tree["children"]["todelete.md"]["deleted"], 2)
        self.assertEqual(tree["children"]["added.md"]["added"], 3)


class TestNumstatParser(unittest.TestCase):
    """Unit tests for the --numstat -z tokenizer (no git needed)."""

    def test_regular_rename_binary_and_tab_paths(self):
        out = (b"1\t0\tadded.md\0"
               b"-\t-\tbin.dat\0"
               b"2\t1\t\0old.txt\0new.txt\0"
               b"1\t0\twith\ttab.txt\0").decode()
        self.assertEqual(_parse_numstat_z(out), [
            (1, 0, None, "added.md"),
            (None, None, None, "bin.dat"),
            (2, 1, "old.txt", "new.txt"),
            (1, 0, None, "with\ttab.txt"),
        ])

    def test_empty_output(self):
        self.assertEqual(_parse_numstat_z(""), [])

    def test_missing_trailing_nul(self):
        self.assertEqual(_parse_numstat_z("1\t0\ta.md"),
                         [(1, 0, None, "a.md")])
        self.assertEqual(_parse_numstat_z("0\t0\t\0old\0new"),
                         [(0, 0, "old", "new")])

    def test_binary_rename(self):
        self.assertEqual(_parse_numstat_z("-\t-\t\0old.bin\0new.bin\0"),
                         [(None, None, "old.bin", "new.bin")])

    def test_truncated_rename_header_is_ignored(self):
        self.assertEqual(_parse_numstat_z("0\t0\t\0orphan"), [])


if __name__ == "__main__":
    unittest.main()
