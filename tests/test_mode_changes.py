import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.git_helpers import parse_commit_mode_changes, format_file_mode, build_file_tree


class TestModeChanges(unittest.TestCase):

    def test_format_file_mode(self):
        self.assertEqual(format_file_mode("100755"), "755")
        self.assertEqual(format_file_mode("100644"), "644")
        self.assertEqual(format_file_mode("120000"), "symlink")
        self.assertEqual(format_file_mode("160000"), "submodule")
        self.assertEqual(format_file_mode(""), "")

    def test_parse_commit_mode_changes(self):
        diff_sample = """diff --git a/script.sh b/script.sh
old mode 100644
new mode 100755
index 123456..789abc
--- a/script.sh
+++ b/script.sh
@@ -1 +1 @@
-echo "hello"
+echo "hello world"
"""
        mode_map = parse_commit_mode_changes(diff_sample)
        self.assertIn("script.sh", mode_map)
        self.assertEqual(mode_map["script.sh"], ("100644", "100755"))

    def test_build_file_tree_with_mode_changes(self):
        files = [('M', 'dir/script.sh', 'dir/script.sh')]
        file_stats = {'dir/script.sh': (0, 0, 0, 0, '100644', '100755')}
        tree = build_file_tree(files, file_stats)
        dir_node = tree["children"]["dir"]
        script_node = dir_node["children"]["script.sh"]
        self.assertEqual(script_node.get("old_mode"), "100644")
        self.assertEqual(script_node.get("new_mode"), "100755")

    def test_format_tree_node_stats_binary_mode_change(self):
        from lib.git_helpers.commits import format_tree_node_stats
        node = {
            "added": 0,
            "deleted": 0,
            "old_size": 138240,
            "new_size": 138240,
            "old_mode": "100755",
            "new_mode": "100644",
        }
        res = format_tree_node_stats(node)
        self.assertIn("135.0 KB", res)
        self.assertIn("mode: 755 -> 644", res)

    def test_branch_diff_dialog_enriches_mode_map(self):
        diff_text = """diff --git a/ls b/ls
old mode 100755
new mode 100644
"""
        from lib.git_helpers import parse_commit_mode_changes
        mode_map = parse_commit_mode_changes(diff_text)
        self.assertEqual(mode_map["ls"], ("100755", "100644"))


if __name__ == "__main__":
    unittest.main()
