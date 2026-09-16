import os
import shlex
import subprocess
import tempfile
import time
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
)
from lib.dialogs import ProgressDialog
from lib.app_window.helpers import (
    _posix_path,
    _safe_unlink,
    _script_command,
)


class RebaseMixin:
    """Interactive rebase and commit move operations."""

    def perform_move(self, new_shas, original_shas=None, upstream_override=None):
        """Performs commit reordering using our unified rebase logic."""
        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return
        if not self._check_staged_changes():
            return
        old_head = self.get_head_sha()
        print(f"[rebase] Commit reorder: {len(new_shas)} commits")
        result = self.run_interactive_rebase(new_shas, original_shas=original_shas, upstream_override=upstream_override, progress_title="Moving Commits", progress_text="Reordering commits. Please wait...")
        if result:
            self.load_history()
            new_head = self.get_head_sha()
            self.log_action("N/A", "reordered commits", old_head, new_head)
            QMessageBox.information(self, "Success", "Commits reordered successfully!")
            return
        self.load_history()

    def run_interactive_rebase(self, new_shas, rephrase_map=None, squash_shas=None, original_shas=None, upstream_override=None, progress_title="Rebasing", progress_text="Executing interactive rebase. Please wait...\nThis might take a few moments.", suppress_failure_box=False, progress_dialog=None):
        """
        Unified handler for history rewriting using git rebase -i.
        original_shas: The pre-change SHA order (latest-first). If provided, used
                       for prefix comparison instead of reading list_widget (which
                       may already show the new order after a drag-drop).
        upstream_override: If provided, skip common-prefix detection and rebase
                           these SHAs onto this upstream directly.
        """
        self.save_undo_state()
        print("Starting interactive rebase...")
        try:
            # If upstream is pre-computed (e.g. multi-drag with affected-only SHAs),
            # skip common-prefix detection entirely and rebase the provided SHAs
            # directly onto the given upstream.
            if upstream_override is not None:
                # Pre-computed upstream (e.g. multi-drag with affected-only SHAs).
                # Skip common-prefix detection and rebase the provided SHAs directly.
                upstream = upstream_override
                todo_shas = list(reversed(new_shas))
                common_count = 0
            else:
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

                    # Detect merge commits — they need --rebase-merges
                    merge_shas = set()
                    for sha in todo_shas:
                        try:
                            cat = subprocess.run(
                                ["git", "cat-file", "-p", sha],
                                cwd=self.repo_path, capture_output=True, text=True,
                                encoding='utf-8', errors='replace',
                            )
                            parents = [l for l in cat.stdout.splitlines() if l.startswith("parent ")]
                            if len(parents) > 1:
                                merge_shas.add(sha)
                        except Exception:
                            pass

                    has_merges = bool(merge_shas)

                    # Build a sequence editor script
                    if has_merges:
                        # --rebase-merges: git generates a complex todo with
                        # reset/# Branch/merge -C lines.  Our script must READ
                        # that todo, parse it into reorderable blocks, and
                        # rewrite it in the desired order.
                        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.py') as f:
                            f.write("#!/usr/bin/env python3\n")
                            f.write("import sys, re\n")
                            f.write(f"new_order = {todo_shas}\n")
                            f.write(f"squash_shas = {squash_shas or []}\n")
                            f.write(f"msg_files = {repr(msg_files)}\n")
                            f.write(f"msg_f_args = {repr(msg_f_args)}\n")
                            f.write("todo_path = sys.argv[1]\n")
                            f.write("with open(todo_path) as tf:\n")
                            f.write("    lines = tf.readlines()\n")
                            # Parse into blocks: each block is identified by a SHA.
                        # --rebase-merges todo format:
                        #   reset onto <sha>          (line 0, always present)
                        #   pick <sha> <msg>          (standalone commit)
                        #   # Branch <ref>            (start of merge block)
                        #   reset <parent-sha>
                        #   pick <sha> <msg> ...      (branch commits)
                        #   merge -C <sha> <ref> # <msg>  (end of merge block)
                            f.write("blocks = []  # list of (sha, [lines])\n")
                            f.write("current = []\n")
                            f.write("in_merge = False\n")
                            f.write("onto_line = lines[0] if lines else ''\n")
                            f.write("for line in lines[1:]:\n")
                            f.write("    s = line.strip()\n")
                            f.write("    if s.startswith('# Branch'):\n")
                            f.write("        if current:\n")
                            f.write("            blocks.append(current)\n")
                            f.write("        current = [line]\n")
                            f.write("        in_merge = True\n")
                            f.write("    elif s.startswith('merge -C') or s.startswith('merge -c'):\n")
                            f.write("        current.append(line)\n")
                            f.write("        blocks.append(current)\n")
                            f.write("        current = []\n")
                            f.write("        in_merge = False\n")
                            f.write("    elif in_merge:\n")
                            f.write("        current.append(line)\n")
                            f.write("    elif s.startswith('pick '):\n")
                            f.write("        if current:\n")
                            f.write("            blocks.append(current)\n")
                            f.write("        current = [line]\n")
                            f.write("    elif s.startswith('reset onto'):\n")
                            f.write("        pass  # handled separately\n")
                            f.write("    else:\n")
                            f.write("        if current:\n")
                            f.write("            current.append(line)\n")
                            f.write("        else:\n")
                            f.write("            current = [line]\n")
                            f.write("if current:\n")
                            f.write("    blocks.append(current)\n")
                            # Extract SHA from each block
                            f.write("def block_sha(bl):\n")
                            f.write("    first = bl[0].strip()\n")
                            f.write("    if first.startswith('pick '):\n")
                            f.write("        return first.split()[1]\n")
                            f.write("    # merge block — find merge -C line\n")
                            f.write("    for bl in bl:\n")
                            f.write("        s = bl.strip()\n")
                            f.write("        if s.startswith('merge -C') or s.startswith('merge -c'):\n")
                            f.write("            parts = s.split()\n")
                            f.write("            if '-C' in parts:\n")
                            f.write("                return parts[parts.index('-C') + 1]\n")
                            f.write("            elif '-c' in parts:\n")
                            f.write("                return parts[parts.index('-c') + 1]\n")
                            f.write("    return None\n")
                            # Map SHA -> block
                            f.write("block_map = {}\n")
                            f.write("orphan = []\n")
                            f.write("for bl in blocks:\n")
                            f.write("    sha = block_sha(bl)\n")
                            f.write("    if sha:\n")
                            f.write("        block_map[sha] = bl\n")
                            f.write("    else:\n")
                            f.write("        orphan.append(bl)\n")
                            # Reorder and write
                            f.write("with open(todo_path, 'w') as f:\n")
                            f.write("    f.write(onto_line)\n")
                            f.write("    for sha in new_order:\n")
                            f.write("        if sha in block_map:\n")
                            f.write("            bl = block_map[sha]\n")
                            f.write("            if sha in squash_shas:\n")
                            f.write("                # Change first pick to squash; for merge use 'merge -c' with -m\n")
                            f.write("                first = bl[0]\n")
                            f.write("                if first.strip().startswith('pick '):\n")
                            f.write("                    bl = [first.replace('pick ', 'squash ', 1)] + bl[1:]\n")
                            f.write("                elif first.strip().startswith('merge -C'):\n")
                            f.write("                    bl = [first.replace('merge -C', 'merge -c', 1)] + bl[1:]\n")
                            f.write("            for bline in bl:\n")
                            f.write("                f.write(bline)\n")
                            f.write("            if sha in msg_files:\n")
                            f.write("                f.write(f'exec git commit --amend -F {msg_f_args[sha]}\\n')\n")
                            f.write("        else:\n")
                            f.write("            f.write(f'pick {sha}\\n')\n")
                            f.write("            if sha in msg_files:\n")
                            f.write("                f.write(f'exec git commit --amend -F {msg_f_args[sha]}\\n')\n")
                            f.write("    for bl in orphan:\n")
                            f.write("        for bline in bl:\n")
                            f.write("            f.write(bline)\n")
                            editor_script = f.name
                    else:
                        # Simple case: no merge commits, write pick/squash lines
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

                    if has_merges:
                        cmd.insert(cmd.index("-i") + 1, "--rebase-merges")

                    process = subprocess.Popen(cmd, cwd=self.repo_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    out_chunks, err_chunks = [], []
                    while process.poll() is None:
                        QApplication.processEvents()
                        try:
                            out, err = process.communicate(timeout=0.05)
                            out_chunks.append(out)
                            err_chunks.append(err)
                        except subprocess.TimeoutExpired as te:
                            if te.stdout:
                                out_chunks.append(te.stdout if isinstance(te.stdout, str) else te.stdout.decode('utf-8', 'replace'))
                            if te.stderr:
                                err_chunks.append(te.stderr if isinstance(te.stderr, str) else te.stderr.decode('utf-8', 'replace'))

                    out_rest, err_rest = process.communicate()
                    out_chunks.append(out_rest)
                    err_chunks.append(err_rest)

                    stdout = "".join(out_chunks)
                    stderr = "".join(err_chunks)

                    result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
                finally:
                    _safe_unlink(editor_script, *msg_files.values())

                if result.returncode == 0:
                    return True
                else:
                    ok, detail = self._abort_rebase_safely()
                    if not ok:
                        self._warn_rebase_abort_failure(detail)
                    # Restore the list to the correct (pre-rebase) state
                    # BEFORE showing the failure dialog, so the user sees
                    # the right commits behind the modal.
                    self.load_history()
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
