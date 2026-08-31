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
    QGroupBox,
    QRadioButton,
    QButtonGroup,
)
from PySide6.QtCore import Qt

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
    User enters a SHA/branch/HEAD, types or browses for a file, and opens
    it with the system default application."""

    def __init__(self, repo_path, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.selected_file = None
        self.resolved_sha = None
        self.setWindowTitle("Open File at Commit")
        self.setMinimumWidth(550)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # SHA / branch / tag input
        ref_label = QLabel("Commit / Branch / Tag:")
        layout.addWidget(ref_label)

        self.ref_combo = QComboBox()
        self.ref_combo.setEditable(True)
        self.ref_combo.addItem("HEAD")
        self.ref_combo.addItems(get_branch_names(self.repo_path))
        if self.ref_combo.lineEdit():
            self.ref_combo.lineEdit().setPlaceholderText("e.g. HEAD, main, abc1234, v1.0")
        layout.addWidget(self.ref_combo)

        # File input
        file_label = QLabel("File:")
        layout.addWidget(file_label)

        file_layout = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("e.g. src/main.c, README.md")
        file_layout.addWidget(self.file_edit)

        browse_btn = QPushButton("Browse…")
        browse_btn.setToolTip("List files at the selected commit and pick one.")
        browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(browse_btn)
        layout.addLayout(file_layout)

        # Buttons
        open_btn = QPushButton("Open with Default App")
        open_btn.setDefault(True)
        open_btn.clicked.connect(self._on_open)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(open_btn)
        layout.addLayout(btn_layout)

        self.ref_combo.setFocus()

    def _browse_file(self):
        """Show a file picker populated with files at the given ref."""
        ref = self.ref_combo.currentText().strip()
        if not ref:
            QMessageBox.warning(self, "No ref", "Please enter a commit, branch, or tag first.")
            return

        try:
            import subprocess
            result = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", ref],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding='utf-8', errors='replace'
            )
            if result.returncode != 0:
                QMessageBox.critical(self, "Invalid Ref",
                                     f"'{ref}' does not resolve to a valid commit.\n\n{result.stderr}")
                return
            files = [f for f in result.stdout.strip().split('\n') if f.strip()]
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not list files: {e}")
            return

        # Simple selection dialog
        from PySide6.QtWidgets import QDialog, QListWidget, QDialogButtonBox
        pick = QDialog(self)
        pick.setWindowTitle(f"Select file at {ref}")
        pick.setMinimumSize(500, 400)
        pick_layout = QVBoxLayout(pick)

        search = QLineEdit()
        search.setPlaceholderText("Type to filter…")
        pick_layout.addWidget(search)

        lst = QListWidget()
        for f in files:
            lst.addItem(f)
        pick_layout.addWidget(lst)

        def filter_list(text):
            lst.clear()
            term = text.lower()
            for f in files:
                if term in f.lower():
                    lst.addItem(f)
        search.textChanged.connect(filter_list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(pick.accept)
        buttons.rejected.connect(pick.reject)
        pick_layout.addWidget(buttons)

        if pick.exec() == QDialog.Accepted and lst.currentItem():
            self.file_edit.setText(lst.currentItem().text())

    def _on_open(self):
        """Resolve the ref and accept with the file path."""
        filepath = self.file_edit.text().strip()
        if not filepath:
            QMessageBox.information(self, "No file", "Please enter or browse for a file.")
            return

        ref = self.ref_combo.currentText().strip()
        if not ref:
            QMessageBox.warning(self, "No ref", "Please enter a commit, branch, or tag.")
            return

        # Resolve ref to SHA
        try:
            import subprocess
            result = subprocess.run(
                ["git", "rev-parse", ref],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding='utf-8', errors='replace'
            )
            if result.returncode != 0:
                QMessageBox.critical(self, "Invalid Ref",
                                     f"'{ref}' does not resolve.\n\n{result.stderr}")
                return
            self.resolved_sha = result.stdout.strip()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not resolve ref: {e}")
            return

        self.selected_file = filepath
        self.accept()


class DiffFileAtRefDialog(QDialog):
    """Dialog to diff a file against a different version.

    Two group boxes:
    - Source file: read-only path, radio buttons for HEAD vs selected-commit version.
    - Destination file: ref combo + editable file path.

    Two Run buttons:
    - Run Git Difftool: always enabled (uses temp files + git difftool).
    - External Difftool: enabled only when source == HEAD or file unchanged,
      and a custom difftool command is configured via External Tools Integration.
    """

    def __init__(self, repo_path, filepath, selected_sha, head_sha, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.filepath = filepath
        self.selected_sha = selected_sha
        self.head_sha = head_sha
        self.resolved_sha = None
        self.selected_file = None
        self.use_direct = False

        self.setWindowTitle("Diff File against Different Version")
        self.setMinimumWidth(600)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # --- Source file group ---
        src_group = QGroupBox("Source file")
        src_layout = QVBoxLayout(src_group)

        self.src_path_label = QLabel(filepath)
        self.src_path_label.setStyleSheet("font-weight: bold;")
        src_layout.addWidget(self.src_path_label)

        self.src_radio_group = QButtonGroup(self)
        self.src_selected_radio = QRadioButton(f"Version at selected commit ({selected_sha[:8]})")
        self.src_head_radio = QRadioButton(f"HEAD version ({head_sha[:8]})")
        self.src_selected_radio.setChecked(True)
        self.src_radio_group.addButton(self.src_selected_radio, 0)
        self.src_radio_group.addButton(self.src_head_radio, 1)
        self.src_selected_radio.toggled.connect(lambda: self._update_direct_enabled())
        src_layout.addWidget(self.src_selected_radio)
        if selected_sha != head_sha:
            src_layout.addWidget(self.src_head_radio)
        layout.addWidget(src_group)

        # --- Destination file group ---
        dst_group = QGroupBox("Destination file")
        dst_layout = QVBoxLayout(dst_group)

        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("Commit / Branch / Tag / SHA:"))
        self.ref_combo = QComboBox()
        self.ref_combo.setEditable(True)
        self.ref_combo.addItems(get_branch_names(self.repo_path))
        try:
            import subprocess
            result = subprocess.run(
                ["git", "tag", "-l"], cwd=self.repo_path,
                capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode == 0:
                tags = [t.strip() for t in result.stdout.strip().split('\n') if t.strip()]
                if tags:
                    self.ref_combo.insertSeparator(self.ref_combo.count())
                    self.ref_combo.addItems(tags)
        except Exception:
            pass
        if self.ref_combo.lineEdit():
            self.ref_combo.lineEdit().setPlaceholderText("e.g. HEAD, main, abc1234, v1.0")
        ref_row.addWidget(self.ref_combo, 1)
        dst_layout.addLayout(ref_row)

        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("File path:"))
        self.file_edit = QLineEdit(filepath)
        self.file_edit.setPlaceholderText("Path to the file (e.g. src/main.py)")
        file_row.addWidget(self.file_edit, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse)
        file_row.addWidget(browse_btn)
        dst_layout.addLayout(file_row)

        layout.addWidget(dst_group)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.direct_btn = QPushButton("External Difftool")
        self.direct_btn.setToolTip(self._direct_tooltip())
        self.direct_btn.clicked.connect(self._on_direct)
        btn_layout.addWidget(self.direct_btn)

        self.difftool_btn = QPushButton("Run Git Difftool")
        self.difftool_btn.setDefault(True)
        self.difftool_btn.setToolTip(
            "Extract the selected file versions temporarily and open them "
            "using git difftool.")
        self.difftool_btn.clicked.connect(self._on_difftool)
        btn_layout.addWidget(self.difftool_btn)
        layout.addLayout(btn_layout)

        self._update_direct_enabled()
        self.ref_combo.setFocus()

    def _direct_tooltip(self):
        if self.direct_btn.isChecked() if hasattr(self.direct_btn, 'isChecked') else False:
            return ""
        return (
            "Direct comparison is unavailable because this file has changed "
            "after the selected commit, or the working tree has local modifications."
        )

    def _update_direct_enabled(self):
        """Enable 'External Difftool' only when source is HEAD or file unchanged."""
        from lib.git_helpers import (
            is_file_unchanged_between, is_file_working_tree_clean)

        source_is_head = self.src_head_radio.isChecked()
        if source_is_head:
            # Source is HEAD — the repo file IS the source version
            self.direct_btn.setEnabled(True)
            self.direct_btn.setToolTip(
                "Compare the current repository file directly with the "
                "selected version using Git's configured difftool.")
            return

        # Source is the selected commit — check if file is unchanged to HEAD
        # and working tree is clean
        unchanged = is_file_unchanged_between(
            self.repo_path, self.filepath, self.selected_sha, self.head_sha)
        clean = is_file_working_tree_clean(self.repo_path, self.filepath)

        if unchanged and clean:
            self.direct_btn.setEnabled(True)
            self.direct_btn.setToolTip(
                "Compare the current repository file directly with the "
                "selected version using Git's configured difftool.")
        else:
            self.direct_btn.setEnabled(False)
            reason = []
            if not unchanged:
                reason.append("this file has changed after the selected commit")
            if not clean:
                reason.append("the working tree has local modifications")
            self.direct_btn.setToolTip(
                "Direct comparison is unavailable because " + " and ".join(reason) + ".")

    def _on_browse(self):
        ref = self.ref_combo.currentText().strip()
        if not ref:
            QMessageBox.information(self, "No ref",
                                    "Enter a commit, branch, or tag first.")
            return
        try:
            import subprocess
            result = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", ref],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding='utf-8', errors='replace')
            if result.returncode != 0:
                QMessageBox.critical(self, "Invalid Ref",
                                     f"'{ref}' does not resolve to a valid commit.\n\n{result.stderr}")
                return
            files = [f for f in result.stdout.strip().split('\n') if f.strip()]
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not list files: {e}")
            return

        from PySide6.QtWidgets import QDialog as _D, QListWidget, QDialogButtonBox
        pick = _D(self)
        pick.setWindowTitle(f"Select file at {ref}")
        pick.setMinimumSize(500, 400)
        pick_layout = QVBoxLayout(pick)

        search = QLineEdit()
        search.setPlaceholderText("Type to filter...")
        pick_layout.addWidget(search)

        lst = QListWidget()
        for f in files:
            lst.addItem(f)
        pick_layout.addWidget(lst)

        def filter_list(text):
            lst.clear()
            term = text.lower()
            for f in files:
                if term in f.lower():
                    lst.addItem(f)
        search.textChanged.connect(filter_list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(pick.accept)
        buttons.rejected.connect(pick.reject)
        pick_layout.addWidget(buttons)

        if pick.exec() == _D.Accepted and lst.currentItem():
            self.file_edit.setText(lst.currentItem().text())

    def _resolve_ref(self):
        """Resolve the destination ref to a SHA. Returns True on success."""
        ref = self.ref_combo.currentText().strip()
        if not ref:
            QMessageBox.warning(self, "No ref", "Please enter a commit, branch, or tag.")
            return False

        filepath = self.file_edit.text().strip()
        if not filepath:
            QMessageBox.information(self, "No file", "Please enter or browse for a file.")
            return False

        import subprocess
        try:
            result = subprocess.run(
                ["git", "rev-parse", ref],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding='utf-8', errors='replace')
            if result.returncode != 0:
                QMessageBox.critical(self, "Invalid Ref",
                                     f"'{ref}' does not resolve.\n\n{result.stderr}")
                return False
            self.resolved_sha = result.stdout.strip()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not resolve ref: {e}")
            return False

        source_sha = self.head_sha if self.src_head_radio.isChecked() else self.selected_sha
        if self.resolved_sha == source_sha:
            QMessageBox.information(self, "Same version",
                                    "Source and destination are the same version.")
            return False

        # Verify file exists at the target ref
        try:
            check = subprocess.run(
                ["git", "ls-tree", self.resolved_sha, "--", filepath],
                cwd=self.repo_path, capture_output=True, text=True,
                encoding='utf-8', errors='replace')
            if check.returncode != 0 or not check.stdout.strip():
                QMessageBox.critical(
                    self, "File not found",
                    f"'{filepath}' does not exist at {ref} ({self.resolved_sha[:8]}).\n\n"
                    "Use Browse... to select the correct file at that version.")
                return False
        except Exception:
            pass

        self.selected_file = filepath
        return True

    def _check_difftool(self):
        """Check if difftool is configured. Returns True if ok or user confirms."""
        from lib.git_helpers import get_difftool_name
        name = get_difftool_name(self.repo_path)
        if not name:
            reply = QMessageBox.question(
                self, "Difftool not configured",
                "No difftool is configured (diff.tool is not set).\n\n"
                "git difftool will fall back to vimdiff.\n\n"
                "Configure one first, e.g.:\n"
                "  git config --global diff.tool meld\n"
                "  git config --global difftool.prompt false\n\n"
                "Continue anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            return reply == QMessageBox.Yes
        return True

    def _on_difftool(self):
        """Run difftool using temp files (extracted versions)."""
        if not self._resolve_ref():
            return
        if not self._check_difftool():
            return
        self.use_direct = False
        self.accept()

    def _on_direct(self):
        """Run configured diff tool directly (repo file vs target ref)."""
        from PySide6.QtCore import QSettings
        settings = QSettings("git-interactive-rebase-gui-tool", "config")
        mode = settings.value("difftool/mode", "git")
        command = settings.value("difftool/command", "")
        if mode != "custom" or not command.strip():
            QMessageBox.information(
                self, "Diff tool not configured",
                "No custom diff tool is configured.\n\n"
                "Open Configure > External Tools Integration "
                "to set up your preferred diff tool.")
            return
        if not self._resolve_ref():
            return
        self.use_direct = True
        self.accept()
