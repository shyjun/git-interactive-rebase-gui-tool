"""git progress: parsing, the progress dialog, and the worker plumbing.

git reports network progress on stderr as CR-separated updates
("Receiving objects:  42% (17/40), ...") but only when asked with
--progress and never when its output is a pipe - so GitWorker must run the
command through Popen, read stderr itself, and forward the percentages to
ProgressDialog.set_progress().

Runtime coverage for fetch/pull against real repos lives in
test_pull_flow.py; this file covers the parser, the dialog and the worker.
"""
import ast
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PySide6.QtWidgets import QApplication
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False


# --- parser ---------------------------------------------------------------

class TestParseGitProgress(unittest.TestCase):
    def _parse(self, line):
        from lib.app_window.workers import parse_git_progress
        return parse_git_progress(line)

    def test_receive_phase(self):
        self.assertEqual(
            self._parse("Receiving objects:  42% (17/40), 1.23 MiB | 2.00 MiB/s"),
            ("Receiving objects", 42),
        )

    def test_remote_prefixed_phase(self):
        self.assertEqual(
            self._parse("remote: Counting objects: 12% (5/40)"),
            ("Counting objects", 12),
        )

    def test_complete_phase(self):
        self.assertEqual(
            self._parse("Compressing objects: 100% (8/8), done."),
            ("Compressing objects", 100),
        )

    def test_push_write_phase(self):
        self.assertEqual(
            self._parse("Writing objects:  45% (10/22), 1.00 KiB | 1.00 KiB/s, done."),
            ("Writing objects", 45),
        )

    def test_bytes_input(self):
        self.assertEqual(
            self._parse(b"Resolving deltas: 100% (1234/1234), done."),
            ("Resolving deltas", 100),
        )

    def test_non_progress_lines_are_ignored(self):
        for line in (
            "",
            "   abc123..def456  main -> main",
            "From https://github.com/shyjun/tool",
            "fatal: could not read Username for 'https://github.com'",
            "Already up to date.",
        ):
            self.assertIsNone(self._parse(line), line)

    def test_out_of_range_percent_is_ignored(self):
        self.assertIsNone(self._parse("error: failed 200% of something"))

    def test_missing_phase_is_ignored(self):
        self.assertIsNone(self._parse(": 50%"))

    def test_strip_progress_keeps_the_error(self):
        from lib.app_window.workers import _strip_progress
        text = (
            "Receiving objects:  42% (17/40), 1.23 MiB | 2.00 MiB/s\n"
            "remote: Counting objects: 12% (5/40)\n"
            "fatal: could not read Username for 'https://github.com'"
        )
        self.assertEqual(
            _strip_progress(text),
            "fatal: could not read Username for 'https://github.com'",
        )


# --- dialog ---------------------------------------------------------------

class TestProgressDialogSetProgress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE and not QApplication.instance():
            cls.app = QApplication([])

    def _dialog(self):
        from lib.dialogs.confirmation_dialogs import ProgressDialog
        return ProgressDialog("Git Fetching", "git fetch in progress...")

    def test_starts_indeterminate(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        dlg = self._dialog()
        self.assertEqual(dlg.progress_bar.maximum(), 0)
        self.assertEqual(dlg.label.text(), "git fetch in progress...")
        dlg.deleteLater()

    def test_set_progress_switches_bar_and_label(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        dlg = self._dialog()
        dlg.set_progress("Receiving objects", 42)
        self.assertEqual(dlg.progress_bar.maximum(), 100)
        self.assertEqual(dlg.progress_bar.value(), 42)
        self.assertEqual(dlg.label.text(), "Receiving objects: 42%")
        # a later phase update must not reset the bar to indeterminate
        dlg.set_progress("Resolving deltas", 7)
        self.assertEqual(dlg.progress_bar.maximum(), 100)
        self.assertEqual(dlg.progress_bar.value(), 7)
        dlg.deleteLater()

    def test_invalid_percent_is_ignored(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        for bad in (-1, 150, "42", None):
            dlg = self._dialog()
            dlg.set_progress("Receiving objects", bad)
            self.assertEqual(dlg.progress_bar.maximum(), 0,
                             f"bad percent {bad!r} must keep it indeterminate")
            self.assertEqual(dlg.label.text(), "git fetch in progress...")
            dlg.deleteLater()

    def test_signal_order_reaches_the_slot(self):
        """git_progress emits (phase, percent) - the slot must take them
        in that order, otherwise every update is rejected as a bad percent.

        Regression: the slot used to be set_progress(percent, phase), so a
        real fetch emitted 458 updates and the bar never left the marquee.
        """
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        from lib.app_window.workers import GitWorker
        worker = GitWorker(["git", "fetch"], os.getcwd())
        dlg = self._dialog()
        worker.git_progress.connect(dlg.set_progress)
        worker.git_progress.emit("Receiving objects", 42)
        for _ in range(3):
            QApplication.processEvents()
        self.assertEqual(dlg.progress_bar.maximum(), 100)
        self.assertEqual(dlg.progress_bar.value(), 42)
        self.assertEqual(dlg.label.text(), "Receiving objects: 42%")
        worker.deleteLater()
        dlg.deleteLater()


# --- worker ---------------------------------------------------------------

# Writes canned git progress to stderr, split awkwardly across writes to
# exercise the CR-splitting, then exits with *code*.
_PROGRESS_SCRIPT = r"""
import sys, time
sys.stderr.write("\rCounting objects:  10% (1/10)")
sys.stderr.flush()
time.sleep(0.05)
# split a single update across two writes
sys.stderr.write("\rReceiving objects:  4")
sys.stderr.flush()
time.sleep(0.05)
sys.stderr.write("2% (17/40), 1.23 MiB | 2.00 MiB/s")
sys.stderr.flush()
time.sleep(0.05)
sys.stderr.write("\rReceiving objects: 100% (40/40), done.\r")
sys.stderr.flush()
sys.stdout.write("fetched\n")
sys.stdout.flush()
sys.exit(__CODE__)
"""

_SLEEP_SCRIPT = "import time, sys; time.sleep(30); sys.exit(0)"


def _script(code):
    return _PROGRESS_SCRIPT.replace("__CODE__", str(code))


class TestGitWorkerProgress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAS_PYSIDE:
            return
        if not QApplication.instance():
            cls.app = QApplication([])

    def setUp(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        self.tmp = tempfile.mkdtemp(prefix="gitprogress_")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, script, timeout=15, progress=True):
        from lib.app_window.workers import GitWorker
        events = {"progress": [], "finished": []}
        worker = GitWorker([sys.executable, "-c", script], self.tmp,
                           timeout=timeout, progress=progress)
        worker.git_progress.connect(
            lambda phase, pct: events["progress"].append((phase, pct)))
        worker.git_finished.connect(
            lambda ok, out, err: events["finished"].append((ok, out, err)))
        worker.start()
        self.assertTrue(worker.wait(20000), "worker must finish")
        # flush any queued deliveries (the receiver lives in this thread)
        for _ in range(3):
            if QApplication.instance():
                QApplication.processEvents()
        return events

    def test_progress_updates_are_emitted(self):
        events = self._run(_script(0))
        self.assertEqual(
            events["progress"],
            [("Counting objects", 10),
             ("Receiving objects", 42),
             ("Receiving objects", 100)],
        )
        self.assertEqual(events["finished"],
                         [(True, "fetched\n", "")])

    def test_failure_keeps_the_error_not_the_progress(self):
        events = self._run(_script(1))
        ok, out, err = events["finished"][0]
        self.assertFalse(ok)
        self.assertEqual(out, "",
                         "failures report stderr only, like the plain path")
        self.assertNotIn("Receiving objects", err,
                         "progress must not pollute the error message")
        self.assertTrue(events["progress"], "progress is emitted either way")

    def test_progress_flag_appends_the_git_option(self):
        from lib.app_window.workers import GitWorker
        seen = []
        worker = GitWorker([sys.executable, "-c",
                            "import sys; print(' '.join(sys.argv[1:]))"],
                           self.tmp, timeout=15, progress=True)
        worker.git_finished.connect(
            lambda ok, out, err: seen.append((ok, out, err)))
        worker.start()
        self.assertTrue(worker.wait(20000))
        for _ in range(3):
            if QApplication.instance():
                QApplication.processEvents()
        self.assertTrue(seen and seen[0][0], seen)
        self.assertEqual(seen[0][1].strip(), "--progress",
                         "the worker must ask git for progress itself")

    def test_timeout_is_enforced_on_the_progress_path(self):
        events = self._run(_SLEEP_SCRIPT, timeout=1)
        ok, out, err = events["finished"][0]
        self.assertFalse(ok)
        self.assertIn("Command timed out after 1s", err)


# --- wiring ---------------------------------------------------------------

class TestProgressWiring(unittest.TestCase):
    """reset_mixin must ask for progress and forward it to the dialog."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(__file__), "..",
                            "lib/app_window/reset_mixin.py")
        with open(path, encoding="utf-8") as fh:
            cls.tree = ast.parse(fh.read())
        cls.funcs = [
            n for n in ast.walk(cls.tree) if isinstance(n, ast.FunctionDef)
        ]

    @staticmethod
    def _gitworker_calls(func):
        return [
            n for n in ast.walk(func)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == "GitWorker"
        ]

    @staticmethod
    def _is_network(call):
        if not call.args:
            return False
        first = call.args[0]
        if isinstance(first, ast.Name):      # the push/pull `cmd` variable
            return True
        if isinstance(first, (ast.List, ast.Tuple)):
            strings = {
                n.value for n in ast.walk(first)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            }
            return bool(strings & {"fetch", "pull", "push"})
        return False

    def _network_calls(self):
        found = []
        for func in self.funcs:
            for call in self._gitworker_calls(func):
                if self._is_network(call):
                    found.append((func, call))
        return found

    def test_four_network_sites_ask_for_progress(self):
        found = self._network_calls()
        self.assertEqual(len(found), 4,
                         f"expected fetch x2 + pull + push, got "
                         f"{[f.name for f, _ in found]}")
        for func, call in found:
            progress = [kw.value for kw in call.keywords
                        if kw.arg == "progress"]
            self.assertEqual(len(progress), 1,
                             f"{func.name}: GitWorker must pass progress=")
            self.assertIsInstance(progress[0], ast.Constant,
                                  f"{func.name}: progress must be a literal")
            self.assertIs(progress[0].value, True,
                          f"{func.name}: progress=True required")

    def test_each_site_forwards_progress_to_the_dialog(self):
        for func, _ in self._network_calls():
            connects = [
                n for n in ast.walk(func)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "connect"
                and isinstance(n.func.value, ast.Attribute)
                and n.func.value.attr == "git_progress"
            ]
            self.assertTrue(connects,
                            f"{func.name}: git_progress must be connected")
            for conn in connects:
                dotted = ast.unparse(conn.args[0]) if conn.args else ""
                self.assertIn("set_progress", dotted,
                              f"{func.name}: git_progress must reach "
                              f"ProgressDialog.set_progress, got {dotted}")

    def test_each_site_runs_git_with_progress_flag(self):
        for func, _ in self._network_calls():
            flags = [
                n.value for n in ast.walk(func)
                if isinstance(n, ast.Constant) and n.value == "--progress"
            ]
            self.assertTrue(flags,
                            f"{func.name}: the git command must include "
                            "--progress")


if __name__ == "__main__":
    unittest.main()
