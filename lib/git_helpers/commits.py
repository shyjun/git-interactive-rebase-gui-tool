import re
import subprocess

from .core import _git_capture, _pad_diff_separators


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
    except subprocess.CalledProcessError as e:
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
    """Returns a dict mapping filepath -> (added_lines, deleted_lines) for a commit.
    Uses git show --numstat. Binary files are mapped to (0, 0)."""
    try:
        cmd = ["git", "show", "--numstat", "--format=", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        stats = {}
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split('\t', 2)
            if len(parts) == 3:
                added_str, deleted_str, filepath = parts
                try:
                    added = int(added_str)
                    deleted = int(deleted_str)
                except ValueError:
                    added, deleted = 0, 0  # binary file
                stats[filepath.strip()] = (added, deleted)
        return stats
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"[git_helpers] get_commit_file_stats: git show --numstat failed for {commit_sha}: {err}")
        return {}


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
