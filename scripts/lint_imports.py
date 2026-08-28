#!/usr/bin/env python3
"""AST-based linter that detects missing imports in Python files.

Scans all .py files under lib/ and reports:
  - Names used in function/method bodies that aren't imported
  - Focuses on CamelCase names (likely class/type references)
  - Also catches common builtins and module-level names

Exit code 0 = clean, 1 = issues found.
"""
import ast
import os
import sys
import glob

BUILTIN_NAMES = set(dir(__builtins__)) if isinstance(__builtins__, dict) else set(dir(__builtins__))
# Common names that don't need imports
KNOWN_GLOBALS = {
    "self", "cls", "super", "True", "False", "None",
    "__name__", "__file__", "__init__", "__all__",
    "print", "len", "range", "enumerate", "zip", "map", "filter",
    "isinstance", "hasattr", "getattr", "setattr", "delattr",
    "str", "int", "float", "bool", "list", "dict", "set", "tuple",
    "type", "object", "property", "staticmethod", "classmethod",
    "abs", "min", "max", "sum", "sorted", "reversed",
    "open", "os", "sys", "re", "json", "subprocess", "shutil",
    "glob", "tempfile", "shlex", "signal",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
    "RuntimeError", "AttributeError", "FileNotFoundError",
    "StopIteration", "NotImplementedError",
    "Any", "Optional", "Union", "List", "Dict", "Set", "Tuple",
}
KNOWN_GLOBALS |= BUILTIN_NAMES

# Names from common PySide6 modules that we expect to be imported
# If you see these used but not imported, it's a bug
PY_SIDE_NAMES = {
    "Q", "QApplication", "QAction", "QBoxLayout", "QCheckBox", "QColor",
    "QComboBox", "QDialog", "QDialogButtonBox", "QDir", "QDoubleSpinBox",
    "QFileDialog", "QFont", "QFontMetrics", "QFrame", "QGridLayout",
    "QGroupBox", "QHBoxLayout", "QHeaderView", "QIcon", "QKeySequence",
    "QLabel", "QLineEdit", "QMenu", "QMenuBar", "QMessageBox", "QPainter",
    "QPalette", "QPen", "QPixmap", "QPlainTextEdit", "QPushButton",
    "QScrollArea", "QScrollBar", "QSizePolicy", "QSlider", "QSpinBox",
    "QSplitter", "QShortcut", "QStackedWidget", "QStyle", "QStyleFactory",
    "QTabWidget", "QTextEdit", "QTimer", "QToolButton", "QToolTip",
    "QTreeWidget", "QTreeWidgetItem", "QVBoxLayout", "QWidget",
    "QMainWindow", "QListWidget", "QListWidgetItem",
    "QDesktopServices", "QUrl", "QTextCursor", "QTextCharFormat",
    "QTextFormat", "QTextBlock", "QTextDocument", "QSyntaxHighlighter",
    "QRegularExpression", "QRegularExpressionMatch", "QTextCursor",
    "QAbstractItemView", "QItemSelectionModel", "QModelIndex",
    "QProcess", "QSystemTrayIcon",
    "Qt", "QPoint", "QRect", "QSize", "QMargins",
    "Signal", "Slot", "QThread", "QMutex", "QWaitCondition",
    "QTimer", "QEventLoop",
    "QStyleOptionViewItem",
    "QHeaderView",
}


def check_file(filepath):
    """Check a single Python file for missing imports."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        return [(filepath, e.lineno or 0, f"SyntaxError: {e.msg}")]

    # Collect all imported names
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                imported.add(name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[-1])
            for alias in node.names:
                if alias.name == "*":
                    continue
                name = alias.asname or alias.name
                imported.add(name)

    # Collect module-level defined names (variables, functions, classes)
    module_level_names = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_level_names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            module_level_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_level_names.add(target.id)

    all_defined = imported | module_level_names | KNOWN_GLOBALS

    issues = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Collect local variables assigned in this function
            local_names = set()
            # Add function parameters
            for arg in node.args.args:
                local_names.add(arg.arg)
            for arg in node.args.posonlyargs:
                local_names.add(arg.arg)
            for arg in node.args.kwonlyargs:
                local_names.add(arg.arg)
            if node.args.vararg:
                local_names.add(node.args.vararg.arg)
            if node.args.kwarg:
                local_names.add(node.args.kwarg.arg)

            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name):
                            local_names.add(target.id)
                elif isinstance(child, ast.AugAssign) and isinstance(child.target, ast.Name):
                    local_names.add(child.target.id)
                elif isinstance(child, ast.For) and isinstance(child.target, ast.Name):
                    local_names.add(child.target.id)
                elif isinstance(child, (ast.With)):
                    for item in child.items:
                        if item.optional_vars and isinstance(item.optional_vars, ast.Name):
                            local_names.add(item.optional_vars.id)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child is not node:
                        continue

            func_defined = all_defined | local_names
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id not in func_defined:
                    name = child.id
                    if name[0].isupper() and len(name) > 1:
                        issues.append((
                            filepath, child.lineno,
                            f"NameError: '{name}' is not imported"
                        ))
    return issues


def main():
    lib_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lib")
    files = glob.glob(os.path.join(lib_dir, "**", "*.py"), recursive=True)
    files.sort()

    all_issues = []
    for filepath in files:
        issues = check_file(filepath)
        all_issues.extend(issues)

    if all_issues:
        print(f"\n{len(all_issues)} missing import(s) found:\n")
        for filepath, lineno, msg in all_issues:
            rel = os.path.relpath(filepath, os.path.dirname(lib_dir))
            print(f"  {rel}:{lineno}  {msg}")
        print()
        return 1

    print("All imports OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
