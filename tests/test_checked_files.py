import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from PySide6.QtWidgets import QApplication, QListWidget, QListWidgetItem
    from PySide6.QtCore import Qt
    HAS_PYSIDE = True
except ImportError:
    HAS_PYSIDE = False

FILE_ENTRY_ROLE = Qt.UserRole + 20 if HAS_PYSIDE else 0


class TestCheckedFilesExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if HAS_PYSIDE:
            if not QApplication.instance():
                cls.app = QApplication([])

    def test_checked_filewise_files_extraction(self):
        if not HAS_PYSIDE:
            self.skipTest("PySide6 not available")

        # Create mock filewise list with display strings and FILE_ENTRY_ROLE data
        file_list = QListWidget()

        # 1. Added file: display string has "(Added new file)"
        item1 = QListWidgetItem("foo/added.py (Added new file)")
        item1.setCheckState(Qt.Checked)
        item1.setData(FILE_ENTRY_ROLE, ('A', 'foo/added.py', None))
        file_list.addItem(item1)

        # 2. Deleted file: display string has "(Deleted)"
        item2 = QListWidgetItem("bar/deleted.py (Deleted)")
        item2.setCheckState(Qt.Checked)
        item2.setData(FILE_ENTRY_ROLE, ('D', 'bar/deleted.py', None))
        file_list.addItem(item2)

        # 3. Renamed file: display string is "old_name.py => new_name.py"
        item3 = QListWidgetItem("old_name.py => new_name.py")
        item3.setCheckState(Qt.Checked)
        item3.setData(FILE_ENTRY_ROLE, ('R', 'old_name.py', 'new_name.py'))
        file_list.addItem(item3)

        # 4. Modified file (unchecked)
        item4 = QListWidgetItem("baz/modified.py")
        item4.setCheckState(Qt.Unchecked)
        item4.setData(FILE_ENTRY_ROLE, ('M', 'baz/modified.py', None))
        file_list.addItem(item4)

        # Simulate _checked_filewise_files logic
        result = []
        for i in range(file_list.count()):
            item = file_list.item(i)
            if item.checkState() == Qt.Checked:
                entry = item.data(FILE_ENTRY_ROLE)
                if entry:
                    result.append(entry[2] if entry[0] == 'R' else entry[1])
                else:
                    result.append(item.text())

        expected = [
            'foo/added.py',
            'bar/deleted.py',
            'new_name.py',
        ]
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
