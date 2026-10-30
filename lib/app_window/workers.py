import subprocess
from PySide6.QtCore import (
    QThread,
    Signal,
)
from lib.git_helpers import perform_self_update, bulk_commit_all, amend_with_head


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
    """Runs amend_with_head (git commit --amend --only -- <files>) off the UI
    thread so a ProgressDialog's exec() event loop stays live and paints.
    Only the given (submodule-excluded) files are amended into HEAD."""
    git_finished = Signal(bool, str)

    def __init__(self, repo_path, files, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.files = files

    def run(self):
        try:
            ok, detail = amend_with_head(self.repo_path, self.files)
            self.git_finished.emit(ok, detail)
        except Exception as e:
            self.git_finished.emit(False, str(e))


class GitWorker(QThread):
    git_finished = Signal(bool, str, str)

    def __init__(self, command, cwd, timeout=30):
        super().__init__()
        self.command = command
        self.cwd = cwd
        self.timeout = timeout

    def run(self):
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
