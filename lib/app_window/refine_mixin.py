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
    RefineFileSelectDialog, RefineChangesDialog,
    NewCommitMessageDialog, ProgressDialog,
)
from lib.app_window.helpers import _script_command, _safe_unlink
from lib.app_window.split_utils import (
    parse_hunks as _parse_hunks,
    rebuild_patch as _rebuild_patch,
    patch_has_changes as _patch_has_changes,
)


class RefineMixin:
    """Refine changes within a single file of a commit."""

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

            hunks = _parse_hunks(raw_diff)
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

            partial_patch = _rebuild_patch(diff_header_text, all_hunks, kept_indices)
            # DEBUG: partial_patch prints removed
            move_patch = ""
            if result_action == "move":
                move_patch = _rebuild_patch(diff_header_text, all_hunks, moved_indices)

            # Minimal: warn if editing/deselecting leaves NO content in the only file
            if is_only_file and not _patch_has_changes(partial_patch):
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
