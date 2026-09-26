import glob
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PySide6.QtWidgets import QApplication, QDialog
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False

if HAS_PYSIDE:
    from lib import unclean_exit
    from lib.crash_report import GITHUB_NEW_ISSUE_URL

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


class _UncleanExitBase(unittest.TestCase):

    def setUp(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        if not QApplication.instance():
            type(self)._app = QApplication([])
        self._tmpdir = tempfile.TemporaryDirectory(prefix="unclean_exit_test_")
        self._old_marker_dir = os.environ.get("GIT_REBASE_GUI_MARKER_DIR")
        os.environ["GIT_REBASE_GUI_MARKER_DIR"] = self._tmpdir.name
        unclean_exit._current_marker_path = None
        self._children = []

    def tearDown(self):
        for child in self._children:
            try:
                child.kill()
                child.wait(timeout=5)
            except Exception:
                pass
        try:
            unclean_exit.cleanup_current_marker()
        except Exception:
            pass
        if self._old_marker_dir is None:
            os.environ.pop("GIT_REBASE_GUI_MARKER_DIR", None)
        else:
            os.environ["GIT_REBASE_GUI_MARKER_DIR"] = self._old_marker_dir
        self._tmpdir.cleanup()

    def _spawn_live_child(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self._children.append(proc)
        return proc

    def _write_marker(self, pid, **overrides):
        marker = {
            "pid": pid,
            "tool_version": "deadbeef",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "executable": sys.executable,
            "working_directory": "/somewhere",
            "command_line": [sys.executable, "-m", "fake"],
        }
        marker.update(overrides)
        path = os.path.join(self._tmpdir.name, f"git-interactive-rebase-gui-{pid}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(marker, handle)
        return path

    def _marker_files(self):
        return sorted(glob.glob(os.path.join(self._tmpdir.name, "*.json")))

    def _own_marker_path(self):
        return os.path.join(
            self._tmpdir.name, f"git-interactive-rebase-gui-{os.getpid()}.json"
        )


class TestNormalStartAndExit(_UncleanExitBase):

    def test_marker_created_with_expected_fields(self):
        with mock.patch.object(unclean_exit, "show_previous_run_notification"):
            unclean_exit.install_unclean_exit_detection()
        path = self._own_marker_path()
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as handle:
            marker = json.load(handle)
        self.assertEqual(marker["pid"], os.getpid())
        for field in ("tool_version", "started_at", "executable",
                      "working_directory", "command_line"):
            self.assertIn(field, marker)

    def test_marker_removed_on_normal_exit_and_no_notification(self):
        with mock.patch.object(unclean_exit, "show_previous_run_notification") as show:
            unclean_exit.install_unclean_exit_detection()
            self.assertTrue(os.path.exists(self._own_marker_path()))
            unclean_exit.cleanup_current_marker()
            self.assertFalse(os.path.exists(self._own_marker_path()))
            unclean_exit.cleanup_current_marker()  # idempotent
            unclean_exit.install_unclean_exit_detection()
            show.assert_not_called()

    def test_own_marker_never_reported_as_stale(self):
        with mock.patch.object(unclean_exit, "show_previous_run_notification") as show:
            unclean_exit.install_unclean_exit_detection()
            # Simulate an unexpected re-install in the same process.
            unclean_exit.install_unclean_exit_detection()
            show.assert_not_called()


class TestStaleDetection(_UncleanExitBase):

    def test_dead_pid_marker_triggers_one_notification(self):
        pid = _dead_pid()
        path = self._write_marker(pid)
        with mock.patch.object(unclean_exit, "show_previous_run_notification") as show:
            unclean_exit.install_unclean_exit_detection()
        show.assert_called_once()
        entries = show.call_args[0][0]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["pid"], pid)
        self.assertFalse(os.path.exists(path))
        self.assertTrue(os.path.exists(self._own_marker_path()))

    def test_multiple_stale_markers_single_notification(self):
        pids = [_dead_pid() for _ in range(3)]
        paths = [self._write_marker(pid) for pid in pids]
        with mock.patch.object(unclean_exit, "show_previous_run_notification") as show:
            unclean_exit.install_unclean_exit_detection()
        show.assert_called_once()
        entries = show.call_args[0][0]
        self.assertEqual(sorted(e["pid"] for e in entries), sorted(pids))
        for path in paths:
            self.assertFalse(os.path.exists(path))

    def test_running_instances_not_reported(self):
        first = self._spawn_live_child()
        second = self._spawn_live_child()
        path_one = self._write_marker(first.pid)
        path_two = self._write_marker(second.pid)
        with mock.patch.object(unclean_exit, "show_previous_run_notification") as show:
            unclean_exit.install_unclean_exit_detection()
        show.assert_not_called()
        self.assertTrue(os.path.exists(path_one))
        self.assertTrue(os.path.exists(path_two))

    def test_pid_reuse_by_other_process_reported_stale(self):
        child = self._spawn_live_child()
        path = self._write_marker(
            child.pid,
            started_at=time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 3600)
            ),
            executable="/nonexistent/other-app",
        )
        with mock.patch.object(unclean_exit, "show_previous_run_notification") as show:
            unclean_exit.install_unclean_exit_detection()
        show.assert_called_once()
        self.assertEqual(show.call_args[0][0][0]["pid"], child.pid)
        self.assertFalse(os.path.exists(path))

    def test_corrupt_marker_ignored_not_deleted_and_no_notification(self):
        pid = _dead_pid()
        path = os.path.join(self._tmpdir.name, f"git-interactive-rebase-gui-{pid}.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not valid json")
        with mock.patch.object(unclean_exit, "show_previous_run_notification") as show:
            unclean_exit.install_unclean_exit_detection()
        show.assert_not_called()
        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.exists(self._own_marker_path()))


class TestFailureAndDisabled(_UncleanExitBase):

    def test_marker_creation_failure_is_swallowed(self):
        with mock.patch.object(
            unclean_exit, "_create_marker", side_effect=OSError("disk full")
        ):
            unclean_exit.install_unclean_exit_detection()  # must not raise
        self.assertIsNone(unclean_exit._current_marker_path)

    def test_disabled_feature_does_nothing(self):
        pid = _dead_pid()
        path = self._write_marker(pid)
        with mock.patch.object(unclean_exit, "ENABLE_UNCLEAN_EXIT_DETECTION", False), \
                mock.patch.object(unclean_exit, "_scan_markers") as scan, \
                mock.patch.object(unclean_exit, "_create_marker") as create, \
                mock.patch.object(unclean_exit, "show_previous_run_notification") as show:
            unclean_exit.install_unclean_exit_detection()
        scan.assert_not_called()
        create.assert_not_called()
        show.assert_not_called()
        self.assertIsNone(unclean_exit._current_marker_path)
        self.assertTrue(os.path.exists(path))  # no scan, no cleanup
        self.assertEqual(self._marker_files(), [path])

    def test_install_survives_scan_failure(self):
        with mock.patch.object(
            unclean_exit, "_scan_markers", side_effect=RuntimeError("boom")
        ):
            unclean_exit.install_unclean_exit_detection()  # must not raise
        self.assertTrue(os.path.exists(self._own_marker_path()))


class TestSigkilledSubprocess(_UncleanExitBase):

    def test_sigkill_leaves_marker_and_next_run_reports_it(self):
        script = (
            "import os, sys\n"
            f"sys.path.insert(0, {REPO_ROOT!r})\n"
            "from lib.unclean_exit import install_unclean_exit_detection\n"
            "install_unclean_exit_detection()\n"
            "os.kill(os.getpid(), 9)\n"
        )
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            env=env,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _, stderr = proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, -9, stderr)
        leftover = [
            path for path in self._marker_files()
            if not path.endswith(f"-{os.getpid()}.json")
        ]
        self.assertEqual(len(leftover), 1, leftover)
        with open(leftover[0], encoding="utf-8") as handle:
            marker = json.load(handle)
        self.assertEqual(marker["pid"], proc.pid)

        with mock.patch.object(unclean_exit, "show_previous_run_notification") as show:
            unclean_exit.install_unclean_exit_detection()
        show.assert_called_once()
        entries = show.call_args[0][0]
        self.assertEqual(entries[0]["pid"], proc.pid)
        self.assertFalse(os.path.exists(leftover[0]))


class TestNotificationDialog(_UncleanExitBase):

    def test_details_format_single_instance(self):
        entry = {
            "path": "/x/git-interactive-rebase-gui-42.json",
            "pid": 42,
            "marker": {
                "tool_version": "abc123",
                "working_directory": "/repo",
                "command_line": ["/usr/bin/python3", "tool.py"],
                "started_at": "2026-09-26T10:00:00",
            },
        }
        details = unclean_exit._format_notification_details([entry])
        self.assertIn("Previous instance", details)
        self.assertNotIn("#1", details)
        self.assertIn("Tool version: abc123", details)
        self.assertIn("Location: /repo", details)
        self.assertIn("Command: /usr/bin/python3 tool.py", details)
        self.assertIn("Started: 2026-09-26T10:00:00", details)
        self.assertIn("PID: 42", details)

    def test_details_format_multiple_instances_separated(self):
        entries = [
            {"path": "a", "pid": 1, "marker": {}},
            {"path": "b", "pid": 2, "marker": {}},
        ]
        details = unclean_exit._format_notification_details(entries)
        self.assertIn("Previous instance #1", details)
        self.assertIn("Previous instance #2", details)
        self.assertIn("-" * 48, details)

    def test_dialog_buttons_and_wording(self):
        dialog = unclean_exit._build_notification_dialog("DETAILS-HERE")
        self.assertEqual(dialog.windowTitle(), "Previous Run")
        self.assertEqual(dialog.open_button.text(), "Open GitHub Issues")
        self.assertEqual(dialog.noted_button.text(), "Noted. Continue")
        self.assertIn("did not exit normally", unclean_exit.NOTIFICATION_MESSAGE)
        self.assertEqual(dialog.details_area.toPlainText(), "DETAILS-HERE")
        dialog.deleteLater()

    def test_noted_button_dismisses_dialog(self):
        dialog = unclean_exit._build_notification_dialog("x")
        dialog.noted_button.click()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        dialog.deleteLater()

    def test_open_github_issues_button_opens_issue_url(self):
        with mock.patch.object(unclean_exit.webbrowser, "open") as open_url:
            unclean_exit._open_github_issues()
        open_url.assert_called_once_with(GITHUB_NEW_ISSUE_URL)

    def test_show_notification_never_raises(self):
        with mock.patch.object(
            unclean_exit, "_build_notification_dialog", side_effect=RuntimeError("boom")
        ):
            unclean_exit.show_previous_run_notification([])  # must not raise


if __name__ == "__main__":
    unittest.main()
