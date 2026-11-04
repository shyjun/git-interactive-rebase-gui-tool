import os
import shutil
import subprocess

from lib.logger import _log


def _normalize_rel(path):
    """Normalizes a user-entered repo-relative path: strips whitespace, turns
    backslashes into '/', collapses duplicate slashes, drops a leading './'
    and any trailing '/'."""
    p = (path or "").strip().replace("\\", "/").strip("/")
    while "//" in p:
        p = p.replace("//", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def rename_move_path(repo_path, src_rel, dst_rel):
    """Validates and performs a working-tree rename/move of *src_rel* to
    *dst_rel* (both repo-relative, '/'-separated).

    Guards: neither path may be the repository root or live under .git/,
    both must resolve inside the repository, source must exist, destination
    must not already exist (case-only renames are allowed), and a folder may
    not be moved into itself. Missing destination parent directories are
    created; folders are moved recursively.

    Returns (True, "") on success or (False, detail) with a user-readable
    reason. On success *detail* is "src -> dst" with normalized paths."""
    src = _normalize_rel(src_rel)
    dst = _normalize_rel(dst_rel)
    if not src or not dst:
        return False, "Please provide both a source and a destination path."
    if src == dst:
        return False, "Source and destination are the same path."

    root = os.path.realpath(repo_path)
    src_abs = os.path.realpath(os.path.join(repo_path, src))
    dst_abs = os.path.realpath(os.path.join(repo_path, dst))
    if src_abs == root or dst_abs == root:
        return False, "Cannot rename/move the repository root itself."
    if not (src_abs.startswith(root + os.sep) and dst_abs.startswith(root + os.sep)):
        return False, "Both paths must be inside the repository."
    if ".git" in src.split("/") or ".git" in dst.split("/"):
        return False, "Paths under .git/ cannot be renamed/moved."

    # Case-only rename (Foo.txt -> foo.txt): allowed even though the
    # destination "exists" on case-insensitive filesystems.
    case_only = (os.path.normcase(src_abs) == os.path.normcase(dst_abs)
                 and src_abs != dst_abs)
    if not os.path.exists(src_abs):
        return False, f"Source does not exist:\n{src}"
    if os.path.exists(dst_abs) and not case_only:
        return False, f"Destination already exists:\n{dst}"
    if not case_only and dst_abs.startswith(src_abs + os.sep):
        return False, "Cannot move a folder into itself."

    try:
        parent = os.path.dirname(dst_abs)
        if parent:
            os.makedirs(parent, exist_ok=True)
        try:
            os.rename(src_abs, dst_abs)
        except OSError:
            # Different filesystem: fall back to copy+remove.
            shutil.move(src_abs, dst_abs)
    except OSError as e:
        _log(f"rename/move failed: {src} -> {dst}: {e}")
        return False, f"Could not rename/move:\n{e}"
    _log(f"Renamed/moved: {src} -> {dst}")
    return True, f"{src} -> {dst}"


def path_is_dirty(repo_path, rel_path):
    """True when *rel_path* carries uncommitted changes (staged,
    unstaged, or untracked content) — i.e. `git rm` would refuse it
    without -f."""
    rel = _normalize_rel(rel_path)
    if not rel:
        return False
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "--", rel],
            cwd=repo_path, capture_output=True, text=True,
            encoding="utf-8", errors="replace")
    except OSError as e:
        _log(f"status failed for {rel}: {e}")
        return False
    return res.returncode == 0 and bool(res.stdout.strip())


def remove_file_path(repo_path, rel_path, force=False):
    """Validates and removes a tracked path from the index and the
    working tree with `git rm` (folders are removed recursively).

    Guards: the path must be non-empty, resolve inside the repository,
    neither be the repository root nor live under .git/, must exist on
    disk, and must be tracked by git — an untracked path is rejected
    because git rm cannot match it and deleting it would be
    unrecoverable (no history to restore from).

    A path with uncommitted changes refuses to go unless *force* is
    True (the caller is expected to have warned the user first); with
    force it is removed via `git rm -f`, discarding those changes.

    Returns (True, "") on success or (False, detail) with a
    user-readable reason."""
    rel = _normalize_rel(rel_path)
    if not rel:
        return False, "Please provide a path to remove."

    root = os.path.realpath(repo_path)
    abs_path = os.path.realpath(os.path.join(repo_path, rel))
    if abs_path == root:
        return False, "Cannot remove the repository root itself."
    if not abs_path.startswith(root + os.sep):
        return False, "The path must be inside the repository."
    if ".git" in rel.split("/"):
        return False, "Paths under .git/ cannot be removed."
    if not os.path.exists(abs_path):
        return False, f"Path does not exist:\n{rel}"

    # Tracked only: git rm only ever matches tracked paths, and deleting
    # an untracked file would leave nothing to restore it from.
    try:
        listed = subprocess.run(
            ["git", "ls-files", "--", rel],
            cwd=repo_path, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        _log(f"remove: git ls-files failed for {rel}: {e}")
        return False, f"Could not check whether the path is tracked:\n{e}"
    if not listed.stdout.strip():
        return False, (
            f"Not tracked by git:\n{rel}\n\n"
            "Only tracked files and folders can be removed — an untracked "
            "path has no history to restore from.")

    cmd = ["git", "rm", "-q"]
    if os.path.isdir(abs_path):
        cmd.append("-r")
    if force:
        cmd.append("-f")
    cmd += ["--", rel]
    try:
        res = subprocess.run(
            cmd, cwd=repo_path, capture_output=True, text=True,
            encoding="utf-8", errors="replace")
    except OSError as e:
        _log(f"remove failed: {rel}: {e}")
        return False, f"Could not remove:\n{e}"
    if res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip()
        _log(f"git rm failed for {rel}: {err}")
        if not force and path_is_dirty(repo_path, rel):
            return False, (
                f"Uncommitted changes would be lost:\n{rel}\n\n{err}")
        return False, f"Could not remove:\n{err}"
    _log(f"Removed: {rel}")
    return True, ""
