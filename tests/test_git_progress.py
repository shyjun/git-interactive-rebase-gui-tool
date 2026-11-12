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


# --- failure-message extraction ------------------------------------------

# Real output of a tag-heavy `git fetch` that failed afterwards in the
# submodule phase: ~280 sideband report lines followed by the one line
# that matters. The failure box used to show all ~13 KB of it.
_USER_FETCH_FAILURE = (
    "From git.innophaseiot.com:skywalker/software/apu_uc\n"
    " * [new branch]        1030_ps_dev    -> origin/1030_ps_dev\n"
    "   bcfd16a6..e93309f0  Helium_B0_bringup  -> origin/Helium_B0_bringup\n"
    " + 9f012991...af83bfbc VK/USDK-97_iperf3  -> "
    "origin/VK/USDK-97_iperf3  (forced update)\n"
    " * [new tag]           dev_v2.1       -> dev_v2.1\n"
    "Fetching submodule components/soc/helium-b0/npu\n"
    "fatal: remote error: upload-pack: not our ref "
    "9739bef4cdc4a268bd6f53c57199c2a497c8f7a9\n"
    "Errors during submodule fetch:\n"
    "\tcomponents/soc/helium-b0/npu\n"
)


class TestExtractError(unittest.TestCase):
    def _extract(self, text):
        from lib.app_window.workers import _extract_error
        return _extract_error(text)

    def test_report_lines_dropped_fatal_kept(self):
        out = self._extract(_USER_FETCH_FAILURE)
        self.assertNotIn("[new branch]", out)
        self.assertNotIn("[new tag]", out)
        self.assertNotIn("(forced update)", out)
        self.assertNotIn("bcfd16a6..e93309f0", out)
        self.assertIn("From git.innophaseiot.com:skywalker/software/apu_uc", out)
        self.assertIn("Fetching submodule components/soc/helium-b0/npu", out)
        self.assertIn(
            "fatal: remote error: upload-pack: not our ref "
            "9739bef4cdc4a268bd6f53c57199c2a497c8f7a9", out)
        self.assertIn("\tcomponents/soc/helium-b0/npu", out)
        self.assertLess(len(out), 400,
                        "the box must shrink from ~13 KB to the real error")

    def test_output_without_report_lines_is_untouched(self):
        for text in (
            "fatal: could not read Username for 'https://github.com'",
            "CONFLICT (content): Merge conflict in a.txt",
            "error: pathspec 'x' did not match",
        ):
            self.assertEqual(self._extract(text), text, text)

    def test_report_only_output_still_yields_something(self):
        """A failure box must never come up empty."""
        out = self._extract(
            " * [new tag]  dev_v2.1  -> dev_v2.1\n"
            " * [new branch]  x  -> origin/x\n")
        self.assertTrue(out.strip())
        self.assertIn("[new tag]", out, "fallback keeps the raw tail")

    def test_empty_input_stays_empty(self):
        self.assertEqual(self._extract(""), "")

    def test_very_long_report_only_output_is_capped_to_the_tail(self):
        out = self._extract(
            "".join(f" * [new tag]  t{i} -> t{i}\n" for i in range(500)))
        self.assertLessEqual(len(out.splitlines()), 15)


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

    def test_no_abort_button_by_default(self):
        """Local ops, update checks, the pull stage: no dead button."""
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        dlg = self._dialog()
        self.assertIsNone(dlg.abort_btn)
        dlg.deleteLater()

    def test_abort_button_emits_once_then_disables(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        from lib.dialogs.confirmation_dialogs import ProgressDialog
        dlg = ProgressDialog("Git Fetching", "git fetch in progress...",
                             abortable=True)
        clicks = []
        dlg.abort_requested.connect(lambda: clicks.append(1))
        self.assertIsNotNone(dlg.abort_btn)
        self.assertTrue(dlg.abort_btn.isEnabled())
        dlg.abort_btn.click()
        self.assertEqual(clicks, [1])
        self.assertFalse(dlg.abort_btn.isEnabled(),
                         "Abort must be one-shot")
        self.assertEqual(dlg.label.text(), "Aborting...")
        dlg.abort_btn.click()
        self.assertEqual(clicks, [1], "a second click must do nothing")
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

    def test_failure_message_drops_sideband_report_lines(self):
        """A failed fetch/push reports the actual fatal error, not
        hundreds of ' * [new tag]' lines that bury it (the box used to
        carry ~13 KB of report chatter for a one-line submodule error)."""
        script = (
            "import sys\n"
            "sys.stderr.write(' * [new branch]        1030_ps_dev    "
            "-> origin/1030_ps_dev\\n')\n"
            "sys.stderr.write(' * [new tag]           dev_v2.1       "
            "-> dev_v2.1\\n')\n"
            "sys.stderr.write('Fetching submodule "
            "components/soc/helium-b0/npu\\n')\n"
            "sys.stderr.write('fatal: remote error: upload-pack: not our "
            "ref abc123def\\n')\n"
            "sys.stderr.write('Errors during submodule fetch:\\n')\n"
            "sys.stderr.write('\\tcomponents/soc/helium-b0/npu\\n')\n"
            "sys.exit(1)\n"
        )
        events = self._run(script)
        ok, out, err = events["finished"][0]
        self.assertFalse(ok)
        self.assertNotIn("[new branch]", err)
        self.assertNotIn("[new tag]", err)
        self.assertIn("Fetching submodule components/soc/helium-b0/npu", err)
        self.assertIn(
            "fatal: remote error: upload-pack: not our ref abc123def", err)
        self.assertIn("\tcomponents/soc/helium-b0/npu", err)

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

    def test_silent_child_is_stalled_out(self):
        """Option B: no total deadline, but total silence for `timeout`
        seconds means the remote is dead, not slow - kill it and say so."""
        events = self._run(_SLEEP_SCRIPT, timeout=1)
        ok, out, err = events["finished"][0]
        self.assertFalse(ok)
        self.assertIn("No response from remote after 1s", err)

    def test_child_talking_runs_past_the_old_deadline(self):
        """The whole point of dropping the 120s timeout: a command that keeps
        emitting output is never killed, no matter how long it runs - the
        timeout is only the silence window now."""
        import time as _time
        talkative = (
            "import sys, time\n"
            "for i in range(8):\n"
            "    sys.stderr.write('\\rReceiving objects: %3d%% (%d/8)'"
            " % (i * 13, i))\n"
            "    sys.stderr.flush()\n"
            "    time.sleep(0.4)\n"
            "sys.stdout.write('done\\n')\n"
            "sys.exit(0)\n"
        )
        t0 = _time.monotonic()
        events = self._run(talkative, timeout=1)
        elapsed = _time.monotonic() - t0
        ok, out, err = events["finished"][0]
        self.assertTrue(ok, (out, err))
        self.assertGreater(elapsed, 2.0,
                           "the script must outlive the 1s silence window")
        self.assertTrue(events["progress"],
                        "progress must flow the whole time")

    def test_abort_kills_the_child_quickly(self):
        """Abort ends a running command in a moment - not after some
        timeout - and reports the ABORTED sentinel, not an error."""
        import time as _time
        from lib.app_window.workers import GitWorker, ABORTED
        events = {"finished": []}
        worker = GitWorker([sys.executable, "-c", _SLEEP_SCRIPT], self.tmp,
                           timeout=30, progress=True)
        worker.git_finished.connect(
            lambda ok, out, err: events["finished"].append((ok, out, err)))
        worker.start()
        _time.sleep(0.3)             # let the child get going
        t0 = _time.monotonic()
        worker.abort()
        self.assertTrue(worker.wait(3000), "abort must end the worker fast")
        for _ in range(3):
            if QApplication.instance():
                QApplication.processEvents()
        elapsed = _time.monotonic() - t0
        self.assertEqual(events["finished"], [(False, "", ABORTED)])
        self.assertLess(elapsed, 3.0, f"abort took {elapsed:.1f}s")

    def test_abort_before_the_child_starts_is_honoured(self):
        """abort() racing ahead of Popen must still prevent the work."""
        import time as _time
        from lib.app_window.workers import GitWorker, ABORTED
        events = {"finished": []}
        worker = GitWorker([sys.executable, "-c", _SLEEP_SCRIPT], self.tmp,
                           timeout=30, progress=True)
        worker.git_finished.connect(
            lambda ok, out, err: events["finished"].append((ok, out, err)))
        worker.abort()               # before start()
        worker.start()
        self.assertTrue(worker.wait(5000))
        for _ in range(3):
            if QApplication.instance():
                QApplication.processEvents()
        self.assertEqual(events["finished"], [(False, "", ABORTED)])


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

    # --- abort wiring (option B) ------------------------------------------

    def _func(self, name):
        for func in self.funcs:
            if func.name == name:
                return func
        raise AssertionError(f"{name} must exist in reset_mixin")

    @staticmethod
    def _progress_dialog_calls(func):
        return [
            n for n in ast.walk(func)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == "ProgressDialog"
        ]

    @staticmethod
    def _abort_connects(func):
        return [
            n for n in ast.walk(func)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "connect"
            and isinstance(n.func.value, ast.Attribute)
            and n.func.value.attr == "abort_requested"
        ]

    def test_abort_button_at_the_three_user_abortable_sites(self):
        """fetch, the pull flow's fetch stage and push are abortable; the
        `git pull --rebase` stage must NOT be - killing it mid-flight
        would strand the repo mid-rebase."""
        for name in ("handle_git_fetch", "handle_git_pull",
                     "handle_git_push_force"):
            calls = self._progress_dialog_calls(self._func(name))
            self.assertEqual(len(calls), 1,
                             f"{name}: exactly one ProgressDialog expected")
            vals = [kw.value for kw in calls[0].keywords
                    if kw.arg == "abortable"]
            self.assertEqual(len(vals), 1, f"{name}: pass abortable=")
            self.assertIsInstance(vals[0], ast.Constant,
                                  f"{name}: abortable must be a literal")
            self.assertIs(vals[0].value, True,
                          f"{name}: abortable=True required")

        calls = self._progress_dialog_calls(self._func("_on_pull_fetch_finished"))
        self.assertEqual(len(calls), 1)
        for kw in calls[0].keywords:
            if kw.arg == "abortable":
                self.assertIsNot(getattr(kw.value, "value", None), True,
                                 "_on_pull_fetch_finished: the pull stage "
                                 "must not offer Abort")

    def test_abort_signal_reaches_worker_abort(self):
        for name in ("handle_git_fetch", "handle_git_pull",
                     "handle_git_push_force"):
            connects = self._abort_connects(self._func(name))
            self.assertEqual(len(connects), 1,
                             f"{name}: abort_requested must be connected "
                             "exactly once")
            dotted = ast.unparse(connects[0].args[0]) if connects[0].args else ""
            self.assertIn("worker.abort", dotted,
                          f"{name}: abort_requested must reach "
                          f"GitWorker.abort, got {dotted}")

        self.assertEqual(
            self._abort_connects(self._func("_on_pull_fetch_finished")), [],
            "the pull stage must not connect an Abort it does not offer")

    def test_handlers_recognise_the_aborted_sentinel(self):
        """Each finish handler must branch on ABORTED before failing or
        refreshing: an abort is informational and changes nothing."""
        for name in ("on_fetch_finished", "_on_pull_fetch_finished",
                     "_on_pull_finished", "on_push_finished"):
            func = self._func(name)
            compares = [
                n for n in ast.walk(func)
                if isinstance(n, ast.Compare)
                and isinstance(n.left, ast.Name) and n.left.id == "stderr"
                and any(isinstance(c, ast.Name) and c.id == "ABORTED"
                        for c in n.comparators)
            ]
            self.assertTrue(compares,
                            f"{name}: must compare stderr == ABORTED")


if __name__ == "__main__":
    unittest.main()
