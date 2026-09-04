import os
import subprocess
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from lib.git_helpers import build_update_command, _is_git_install, GIT_REPO_URL
from lib.utils import get_assets_path
from lib.dialogs import ProgressDialog
from lib.app_window.workers import GitWorker, SelfUpdateWorker


class UpdateMixin:
    def handle_check_for_updates(self):
        """Checks for updates from the remote repository."""
        REPO_URL = GIT_REPO_URL.removeprefix("git+")
        UPDATE_URL = "https://github.com/shyjun/git-interactive-rebase-gui-tool?tab=readme-ov-file#-staying-updated"

        # BUG-13 fix: prevent concurrent check/update workers by disabling
        # the action while it is already in flight.
        if getattr(self, "_update_in_flight", False):
            return
        self._update_in_flight = True

        # 1. Find the tool's own directory
        tool_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        local_sha = "Unknown"
        is_git_install = _is_git_install(tool_dir)
        print(f"[check_update] tool_dir={tool_dir}  is_git={is_git_install}")

        # 2. Extract local SHA
        if is_git_install:
            try:
                res = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=tool_dir, capture_output=True, text=True,
                    encoding='utf-8', errors='replace',
                )
                if res.returncode == 0:
                    local_sha = res.stdout.strip()
            except Exception:  # BUG-15 fix: catch Exception, not bare except
                pass
        else:
            # Check for app_version.json (pip install case)
            try:
                import json
                assets_dir = get_assets_path()
                json_path = os.path.join(assets_dir, "app_version.json")
                if os.path.exists(json_path):
                    with open(json_path, "r", encoding='utf-8') as f:
                        data = json.load(f)
                        local_sha = data.get("sha", "Unknown")
            except Exception:
                pass

        # 3. If no version info found, show manual update help
        if not local_sha or local_sha.strip().lower() in ("unknown", ""):
            self._update_in_flight = False
            msg = (
                "<b>Version Check Unavailable</b><br><br>"
                "Could not determine your current version (missing .git folder and app_version.json).<br><br>"
                f"Please check the <a href='{UPDATE_URL}'>Staying Updated</a> section in README for update instructions."
            )
            box = QMessageBox(self)
            box.setWindowTitle("Check for Updates")
            box.setText(msg)
            box.setTextFormat(Qt.RichText)
            box.setIcon(QMessageBox.Information)
            box.setStandardButtons(QMessageBox.Ok)
            box.exec()
            return

        # 4. Proceed with Remote check
        self.progress_dialog = ProgressDialog("Checking for Updates", "Connecting to GitHub...", self)

        # BUG-9 fix: use tool_dir (a valid directory) as cwd, not self.repo_path
        # (the user's repository), which is semantically wrong and fragile.
        self.worker = GitWorker(["git", "ls-remote", REPO_URL, "HEAD"], tool_dir)

        def on_check_finished(success, stdout, stderr):
            self._update_in_flight = False
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.close()

            if not success or not stdout.strip():
                QMessageBox.warning(self, "Check Failed", "Could not check for updates. Please check your internet connection.")
                return

            remote_sha = stdout.split()[0]

            if remote_sha == local_sha:
                QMessageBox.information(self, "No Updates", "You are already using the latest version.")
            else:
                cmd = build_update_command(tool_dir, is_pip=not is_git_install)
                msg = (
                    "<b>Update Available!</b><br><br>"
                    "A newer version of the tool is available on GitHub.<br><br>"
                    "You can update now, or copy the command below to update later:<br><br>"
                    f"<code>{cmd}</code><br><br>"
                    "After updating, the tool must be restarted for changes to take effect."
                )
                box = QMessageBox(self)
                box.setWindowTitle("Update Available")
                box.setText(msg)
                box.setTextFormat(Qt.RichText)
                box.setIcon(QMessageBox.Information)
                update_button = box.addButton("Update Now", QMessageBox.AcceptRole)
                copy_button = box.addButton("Copy to clipboard", QMessageBox.ActionRole)
                cancel_button = box.addButton("Cancel", QMessageBox.RejectRole)
                box.setDefaultButton(update_button)
                box.exec()

                clicked = box.clickedButton()
                if clicked == copy_button:
                    QApplication.clipboard().setText(cmd)
                    QMessageBox.information(self, "Copied", f"Command copied to clipboard:\n\n{cmd}")
                elif clicked == update_button:
                    self._run_self_update(tool_dir)

        self.worker.finished.connect(on_check_finished)
        print(f"[thread] update check worker.start()")
        self.worker.start()
        self.progress_dialog.exec()

    def _run_self_update(self, tool_dir):
        """Performs the in-app self-update with a progress dialog."""
        # BUG-13 fix: mark in-flight so a second invocation is blocked.
        self._update_in_flight = True
        self.update_progress_dialog = ProgressDialog("Updating Tool", "Updating to the latest version...", self)
        self.update_worker = SelfUpdateWorker(tool_dir)

        def on_update_finished(ok, message):
            self._update_in_flight = False
            if hasattr(self, 'update_progress_dialog'):
                self.update_progress_dialog.close()

            if ok:
                QMessageBox.information(
                    self, "Update Successful",
                    f"{message}\n\nPlease restart the tool to apply the update."
                )
            else:
                QMessageBox.critical(self, "Update Failed", message)

        self.update_worker.finished.connect(on_update_finished)
        print(f"[thread] update self-update worker.start()")
        self.update_worker.start()
        self.update_progress_dialog.exec()
