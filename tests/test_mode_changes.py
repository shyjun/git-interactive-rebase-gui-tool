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


if __name__ == "__main__":
    unittest.main()
