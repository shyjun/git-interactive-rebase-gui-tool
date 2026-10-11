"""Pre-flight graphical-display check (Linux only).

Qt aborts the process (SIGABRT, not a Python exception) when no platform
plugin can initialize — e.g. a headless SSH session, or DISPLAY set but
authorization missing.  Call ``check_display()`` before creating a
QApplication so such cases exit cleanly with a message instead.
"""
import ctypes
import ctypes.util
import os
import platform
import socket


def check_display():
    """Best-effort check that a GUI display can be opened.

    Returns (ok, message).  Never raises.  On failure, ``message`` explains
    the problem for the user.
    """
    if platform.system() != "Linux":
        return True, ""

    if os.environ.get("QT_QPA_PLATFORM"):
        # Explicit Qt platform override (offscreen, vnc, ...) — skip probing.
        return True, ""

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
