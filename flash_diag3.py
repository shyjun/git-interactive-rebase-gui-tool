#!/usr/bin/env python3
"""flash_diag v3 - event-driven window/process tracer for the startup-flash mystery.

Usage (same args you'd give the tool):
    python flash_diag.py [tool args...]

Writes flash_diag.log next to this script. Press Enter when you SEE a flash
to drop a USER MARK in the log. Delete this file + log when done.
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading
import time
import traceback

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flash_diag.log")
_logf = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
_lock = threading.Lock()
T0 = time.perf_counter()
_stop = threading.Event()


def wlog(msg):
    dt = time.perf_counter() - T0
    with _lock:
        _logf.write(f"{dt:10.3f} {msg}\n")


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

OBJID_WINDOW = 0
EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_CREATE = 0x8000
EVENT_OBJECT_DESTROY = 0x8001
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_HIDE = 0x8003
WINEVENT_OUTOFCONTEXT = 0x0000
WS_CHILD = 0x40000000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GA_ROOT = 2
GWL_STYLE = -16
GWL_EXSTYLE = -20
PM_REMOVE = 1
WM_QUIT = 0x0012

WINEVENTPROC = ctypes.WINFUNCTYPE(
    None, wt.HANDLE, wt.DWORD, wt.HWND, wt.LONG, wt.LONG, wt.DWORD, wt.DWORD
)
ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

user32.SetWinEventHook.argtypes = [wt.DWORD, wt.DWORD, wt.HANDLE, WINEVENTPROC,
                                   wt.DWORD, wt.DWORD, wt.DWORD]
user32.SetWinEventHook.restype = wt.HANDLE
user32.UnhookWinEvent.argtypes = [wt.HANDLE]
user32.UnhookWinEvent.restype = wt.BOOL
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetClassNameW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL
user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
user32.GetAncestor.restype = wt.HWND
user32.GetParent.argtypes = [wt.HWND]
user32.GetParent.restype = wt.HWND
user32.EnumWindows.argtypes = [ENUMPROC, wt.LPARAM]
user32.EnumWindows.restype = wt.BOOL
user32.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
user32.PeekMessageW.restype = wt.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_wchar_p,
                                                ctypes.POINTER(wt.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wt.BOOL
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.GetTickCount.restype = wt.DWORD


def proc_name(pid):
    if not pid:
        return "?"
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return f"?pid{pid}"
    try:
        buf = ctypes.create_unicode_buffer(512)
        n = wt.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return os.path.basename(buf.value)
        return f"?pid{pid}"
    finally:
        kernel32.CloseHandle(h)


def win_info(hwnd):
    tid_pid = wt.DWORD(0)
    tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid_pid))
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title, 512)
    style = user32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF
    root = user32.GetAncestor(hwnd, GA_ROOT)
    parent = user32.GetParent(hwnd)
    return tid, tid_pid.value, cls.value, title.value, style, ex, root, parent


EVENT_NAMES = {
    EVENT_SYSTEM_FOREGROUND: "FOREGROUND",
    EVENT_OBJECT_CREATE: "CREATE",
    EVENT_OBJECT_DESTROY: "DESTROY",
    EVENT_OBJECT_SHOW: "SHOW",
    EVENT_OBJECT_HIDE: "HIDE",
}
_hook_seen = set()
_samp_seen = set()


def _handle_event(event, hwnd, id_object, thread_id, ts_ms):
    if id_object != OBJID_WINDOW:
        return
    name = EVENT_NAMES.get(event, hex(event))
    alive = bool(user32.IsWindow(hwnd))
    if not alive:
        if event == EVENT_OBJECT_DESTROY and hwnd in _hook_seen:
            wlog(f"WEV {name:10} hwnd={hwnd:#010x} (dead)")
        return
    vis = bool(user32.IsWindowVisible(hwnd))
    style = user32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF
    is_child = bool(style & WS_CHILD)
    # Noise filters: skip invisible child-window churn; keep anything visible/top-level.
    if event in (EVENT_OBJECT_CREATE, EVENT_OBJECT_HIDE) and is_child and not vis:
        return
    if event == EVENT_OBJECT_DESTROY and hwnd not in _hook_seen:
        return
    _hook_seen.add(hwnd)
    tid, pid, cls, title, style, ex, root, parent = win_info(hwnd)
    lag = (kernel32.GetTickCount() - ts_ms) & 0xFFFFFFFF
    wlog(
        f"WEV {name:10} hwnd={hwnd:#010x} cls='{cls}' title={title!r} "
        f"pid={pid} proc='{proc_name(pid)}' tid={tid} style={style:#010x} "
        f"ex={ex:#010x} root={root:#010x} parent={parent:#010x} "
        f"vis={int(vis)} child={int(is_child)} evt_tid={thread_id} lag_ms={lag}"
    )


def _hook_thread():
    @WINEVENTPROC
    def cb(hook, event, hwnd, id_object, id_child, thread_id, ts_ms):
        try:
            _handle_event(event, hwnd, id_object, thread_id, ts_ms)
        except Exception as e:
            wlog(f"WEV callback error: {e!r}")

    global _cb_ref
    _cb_ref = cb  # prevent GC while hook is active
    hooks = []
    for lo, hi in ((EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND),
                   (EVENT_OBJECT_CREATE, EVENT_OBJECT_HIDE)):
        h = user32.SetWinEventHook(lo, hi, 0, cb, 0, 0, WINEVENT_OUTOFCONTEXT)
        hooks.append(h)
        wlog(f"WinEventHook {name_range(lo)} installed={bool(h)}")
    if not any(hooks):
        wlog("WARNING: no WinEvent hooks installed - sampler only")
    msg = wt.MSG()
    while not _stop.is_set():
        while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, PM_REMOVE):
            if msg.message == WM_QUIT:
                return
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.001)
    for h in hooks:
        if h:
            user32.UnhookWinEvent(h)


def name_range(lo):
    return EVENT_NAMES.get(lo, hex(lo))


def _sampler_thread():
    """Backup: 5ms poll of visible top-level windows; logs only NEW hwnds."""
    def cb(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and not (user32.GetWindowLongW(hwnd, GWL_STYLE) & WS_CHILD):
            if hwnd not in _samp_seen and hwnd not in _hook_seen:
                _samp_seen.add(hwnd)
                tid, pid, cls, title, style, ex, root, parent = win_info(hwnd)
                wlog(
                    f"SAMP NEW      hwnd={hwnd:#010x} cls='{cls}' title={title!r} "
                    f"pid={pid} proc='{proc_name(pid)}' tid={tid} "
                    f"style={style:#010x} ex={ex:#010x}"
                )
        return True

    enum_cb = ENUMPROC(cb)
    while not _stop.is_set():
        try:
            user32.EnumWindows(enum_cb, 0)
        except Exception as e:
            wlog(f"SAMP error: {e!r}")
        time.sleep(0.005)


def _marker_thread():
    try:
        for line in sys.stdin:
            wlog(f"USER MARK: {line.strip()!r}")
    except Exception:
        pass


# --- subprocess spawn logger (same injection as the tool's fix, plus stack traces)
_orig_popen_init = None


def _is_git_args(args):
    try:
        if isinstance(args, (list, tuple)) and args:
            return os.path.basename(str(args[0])).lower() in ("git", "git.exe")
    except Exception:
        pass
    return False


def _install_popen_logger():
    global _orig_popen_init
    import subprocess
    _orig_popen_init = subprocess.Popen.__init__

    class QuietPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            if os.name == "nt" and "creationflags" not in kwargs:
                kwargs["creationflags"] = 0x08000000
            _orig_popen_init(self, *args, **kwargs)
            a = args[0] if args else kwargs.get("args")
            cf = kwargs.get("creationflags", 0)
            shell = bool(kwargs.get("shell"))
            extra = ""
            if not _is_git_args(a):
                stack = "".join(traceback.format_stack(limit=10)[:-1])
                extra = f" shell={int(shell)}\n    stack:\n{stack}"
            wlog(f"SPAWN pid={self.pid} args={a!r} cf={cf}{extra}")

    subprocess.Popen = QuietPopen


def main():
    wlog(f"=== flash_diag v3 start pid={os.getpid()} py={sys.version.split()[0]} "
         f"argv={sys.argv!r} stdin_tty={bool(sys.stdin and sys.stdin.isatty())} ===")
    _install_popen_logger()
    threading.Thread(target=_hook_thread, daemon=True, name="winevent").start()
    threading.Thread(target=_sampler_thread, daemon=True, name="sampler").start()
    if sys.stdin and sys.stdin.isatty():
        threading.Thread(target=_marker_thread, daemon=True, name="marker").start()
        wlog("Press Enter in this console each time you SEE a flash (USER MARK).")
    time.sleep(0.3)
    import git_interactive_rebase as tool
    wlog("=== calling tool.main() ===")
    try:
        tool.main()
    except SystemExit as e:
        wlog(f"=== tool.main() SystemExit({e.code}) ===")
    except BaseException:
        wlog(f"=== tool.main() crashed ===\n{traceback.format_exc()}")
    finally:
        _stop.set()
        wlog("=== flash_diag v3 end ===")


if __name__ == "__main__":
    main()
