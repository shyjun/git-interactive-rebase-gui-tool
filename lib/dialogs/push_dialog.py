# pyrefly: ignore [missing-import]
from PySide6.QtCore import Qt
# pyrefly: ignore [missing-import]
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
)
# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)


def create_warning_pixmap(size=44):
    """Draw a vector warning triangle icon with exclamation mark."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    scale = size / 48.0
    painter.scale(scale, scale)

    # Triangle path with rounded vertices
    path = QPainterPath()
    path.moveTo(8.5, 41.0)
    path.lineTo(39.5, 41.0)
    path.quadTo(44.0, 41.0, 42.2, 37.2)
    path.lineTo(26.2, 6.5)
    path.quadTo(24.0, 2.5, 21.8, 6.5)
    path.lineTo(5.8, 37.2)
    path.quadTo(4.0, 41.0, 8.5, 41.0)
    path.closeSubpath()

    gradient = QLinearGradient(24.0, 4.0, 24.0, 41.0)
    gradient.setColorAt(0.0, QColor("#fbbf24"))  # Warm amber/yellow
    gradient.setColorAt(0.5, QColor("#f59e0b"))  # Amber
    gradient.setColorAt(1.0, QColor("#d97706"))  # Deep orange

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawPath(path)

    # Exclamation mark
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor("#ffffff")))

    # Upper vertical bar with rounded caps
    bar_path = QPainterPath()
    bar_path.addRoundedRect(22.3, 17.0, 3.4, 11.5, 1.7, 1.7)
    painter.drawPath(bar_path)

    # Lower dot
    painter.drawEllipse(22.3, 31.8, 3.4, 3.4)

    painter.end()
    return pixmap


class PushDialog(QDialog):
    """Dialog allowing user to choose git push options.

    Follows the same flat layout pattern as MergeBaseDialog so the global app
    stylesheet (bold QPushButtons, bold QLabels, themed QDialog background,
    etc.) applies uniformly.
    """

    OPTION_NORMAL = "normal"
    OPTION_FORCE = "force"
    OPTION_FORCE_WITH_LEASE = "force_with_lease"

    def __init__(self, parent=None, is_dark=None, remote="origin"):
        super().__init__(parent)
        self.setWindowTitle("Push")
        self.setModal(True)
        self.setMinimumWidth(460)

        # is_dark kept for test compatibility; actual styling comes from
        # the global QApplication stylesheet set by apply_theme().
        if is_dark is None:
            if hasattr(parent, 'is_dark_theme'):
                is_dark = bool(parent.is_dark_theme)
            else:
                is_dark = False
        self.is_dark = is_dark
        self.remote = remote or "origin"

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # ── Header: Warning icon + Title ──
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(create_warning_pixmap(36))
        self.icon_label.setFixedSize(36, 36)
        header_layout.addWidget(self.icon_label)

        self.header_title = QLabel("Push can overwrite remote history")
        layout.addLayout(header_layout)

        header_layout.addWidget(self.header_title)

        # ── Subtitle (non-bold to match the "VS" style label in MergeBase) ──
        self.header_subtitle = QLabel(
            f"Choose how to push your current branch to {self.remote}."
        )
        self.header_subtitle.setStyleSheet("font-size: 13px; color: gray;")
        layout.addWidget(self.header_subtitle)

        # ── Push option radio buttons ──
        self.button_group = QButtonGroup(self)

        self.normal_radio = QRadioButton("Normal push  (git push)")
        self.normal_radio.setChecked(True)
        self.button_group.addButton(self.normal_radio, 0)
        layout.addWidget(self.normal_radio)

        self.force_radio = QRadioButton("Force push  (git push --force)")
        self.button_group.addButton(self.force_radio, 1)
        layout.addWidget(self.force_radio)

        self.lease_radio = QRadioButton(
            "Force push with lease  (git push --force-with-lease)"
        )
        self.button_group.addButton(self.lease_radio, 2)
        layout.addWidget(self.lease_radio)

        # ── Buttons (same pattern as MergeBaseDialog) ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.push_btn = QPushButton("Push")
        self.push_btn.setDefault(True)
        self.push_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.push_btn)

        layout.addLayout(btn_layout)

    def get_selected_option(self):
        """Returns the selected option identifier:
        'normal', 'force', or 'force_with_lease'.
        """
        if self.force_radio.isChecked():
            return self.OPTION_FORCE
        if self.lease_radio.isChecked():
            return self.OPTION_FORCE_WITH_LEASE
        return self.OPTION_NORMAL

    def get_git_command(self):
        """Returns the git command argument list and human-readable label."""
        option = self.get_selected_option()
        if option == self.OPTION_FORCE:
            return ["git", "push", "--force"], "git push --force"
        if option == self.OPTION_FORCE_WITH_LEASE:
            return ["git", "push", "--force-with-lease"], "git push --force-with-lease"
        return ["git", "push"], "git push"
