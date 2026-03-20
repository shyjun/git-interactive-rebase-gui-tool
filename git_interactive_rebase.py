#!/usr/bin/env python3
"""
Project: git-interactive-rebase-gui-tool
Description: A premium PySide6 GUI for interactive git rebasing, squashing, and rephrasing.
Author: n.shyju@gmail.com
Version: 1.0.0
Date: Feb 2026
"""
import argparse
import sys
import os

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QIcon
import tempfile
import stat

from lib.utils import get_assets_path
from lib.git_helpers import get_root_commit, has_uncommitted_changes, stash_changes
from lib.app_window import GitInteractiveRebaseApp
from lib.dialogs import UnstagedChangesDialog

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
            commit_sha = get_root_commit(repo_path)
            print(f"No SHA provided. Starting from root commit: {commit_sha}")
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Could not find root commit: {e}")
            sys.exit(1)
    
    # Check for unstaged changes
    stashed = False
    if has_uncommitted_changes(repo_path):
        dialog = UnstagedChangesDialog()
        if dialog.exec() == UnstagedChangesDialog.Accepted:
            if stash_changes(repo_path):
                print("Changes stashed successfully.")
                stashed = True
            else:
                QMessageBox.critical(None, "Error", "Failed to stash changes. Please stash or commit manually.")
                sys.exit(1)
        else:
            print("Exiting as requested by the user.")
            sys.exit(0)

    window = GitInteractiveRebaseApp(repo_path, commit_sha)
    window.show()
    
    exit_code = app.exec()
    
    if stashed:
        # Final reminder before exiting the process completely
        QMessageBox.information(None, "Stash Reminder", 
            "A stash was created for your unstaged changes when the app started.\n\n"
            "Don't forget to 'git stash pop' if you need those changes back.")

    sys.exit(exit_code)

if __name__ == "__main__":
    main()
