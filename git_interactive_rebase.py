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

from PySide6.QtWidgets import QApplication

from lib.git_helpers import get_root_commit
from lib.app_window import GitHistoryApp

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
    window = GitHistoryApp(repo_path, commit_sha)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
