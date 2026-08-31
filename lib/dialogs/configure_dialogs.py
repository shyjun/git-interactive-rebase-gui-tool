
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
    """Dialog to configure external tool integrations.

    Currently supports:
    - Diff tool (Not configured / Git configured / Custom command)

    Future: Mergetool, etc.
    """

    def __init__(self, repo_path, parent=None):
        super().__init__(parent)
        self.repo_path = repo_path
        self.setWindowTitle("External Tools")
        self.setFixedSize(520, 320)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── Diff tool group ──
        diff_group = QGroupBox("Diff tool")
        diff_group.setStyleSheet("QGroupBox { padding-top: 8px; }")
        diff_layout = QVBoxLayout(diff_group)
        diff_layout.setSpacing(2)
        diff_layout.setContentsMargins(8, 4, 8, 6)

        self.mode_group = QButtonGroup(self)

        # Not configured — compact
        self.none_radio = QRadioButton("Not configured")
        self.none_radio.setToolTip("External difftool integration is disabled.")
        self.none_radio.setChecked(True)
        self.mode_group.addButton(self.none_radio, 0)
        diff_layout.addWidget(self.none_radio)

        none_desc = QLabel("External difftool integration is disabled.")
        none_desc.setStyleSheet("color: gray;")
        none_desc.setContentsMargins(24, 0, 0, 0)
        diff_layout.addWidget(none_desc)

        diff_layout.addSpacing(2)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setFrameShadow(QFrame.Sunken)
        diff_layout.addWidget(sep1)

        diff_layout.addSpacing(2)

        # Git difftool — compact
        self.git_radio = QRadioButton("Use Git configured difftool")
        self.git_radio.setToolTip("Use the difftool configured in your Git settings (diff.tool).")
        self.mode_group.addButton(self.git_radio, 1)
        diff_layout.addWidget(self.git_radio)

        self.git_tool_label = QLabel("Git difftool: (detecting...)")
        self.git_tool_label.setContentsMargins(24, 0, 0, 0)
        diff_layout.addWidget(self.git_tool_label)

        self.git_status_label = QLabel("Status: (detecting...)")
        self.git_status_label.setContentsMargins(24, 0, 0, 0)
        diff_layout.addWidget(self.git_status_label)

        diff_layout.addSpacing(2)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFrameShadow(QFrame.Sunken)
        diff_layout.addWidget(sep2)

        diff_layout.addSpacing(2)

        # Custom command — compact
        self.custom_radio = QRadioButton("Use custom command")
        self.custom_radio.setToolTip("Specify a custom diff tool command.")
        self.mode_group.addButton(self.custom_radio, 2)
        diff_layout.addWidget(self.custom_radio)

        cmd_row = QHBoxLayout()
        cmd_row.setContentsMargins(24, 0, 0, 0)
        cmd_row.addWidget(QLabel("Command:"))
        self.command_edit = QLineEdit()
        self.command_edit.setPlaceholderText("e.g. kdiff3, code, diffmerge")
        cmd_row.addWidget(self.command_edit, 1)
        diff_layout.addLayout(cmd_row)

        diff_layout.addSpacing(4)

        args_row = QHBoxLayout()
        args_row.setContentsMargins(24, 0, 0, 0)
        args_row.addWidget(QLabel("Arguments:"))
        self.args_edit = QLineEdit()
        self.args_edit.setPlaceholderText("{file1} {file2}")
        args_row.addWidget(self.args_edit, 1)
        diff_layout.addLayout(args_row)

        example = QLabel("Example: kdiff3 {file1} {file2}")
        example.setStyleSheet("color: gray; font-size: 11px;")
        example.setContentsMargins(24, 0, 0, 0)
        diff_layout.addWidget(example)

        layout.addWidget(diff_group)

        # ── Wire radio toggles ──
        self.none_radio.toggled.connect(self._update_ui)
        self.git_radio.toggled.connect(self._update_ui)
        self.custom_radio.toggled.connect(self._update_ui)

        # ── Buttons ──
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
        mode = settings.value("difftool/mode", "none")
        command = settings.value("difftool/command", "")
        args = settings.value("difftool/args", "{file1} {file2}")

        self.command_edit.setText(command)
        self.args_edit.setText(args)

        if mode == "custom":
            self.custom_radio.setChecked(True)
        elif mode == "git":
            self.git_radio.setChecked(True)
        else:
            self.none_radio.setChecked(True)

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
        elif self.custom_radio.isChecked():
            cmd = self.command_edit.text().strip()
            self.save_btn.setEnabled(bool(cmd))
            self.save_btn.setToolTip("" if cmd else "Enter a command to enable Save.")
        else:
            self.save_btn.setEnabled(True)
            self.save_btn.setToolTip("")

    def _on_save(self):
        """Save the configuration and close."""
        from PySide6.QtCore import QSettings
        settings = QSettings("git-interactive-rebase-gui-tool", "config")

        if self.none_radio.isChecked():
            settings.setValue("difftool/mode", "none")
            settings.setValue("difftool/command", "")
            settings.setValue("difftool/args", "")
        elif self.git_radio.isChecked():
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
        """Read the saved difftool configuration and return (command_list, is_direct)."""
        from PySide6.QtCore import QSettings
        settings = QSettings("git-interactive-rebase-gui-tool", "config")
        mode = settings.value("difftool/mode", "none")

        if mode == "custom":
            command = settings.value("difftool/command", "")
            args = settings.value("difftool/args", "{file1} {file2}")
            if command:
                return command, args, False

        return None, None, None
