import contextlib
import io
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False

if HAS_PYSIDE:
    from lib.app_window.helpers import mono_font
    from lib.crash_report import (
        GITHUB_NEW_ISSUE_URL,
        CrashDialog,
        format_crash_report,
        install_excepthook,
    )

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _raised():
    try:
        raise ValueError("boom")
    except ValueError:
        return sys.exc_info()


class TestCrashReportFormat(unittest.TestCase):

    def test_report_contains_environment_and_traceback(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        exc_type, exc_value, tb = _raised()
        report = format_crash_report(exc_type, exc_value, tb)
        self.assertIn("Git Interactive Rebase GUI — crash report", report)
        self.assertIn("Tool version:", report)
        self.assertIn(f"Python: {sys.version.splitlines()[0]}", report)
        self.assertIn("Platform:", report)
        self.assertIn("Exception: ValueError: boom", report)
        self.assertIn("Traceback (most recent call last)", report)
        self.assertIn("raise ValueError(\"boom\")", report)


class TestGlobalExceptionHandler(unittest.TestCase):

    def setUp(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        if not QApplication.instance():
            type(self)._app = QApplication([])
        self._prev_hooks = (sys.excepthook, threading.excepthook)
        install_excepthook()

    def tearDown(self):
        sys.excepthook, threading.excepthook = self._prev_hooks

    def test_unhandled_exception_reaches_global_handler(self):
        self.assertIsNot(sys.excepthook, sys.__excepthook__)
        with mock.patch("lib.crash_report.show_crash_dialog") as show_dialog:
            with contextlib.redirect_stderr(io.StringIO()) as err:
                try:
                    raise RuntimeError("kaboom")
                except RuntimeError:
                    sys.excepthook(*sys.exc_info())
        show_dialog.assert_called_once()
        report = show_dialog.call_args[0][0]
        self.assertIn("RuntimeError: kaboom", report)
        self.assertIn("Traceback (most recent call last)", report)
        self.assertIn("RuntimeError: kaboom", err.getvalue())

    def test_python_itself_routes_uncaught_exception_to_hook(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "report.txt")
            code = (
                "import sys\n"
                f"sys.path.insert(0, {REPO_ROOT!r})\n"
                "import lib.crash_report as cr\n"
                "cr.install_excepthook()\n"
                "cr.show_crash_dialog = lambda report: open(sys.argv[1], 'w').write(report)\n"
                "raise RuntimeError('subprocess-boom')\n"
            )
            proc = subprocess.run(
                [sys.executable, "-c", code, out_path],
                capture_output=True, text=True, timeout=120,
                cwd=REPO_ROOT,
                env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            )
            self.assertEqual(proc.returncode, 1, proc.stderr)
            with open(out_path, encoding="utf-8") as f:
                report = f.read()
        self.assertIn("RuntimeError: subprocess-boom", report)
        self.assertIn("Traceback (most recent call last)", report)
        self.assertIn("RuntimeError: subprocess-boom", proc.stderr)

    def test_worker_thread_exception_is_reported_to_stderr(self):
        with mock.patch("lib.crash_report.show_crash_dialog") as show_dialog:
            with contextlib.redirect_stderr(io.StringIO()) as err:

                def boom():
                    raise OSError("thread boom")

                worker = threading.Thread(target=boom, name="crash-test-worker")
                worker.start()
                worker.join(timeout=30)
        # The dialog must never be shown directly from a worker thread.
        show_dialog.assert_not_called()
        self.assertIn("OSError: thread boom", err.getvalue())
        self.assertIn("Source: background thread 'crash-test-worker'",
                      err.getvalue())

    def test_handled_exception_does_not_show_crash_dialog(self):
        with mock.patch("lib.crash_report.show_crash_dialog") as show_dialog:
            with contextlib.redirect_stderr(io.StringIO()):
                try:
                    raise ValueError("handled")
                except ValueError:
                    pass
        show_dialog.assert_not_called()

    def test_existing_error_path_still_behaves_unchanged(self):
        from lib.git_helpers import get_head_sha
        with mock.patch("lib.crash_report.show_crash_dialog") as show_dialog:
            with contextlib.redirect_stderr(io.StringIO()):
                result = get_head_sha("/nonexistent/path/for/crash/report")
        self.assertEqual(result, "Unknown")
        show_dialog.assert_not_called()


class TestCrashDialog(unittest.TestCase):

    def setUp(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")
        if not QApplication.instance():
            type(self)._app = QApplication([])
        self.exc_type, self.exc_value, self.tb = _raised()
        self.report = format_crash_report(self.exc_type, self.exc_value,
                                          self.tb)

    def test_traceback_is_displayed_read_only(self):
        dialog = CrashDialog(self.report)
        shown = dialog.text_area.toPlainText()
        self.assertEqual(shown, self.report)
        self.assertIn("Traceback (most recent call last)", shown)
        self.assertIn("Exception: ValueError: boom", shown)
        self.assertTrue(dialog.text_area.isReadOnly())
        self.assertIn("crashed unexpectedly", dialog.message_label.text())
        self.assertIn("report this as a bug on GitHub",
                      dialog.message_label.text())

    def test_text_area_uses_main_window_font(self):
        settings = QSettings("shyjun", "GitInteractiveRebase")
        expected = mono_font(
            int(settings.value("font_size", 10)),
            family=settings.value("font_family", None))
        dialog = CrashDialog(self.report)
        font = dialog.text_area.font()
        self.assertEqual(font.family(), expected.family())
        self.assertEqual(font.pointSize(), expected.pointSize())

    def test_copy_to_clipboard_contains_traceback(self):
        dialog = CrashDialog(self.report)
        QApplication.clipboard().clear()
        dialog.copy_button.click()
        self.assertEqual(QApplication.clipboard().text(), self.report)
        self.assertIn("Traceback (most recent call last)",
                      QApplication.clipboard().text())

    def test_github_issue_button_opens_expected_url(self):
        dialog = CrashDialog(self.report)
        with mock.patch("lib.crash_report.webbrowser.open") as open_url:
            dialog.issue_button.click()
        open_url.assert_called_once()
        url = open_url.call_args[0][0]
        self.assertTrue(url.startswith(GITHUB_NEW_ISSUE_URL + "?"), url)
        query = parse_qs(urlparse(url).query)
        self.assertIn("ValueError: boom", query["title"][0])
        self.assertEqual(query["body"][0], self.report)

    def test_close_button_closes_dialog(self):
        dialog = CrashDialog(self.report)
        dialog.close_button.click()
        self.assertFalse(dialog.isVisible())


if __name__ == "__main__":
    unittest.main()
