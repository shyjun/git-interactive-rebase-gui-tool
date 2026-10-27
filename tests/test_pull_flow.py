import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from lib.app_window import reset_mixin
    from lib.app_window.reset_mixin import ResetMixin
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False


def _git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    )


class _FakeSignal:
    def __init__(self):
        self._slots = []

    def connect(self, fn):
        self._slots.append(fn)

    def emit(self, *args):
        for fn in self._slots:
            fn(*args)


class _FakeGitWorker:
    """Runs the real git command synchronously on start() - the full
    ResetMixin chain (fetch -> conflict check -> pull) exercises real git
    against the scratch repos, without threads."""

    made = []

    def __init__(self, cmd, repo_path):
        self.cmd = list(cmd)
        self.repo_path = repo_path
        self.git_finished = _FakeSignal()
        _FakeGitWorker.made.append(self)

    def start(self):
        r = subprocess.run(self.cmd, cwd=self.repo_path,
                           capture_output=True, text=True)
        self.git_finished.emit(r.returncode == 0, r.stdout, r.stderr)


class _FakeProgressDialog:
    def __init__(self, title, message, parent=None):
        self.title = title

    def exec(self):
        pass

    def close(self):
        pass


class _FakeMessageBox:
    events = []

    @classmethod
    def warning(cls, parent, title, text, *a, **k):
        cls.events.append(("warning", title, text))

    @classmethod
    def information(cls, parent, title, text, *a, **k):
        cls.events.append(("information", title, text))

    @classmethod
    def critical(cls, parent, title, text, *a, **k):
        cls.events.append(("critical", title, text))


class _FakePullDialog:
    """Scripted stand-in for PullDialog; carries the real option ids."""
    OPTION_FETCH = "fetch"
    OPTION_MERGE = "merge"
    OPTION_REBASE = "rebase"
    option = "merge"
    result = 1  # QDialog.Accepted

    def __init__(self, parent=None, branch=None):
        pass

    def exec(self):
        return type(self).result

    def get_selected_option(self):
        return type(self).option


class _FakePullWindow(ResetMixin):
    """ResetMixin bound to a repo path, with the real conflict-check and
    pull chain intact; only window-side hooks are stubbed."""

    def __init__(self, repo_path):
        self.repo_path = repo_path
        self.calls = []
        self.worker = None
        self._active_workers = set()
        self._pull_rebase = False
        self.last_head = None

    def save_undo_state(self):
        """Mirrors UndoMixin.save_undo_state: snapshot HEAD pre-operation."""
        self.calls.append("save_undo_state")
        self.last_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.repo_path,
            text=True).strip()

    def _check_not_viewer_mode(self):
        return True

    def _check_head_unchanged(self):
        return True

    def _check_no_unstaged_changes(self):
        return True

    def load_history(self):
        self.calls.append("load_history")

    def _notify_browse_windows(self):
        self.calls.append("notify_browse_windows")


class TestPullFlow(unittest.TestCase):
    """End-to-end handle_git_pull against real scratch repos + bare origin."""

    @classmethod
    def setUpClass(cls):
        if not HAS_PYSIDE:
            return
        if not hasattr(cls, "app"):
            try:
                from PySide6.QtWidgets import QApplication
                if not QApplication.instance():
                    cls.app = QApplication([])
            except Exception:
                pass

    def setUp(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        _FakeGitWorker.made = []
        _FakeMessageBox.events = []
        _FakePullDialog.option = "merge"
        _FakePullDialog.result = 1
        for target, fake in (
            ("GitWorker", _FakeGitWorker),
            ("ProgressDialog", _FakeProgressDialog),
            ("QMessageBox", _FakeMessageBox),
            ("PullDialog", _FakePullDialog),
        ):
            patcher = mock.patch.object(reset_mixin, target, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        if getattr(self, "root", None):
            shutil.rmtree(self.root, ignore_errors=True)

    def _build_repo(self, mode):
        """Scratch repo + bare origin. mode:
        - conflict: both sides edit base.txt differently
        - clean:    local adds local.txt, origin adds remote.txt
        - behind:   local stays at base (fast-forward only)
        """
        self.root = tempfile.mkdtemp(prefix="pullflow_")
        origin = os.path.join(self.root, "origin.git")
        repo = os.path.join(self.root, "repo")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", "--bare", origin], check=True)
        subprocess.run(
            ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
            cwd=origin, check=True, capture_output=True)
        _git(repo, "init", "-qb", "main")
        with open(os.path.join(repo, "base.txt"), "w") as f:
            f.write("base\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "base")
        _git(repo, "remote", "add", "origin", origin)
        _git(repo, "push", "-qu", "origin", "main")
        clone = os.path.join(self.root, "clone")
        subprocess.run(["git", "clone", "-q", origin, clone], check=True)
        subprocess.run(["git", "checkout", "-q", "main"], cwd=clone,
                       capture_output=True)
        if mode == "conflict":
            with open(os.path.join(clone, "base.txt"), "w") as f:
                f.write("remote change\n")
        else:
            with open(os.path.join(clone, "remote.txt"), "w") as f:
                f.write("remote work\n")
        _git(clone, "add", ".")
        _git(clone, "commit", "-m", "remote commit")
        _git(clone, "push", "-q")
        if mode == "conflict":
            with open(os.path.join(repo, "base.txt"), "w") as f:
                f.write("local change\n")
            _git(repo, "add", ".")
            _git(repo, "commit", "-m", "local commit")
        elif mode == "clean":
            with open(os.path.join(repo, "local.txt"), "w") as f:
                f.write("local work\n")
            _git(repo, "add", ".")
            _git(repo, "commit", "-m", "local commit")
        return repo

    def _head(self, repo):
        return _git(repo, "rev-parse", "HEAD").stdout.strip()

    def _merge_head(self, repo):
        return os.path.exists(os.path.join(repo, ".git", "MERGE_HEAD"))

    def _worker_cmds(self):
        return [w.cmd for w in _FakeGitWorker.made]

    def test_conflict_merge_pull_refused(self):
        """Divergent same-file edits: only the fetch worker runs, the pull
        worker is never created, the warning names the file, and the repo
        is left untouched (HEAD unchanged, no MERGE_HEAD)."""
        repo = self._build_repo("conflict")
        head_before = self._head(repo)
        win = _FakePullWindow(repo)
        win.handle_git_pull()
        self.assertEqual(self._worker_cmds(), [["git", "fetch"]])
        warnings = [e for e in _FakeMessageBox.events if e[0] == "warning"]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0][1], "Pull May Conflict")
        self.assertIn("base.txt", warnings[0][2])
        self.assertIn("git pull", warnings[0][2])
        self.assertEqual(self._head(repo), head_before)
        self.assertFalse(self._merge_head(repo))
        self.assertNotIn("load_history", win.calls)
        self.assertNotIn("save_undo_state", win.calls,
                         "a refused pull must not arm undo")

    def test_conflict_rebase_pull_refused(self):
        """Same for git pull --rebase: the pre-check runs before any
        rebase is attempted."""
        repo = self._build_repo("conflict")
        head_before = self._head(repo)
        win = _FakePullWindow(repo)
        _FakePullDialog.option = "rebase"
        win.handle_git_pull()
        self.assertEqual(self._worker_cmds(), [["git", "fetch"]])
        warnings = [e for e in _FakeMessageBox.events if e[0] == "warning"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("Pull May Conflict", warnings[0][1])
        self.assertIn("git pull --rebase", warnings[0][2])
        self.assertEqual(self._head(repo), head_before)
        self.assertFalse(self._merge_head(repo))

    def test_clean_divergence_merges(self):
        """Non-overlapping local/origin commits: fetch then
        git pull --no-rebase runs, succeeds, refreshes, and arms undo
        with the pre-pull HEAD."""
        repo = self._build_repo("clean")
        head_before = self._head(repo)
        win = _FakePullWindow(repo)
        win.handle_git_pull()
        self.assertEqual(self._worker_cmds(),
                         [["git", "fetch"], ["git", "pull", "--no-rebase"]])
        infos = [e for e in _FakeMessageBox.events if e[0] == "information"]
        self.assertEqual(len(infos), 1)
        self.assertIn("Success", infos[0][1])
        self.assertIn("load_history", win.calls)
        self.assertIn("notify_browse_windows", win.calls)
        log = _git(repo, "log", "--oneline").stdout
        self.assertIn("remote commit", log)
        self.assertTrue(os.path.exists(os.path.join(repo, "remote.txt")))
        self.assertIn("save_undo_state", win.calls)
        self.assertEqual(win.last_head, head_before,
                         "undo must snapshot the pre-pull HEAD")
        self.assertNotEqual(self._head(repo), head_before)

    def test_clean_divergence_rebases(self):
        """git pull --rebase: local commit is replayed on top, history
        stays linear."""
        repo = self._build_repo("clean")
        win = _FakePullWindow(repo)
        _FakePullDialog.option = "rebase"
        win.handle_git_pull()
        self.assertEqual(self._worker_cmds(),
                         [["git", "fetch"], ["git", "pull", "--rebase"]])
        infos = [e for e in _FakeMessageBox.events if e[0] == "information"]
        self.assertEqual(len(infos), 1)
        parents = _git(repo, "rev-list", "--parents", "-n", "1",
                       "HEAD").stdout.split()
        self.assertEqual(len(parents), 2, "rebase must keep history linear")
        log = _git(repo, "log", "--oneline").stdout
        self.assertIn("remote commit", log)
        self.assertIn("local commit", log)
        self.assertIn("save_undo_state", win.calls,
                      "pull --rebase must arm undo too")

    def test_fast_forward_pull(self):
        """Local behind origin with no local commits: pull fast-forwards."""
        repo = self._build_repo("behind")
        # the bare origin's tip (the local repo's origin/main is stale
        # until the flow's fetch refreshes it)
        origin_sha = _git(os.path.join(self.root, "origin.git"),
                          "rev-parse", "main").stdout.strip()
        head_before = self._head(repo)
        win = _FakePullWindow(repo)
        win.handle_git_pull()
        self.assertEqual(self._worker_cmds(),
                         [["git", "fetch"], ["git", "pull", "--no-rebase"]])
        self.assertEqual(self._head(repo), origin_sha)
        self.assertIn("load_history", win.calls)
        self.assertEqual(win.last_head, head_before,
                         "undo must snapshot the pre-fast-forward HEAD")

    def test_no_upstream_warns_without_running(self):
        """No origin/<branch>: warning, zero workers started."""
        self.root = tempfile.mkdtemp(prefix="pullflow_")
        repo = os.path.join(self.root, "repo")
        os.makedirs(repo)
        _git(repo, "init", "-qb", "main")
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("a\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "base")
        win = _FakePullWindow(repo)
        win.handle_git_pull()
        self.assertEqual(self._worker_cmds(), [])
        warnings = [e for e in _FakeMessageBox.events if e[0] == "warning"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("No upstream", warnings[0][2])

    def test_fetch_failure_aborts_before_pull(self):
        """A failing fetch (bad remote) surfaces a critical box and never
        reaches the conflict check or the pull."""
        repo = self._build_repo("clean")
        _git(repo, "remote", "set-url", "origin",
             os.path.join(self.root, "gone.git"))
        win = _FakePullWindow(repo)
        win.handle_git_pull()
        self.assertEqual(self._worker_cmds(), [["git", "fetch"]])
        crits = [e for e in _FakeMessageBox.events if e[0] == "critical"]
        self.assertEqual(len(crits), 1)
        self.assertIn("Pull Failed", crits[0][1])
        self.assertNotIn("load_history", win.calls)
        self.assertNotIn("save_undo_state", win.calls,
                         "a failed fetch must not arm undo")

    def test_fetch_only_runs_fetch_no_pull_no_undo(self):
        """The fetch option reuses the fetch-only flow: one fetch worker,
        no conflict check, no undo, no pull."""
        repo = self._build_repo("clean")
        win = _FakePullWindow(repo)
        _FakePullDialog.option = "fetch"
        win.handle_git_pull()
        self.assertEqual(self._worker_cmds(), [["git", "fetch"]])
        infos = [e for e in _FakeMessageBox.events if e[0] == "information"]
        self.assertEqual(len(infos), 1)
        self.assertIn("git fetch", infos[0][2])
        self.assertNotIn("save_undo_state", win.calls)
        self.assertNotIn("notify_browse_windows", win.calls)
        self.assertIn("load_history", win.calls,
                      "fetch refreshes the history list")

    def test_fetch_only_works_without_upstream(self):
        """Fetch-only must not require an origin/<branch> upstream."""
        self.root = tempfile.mkdtemp(prefix="pullflow_")
        origin = os.path.join(self.root, "origin.git")
        repo = os.path.join(self.root, "repo")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", "--bare", origin], check=True)
        _git(repo, "init", "-qb", "main")
        with open(os.path.join(repo, "a.txt"), "w") as f:
            f.write("a\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "base")
        _git(repo, "remote", "add", "origin", origin)
        _git(repo, "push", "-qu", "origin", "main")
        # A branch with no upstream: main tracks origin/main, use a new one
        _git(repo, "checkout", "-qb", "feature")
        win = _FakePullWindow(repo)
        _FakePullDialog.option = "fetch"
        win.handle_git_pull()
        self.assertEqual(self._worker_cmds(), [["git", "fetch"]])
        warnings = [e for e in _FakeMessageBox.events if e[0] == "warning"]
        self.assertEqual(warnings, [], "fetch must not demand an upstream")
        infos = [e for e in _FakeMessageBox.events if e[0] == "information"]
        self.assertEqual(len(infos), 1)

    def test_dialog_cancel_runs_nothing(self):
        """Rejecting the PullDialog starts no workers at all."""
        repo = self._build_repo("clean")
        win = _FakePullWindow(repo)
        _FakePullDialog.result = 0
        win.handle_git_pull()
        self.assertEqual(self._worker_cmds(), [])
        self.assertEqual(_FakeMessageBox.events, [])
        self.assertNotIn("save_undo_state", win.calls)


if __name__ == "__main__":
    unittest.main()
