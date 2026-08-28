import unittest
import sys
import os
import importlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MODULES_TO_TEST = [
    "lib.utils",
    "lib.widgets",
    "lib.commit_filter_controller",
    "lib.git_helpers",
    "lib.git_helpers.core",
    "lib.git_helpers.blame",
    "lib.git_helpers.branches",
    "lib.git_helpers.commit_ops",
    "lib.git_helpers.commits",
    "lib.git_helpers.diffs",
    "lib.git_helpers.history",
    "lib.git_helpers.stash",
    "lib.git_helpers.status",
    "lib.git_helpers.update",
    "lib.dialogs",
    "lib.dialogs.blame_dialog",
    "lib.dialogs.commit_action_dialogs",
    "lib.dialogs.commit_message_dialogs",
    "lib.dialogs.confirmation_dialogs",
    "lib.dialogs.diff_dialogs",
    "lib.dialogs.diff_viewer_dialog",
    "lib.dialogs.history_branch_dialogs",
    "lib.dialogs.hunk_file_dialogs",
    "lib.dialogs.hunk_widgets",
    "lib.dialogs.refine_changes_dialog",
    "lib.dialogs.split_drop_dialogs",
    "lib.dialogs.unstaged_dialogs",
    "lib.app_window",
    "lib.app_window.appearance_mixin",
    "lib.app_window.browse_mixin",
    "lib.app_window.cherry_pick_mixin",
    "lib.app_window.commit_list",
    "lib.app_window.commit_ops_mixin",
    "lib.app_window.delegates",
    "lib.app_window.diff_mixin",
    "lib.app_window.help_dialog",
    "lib.app_window.helpers",
    "lib.app_window.init_mixin",
    "lib.app_window.main",
    "lib.app_window.menus_mixin",
    "lib.app_window.rebase_mixin",
    "lib.app_window.refine_mixin",
    "lib.app_window.rescan_mixin",
    "lib.app_window.reset_mixin",
    "lib.app_window.split_bulk_mixin",
    "lib.app_window.split_file_mixin",
    "lib.app_window.split_mixin",
    "lib.app_window.split_utils",
    "lib.app_window.squash_mixin",
    "lib.app_window.stash_mixin",
    "lib.app_window.toolbar_mixin",
    "lib.app_window.ui_mixin",
    "lib.app_window.undo_mixin",
    "lib.app_window.update_mixin",
    "lib.app_window.workers",
]


class TestImports(unittest.TestCase):
    pass


def _make_import_test(module_name):
    def test_func(self):
        try:
            mod = importlib.import_module(module_name)
            self.assertIsNotNone(mod)
        except NameError as e:
            self.fail(f"NameError importing {module_name}: {e}")
        except ImportError as e:
            msg = str(e)
            if ("No module named" in msg and module_name.split(".")[0] in msg):
                self.skipTest(f"Module {module_name} not available")
            if ".so" in msg or "cannot open shared object" in msg:
                self.skipTest(f"System library missing for {module_name}: {msg}")
            self.fail(f"ImportError importing {module_name}: {e}")

    test_func.__doc__ = f"Import {module_name}"
    return test_func


for mod_name in MODULES_TO_TEST:
    test_name = f"test_import_{mod_name.replace('.', '_')}"
    setattr(TestImports, test_name, _make_import_test(mod_name))


if __name__ == "__main__":
    unittest.main()
