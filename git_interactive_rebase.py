#!/usr/bin/env python3
"""
Project: git-interactive-rebase-gui-tool
Description: A premium PySide6 GUI for interactive git rebasing, squashing, and rephrasing.
Author: shyjun(n.shyju@gmail.com)
Version: 1.0.0
Date: Feb 2026
"""
import argparse
# Copyright (c) 2026 shyjun
# This project is licensed under the MIT License - see the LICENSE file for details.
import json
import sys
import os
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import (
    Qt,
    QSettings,
    QTimer,
)

from lib.utils import get_assets_path
from lib.git_helpers import (
    get_recent_history_start,
    get_branch_base_info,
    stash_changes,
    get_unstaged_files,
    classify_tracked_changes,
    commit_file,
    bulk_commit_all,
    amend_with_head,
    stash_pop,
    stash_pop_can_apply,
    get_full_head_sha,
    get_head_sha,
    discard_changes,
    get_stash_status,
    STASH_NOTHING_STASHED,
    normalize_branch_ref,
    get_merge_base,
    perform_self_update,
)
from lib.app_window import (
    GitInteractiveRebaseApp,
    get_theme_stylesheet,
)
from lib.dialogs import (
    UnstagedChangesDialog,
    ProgressDialog,
    StashNoticeDialog,
)

import shutil

def main():
    # 1. Runtime check for Git CLI
    if not shutil.which("git"):
        raise RuntimeError("Git CLI not found. Please install Git and ensure it is in PATH.")

    parser = argparse.ArgumentParser(description="git-interactive-rebase-gui-tool: A premium PySide6 GUI for interactive git rebasing.")
    parser.add_argument("-C", "--location", type=str, default=os.getcwd())
    parser.add_argument("--viewer-mode", action="store_true", help="Run in read-only viewer mode.")
    parser.add_argument("--update", action="store_true", help="Update the tool to the latest version and exit.")
    parser.add_argument("--version", action="store_true", help="Print the tool's version (short git id) and exit.")
    parser.add_argument("positional", nargs="*", help="Branch, file, tag, or commit ref (auto-detected)")
    args = parser.parse_args()

    if args.version:
        # BUG-1 / BUG-12 fix: anchor to lib package, not the console-script wrapper.
        import lib
        tool_dir = os.path.abspath(os.path.join(os.path.dirname(lib.__file__), ".."))
        short_sha = get_head_sha(tool_dir)
        if short_sha == "Unknown":
            try:
                assets_dir = get_assets_path()
                vpath = os.path.join(assets_dir, "app_version.json")
                if os.path.exists(vpath):
                    with open(vpath, encoding='utf-8') as f:  # BUG-12 fix
                        data = json.load(f)
                        short_sha = data.get("sha", "Unknown")
            except Exception as exc:
                print(f"[tool version] could not read app_version.json: {exc}")
        if not short_sha or short_sha == "Unknown":
            short_sha = "Unknown"
        else:
            short_sha = short_sha[:8]  # BUG-5 fix: always show abbreviated 8-char SHA
        print(f"git-interactive-rebase-gui-tool {short_sha}")
        sys.exit(0)

    if args.update:
        # BUG-1 fix: derive tool_dir from the lib package location, not __file__.
        # When installed via pip, __file__ is the generated console-script wrapper
        # inside /usr/local/bin/ (or equivalent), which is NOT the tool's root.
        # lib.__file__ is always inside site-packages/<lib>, so its parent is the
        # correct installation root regardless of how the tool was invoked.
        import lib
        tool_dir = os.path.abspath(os.path.join(os.path.dirname(lib.__file__), ".."))
        ok, message = perform_self_update(tool_dir)
        print(message)
        sys.exit(0 if ok else 1)

    repo_path = os.path.abspath(os.path.expanduser(args.location))

    # Ignore SIGHUP so the app survives terminal close when launched with &
    import signal
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    now = datetime.now()
    app_start_time = f"{now.strftime('%I.%M%p').lower()} {now.day}-{now.strftime('%b-%Y')}"
    head_sha = get_full_head_sha(repo_path)
    import lib
    tool_dir = os.path.abspath(os.path.join(os.path.dirname(lib.__file__), ".."))
    tool_sha = get_head_sha(tool_dir)
    if tool_sha == "Unknown":
        try:
            assets_dir = get_assets_path()
            vpath = os.path.join(assets_dir, "app_version.json")
            if os.path.exists(vpath):
                with open(vpath, encoding='utf-8') as f:  # BUG-12 fix
                    tool_sha = json.load(f).get("sha", "Unknown")
        except Exception as exc:
            print(f"[tool version] could not read app_version.json: {exc}")
    if not tool_sha:
        tool_sha = "Unknown"
    print(f"App started at {app_start_time} | Tool version: {tool_sha} | HEAD commit: {head_sha}")

    app = QApplication(sys.argv)

    # Global Ctrl+Q handler — closes the active window (any window)
    from PySide6.QtCore import QObject, QEvent
    class CtrlQFilter(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.KeyPress:
                if event.key() == Qt.Key_Q and (event.modifiers() & Qt.ControlModifier):
                    active = app.activeWindow()
                    if active:
                        active.close()
                    return True
            return False
    app.installEventFilter(CtrlQFilter())

    # Set global application icon
    try:
        assets_dir = get_assets_path()
        icon_path = os.path.join(assets_dir, "app_icon.png")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
    except Exception as e:
        print(f"Warning: Could not load application icon: {e}")

    # Check if we are inside a git repository
    import subprocess
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo_path, check=True, capture_output=True, encoding='utf-8', errors='replace')
        root_res = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=repo_path, check=True, capture_output=True, encoding='utf-8', errors='replace')
        if root_res.stdout.strip():
            repo_path = root_res.stdout.strip()
    except FileNotFoundError:
        QMessageBox.critical(None, "Git not found",
            "git is not installed or not in your PATH.\n\n"
            "Install git and try again.")
        sys.exit(1)
    except Exception:
        QMessageBox.critical(None, "Not a Git Repository",
            f"The directory '{repo_path}' is not a valid git repository.\n\n"
            "Please run this tool inside a git repository.")
        sys.exit(1)

    # --- Detect positional arg types ---

    def _is_file(repo_path, arg):
        return os.path.isfile(os.path.join(repo_path, arg))

    def _is_branch(repo_path, arg):
        res = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{arg}"],
            cwd=repo_path, capture_output=True
        )
        return res.returncode == 0

    def _is_tag(repo_path, arg):
        res = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{arg}"],
            cwd=repo_path, capture_output=True
        )
        return res.returncode == 0

    def _is_commit_ref(repo_path, arg):
        res = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", arg],
            cwd=repo_path, capture_output=True
        )
        return res.returncode == 0

    positional = args.positional
    commit_sha = None
    base_branch = None
    detect_base = False
    browse_branch = None
    browse_file = None
    browse_tag_name = None

    if len(positional) == 0:
        # No args: auto-detect base
        print("No args provided. Will detect branch base after window opens.")
        base_sha = get_recent_history_start(repo_path, count=200)
        commit_sha = base_sha
        detect_base = True
    elif len(positional) == 1:
        arg = positional[0]
        if _is_file(repo_path, arg):
            print(f"Arg '{arg}' is a file. Opening file log.")
            browse_file = arg
        elif _is_branch(repo_path, arg):
            print(f"Arg '{arg}' is a branch. Browsing branch.")
            browse_branch = normalize_branch_ref(repo_path, arg)
        elif _is_tag(repo_path, arg):
            print(f"Arg '{arg}' is a tag. Browsing from tag.")
            browse_tag_name = arg
        elif _is_commit_ref(repo_path, arg):
            print(f"Arg '{arg}' is a commit ref. Resolving...")
            res = subprocess.run(["git", "rev-parse", arg], cwd=repo_path, check=True,
                                 capture_output=True, encoding='utf-8', errors='replace')
            commit_sha = res.stdout.strip()
            print(f"Resolved '{arg}' -> {commit_sha}")
        else:
            QMessageBox.critical(None, "Error", f"Cannot understand argument: '{arg}'\n\nNot a file, branch, tag, or commit reference.")
            sys.exit(1)
    elif len(positional) == 2:
        # Two args: <branch-or-tag> <file>
        ref_arg, file_arg = positional
        if _is_file(repo_path, file_arg):
            if _is_branch(repo_path, ref_arg):
                print(f"Browsing branch '{ref_arg}', file '{file_arg}'")
                browse_branch = normalize_branch_ref(repo_path, ref_arg)
                browse_file = file_arg
            elif _is_tag(repo_path, ref_arg):
                print(f"Browsing tag '{ref_arg}', file '{file_arg}'")
                browse_tag_name = ref_arg
                browse_file = file_arg
            else:
                QMessageBox.critical(None, "Error",
                    f"First argument '{ref_arg}' is not a branch or tag.")
                sys.exit(1)
        else:
            QMessageBox.critical(None, "Error",
                f"Second argument '{file_arg}' is not a valid file path.")
            sys.exit(1)
    else:
        QMessageBox.critical(None, "Error", "Too many arguments. Use at most 2: <branch-or-tag> <file>")
        sys.exit(1)

    # Apply global stylesheet before any dialog, so the startup unstaged-changes
    # dialog matches the themed look of the rest of the app.
    theme_name = QSettings("git-interactive-rebase-gui-tool", "settings").value("theme", "light", type=str)
    QApplication.instance().setStyleSheet(get_theme_stylesheet(theme_name))

    # Check for unstaged changes (ignoring submodules as per design)
    created_stash_sha = None
    ack_messages = []  # (kind, title, text) shown after the main window appears
    deferred_selective_commit = False
    unstaged_files = get_unstaged_files(repo_path, ignore_submodules=True)
    if unstaged_files and not args.viewer_mode:
        dialog = UnstagedChangesDialog(len(unstaged_files), repo_path=repo_path, unstaged_files=unstaged_files)
        result = dialog.exec()

        if result == UnstagedChangesDialog.SelectiveCommitResult:
            # Defer until the main window exists so the dialog gets the app's
            # font/theme; runs through the shared handler.
            deferred_selective_commit = True
        elif result == UnstagedChangesDialog.Accepted:
            created_stash_sha, stash_err = stash_changes(repo_path)
            if created_stash_sha is not None and created_stash_sha is not STASH_NOTHING_STASHED:
                print(f"Changes stashed successfully (SHA: {created_stash_sha}).")
                ack_messages.append(("info", "Stash Successful", f"Changes stashed successfully (SHA: {created_stash_sha[:8]})."))
            elif created_stash_sha is STASH_NOTHING_STASHED:
                ack_messages.append(("info", "No Changes Stashed",
                                     "There was nothing to stash (e.g. changes are in untracked files). "
                                     "Please handle them manually."))
            else:
                detail = f"\n\n{stash_err}" if stash_err else ""
                QMessageBox.critical(None, "Error", f"Failed to stash changes. Please stash or commit manually.{detail}")
                sys.exit(1)
        elif result == UnstagedChangesDialog.CommitEachResult:
            # We already have the files list
            progress = ProgressDialog("Committing Changes", f"Committing {len(unstaged_files)} files individually...", None)
            progress.show()
            QApplication.processEvents()

            success_count = 0
            committed_shas = []
            failed_files = []
            for i, f in enumerate(unstaged_files):
                progress.label.setText(f"Committing ({i+1}/{len(unstaged_files)}): {f}")
                QApplication.processEvents()
                ok, err = commit_file(repo_path, f, f"changes in {f}")
                if ok:
                    committed_shas.append(get_head_sha(repo_path)[:8])
                    success_count += 1
                else:
                    print(f"Failed to commit {f}")
                    failed_files.append((f, err))

            progress.close()
            if committed_shas:
                ids = "\n".join(committed_shas)
                ack_messages.append(("info", "Commit Successful",
                                     f"Done. Successfully committed {success_count} file(s) individually.\n\nCommit IDs:\n{ids}"))
            if failed_files:
                fail_lines = "\n".join(f"  {name}: {err}".rstrip() for name, err in failed_files)
                ack_messages.append(("critical", "Some Commits Failed",
                                     f"Failed to commit {len(failed_files)} of {len(unstaged_files)} file(s):\n\n{fail_lines}"))
            print(f"Successfully committed {success_count} files.")
        elif result == UnstagedChangesDialog.BulkCommitResult:
            msg = f"bulk commit (Number of modified files: {len(unstaged_files)})"

            ok, detail = bulk_commit_all(repo_path, msg)
            if ok:
                print("Bulk commit successful.")
                ack_messages.append(("info", "Bulk Commit Successful",
                                     f"Done. Bulk commit successful.\n\nCommit ID:\n{get_head_sha(repo_path)[:8]}"))
            else:
                print("Bulk commit failed.")
                ack_messages.append(("critical", "Error", f"Bulk commit failed.\n\n{detail}"))

        elif result == UnstagedChangesDialog.AmendResult:
            old_head = get_head_sha(repo_path)
            ok, detail = amend_with_head(repo_path)
            if ok:
                new_head = get_head_sha(repo_path)
                print("Amend successful.")
                ack_messages.append(("info", "Amend Successful",
                                     f"Done. Changes amended into HEAD commit.\n\nOLD COMMIT: {old_head[:8]}\nNEW COMMIT: {new_head[:8]}"))
            else:
                print("Amend failed.")
                ack_messages.append(("critical", "Error", f"Amend failed.\n\n{detail}"))

        elif result == UnstagedChangesDialog.DiscardResult:
            ok, detail = discard_changes(repo_path)
            if ok:
                print("Unstaged changes discarded.")
                ack_messages.append(("info", "Discard Successful", "Done. Unstaged changes discarded (git checkout .)."))
            else:
                print("Discard failed.")
                ack_messages.append(("critical", "Error", f"Discard failed.\n\n{detail}"))

        elif result == UnstagedChangesDialog.ViewerModeResult:
            args.viewer_mode = True
        else:
            print("Exiting as requested by the user.")
            sys.exit(0)

    # Warn about staged changes (informational only)
    has_staged, _ = classify_tracked_changes(repo_path)
    if has_staged:
        ack_messages.append(("info", "Staged Changes",
                             "You have staged changes in the repository.\n\n"
                             "Use Repo → Handle Staged Changes to commit, unstage, or discard them."))

    window = GitInteractiveRebaseApp(
        repo_path, commit_sha, app_start_time,
        base_branch=base_branch,
        viewer_mode=args.viewer_mode or bool(browse_branch or browse_file or browse_tag_name),
        browse_branch=browse_branch or browse_tag_name,
        browse_file=browse_file,
        browse_file_ref=(browse_tag_name or browse_branch) if browse_file else None,
        browse_tag=bool(browse_tag_name),
        cli_mode=bool(browse_branch or browse_tag_name),
        auto_detect_base=detect_base,
    )
    window.show()
    if created_stash_sha:
        window.app_managed_stash_sha = created_stash_sha
        window._update_stash_btn_visibility()
        window._flash_pop_stash_btn()

    # Highlight repo button when staged changes exist
    if has_staged:
        from lib.app_window.helpers import highlight_button_temporarily
        QTimer.singleShot(500, lambda: highlight_button_temporarily(window.repo_btn, blinks=5))

    # Deferred 'Commit Selectively' chosen at startup - run once the window is up.
    if deferred_selective_commit:
        QTimer.singleShot(0, window._commit_selectively_from_dialog)

    # Show any acknowledgment/error boxes only after the main window is up.
    if ack_messages:
        def _show_deferred_acks():
            for kind, title, text in ack_messages:
                if kind == "critical":
                    QMessageBox.critical(None, title, text)
                else:
                    QMessageBox.information(None, title, text)
        QTimer.singleShot(0, _show_deferred_acks)

    exit_code = app.exec()

    stash_sha = getattr(window, "app_managed_stash_sha", None)
    if stash_sha:
        status, _ = get_stash_status(repo_path, stash_sha)
        short_sha = stash_sha[:8]

        def show_missing_box(not_at_head):
            if not_at_head:
                text = (f"The stash created by app ({short_sha}) is found in stash list, but not at HEAD position. "
                        f"Please investigate and stash pop manually.\n\n"
                        f"Please note down the sha: {short_sha}")
            else:
                text = (f"The stash created during app start is missing. "
                        f"{short_sha} not found in stash list. "
                        f"Please investigate and stash pop manually.\n\n"
                        f"Please note down the sha: {short_sha}")
            StashNoticeDialog(text, stash_sha).exec()

        if status == "ERROR":
            QMessageBox.critical(
                None, "Error",
                f"Could not verify the status of the app-created stash ({short_sha}). "
                f"Please investigate and stash pop manually.\n\n"
                f"Please note down the sha: {short_sha}"
            )
        elif status == "NOT_FOUND":
            show_missing_box(not_at_head=False)
        elif status == "NOT_HEAD":
            show_missing_box(not_at_head=True)
        else:
            # Final reminder before exiting the process completely
            msg_box = QMessageBox(None)
            msg_box.setWindowTitle("Stash Reminder")
            msg_box.setText("A stash was created during this session. Do you want to stash pop it ??")
            yes_button = msg_box.addButton("Yes, stash pop now.", QMessageBox.YesRole)
            no_button = msg_box.addButton("No, i will do manually.", QMessageBox.NoRole)
            msg_box.exec()

            if msg_box.clickedButton() == yes_button:
                can_apply, conflict_detail = stash_pop_can_apply(repo_path, stash_sha)
                if not can_apply:
                    QMessageBox.warning(
                        None,
                        "Cannot Pop Stash",
                        f"Popping this stash would create a merge conflict (HEAD has moved since it was created), "
                        f"so it was not applied.\n\n"
                        f"{conflict_detail}\n\nThe stash (SHA: {short_sha}) was left untouched."
                    )
                else:
                    success, msg = stash_pop(repo_path, stash_sha)
                    if success:
                        print(f"Stash {stash_sha[:8]}({msg}) popped successfully.")
                        QMessageBox.information(None, "Success", f"Stash {stash_sha[:8]}({msg}) popped successfully.")
                    else:
                        detail = f"\n\n{msg}" if msg else ""
                        QMessageBox.critical(None, "Error", "Failed to pop stash. You may need to do it manually." + detail)

    sys.exit(exit_code)

if __name__ == "__main__":
    import platform
    # Auto-background: detach from terminal so it returns immediately.
    # Skip for --update/--version (need terminal output) and when already backgrounded.
    if platform.system() != "Windows" and "--update" not in sys.argv and "--version" not in sys.argv:
        if sys.stdout and sys.stdout.isatty():
            pid = os.fork()
            if pid > 0:
                # Parent exits immediately — terminal is free.
                print(f"Tool started in background (PID {pid})")
                sys.exit(0)
            # Child continues: new session, close stdin
            os.setsid()
            try:
                sys.stdin = open(os.devnull, "r")
            except Exception:
                pass
    main()
