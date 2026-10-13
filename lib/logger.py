import os
import sys
import time

_VERBOSE = False
_VERBOSE_TAGS = {'perf', 'ctx', 'diff', 'stats', 'thread', 'rescan'}
_BROKEN = False


def set_verbose(enabled=True):
    global _VERBOSE
    _VERBOSE = enabled


def _log(msg, **_kw):
    """Log a message with a millisecond-precision timestamp.
    In non-verbose mode, only errors and untagged startup messages are shown.
    Verbose-tagged messages (perf, diff, ctx, etc.) require -v / --verbose.

    Logging must never crash the app: the background-forked tool inherits the
    launching terminal's stdout, and once that terminal/pane is closed every
    write raises OSError(5) (EIO on a pty whose master is gone). Falls back to
    stderr once; if stderr is dead too (same terminal), console logging is
    disabled and stdio is rebound to devnull so interpreter shutdown's final
    flush cannot raise either."""
    global _BROKEN
    if _BROKEN:
        return
    if not _VERBOSE:
        tag = msg.split(']')[0].lstrip('[') if ']' in msg else ''
        is_error = any(k in msg for k in ('FAILED', 'Error', 'error', 'Exception', 'Traceback'))
        if tag in _VERBOSE_TAGS and not is_error:
            return
    line = f"[{time.strftime('%H:%M:%S')}.{(time.time_ns() // 1_000_000) % 1000:03d}] {msg}"
    try:
        print(line, flush=True)
    except Exception:
        try:
            print(line, file=sys.stderr, flush=True)
        except Exception:
            _BROKEN = True
            try:
                devnull = open(os.devnull, "w")
                sys.stdout = devnull
                sys.stderr = devnull
            except Exception:
                pass
