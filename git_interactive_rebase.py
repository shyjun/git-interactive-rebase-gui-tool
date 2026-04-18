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
import sys
import os
from datetime import datetime

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon
import tempfile
import stat

from lib.utils import get_assets_path
from lib.git_helpers import (
    get_root_commit, get_recent_history_start, get_branch_base_info,
    has_uncommitted_changes, stash_changes, get_unstaged_files, commit_file,
    bulk_commit_all, stash_pop, get_full_head_sha
)
from lib.app_window import GitInteractiveRebaseApp
from lib.dialogs import UnstagedChangesDialog, ProgressDialog

import shutil

def main():
    # 1. Runtime check for Git CLI
    if not shutil.which("git"):
        raise RuntimeError("Git CLI not found. Please install Git and ensure it is in PATH.")

    parser = argparse.ArgumentParser(description="git-interactive-rebase-gui-tool: A premium PySide6 GUI for interactive git rebasing.")
    parser.add_argument("-C", "--location", type=str, default=os.getcwd())
    parser.add_argument("commit_sha", type=str, nargs="?", help="Starting commit SHA (optional, defaults to root)")
    args = parser.parse_args()

    repo_path = os.path.abspath(os.path.expanduser(args.location))

    now = datetime.now()
    app_start_time = f"{now.strftime('%I.%M%p').lower()} {now.day}-{now.strftime('%b-%Y')}"
    head_sha = get_full_head_sha(repo_path)
    print(f"App started at {app_start_time} | HEAD commit: {head_sha}")

    app = QApplication(sys.argv)

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
    except Exception:
        QMessageBox.critical(None, "Not a Git Repository",
            f"The directory '{repo_path}' is not a valid git repository.\n\n"
            "Please run this tool inside a git repository.")
        sys.exit(1)

    commit_sha = args.commit_sha
    if not commit_sha:
        try:
            print("No commit SHA provided. Detecting branch base...")
            base_sha, base_branch = get_branch_base_info(repo_path)
            if base_sha:
                commit_sha = base_sha
                print(f"Detected branch base: {commit_sha} (looks like it branched out from '{base_branch}', showing commits since that point)")
            else:
                print("Could not detect branch base. Falling back to recent history limit (HEAD~200)...")
                commit_sha = get_recent_history_start(repo_path, count=200)
                print(f"Defaulting to recent history: {commit_sha}")
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Could not find start commit: {e}")
            sys.exit(1)
    else:
        print(f"Commit SHA provided: {commit_sha} (showing commits from this point)")

    # Check for unstaged changes (ignoring submodules as per design)
    created_stash_sha = None
    unstaged_files = get_unstaged_files(repo_path, ignore_submodules=True)
    if unstaged_files:
        dialog = UnstagedChangesDialog(len(unstaged_files))
        result = dialog.exec()

        if result == UnstagedChangesDialog.Accepted:
            created_stash_sha = stash_changes(repo_path)
            if created_stash_sha:
                print(f"Changes stashed successfully (SHA: {created_stash_sha}).")
            else:
                QMessageBox.critical(None, "Error", "Failed to stash changes. Please stash or commit manually.")
                sys.exit(1)
        elif result == UnstagedChangesDialog.CommitEachResult:
            # We already have the files list
            progress = ProgressDialog("Committing Changes", f"Committing {len(unstaged_files)} files individually...", None)
            progress.show()
            QApplication.processEvents()

            success_count = 0
            for i, f in enumerate(unstaged_files):
                progress.label.setText(f"Committing ({i+1}/{len(unstaged_files)}): {f}")
                QApplication.processEvents()
                if commit_file(repo_path, f, f"changes in {f}"):
                    success_count += 1
                else:
                    print(f"Failed to commit {f}")

            progress.close()
            print(f"Successfully committed {success_count} files.")
        elif result == UnstagedChangesDialog.BulkCommitResult:
            msg = f"bulk commit (Number of modified files: {len(unstaged_files)})"
            progress = ProgressDialog("Bulk Committing", f"Committing {len(unstaged_files)} files at once...", None)
            progress.show()
            QApplication.processEvents()

            if bulk_commit_all(repo_path, msg):
                print("Bulk commit successful.")
            else:
                print("Bulk commit failed.")

            progress.close()
        else:
            print("Exiting as requested by the user.")
            sys.exit(0)

    window = GitInteractiveRebaseApp(repo_path, commit_sha, app_start_time)
    window.show()

    exit_code = app.exec()

    if created_stash_sha:
        # Final reminder before exiting the process completely
        msg_box = QMessageBox(None)
        msg_box.setWindowTitle("Stash Reminder")
        msg_box.setText("A stash was created during app startup. Do you want to stash pop it ??")
        yes_button = msg_box.addButton("Yes, stash pop now.", QMessageBox.YesRole)
        no_button = msg_box.addButton("No, i will do manually.", QMessageBox.NoRole)
        msg_box.exec()

        if msg_box.clickedButton() == yes_button:
            success, msg = stash_pop(repo_path, created_stash_sha)
            if success:
                short_sha = created_stash_sha[:7]
                print(f"Stash {short_sha}({msg}) popped successfully.")
                QMessageBox.information(None, "Success", f"Stash {short_sha}({msg}) popped successfully.")
            else:
                QMessageBox.critical(None, "Error", "Failed to pop stash. You may need to do it manually.")

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
