import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from lib.app_window.helpers import mono_font


class RenameMoveDialog(QDialog):
    """Pick a source and destination path in the working tree, then choose
    how the rename/move should land in git: staged only, committed as a new
    commit, or amended into HEAD.

    Returns the normalized repo-relative paths via *src_path* / *dst_path*
    and the chosen action via *action* (StageAction / CommitAction /
    AmendAction). Validation runs on every action click; the dialog stays
    open with a warning on invalid input."""

    StageAction = "stage"
    CommitAction = "commit"
    AmendAction = "amend"

    def __init__(self, repo_path, font_size=10, font_family=None, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.action = self.StageAction
        self.src_path = ""
        self.dst_path = ""
        self.font_size = font_size
        self.font_family = font_family

        self.setWindowTitle("Rename / Move a File or Folder")
        self.setMinimumWidth(560)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QLabel(
            "Rename or move a file/folder in the working tree. Git records it "
            "as a rename when both paths are staged (<code>git add -A</code>)."
        )
        header.setTextFormat(Qt.RichText)
        header.setWordWrap(True)
        layout.addWidget(header)

        layout.addWidget(QLabel("From (repo-relative path):"))
        from_row = QHBoxLayout()
        from_row.setSpacing(6)
        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText("e.g. lib/app_window.py, docs/old-name.md")
        self.src_edit.setToolTip(
            "Path of the file or folder to rename/move, relative to the repository root."
        )
        self.src_edit.setFont(mono_font(font_size, family=font_family))
        from_row.addWidget(self.src_edit, 1)
        pick_file_btn = QPushButton("File…")
        pick_file_btn.setToolTip("Pick a file inside the repository.")
        pick_file_btn.clicked.connect(self._pick_source_file)
        from_row.addWidget(pick_file_btn)
        pick_dir_btn = QPushButton("Folder…")
        pick_dir_btn.setToolTip("Pick a folder inside the repository.")
        pick_dir_btn.clicked.connect(self._pick_source_dir)
        from_row.addWidget(pick_dir_btn)
        layout.addLayout(from_row)

        layout.addWidget(QLabel("To (new repo-relative path):"))
        to_row = QHBoxLayout()
        to_row.setSpacing(6)
        self.dst_edit = QLineEdit()
        self.dst_edit.setPlaceholderText("e.g. lib/renamed.py, docs/new-name.md")
        self.dst_edit.setToolTip(
            "The new path (and/or new name) relative to the repository root. "
            "Use Folder… to pick a destination folder; the current name is appended."
        )
        self.dst_edit.setFont(mono_font(font_size, family=font_family))
        to_row.addWidget(self.dst_edit, 1)
        to_dir_btn = QPushButton("Folder…")
        to_dir_btn.setToolTip(
            "Pick the destination folder; the To field becomes <folder>/<current name>."
        )
        to_dir_btn.clicked.connect(self._pick_dest_dir)
        to_row.addWidget(to_dir_btn)
        layout.addLayout(to_row)

        note = QLabel(
            "<b>Stage</b> only updates the index — handle it later via "
            "<b>Repo → Handle Staged Changes</b>. <b>Commit</b> and <b>Amend</b> "
            "open the commit-message dialog (Amend pre-fills HEAD's message)."
        )
        note.setTextFormat(Qt.RichText)
        note.setWordWrap(True)
        layout.addWidget(note)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.amend_btn = QPushButton("commit --amend the rename/move")
        self.amend_btn.setToolTip(
            "Move the path and amend the rename into the HEAD commit, message editable."
        )
        self.amend_btn.setStyleSheet(
            "QPushButton { color: #8e44ad; border: 2px solid #8e44ad; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #f6eefb; }"
        )

        self.commit_btn = QPushButton("Commit the Rename/Move")
        self.commit_btn.setDefault(True)
        self.commit_btn.setToolTip(
            "Move the path and commit the rename as a new commit (git commit --only)."
        )
        self.commit_btn.setStyleSheet(
            "QPushButton { color: #0055cc; border: 2px solid #0055cc; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #eef4ff; }"
        )

        self.stage_btn = QPushButton("Stage the Rename/Move")
        self.stage_btn.setToolTip(
            "Move the path and stage both sides (git add -A) for Repo → Handle Staged Changes."
        )
        self.stage_btn.setStyleSheet(
            "QPushButton { color: #22863a; border: 2px solid #22863a; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #f0fff0; }"
        )

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setToolTip("Close without renaming/moving anything.")
        cancel_btn.setStyleSheet(
            "QPushButton { color: #555; border: 2px solid #555; padding: 10px 18px; "
            "border-radius: 6px; font-weight: bold; } "
            "QPushButton:hover { background-color: #f5f5f5; }"
        )

        self.amend_btn.clicked.connect(self._on_amend)
        self.commit_btn.clicked.connect(self._on_commit)
        self.stage_btn.clicked.connect(self._on_stage)
        cancel_btn.clicked.connect(self.reject)

        # One column per button with a small colored note underneath, exactly
        # like the Commit Selectively dialog.
        amend_col = QVBoxLayout()
        amend_col.setSpacing(2)
        amend_col.addWidget(self.amend_btn)
        amend_note = QLabel("(amend HEAD message)")
        amend_note.setStyleSheet("color: #8e44ad; font-size: 11px;")
        amend_note.setAlignment(Qt.AlignCenter)
        amend_col.addWidget(amend_note)

        commit_col = QVBoxLayout()
        commit_col.setSpacing(2)
        commit_col.addWidget(self.commit_btn)
        commit_note = QLabel("(new commit, only these paths)")
        commit_note.setStyleSheet("color: #0055cc; font-size: 11px;")
        commit_note.setAlignment(Qt.AlignCenter)
        commit_col.addWidget(commit_note)

        stage_col = QVBoxLayout()
        stage_col.setSpacing(2)
        stage_col.addWidget(self.stage_btn)
        stage_note = QLabel("(stage for Handle Staged Changes)")
        stage_note.setStyleSheet("color: #22863a; font-size: 11px;")
        stage_note.setAlignment(Qt.AlignCenter)
        stage_col.addWidget(stage_note)

        cancel_col = QVBoxLayout()
        cancel_col.setSpacing(2)
        cancel_col.addWidget(cancel_btn)
        cancel_note = QLabel("Cancel")
        cancel_note.setStyleSheet("color: #555; font-size: 11px;")
        cancel_note.setAlignment(Qt.AlignCenter)
        cancel_col.addWidget(cancel_note)

        btn_row.addStretch()
        btn_row.addLayout(amend_col)
        btn_row.addLayout(commit_col)
        btn_row.addLayout(stage_col)
        btn_row.addLayout(cancel_col)
        layout.addLayout(btn_row)

        self.src_edit.setFocus()

    # ------------------------------------------------------------------ #
    # Path picking
    # ------------------------------------------------------------------ #

    def _rel_or_warn(self, abs_path):
        """Converts an absolute path to a repo-relative '/' path, warning and
        returning None when it lies outside the repository."""
        try:
            rel = os.path.relpath(abs_path, self.repo_path)
        except ValueError:
            rel = ".."
        if rel.startswith(".."):
            QMessageBox.warning(
                self, "Outside repository",
                "Please choose a path inside the repository.")
            return None
        return rel.replace(os.sep, "/").rstrip("/")

    def _pick_source_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select file to rename/move", self.repo_path)
        if path:
            rel = self._rel_or_warn(path)
            if rel:
                self.src_edit.setText(rel)
                if not self.dst_edit.text().strip():
                    self.dst_edit.setText(rel)

    def _pick_source_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select folder to rename/move", self.repo_path)
        if path:
            rel = self._rel_or_warn(path)
            if rel:
                self.src_edit.setText(rel)
                if not self.dst_edit.text().strip():
                    self.dst_edit.setText(rel)

    def _pick_dest_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select destination folder", self.repo_path)
        if path:
            rel = self._rel_or_warn(path)
            if rel:
                name = os.path.basename(self._norm(self.src_edit.text()))
                self.dst_edit.setText(f"{rel}/{name}" if name else rel)

    # ------------------------------------------------------------------ #
    # Validation and action selection
    # ------------------------------------------------------------------ #

    @staticmethod
    def _norm(path):
        p = (path or "").strip().replace("\\", "/").strip("/")
        while "//" in p:
            p = p.replace("//", "/")
        while p.startswith("./"):
            p = p[2:]
        return p

    def _validate(self):
        src = self._norm(self.src_edit.text())
        dst = self._norm(self.dst_edit.text())
        if not src or not dst:
            QMessageBox.warning(
                self, "Missing path",
                "Please enter both a source and a destination path.")
            return False
        if src == dst:
            QMessageBox.warning(
                self, "Same path",
                "Source and destination are the same path.")
            return False

        root = os.path.realpath(self.repo_path)
        src_abs = os.path.realpath(os.path.join(self.repo_path, src))
        dst_abs = os.path.realpath(os.path.join(self.repo_path, dst))
        if src_abs == root or dst_abs == root:
            QMessageBox.warning(
                self, "Repository root",
                "Cannot rename/move the repository root itself.")
            return False
        if not (src_abs.startswith(root + os.sep)
                and dst_abs.startswith(root + os.sep)):
            QMessageBox.warning(
                self, "Outside repository",
                "Both paths must be inside the repository.")
            return False
        if ".git" in src.split("/") or ".git" in dst.split("/"):
            QMessageBox.warning(
                self, "Inside .git",
                "Paths under .git/ cannot be renamed/moved.")
            return False

        case_only = (os.path.normcase(src_abs) == os.path.normcase(dst_abs)
                     and src_abs != dst_abs)
        if not os.path.exists(src_abs):
            QMessageBox.warning(
                self, "Missing source",
                f"The source path does not exist:\n{src}")
            return False
        if os.path.exists(dst_abs) and not case_only:
            QMessageBox.warning(
                self, "Destination exists",
                f"The destination already exists:\n{dst}")
            return False
        if not case_only and dst_abs.startswith(src_abs + os.sep):
            QMessageBox.warning(
                self, "Into itself",
                "Cannot move a folder into itself.")
            return False

        self.src_path = src
        self.dst_path = dst
        return True

    def _on_stage(self):
        if self._validate():
            self.action = self.StageAction
            self.accept()

    def _on_commit(self):
        if self._validate():
            self.action = self.CommitAction
            self.accept()

    def _on_amend(self):
        if self._validate():
            self.action = self.AmendAction
            self.accept()
