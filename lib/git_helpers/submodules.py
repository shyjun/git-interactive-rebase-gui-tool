import subprocess
from lib.logger import _log

# Submodule states reported by list_submodules()
STATUS_CLEAN = "clean"
STATUS_POINTER = "pointer"        # submodule HEAD differs from the recorded gitlink
STATUS_DIRTY = "dirty"            # modified content inside the submodule
STATUS_UNINITIALIZED = "uninitialized"
STATUS_CONFLICT = "conflict"


def _index_gitlinks(repo_path):
    """Maps submodule path -> gitlink SHA recorded in the index (mode 160000)."""
    links = {}
    try:
        result = subprocess.run(
            ["git", "ls-files", "-s"],
            cwd=repo_path, capture_output=True, text=True, check=True,
            encoding='utf-8', errors='replace')
        for line in result.stdout.splitlines():
            # format: "<mode> <sha> <stage>\t<path>"
            meta, _, path = line.partition('\t')
            parts = meta.split()
            if len(parts) == 3 and parts[0] == "160000":
                links[path] = parts[1]
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        _log(f"[git_helpers] _index_gitlinks: git ls-files failed: {err}")
    return links


def list_submodules(repo_path):
    """Returns a list of dicts describing each configured submodule:

        {"path", "record_sha", "current_sha", "status"}

    where status is one of the STATUS_* constants. Uses `git submodule status`
    (prefix ' ' = clean, '+' = current HEAD differs from the recorded gitlink,
    '-' = uninitialized, 'U' = conflict), the index gitlink for the recorded
    SHA, and a per-path `git status` to flag dirty content."""
    try:
        result = subprocess.run(
            ["git", "submodule", "status"],
            cwd=repo_path, capture_output=True, text=True, check=True,
            encoding='utf-8', errors='replace')
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        _log(f"[git_helpers] list_submodules: git submodule status failed: {err}")
        return []

    gitlinks = _index_gitlinks(repo_path)

    subs = []
    for line in result.stdout.splitlines():
        if len(line) < 42:
            continue
        prefix, current_sha = line[0], line[1:41]
        path = line[42:].split(' (')[0].strip()
        record_sha = gitlinks.get(path, current_sha)
        if prefix == '-':
            status = STATUS_UNINITIALIZED
        elif prefix == 'U':
            status = STATUS_CONFLICT
        elif prefix == '+':
            status = STATUS_POINTER
        else:
            status = STATUS_CLEAN
        subs.append({
            "path": path,
            "record_sha": record_sha,
            "current_sha": None if prefix == '-' else current_sha,
            "status": status,
        })

    # A submodule can be pointer-clean but have dirty content; git submodule
    # status doesn't report that, so check git status for the remaining ones.
    for sub in subs:
        if sub["status"] != STATUS_CLEAN:
            continue
        try:
            st = subprocess.run(
                ["git", "status", "--porcelain", "--", sub["path"]],
                cwd=repo_path, capture_output=True, text=True, check=True,
                encoding='utf-8', errors='replace')
            if st.stdout.strip():
                sub["status"] = STATUS_DIRTY
        except subprocess.CalledProcessError:
            pass
    return subs


def has_submodule_changes(repo_path):
    """True if any submodule has a pointer change, dirty content, or is
    uninitialized/conflicted. Used for informational notices."""
    return any(s["status"] != STATUS_CLEAN for s in list_submodules(repo_path))


def stage_submodule_pointers(repo_path, paths):
    """Stages the gitlink pointer for the given submodule paths (git add --).
    Returns (True, "") on success or (False, detail)."""
    if not paths:
        return False, "No submodules selected."
    try:
        subprocess.run(["git", "add", "--"] + list(paths), cwd=repo_path,
                       check=True, capture_output=True)
        return True, ""
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.decode('utf-8', errors='replace') if exc.stderr else str(exc)
        return False, err


def commit_submodule_pointers(repo_path, paths, message):
    """Commits the pointer change of the given submodule paths as a new commit
    via `git commit --only -- <paths>`. Returns (True, "") or (False, detail)."""
    if not paths:
        return False, "No submodules selected."
    try:
        subprocess.run(
            ["git", "commit", "--only", "-m", message, "--"] + list(paths),
            cwd=repo_path, check=True, capture_output=True)
        return True, ""
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.decode('utf-8', errors='replace') if exc.stderr else str(exc)
        return False, err


def discard_submodule_changes(repo_path, paths):
    """Moves each submodule back to the SHA recorded in the superproject via
    `git submodule update -- <paths>`. Fails (with git's message) if there are
    local modifications inside the submodule that would be overwritten.
    Returns (True, "") or (False, detail)."""
    if not paths:
        return False, "No submodules selected."
    try:
        subprocess.run(
            ["git", "submodule", "update", "--"] + list(paths),
            cwd=repo_path, check=True, capture_output=True)
        return True, ""
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.decode('utf-8', errors='replace') if exc.stderr else str(exc)
        return False, err
