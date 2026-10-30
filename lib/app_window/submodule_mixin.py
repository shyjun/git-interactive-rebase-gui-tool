from PySide6.QtWidgets import QMessageBox

from lib.dialogs import SubmodulesDialog
from lib.app_window.helpers import _log


class SubmoduleMixin:
    def handle_submodules(self):
        """Open the submodule manager dialog (Repo menu).

        Submodule changes are excluded from all unstaged-change flows; this
        dialog is the dedicated place to stage / commit / discard them."""
        dialog = SubmodulesDialog(
            self.repo_path,
            font_size=self.current_font_size,
            font_family=self.current_font_family,
            can_modify=not self.viewer_mode,
            parent=self,
        )
        # Synchronous (direct-connection) so the undo state is saved before the
        # dialog creates the pointer commit.
        dialog.will_mutate_history.connect(self.save_undo_state)

        def _on_changed(history_mutated):
            if history_mutated:
                _log("[submodules] Pointer commit created; reloading history.")
                self.load_history()
                self._notify_browse_windows()
                QMessageBox.information(
                    self, "Submodule Commit Successful",
                    f"Done. Submodule pointer commit created.\n\nCommit ID:\n{self.get_head_sha()[:8]}"
                )

        dialog.changed.connect(_on_changed)
        dialog.exec()
