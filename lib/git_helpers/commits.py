import re
import subprocess

from .core import _git_capture, _pad_diff_separators


def format_tree_node_stats(node):
    """Format stats text for a tree node (folder or file).

    Returns a string like '+5 / -3' for text files or
    'old: 1.2 KB, new: 1.5 KB' for binary files.
    Returns '' if no stats to display.
    """
    added = node.get("added", 0)
    deleted = node.get("deleted", 0)
    old_size = node.get("old_size", 0)
    new_size = node.get("new_size", 0)
    is_binary = (old_size != 0 or new_size != 0) and added == 0 and deleted == 0

    if is_binary:
        if old_size >= 0 and new_size >= 0 and old_size != new_size:
            return f"size: {_format_bytes(old_size)} -> {_format_bytes(new_size)}"
        elif new_size >= 0:
            return f"size: {_format_bytes(new_size)}"
        elif old_size >= 0:
            return f"size: {_format_bytes(old_size)}"
        return ""
    elif added or deleted:
        stats_parts = []
        if added:
            stats_parts.append(f"+{added}")
        if deleted:
            stats_parts.append(f"-{deleted}")
        return " / ".join(stats_parts)
    return ""


def _format_bytes(size_bytes):
    """Format a byte count into a human-readable string."""
    if size_bytes < 0:
        return "unknown"
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def get_commit_diff(repo_path, commit_sha):
    """Fetches the diff for a specific commit."""
    try:
        cmd = ["git", "show", commit_sha, "--format="]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')

        # Inject a newline before every 'diff --git' block (except the very first if it's at start)
        diff_text = result.stdout
        # Inject a newline before every 'diff --git' block, but NOT if it's at the absolute start
        # This prevents an extra empty line at the top of the diff viewer.
        diff_text = re.sub(r'(\n)(diff --git )', r'\1\n\2', diff_text)

        return diff_text
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch diff: {e.stderr}")

def get_full_commit_message(repo_path, commit_sha):
    """Fetches the full (multi-line) commit message."""
    try:
        cmd = ["git", "log", "-1", "--format=%B", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch commit message: {e.stderr}")

def get_commit_subject(repo_path, commit_sha):
    """Fetches the single-line subject of a commit."""
    try:
        cmd = ["git", "log", "-1", "--format=%s", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch commit subject: {e.stderr}")

def get_commit_metadata_and_message(repo_path, commit_sha):
    """Fetches both metadata and message in a single git log call for performance."""
    try:
        cmd = ["git", "log", "-1", "--format=%an <%ae>, %ad%n%n%B", "--date=format:%d %b %Y %H:%M", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        parts = result.stdout.strip().split('\n\n', 1)
        meta = parts[0]
        msg = parts[1] if len(parts) > 1 else ""
        return meta, msg.strip()
    except Exception as exc:
        print(f"[git_helpers] get_commit_metadata_and_message: git log failed for {commit_sha}: {exc}")
        return "Unknown author", ""

def get_commit_metadata(repo_path, commit_sha):
    """Fetches author name, email, and date for a commit."""
    try:
        # %an = author name, %ae = author email, %ad = author date (human-readable)
        cmd = ["git", "log", "-1", "--format=%an <%ae>, %ad", "--date=format:%d %b %Y %H:%M", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "Unknown author"

def get_commit_files(repo_path, commit_sha):
    """Returns a list of file paths changed by a given commit."""
    try:
        cmd = ["git", "diff-tree", "--no-commit-id", "--root", "-r", "--name-only", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return [f for f in result.stdout.strip().split('\n') if f.strip()]
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to list commit files: {e.stderr}")

def get_commit_file_stats(repo_path, commit_sha):
    """Returns a dict mapping filepath -> (added_lines, deleted_lines, old_size, new_size).

    For text files: old_size and new_size are 0.
    For binary files: added and deleted are 0, old_size/new_size are byte counts (-1 if unavailable).
    Uses git show --numstat. Binary files have '-' for added/deleted.
    """
    try:
        cmd = ["git", "show", "--numstat", "--format=", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        stats = {}
        binary_files = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split('\t', 2)
            if len(parts) == 3:
                added_str, deleted_str, filepath = parts
                filepath = filepath.strip()
                try:
                    added = int(added_str)
                    deleted = int(deleted_str)
                    stats[filepath] = (added, deleted, 0, 0)
                except ValueError:
                    # Binary file (numstat shows '-')
                    binary_files.append(filepath)
        # Get file sizes for binary files
        if binary_files:
            _fill_binary_sizes(repo_path, commit_sha, binary_files, stats, is_commit=True)
        return stats
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"[git_helpers] get_commit_file_stats: git show --numstat failed for {commit_sha}: {err}")
        return {}


def _fill_binary_sizes(repo_path, sha, binary_files, stats, is_commit=True):
    """Fill in old_size/new_size for binary files using git ls-tree."""
    for filepath in binary_files:
        new_size = _get_file_size(repo_path, sha, filepath)
        if is_commit:
            old_size = _get_file_size(repo_path, f"{sha}^", filepath)
        else:
            old_size = _get_file_size(repo_path, sha, filepath)
        stats[filepath] = (0, 0, old_size, new_size)


def _get_file_size(repo_path, ref, filepath):
    """Get file size in bytes at a given ref. Returns -1 if not found."""
    try:
        result = subprocess.run(
            ["git", "cat-file", "-s", f"{ref}:{filepath}"],
            cwd=repo_path, capture_output=True, text=True,
            encoding='utf-8', errors='replace')
        if result.returncode == 0:
            return int(result.stdout.strip())
    except (ValueError, subprocess.SubprocessError):
        pass
    return -1


def get_commit_files_with_status(repo_path, commit_sha, stash=False):
    """Returns a list of (status, path1, path2) tuples for files changed by a commit.
    status is a single letter: A (added), D (deleted), M (modified), R (renamed),
    T (type changed), C (copied), etc. For renames path1 = old path, path2 = new path;
    otherwise path2 is empty. Uses -M so renames are detected and combined into one entry.

    When stash=True the commit is treated as a stash: it is diffed against its
    first parent (``<sha>^1``) instead of root, since a stash is a merge commit
    and a plain ``diff-tree`` would return nothing."""
    try:
        if stash:
            cmd = ["git", "diff-tree", "--no-commit-id", "-r", "-M", "--name-status", f"{commit_sha}^1", commit_sha]
        else:
            cmd = ["git", "diff-tree", "--no-commit-id", "--root", "-r", "-M", "--name-status", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        entries = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split('\t')
            code = parts[0][0]
            if code == 'R' and len(parts) >= 3:
                entries.append(('R', parts[1], parts[2]))
            elif len(parts) >= 2:
                entries.append((code, parts[1], ''))
        return entries
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to list commit files: {e.stderr}")

def get_rename_diff_in_commit(repo_path, commit_sha, old_path, new_path):
    """Returns the diff section for a renamed file within a commit.
    Extracts the relevant section from the full commit diff so the rename
    headers ('similarity index', 'rename from'/'rename to') are preserved;
    a path-filtered diff would force git to show an add/delete instead."""
    try:
        cmd = ["git", "show", "--format=", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        diff_text = result.stdout
        chunks = re.split(r'(?m)^(?=diff --git )', diff_text)
        for chunk in chunks:
            if f"rename from {old_path}" in chunk and f"rename to {new_path}" in chunk:
                chunk = re.sub(r'(\n)(diff --git )', r'\1\n\2', chunk)
                return chunk
        for chunk in chunks:
            if f"a/{old_path} b/{new_path}" in chunk:
                chunk = re.sub(r'(\n)(diff --git )', r'\1\n\2', chunk)
                return chunk
        return ""
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get rename diff: {e.stderr}")

def get_file_diff_only_in_commit(repo_path, commit_sha, filepath):
    """Returns the diff for a single file within a commit, excluding the commit message header."""
    return _pad_diff_separators(
        _git_capture(repo_path, ["git", "show", "--format=", commit_sha, "--", filepath],
                     "Failed to get file diff"))


def build_file_tree(files, file_stats):
    """Build a nested tree dict from flat file entries for the tree-wise diff tab.

    Args:
        files: list of (status, path1, path2) tuples from get_commit_files_with_status.
        file_stats: dict mapping filepath -> (added, deleted, old_size, new_size).

    Returns a dict where each key is a name (folder or file basename) and each value is:
        {"children": {}, "added": int, "deleted": int, "entries": [],
         "old_size": int, "new_size": int}
    Folder nodes have children; leaf file nodes have entries.
    """
    root = {"children": {}, "added": 0, "deleted": 0, "entries": [], "old_size": 0, "new_size": 0}

    for entry in files:
        status, path1, path2 = entry
        # For renames, use the new path for tree placement
        display_path = path2 if status == 'R' and path2 else path1
        parts = display_path.split('/')
        stats = file_stats.get(path1, (0, 0, 0, 0))
        added, deleted = stats[0], stats[1]
        old_size, new_size = stats[2] if len(stats) > 2 else 0, stats[3] if len(stats) > 3 else 0
        is_binary = (old_size != 0 or new_size != 0) and added == 0 and deleted == 0

        node = root
        for part in parts[:-1]:
            if part not in node["children"]:
                node["children"][part] = {"children": {}, "added": 0, "deleted": 0, "entries": [], "old_size": 0, "new_size": 0}
            node["children"][part]["added"] += added
            node["children"][part]["deleted"] += deleted
            node = node["children"][part]

        # Leaf file node
        basename = parts[-1]
        if basename not in node["children"]:
            node["children"][basename] = {"children": {}, "added": 0, "deleted": 0, "entries": [], "old_size": 0, "new_size": 0}
        node["children"][basename]["added"] += added
        node["children"][basename]["deleted"] += deleted
        node["children"][basename]["entries"].append(entry)
        if is_binary:
            node["children"][basename]["old_size"] = old_size
            node["children"][basename]["new_size"] = new_size
        # Propagate binary sizes up to folders
        if is_binary:
            node["old_size"] = node.get("old_size", 0) + old_size
            node["new_size"] = node.get("new_size", 0) + new_size
            root["old_size"] = root.get("old_size", 0) + old_size
            root["new_size"] = root.get("new_size", 0) + new_size

        # Also add stats to root
        root["added"] += added
        root["deleted"] += deleted

    return root
