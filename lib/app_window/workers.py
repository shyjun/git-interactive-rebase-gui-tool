import subprocess
from PySide6.QtCore import QThread, Signal
from lib.git_helpers import perform_self_update


class GitWorker(QThread):
    finished = Signal(bool, str, str)

    def __init__(self, command, cwd):
        super().__init__()
        self.command = command
        self.cwd = cwd

    def run(self):
        try:
            result = subprocess.run(self.command, cwd=self.cwd, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
            self.finished.emit(True, result.stdout, "")
        except subprocess.CalledProcessError as e:
            self.finished.emit(False, "", e.stderr)
        except Exception as e:
            self.finished.emit(False, "", str(e))


class SelfUpdateWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, tool_dir):
        super().__init__()
        self.tool_dir = tool_dir

    def run(self):
        try:
            ok, message = perform_self_update(self.tool_dir)
            self.finished.emit(ok, message)
        except Exception as e:
            self.finished.emit(False, str(e))


class SplitWorker(QThread):
    finished = Signal(int, str, str)

    def __init__(self, cmd, cwd, env=None):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd
        self.env = env

    def run(self):
        try:
            result = subprocess.run(self.cmd, cwd=self.cwd, env=self.env, capture_output=True, text=True, encoding='utf-8', errors='replace')
            self.finished.emit(result.returncode, result.stdout, result.stderr)
        except Exception as e:
            self.finished.emit(-1, "", str(e))
