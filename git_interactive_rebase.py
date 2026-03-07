#!/usr/bin/env python3
"""
Project: Git Interactive Rebase Helper
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

from lib.git_helpers import get_root_commit, has_uncommitted_changes, stash_changes
from lib.app_window import GitInteractiveRebaseApp
from lib.dialogs import UnstagedChangesDialog

def main():
    parser = argparse.ArgumentParser(description="Git Interactive Rebase Helper.")
    parser.add_argument("-C", "--location", type=str, default=os.getcwd())
    parser.add_argument("commit_sha", type=str, nargs="?", help="Starting commit SHA (optional, defaults to root)")
    args = parser.parse_args()

    repo_path = os.path.abspath(os.path.expanduser(args.location))
    
    commit_sha = args.commit_sha
    if not commit_sha:
        try:
            commit_sha = get_root_commit(repo_path)
            print(f"No SHA provided. Starting from root commit: {commit_sha}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    
    app = QApplication(sys.argv)
    
    # Set global application icon
    icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "app_icon.png"))
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
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
