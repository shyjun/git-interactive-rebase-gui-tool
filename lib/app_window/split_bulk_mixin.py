import os
import subprocess
import tempfile
import time
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from lib.git_helpers import (
    get_commit_files, get_full_commit_message,
)
from lib.dialogs import ProgressDialog
from lib.app_window.workers import SplitWorker
from lib.app_window.helpers import _script_command, _safe_unlink


class SplitBulkMixin:
    """Bulk split operations: split-all-hunks and split-per-file."""

    def handle_split_all_commits(self, item):
        sha = item.text().split()[0]
        try:
            files = get_commit_files(self.repo_path, sha)
            if len(files) != 1:
                QMessageBox.critical(
                    self,
                    "Cannot Split All Commits",
                    "This commit contains multiple files.\n\n"
                    "To split this commit:\n"
                    "1. First move a file changes out of this commit and then split all changes in this file to separate commits.\n\n"
                    "2. Split each file changes to separate commits, and then select the file and split its changes to separate commits."
                )
                return
            filepath = files[0]
            # Count hunks for the confirmation dialog
            diff_text = subprocess.check_output(
                ["git", "log", "-p", "-1", sha, "--", filepath],
                cwd=self.repo_path, encoding='utf-8', errors='replace'
            )
            n_hunks = sum(1 for line in diff_text.split('\n') if line.startswith('@@'))
            reply = QMessageBox.question(
                self,
                "Confirm Split All Changes",
                f"File <b>{filepath}</b> in commit <b>{sha}</b> has <b>{n_hunks}</b> hunk(s).<br><br>"
                f"This will split it into <b>{n_hunks}</b> separate commits (one per hunk).<br><br>"
                "Proceed?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            self.perform_split_all_commits(sha, filepath)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not check commit files: {str(e)}")

    def perform_split_all_commits(self, sha, filepath):
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return
        old_head = self.get_head_sha()
        self.save_undo_state()
        action_path = None
        editor_script = None
        split_action_script = None
        try:
            short_sha = sha[:8]
            original_msg = get_full_commit_message(self.repo_path, sha)

            # The script will be executed when the sequence editor inserts an
            # 'exec <interpreter> <script>' todo line
            split_script_content = f"""#!/usr/bin/env python3
import sys
import subprocess
import os
import tempfile

target_sha = {repr(sha)}
filepath = {repr(filepath)}
original_msg = {repr(original_msg)}

# 1. Get the diff of the file in the commit
diff_text = subprocess.check_output(['git', 'log', '-p', '-1', target_sha, '--', filepath]).decode('utf-8')

# 2. Parse into header and hunks
lines = diff_text.split('\\n')
header = []
hunks = []
current_hunk = []
in_diff = False
in_hunks = False

for line in lines:
    if line.startswith('diff --git'):
        in_diff = True
        header = [line]
    elif in_diff and (line.startswith('index ') or line.startswith('--- ') or line.startswith('+++ ')):
        header.append(line)
    elif in_diff and line.startswith('@@'):
        in_hunks = True
        if current_hunk:
            hunks.append(current_hunk)
        current_hunk = [line]
    elif in_hunks:
        current_hunk.append(line)

if current_hunk:
    hunks.append(current_hunk)

if not hunks:
    sys.exit(0)

# 3. Reset the working tree & index to parent commit state
subprocess.check_call(['git', 'reset', '--hard', 'HEAD~1'])

# 4. Apply each hunk as a separate patch and commit
for i, hunk in enumerate(hunks):
    patch_content = '\\n'.join(header) + '\\n' + '\\n'.join(hunk) + '\\n'

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.patch', encoding='utf-8') as pf:
        pf.write(patch_content)
        patch_path = pf.name
    try:
        # Apply patch. --no-backup-if-mismatch ignores minor offset issues.
        subprocess.check_call(['patch', '-p1', '-i', patch_path, '--no-backup-if-mismatch'])
        subprocess.check_call(['git', 'add', filepath])

        new_msg = f"change-{{i+1}} of {{target_sha[:8]}}\\n\\n{{original_msg}}"

        # Use temp file for multiline message
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as mf:
            mf.write(new_msg)
            mf_path = mf.name
        try:
            subprocess.check_call(['git', 'commit', '-F', mf_path])
        finally:
            if os.path.exists(mf_path):
                os.unlink(mf_path)
    finally:
        if os.path.exists(patch_path):
            os.unlink(patch_path)
"""

            # Write the action script
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py', encoding='utf-8') as sf:
                sf.write(split_script_content)
                split_action_script = sf.name

            single_exec = f"exec {_script_command(split_action_script)}"

            current_shas = [self.list_widget.item(i).text().split()[0] for i in range(self.list_widget.count())]

            # Write the sequence editor script
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py', encoding='utf-8') as f:
                f.write("#!/usr/bin/env python3\n")
                f.write("import sys\n")
                f.write(f"target_sha = {repr(sha)}\n")
                f.write(f"single_exec = {repr(single_exec)}\n")
                f.write("todo_path = sys.argv[1]\n")
                f.write("with open(todo_path, 'r') as tf:\n")
                f.write("    lines = tf.readlines()\n")
                f.write("output = []\n")
                f.write("for line in lines:\n")
                f.write("    output.append(line)\n")
                f.write("    stripped = line.strip()\n")
                f.write("    if not stripped.startswith('#') and len(stripped.split()) >= 2 and stripped.split()[1].startswith(target_sha):\n")
                f.write("        # Add our exec script AFTER the pick line\n")
                f.write("        output.append(single_exec + '\\n')\n")
                f.write("with open(todo_path, 'w') as tf:\n")
                f.write("    tf.writelines(output)\n")
                editor_script = f.name

            # Upstream logic
            sha_idx = current_shas.index(sha) if sha in current_shas else -1
            if sha_idx == len(current_shas) - 1:
                has_parent = False
                try:
                    subprocess.run(["git", "rev-parse", f"{sha}^"], cwd=self.repo_path, check=True, capture_output=True)
                    has_parent = True
                except Exception:
                    pass
                upstream = f"{sha}^" if has_parent else "--root"
            else:
                upstream = current_shas[sha_idx + 1]

            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = _script_command(editor_script)
            env["GIT_EDITOR"] = "true"

            cmd = ["git", "rebase", "-i", upstream] if upstream != "--root" else ["git", "rebase", "-i", "--root"]

            progress = ProgressDialog("Splitting Changes", f"Splitting commit {short_sha} into separate commits...", self)
            self.split_worker = SplitWorker(cmd, self.repo_path, env)

            def on_split_finished(returncode, stdout, stderr):
                try:
                    if progress.isVisible():
                        progress.close()
                    try:
                        os.unlink(editor_script)
                        os.unlink(split_action_script)
                    except:
                        pass

                    if returncode == 0:
                        self.load_history()
                        new_head = self.get_head_sha()
                        self.log_action(sha, f"split {filepath} in", old_head, new_head)
                        QMessageBox.information(self, "Success",
                            f"Commit {short_sha} has been split into multiple commits for file '{filepath}'.")
                    else:
                        ok, detail = self._abort_rebase_safely()
                        if not ok:
                            self._warn_rebase_abort_failure(detail)
                        QMessageBox.critical(self, "Split Failed",
                            f"The split operation failed and has been aborted.\n\nError: {stderr}\nOutput: {stdout}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
                finally:
                    self.load_history()

            self.split_worker.finished.connect(on_split_finished)
            print("[thread] split_bulk split_worker.start()")
            self.split_worker.start()
            progress.exec()
        except Exception as e:
            _safe_unlink(editor_script, split_action_script)
            QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
            self.load_history()

    def handle_split_per_file(self, item):
        """Splits each file in a commit into its own separate commit."""
        sha = item.text().split()[0]
        try:
            files = get_commit_files(self.repo_path, sha)
            if not files:
                QMessageBox.information(self, "No Files", f"Commit {sha} has no file changes to split.")
                return
            if len(files) == 1:
                QMessageBox.information(self, "Info", "This commit only has 1 file changed. Nothing to split.")
                return

            n = len(files)
            reply = QMessageBox.question(
                self,
                "Confirm Split Per File",
                f"Commit <b>{sha}</b> has <b>{n}</b> file(s) changed.<br><br>"
                f"This will split it into <b>{n}</b> separate commits (one per file).<br><br>"
                "Proceed?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

            self.perform_split_per_file(sha, files)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not check commit files: {str(e)}")

    def perform_split_per_file(self, sha, files):
        """
        Splits each file in a commit into its own separate commit.
        """
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return
        old_head = self.get_head_sha()
        self.save_undo_state()
        """Executes splitting each file into its own commit using rebase exec."""
        self.save_undo_state()
        action_path = None
        editor_script = None
        try:
            short_sha = sha[:8]
            original_msg = get_full_commit_message(self.repo_path, sha)

            # Action script content for splitting each file
            action_script_content = f"""#!/usr/bin/env python3
import subprocess
import os
import tempfile
import sys

sha = {repr(sha)}
files = {repr(files)}
short_sha = {repr(short_sha)}
original_msg = {repr(original_msg)}

# This script is executed *after* the 'pick' line, so HEAD is already at target_sha.
# We need to reset to its parent to re-apply changes.
subprocess.check_call(['git', 'reset', '--hard', 'HEAD~1'])

for i, filename in enumerate(files):
    # checkout file from original commit to stage it
    subprocess.check_call(['git', 'checkout', sha, '--', filename])

    if i == 0:
        # First file gets original commit message
        subprocess.check_call(['git', 'commit', '-C', sha])
    else:
        # Others get "filename changes separated out from short_sha" + original_msg
        msg = f"{{filename}} changes separated out from {{short_sha}}\\n\\n{{original_msg}}"

        # Use temp file for multiline message
        msg_fd, msg_path = tempfile.mkstemp(prefix='git_msg_split_', text=True)
        with os.fdopen(msg_fd, 'w', encoding='utf-8') as f:
            f.write(msg)
        try:
            subprocess.check_call(['git', 'commit', '-F', msg_path, '--no-verify'])
        finally:
            try:
                os.unlink(msg_path)
            except:
                pass
"""
            action_fd, action_path = tempfile.mkstemp(prefix='git_split_perfile_', suffix='.py', text=True)
            with os.fdopen(action_fd, 'w', encoding='utf-8') as f:
                f.write(action_script_content)

            single_exec = f"exec {_script_command(action_path)}"

            current_shas = [self.list_widget.item(i).text().split()[0]
                            for i in range(self.list_widget.count())]

            # Write the sequence editor script
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py', encoding='utf-8') as f:
                f.write("#!/usr/bin/env python3\n")
                f.write("import sys\n")
                f.write(f"target_sha = {repr(sha)}\n")
                f.write(f"single_exec = {repr(single_exec)}\n")
                f.write("todo_path = sys.argv[1]\n")
                f.write("with open(todo_path, 'r') as tf:\n")
                f.write("    lines = tf.readlines()\n")
                f.write("output = []\n")
                f.write("for line in lines:\n")
                f.write("    output.append(line)\n")
                f.write("    stripped = line.strip()\n")
                f.write("    if not stripped.startswith('#') and len(stripped.split()) >= 2 and stripped.split()[1].startswith(target_sha):\n")
                f.write("        # Add our exec line AFTER the pick line\n")
                f.write("        output.append(single_exec + '\\n')\n")
                f.write("with open(todo_path, 'w') as tf:\n")
                f.write("    tf.writelines(output)\n")
                editor_script = f.name

            # Upstream logic
            sha_idx = current_shas.index(sha) if sha in current_shas else -1
            if sha_idx == len(current_shas) - 1:
                has_parent = False
                try:
                    subprocess.run(["git", "rev-parse", f"{sha}^"], cwd=self.repo_path, check=True, capture_output=True)
                    has_parent = True
                except Exception:
                    pass
                upstream = f"{sha}^" if has_parent else "--root"
            else:
                upstream = current_shas[sha_idx + 1]

            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = _script_command(editor_script)
            env["GIT_EDITOR"] = "true"

            cmd = ["git", "rebase", "-i", upstream] if upstream != "--root" else ["git", "rebase", "-i", "--root"]

            progress = ProgressDialog("Splitting Changes", f"Splitting commit {short_sha} into {len(files)} separate commits...", self)
            self.split_worker = SplitWorker(cmd, self.repo_path, env)

            def on_split_finished(returncode, stdout, stderr):
                try:
                    if progress.isVisible():
                        progress.close()
                    try:
                        os.unlink(editor_script)
                        os.unlink(action_path)
                    except:
                        pass

                    if returncode == 0:
                        self.load_history()
                        new_head = self.get_head_sha()
                        self.log_action(sha, "split per-file", old_head, new_head)
                        QMessageBox.information(self, "Success",
                            f"Commit {short_sha} has been split into {len(files)} commits.")
                    else:
                        ok, detail = self._abort_rebase_safely()
                        if not ok:
                            self._warn_rebase_abort_failure(detail)
                        QMessageBox.critical(self, "Split Failed",
                            f"The split operation failed and has been aborted.\n\nError: {stderr}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
                finally:
                    self.load_history()

            self.split_worker.finished.connect(on_split_finished)
            print("[thread] split_bulk split_worker.start()")
            self.split_worker.start()
            progress.exec()
        except Exception as e:
            _safe_unlink(editor_script, action_path)
            QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
            self.load_history()
