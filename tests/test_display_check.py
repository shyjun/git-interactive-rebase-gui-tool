import os
import socket
import tempfile
import unittest
from unittest import mock

from lib.display_check import check_display


class TestCheckDisplay(unittest.TestCase):
    def _env(self, **overrides):
        return mock.patch.dict(os.environ, overrides, clear=False)

    def test_qt_platform_override_skips(self):
        with mock.patch("platform.system", return_value="Linux"):
            with self._env(QT_QPA_PLATFORM="offscreen", DISPLAY=":99"):
                ok, msg = check_display()
        self.assertTrue(ok)

    def test_linux_no_display_fails(self):
        with mock.patch("platform.system", return_value="Linux"):
            env = {"QT_QPA_PLATFORM": "", "WAYLAND_DISPLAY": "", "DISPLAY": ""}
            with mock.patch.dict(os.environ, env, clear=False):
                # Ensure vars are actually empty for the check
                for k in env:
                    if not env[k]:
                        os.environ.pop(k, None)
                ok, msg = check_display()
        self.assertFalse(ok)
        self.assertIn("DISPLAY", msg)

    def test_wayland_socket_ok(self):
        with tempfile.TemporaryDirectory() as xdg:
            sock_path = os.path.join(xdg, "wayland-0")
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            srv.bind(sock_path)
            srv.listen(1)
            try:
                with mock.patch("platform.system", return_value="Linux"):
                    env = {
                        "QT_QPA_PLATFORM": "",
                        "DISPLAY": "",
                        "WAYLAND_DISPLAY": "wayland-0",
                        "XDG_RUNTIME_DIR": xdg,
                    }
                    with mock.patch.dict(os.environ, env, clear=False):
                        for k in ("QT_QPA_PLATFORM", "DISPLAY"):
                            os.environ.pop(k, None)
                        ok, msg = check_display()
                self.assertTrue(ok, msg)
            finally:
                srv.close()

    def test_x11_open_display_null_fails(self):
        fake_lib = mock.MagicMock()
        fake_lib.XOpenDisplay.return_value = None
        with mock.patch("platform.system", return_value="Linux"):
            with mock.patch("ctypes.util.find_library", return_value="libX11.so.6"):
                with mock.patch("ctypes.CDLL", return_value=fake_lib):
                    env = {"QT_QPA_PLATFORM": "", "WAYLAND_DISPLAY": "", "DISPLAY": ":1"}
                    with mock.patch.dict(os.environ, env, clear=False):
                        os.environ.pop("QT_QPA_PLATFORM", None)
                        os.environ.pop("WAYLAND_DISPLAY", None)
                        ok, msg = check_display()
        self.assertFalse(ok)
        self.assertIn(":1", msg)

    def test_x11_open_display_ok(self):
        fake_lib = mock.MagicMock()
        fake_lib.XOpenDisplay.return_value = 12345  # non-NULL
        with mock.patch("platform.system", return_value="Linux"):
            with mock.patch("ctypes.util.find_library", return_value="libX11.so.6"):
                with mock.patch("ctypes.CDLL", return_value=fake_lib):
                    env = {"QT_QPA_PLATFORM": "", "WAYLAND_DISPLAY": "", "DISPLAY": ":0"}
                    with mock.patch.dict(os.environ, env, clear=False):
                        os.environ.pop("QT_QPA_PLATFORM", None)
                        os.environ.pop("WAYLAND_DISPLAY", None)
                        ok, msg = check_display()
        self.assertTrue(ok, msg)
        fake_lib.XCloseDisplay.assert_called_once_with(12345)

    def test_missing_libx11_falls_through(self):
        with mock.patch("platform.system", return_value="Linux"):
            with mock.patch("ctypes.util.find_library", return_value=None):
                env = {"QT_QPA_PLATFORM": "", "WAYLAND_DISPLAY": "", "DISPLAY": ":1"}
                with mock.patch.dict(os.environ, env, clear=False):
                    os.environ.pop("QT_QPA_PLATFORM", None)
                    os.environ.pop("WAYLAND_DISPLAY", None)
                    ok, msg = check_display()
        self.assertTrue(ok)


class TestCheckDisplayWindows(unittest.TestCase):
    def _check(self, **env):
        with mock.patch("platform.system", return_value="Windows"):
            with mock.patch.dict(os.environ, env, clear=False):
                for k in ("QT_QPA_PLATFORM", "SSH_CONNECTION", "SSH_CLIENT", "SESSIONNAME"):
                    if k not in env:
                        os.environ.pop(k, None)
                return check_display()

    def test_services_session_fails(self):
        ok, msg = self._check(SESSIONNAME="Services")
        self.assertFalse(ok)
        self.assertIn("SSH", msg)

    def test_ssh_connection_fails(self):
        ok, msg = self._check(SSH_CONNECTION="1.2.3.4 5 6.7.8.9 22")
        self.assertFalse(ok)

    def test_console_session_passes(self):
        ok, msg = self._check(SESSIONNAME="Console")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_rdp_session_passes(self):
        ok, msg = self._check(SESSIONNAME="RDP-Tcp#3")
        self.assertTrue(ok)


class TestCheckDisplayMacOS(unittest.TestCase):
    def _check(self, managername="Aqua", rc=0, raises=False):
        res = mock.MagicMock()
        res.returncode = rc
        res.stdout = managername + "\n"
        run = mock.MagicMock(side_effect=Exception("boom") if raises else None, return_value=res)
        with mock.patch("platform.system", return_value="Darwin"):
            with mock.patch.dict(os.environ, {"QT_QPA_PLATFORM": ""}, clear=False):
                os.environ.pop("QT_QPA_PLATFORM", None)
                with mock.patch("subprocess.run", run):
                    return check_display()

    def test_aqua_session_passes(self):
        ok, msg = self._check(managername="Aqua")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_background_session_fails(self):
        ok, msg = self._check(managername="Background")
        self.assertFalse(ok)
        self.assertIn("WindowServer", msg)

    def test_launchctl_error_passes(self):
        ok, msg = self._check(raises=True)
        self.assertTrue(ok)

    def test_launchctl_nonzero_passes(self):
        ok, msg = self._check(managername="", rc=1)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
