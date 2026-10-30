import unittest
import sys
import os
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Import lib.app_window first, matching the app's import order: importing
# lib.git_helpers first hits a package-init cycle (git_helpers -> core ->
# app_window.helpers -> app_window.__init__ -> init_mixin -> git_helpers).
import lib.app_window.helpers  # noqa: F401
from lib.git_helpers import (
    STATUS_CLEAN,
    STATUS_POINTER,
    amend_with_head,
    bulk_commit_all,
    commit_submodule_pointers,
    discard_submodule_changes,
    get_unstaged_files,
    list_submodules,
    stage_submodule_pointers,
)


def _git(cwd, *args):
    return subprocess.run(["git"] + list(args), cwd=cwd, check=True,
                          capture_output=True, text=True)


class SubmoduleRepoFixture(unittest.TestCase):
    """Builds a superproject 'main' with a real submodule 'vendor/libfoo'
    recorded at libfoo's v2 commit, plus a pointer change (submodule checked
    out at v1) and a modified regular file f.txt."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sub = os.path.join(self.tmp, "libfoo")
        self.repo = os.path.join(self.tmp, "main")

        os.makedirs(self.sub)
        _git(self.sub, "init", "-q")
        _git(self.sub, "config", "user.email", "t@t.com")
        _git(self.sub, "config", "user.name", "t")
        with open(os.path.join(self.sub, "ver.txt"), "w") as f:
            f.write("v1\n")
        _git(self.sub, "add", ".")
        _git(self.sub, "commit", "-qm", "v1")
        self.sha_v1 = _git(self.sub, "rev-parse", "HEAD").stdout.strip()
        with open(os.path.join(self.sub, "ver.txt"), "w") as f:
            f.write("v2\n")
        _git(self.sub, "commit", "-qam", "v2")
        self.sha_v2 = _git(self.sub, "rev-parse", "HEAD").stdout.strip()

        os.makedirs(self.repo)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t.com")
        _git(self.repo, "config", "user.name", "t")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("base\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "base")
        # protocol.file.allow keeps this working on git >= 2.38 as well.
        _git(self.repo, "-c", "protocol.file.allow=always",
             "submodule", "add", "-q", self.sub, "vendor/libfoo")
        _git(self.repo, "commit", "-qm", "add submodule")
        # Pointer change: check out the older commit inside the submodule
        # worktree (the superproject's clone, not the source repo).
        _git(os.path.join(self.repo, "vendor", "libfoo"), "checkout", "-q", self.sha_v1)
        # Regular file change alongside it.
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("modified\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _gitlink(self, ref="HEAD"):
        out = _git(self.repo, "ls-tree", ref, "vendor/libfoo").stdout
        # "160000 commit <sha>\tvendor/libfoo"
        return out.split()[2]

    def _staged_gitlink(self):
        out = _git(self.repo, "ls-files", "-s", "--", "vendor/libfoo").stdout
        # "160000 <sha> 0\tvendor/libfoo"
        return out.split()[1]

    def _file_content_at(self, ref, path="f.txt"):
        return _git(self.repo, "show", f"{ref}:{path}").stdout


class TestUnstagedFlowsExcludeSubmodules(SubmoduleRepoFixture):

    def test_get_unstaged_files_excludes_submodule(self):
        files = get_unstaged_files(self.repo, ignore_submodules=True)
        self.assertEqual(files, ["f.txt"])

    def test_bulk_commit_excludes_submodule_pointer(self):
        files = get_unstaged_files(self.repo, ignore_submodules=True)
        ok, detail = bulk_commit_all(self.repo, "bulk changes", files)
        self.assertTrue(ok, detail)
        # The regular file change was committed...
        self.assertIn("modified", self._file_content_at("HEAD"))
        # ...but the submodule pointer still records v2, not the bumped v1.
        self.assertEqual(self._gitlink("HEAD"), self.sha_v2)
        committed = _git(self.repo, "show", "--name-only",
                         "--format=", "HEAD").stdout.split()
        self.assertEqual(committed, ["f.txt"])

    def test_bulk_commit_empty_list_is_safe(self):
        ok, detail = bulk_commit_all(self.repo, "nothing", [])
        self.assertFalse(ok)
        self.assertIn("No files", detail)

    def test_amend_excludes_submodule_pointer(self):
        files = get_unstaged_files(self.repo, ignore_submodules=True)
        old_head = _git(self.repo, "rev-parse", "HEAD").stdout.strip()
        ok, detail = amend_with_head(self.repo, files)
        self.assertTrue(ok, detail)
        new_head = _git(self.repo, "rev-parse", "HEAD").stdout.strip()
        self.assertNotEqual(new_head, old_head)
        # HEAD now has the file change but still records the v2 gitlink.
        self.assertIn("modified", self._file_content_at("HEAD"))
        self.assertEqual(self._gitlink("HEAD"), self.sha_v2)

    def test_amend_empty_list_is_safe(self):
        ok, detail = amend_with_head(self.repo, [])
        self.assertFalse(ok)
        self.assertIn("No files", detail)


class TestSubmoduleHelpers(SubmoduleRepoFixture):

    def test_list_submodules_reports_pointer_change(self):
        subs = list_submodules(self.repo)
        self.assertEqual(len(subs), 1)
        sub = subs[0]
        self.assertEqual(sub["path"], "vendor/libfoo")
        self.assertEqual(sub["status"], STATUS_POINTER)
        self.assertEqual(sub["record_sha"], self.sha_v2)
        self.assertEqual(sub["current_sha"], self.sha_v1)

    def test_stage_and_commit_pointer(self):
        ok, detail = stage_submodule_pointers(self.repo, ["vendor/libfoo"])
        self.assertTrue(ok, detail)
        self.assertEqual(self._gitlink("HEAD"), self.sha_v2)
        self.assertEqual(self._staged_gitlink(), self.sha_v1)  # staged in index

        ok, detail = commit_submodule_pointers(
            self.repo, ["vendor/libfoo"], "bump libfoo to v1")
        self.assertTrue(ok, detail)
        self.assertEqual(self._gitlink("HEAD"), self.sha_v1)
        self.assertEqual(list_submodules(self.repo)[0]["status"], STATUS_CLEAN)

    def test_commit_pointer_without_staging(self):
        ok, detail = commit_submodule_pointers(
            self.repo, ["vendor/libfoo"], "bump libfoo to v1")
        self.assertTrue(ok, detail)
        self.assertEqual(self._gitlink("HEAD"), self.sha_v1)

    def test_discard_pointer_change(self):
        ok, detail = discard_submodule_changes(self.repo, ["vendor/libfoo"])
        self.assertTrue(ok, detail)
        sub = list_submodules(self.repo)[0]
        self.assertEqual(sub["status"], STATUS_CLEAN)
        self.assertEqual(sub["current_sha"], self.sha_v2)


class TestEmbeddedRepo(unittest.TestCase):
    """A gitlink added via plain `git add` (no `git submodule add`, no
    .gitmodules mapping) — `git submodule status` fatals on these, but they
    must still be listed and manageable."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "main")
        os.makedirs(self.repo)
        self.nested = os.path.join(self.repo, "nested")

        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t.com")
        _git(self.repo, "config", "user.name", "t")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("base\n")
        _git(self.repo, "add", "f.txt")
        _git(self.repo, "commit", "-qm", "base")

        os.makedirs(self.nested)
        _git(self.nested, "init", "-q")
        _git(self.nested, "config", "user.email", "t@t.com")
        _git(self.nested, "config", "user.name", "t")
        with open(os.path.join(self.nested, "a.txt"), "w") as f:
            f.write("v1\n")
        _git(self.nested, "add", ".")
        _git(self.nested, "commit", "-qm", "v1")
        self.sha_v1 = _git(self.nested, "rev-parse", "HEAD").stdout.strip()
        with open(os.path.join(self.nested, "a.txt"), "w") as f:
            f.write("v2\n")
        _git(self.nested, "commit", "-qam", "v2")
        self.sha_v2 = _git(self.nested, "rev-parse", "HEAD").stdout.strip()

        # Plain `git add` of a nested repo creates a gitlink with NO
        # .gitmodules entry (the "embedded repository" case).
        _git(self.repo, "add", "nested")
        _git(self.repo, "commit", "-qm", "add nested repo")
        # Pointer change: check out the older commit inside the nested repo.
        _git(self.nested, "checkout", "-q", self.sha_v1)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _gitlink(self, ref="HEAD"):
        out = _git(self.repo, "ls-tree", ref, "nested").stdout
        return out.split()[2]

    def test_git_submodule_status_fatals_but_list_still_works(self):
        # Sanity: confirm the raw command really fails in this scenario.
        with self.assertRaises(subprocess.CalledProcessError):
            _git(self.repo, "submodule", "status")
        subs = list_submodules(self.repo)
        self.assertEqual(len(subs), 1)
        sub = subs[0]
        self.assertEqual(sub["path"], "nested")
        self.assertTrue(sub["embedded"])
        self.assertEqual(sub["status"], STATUS_POINTER)
        self.assertEqual(sub["record_sha"], self.sha_v2)
        self.assertEqual(sub["current_sha"], self.sha_v1)

    def test_excluded_from_unstaged_flows(self):
        files = get_unstaged_files(self.repo, ignore_submodules=True)
        self.assertEqual(files, [])
        ok, detail = bulk_commit_all(self.repo, "nothing", files)
        self.assertFalse(ok)

    def test_stage_and_commit_pointer(self):
        ok, detail = stage_submodule_pointers(self.repo, ["nested"])
        self.assertTrue(ok, detail)
        ok, detail = commit_submodule_pointers(self.repo, ["nested"], "bump nested to v1")
        self.assertTrue(ok, detail)
        self.assertEqual(self._gitlink("HEAD"), self.sha_v1)
        sub = list_submodules(self.repo)[0]
        self.assertEqual(sub["status"], STATUS_CLEAN)
        self.assertTrue(sub["embedded"])

    def test_discard_falls_back_to_nested_checkout(self):
        ok, detail = discard_submodule_changes(self.repo, ["nested"])
        self.assertTrue(ok, detail)
        sub = list_submodules(self.repo)[0]
        self.assertEqual(sub["status"], STATUS_CLEAN)
        self.assertEqual(sub["current_sha"], self.sha_v2)


if __name__ == "__main__":
    unittest.main()
