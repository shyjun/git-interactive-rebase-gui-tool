import os
import re
import subprocess
import tempfile
import time
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from lib.git_helpers import (
    get_commit_files, get_file_diff_only_in_commit,
    get_full_commit_message, rebase_in_progress,
)
from lib.dialogs import (
    SplitCommitDialog, RefineFileSelectDialog, RefineChangesDialog,
    NewCommitMessageDialog, ConfirmDropFileDialog, ConfirmMoveFileDialog,
    ConfirmRemoveFileOnwardsDialog, AggressiveRemoveConfirmationDialog,
    DropFileFromCommitDialog, ProgressDialog,
)
from lib.app_window.workers import SplitWorker
from lib.app_window.helpers import _script_command, _safe_unlink


class SplitMixin:
    """Commit splitting, file-moving, and refine operations."""

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

    # ─────────────────────────────────────────────────────────────────
    #  Refine Changes in Selected File
    # ─────────────────────────────────────────────────────────────────

    def handle_refine_changes(self, item):
        """Opens RefineFileSelectDialog to let user pick a file to refine."""
        sha = item.text().split()[0]
        try:
            files = get_commit_files(self.repo_path, sha)
            if not files:
                QMessageBox.information(self, "No Files",
                                        f"Commit {sha} has no file changes.")
                return

            dialog = RefineFileSelectDialog(self.repo_path, sha, files,
                                            self.current_font_size, self)
            if dialog.exec() == QDialog.Accepted:
                selected_file = dialog.get_selected_file()
                if selected_file:
                    self.perform_refine_changes(sha, selected_file)
            else:
                print(f"Cancelled refine {sha}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open refine dialog: {str(e)}")

    @staticmethod
    def _parse_hunks(diff_text):
        """
        Parse a unified diff (for one file) into a list of (header_line, body_text) tuples.
        header_line: the '@@ … @@' line (stripped)
        body_text:   the context/+/- lines that follow, as a single string
        """
        hunks = []
        current_header = None
        current_body_lines = []
        for line in diff_text.splitlines():
            if line.startswith("@@"):
                if current_header is not None:
                    hunks.append((current_header, "\n".join(current_body_lines)))
                current_header = line
                current_body_lines = []
            elif current_header is not None:
                current_body_lines.append(line)
        if current_header is not None:
            hunks.append((current_header, "\n".join(current_body_lines)))
        return hunks

    @staticmethod
    def _patch_has_changes(patch_text):
        """Return True if the patch still contains any added/removed content lines."""
        for line in patch_text.splitlines():
            if line.startswith(('+++', '---')):
                continue
            if line.startswith(('+', '-')):
                return True
        return False

    @staticmethod
    def _rebuild_patch(diff_header_text, all_hunks, kept_indices):
        """
        Build a minimal unified-diff patch string that contains only the kept hunks.
        Recalculates the +line offsets so 'git apply' accepts the patch cleanly.

        diff_header_text: the part of the diff before the first @@ (diff --git / --- / +++)
        all_hunks:        list of (header_line, body_text) for ALL hunks
        kept_indices:     indices into all_hunks that should appear in the result
        """
        if not kept_indices:
            return ""

        # Parse the original @@ -a,b +c,d @@ tails
        import re

        patch_parts = [diff_header_text]
        cumulative_offset = 0
        for idx in kept_indices:
            orig_hdr, body = all_hunks[idx]
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", orig_hdr)
            if not m:
                patch_parts.append(orig_hdr)
                patch_parts.append(body)
                continue

            minus_start = int(m.group(1))
            plus_start  = int(m.group(3))
            orig_plus_count = int(m.group(4)) if m.group(4) is not None else 1
            tail        = m.group(5)

            new_plus_start = plus_start + cumulative_offset

            # Count lines from body (splitlines preserves empty lines at end if keepends=False + trailing check)
            body_lines = body.split("\n")
            # Remove a single trailing empty string caused by a trailing \n
            if body_lines and body_lines[-1] == "":
                body_lines = body_lines[:-1]

            real_plus_count = sum(1 for l in body_lines if not l.startswith('-'))
            real_minus_count = sum(1 for l in body_lines if not l.startswith('+'))

            new_hdr = f"@@ -{minus_start},{real_minus_count} +{new_plus_start},{real_plus_count} @@{tail}"
            # Reconstruct body ensuring each line ends with \n
            body_text = "\n".join(body_lines) + "\n"

            patch_parts.append(new_hdr)
            patch_parts.append(body_text)

            # Update cumulative offset for subsequent hunks
            cumulative_offset += (real_plus_count - orig_plus_count)

        return "".join(f"{p}\n" if not p.endswith("\n") else p for p in patch_parts)

    def perform_refine_changes(self, sha, filepath):
        """
        Opens the hunk-selection dialog and, on acceptance, rewrites the commit
        so that only the selected hunks of `filepath` are kept.
        Keeps the dialog open and refreshes it until the user cancels.
        """
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return
        while True:
            try:
                raw_diff = get_file_diff_only_in_commit(self.repo_path, sha, filepath)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not load diff for {filepath}: {e}")
                break

            hunks = self._parse_hunks(raw_diff)
            if not hunks:
                QMessageBox.information(self, "No Hunks",
                                        f"No individual hunks found for {filepath} in commit {sha}.")
                break


            try:
                commit_msg = get_full_commit_message(self.repo_path, sha)
            except Exception:
                commit_msg = ""

            try:
                all_files = get_commit_files(self.repo_path, sha)
            except:
                all_files = [filepath]
            is_only_file = len(all_files) == 1

            dialog = RefineChangesDialog(sha, filepath, commit_msg,
                                         hunks, self.current_font_size, self, is_only_file=is_only_file)

            # When user clicks "Apply modification" in a hunk menu, treat it as a final "Keep Selected" action
            dialog.apply_hunk_modification.connect(dialog._on_keep)
            dialog.drop_hunk.connect(dialog._on_keep)

            if dialog.exec() != QDialog.Accepted:
                break

            result_action = getattr(dialog, 'result_action', 'keep')
            all_hunks = dialog.get_hunk_data() if hasattr(dialog, 'get_hunk_data') else hunks
            kept_indices = dialog.kept_indices
            moved_indices = getattr(dialog, 'moved_indices', [])

            # Bug fix: if it's the only file and we result in an empty commit, warn user
            # (is_only_file already computed above)

            if not kept_indices:
                if is_only_file:
                    action_name = "Drop" if result_action != "move" else "Move All"
                    feature_name = "Drop Commit" if result_action != "move" else "Move file changes out of this commit"
                    QMessageBox.information(
                        self, "Empty Commit",
                        f"You have selected to {action_name} all changes from the only file in this commit.\n\n"
                        f"This would result in an empty commit. Please use the dedicated '{feature_name}' feature instead."
                    )
                    break
                else:
                    # If there are other files, it's okay to drop all hunks from this one.
                    pass

            move_msg = ""
            if result_action == "move":
                default_msg = f"Change hunk from {sha[:8]} in {filepath}"
                dialog = NewCommitMessageDialog(
                    "New Commit Message",
                    "Enter commit message for the new commit (containing moved hunks):",
                    default_msg,
                    self.current_font_size,
                    self
                )
                if dialog.exec() != QDialog.Accepted:
                    break
                move_msg = dialog.get_message()

            self.save_undo_state()
            old_head = self.get_head_sha()

            # Build the partial patch (or empty string for full-drop)
            # Extract the diff header lines (up to first @@)
            header_lines = []
            for line in raw_diff.splitlines():
                if line.startswith("@@"):
                    break
                header_lines.append(line)
            diff_header_text = "\n".join(header_lines)

            partial_patch = self._rebuild_patch(diff_header_text, all_hunks, kept_indices)
            # DEBUG: partial_patch prints removed
            move_patch = ""
            if result_action == "move":
                move_patch = self._rebuild_patch(diff_header_text, all_hunks, moved_indices)

            # Minimal: warn if editing/deselecting leaves NO content in the only file
            if is_only_file and not self._patch_has_changes(partial_patch):
                QMessageBox.information(
                    self, "Empty Commit",
                    f"After refinement, '{filepath}' has no remaining changes in commit {sha[:8]}, "
                    "which is the only file in this commit.\n\n"
                    "This would create an empty commit. Please cancel and use "
                    "'Drop Commit' or 'Move file changes out of this commit' instead."
                )
                break

            action_script_content = f"""#!/usr/bin/env python3
import subprocess
import os
import tempfile
import sys

sha = {repr(sha)}
filepath = {repr(filepath)}
commit_msg = {repr(commit_msg)}
partial_patch = {repr(partial_patch)}
move_patch = {repr(move_patch)}
move_msg = {repr(move_msg)}
result_action = {repr(result_action)}

# 1. Soft-reset so the commit's changes go back into the staging area
subprocess.check_call(['git', 'reset', '--soft', 'HEAD~1'])

# 2. Restore this file to the state it had BEFORE the commit (parent's version)
subprocess.check_call(['git', 'checkout', 'HEAD', '--', filepath])

# 3. Apply the 'keep' patch (the ones that stay in original commit)
if partial_patch.strip():
    patch_fd, patch_path = tempfile.mkstemp(prefix='git_refine_keep_', suffix='.patch', text=True)
    with os.fdopen(patch_fd, 'w', encoding='utf-8') as pf:
        pf.write(partial_patch)
    try:
        subprocess.check_call(['git', 'apply', '--ignore-whitespace', patch_path])
        subprocess.check_call(['git', 'add', '--', filepath])
    except subprocess.CalledProcessError as e:
        print(f"FAILED to apply refinement patch for {{filepath}} in {{sha}}")
        print(f"Error: {{e}}")
        sys.exit(1)
    finally:
        try:
            os.unlink(patch_path)
        except:
            pass

# 4. Commit original changes (the ones we kept)
#    Use --allow-empty as a safety safeguard.
msg_fd, msg_path = tempfile.mkstemp(prefix='git_msg_orig_', text=True)
with os.fdopen(msg_fd, 'w', encoding='utf-8') as f:
    f.write(commit_msg)
try:
    subprocess.check_call(['git', 'commit', '--allow-empty', '-F', msg_path])
finally:
    try:
        os.unlink(msg_path)
    except:
        pass

# 5. If we are moving, apply the 'move' patch and commit again
if result_action == "move" and move_patch.strip():
    patch_fd, patch_path = tempfile.mkstemp(prefix='git_refine_move_', suffix='.patch', text=True)
    with os.fdopen(patch_fd, 'w', encoding='utf-8') as pf:
        pf.write(move_patch)
    try:
        subprocess.check_call(['git', 'apply', '--ignore-whitespace', patch_path])
        subprocess.check_call(['git', 'add', '--', filepath])
    except subprocess.CalledProcessError as e:
        print(f"FAILED to apply move patch for {{filepath}} in {{sha}}")
        print(f"Error: {{e}}")
        sys.exit(1)
    finally:
        try:
            os.unlink(patch_path)
        except:
            pass

    msg_fd, msg_path = tempfile.mkstemp(prefix='git_msg_move_', text=True)
    with os.fdopen(msg_fd, 'w', encoding='utf-8') as f:
        f.write(move_msg)
    try:
        subprocess.check_call(['git', 'commit', '--allow-empty', '-F', msg_path])
    finally:
        try:
            os.unlink(msg_path)
        except:
            pass
"""
            action_path = None
            editor_script = None
            try:
                action_fd, action_path = tempfile.mkstemp(prefix='git_refine_exec_', suffix='.py', text=True)
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
                    f.write("    stripped = line.strip()\n")
                    f.write("    parts = stripped.split()\n")
                    f.write("    # Match pick/reword/edit etc. followed by SHA\n")
                    f.write("    if not stripped.startswith('#') and len(parts) >= 2 and len(parts[1]) >= 4:\n")
                    f.write("        todo_sha = parts[1]\n")
                    f.write(f"        if {repr(sha)}.startswith(todo_sha) or todo_sha.startswith({repr(sha[:4])}):\n")
                    f.write("             output.append('pick ' + stripped.split(None, 1)[1] + '\\n')\n")
                    f.write("             output.append(single_exec + '\\n')\n")
                    f.write("             continue\n")
                    f.write("    output.append(line)\n")
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
                    if not has_parent:
                        QMessageBox.critical(self, "Cannot Refine",
                                             "Cannot refine the oldest commit (no parent).\n"
                                             "This operation only works when the commit has a parent.")
                        break
                    upstream = f"{sha}^"
                else:
                    upstream = current_shas[sha_idx + 1]

                env = os.environ.copy()
                env["GIT_SEQUENCE_EDITOR"] = _script_command(editor_script)
                env["GIT_EDITOR"] = "true"

                progress = ProgressDialog(
                    f"Applying refinement to {sha[:8]}...",
                    f"Processing changes in {filepath}. Please wait...",
                    self
                )
                progress.show()
                # Force visibility and add a small delay for human perception
                for _ in range(5):
                    QApplication.processEvents()
                    time.sleep(0.02)

                cmd = ["git", "rebase", "-i", upstream]
                result = subprocess.run(cmd, cwd=self.repo_path, env=env,
                                        capture_output=True, text=True)
            finally:
                _safe_unlink(editor_script, action_path)

            # Ensure the user sees the progress before it closes
            for _ in range(5):
                QApplication.processEvents()
                time.sleep(0.02)
            progress.close()

            if result.returncode == 0:
                self.load_history()
                new_head = self.get_head_sha()
                self.log_action(sha, f"refined {filepath}", old_head, new_head)
                # Find the new SHA at the same position to allow refreshing the dialog
                new_shas = [self.list_widget.item(i).text().split()[0]
                            for i in range(self.list_widget.count())]
                if sha_idx >= 0 and sha_idx < len(new_shas):
                    sha = new_shas[sha_idx]

                QMessageBox.information(self, "Success",
                                        f"Successfully refined changes for '{filepath}' in commit {sha[:8]}.\n\n"
                                        "The Refine/Edit window will now refresh.")
            else:
                print(f"Refine Changes: FAILED. {result.stderr}")
                ok, detail = self._abort_rebase_safely()
                if not ok:
                    self._warn_rebase_abort_failure(detail)
                QMessageBox.critical(
                    self,
                    "Refine Failed",
                    f"Could not apply refined changes.\n\n"
                    f"Patch failed to apply during rebase.\n\n"
                    f"Error:\n{result.stderr}\n\n"
                    f"If needed, resolve the issue manually and run:\n\n"
                    f"git rebase --continue"
                )
                self.load_history()
                break

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
            import tempfile, os, stat
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

            for index, (drop_sha, msg, will_be_empty) in enumerate(commits_to_drop):
                progress.label.setText(f"Rewriting commit {index+1}/{len(commits_to_drop)}...\n({drop_sha[:8]})")
                for _ in range(3):
                    QApplication.processEvents()

                # drop_sha is correctly the original SHA because we are rebasing backward
                has_parent = False
                try:
                    subprocess.run(["git", "rev-parse", f"{drop_sha}^"], cwd=self.repo_path, check=True, capture_output=True)
                    has_parent = True
                except:
                    pass
                upstream = f"{drop_sha}^" if has_parent else "--root"

                # Setup skip variables logic
                should_drop_entirely = drop_empty_commits and will_be_empty
                if should_drop_entirely:
                    empty_commits_dropped_count += 1

                action_script_content = f"""#!/usr/bin/env python3
import subprocess
import sys

filepath = {repr(filepath)}
drop_sha = {repr(drop_sha)}

try:
    if subprocess.run(['git', 'rev-parse', 'HEAD~1'], capture_output=True).returncode != 0:
        subprocess.check_call(['git', 'rm', '-f', '--ignore-unmatch', '--', filepath])
        subprocess.check_call(['git', 'commit', '--amend', '--allow-empty', '-C', drop_sha])
    else:
        subprocess.check_call(['git', 'reset', '--soft', 'HEAD~1'])
        subprocess.check_call(['git', 'reset', 'HEAD', '--', filepath])
        subprocess.check_call(['git', 'commit', '--allow-empty', '-C', drop_sha])
        subprocess.check_call(['git', 'reset', '--hard', 'HEAD'])
        subprocess.check_call(['git', 'clean', '-fd', '--', filepath])
except Exception as e:
    print("FAILED to replace commit:", e)
    sys.exit(1)
"""
                import tempfile, os, stat
                action_fd, action_path = tempfile.mkstemp(prefix='git_remove_action_', suffix='.py', text=True)
                with os.fdopen(action_fd, 'w', encoding='utf-8') as f:
                    f.write(action_script_content)

                single_exec = f"exec {_script_command(action_path)}"

                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
                    f.write("#!/usr/bin/env python3\n")
                    f.write("import sys\n")
                    f.write(f"target_sha = {repr(drop_sha)}\n")
                    f.write(f"should_drop_entirely = {repr(should_drop_entirely)}\n")
                    f.write(f"single_exec = {repr(single_exec)}\n")
                    f.write("todo_path = sys.argv[1]\n")
                    f.write("with open(todo_path, 'r') as tf:\n")
                    f.write("    lines = tf.readlines()\n")
                    f.write("output = []\n")
                    f.write("for line in lines:\n")
                    f.write("    stripped = line.strip()\n")
                    f.write("    is_target = not stripped.startswith('#') and len(stripped.split()) >= 2 and stripped.split()[1].startswith(target_sha)\n")
                    f.write("    if is_target and should_drop_entirely:\n")
                    f.write("        continue\n")
                    f.write("    output.append(line)\n")
                    f.write("    if is_target and not should_drop_entirely:\n")
                    f.write("        output.append(single_exec + '\\n')\n")
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
                except:
                    pass

                if result.returncode != 0:
                    ok, detail = self._abort_rebase_safely()
                    if not ok:
                        self._warn_rebase_abort_failure(detail)
                    progress.close()
                    QMessageBox.critical(self, "Failed", f"Failed while processing {drop_sha[:8]}. Aborted.\\n\\n{result.stderr}")
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
            _safe_unlink(editor_script, action_path)
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
        finally:
            self.load_history()

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
                        self.log_action(sha, f"split per-file", old_head, new_head)
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
            self.split_worker.start()
            progress.exec()
        except Exception as e:
            _safe_unlink(editor_script, action_path)
            QMessageBox.critical(self, "Error", f"An error occurred during split: {str(e)}")
            self.load_history()
