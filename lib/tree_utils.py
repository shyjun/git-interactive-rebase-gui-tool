"""Shared QTreeWidgetItem helpers for tree-wise file lists.

These are pure traversal functions with no application-specific coupling.
They operate on items whose data convention is:
    item.data(0, Qt.UserRole + 10) -> {"type": "folder"|"file", ...}
"""

from PySide6.QtCore import Qt


def set_tree_children_checked(item, checked):
    """Recursively set check state for all children of *item*."""
    for i in range(item.childCount()):
        child = item.child(i)
        child.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        child_data = child.data(0, Qt.UserRole + 10)
        if child_data and child_data["type"] == "folder":
            set_tree_children_checked(child, checked)


def update_folder_check_state(folder_item):
    """Update a folder's tri-state checkbox based on its children.

    Sets Qt.Checked / Qt.PartiallyChecked / Qt.Unchecked as appropriate.
    Recurses into child folders first so their state is up-to-date.
    """
    if folder_item.childCount() == 0:
        return
    all_checked = True
    has_checked = False
    for i in range(folder_item.childCount()):
        child = folder_item.child(i)
        child_data = child.data(0, Qt.UserRole + 10)
        if child_data and child_data["type"] == "folder":
            update_folder_check_state(child)
        state = child.checkState(0)
        if state == Qt.Checked:
            has_checked = True
        elif state == Qt.PartiallyChecked:
            has_checked = True
            all_checked = False
        else:
            all_checked = False
    if all_checked:
        folder_item.setCheckState(0, Qt.Checked)
    elif has_checked:
        folder_item.setCheckState(0, Qt.PartiallyChecked)
    else:
        folder_item.setCheckState(0, Qt.Unchecked)
