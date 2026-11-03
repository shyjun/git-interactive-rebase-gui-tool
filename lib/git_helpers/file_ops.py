import os
import shutil

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
