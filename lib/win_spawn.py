"""Windows: keep child processes from flashing a console window.

Every ``git.exe`` we spawn is a console-subsystem binary.  When the tool
itself is not attached to a console (shortcut, pythonw, packaged exe),
Windows briefly creates a console window per child — the flicker seen
during startup.  The fix is the same as Rust's ``CREATE_NO_WINDOW``
creation flag: pass it to ``CreateProcess`` via ``creationflags``.

``subprocess.run``/``check_output``/``check_call`` all funnel through
``subprocess.Popen``, so patching ``Popen`` once covers every spawn site
(253 of them) without touching any caller.
"""

import subprocess
import sys

# Windows API value; the subprocess module only defines its own constant
# on Windows builds, so keep a literal fallback for POSIX (tests).
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _is_windows():
    return sys.platform == "win32"


def _ensure_no_window(kwargs, is_windows=None):
    """Add CREATE_NO_WINDOW on Windows unless the caller set its own flags."""
    if is_windows is None:
        is_windows = _is_windows()
    if is_windows and "creationflags" not in kwargs:
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return kwargs


def install():
    """Patch subprocess.Popen so every child gets CREATE_NO_WINDOW on Windows.

    Idempotent; on POSIX the wrapper injects nothing but the patch itself is
    harmless (subprocess rejects nonzero creationflags there, which is why
    the platform check happens at spawn time, not install time).
    """
    if getattr(subprocess.Popen, "_quiet_spawn", False):
        return
    base = subprocess.Popen

    class QuietPopen(base):
        _quiet_spawn = True

        def __init__(self, args, *popenargs, **kwargs):
            _ensure_no_window(kwargs)
            super().__init__(args, *popenargs, **kwargs)

    subprocess.Popen = QuietPopen
