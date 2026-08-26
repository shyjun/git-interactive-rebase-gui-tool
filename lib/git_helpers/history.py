import subprocess

from .core import _parse_combined_log, _parse_reflog_records, _parse_stash_records


def get_git_history(repo_path, start_sha, end_sha, limit=None):
    """Fetches git history from *start_sha* (exclusive) down to *end_sha* inclusive.

    Uses a single ``git log`` call with ``%x1f``-delimited fields, ``%x1f%B%x1e``
    body+record-separator, and ``%D`` decorator so stats, full commit messages,
    and tag info are all parsed in one pass.

    Returns (commits, tag_map) where tag_map maps commit sha to a list of tag names.

    Args:
        limit: optional max number of commits to return (``-n`` flag)."""
    def _build(sha_from, sha_to):
        has_parent = False
        try:
            subprocess.run(["git", "rev-parse", f"{sha_from}^"],
                           cwd=repo_path, check=True, capture_output=True, encoding='utf-8', errors='replace')
            has_parent = True
        except:
            has_parent = False

        log_cmd = (
            ["git", "log", f"{sha_from}..{sha_to}"] if has_parent
            else ["git", "log", sha_to]
        )
        log_cmd += [
            "--format=%h%x1f%cd%x1f%an <%ae>%x1f%s%x1f%P%x1f%B%x1f%D%x1e",
            "--date=format:%d %b %Y",
            "--shortstat",
        ]
        if limit is not None:
            log_cmd.append(f"-n{limit}")

        result = subprocess.run(log_cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return _parse_combined_log(result.stdout)

    try:
        commits, tag_map = _build(start_sha, end_sha)
        if not commits and start_sha != end_sha:
            commits, tag_map = _build(end_sha, start_sha)
        return commits, tag_map
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch git history: {e.stderr}")


def get_branch_history(repo_path, branch, limit=None):
    """Fetches a branch's history (commits reachable from its tip).

    Returns (commits, tag_map) like get_git_history."""
    try:
        log_cmd = [
            "git", "log", branch,
            "--format=%h%x1f%cd%x1f%an <%ae>%x1f%s%x1f%P%x1f%B%x1f%D%x1e",
            "--date=format:%d %b %Y",
            "--shortstat"
        ]
        if limit is not None:
            log_cmd.append(f"-n{limit}")
        result = subprocess.run(log_cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return _parse_combined_log(result.stdout)
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch branch history: {e.stderr}")

def get_file_history(repo_path, filepath, limit=None, ref=None):
    """Fetches the history of a single file (commits that touched it).

    Returns (commits, tag_map) like get_git_history."""
    try:
        log_cmd = [
            "git", "log", "--follow",
            "--format=%h%x1f%cd%x1f%an <%ae>%x1f%s%x1f%P%x1f%B%x1f%D%x1e",
            "--date=format:%d %b %Y",
            "--shortstat"
        ]
        if ref:
            log_cmd.append(ref)
        if limit is not None:
            log_cmd.append(f"-n{limit}")
        log_cmd += ["--", filepath]
        result = subprocess.run(log_cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return _parse_combined_log(result.stdout)
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch file history: {e.stderr}")

def get_reflog_history(repo_path, limit=None):
    """Fetches the repository's HEAD reflog (most recent first).

    Args:
        repo_path: repository path.
        limit: max number of reflog entries to return (None = unlimited).

    Returns parsed reflog dicts in the same shape as get_git_history, with the
    reflog selector (e.g. ``HEAD@{0}``) stored in ``selector`` and the reflog
    subject stored in ``message``.
    """
    try:
        log_cmd = ["git", "reflog", "--format=%h|%gd|%gs"]
        if limit is not None:
            log_cmd.append(f"-n{limit}")
        result = subprocess.run(log_cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return _parse_reflog_records(result.stdout)
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch reflog history: {e.stderr}")

def get_tags_history(repo_path, limit=None):
    """Fetches all tags in the repository (most recent first).

    Returns parsed dicts in the same shape as get_git_history, with the
    tag name stored in ``message`` and ``raw_text`` formatted as
    ``<commit_sha> <tag_name>`` so existing SHA-extraction logic keeps
    working.
    """
    try:
        # %(objectname:short) = tag object SHA (annotated) or commit SHA (lightweight)
        # %(*objectname:short) = commit SHA (annotated) or empty (lightweight)
        # %(refname:short)     = tag name
        # %(creatordate:iso)  = tag date
        cmd = ["git", "for-each-ref",
               "--sort=-creatordate",
               "--format=%(objectname:short)\t%(*objectname:short)\t%(refname:short)\t%(creatordate:iso)",
               "refs/tags/"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True,
                                encoding='utf-8', errors='replace')
        entries = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split('\t')
            if len(parts) < 3:
                continue
            obj_sha, deref_sha, tag_name = parts[0], parts[1], parts[2]
            date = parts[3] if len(parts) > 3 else ""
            commit_sha = deref_sha if deref_sha else obj_sha
            raw = f"{commit_sha} {tag_name}"
            entries.append({
                "sha": commit_sha,
                "message": tag_name,
                "date": date,
                "author": "",
                "parents": "",
                "added": 0,
                "deleted": 0,
                "raw_text": raw,
            })
            if limit is not None and len(entries) >= limit:
                break
        return entries
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch tags: {e.stderr}")

def get_stash_history(repo_path, limit=None):
    """Fetches the repository's stash list (most recent first).

    Args:
        repo_path: repository path.
        limit: max number of stash entries to return (None = unlimited).

    Returns parsed stash dicts in the same shape as get_git_history, with the
    stash selector (e.g. ``stash@{0}``) stored in ``selector`` and the stash
    subject stored in ``message``.
    """
    try:
        log_cmd = ["git", "stash", "list", "--format=%H|%gd|%gs"]
        if limit is not None:
            log_cmd.append(f"-n{limit}")
        result = subprocess.run(log_cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return _parse_stash_records(result.stdout)
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch stash history: {e.stderr}")
