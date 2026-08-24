from lib.app_window.split_utils import parse_hunks as _parse_hunks, patch_has_changes as _patch_has_changes, rebuild_patch as _rebuild_patch
from lib.app_window.refine_mixin import RefineMixin
from lib.app_window.split_file_mixin import SplitFileMixin
from lib.app_window.split_bulk_mixin import SplitBulkMixin


class SplitMixin(RefineMixin, SplitFileMixin, SplitBulkMixin):
    """Commit splitting, file-moving, and refine operations."""
    pass
