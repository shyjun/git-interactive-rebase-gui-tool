import io
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import lib.logger as logger
from lib.logger import _log


class _BrokenStream:
    """A stream whose writes fail the way a dead terminal pty does."""

    def __init__(self, err=OSError(5, "Input/output error")):
        self.err = err

    def write(self, _data):
        raise self.err

    def flush(self):
        raise self.err


class TestLoggerResilience(unittest.TestCase):
    """_log must never raise: a background-forked tool whose launching
    terminal was closed gets Errno 5 (EIO) on every stdout write."""

    def setUp(self):
        self._saved = (sys.stdout, sys.stderr,
                       logger._VERBOSE, logger._BROKEN)
        logger._VERBOSE = False
        logger._BROKEN = False

    def tearDown(self):
        sys.stdout, sys.stderr, logger._VERBOSE, logger._BROKEN = self._saved

    def test_broken_stdout_falls_back_to_stderr(self):
        sys.stdout = _BrokenStream()
        captured = io.StringIO()
        sys.stderr = captured
        _log("hello from the tool")
        self.assertIn("hello from the tool", captured.getvalue())
        self.assertFalse(logger._BROKEN)

    def test_broken_stdout_and_stderr_disables_logging(self):
        sys.stdout = _BrokenStream()
        sys.stderr = _BrokenStream()
        _log("first")
        self.assertTrue(logger._BROKEN)
        # stdio rebound to devnull so interpreter shutdown's flush is clean.
        self.assertEqual(sys.stdout.name, os.devnull)
        self.assertEqual(sys.stderr.name, os.devnull)
        # Subsequent calls are silent no-ops and still must not raise.
        _log("second")

    def test_logging_disabled_is_zero_cost_noop(self):
        logger._BROKEN = True
        sys.stdout = _BrokenStream()
        _log("never printed")

    def test_verbose_filter_unchanged(self):
        logger._VERBOSE = False
        captured = io.StringIO()
        sys.stdout = captured
        _log("[perf] tagged and silent")
        _log("[rescan] also silent")
        _log("untagged startup message")
        _log("[rescan] FAILED something")
        out = captured.getvalue()
        self.assertNotIn("tagged and silent", out)
        self.assertNotIn("also silent", out)
        self.assertIn("untagged startup message", out)
        self.assertIn("FAILED something", out)

    def test_verbose_mode_prints_tagged(self):
        logger._VERBOSE = True
        captured = io.StringIO()
        sys.stdout = captured
        _log("[perf] now visible")
        self.assertIn("now visible", captured.getvalue())


class TestLoggerE2EPty(unittest.TestCase):
    """End-to-end on a real pty: closing the master simulates the user's
    exact repro — start tool in tilix, close tilix, click refresh."""

    def _spawn(self, child_code, both_on_pty=False):
        import subprocess
        import pty
        import time

        master, slave = pty.openpty()
        if both_on_pty:
            # stdout AND stderr on the same pty — the real tilix scenario.
            proc = subprocess.Popen(
                [sys.executable, "-c", child_code],
                stdin=subprocess.PIPE, stdout=slave, stderr=slave,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            )
        else:
            proc = subprocess.Popen(
                [sys.executable, "-c", child_code],
                stdin=subprocess.PIPE, stdout=slave, stderr=subprocess.PIPE,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            )
        os.close(slave)
        try:
            time.sleep(0.5)                  # let the first _log land
            os.close(master)                 # simulate closing tilix
            proc.stdin.write(b"go\n")
            proc.stdin.flush()
            proc.stdin.close()
            stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
            rc = proc.wait(timeout=15)
        finally:
            proc.kill()
            proc.wait()
            try:
                os.close(master)
            except OSError:
                pass
        return rc, stderr

    def test_repro_both_streams_on_closed_pty(self):
        """User's repro: tool's stdout+stderr both on the tilix pty; tilix
        closes; next _log must not crash the app and exit must stay clean."""
        code = (
            "import sys, time\n"
            "from lib.logger import _log\n"
            "_log('before close')\n"
            "sys.stdin.readline()\n"
            "_log('after close - must not crash')\n"
            "sys.exit(0)\n"
        )
        rc, _stderr = self._spawn(code, both_on_pty=True)
        self.assertEqual(rc, 0, "tool crashed after its pty master closed")

    def test_fallback_message_reaches_live_stderr(self):
        """When only stdout's pty died but stderr is alive, the log line
        must still be delivered via the stderr fallback."""
        code = (
            "import sys\n"
            "from lib.logger import _log\n"
            "_log('before close')\n"
            "sys.stdin.readline()\n"
            "_log('after close - must not crash')\n"
            "print('SURVIVED', file=sys.stderr)\n"
        )
        rc, stderr = self._spawn(code)
        self.assertIn("after close - must not crash", stderr)
        self.assertIn("SURVIVED", stderr)
        # rc 120 = CPython's exit code when flushing the still-dead stdout at
        # interpreter shutdown (no rebind — stderr fallback kept it alive).
        self.assertIn(rc, (0, 120), f"unexpected rc={rc}, stderr={stderr!r}")


if __name__ == "__main__":
    unittest.main()
