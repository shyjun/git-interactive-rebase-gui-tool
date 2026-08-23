import re
import subprocess
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from lib.git_helpers import (
    get_current_branch, get_full_head_sha, get_commit_subject,
    has_uncommitted_changes, normalize_branch_ref,
    cherry_pick_in_progress, classify_cherry_pick_failure,
    rebase_in_progress,
)
from lib.dialogs import CherryPickDialog


class CherryPickMixin:
    def handle_cherry_pick(self):
        """Cherry-picks a single commit entered by the user."""
        import re
        dialog = CherryPickDialog(self.current_font_size, self)
        if dialog.exec() != QDialog.Accepted:
            print("Cancelled cherry-pick.")
            return

        sha = dialog.get_sha()
        if not re.fullmatch(r"[0-9a-fA-F]{4,40}", sha):
            QMessageBox.warning(self, "Invalid Commit SHA", "Please enter a valid commit SHA.")
            return

        if not self._check_not_viewer_mode():
            return
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return

        cmd = ["git", "cherry-pick"]
        no_commit = dialog.chosen == "no_commit"
        if no_commit:
            cmd.append("--no-commit")
        cmd.append(sha)

        try:
            result = subprocess.run(
                cmd, cwd=self.repo_path, capture_output=True, text=True,
                encoding='utf-8', errors='replace'
            )
            if result.returncode == 0:
                self.load_history()
                if no_commit:
                    QMessageBox.information(
                        self, "Success",
                        "Changes have been applied without creating a commit."
                    )
                else:
                    self._show_cherry_pick_result("Cherry-pick succeeded.", [sha], [])
                return

            message = self._cherry_pick_failure_message(sha, result.stderr or "")
            try:
                ok, detail = self._run_abort_cherry_pick()
                if not ok:
                    self._warn_abort_failure(detail)
            except Exception:
                pass
            self.load_history()
            QMessageBox.critical(
                self, "Cherry-pick Failed", message
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred while cherry-picking: {str(e)}")

    def _collect_browse_cherry_pick_shas(self):
        """Returns the SHAs to cherry-pick from the browse window.

        In multi-select mode, gathers the checked commits (in list order, which
        is newest first) and then reverses them so cherry-picks apply oldest
        first, matching the original branch chronology (e.g. branch
        A-B-C-D-E-F pick B, D, F in that order).
        Otherwise returns the single currently selected commit.
        """
        if self.multi_select_mode:
            shas = [
                self.list_widget.item(i).text().split()[0]
                for i in range(self.list_widget.count())
                if self.list_widget.item(i).checkState() == Qt.Checked
            ]
            shas.reverse()
        else:
            item = self.list_widget.currentItem()
            shas = [item.text().split()[0]] if item else []
        return shas

    def _run_cherry_pick(self, sha):
        """Runs 'git cherry-pick <sha>'. Returns (success, stderr_or_empty)."""
        try:
            result = subprocess.run(
                ["git", "cherry-pick", sha], cwd=self.repo_path,
                capture_output=True, text=True, encoding='utf-8', errors='replace'
            )
        except Exception as e:
            return False, str(e)
        if result.returncode == 0:
            return True, ""
        return False, result.stderr.strip()

    def _run_abort_cherry_pick(self):
        """Runs 'git cherry-pick --abort' and verifies the repo is clean again.

        Returns (ok, detail). ok is True only if no pending cherry-pick state
        remains. '--abort' failing because nothing was in progress counts as
        clean, so ok is based on CHERRY_PICK_HEAD being gone, not the command's
        exit code."""
        try:
            result = subprocess.run(
                ["git", "cherry-pick", "--abort"], cwd=self.repo_path,
                capture_output=True, text=True, encoding='utf-8', errors='replace'
            )
        except Exception as e:
            return False, f"{e}"
        if cherry_pick_in_progress(self.repo_path):
            detail = result.stderr.strip() or result.stdout.strip()
            return False, detail or "repo is still in a cherry-pick state"
        return True, ""

    def _cherry_pick_failure_message(self, sha, stderr):
        """Builds a user-friendly failure message for a failed cherry-pick.

        The cherry-pick is aborted by callers shortly after, so the message
        avoids git's own 'resolve conflicts / --continue / --skip / --abort'
        hints that would no longer apply."""
        kind, detail = classify_cherry_pick_failure(self.repo_path, stderr)
        short = sha[:10] if sha else "commit"
        if kind == "conflict":
            files = "<br/>".join(f"&nbsp;&nbsp;&nbsp;&nbsp;{path}" for path in detail.splitlines())
            return (
                f"<p>Cherry-pick of <b>{short}</b> failed because it conflicts with "
                f"the current branch.</p>"
                f"<p>The cherry-pick was <b>aborted</b>, so no changes were made.</p>"
                f"<p>Conflicting files:<br/>{files}</p>"
            )
        if kind == "empty":
            return (
                f"<p>Cherry-pick of <b>{short}</b> failed - the commit is already "
                f"present in this branch or produces no change here.</p>"
                f"<p>No changes were made.</p>"
            )
        first_line = detail.splitlines()[0] if detail else "no error details"
        return (
            f"<p>Cherry-pick of <b>{short}</b> failed.</p>"
            f"<p>No changes were made, and the cherry-pick was aborted.</p>"
            f"<p>{first_line}</p>"
        )

    def _warn_abort_failure(self, detail):
        """Shows a warning when cleanup after a failed cherry-pick did not fully
        succeed, so the user is never left mid-pick without knowing it."""
        QMessageBox.warning(
            self, "Cherry-pick Cleanup Failed",
            f"The repository may still be in a cherry-pick state:\n\n{detail}"
        )

    def _show_cherry_pick_result(self, headline, cherry_picked_shas, skipped_shas):
        """Shows a summary of a cherry-pick operation (single or batch).

        Lists how many commits succeeded and failed, plus the SHAs of the
        failed ones, so the user always gets pass/fail counts."""
        picked = cherry_picked_shas or []
        failed = skipped_shas or []

        def block(label, shas_list):
            if not shas_list:
                return f"<b>{label}:</b> 0"
            body = "<br/>".join(s[:7] for s in shas_list)
            return f"<b>{label}:</b> {len(shas_list)}<br/>{body}"

        QMessageBox.information(
            self, "Cherry-pick Result",
            f"<p><b>{headline}</b></p>"
            f"<p>{block('Cherry-picked', picked)}<br/><br/>"
            f"{block('Failed', failed)}</p>"
        )

    def handle_browse_cherry_pick(self):
        """Cherry-picks the selected commit(s) from the browse window.

        Single selection: cherry-pick that commit directly (with the same
        standard pre-checks as the main window).
        Multi selection: confirm the apply order, then apply one by one,
        handling each failure, and report a summary at the end.
        """
        # If the browsed branch is the same as the current branch, there is
        # nothing meaningful to cherry-pick.
        if self.browse_branch:
            current_branch = get_current_branch(self.repo_path)
            if current_branch:
                current_ref = normalize_branch_ref(self.repo_path, current_branch)
                if current_ref == self.browse_branch:
                    QMessageBox.information(
                        self, "Same Branch",
                        "The branch you are browsing is the same as your current "
                        "branch, so cherry-picking is not applicable."
                    )
                    return

        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return

        shas = self._collect_browse_cherry_pick_shas()
        if not shas:
            QMessageBox.warning(self, "No Selection",
                                "Please select a commit to cherry-pick.")
            return

        if len(shas) == 1:
            self._cherry_pick_single(shas[0])
        else:
            self._cherry_pick_sequence(shas)

        # The pick reloaded the list asynchronously with fresh items that carry
        # no checkboxes, but the button/checkbox state from select-mode is still
        # active. Drop it so the UI returns to the normal single-select state.
        if self.multi_select_mode:
            self.exit_browse_multi_select()

    @staticmethod
    def _make_resizable_message_box(parent):
        """Creates a QMessageBox that is genuinely resizable.

        QMessageBox caps its own maximum size when it builds its layout, so
        enabling the size grip alone shows the grab-handle but the window will
        not grow. Keeps lifting the cap for the first second the box is shown,
        at which point Qt has finished its internal layout passes."""
        box = QMessageBox(parent)
        box.setSizeGripEnabled(True)

        def unlock():
            box.setMaximumSize(16777215, 16777215)

        unlock_timer = QTimer(box)
        unlock_timer.setInterval(15)
        unlock_timer.timeout.connect(unlock)
        unlock_timer.start()
        QTimer.singleShot(1000, unlock_timer.stop)
        return box

    def _refresh_parent_main_window(self):
        """Reloads the commit list of the main (parent) window that owns this
        browse viewer, so cherry-picks done from the browse window are reflected
        there immediately. The cached HEAD is updated before sync too, so
        immediate re-checks never see a stale 'repository has changed' state
        even before the async history reload finishes."""
        parent = self.parent()
        if parent is None or getattr(parent, "browse_mode", False):
            return
        parent.cached_current_head_full_sha = get_full_head_sha(self.repo_path)
        parent.cached_has_uncommitted = has_uncommitted_changes(self.repo_path)
        parent.load_history()

    def _sync_cached_head(self):
        """Refreshes this window's cached HEAD/status synchronously so that
        subsequent pre-checks do not report a bogus 'repository has changed'
        while the asynchronous history reload is still running."""
        self.cached_current_head_full_sha = get_full_head_sha(self.repo_path)
        self.cached_has_uncommitted = has_uncommitted_changes(self.repo_path)

    def _cherry_pick_single(self, sha):
        """Cherry-picks a single commit with the standard safety checks."""
        # Safety checks: repo unchanged and no unstaged changes.
        if not self._check_head_unchanged():
            return
        if not self._check_no_unstaged_changes():
            return

        success, err = self._run_cherry_pick(sha)
        if success:
            self._sync_cached_head()
            self.load_history()
            self._refresh_parent_main_window()
            self._show_cherry_pick_result("Cherry-pick succeeded.", [sha], [])
        else:
            message = self._cherry_pick_failure_message(sha, err)
            ok, detail = self._run_abort_cherry_pick()
            if not ok:
                self._warn_abort_failure(detail)
            self._sync_cached_head()
            self.load_history()
            self._refresh_parent_main_window()
            box = self._make_resizable_message_box(self)
            box.setWindowTitle("Cherry-pick Failed")
            box.setTextFormat(Qt.RichText)
            box.setText(message)
            box.setIcon(QMessageBox.Critical)
            box.addButton("OK", QMessageBox.AcceptRole)
            box.exec()

    def _cherry_pick_sequence(self, shas):
        """Cherry-picks a list of SHAs one by one, asking how to proceed on
        each failure, then shows a summary."""
        # (Safety checks already done by the caller.)
        target_branch = get_current_branch(self.repo_path)

        n = len(shas)
        lines = []
        for i, sha in enumerate(shas):
            try:
                subject = get_commit_subject(self.repo_path, sha)
            except Exception:
                subject = ""
            if len(subject) > 80:
                subject = subject[:80] + "..."
            lines.append(f"{i + 1}. {sha[:7]}: {subject}".rstrip())
        order_html = "<br/>".join(lines) if lines else ", ".join(sha[:7] for sha in shas)

        box = self._make_resizable_message_box(self)
        box.setWindowTitle("Cherry-pick Selected Commits")
        box.setTextFormat(Qt.RichText)
        box.setText(
            f"<p>Cherry-pick selected commit(s) to <b>{target_branch}</b>?</p>"
            f"<p>They will be applied in this order:</p>"
            f"<p>{order_html}</p>"
            f"<p>Continue?</p>"
        )
        yes_btn = box.addButton("Yes", QMessageBox.YesRole)
        no_btn = box.addButton("No", QMessageBox.NoRole)
        box.exec()
        if box.clickedButton() is not yes_btn:
            return

        head_before = get_full_head_sha(self.repo_path)

        cherry_picked_total = len(shas)
        cherry_picked = 0
        skipped = 0
        cherry_picked_shas = []
        skipped_shas = []
        # 'not_cherry_picked' counts commits that were neither applied nor skipped
        # (failures the user stopped on, plus everything left after a stop/undo).
        not_cherry_picked = 0
        stop = False

        for current_index, sha in enumerate(shas):
            success, err = self._run_cherry_pick(sha)
            if success:
                cherry_picked += 1
                cherry_picked_shas.append(sha)
                continue

            # A cherry-pick failed. Offer recovery choices.
            remaining_after = cherry_picked_total - cherry_picked - skipped - 1
            kind, detail = classify_cherry_pick_failure(self.repo_path, err)
            if kind == "conflict":
                reason = "It conflicts with the current branch."
            elif kind == "empty":
                reason = "The commit is already present or produces no change."
            else:
                reason = detail.splitlines()[0] if detail else "unknown error"
            def format_sha_list(shas_list):
                lines = []
                for s in shas_list:
                    try:
                        subject = get_commit_subject(self.repo_path, s)
                    except Exception:
                        subject = ""
                    if len(subject) > 80:
                        subject = subject[:80] + "..."
                    lines.append(f"{s[:7]}: {subject}".rstrip())
                return "<br/>".join(lines) if lines else "<i>none</i>"

            pending_shas = shas[current_index + 1:]
            box = self._make_resizable_message_box(self)
            box.setWindowTitle("Cherry-pick Failed")
            box.setTextFormat(Qt.RichText)
            box.setText(
                f"<p>Cherry-pick of <b>{sha[:10]}</b> failed.</p>"
                f"<p>Reason: {reason}</p>"
                f"<p>Successfully cherry-picked so far: <b>{cherry_picked}</b><br/>"
                f"{format_sha_list(cherry_picked_shas)}</p>"
                f"<p>Pending commits: <b>{remaining_after}</b><br/>"
                f"{format_sha_list(pending_shas)}</p>"
            )
            undo_btn = box.addButton("Undo entire cherry-pick", QMessageBox.DestructiveRole)
            skip_btn = box.addButton("Skip this and continue with next", QMessageBox.AcceptRole)
            stop_btn = box.addButton("Stop cherry-pick here, I'll cherry-pick manually",
                                     QMessageBox.RejectRole)
            box.exec()
            clicked = box.clickedButton()

            if clicked is undo_btn:
                subprocess.run(
                    ["git", "reset", "--hard", head_before], cwd=self.repo_path,
                    capture_output=True, text=True, encoding='utf-8', errors='replace'
                )
                ok, detail = self._run_abort_cherry_pick()
                if not ok:
                    self._warn_abort_failure(detail)
                # Nothing remains applied; skipped commits were never applied.
                skipped += 1  # the failed one counts as skipped
                skipped_shas.append(sha)
                cherry_picked = 0
                cherry_picked_shas = []
                stop = True
            elif clicked is skip_btn:
                ok, detail = self._run_abort_cherry_pick()
                if not ok:
                    self._warn_abort_failure(detail)
                skipped += 1
                skipped_shas.append(sha)
            else:  # stop
                ok, detail = self._run_abort_cherry_pick()
                if not ok:
                    self._warn_abort_failure(detail)
                skipped += 1
                skipped_shas.append(sha)
                stop = True

            if stop:
                break

        # Everything not cherry-picked or skipped is "not cherry-picked".
        not_cherry_picked = cherry_picked_total - cherry_picked - skipped
        not_cherry_picked_shas = [s for s in shas
                                  if s not in cherry_picked_shas and s not in skipped_shas]

        self._sync_cached_head()
        self.load_history()
        if cherry_picked > 0:
            self._refresh_parent_main_window()

        if not_cherry_picked == 0 and skipped == 0:
            headline = "Cherry-pick(s) succeeded."
        elif cherry_picked == 0:
            headline = "Cherry-pick failed - no commits were applied."
        else:
            headline = "Cherry-pick partially succeeded."

        def _summary_block(label, shas_list):
            if not shas_list:
                return f"<b>{label}:</b> 0"
            body = "<br/>".join(s[:7] for s in shas_list)
            return f"<b>{label}:</b> {len(shas_list)}<br/>{body}"

        box = self._make_resizable_message_box(self)
        box.setWindowTitle("Cherry-pick Summary")
        box.setTextFormat(Qt.RichText)
        box.setText(
            f"<p><b>{headline}</b></p>"
            f"<p>{_summary_block('Cherry-picked', cherry_picked_shas)}<br/><br/>"
            f"{_summary_block('Skipped', skipped_shas)}<br/><br/>"
            f"{_summary_block('Not cherry-picked', not_cherry_picked_shas)}</p>"
        )
        box.addButton("OK", QMessageBox.AcceptRole)
        box.exec()

    def _abort_rebase_safely(self):
        """Runs 'git rebase --abort' and verifies the repository is out of a rebase state.

        Returns (ok, detail). ok is True only when the repository is definitively
        known to be out of a rebase state afterwards, and the abort actually ran
        cleanly when a rebase was in progress. If no rebase was in progress
        beforehand, it is trivially clean. A rebase state whose presence could not
        be determined (None) is never treated as clean."""
        try:
            before = rebase_in_progress(self.repo_path)
            if before is False:
                return True, ""
            result = subprocess.run(
                ["git", "rebase", "--abort"], cwd=self.repo_path,
                capture_output=True, text=True, encoding='utf-8', errors='replace'
            )
            if before is True and result.returncode != 0:
                stderr = result.stderr.strip() if result.stderr else ""
                return False, (
                    f"'git rebase --abort' exited with code {result.returncode}"
                    + (f": {stderr}" if stderr else "")
                )
            after = rebase_in_progress(self.repo_path)
            if after is not False:
                if after is None:
                    return False, "could not determine whether the repository is still in a rebase state"
                return False, "the repo is still in a rebase state"
            return True, ""
        except Exception as e:
            return False, f"{e}"

    def _warn_rebase_abort_failure(self, detail):
        """Shows a warning when cleanup after a failed rebase did not fully
        succeed, so the user is never left mid-rebase without knowing it."""
        QMessageBox.warning(
            self, "Rebase Cleanup Failed",
            f"The repository may still be in a rebase state:\n\n{detail}"
        )
