import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Import lib.app_window first, matching the app's import order: importing
# lib.git_helpers first hits a package-init cycle (git_helpers -> core ->
# app_window.helpers -> app_window.__init__ -> init_mixin -> git_helpers).
import lib.app_window.helpers  # noqa: F401
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDropEvent, QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QWidget,
)
from lib.app_window import commit_list as commit_list_mod
from lib.app_window import init_mixin as init_mixin_mod
from lib.app_window import rebase_mixin as rebase_mixin_mod
from lib.app_window.commit_list import CommitListWidget
from lib.app_window.init_mixin import InitMixin
from lib.app_window.rebase_mixin import RebaseMixin

app = QApplication.instance() or QApplication([])

S4 = ["aaaaaaa1", "bbbbbbb2", "ccccccc3", "ddddddd4"]
GUARDS = [
    "_check_not_viewer_mode",
    "_check_head_unchanged",
    "_check_no_unstaged_changes",
    "_check_staged_changes",
]


def _requires_screen(test):
    """In-test drag sessions (QTest mouse drag) don't work on the offscreen
    platform — verified: the drop never lands, so skip there."""
    if QGuiApplication.platformName() == "offscreen":
        test.skipTest("in-test drag-and-drop needs a real platform (xcb)")


class _MsgBox:
    """Module-level stand-in for QMessageBox (never opens a modal)."""

    Yes = QMessageBox.Yes
    No = QMessageBox.No
    Ok = QMessageBox.Ok
    answer = QMessageBox.Yes
    question_calls = []
    critical_calls = []
    information_calls = []

    @classmethod
    def reset(cls, answer=QMessageBox.Yes):
        cls.answer = answer
        cls.question_calls = []
        cls.critical_calls = []
        cls.information_calls = []

    @classmethod
    def question(cls, parent, title, text, buttons=None, default=None):
        cls.question_calls.append((title, text))
        return cls.answer

    @classmethod
    def critical(cls, parent, title, text, *args):
        cls.critical_calls.append((title, text))
        return QMessageBox.Ok

    @classmethod
    def information(cls, parent, title, text, *args):
        cls.information_calls.append((title, text))
        return QMessageBox.Ok


class _StubProgress:
    def __init__(self, *args, **kwargs):
        pass

    def show(self):
        pass

    def close(self):
        pass


class _StubMainWindow(QWidget):
    """Duck-typed main window: recorders instead of real rebase work."""

    def __init__(self):
        super().__init__()
        self.browse_mode = False
        self.multi_select_mode = False
        self.perform_move_calls = []
        self.check_calls = []
        self.exit_multi_calls = 0
        self._guards = {name: True for name in GUARDS}
        # Guard entry points are called like the real methods
        # (`main._check_head_unchanged()`), so bind recorders that return bool.
        for name in GUARDS:
            setattr(self, name, self._make_check(name))

    def perform_move(self, new_shas, original_shas=None, upstream_override=None):
        self.perform_move_calls.append((
            list(new_shas),
            list(original_shas) if original_shas is not None else None,
            upstream_override,
        ))

    def exit_multi_select_mode(self):
        self.exit_multi_calls += 1
        self.multi_select_mode = False

    def fail_guard(self, name):
        self._guards[name] = False

    def _make_check(self, name):
        def check():
            self.check_calls.append(name)
            return self._guards[name]
        return check


class _Harness(RebaseMixin, InitMixin, QWidget):
    """Real perform_move/run_interactive_rebase/checks on a temp repo.

    Only the outer UI/session hooks are stubbed; InitMixin.__init__ (the full
    app startup) is intentionally never called."""

    def __init__(self, repo_path, commit_sha):
        QWidget.__init__(self)
        self.repo_path = repo_path
        self.commit_sha = commit_sha
        self.viewer_mode = False
        self.cli_mode = False
        self.multi_select_mode = False
        self.browse_windows = []
        self.load_history_calls = 0
        self.cached_current_head_full_sha = self.get_head_sha()

    def save_undo_state(self):
        pass

    def load_history(self):
        self.load_history_calls += 1

    def _notify_browse_windows(self):
        pass

    def _abort_rebase_safely(self):
        return True, ""

    def _warn_rebase_abort_failure(self, detail):
        pass

    def get_commit_shas(self):
        return self.list_widget.get_commit_shas()

    def closeEvent(self, event):
        # The harness never runs InitMixin.__init__, so it has no settings
        # store; teardown only needs close() to be harmless.
        event.accept()


def _git(repo, *args):
    subprocess.run(["git"] + list(args), cwd=repo, check=True,
                   capture_output=True, text=True)


def _out(repo, *args):
    return subprocess.run(["git"] + list(args), cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def _write(repo, name, content):
    with open(os.path.join(repo, name), "w") as f:
        f.write(content)


class _DropTestCase(unittest.TestCase):
    """QMessageBox/_log/ProgressDialog patches + widget lifecycle."""

    def setUp(self):
        self._orig = (
            commit_list_mod.QMessageBox,
            commit_list_mod._log,
            rebase_mixin_mod.QMessageBox,
            rebase_mixin_mod.ProgressDialog,
            init_mixin_mod.QMessageBox,
        )
        self.logs = []
        commit_list_mod.QMessageBox = _MsgBox
        commit_list_mod._log = self.logs.append
        rebase_mixin_mod.QMessageBox = _MsgBox
        rebase_mixin_mod.ProgressDialog = _StubProgress
        # The real guard dialogs live in init_mixin; unpatched they are real
        # modal boxes that block the test run until someone clicks them.
        init_mixin_mod.QMessageBox = _MsgBox
        _MsgBox.reset()

    def tearDown(self):
        (commit_list_mod.QMessageBox,
         commit_list_mod._log,
         rebase_mixin_mod.QMessageBox,
         rebase_mixin_mod.ProgressDialog,
         init_mixin_mod.QMessageBox) = self._orig

    def _track(self, widget):
        self.addCleanup(lambda w=widget: (w.close(), w.deleteLater()))
        return widget

    def _build(self, main, shas=S4, sentinel_at=None):
        """List [sha subject...] newest-first style; sentinel_at inserts a
        'Load 100 more...' row with the load_more role."""
        self._track(main)
        main.show()
        lw = self._track(CommitListWidget(main))
        for i, sha in enumerate(shas):
            if sentinel_at is not None and i == sentinel_at:
                sentinel = QListWidgetItem("Load 100 more...")
                sentinel.setData(Qt.UserRole + 9, "load_more")
                lw.addItem(sentinel)
            lw.addItem(f"{sha} subject {i + 1}")
        if sentinel_at is not None and sentinel_at == len(shas):
            sentinel = QListWidgetItem("Load 100 more...")
            sentinel.setData(Qt.UserRole + 9, "load_more")
            lw.addItem(sentinel)
        lw.resize(280, 340)
        lw.show()
        app.processEvents()
        # perform_move reads merge flags from the live list, exactly as the
        # real main window does.
        main.list_widget = lw
        return lw

    @staticmethod
    def _drop_event(lw, target_row):
        """Synthetic drop in viewport coordinates.

        Enough for every path that returns before super().dropEvent (confirm
        No, guard failures) and for multi-select, which never calls super()."""
        if target_row is None:
            last = lw.visualRect(lw.model().index(lw.count() - 1, 0))
            pos = QPointF(lw.viewport().width() // 2, last.bottom() + 8)
            data = QMimeData()
        else:
            idx = lw.model().index(target_row, 0)
            pos = QPointF(lw.visualRect(idx).center())
            data = lw.model().mimeData([idx])
        return QDropEvent(pos, Qt.MoveAction, data, Qt.LeftButton, Qt.NoModifier)

    @staticmethod
    def _rows(lw):
        return [lw.item(i).text().split()[0] for i in range(lw.count())]

    @staticmethod
    def _check_rows(lw, rows):
        for r in rows:
            item = lw.item(r)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)

    @staticmethod
    def _qt_drag(lw, from_row, to_row):
        p0 = lw.visualRect(lw.model().index(from_row, 0)).center()
        p2 = lw.visualRect(lw.model().index(to_row, 0)).center()
        QTest.mousePress(lw.viewport(), Qt.LeftButton, Qt.NoModifier, p0)
        # Two passes so the drag always starts (a single short pass can end
        # before Qt begins the drag session, which silently drops the release).
        for _ in range(2):
            for i in range(1, 9):
                step = QPoint(p0.x() + (p2.x() - p0.x()) * i // 8,
                              p0.y() + (p2.y() - p0.y()) * i // 8)
                QTest.mouseMove(lw.viewport(), step)
                app.processEvents()
        QTest.mouseRelease(lw.viewport(), Qt.LeftButton, Qt.NoModifier, p2)
        app.processEvents()


class TestConstructionAndHelpers(_DropTestCase):

    def test_browse_mode_disables_drag(self):
        main = _StubMainWindow()
        main.browse_mode = True
        lw = CommitListWidget(main)
        self._track(lw)
        self.assertEqual(lw.dragDropMode(), QListWidget.NoDragDrop)

    def test_default_enables_internal_move_drag(self):
        lw = CommitListWidget(self._track(_StubMainWindow()))
        self.assertEqual(lw.dragDropMode(), QListWidget.InternalMove)
        self.assertTrue(lw.dragEnabled())
        self.assertTrue(lw.acceptDrops())

    def test_get_commit_shas_excludes_sentinels_and_bad_tokens(self):
        lw = CommitListWidget(self._track(_StubMainWindow()))
        lw.addItem("aaaaaaa1 subject one")
        sentinel = QListWidgetItem("Load 100 more...")
        sentinel.setData(Qt.UserRole + 9, "load_more")
        lw.addItem(sentinel)
        lw.addItem("bbbbbbb2 subject two")
        lw.addItem("Load something else")
        lw.addItem("xyz short")
        lw.addItem("zzzzzzz9 not hex at all")
        self.assertEqual(lw.get_commit_shas(), ["aaaaaaa1", "bbbbbbb2"])
        self.assertEqual(lw.get_commit_count(), 2)


class TestSingleDropLogic(_DropTestCase):

    def test_confirm_no_leaves_order_unchanged(self):
        main = _StubMainWindow()
        lw = self._build(main)
        _MsgBox.reset(answer=QMessageBox.No)
        lw.setCurrentRow(0)
        lw.dropEvent(self._drop_event(lw, 2))
        app.processEvents()
        self.assertEqual(self._rows(lw), S4)
        self.assertEqual(main.perform_move_calls, [])
        self.assertTrue(any("Cancelled reorder of aaaaaaa1" in line
                            for line in self.logs))

    def test_each_guard_blocks_the_move(self):
        for guard in GUARDS:
            with self.subTest(guard=guard):
                main = _StubMainWindow()
                main.fail_guard(guard)
                lw = self._build(main)
                _MsgBox.reset(answer=QMessageBox.Yes)
                lw.setCurrentRow(0)
                lw.dropEvent(self._drop_event(lw, 2))
                app.processEvents()
                self.assertEqual(self._rows(lw), S4,
                                 f"{guard} must block the reorder")
                self.assertEqual(main.perform_move_calls, [])
                expected = GUARDS[:GUARDS.index(guard) + 1]
                self.assertEqual(main.check_calls, expected)

    def test_no_current_item_asks_nothing(self):
        main = _StubMainWindow()
        lw = self._build(main)
        lw.setCurrentRow(-1)
        self.assertIsNone(lw.currentItem())
        lw.dropEvent(self._drop_event(lw, 2))
        app.processEvents()
        self.assertEqual(_MsgBox.question_calls, [])
        self.assertEqual(main.perform_move_calls, [])

    def test_confirm_text_names_target_commit(self):
        main = _StubMainWindow()
        lw = self._build(main)
        _MsgBox.reset(answer=QMessageBox.No)
        lw.setCurrentRow(0)
        lw.dropEvent(self._drop_event(lw, 2))
        self.assertEqual(len(_MsgBox.question_calls), 1)
        _, text = _MsgBox.question_calls[0]
        self.assertIn(f"near commit <b>{S4[2]}</b>", text)

    def test_confirm_text_for_drop_past_list_end(self):
        main = _StubMainWindow()
        lw = self._build(main)
        _MsgBox.reset(answer=QMessageBox.No)
        lw.setCurrentRow(0)
        lw.dropEvent(self._drop_event(lw, None))
        self.assertEqual(len(_MsgBox.question_calls), 1)
        _, text = _MsgBox.question_calls[0]
        self.assertIn("to the end of the list", text)


class TestSingleDropRealDrag(_DropTestCase):

    def test_confirm_yes_reorders_and_moves(self):
        _requires_screen(self)
        main = _StubMainWindow()
        lw = self._build(main)
        _MsgBox.reset(answer=QMessageBox.Yes)
        original = lw.get_commit_shas()
        self._qt_drag(lw, 0, 2)
        app.processEvents()
        new = lw.get_commit_shas()
        self.assertNotEqual(new, original)
        self.assertEqual(len(main.perform_move_calls), 1)
        got_new, got_orig, upstream = main.perform_move_calls[0]
        self.assertEqual(got_orig, original)
        self.assertEqual(got_new, new)
        self.assertEqual(got_new, lw.get_commit_shas())
        self.assertIsNone(upstream)
        self.assertEqual(len(_MsgBox.question_calls), 1)

    def test_confirm_no_drag_leaves_order(self):
        _requires_screen(self)
        main = _StubMainWindow()
        lw = self._build(main)
        _MsgBox.reset(answer=QMessageBox.No)
        original = lw.get_commit_shas()
        self._qt_drag(lw, 0, 2)
        app.processEvents()
        self.assertEqual(lw.get_commit_shas(), original)
        self.assertEqual(main.perform_move_calls, [])


class TestMultiSelectDrop(_DropTestCase):

    def _multi(self, check_rows, current_row, fail_guard=None):
        main = _StubMainWindow()
        main.multi_select_mode = True
        if fail_guard:
            main.fail_guard(fail_guard)
        lw = self._build(main)
        self._check_rows(lw, check_rows)
        lw.setCurrentRow(current_row)
        return main, lw

    def test_nothing_checked_ignores(self):
        main, lw = self._multi([], 0)
        lw.dropEvent(self._drop_event(lw, 3))
        self.assertEqual(_MsgBox.question_calls, [])
        self.assertEqual(self._rows(lw), S4)

    def test_dragged_row_must_be_checked(self):
        main, lw = self._multi([1], 0)
        lw.dropEvent(self._drop_event(lw, 3))
        self.assertEqual(_MsgBox.question_calls, [])
        self.assertEqual(self._rows(lw), S4)

    def test_non_adjacent_checked_rejected(self):
        main, lw = self._multi([0, 2], 0)
        lw.dropEvent(self._drop_event(lw, 3))
        self.assertEqual(len(_MsgBox.critical_calls), 1)
        self.assertEqual(_MsgBox.critical_calls[0][0], "Non-Adjacent Commits")
        self.assertIn("adjacent", _MsgBox.critical_calls[0][1].lower())
        self.assertEqual(_MsgBox.question_calls, [])
        self.assertEqual(self._rows(lw), S4)

    def test_drop_inside_block_is_noop(self):
        main, lw = self._multi([0, 1], 0)
        lw.dropEvent(self._drop_event(lw, 1))
        self.assertEqual(_MsgBox.question_calls, [])
        self.assertEqual(self._rows(lw), S4)

    def test_drop_that_changes_nothing_is_ignored(self):
        # Block [0,1] dropped at row 2 inserts back at position 0.
        main, lw = self._multi([0, 1], 0)
        lw.dropEvent(self._drop_event(lw, 2))
        self.assertEqual(_MsgBox.question_calls, [])
        self.assertEqual(self._rows(lw), S4)

    def test_valid_move_above_target(self):
        main, lw = self._multi([2, 3], 2)
        _MsgBox.reset(answer=QMessageBox.Yes)
        lw.dropEvent(self._drop_event(lw, 0))
        self.assertEqual(self._rows(lw), [S4[2], S4[3], S4[0], S4[1]])
        self.assertEqual(len(_MsgBox.question_calls), 1)
        self.assertIn("move 2 commits", _MsgBox.question_calls[0][1])
        app.processEvents()  # flush the deferred perform_move
        self.assertEqual(len(main.perform_move_calls), 1)
        got_new, got_orig, upstream = main.perform_move_calls[0]
        self.assertEqual(got_orig, S4)
        self.assertEqual(got_new, [S4[2], S4[3], S4[0], S4[1]])
        self.assertIsNone(upstream)
        self.assertEqual(main.exit_multi_calls, 1)
        self.assertFalse(main.multi_select_mode)

    def test_valid_move_below_target(self):
        main, lw = self._multi([0, 1], 0)
        _MsgBox.reset(answer=QMessageBox.Yes)
        lw.dropEvent(self._drop_event(lw, 3))
        self.assertEqual(self._rows(lw), [S4[2], S4[0], S4[1], S4[3]])
        app.processEvents()
        got_new, got_orig, upstream = main.perform_move_calls[0]
        self.assertEqual(got_orig, S4)
        self.assertEqual(got_new, [S4[2], S4[0], S4[1], S4[3]])
        self.assertIsNone(upstream)

    def test_valid_move_to_list_end(self):
        main, lw = self._multi([0, 1], 0)
        _MsgBox.reset(answer=QMessageBox.Yes)
        lw.dropEvent(self._drop_event(lw, None))
        self.assertEqual(self._rows(lw), [S4[2], S4[3], S4[0], S4[1]])
        app.processEvents()
        got_new, got_orig, upstream = main.perform_move_calls[0]
        self.assertEqual(got_orig, S4)
        self.assertEqual(got_new, [S4[2], S4[3], S4[0], S4[1]])
        self.assertIsNone(upstream)

    def test_declined_move_keeps_everything(self):
        main, lw = self._multi([0, 1], 0)
        _MsgBox.reset(answer=QMessageBox.No)
        lw.dropEvent(self._drop_event(lw, 3))
        app.processEvents()
        self.assertEqual(self._rows(lw), S4)
        self.assertEqual(main.perform_move_calls, [])
        self.assertEqual(main.exit_multi_calls, 0)

    def test_guard_failure_keeps_order_and_multi_mode(self):
        main, lw = self._multi([0, 1], 0, fail_guard="_check_staged_changes")
        _MsgBox.reset(answer=QMessageBox.Yes)
        lw.dropEvent(self._drop_event(lw, 3))
        app.processEvents()
        self.assertEqual(self._rows(lw), S4)
        self.assertEqual(main.perform_move_calls, [])
        self.assertEqual(main.exit_multi_calls, 0)
        self.assertTrue(main.multi_select_mode)

    def test_load_more_sentinel_moves_but_stays_out_of_shas(self):
        main = _StubMainWindow()
        main.multi_select_mode = True
        lw = self._build(main, shas=S4, sentinel_at=2)
        self.assertEqual(lw.count(), 5)
        self._check_rows(lw, [0, 1])
        lw.setCurrentRow(0)
        _MsgBox.reset(answer=QMessageBox.Yes)
        lw.dropEvent(self._drop_event(lw, None))
        texts = [lw.item(i).text() for i in range(lw.count())]
        # Rows were [a, b, SENTINEL, c, d]; moving [a, b] to the end leaves
        # [SENTINEL, c, d, a, b].
        self.assertTrue(texts[0].startswith("Load"))
        self.assertEqual(
            [lw.item(i).text().split()[0] for i in range(1, 5)],
            [S4[2], S4[3], S4[0], S4[1]],
        )
        app.processEvents()
        got_new, got_orig, _upstream = main.perform_move_calls[0]
        self.assertEqual(got_orig, S4)  # sentinel never reaches the SHAs
        self.assertEqual(got_new, [S4[2], S4[3], S4[0], S4[1]])
        self.assertNotIn("Load", got_new)


def _make_linear_repo():
    repo = tempfile.mkdtemp()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "t")
    _write(repo, "f.txt", "base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base commit")
    for i in range(1, 5):
        _write(repo, f"file{i}.txt", f"{i}\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", f"commit {i}")
    lines = _out(repo, "log", "--format=%H%x09%s").splitlines()
    subjects = {}
    order = []
    for line in lines:
        sha, subj = line.split("\t")
        subjects[sha] = subj
        order.append(sha)
    base_sha = _out(repo, "rev-parse", "HEAD~4")
    return repo, base_sha, order, subjects


class TestEndToEndGitReorder(_DropTestCase):

    def test_drag_yes_rewrites_history(self):
        _requires_screen(self)
        repo, base_sha, order, subjects = _make_linear_repo()
        self.addCleanup(shutil.rmtree, repo, True)
        harness = _Harness(repo, base_sha)
        shas = order[:-1]  # branch point is the base, not a listed commit
        lw = self._build(harness, shas=shas)
        self.assertEqual(lw.get_commit_shas(), shas)
        _MsgBox.reset(answer=QMessageBox.Yes)

        self._qt_drag(lw, 0, 2)
        app.processEvents()

        new_shas = lw.get_commit_shas()
        self.assertNotEqual(new_shas, shas)
        expected = ["base commit"] + [subjects[s] for s in reversed(new_shas)]
        actual = _out(repo, "log", "--reverse", "--format=%s").splitlines()
        self.assertEqual(actual, expected)
        self.assertIn(("Success", "Commits reordered successfully!"),
                      _MsgBox.information_calls)
        self.assertGreaterEqual(harness.load_history_calls, 1)
        self.assertEqual(_out(repo, "status", "--porcelain"), "")

    def test_drag_no_leaves_history(self):
        _requires_screen(self)
        repo, base_sha, order, _subjects = _make_linear_repo()
        self.addCleanup(shutil.rmtree, repo, True)
        harness = _Harness(repo, base_sha)
        shas = order[:-1]
        lw = self._build(harness, shas=shas)
        before = _out(repo, "log", "--format=%H").splitlines()
        _MsgBox.reset(answer=QMessageBox.No)

        self._qt_drag(lw, 0, 2)
        app.processEvents()

        after = _out(repo, "log", "--format=%H").splitlines()
        self.assertEqual(after, before)
        self.assertEqual(lw.get_commit_shas(), shas)
        self.assertEqual(harness.load_history_calls, 0)

    def test_stale_head_guard_blocks_drop(self):
        repo, base_sha, order, _subjects = _make_linear_repo()
        self.addCleanup(shutil.rmtree, repo, True)
        harness = _Harness(repo, base_sha)
        shas = order[:-1]
        lw = self._build(harness, shas=shas)
        harness.cached_current_head_full_sha = "0" * 40
        before = _out(repo, "log", "--format=%H").splitlines()
        _MsgBox.reset(answer=QMessageBox.Yes)

        # Guards run before super().dropEvent, so a direct drop reaches them
        # without needing a real drag session.
        lw.setCurrentRow(0)
        lw.dropEvent(self._drop_event(lw, 2))
        app.processEvents()

        self.assertIn(("Repository Changed",),
                      [(t,) for t, _ in _MsgBox.information_calls])
        self.assertEqual(self._rows(lw), shas)
        self.assertEqual(_out(repo, "log", "--format=%H").splitlines(), before)

    def test_merge_crossing_blocked_before_rebase(self):
        repo = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, repo, True)
        _git(repo, "init", "-q")
        _git(repo, "config", "user.email", "t@t.com")
        _git(repo, "config", "user.name", "t")
        _write(repo, "f.txt", "base\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "base commit")
        _write(repo, "a.txt", "a\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "commit A")
        _write(repo, "b.txt", "b\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "commit B")
        main_branch = _out(repo, "rev-parse", "--abbrev-ref", "HEAD")
        side_point = _out(repo, "rev-parse", "HEAD~1")  # commit A
        _git(repo, "checkout", "-q", "-b", "side", side_point)
        _write(repo, "c.txt", "c\n")
        _git(repo, "add", ".")
        _git(repo, "commit", "-qm", "commit C")
        _git(repo, "checkout", "-q", main_branch)
        _git(repo, "merge", "--no-ff", "-q", "-m", "merge commit", "side")
        sha_m = _out(repo, "rev-parse", "HEAD")
        sha_b = _out(repo, "rev-parse", "HEAD~1")
        sha_a = _out(repo, "rev-parse", "HEAD~2")
        sha_c = _out(repo, "rev-parse", "side")

        original = [sha_m, sha_c, sha_b, sha_a]
        new = [sha_a, sha_m, sha_c, sha_b]  # A crosses above the merge
        base_sha = _out(repo, "rev-parse", "HEAD~3")
        harness = _Harness(repo, base_sha)
        lw = self._build(harness, shas=original)
        # Flag the merge item the way the real history loader does.
        merge_item = lw.item(0)
        self.assertTrue(merge_item.text().startswith(sha_m))
        merge_item.setData(Qt.UserRole + 5, True)
        before = _out(repo, "log", "--format=%H").splitlines()
        _MsgBox.reset()

        harness.perform_move(new, original)

        self.assertEqual(len(_MsgBox.critical_calls), 1)
        self.assertEqual(_MsgBox.critical_calls[0][0],
                         "Cannot Reorder Across Merge")
        self.assertIn("across merge", _MsgBox.critical_calls[0][1].lower())
        self.assertEqual(_out(repo, "log", "--format=%H").splitlines(), before)
        self.assertEqual(harness.load_history_calls, 0)


if __name__ == "__main__":
    unittest.main()
