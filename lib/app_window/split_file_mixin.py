import os
import subprocess
import tempfile
import time
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from lib.git_helpers import (
    get_commit_files, get_file_diff_only_in_commit,
    get_full_commit_message,
)
from lib.dialogs import (
    SplitCommitDialog, DropFileFromCommitDialog,
    ConfirmDropFileDialog, ConfirmMoveFileDialog,
    ConfirmRemoveFileOnwardsDialog, AggressiveRemoveConfirmationDialog,
    ProgressDialog,
)
from lib.app_window.workers import SplitWorker
from lib.app_window.helpers import _script_command, _safe_unlink


class SplitFileMixin:
    """Split a single file out of / drop from / remove from a commit."""

    def handle_split_commit(self, item):
        """Opens SplitCommitDialog to allow moving a file out of a commit."""
        sha = item.text().split()[0]
        try:
            files = get_commit_files(self.repo_path, sha)
            if not files:
                QMessageBox.information(self, "No Files", f"Commit {sha} has no file changes to split.")
                return
            if len(files) == 1:
                QMessageBox.warning(self, "Warning", "This commit has changes only in 1 file.")
                return

            dialog = SplitCommitDialog(self.repo_path, sha, files, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                selected_file = dialog.get_selected_file()
                if selected_file:
                    self.perform_move_file_out(sha, selected_file)
            else:
                print(f"Cancelled split/move file from {sha}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open split dialog: {str(e)}")

    def perform_move_file_out(self, sha, filepath):
        """
        Moves a single file's changes out of a commit into a new commit after it.
        """
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
        try:
            all_files = get_commit_files(self.repo_path, sha)
            other_files = [f for f in all_files if f != filepath]
            short_sha = sha[:8]

            if not other_files:
                QMessageBox.information(self, "Info", f"File '{filepath}' is the only modified file in this commit. Nothing to split.")
                return

            # Show confirmation dialog with file diff
            try:
                diff_text = get_file_diff_only_in_commit(self.repo_path, sha, filepath)
            except Exception:
                diff_text = "Could not load diff for this file."

            confirm_dialog = ConfirmMoveFileDialog(sha, filepath, diff_text, self.current_font_size, self)
            if confirm_dialog.exec() != QDialog.Accepted:
                return

            original_msg = get_full_commit_message(self.repo_path, sha)
            new_msg = f"{filepath} changes separated out from {short_sha}\n\n{original_msg}"

            # Action script content
            action_script_content = f"""#!/usr/bin/env python3
import subprocess
import os
import tempfile
import sys

sha = {repr(sha)}
filepath = {repr(filepath)}
new_msg = {repr(new_msg)}

# 1. Soft-reset to unstage the commit
subprocess.check_call(['git', 'reset', '--soft', 'HEAD~1'])
# 2. Un-stage the target file from the index
subprocess.check_call(['git', 'reset', 'HEAD', '--', filepath])
# 3. Re-commit the remaining files with the original commit message
subprocess.check_call(['git', 'commit', '-C', sha])
# 4. Stage the target file
subprocess.check_call(['git', 'add', '--all', '--', filepath])
# 5. Commit the target file with the new descriptive message
msg_fd, msg_path = tempfile.mkstemp(prefix='git_msg_', text=True)
with os.fdopen(msg_fd, 'w', encoding='utf-8') as f:
    f.write(new_msg)
try:
    subprocess.check_call(['git', 'commit', '-F', msg_path])
finally:
    try:
        os.unlink(msg_path)
    except:
        pass
"""
            action_fd, action_path = tempfile.mkstemp(prefix='git_split_action_', suffix='.py', text=True)
            with os.fdopen(action_fd, 'w', encoding='utf-8') as f:
                f.write(action_script_content)

            single_exec = f"exec {_script_command(action_path)}"

            current_shas = [self.list_widget.item(i).text().split()[0]
                            for i in range(self.list_widget.count())]

            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
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
                f.write("        output.append(single_exec + '\\n')\n")
                f.write("with open(todo_path, 'w') as tf:\n")
                f.write("    tf.writelines(output)\n")
                editor_script = f.name


            sha_idx = current_shas.index(sha) if sha in current_shas else -1
            if sha_idx == len(current_shas) - 1:
                has_parent = False
                try:
                    subprocess.run(["git", "rev-parse", f"{sha}^"],
                                   cwd=self.repo_path, check=True, capture_output=True)
                    has_parent = True
                except Exception:
                    pass
                upstream = f"{sha}^" if has_parent else "--root"
            else:
                upstream = current_shas[sha_idx + 1]

            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = _script_command(editor_script)
            env["GIT_EDITOR"] = "true"

            if upstream == "--root":
                cmd = ["git", "rebase", "-i", "--root"]
            else:
                cmd = ["git", "rebase", "-i", upstream]

            progress = ProgressDialog("Moving File Out", f"Moving '{filepath}' out of commit {short_sha}...", self)
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
                        self.log_action(sha, f"moved {filepath} out of", old_head, new_head)
                        QMessageBox.information(self, "Success",
                            f"File '{filepath}' has been moved out of commit {short_sha}.\n\n"
                            f"A new commit was created with message: \"{filepath} changes separated out from {short_sha}\"")
                    else:
                        ok, detail = self._abort_rebase_safely()
                        if not ok:
                            self._warn_rebase_abort_failure(detail)
                        QMessageBox.critical(self, "Split Failed",
                            f"The split operation failed and has been aborted.\n\n"
                            f"Error: {stderr}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
                finally:
                    self.load_history()

            self.split_worker.finished.connect(on_split_finished)
            print("[thread] split_file split_worker.start()")
            self.split_worker.start()
            progress.exec()
        except Exception as e:
            _safe_unlink(editor_script, action_path)
            QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
            self.load_history()

    def handle_split_drop_file(self, item):
        """Opens DropFileFromCommitDialog to allow dropping a file from a commit."""
        sha = item.text().split()[0]
        try:
            files = get_commit_files(self.repo_path, sha)
            if not files:
                QMessageBox.information(self, "No Files", f"Commit {sha} has no file changes to drop.")
                return
            if len(files) == 1:
                QMessageBox.warning(self, "Warning", "This commit has changes only in 1 file.")
                return

            dialog = DropFileFromCommitDialog(self.repo_path, sha, files, self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                selected_file = dialog.get_selected_file()
                if selected_file:
                    self.perform_drop_file_from_commit(sha, selected_file)
            else:
                print(f"Cancelled drop file from {sha}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open drop file dialog: {str(e)}")

    def perform_drop_file_from_commit(self, sha, filepath):
        """
        Drops a single file's changes from a commit without moving it to a new one.
        """
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
        try:
            all_files = get_commit_files(self.repo_path, sha)
            other_files = [f for f in all_files if f != filepath]
            short_sha = sha[:8]

            if not other_files:
                QMessageBox.information(self, "Info", f"File '{filepath}' is the only modified file in this commit. Dropping it means dropping the commit completely. Use Drop action instead.")
                return

            # Show confirmation dialog with file diff
            try:
                diff_text = get_file_diff_only_in_commit(self.repo_path, sha, filepath)
            except Exception:
                diff_text = "Could not load diff for this file."

            confirm_dialog = ConfirmDropFileDialog(sha, filepath, diff_text, self.current_font_size, self)
            if confirm_dialog.exec() != QDialog.Accepted:
                return

            # Action script content for dropping
            action_script_content = f"""#!/usr/bin/env python3
import subprocess
import sys

sha = {repr(sha)}
filepath = {repr(filepath)}

# 1. Soft-reset to unstage the commit
subprocess.check_call(['git', 'reset', '--soft', 'HEAD~1'])
# 2. Un-stage the target file from the index so it won't be committed
subprocess.check_call(['git', 'reset', 'HEAD', '--', filepath])
# 3. Commit the remaining files with the original commit message
subprocess.check_call(['git', 'commit', '-C', sha])
# 4. Discard the unstaged changes to drop them
subprocess.check_call(['git', 'reset', '--hard', 'HEAD'])
# 5. Clean untracked files (in case the dropped change was a new file)
subprocess.check_call(['git', 'clean', '-fd', '--', filepath])
"""
            import tempfile
            import os
            import stat
            action_fd, action_path = tempfile.mkstemp(prefix='git_drop_action_', suffix='.py', text=True)
            with os.fdopen(action_fd, 'w', encoding='utf-8') as f:
                f.write(action_script_content)

            single_exec = f"exec {_script_command(action_path)}"

            current_shas = [self.list_widget.item(i).text().split()[0]
                            for i in range(self.list_widget.count())]

            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
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
                f.write("        output.append(single_exec + '\\n')\n")
                f.write("with open(todo_path, 'w') as tf:\n")
                f.write("    tf.writelines(output)\n")
                editor_script = f.name


            sha_idx = current_shas.index(sha) if sha in current_shas else -1
            if sha_idx == len(current_shas) - 1:
                has_parent = False
                try:
                    subprocess.run(["git", "rev-parse", f"{sha}^"],
                                   cwd=self.repo_path, check=True, capture_output=True)
                    has_parent = True
                except Exception:
                    pass
                upstream = f"{sha}^" if has_parent else "--root"
            else:
                upstream = current_shas[sha_idx + 1]

            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = _script_command(editor_script)
            env["GIT_EDITOR"] = "true"

            if upstream == "--root":
                cmd = ["git", "rebase", "-i", "--root"]
            else:
                cmd = ["git", "rebase", "-i", upstream]

            result = subprocess.run(cmd, cwd=self.repo_path, env=env,
                                    capture_output=True, text=True)

            try:
                os.unlink(editor_script)
                os.unlink(action_path)
            except:
                pass

            if result.returncode == 0:
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha, f"dropped {filepath} from", old_head, new_head)
                QMessageBox.information(self, "Success",
                    f"File '{filepath}' changes have been dropped from commit {short_sha}.")
            else:
                ok, detail = self._abort_rebase_safely()
                if not ok:
                    self._warn_rebase_abort_failure(detail)
                QMessageBox.critical(self, "Drop Failed",
                    f"The drop operation failed and has been aborted.\n\n"
                    f"Error: {result.stderr}")
        except Exception as e:
            _safe_unlink(editor_script, action_path)
            QMessageBox.critical(self, "Error", f"An error occurred during drop: {str(e)}")
        finally:
            self.load_history()

    def perform_remove_file_from_commit_onwards(self, sha, filepath):
        """
        Removes a file from the selected commit and ensures it stays removed
        in all subsequent commits. Useful for cleaning accidentally committed files.
        """
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return
        print(f"[{time.strftime('%H:%M:%S')}] Remove file onwards: starting for file='{filepath}' commit={sha}")
        old_head = self.get_head_sha()
        print(f"[{time.strftime('%H:%M:%S')}] Remove file onwards: starting SHA={self.commit_sha}, selected commit={sha}, HEAD before={old_head}")
        self.save_undo_state()
        action_path = None
        editor_script = None
        deletion_path = None
        try:
            short_sha = sha[:8]

            current_shas = [self.list_widget.item(i).text().split()[0]
                            for i in range(self.list_widget.count())]
            sha_idx = current_shas.index(sha) if sha in current_shas else -1

            commits_to_drop = []
            if sha_idx >= 0:
                # Items before sha_idx are newer commits (since list is newest-first)
                # This naturally processes commits chronologically backward (newest to oldest)
                for i in range(sha_idx + 1):
                    c_sha = current_shas[i]
                    try:
                        c_files = get_commit_files(self.repo_path, c_sha)
                        if filepath in c_files:
                            c_msg = get_full_commit_message(self.repo_path, c_sha)
                            will_be_empty = (len(c_files) == 1)
                            commits_to_drop.append((c_sha, c_msg, will_be_empty))
                    except Exception:
                        pass
            else:
                QMessageBox.warning(self, "Error", "Commit not found in list.")
                return

            later_modifications_detected = len(commits_to_drop) > 1
            has_empty_commits = any(w for _, _, w in commits_to_drop)

            # Show file diff for context
            try:
                diff_text = get_file_diff_only_in_commit(self.repo_path, sha, filepath)
            except Exception:
                diff_text = "Could not load diff for this file."

            confirm_dialog = ConfirmRemoveFileOnwardsDialog(
                sha, filepath, diff_text,
                later_modifications_detected=later_modifications_detected,
                font_size=self.current_font_size, parent=self
            )
            if confirm_dialog.exec() != QDialog.Accepted:
                return

            drop_empty_commits = False

            if later_modifications_detected:
                future_commits = [(s, m) for s, m, _ in commits_to_drop if s != sha]
                agg_dialog = AggressiveRemoveConfirmationDialog(
                    filepath, future_commits, has_empty_commits=has_empty_commits, font_size=self.current_font_size, parent=self
                )
                if agg_dialog.exec() != QDialog.Accepted:
                    return
                drop_empty_commits = agg_dialog.drop_empty_checkbox.isChecked() if has_empty_commits else False

            progress = ProgressDialog(
                f"Removing {filepath}",
                "Preparing history rewrite...",
                self
            )
            progress.show()
            for _ in range(5):
                QApplication.processEvents()
                time.sleep(0.02)

            empty_commits_dropped_count = 0

            import tempfile
            import os

            # commits_to_drop is newest-first; selected commit is LAST (oldest target)
            target_shas = [drop_sha for drop_sha, _, _ in commits_to_drop]
            should_drop_map = {}
            for drop_sha, _, will_be_empty in commits_to_drop:
                should_drop_map[drop_sha] = drop_empty_commits and will_be_empty
                if should_drop_map[drop_sha]:
                    empty_commits_dropped_count += 1

            # Upstream: parent of the selected (oldest) commit
            has_parent = False
            try:
                subprocess.run(["git", "rev-parse", f"{sha}^"], cwd=self.repo_path, check=True, capture_output=True)
                has_parent = True
            except:
                pass
            upstream = f"{sha}^" if has_parent else "--root"

            # Exec script: cherry-picks a commit, then removes the file from it
            action_script_content = f"""#!/usr/bin/env python3
import subprocess
import sys
import os
import tempfile

filepath = {repr(filepath)}
target_sha = sys.argv[1] if len(sys.argv) > 1 else None

try:
    if target_sha:
        subprocess.run(
            ['git', 'cherry-pick', '--no-commit', '--strategy-option=ours', target_sha],
            capture_output=True, text=True)

    original_msg = subprocess.check_output(
        ['git', 'log', '-1', '--format=%B', target_sha or 'HEAD']).decode('utf-8')

    subprocess.run(['git', 'rm', '-f', '--ignore-unmatch', '--', filepath], capture_output=True)
    subprocess.run(['git', 'add', '-A'], capture_output=True)

    msg_fd, msg_path = tempfile.mkstemp(prefix='git_msg_', text=True)
    with os.fdopen(msg_fd, 'w', encoding='utf-8') as f:
        f.write(original_msg)
    try:
        subprocess.check_call(['git', 'commit', '--allow-empty', '-F', msg_path])
    finally:
        try:
            os.unlink(msg_path)
        except:
            pass
except Exception as e:
    print("FAILED to replace commit:", e)
    sys.exit(1)
"""
            action_fd, action_path = tempfile.mkstemp(prefix='git_remove_action_', suffix='.py', text=True)
            with os.fdopen(action_fd, 'w', encoding='utf-8') as f:
                f.write(action_script_content)
            single_exec = f"exec {_script_command(action_path)}"

            # Deletion exec script: actually removes the file from the tree
            deletion_script_content = f"""#!/usr/bin/env python3
import subprocess
import sys

filepath = {repr(filepath)}

try:
    result = subprocess.run(['git', 'rm', '-f', '--', filepath], capture_output=True, text=True)
    if result.returncode != 0:
        subprocess.run(['git', 'rm', '-f', '--ignore-unmatch', '--', filepath], capture_output=True)
    subprocess.check_call(['git', 'commit', '-m', 'Remove {filepath}'])
except Exception as e:
    print("FAILED to create deletion commit:", e)
    sys.exit(1)
"""
            deletion_fd, deletion_path = tempfile.mkstemp(prefix='git_delete_commit_', suffix='.py', text=True)
            with os.fdopen(deletion_fd, 'w', encoding='utf-8') as f:
                f.write(deletion_script_content)
            deletion_exec = f"exec {_script_command(deletion_path)}"

            # Editor script: keep pick for selected, replace others with exec, insert deletion after selected
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
                f.write("#!/usr/bin/env python3\n")
                f.write("import sys\n")
                f.write(f"target_shas = {repr(target_shas)}\n")
                f.write(f"should_drop_map = {repr(should_drop_map)}\n")
                f.write(f"selected_sha = {repr(sha)}\n")
                f.write(f"single_exec = {repr(single_exec)}\n")
                f.write(f"deletion_exec = {repr(deletion_exec)}\n")
                f.write("todo_path = sys.argv[1]\n")
                f.write("with open(todo_path, 'r') as tf:\n")
                f.write("    lines = tf.readlines()\n")
                f.write("output = []\n")
                f.write("deletion_inserted = False\n")
                f.write("for line in lines:\n")
                f.write("    stripped = line.strip()\n")
                f.write("    is_target = False\n")
                f.write("    matched_sha = None\n")
                f.write("    if not stripped.startswith('#') and len(stripped.split()) >= 2:\n")
                f.write("        for ts in target_shas:\n")
                f.write("            if stripped.split()[1].startswith(ts):\n")
                f.write("                is_target = True\n")
                f.write("                matched_sha = ts\n")
                f.write("                break\n")
                f.write("    if is_target and should_drop_map.get(matched_sha, False):\n")
                f.write("        continue\n")
                f.write("    if is_target and matched_sha:\n")
                f.write("        if matched_sha == selected_sha:\n")
                f.write("            output.append(line)\n")
                f.write("            output.append(deletion_exec + '\\n')\n")
                f.write("            deletion_inserted = True\n")
                f.write("        else:\n")
                f.write("            output.append(single_exec + ' ' + matched_sha + '\\n')\n")
                f.write("    else:\n")
                f.write("        output.append(line)\n")
                f.write("with open(todo_path, 'w') as tf:\n")
                f.write("    tf.writelines(output)\n")
                editor_script = f.name

            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = _script_command(editor_script)
            env["GIT_EDITOR"] = "true"

            cmd = ["git", "rebase", "-i", upstream] if upstream != "--root" else ["git", "rebase", "-i", "--root"]
            result = subprocess.run(cmd, cwd=self.repo_path, env=env, capture_output=True, text=True)

            try:
                os.unlink(editor_script)
                os.unlink(action_path)
                os.unlink(deletion_path)
            except:
                pass

            if result.returncode != 0:
                ok, detail = self._abort_rebase_safely()
                if not ok:
                    self._warn_rebase_abort_failure(detail)
                progress.close()
                QMessageBox.critical(self, "Failed", f"Failed while processing {sha[:8]}. Aborted.\n\n{result.stderr}")
                self.load_history()
                return

            progress.close()
            self.load_history()
            new_head = self.get_head_sha()
            self.log_action(sha, f"removed {filepath} onwards completely", old_head, new_head)

            success_msg = f"File '{filepath}' has been perfectly removed from history from {short_sha} onwards."
            if empty_commits_dropped_count > 0:
                success_msg += f"\n\n{empty_commits_dropped_count} empty commit(s) were automatically dropped."

            QMessageBox.information(self, "Success", success_msg)
        except Exception as e:
            _safe_unlink(editor_script, action_path, deletion_path)
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
        finally:
            self.load_history()
