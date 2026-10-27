import os
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.win_spawn import (  # noqa: E402
    CREATE_NO_WINDOW,
    _ensure_no_window,
    install,
)


class TestEnsureNoWindow(unittest.TestCase):
    def test_injects_on_windows(self):
        kwargs = _ensure_no_window({}, is_windows=True)
        self.assertEqual(kwargs, {"creationflags": CREATE_NO_WINDOW})
        self.assertEqual(CREATE_NO_WINDOW, 0x08000000)

    def test_no_inject_on_posix(self):
        self.assertEqual(_ensure_no_window({}, is_windows=False), {})

    def test_preserves_caller_creationflags(self):
        kwargs = {"creationflags": 0x8}
        self.assertIs(_ensure_no_window(kwargs, is_windows=True), kwargs)
        self.assertEqual(kwargs, {"creationflags": 0x8})

    def test_default_uses_platform_check(self):
        with mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(_ensure_no_window({}), {"creationflags": CREATE_NO_WINDOW})
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(_ensure_no_window({}), {})


class TestInstall(unittest.TestCase):
    def setUp(self):
        self._original_popen = subprocess.Popen

    def tearDown(self):
        subprocess.Popen = self._original_popen

    def test_install_patches_popen_once(self):
        install()
        patched = subprocess.Popen
        self.assertTrue(getattr(patched, "_quiet_spawn", False))
        install()  # idempotent — no second wrap
        self.assertIs(subprocess.Popen, patched)

    @unittest.skipIf(sys.platform == "win32", "POSIX rejects creationflags with ValueError")
    def test_flags_reach_subprocess_run(self):
        """Full funnel: patched Popen must inject flags into subprocess.run's call."""
        with mock.patch("lib.win_spawn._is_windows", return_value=True):
            install()
            with self.assertRaisesRegex(ValueError, "creationflags"):
                subprocess.run(["true"], capture_output=True)

    def test_run_still_works_patched_on_posix(self):
        install()
        result = subprocess.run(
            [sys.executable, "-c", "pass"],
            capture_output=True, check=True,
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
