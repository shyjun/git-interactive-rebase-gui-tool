import os
import socket
import tempfile
import unittest
from unittest import mock

from lib.display_check import check_display


class TestCheckDisplay(unittest.TestCase):
    def _env(self, **overrides):
        return mock.patch.dict(os.environ, overrides, clear=False)

    def test_non_linux_skips(self):
        with mock.patch("platform.system", return_value="Windows"):
            ok, msg = check_display()
        self.assertTrue(ok)
        self.assertEqual(msg, "")

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


if __name__ == "__main__":
    unittest.main()
