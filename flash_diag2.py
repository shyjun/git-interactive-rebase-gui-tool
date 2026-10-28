"""flash_diag v2 - name the startup flash windows (Windows only).
Run from repo root: python flash_diag.py   (delete afterwards)
Paste flash_diag.log lines around the flash times."""
import ctypes, ctypes.wintypes as wt, datetime, os, subprocess, sys, threading, time

if os.name != "nt":
    sys.exit("Windows only")

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flash_diag.log")
_lock = threading.Lock()
_logf = open(LOG_PATH, "a", encoding="utf-8")

def wlog(msg):
    with _lock:
        _logf.write(f"{datetime.datetime.now():%H:%M:%S.%f} {msg}\n")
        _logf.flush()

user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

def window_info(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    tbuf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, tbuf, n + 1)
    cbuf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cbuf, 256)
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    name = "?"
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if h:
        nbuf, sz = ctypes.create_unicode_buffer(32768), wt.DWORD(32768)
        if kernel32.QueryFullProcessImageNameW(h, 0, nbuf, ctypes.byref(sz)):
            name = os.path.basename(nbuf.value)
        kernel32.CloseHandle(h)
    return cbuf.value, tbuf.value, pid.value, name

def sampler():
    known, first, end = {}, True, time.time() + 60
    while time.time() < end:
        current = set()
        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                current.add(hwnd)
            return True
        user32.EnumWindows(EnumProc(cb), 0)
        now = time.time()
        for hwnd in current:
            if hwnd not in known:
                cls, title, pid, name = window_info(hwnd)
                if first:
                    known[hwnd] = None          # baseline: don't log
                else:
                    known[hwnd] = (now, cls, title, pid, name)
                    wlog(f"OPEN  hwnd={hwnd:#x} class='{cls}' title='{title}' pid={pid} proc='{name}'")
        for hwnd in list(known):
            if hwnd not in current:
                rec = known.pop(hwnd)
                if rec is not None:
                    wlog(f"CLOSE hwnd={hwnd:#x} class='{rec[1]}' title='{rec[2]}' proc='{rec[3]}' lived={(now - rec[0]) * 1000:.0f}ms")
        first = False
        time.sleep(0.003)
    wlog("--- sampler done ---")

threading.Thread(target=sampler, daemon=True).start()

# Instrument every spawn: timestamp + child pid + argv + creationflags.
_orig_init = subprocess.Popen.__init__
def _logged_init(self, args, *a, **kw):
    try:
        _orig_init(self, args, *a, **kw)
    except Exception as exc:
        wlog(f"SPAWN-FAILED args={args!r} err={exc}")
        raise
    try:
        wlog(f"SPAWN pid={self.pid} cf={kw.get('creationflags', 0)} args={args!r}")
    except Exception:
        pass
subprocess.Popen.__init__ = _logged_init

wlog(f"=== starting tool (diag pid={os.getpid()}) ===")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import git_interactive_rebase as tool
tool.main()
