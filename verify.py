#!/usr/bin/env python3
"""Verify all Python files for syntax errors, import issues, and indentation problems."""
import py_compile
import ast
import sys
import os

REPO = os.path.dirname(os.path.abspath(__file__))
ERRORS = []

def check_syntax(filepath):
    """Check Python syntax via py_compile."""
    try:
        py_compile.compile(filepath, doraise=True)
    except py_compile.PyCompileError as e:
        ERRORS.append(f"SYNTAX: {filepath}: {e}")

def check_ast(filepath):
    """Check AST parsing (catches indentation issues py_compile might miss)."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            ast.parse(f.read(), filepath)
    except SyntaxError as e:
        ERRORS.append(f"AST: {filepath}:{e.lineno}: {e.msg}")

def check_imports(filepath):
    """Check that referenced modules exist."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filepath)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split('.')[0]
                    if mod == 'lib':
                        # Check lib submodules exist
                        parts = alias.name.split('.')
                        path = os.path.join(REPO, *parts)
                        if not os.path.exists(path + '.py') and not os.path.isdir(path):
                            ERRORS.append(f"IMPORT: {filepath}:{node.lineno}: module '{alias.name}' not found")
            elif isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module.split('.')[0]
                if mod == 'lib':
                    parts = node.module.split('.')
                    path = os.path.join(REPO, *parts)
                    if not os.path.exists(path + '.py') and not os.path.isdir(path):
                        ERRORS.append(f"IMPORT: {filepath}:{node.lineno}: module '{node.module}' not found")
    except SyntaxError:
        pass  # Already caught by syntax check

# Find all Python files
count = 0
for root, dirs, files in os.walk(REPO):
    # Skip __pycache__, .git, venv
    dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', 'venv', '.venv', 'node_modules')]
    for f in files:
        if f.endswith('.py'):
            filepath = os.path.join(root, f)
            check_syntax(filepath)
            check_ast(filepath)
            check_imports(filepath)
            count += 1

if ERRORS:
    print(f"\n{len(ERRORS)} error(s) found in {count} files:\n")
    for e in ERRORS:
        print(f"  {e}")
    sys.exit(1)
else:
    print(f"All {count} Python files OK (syntax, AST, imports)")
    sys.exit(0)
