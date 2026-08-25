if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

import os

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QFileDialog,
    QTextEdit,
    QMessageBox,
    QApplication,
    QListWidget,
    QListWidgetItem,
    QSplitter,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from lib.git_helpers import get_branch_names, get_current_branch
from lib.utils import get_theme_colors


class StashNoticeDialog(QDialog):
    """Warning dialog for a missing/not-at-head managed stash. Offers a 'Copy SHA to
    clipboard' button that does NOT close the dialog, and an OK button to dismiss."""
    ManualPopResult = 2

    def __init__(self, text, sha, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Managed Stash")
        self.setMinimumWidth(480)
        self.setModal(True)

        short_sha = sha[:8]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)

        copy_btn = QPushButton("Copy SHA to clipboard")
        copy_btn.setToolTip("Copy the stash SHA to the clipboard.")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(short_sha))

        manual_btn = QPushButton("Its OK, I stash pop-ed it myself manually")
        manual_btn.setToolTip("Mark this stash as manually handled and stop tracking it.")
        manual_btn.clicked.connect(lambda: self.done(self.ManualPopResult))

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(manual_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)


class BrowseBranchDialog(QDialog):
    """Dialog to pick a branch name and how many recent commits to show in the
    read-only branch browser. Returns branch name and an integer commit count."""

    def __init__(self, repo_path, parent=None, default_limit=50):
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle("Browse Branch")
        self.setMinimumWidth(380)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        branch_label = QLabel("Branch name:")
        layout.addWidget(branch_label)

        self.branch_combo = QComboBox()
        self.branch_combo.setEditable(True)
        self.branch_combo.addItem("")
        self.branch_combo.addItems(get_branch_names(self.repo_path))
        if self.branch_combo.lineEdit():
            self.branch_combo.lineEdit().setPlaceholderText("e.g. feature/login, dev, release/1.0")
        self.branch_combo.setToolTip("Existing branches are listed; you can also type a branch that hasn't been fetched yet.")
        layout.addWidget(self.branch_combo)

        limit_label = QLabel("Number of commits to show:")
        layout.addWidget(limit_label)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 1000000)
        self.limit_spin.setValue(default_limit)
        self.limit_spin.setToolTip("How many most-recent commits to load into the browse window.")
        layout.addWidget(self.limit_spin)

        open_btn = QPushButton("Open Browser")
        open_btn.setDefault(True)
        open_btn.setToolTip("Open a read-only viewer of this branch's history.")
        open_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(open_btn)
        layout.addLayout(btn_layout)

        self.branch_combo.setFocus()

    @property
    def branch_name(self):
        return self.branch_combo.currentText().strip()

    @property
    def commit_limit(self):
        return self.limit_spin.value()


class BrowseCommitLogDialog(QDialog):
    """Dialog to pick a commit and how many recent commits to show in the
    read-only commit-log browser. Returns a commit SHA and an integer commit count."""

    def __init__(self, repo_path, parent=None, default_limit=50):
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle("Browse Log of a Commit")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        commit_label = QLabel("Commit SHA or ref:")
        layout.addWidget(commit_label)

        self.commit_edit = QLineEdit()
        self.commit_edit.setPlaceholderText("e.g. c9bbbc4, HEAD, master")
        self.commit_edit.setToolTip("A commit SHA, short SHA, or a ref that resolves to a commit.")
        layout.addWidget(self.commit_edit)

        limit_label = QLabel("Number of commits to show:")
        layout.addWidget(limit_label)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 1000000)
        self.limit_spin.setValue(default_limit)
        self.limit_spin.setToolTip("How many most-recent commits to load into the browse window.")
        layout.addWidget(self.limit_spin)

        open_btn = QPushButton("Open Browser")
        open_btn.setDefault(True)
        open_btn.setToolTip("Open a read-only viewer of this commit's history.")
        open_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(open_btn)
        layout.addLayout(btn_layout)

        self.commit_edit.setFocus()

    @property
    def commit_id(self):
        return self.commit_edit.text().strip()

    @property
    def commit_limit(self):
        return self.limit_spin.value()


class BrowseFileLogDialog(QDialog):
    """Dialog to pick a file and how many recent commits to show in the
    read-only file-log browser. Returns a repo-relative file path and an
    integer commit count."""

    def __init__(self, repo_path, parent=None, default_limit=50):
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle("Browse File Log")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        file_label = QLabel("File path (repo-relative):")
        layout.addWidget(file_label)

        file_row = QHBoxLayout()
        file_row.setSpacing(6)
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("e.g. lib/app_window.py, README.md")
        self.file_edit.setToolTip("A path relative to the repository root; use Browse... to pick a file.")
        file_row.addWidget(self.file_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Pick a file in the repository.")
        browse_btn.clicked.connect(self._pick_file)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        limit_label = QLabel("Number of commits to show:")
        layout.addWidget(limit_label)

        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 1000000)
        self.limit_spin.setValue(default_limit)
        self.limit_spin.setToolTip("How many most-recent commits touching the file to load.")
        layout.addWidget(self.limit_spin)

        open_btn = QPushButton("Open Browser")
        open_btn.setDefault(True)
        open_btn.setToolTip("Open a read-only viewer of this file's history.")
        open_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(open_btn)
        layout.addLayout(btn_layout)

        self.file_edit.setFocus()

    def _pick_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select file to browse", self.repo_path)
        if file_path:
            rel = os.path.relpath(file_path, self.repo_path)
            if rel.startswith(".."):
                QMessageBox.warning(self, "Outside repository",
                                    "Please select a file inside the repository.")
                return
            self.file_edit.setText(rel.replace(os.sep, "/"))

    @property
    def file_path(self):
        return self.file_edit.text().strip()

    @property
    def commit_limit(self):
        return self.limit_spin.value()


class ApplyPatchDialog(QDialog):
    """Dialog to pick a patch file and choose whether to commit the changes or
    leave them unstaged in the working tree."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apply Patch")
        self.setMinimumWidth(440)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        patch_label = QLabel("Patch file:")
        layout.addWidget(patch_label)

        patch_row = QHBoxLayout()
        patch_row.setSpacing(6)
        self.patch_edit = QLineEdit()
        self.patch_edit.setPlaceholderText("e.g. /path/to/change.patch")
        self.patch_edit.setToolTip("A unified-diff or format-patch file to apply.")
        patch_row.addWidget(self.patch_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Pick a patch file.")
        browse_btn.clicked.connect(self._pick_patch_file)
        patch_row.addWidget(browse_btn)
        layout.addLayout(patch_row)

        self.commit_cb = QCheckBox("Create a commit from the patch")
        self.commit_cb.setChecked(False)
        self.commit_cb.setToolTip("If checked, the changes are staged and committed using the patch's own message. "
                                  "If unchecked, the changes are left unstaged in the working tree.")
        layout.addWidget(self.commit_cb)

        apply_btn = QPushButton("Apply Patch")
        apply_btn.setDefault(True)
        apply_btn.setToolTip("Apply the selected patch to the repository.")
        apply_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(apply_btn)
        layout.addLayout(btn_layout)

        self.patch_edit.setFocus()

    def _pick_patch_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select patch file",
                                                   filter="Patch files (*.patch *.diff);;All files (*)")
        if file_path:
            self.patch_edit.setText(file_path)

    @property
    def patch_path(self):
        return self.patch_edit.text().strip()

    @property
    def commit_wanted(self):
        return self.commit_cb.isChecked()


class TagCommitDialog(QDialog):
    """Dialog to create a git tag (lightweight or annotated) on a commit."""

    def __init__(self, sha, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tag Commit")
        self.setMinimumWidth(440)
        self.setMinimumHeight(260)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        sha_label = QLabel(f"Tagging commit: {sha[:12]}")
        sha_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(sha_label)

        tag_label = QLabel("Tag name:")
        layout.addWidget(tag_label)

        self.tag_edit = QLineEdit()
        self.tag_edit.setPlaceholderText("e.g. v1.2.3")
        self.tag_edit.setToolTip("Name for the git tag (e.g. v1.0.0, release-20240101).")
        layout.addWidget(self.tag_edit)

        self.annotate_cb = QCheckBox("Annotate")
        self.annotate_cb.setChecked(False)
        self.annotate_cb.setToolTip("If checked, creates an annotated tag with a message.")
        self.annotate_cb.toggled.connect(self._on_annotate_toggled)
        layout.addWidget(self.annotate_cb)

        self.msg_edit = QTextEdit()
        self.msg_edit.setPlaceholderText("Annotation message (optional)")
        self.msg_edit.setToolTip("Message for an annotated tag. Ignored if 'Annotate' is unchecked.")
        self.msg_edit.setEnabled(False)
        self.msg_edit.setMinimumHeight(80)
        layout.addWidget(self.msg_edit)

        tag_btn = QPushButton("Create Tag")
        tag_btn.setDefault(True)
        tag_btn.setToolTip("Create the git tag.")
        tag_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(tag_btn)
        layout.addLayout(btn_layout)

        self.tag_edit.setFocus()

    def _on_annotate_toggled(self, checked):
        self.msg_edit.setEnabled(checked)
        if checked:
            self.msg_edit.setFocus()

    @property
    def tag_name(self):
        return self.tag_edit.text().strip()

    @property
    def annotated(self):
        return self.annotate_cb.isChecked()

    @property
    def message(self):
        return self.msg_edit.toPlainText().strip()


class MergeBaseDialog(QDialog):
    """Dialog to pick the branch to compare against the current branch's merge-base.
    Shows the current branch first, then a "VS" label, then a branch pulldown."""

    def __init__(self, repo_path, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle("Find Merge-base")
        self.setMinimumWidth(380)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        cur_label = QLabel("Current branch:")
        layout.addWidget(cur_label)

        current = get_current_branch(repo_path) or "HEAD (detached)"
        self.current_branch_label = QLabel(current)
        cur_font = self.current_branch_label.font()
        cur_font.setBold(True)
        self.current_branch_label.setFont(cur_font)
        layout.addWidget(self.current_branch_label)

        vs_label = QLabel("VS")
        vs_label.setStyleSheet("font-size: 13px; color: gray;")
        layout.addWidget(vs_label)

        other_label = QLabel("Compare with branch:")
        layout.addWidget(other_label)

        self.branch_combo = QComboBox()
        self.branch_combo.setEditable(True)
        self.branch_combo.addItem("")
        self.branch_combo.addItems(get_branch_names(repo_path))
        if self.branch_combo.lineEdit():
            self.branch_combo.lineEdit().setPlaceholderText("e.g. origin/main, master")
        self.branch_combo.setToolTip("Pick the branch to find the merge-base against.")
        layout.addWidget(self.branch_combo)

        find_btn = QPushButton("Find")
        find_btn.setDefault(True)
        find_btn.setToolTip("Find the merge-base of the current branch and the selected branch.")
        find_btn.clicked.connect(self.accept)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(find_btn)
        layout.addLayout(btn_layout)

        self.branch_combo.setFocus()

    @property
    def branch_name(self):
        return self.branch_combo.currentText().strip()


class MergeBaseResultDialog(QDialog):
    """Shows the computed merge-base SHA with a copy-to-clipboard button and an
    OK button (styled like StashNoticeDialog)."""

    def __init__(self, text, sha, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Merge-base Found")
        self.setMinimumWidth(480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(label)

        copy_btn = QPushButton("Copy SHA to clipboard")
        copy_btn.setToolTip("Copy the full merge-base SHA to the clipboard.")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(sha))

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(copy_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)


class OpenFileAtRefDialog(QDialog):
    """Dialog to open a file at a specific commit/branch/tag.
    User enters a SHA/branch/HEAD, browses the file list, and opens the
    selected file with the system default application."""

    def __init__(self, repo_path, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.selected_file = None
        self.resolved_sha = None
        self.setWindowTitle("Open File at Commit")
        self.setMinimumSize(600, 500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # SHA / branch input
        ref_layout = QHBoxLayout()
        ref_label = QLabel("Commit / Branch / Tag:")
        ref_layout.addWidget(ref_label)

        self.ref_combo = QComboBox()
        self.ref_combo.setEditable(True)
        self.ref_combo.addItem("HEAD")
        self.ref_combo.addItems(get_branch_names(self.repo_path))
        if self.ref_combo.lineEdit():
            self.ref_combo.lineEdit().setPlaceholderText("e.g. HEAD, main, abc1234, v1.0")
        ref_layout.addWidget(self.ref_combo)
        layout.addLayout(ref_layout)

        # Browse button
        browse_btn = QPushButton("Browse Files")
        browse_btn.setToolTip("List all files at the specified commit/branch/tag.")
        browse_btn.clicked.connect(self._load_files)
        layout.addWidget(browse_btn)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        # Search bar
        search_layout = QHBoxLayout()
        search_label = QLabel("Filter:")
        search_layout.addWidget(search_label)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to filter files...")
        self.search_edit.textChanged.connect(self._filter_files)
        search_layout.addWidget(self.search_edit)
        layout.addLayout(search_layout)

        # File list
        self.file_list = QListWidget()
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.itemDoubleClicked.connect(self._on_open)
        layout.addWidget(self.file_list)

        # Buttons
        open_btn = QPushButton("Open with Default App")
        open_btn.setDefault(True)
        open_btn.setEnabled(False)
        open_btn.clicked.connect(self._on_open)
        self.open_btn = open_btn

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(open_btn)
        layout.addLayout(btn_layout)

        self.ref_combo.setFocus()

    def _load_files(self):
        """List all files at the given ref using git ls-tree."""
        ref = self.ref_combo.currentText().strip()
        if not ref:
            QMessageBox.warning(self, "No ref", "Please enter a commit, branch, or tag.")
            return

        self.status_label.setText(f"Loading files at '{ref}'...")
        self.file_list.clear()
        QApplication.processEvents()

        try:
            import subprocess
            # Resolve the ref to a full SHA
            result = subprocess.run(
                ["git", "rev-parse", ref],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding='utf-8', errors='replace'
            )
            if result.returncode != 0:
                QMessageBox.critical(self, "Invalid Ref",
                                     f"'{ref}' does not resolve to a valid commit.\n\n{result.stderr}")
                self.status_label.setText("")
                return
            self.resolved_sha = result.stdout.strip()

            # List all files at that commit
            result = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", ref],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding='utf-8', errors='replace'
            )
            if result.returncode != 0:
                QMessageBox.critical(self, "Error",
                                     f"Could not list files.\n\n{result.stderr}")
                self.status_label.setText("")
                return

            files = [f for f in result.stdout.strip().split('\n') if f.strip()]
            self._all_files = files
            for f in files:
                self.file_list.addItem(f)

            self.status_label.setText(f"{len(files)} files at '{ref}' ({self.resolved_sha[:8]})")
            self.open_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load files: {e}")
            self.status_label.setText("")

    def _filter_files(self, text):
        """Filter the file list by the search text."""
        if not hasattr(self, '_all_files'):
            return
        self.file_list.clear()
        term = text.lower()
        for f in self._all_files:
            if term in f.lower():
                self.file_list.addItem(f)

    def _on_open(self, *_):
        """Open the selected file from the resolved commit."""
        item = self.file_list.currentItem()
        if not item:
            QMessageBox.information(self, "No file selected", "Please select a file to open.")
            return
        self.selected_file = item.text()
        self.accept()
