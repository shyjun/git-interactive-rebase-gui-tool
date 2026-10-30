import os
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


def _gitmodule_paths(repo_path):
    """Paths declared in .gitmodules. Empty set when the file is missing or
    unreadable (e.g. embedded repos added via plain `git add`)."""
    try:
        result = subprocess.run(
            ["git", "config", "--file", ".gitmodules", "--get-regexp",
             r"^submodule\..*\.path$"],
            cwd=repo_path, capture_output=True, text=True,
            encoding='utf-8', errors='replace')
        if result.returncode != 0:
            return set()
        return {line.split(None, 1)[1].strip()
                for line in result.stdout.splitlines() if line.strip()}
    except (subprocess.CalledProcessError, OSError):
        return set()


def _current_head(path):
    """HEAD SHA of the nested repo at `path`, or None if absent/broken."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=path, capture_output=True, text=True, check=True,
            encoding='utf-8', errors='replace')
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, OSError):
        return None


def _conflict_paths(repo_path):
    """Paths git reports with the 'U' (conflict) prefix. Empty on failure —
    `git submodule status` fatals for embedded gitlinks with no .gitmodules
    mapping, and that must not hide the rest of the list."""
    try:
        result = subprocess.run(
            ["git", "submodule", "status"],
            cwd=repo_path, capture_output=True, text=True, check=True,
            encoding='utf-8', errors='replace')
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        _log(f"[git_helpers] _conflict_paths: git submodule status failed: {err}")
        return set()
    paths = set()
    for line in result.stdout.splitlines():
        if len(line) >= 42 and line[0] == 'U':
            paths.add(line[42:].split(' (')[0].strip())
    return paths


def list_submodules(repo_path):
    """Returns a list of dicts describing each gitlink (mode 160000) recorded
    in the index:

        {"path", "record_sha", "current_sha", "status", "embedded"}

    Enumeration is driven by the index gitlinks (NOT `git submodule status`),
    so embedded repos added via plain `git add` — gitlinks with no .gitmodules
    mapping — are included; `git submodule status` fatals on those. `embedded`
    is True for such unmapped paths. status is one of the STATUS_* constants:
    uninitialized (no nested repo), conflict, pointer (HEAD differs from the
    recorded gitlink), dirty (modified content with a matching pointer), or
    clean."""
    gitlinks = _index_gitlinks(repo_path)
    if not gitlinks:
        return []
    mapped = _gitmodule_paths(repo_path)
    conflicts = _conflict_paths(repo_path)

    subs = []
    for path, record_sha in gitlinks.items():
        current_sha = _current_head(os.path.join(repo_path, path))
        if current_sha is None:
            status = STATUS_UNINITIALIZED
        elif path in conflicts:
            status = STATUS_CONFLICT
        elif current_sha != record_sha:
            status = STATUS_POINTER
        else:
            status = STATUS_CLEAN
        subs.append({
            "path": path,
            "record_sha": record_sha,
            "current_sha": current_sha,
            "status": status,
            "embedded": path not in mapped,
        })

    # A submodule can be pointer-clean but have dirty content; git status
    # flags it, but the porcelain line is identical to a pointer change, so
    # only check the pointer-clean ones.
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
    """Moves each submodule back to the SHA recorded in the superproject.

    Mapped submodules use `git submodule update -- <path>`. Embedded gitlinks
    (no .gitmodules mapping) can't go through the submodule machinery, so they
    fall back to checking out the recorded SHA inside the nested repo
    (`git -C <path> checkout <record_sha>`) — the same end state. Fails (with
    git's message) if there are local modifications that would be overwritten
    or the recorded commit isn't available locally.

    Returns (True, "") or (False, detail)."""
    if not paths:
        return False, "No submodules selected."
    mapped = _gitmodule_paths(repo_path)
    gitlinks = _index_gitlinks(repo_path)
    errors = []
    for path in paths:
        if path in mapped:
            try:
                subprocess.run(["git", "submodule", "update", "--", path],
                               cwd=repo_path, check=True, capture_output=True)
            except subprocess.CalledProcessError as exc:
                err = exc.stderr.decode('utf-8', errors='replace') if exc.stderr else str(exc)
                errors.append(f"{path}: {err.strip()}")
        elif path in gitlinks:
            try:
                subprocess.run(["git", "checkout", "-q", gitlinks[path]],
                               cwd=os.path.join(repo_path, path),
                               check=True, capture_output=True)
            except subprocess.CalledProcessError as exc:
                err = exc.stderr.decode('utf-8', errors='replace') if exc.stderr else str(exc)
                errors.append(f"{path}: {err.strip()}")
        else:
            errors.append(f"{path}: not a gitlink recorded in the index")
    if errors:
        return False, "\n".join(errors)
    return True, ""
