import os
import subprocess


def get_staged_files(repo_path):
    """Returns list of staged files (excluding submodules)."""
    try:
        cmd = ["git", "diff", "--cached", "--name-only", "--ignore-submodules=all"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True,
                                encoding='utf-8', errors='replace')
        return [f for f in result.stdout.strip().split('\n') if f]
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"[git_helpers] get_staged_files: git diff --cached failed: {err}")
        return []


def has_uncommitted_changes(repo_path):
    """Returns True if there are uncommitted changes in the repository."""
    try:
        # Check excluding submodules to avoid recursive deep checks
        cmd_ignored = ["git", "status", "--porcelain", "--untracked-files=no", "--ignore-submodules=all"]
        result = subprocess.run(cmd_ignored, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return bool(result.stdout.strip())
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"[git_helpers] has_uncommitted_changes: git status failed: {err}")
        return True

def cherry_pick_in_progress(repo_path):
    """Returns True if a cherry-pick is pending (CHERRY_PICK_HEAD exists)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "CHERRY_PICK_HEAD"],
            cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        return result.returncode == 0
    except Exception:
        return False

def rebase_in_progress(repo_path):
    """Returns True if a rebase is pending, False if it is definitively not
    pending, or None if the repository's rebase state could not be determined.

    Uses ``git rev-parse --git-path`` so it works in linked worktrees too. The
    returned path may be repo-relative, so it is resolved against *repo_path*
    before checking. A failed git query (nonzero exit or empty path - including
    a non-repository or invalid path) and an exception are indeterminate (None).
    None must never be treated as 'no rebase exists', since that would mask a
    failure to detect a pending rebase."""
    try:
        for state in ("rebase-merge", "rebase-apply"):
            result = subprocess.run(
                ["git", "rev-parse", "--git-path", state],
                cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace'
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None
            state_dir = result.stdout.strip()
            if not os.path.isabs(state_dir):
                state_dir = os.path.join(repo_path, state_dir)
            if os.path.isdir(state_dir):
                return True
    except Exception:
        return None
    return False

def classify_cherry_pick_failure(repo_path, stderr):
    """Classifies why a cherry-pick failed, before it is aborted.

    Uses the index/working tree state (not stderr text) so it is robust across
    git versions. Returns (kind, detail) where kind is one of
    'conflict', 'empty', or 'other'.
    """
    try:
        unmerged_result = subprocess.run(
            ["git", "ls-files", "--unmerged"], cwd=repo_path,
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        unmerged = unmerged_result.stdout.strip().split('\n') if unmerged_result.stdout.strip() else []
    except Exception:
        unmerged = []
    if unmerged:
        paths = []
        for line in unmerged:
            if "\t" in line:
                path = line.split("\t", 1)[-1]
                if path not in paths:
                    paths.append(path)
        return "conflict", "\n".join(paths) or "conflicting files"

    try:
        staged_result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=repo_path,
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        no_staged = staged_result.returncode == 0
    except Exception:
        no_staged = False
    if no_staged:
        return "empty", ""

    if stderr:
        for line in stderr.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("hint:"):
                return "other", stripped
    return "other", "unknown error"

def classify_tracked_changes(repo_path):
    """Returns (has_staged, has_unstaged) for tracked changes.

    Untracked files are ignored (consistent with the rest of the app).
    Porcelain XY columns: X is the index (staged) state, Y is the worktree
    (unstaged) state.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no", "--ignore-submodules=all"],
            cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace'
        )
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"[git_helpers] classify_tracked_changes: git status failed: {err}")
        return True, True

    has_staged = False
    has_unstaged = False
    for line in result.stdout.split('\n'):
        if len(line) < 2:
            continue
        x = line[0]
        y = line[1]
        if x not in (' ', '?'):
            has_staged = True
        if y not in (' ', '?'):
            has_unstaged = True
        if has_staged and has_unstaged:
            break
    return has_staged, has_unstaged

def get_unstaged_files(repo_path, ignore_submodules=False):
    """Returns a list of file paths that have unstaged changes."""
    try:
        cmd = ["git", "status", "--porcelain", "--untracked-files=no"]
        if ignore_submodules:
            cmd.append("--ignore-submodules=all")

        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        files = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip(): continue
            # Format: XY filename (X=index, Y=worktree)
            # We care about unstaged changes (Y != ' ' and Y != '?')
            # But porcelain v1 is a bit cryptic. Simplified check:
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                filepath = parts[1]
                # git status --porcelain quotes paths with special chars
                if filepath.startswith('"') and filepath.endswith('"'):
                    filepath = filepath[1:-1]
                files.append(filepath)
        return files
    except Exception as exc:
        print(f"[git_helpers] get_unstaged_files: git status failed: {exc}")
        return []


def get_untracked_files(repo_path, ignore_submodules=False):
    """Returns a list of untracked file paths."""
    try:
        cmd = ["git", "status", "--porcelain", "--untracked-files=all"]
        if ignore_submodules:
            cmd.append("--ignore-submodules=all")

        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        files = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip(): continue
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[0] == '??':
                filepath = parts[1]
                if filepath.startswith('"') and filepath.endswith('"'):
                    filepath = filepath[1:-1]
                files.append(filepath)
        return files
    except Exception as exc:
        print(f"[git_helpers] get_untracked_files: git status failed: {exc}")
        return []
