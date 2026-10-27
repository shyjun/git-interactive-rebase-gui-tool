"""flash_diag.py - log visible top-level windows during tool startup.
Run from the repo root:  python flash_diag.py   (Windows only)
Then paste flash_diag.log lines around the flash times."""
import ctypes, ctypes.wintypes as wt, datetime, os, sys, threading, time

if os.name != "nt":
    sys.exit("Windows only")

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flash_diag.log")
_logf = open(LOG_PATH, "a", encoding="utf-8")

def wlog(msg):
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
    open_hwnds, first_tick, end = {}, True, time.time() + 60
    while time.time() < end:
        current = {}
        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                current[hwnd] = window_info(hwnd)
            return True
        user32.EnumWindows(EnumProc(cb), 0)
        now = time.time()
        if first_tick:
            first_tick = False
            wlog("BASELINE: " + "; ".join(f"{i[3]}|'{i[1]}'" for i in current.values()))
        for hwnd, info in current.items():
            if hwnd not in open_hwnds:
                wlog(f"OPEN  hwnd={hwnd:#x} class='{info[0]}' title='{info[1]}' proc='{info[3]}'")
            open_hwnds[hwnd] = (info, now)
        for hwnd in list(open_hwnds):
            if hwnd not in current:
                info, since = open_hwnds.pop(hwnd)
                wlog(f"CLOSE hwnd={hwnd:#x} class='{info[0]}' title='{info[1]}' proc='{info[3]}' lived={(now - since) * 1000:.0f}ms")
        time.sleep(0.015)
    wlog("STILL OPEN: " + "; ".join(f"{i[3]}|'{i[1]}'" for i, _ in open_hwnds.values()))

threading.Thread(target=sampler, daemon=True).start()
wlog("=== starting tool ===")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import git_interactive_rebase as tool
tool.main()
