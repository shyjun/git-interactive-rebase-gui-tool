
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QGroupBox,
    QPushButton,
    QMessageBox,
    QFrame,
)
from PySide6.QtCore import Qt


class ConfigureDiffToolDialog(QDialog):
    """Dialog to configure how external file comparisons are opened.

    Two modes:
    - Use Git configured difftool (reads diff.tool from git config)
    - Use custom command (user-provided command + arguments)
    """

    def __init__(self, repo_path, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle("Configure Diff Tool")
        self.setMinimumWidth(520)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        intro = QLabel("Select how external file comparisons are opened.")
        layout.addWidget(intro)

        # --- Git difftool mode ---
        git_group = QGroupBox()
        git_layout = QVBoxLayout(git_group)

        self.git_radio = QRadioButton("Use Git configured difftool")
        self.git_radio.setToolTip("Use the difftool configured in your Git settings (diff.tool).")
        git_layout.addWidget(self.git_radio)

        info_frame = QFrame()
        info_frame.setContentsMargins(24, 0, 0, 0)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(0, 4, 0, 4)
        info_layout.setSpacing(2)

        self.git_tool_label = QLabel("Git difftool: (detecting...)")
        info_layout.addWidget(self.git_tool_label)

        self.git_status_label = QLabel("Status: (detecting...)")
        info_layout.addWidget(self.git_status_label)

        git_layout.addWidget(info_frame)
        layout.addWidget(git_group)

        # --- Custom command mode ---
        custom_group = QGroupBox()
        custom_layout = QVBoxLayout(custom_group)

        self.custom_radio = QRadioButton("Use custom command")
        self.custom_radio.setToolTip("Specify a custom diff tool command.")
        custom_layout.addWidget(self.custom_radio)

        cmd_frame = QFrame()
        cmd_frame.setContentsMargins(24, 0, 0, 0)
        cmd_layout = QVBoxLayout(cmd_frame)
        cmd_layout.setContentsMargins(0, 4, 0, 4)
        cmd_layout.setSpacing(6)

        cmd_row = QHBoxLayout()
        cmd_row.addWidget(QLabel("Command:"))
        self.command_edit = QLineEdit()
        self.command_edit.setPlaceholderText("e.g. meld, code, diffmerge")
        cmd_row.addWidget(self.command_edit, 1)
        cmd_layout.addLayout(cmd_row)

        args_row = QHBoxLayout()
        args_row.addWidget(QLabel("Arguments:"))
        self.args_edit = QLineEdit()
        self.args_edit.setPlaceholderText("{file1} {file2}")
        args_row.addWidget(self.args_edit, 1)
        cmd_layout.addLayout(args_row)

        example = QLabel("Example: code --diff {file1} {file2}")
        example.setStyleSheet("color: gray; font-size: 11px;")
        cmd_layout.addWidget(example)

        custom_layout.addWidget(cmd_frame)
        layout.addWidget(custom_group)

        # --- Radio group ---
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.git_radio, 0)
        self.mode_group.addButton(self.custom_radio, 1)
        self.git_radio.toggled.connect(self._update_ui)
        self.custom_radio.toggled.connect(self._update_ui)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Re-read the Git difftool configuration.")
        refresh_btn.clicked.connect(self._refresh_git_status)
        btn_layout.addWidget(refresh_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

        self.command_edit.textChanged.connect(self._update_ui)
        self.args_edit.textChanged.connect(self._update_ui)

        # Load saved settings
        self._load_settings()
        self._refresh_git_status()

    def _load_settings(self):
        """Load saved difftool configuration from QSettings."""
        from PySide6.QtCore import QSettings
        settings = QSettings("git-interactive-rebase-gui-tool", "config")
        mode = settings.value("difftool/mode", "git")
        command = settings.value("difftool/command", "")
        args = settings.value("difftool/args", "{file1} {file2}")

        self.command_edit.setText(command)
        self.args_edit.setText(args)

        if mode == "custom":
            self.custom_radio.setChecked(True)
        else:
            self.git_radio.setChecked(True)

    def _refresh_git_status(self):
        """Read the Git difftool configuration and update the display."""
        from lib.git_helpers import get_difftool_name
        name = get_difftool_name(self.repo_path)
        if name:
            self.git_tool_label.setText(f"Git difftool: {name}")
            self.git_status_label.setText("Status: \u2713 Configured")
            self.git_status_label.setStyleSheet("color: green;")
        else:
            self.git_tool_label.setText("Git difftool: Not configured")
            self.git_status_label.setText("Status: \u26a0 Not configured")
            self.git_status_label.setStyleSheet("color: orange;")
        self._update_ui()

    def _update_ui(self):
        """Enable/disable controls based on selected mode."""
        is_custom = self.custom_radio.isChecked()
        self.command_edit.setEnabled(is_custom)
        self.args_edit.setEnabled(is_custom)

        # Prevent saving Git mode if no difftool is configured
        if self.git_radio.isChecked():
            from lib.git_helpers import get_difftool_name
            name = get_difftool_name(self.repo_path)
            self.save_btn.setEnabled(bool(name))
            if not name:
                self.save_btn.setToolTip(
                    "Cannot save: no Git difftool is configured. "
                    "Configure one first (git config --global diff.tool <tool>) "
                    "or switch to custom command.")
            else:
                self.save_btn.setToolTip("")
        else:
            # Custom mode: enabled if command is non-empty
            cmd = self.command_edit.text().strip()
            self.save_btn.setEnabled(bool(cmd))
            self.save_btn.setToolTip("" if cmd else "Enter a command to enable Save.")

    def _on_save(self):
        """Save the configuration and close."""
        from PySide6.QtCore import QSettings
        settings = QSettings("git-interactive-rebase-gui-tool", "config")

        if self.git_radio.isChecked():
            settings.setValue("difftool/mode", "git")
            settings.setValue("difftool/command", "")
            settings.setValue("difftool/args", "")
        else:
            cmd = self.command_edit.text().strip()
            if not cmd:
                QMessageBox.warning(self, "No command", "Please enter a command.")
                return
            settings.setValue("difftool/mode", "custom")
            settings.setValue("difftool/command", cmd)
            settings.setValue("difftool/args", self.args_edit.text().strip() or "{file1} {file2}")

        self.accept()

    @staticmethod
    def get_difftool_command(repo_path):
        """Read the saved difftool configuration and return (command_list, is_direct).

        Returns a list suitable for subprocess.Popen (with {file1}/{file2} already
        replaced) and a boolean indicating whether to use direct repo comparison
        (True) or temp-file extraction (False).

        If no configuration exists, falls back to git difftool.
        """
        from PySide6.QtCore import QSettings
        settings = QSettings("git-interactive-rebase-gui-tool", "config")
        mode = settings.value("difftool/mode", "git")

        if mode == "custom":
            command = settings.value("difftool/command", "")
            args = settings.value("difftool/args", "{file1} {file2}")
            if command:
                return command, args, False  # custom always uses temp files

        # Fall back to git difftool
        return None, None, None  # signals caller to use git difftool
