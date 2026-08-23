import os
import shlex
import subprocess
import tempfile
import time
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from lib.dialogs import ProgressDialog
from lib.app_window.helpers import _script_command, _safe_unlink, _posix_path


class RebaseMixin:
    """Interactive rebase and commit move operations."""

    def perform_move(self, new_shas, original_shas=None):
        """Performs commit reordering using our unified rebase logic."""
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return
        old_head = self.get_head_sha()
        print(f"[rebase] Commit reorder: {len(new_shas)} commits")
        if self.run_interactive_rebase(new_shas, original_shas=original_shas, progress_title="Moving Commits", progress_text="Reordering commits. Please wait..."):
            self.load_history()
            new_head = self.get_head_sha()
            self.log_action("N/A", "reordered commits", old_head, new_head)
            QMessageBox.information(self, "Success", "Commits reordered successfully!")
            return
        self.load_history()

    def run_interactive_rebase(self, new_shas, rephrase_map=None, squash_shas=None, original_shas=None, progress_title="Rebasing", progress_text="Executing interactive rebase. Please wait...\nThis might take a few moments.", suppress_failure_box=False, progress_dialog=None):
        """
        Unified handler for history rewriting using git rebase -i.
        original_shas: The pre-change SHA order (latest-first). If provided, used
                       for prefix comparison instead of reading list_widget (which
                       may already show the new order after a drag-drop).
        """
        self.save_undo_state()
        print("Starting interactive rebase...")
        try:
            # 1. Determine common prefix to minimize work
            # Use the explicitly passed original order when available (e.g., after a drag)
            if original_shas is not None:
                display_shas = original_shas
            else:
                display_shas = [self.list_widget.item(i).text().split()[0] for i in range(self.list_widget.count())]
            old_order = list(reversed(display_shas))
            proposed_order = list(reversed(new_shas))

            common_count = 0
            for old, new in zip(old_order, proposed_order):
                # A commit is only "common" if it's the same SHA AND not being modified
                if old == new and (not rephrase_map or old not in rephrase_map) and (not squash_shas or old not in squash_shas):
                    common_count += 1
                else:
                    break

            # Determine upstream and suffix to re-process
            if common_count > 0:
                upstream = old_order[common_count - 1]
                todo_shas = proposed_order[common_count:]

                # SQUASH FIX: If the first commit to reprocess is a squash,
                # we MUST include at least one commit before it (the pick target)
                if todo_shas and squash_shas and todo_shas[0] in squash_shas:
                    if common_count > 1:
                        common_count -= 1
                        upstream = old_order[common_count - 1]
                        todo_shas = proposed_order[common_count:]
                    else:
                        # We are squashing into the very first commit of our visible range
                        common_count = 0 # Fall back to full rebase logic below

            if common_count == 0:
                # Check root status (self.commit_sha is the branch base / the last commit NOT shown)
                # We use self.commit_sha directly as upstream, NOT self.commit_sha^.
                # self.commit_sha is already the parent of the first local commit, so only
                # local commits fall in the rebase range. Using self.commit_sha^ would pull
                # the branch-base commit into the rebase range, causing it to be dropped or
                # squashed because it doesn't appear in the todo list.
                has_parent = False
                try:
                    subprocess.run(["git", "rev-parse", f"{self.commit_sha}^"],
                                   cwd=self.repo_path, check=True, capture_output=True)
                    has_parent = True
                except:
                    has_parent = False
                upstream = self.commit_sha if has_parent else "--root"
                todo_shas = proposed_order

            # Show progress dialog
            own_progress = progress_dialog is None
            if own_progress:
                progress = ProgressDialog(progress_title, progress_text, self)
                progress.show()
                QApplication.processEvents()
            else:
                progress = progress_dialog

            try:
                # Feature: Fast-track top-drops (reset --hard)
                if not todo_shas and common_count > 0:
                    print(f"Fast-tracking drop via reset --hard to {upstream}")
                    process = subprocess.Popen(["git", "reset", "--hard", upstream],
                                               cwd=self.repo_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    while process.poll() is None:
                        QApplication.processEvents()
                        time.sleep(0.05)

                    if process.returncode != 0:
                        stdout, stderr = process.communicate()
                        raise Exception(f"Fast-track reset failed: {stderr}")

                    # Small non-blocking delay to ensure the progress window is seen by the user
                    # and has a chance to paint correctly if the operation was near-instant.
                    for _ in range(10):
                        QApplication.processEvents()
                        time.sleep(0.05)
                    return True

                # 2. Proceed with rebase for non-trivial changes
                msg_files = {}  # sha -> temp file path
                editor_script = None
                try:
                    # Write each rephrase message to a temp file to handle multi-line messages safely
                    if rephrase_map:
                        for sha, msg in rephrase_map.items():
                            if sha in todo_shas:
                                mf = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
                                mf.write(msg)
                                mf.close()
                                msg_files[sha] = mf.name

                    # Shell-quote each message path up front so the editor script
                    # (which only imports sys) can embed them in exec todo lines.
                    msg_f_args = {sha: shlex.quote(_posix_path(p)) for sha, p in msg_files.items()}

                    # Build a sequence editor script that writes the rebase todo
                    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
                        f.write("#!/usr/bin/env python3\n")
                        f.write("import sys\n")
                        f.write(f"new_order = {todo_shas}\n")
                        f.write(f"msg_files = {repr(msg_files)}\n")
                        f.write(f"msg_f_args = {repr(msg_f_args)}\n")
                        f.write(f"squash_shas = {squash_shas or []}\n")
                        f.write("todo_path = sys.argv[1]\n")
                        f.write("with open(todo_path, 'w') as f:\n")
                        f.write("    for sha in new_order:\n")
                        f.write("        op = 'squash' if sha in squash_shas else 'pick'\n")
                        f.write("        f.write(f'{op} {sha}\\n')\n")
                        f.write("        if sha in msg_files:\n")
                        f.write("            f.write(f'exec git commit --amend -F {msg_f_args[sha]}\\n')\n")
                        editor_script = f.name


                    env = os.environ.copy()
                    env["GIT_SEQUENCE_EDITOR"] = _script_command(editor_script)
                    env["GIT_EDITOR"] = "true"

                    if upstream == "--root":
                        cmd = ["git", "rebase", "-i", "--autosquash", "--root"]
                    else:
                        cmd = ["git", "rebase", "-i", "--autosquash", upstream]

                    process = subprocess.Popen(cmd, cwd=self.repo_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    while process.poll() is None:
                        QApplication.processEvents()
                        time.sleep(0.05)

                    stdout, stderr = process.communicate()

                    result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
                finally:
                    _safe_unlink(editor_script, *msg_files.values())

                if result.returncode == 0:
                    return True
                else:
                    ok, detail = self._abort_rebase_safely()
                    if not ok:
                        self._warn_rebase_abort_failure(detail)
                    if not suppress_failure_box:
                        QMessageBox.critical(self, "Rebase Failed",
                            f"Action failed (likely due to merge conflicts).\n"
                            f"The rebase has been aborted.\n\nError: {result.stderr}")
                    return False

            finally:
                if own_progress:
                    progress.close()

        except Exception as e:
            if not suppress_failure_box:
                QMessageBox.critical(self, "Error", f"An error occurred during rebase: {str(e)}")
            return False
