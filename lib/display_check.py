"""Pre-flight graphical-display check.

Qt aborts the process (SIGABRT, not a Python exception) when no platform
plugin can initialize — e.g. a headless SSH session, or DISPLAY set but
authorization missing.  A Python ``try/except`` around ``QApplication()``
cannot catch this, so the check must happen *before* the QApplication is
created.  Call ``check_display()`` there so such cases exit cleanly with a
message instead.

Checks are cheap OS-specific heuristics (env vars / one small subprocess);
none of them instantiate Qt.  Returns ``(ok, message)`` and never raises.
"""
import ctypes
import ctypes.util
import os
import platform
import socket
import subprocess


def _check_windows():
    """Detect a headless Windows session (OpenSSH server / service).

    OpenSSH server runs sessions in the non-interactive ``Services``
    window station; ``Console`` (local) and ``RDP-Tcp#N`` (RDP) are
    interactive desktops where Qt can draw.
    """
    session = os.environ.get("SESSIONNAME", "")
    if session.upper() == "SERVICES" or os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
        return False, (
            "Cannot open a graphical display: this looks like an SSH or "
            "service session with no desktop.\n"
            "Run the tool in a local console or RDP session instead."
        )
    return True, ""


def _check_macos():
    """Detect a headless macOS session via ``launchctl managername``.

    Only an ``Aqua`` session has WindowServer access; an SSH session
    reports ``Background``.  Errors fall through to "assume ok" so a
    missing/failing ``launchctl`` never causes a false reject.
    """
    try:
        res = subprocess.run(
            ["launchctl", "managername"],
            capture_output=True, text=True, timeout=2,
            encoding="utf-8", errors="replace",
        )
        name = res.stdout.strip() if res.returncode == 0 else ""
    except Exception:
        return True, ""
    if name and name != "Aqua":
        return False, (
            f"Cannot open a graphical display: session type is {name!r} "
            "(no WindowServer access).\n"
            "Run the tool from a logged-in desktop session on this Mac."
        )
    return True, ""


def _check_linux():
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    if wayland_display:
        xdg = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        sock_path = os.path.join(xdg, wayland_display)
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                s.settimeout(0.2)
                s.connect(sock_path)
                return True, ""
            finally:
                s.close()
        except OSError:
            # Wayland display not reachable — fall through to X11 probe,
            # Qt may still fall back to xcb.
            pass

    display = os.environ.get("DISPLAY")
    if not display:
        return False, (
            "Cannot open a graphical display (no DISPLAY or WAYLAND_DISPLAY set).\n"
            "This is a GUI tool — run it on a desktop session, or use SSH "
            "X forwarding (ssh -X)."
        )

    # Real X11 probe: XOpenDisplay uses the same DISPLAY + XAUTHORITY path
    # as Qt's xcb plugin, so it also catches the "authorization required"
    # case where the X socket exists but auth fails.
    lib_name = ctypes.util.find_library("X11")
    if not lib_name:
        # libX11 unavailable — cannot probe; let Qt decide (current behavior).
        return True, ""
    try:
        lib = ctypes.CDLL(lib_name)
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        dpy = lib.XOpenDisplay(None)
        if dpy:
            lib.XCloseDisplay(dpy)
            return True, ""
        return False, (
            f"Cannot open a graphical display (DISPLAY={display!r}):\n"
            "the X server rejected the connection (it may require "
            "authorization, or it is not reachable).\n"
            "This is a GUI tool — run it on a desktop session, or use SSH "
            "X forwarding (ssh -X)."
        )
    except (OSError, AttributeError):
        # Cannot load libX11 — cannot probe; let Qt decide.
        return True, ""


def check_display():
    """Best-effort check that a GUI display can be opened.

    Returns (ok, message).  Never raises.  On failure, ``message`` explains
    the problem for the user.
    """
    if os.environ.get("QT_QPA_PLATFORM"):
        # Explicit Qt platform override (offscreen, vnc, ...) — skip probing.
        return True, ""

    system = platform.system()
    if system == "Windows":
        return _check_windows()
    if system == "Darwin":
        return _check_macos()
    return _check_linux()
