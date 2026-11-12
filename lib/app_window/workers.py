import re
import subprocess
import threading
import time
from PySide6.QtCore import (
    QThread,
    Signal,
)
from lib.git_helpers import perform_self_update, bulk_commit_all, amend_with_head
from lib.logger import _log


class BulkCommitWorker(QThread):
    """Runs bulk_commit_all (git commit --only -- <files> + commit) off the UI
    thread so a ProgressDialog's exec() event loop stays live and keeps painting.
    Only the given (submodule-excluded) files are committed."""
    git_finished = Signal(bool, str)

    def __init__(self, repo_path, message, files, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.message = message
        self.files = files

    def run(self):
        try:
            ok, detail = bulk_commit_all(self.repo_path, self.message, self.files)
            self.git_finished.emit(ok, detail)
        except Exception as e:
            self.git_finished.emit(False, str(e))


class AmendWorker(QThread):
    """Runs amend_with_head (git commit --amend --only [--no-edit|-m msg] -- <files>)
    off the UI thread so a ProgressDialog's exec() event loop stays live and paints.
    Only the given (submodule-excluded) files are amended into HEAD. When *message*
    is given, HEAD's commit message is replaced with it."""
    git_finished = Signal(bool, str)

    def __init__(self, repo_path, files, message=None, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.files = files
        self.message = message

    def run(self):
        try:
            ok, detail = amend_with_head(self.repo_path, self.files, self.message)
            self.git_finished.emit(ok, detail)
        except Exception as e:
            self.git_finished.emit(False, str(e))


# Timeout (seconds) for network-facing commands (fetch/pull/push/ls-remote).
# On the plain path it is a total deadline; on the progress path there is no
# total deadline at all (a healthy big transfer may run for hours) - the
# value is the inactivity window instead: no output for this long means the
# remote is dead, not slow, and the child is killed with "No response...".
_NET_TIMEOUT = 120

# stderr emitted by GitWorker.run() when the user pressed Abort in the
# progress dialog. Handlers compare against it to tell "user cancelled"
# apart from a real git failure (and skip refreshes: nothing changed).
ABORTED = "Aborted by user"

# One git progress update: "Receiving objects:  42% (17/40), 1.23 MiB | ..."
# The remote side arrives prefixed with "remote: " and is stripped first.
_PROGRESS_RE = re.compile(r"^(?P<phase>.*?):\s*(?P<pct>\d{1,3})%")


def parse_git_progress(line):
    """Return (phase, percent) for a git progress update, else None.

    Pure helper so it can be unit-tested against canned git output. Lines that
    are not progress (log output, "fatal: ..." errors, blank lines) return
    None, as do percentages outside 0-100.
    """
    if isinstance(line, bytes):
        line = line.decode("utf-8", "replace")
    line = line.strip()
    if line.startswith("remote: "):
        line = line[len("remote: "):]
    match = _PROGRESS_RE.match(line)
    if match is None:
        return None
    percent = int(match.group("pct"))
    phase = match.group("phase").strip()
    if percent > 100 or not phase:
        return None
    return phase, percent


def _strip_progress(text):
    """Drop progress updates from a captured stream, keeping real output.

    Used for the error message: without this a failed fetch would report
    "Error: Receiving objects: 42% ... fatal: ..." instead of just the error.
    """
    return "\n".join(
        line for line in text.splitlines()
        if parse_git_progress(line) is None
    ).strip()


def _drain_stream(stream, sink, on_activity=None):
    """Read *stream* to EOF into *sink*.

    stdout must keep being drained while stderr is parsed, otherwise the
    child fills its pipe buffer and blocks forever. *on_activity* (if given)
    is called per chunk so the stall watchdog sees stdout as life too.
    """
    try:
        for chunk in iter(lambda: stream.read1(65536), b""):
            sink.append(chunk)
            if on_activity is not None:
                on_activity()
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


class _InactivityWatchdog:
    """Kill *proc* after *timeout* seconds with no output on either stream.

    The progress path deliberately has no total deadline - a slow-but-healthy
    fetch may run for as long as it needs - but a remote that goes completely
    silent (dead connection, frozen proxy) must still stop by itself, so the
    dialog never waits forever on a process that will never speak again.
    Any output resets the clock via poke(); git emits a percentage every
    few seconds during any real transfer, so this never fires on a healthy
    run. Fires at most once; stop() disarms it.
    """

    def __init__(self, proc, timeout, on_stall, tick=None):
        self._proc = proc
        self._timeout = timeout
        self._on_stall = on_stall
        # check often enough for a small test timeout, at most 1x/sec
        self._tick = tick if tick is not None else max(
            0.05, min(timeout / 4.0, 1.0))
        self._last = time.monotonic()
        self._stopped = False
        self.fired = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def poke(self):
        """Record that output was seen - the child is alive."""
        self._last = time.monotonic()

    def _loop(self):
        while not self._stopped:
            time.sleep(self._tick)
            if self._stopped:
                return
            if time.monotonic() - self._last < self._timeout:
                continue
            if self.fired.is_set():
                return
            self.fired.set()
            try:
                self._proc.kill()
            except Exception:
                pass
            self._on_stall()
            return

    def stop(self):
        self._stopped = True


class GitWorker(QThread):
    git_finished = Signal(bool, str, str)
    # (phase, percent) - emitted while a progress=True command runs, from
    # git's stderr ("Receiving objects: 42%"); queued to the GUI thread.
    git_progress = Signal(str, int)

    def __init__(self, command, cwd, timeout=30, progress=False):
        super().__init__()
        self.command = command
        self.cwd = cwd
        self.timeout = timeout
        self.progress = progress
        self._progress_tail = b""
        self._proc = None
        self._abort_requested = threading.Event()

    def abort(self):
        """Kill the running child immediately (GUI-thread safe).

        Called by the progress dialog's Abort button and by closeEvent.
        Safe before start(), after finish(), and when called repeatedly;
        a no-op on the plain path, whose commands are bounded by their
        own timeout anyway.
        """
        self._abort_requested.set()
        proc = self._proc
        if proc is not None:
            _log(f"[progress] DEBUG abort: killing pid={proc.pid}")
            try:
                proc.kill()
            except Exception:
                pass

    def run(self):
        if self.progress:
            self._run_with_progress()
        else:
            self._run_simple()

    def _run_simple(self):
        try:
            result = subprocess.run(
                self.command, cwd=self.cwd,
                capture_output=True, text=True,
                check=True, encoding='utf-8', errors='replace',
                timeout=self.timeout
            )
            self.git_finished.emit(True, result.stdout, "")
        except subprocess.TimeoutExpired:
            self.git_finished.emit(
                False, "", f"Command timed out after {self.timeout}s: {' '.join(str(a) for a in self.command)}"
            )
        except subprocess.CalledProcessError as e:
            self.git_finished.emit(False, "", e.stderr)
        except Exception as e:
            self.git_finished.emit(False, "", str(e))

    def _run_with_progress(self):
        """Run a network command, streaming git's percentages as they arrive.

        subprocess.run() only returns at exit and hides progress (git writes
        it to stderr, and only when asked with --progress), so this uses
        Popen instead: a helper thread drains stdout while this thread reads
        stderr and emits git_progress().

        Deliberately NO total deadline: a slow-but-healthy transfer may run
        for as long as it needs. What stops the child is (a) the Abort
        button via abort(), (b) the inactivity watchdog, which kills it
        only after self.timeout seconds of complete silence on both
        streams - progress means alive, silence means dead - and (c) the
        safety cap on the final wait below.
        """
        command = list(self.command)
        if "--progress" not in command:
            command.append("--progress")
        try:
            proc = subprocess.Popen(
                command, cwd=self.cwd,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except Exception as e:
            self.git_finished.emit(False, "", str(e))
            return
        self._proc = proc
        if self._abort_requested.is_set():
            # abort() raced ahead of Popen: don't let it start work the
            # user already declined.
            try:
                proc.kill()
            except Exception:
                pass

        stall_msg = (f"No response from remote after {self.timeout}s: "
                     f"{' '.join(command)}")
        # the watchdog kills the child itself when the silence window
        # elapses; on_stall only reports it (the kill is logged -v).
        watchdog = _InactivityWatchdog(
            proc, self.timeout,
            lambda: _log(f"[progress] DEBUG stall watchdog: no output for "
                         f"{self.timeout}s, pid={proc.pid} killed"),
        )
        _log(f"[progress] DEBUG start: {' '.join(command)} "
             f"cwd={self.cwd} inactivity={self.timeout}s")

        stdout_chunks = []
        drain = threading.Thread(
            target=_drain_stream,
            args=(proc.stdout, stdout_chunks, watchdog.poke),
            daemon=True,
        )
        drain.start()

        stderr_chunks = []
        self._emitted = 0
        try:
            while True:
                chunk = proc.stderr.read1(65536)
                if not chunk:
                    break
                watchdog.poke()
                if b"%" in chunk:
                    _log(f"[progress] DEBUG raw stderr ({len(chunk)}B): "
                         f"{chunk[:300]!r}")
                stderr_chunks.append(chunk)
                self._feed_progress(chunk)
        except Exception:
            pass
        finally:
            try:
                # stderr EOF means git (and its children) are exiting, so
                # this returns almost immediately. The old total-deadline
                # wait is gone; this flat cap is only a safety net for a
                # child that closed stderr but somehow lives on - abort()
                # and the stall watchdog cover every realistic case.
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass
            except Exception:
                pass
            watchdog.stop()
            drain.join(timeout=2)
            self._feed_progress(b"", final=True)
        self._proc = None

        stdout = b"".join(stdout_chunks).decode("utf-8", "replace")
        stderr = _strip_progress(
            b"".join(stderr_chunks).decode("utf-8", "replace"))
        _log(f"[progress] DEBUG end: rc={proc.returncode} "
             f"aborted={self._abort_requested.is_set()} "
             f"stalled={watchdog.fired.is_set()} emitted={self._emitted} "
             f"stdout={len(stdout)}B stripped_stderr={len(stderr)}B")
        if proc.returncode == 0:
            # a successful git always wins, even if abort landed on the
            # finish line - reporting "aborted" for real fetched data
            # would be a lie.
            self.git_finished.emit(True, stdout, "")
        elif self._abort_requested.is_set():
            self.git_finished.emit(False, "", ABORTED)
        elif watchdog.fired.is_set():
            self.git_finished.emit(False, "", stall_msg)
        else:
            self.git_finished.emit(False, "", stderr)

    def _feed_progress(self, data, final=False):
        """Split raw stderr on CR/LF and emit every progress update found.

        git starts each update with CR, so the pending tail is usually
        already complete: emit it as soon as it parses instead of waiting for
        the next update to terminate it.
        """
        pieces = re.split(b"[\r\n]", self._progress_tail + data)
        if final:
            self._progress_tail = b""
        else:
            self._progress_tail = pieces.pop()
        for piece in pieces:
            self._emit_progress(piece)
        if not final and self._progress_tail:
            if parse_git_progress(self._progress_tail) is not None:
                self._emit_progress(self._progress_tail)
                self._progress_tail = b""
            elif b"%" in self._progress_tail:
                _log("[progress] DEBUG holding partial update: "
                     f"{self._progress_tail[:160]!r}")

    def _emit_progress(self, piece):
        parsed = parse_git_progress(piece)
        if parsed is not None:
            self._emitted = getattr(self, "_emitted", 0) + 1
            _log(f"[progress] DEBUG emit -> git_progress({parsed[0]!r}, "
                 f"{parsed[1]})")
            self.git_progress.emit(parsed[0], parsed[1])
        elif b"%" in piece:
            _log(f"[progress] DEBUG unparsed %-line: {piece[:160]!r}")


class NumstatWorker(QThread):
    numstat_ready = Signal(str, dict)

    def __init__(self, repo_path, commit_sha, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.commit_sha = commit_sha

    def run(self):
        from lib.git_helpers.commits import get_commit_file_stats
        try:
            stats = get_commit_file_stats(self.repo_path, self.commit_sha)
        except Exception:
            stats = {}
        self.numstat_ready.emit(self.commit_sha, stats)


class SelfUpdateWorker(QThread):
    update_finished = Signal(bool, str)

    def __init__(self, tool_dir):
        super().__init__()
        self.tool_dir = tool_dir

    def run(self):
        try:
            ok, message = perform_self_update(self.tool_dir)
            self.update_finished.emit(ok, message)
        except Exception as e:
            self.update_finished.emit(False, str(e))


class SplitWorker(QThread):
    split_finished = Signal(int, str, str)

    def __init__(self, cmd, cwd, env=None):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd
        self.env = env

    def run(self):
        try:
            result = subprocess.run(self.cmd, cwd=self.cwd, env=self.env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.split_finished.emit(result.returncode, result.stdout, result.stderr)
        except Exception as e:
            self.split_finished.emit(-1, "", str(e))
