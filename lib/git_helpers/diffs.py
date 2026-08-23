import re
import subprocess

from .core import _git_capture, _pad_diff_separators


def get_merge_base(repo_path, ref):
    """Returns the merge-base of HEAD with *ref* (e.g. 'origin/main').

    Returns None when the branches share no common ancestor. A genuine git
    failure (anything but the 'no common ancestor' exit code 1) raises an
    Exception carrying git's stderr."""
    try:
        cmd = ["git", "merge-base", "HEAD", ref]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        sha = result.stdout.strip()
        return sha if sha else None
    except subprocess.CalledProcessError as e:
        if e.returncode == 1:
            return None
        raise Exception(f"Failed to find merge-base: {e.stderr}")


def get_diff_between(repo_path, start_sha, end_sha):
    """Fetches the combined diff of all changes between *start_sha* and *end_sha*."""
    try:
        cmd = ["git", "diff", start_sha, end_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch branch diff: {e.stderr}")


def get_files_between(repo_path, start_sha, end_sha):
    """Returns the list of file paths changed between *start_sha* and *end_sha*."""
    try:
        cmd = ["git", "diff", "--name-only", start_sha, end_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return [f for f in result.stdout.strip().split('\n') if f.strip()]
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to list changed files: {e.stderr}")


def get_file_diff_between(repo_path, start_sha, end_sha, filepath):
    """Returns the diff for a single file between *start_sha* and *end_sha*."""
    return _pad_diff_separators(
        _git_capture(repo_path, ["git", "diff", start_sha, end_sha, "--", filepath],
                     "Failed to get file diff"))


def get_file_stats_between(repo_path, start_sha, end_sha):
    """Returns a dict mapping filepath -> (added_lines, deleted_lines) between *start_sha* and *end_sha*."""
    try:
        cmd = ["git", "diff", "--numstat", start_sha, end_sha]
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
        print(f"[git_helpers] get_file_stats_between: git diff --numstat failed between {start_sha} and {end_sha}: {err}")
        return {}


def get_unstaged_diff(repo_path, ignore_submodules=False):
    """Returns the combined diff of all unstaged (worktree vs index) changes."""
    try:
        cmd = ["git", "diff"]
        if ignore_submodules:
            cmd.append("--ignore-submodules=all")
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        diff_text = result.stdout
        # Inject separator padding
        diff_text = re.sub(r'(\n)(diff --git )', r'\1\n\2', diff_text)
        return diff_text
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch unstaged diff: {e.stderr}")


def get_unstaged_file_stats(repo_path, ignore_submodules=False):
    """Returns a dict mapping filepath -> (added_lines, deleted_lines) for unstaged changes."""
    try:
        cmd = ["git", "diff", "--numstat"]
        if ignore_submodules:
            cmd.append("--ignore-submodules=all")
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
        print(f"[git_helpers] get_unstaged_file_stats: git diff --numstat failed: {err}")
        return {}


def get_unstaged_file_diff(repo_path, filepath):
    """Returns the diff for a single file's unstaged changes."""
    return _pad_diff_separators(
        _git_capture(repo_path, ["git", "diff", "--", filepath],
                     "Failed to get unstaged file diff"))
