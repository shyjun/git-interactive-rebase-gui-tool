from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from lib.app_window.helpers import get_theme_stylesheet
from lib.widgets import DiffHighlighter


class AppearanceMixin:
    """Appearance-related methods for GitInteractiveRebaseApp."""

    def apply_theme(self, theme_name):
        """Applies a theme to the entire application globally."""
        if theme_name == "dark":
            # VS Code Dark+ inspired palette
            self.current_theme_colors = {
                "added": "#4ec9b0",   # Soft teal/green
                "removed": "#f48771", # Soft coral/red
                "header": "#569cd6",  # VS Code blue
                "bg": "#1e1e1e",      # Main background
                "fg": "#cccccc",      # Standard text
                "accent": "#007acc",  # VS Code accent blue
                "separator": "#CCCCCC" # Neutral Slate Gray
            }
        else:
            self.current_theme_colors = {
                "added": "#228b22",  # Darker green for light bg
                "removed": "#b22222", # Darker red for light bg
                "header": "#00008b", # Darker blue for light bg
                "bg": "#f5f5f7",
                "fg": "#333333",
                "accent": "#007aff",
                "separator": "#CCCCCC" # Neutral Slate Gray
            }

        # Theme is app-global; only (re)apply the stylesheet when it actually
        # changes, otherwise re-polishing every window would reset their fonts.
        new_stylesheet = get_theme_stylesheet(theme_name)
        if QApplication.instance().styleSheet() != new_stylesheet:
            QApplication.instance().setStyleSheet(new_stylesheet)

        # Update highlighter colors according to the theme
        if hasattr(self, 'side_diff_view'):
            if hasattr(self, 'side_highlighter') and self.side_highlighter is not None:
                self.side_highlighter.setDocument(None)
            self.side_highlighter = DiffHighlighter(
                self.side_diff_view.document(),
                added_color=self.current_theme_colors["added"],
                removed_color=self.current_theme_colors["removed"],
                header_color=self.current_theme_colors["header"]
            )

        if hasattr(self, 'filewise_diff_view'):
            if hasattr(self, 'filewise_highlighter') and self.filewise_highlighter is not None:
                self.filewise_highlighter.setDocument(None)
            self.filewise_highlighter = DiffHighlighter(
                self.filewise_diff_view.document(),
                added_color=self.current_theme_colors["added"],
                removed_color=self.current_theme_colors["removed"],
                header_color=self.current_theme_colors["header"]
            )

        if hasattr(self, 'treewise_diff_view'):
            if hasattr(self, 'treewise_highlighter') and self.treewise_highlighter is not None:
                self.treewise_highlighter.setDocument(None)
            self.treewise_highlighter = DiffHighlighter(
                self.treewise_diff_view.document(),
                added_color=self.current_theme_colors["added"],
                removed_color=self.current_theme_colors["removed"],
                header_color=self.current_theme_colors["header"]
            )

        self.update_font()

        if getattr(self, '_browse_overlay', None) is not None:
            self._browse_overlay.set_is_dark(self.is_dark_theme)
            self._browse_overlay.update()

    def update_font(self):
        font = QFont("Monospace", self.current_font_size)
        self.list_widget.setFont(font)
        if hasattr(self, 'side_diff_view'):
            self.side_diff_view.setFont(font)
        if hasattr(self, 'side_commit_msg'):
            self.side_commit_msg.setFont(font)
        if hasattr(self, 'filewise_diff_view'):
            self.filewise_diff_view.setFont(font)
        if hasattr(self, 'filewise_file_list'):
            self.filewise_file_list.setFont(font)
        if hasattr(self, 'treewise_diff_view'):
            self.treewise_diff_view.setFont(font)
        if hasattr(self, 'treewise_tree'):
            self.treewise_tree.setFont(font)
        # Save persistence (font size is app-wide, not window-scoped)
        self.settings.setValue("font_size", self.current_font_size)
        # Update status bar zoom label
        if hasattr(self, 'zoom_percent_label'):
            default_size = 10
            pct = int(self.current_font_size / default_size * 100)
            self.zoom_percent_label.setText(f"{pct}%")

    def handle_zoom_in(self):
        self.current_font_size += 1
        self.update_font()
        self._propagate_browse_font()

    def handle_zoom_out(self):
        if self.current_font_size > 6:
            self.current_font_size -= 1
            self.update_font()
            self._propagate_browse_font()

    def on_theme_toggled(self):
        theme = "dark" if self.dark_radio.isChecked() else "light"
        self.is_dark_theme = (theme == "dark")
        self.apply_theme(theme)
        self.settings.setValue("theme", theme)
        self._refresh_toolbar_icons()
        for viewer in list(self.browse_windows):
            if not hasattr(viewer, "apply_theme"):
                continue
            if viewer.is_dark_theme != self.is_dark_theme:
                viewer.is_dark_theme = self.is_dark_theme
                viewer.apply_theme("dark" if self.is_dark_theme else "light")
            viewer._refresh_toolbar_icons()
        if self.theme_menu_btn.menu():
            self.theme_menu_btn.menu().close()

    def _propagate_browse_font(self):
        for viewer in list(self.browse_windows):
            viewer.current_font_size = self.current_font_size
            viewer.update_font()

    def on_origin_visibility_toggled(self, visible):
        self.origin_group.setVisible(visible)
        self.settings.setValue(self._sk("show_origin_options"), visible)
        # self.force_window_resize()  # intentionally disabled: window keeps its size instead of auto-collapsing

    def on_rebase_visibility_toggled(self, visible):
        self.rebase_group.setVisible(visible)
        self.settings.setValue(self._sk("show_rebase_options"), visible)
        # self.force_window_resize()  # intentionally disabled: window keeps its size instead of auto-collapsing

    def on_squash_visibility_toggled(self, visible):
        self.squash_group.setVisible(visible)
        self.settings.setValue(self._sk("show_squash_options"), visible)
        # self.force_window_resize()  # intentionally disabled: window keeps its size instead of auto-collapsing

    def on_local_branches_visibility_toggled(self, visible):
        self.show_local_branches = visible
        self.settings.setValue(self._sk("show_local_branches"), self.show_local_branches)
        self.list_widget.viewport().update()

    def on_tags_visibility_toggled(self, visible):
        self.show_tags = visible
        self.settings.setValue(self._sk("show_tags"), self.show_tags)
        self.list_widget.viewport().update()

    def _on_stats_toggled(self, visible):
        self.show_stats = visible
        self.settings.setValue(self._sk("show_stats"), self.show_stats)
        self.list_widget.viewport().update()

    def _on_date_toggled(self, visible):
        self.show_date = visible
        self.settings.setValue(self._sk("show_date"), self.show_date)
        self.list_widget.viewport().update()

    def on_diffs_visibility_toggled(self, visible):
        self.show_diffs = visible
        self.right_panel.setVisible(visible)
        self.settings.setValue(self._sk("show_diffs"), self.show_diffs)
