import time

_VERBOSE = False
_VERBOSE_TAGS = {'perf', 'ctx', 'diff', 'stats', 'thread', 'rescan'}


def set_verbose(enabled=True):
    global _VERBOSE
    _VERBOSE = enabled


def _log(msg, **_kw):
    """Log a message with a millisecond-precision timestamp.
    In non-verbose mode, only errors and untagged startup messages are shown.
    Verbose-tagged messages (perf, diff, ctx, etc.) require -v / --verbose."""
    if not _VERBOSE:
        tag = msg.split(']')[0].lstrip('[') if ']' in msg else ''
        is_error = any(k in msg for k in ('FAILED', 'Error', 'error', 'Exception', 'Traceback'))
        if tag in _VERBOSE_TAGS and not is_error:
            return
    print(f"[{time.strftime('%H:%M:%S')}.{time.time_ns() % 1000:03d}] {msg}")
