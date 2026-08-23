import subprocess

from .core import _parse_log_records, _attach_full_messages, _parse_reflog_records, _parse_stash_records


def get_git_history(repo_path, start_sha, end_sha):
    """Fetches git history from *start_sha* (exclusive) down to *end_sha* inclusive, yielding parsed objects.
    If the range is reversed (start is newer than end) the equivalent commits are returned."""
    def _build(sha_from, sha_to):
        # Check if sha_from has a parent
        has_parent = False
        try:
            subprocess.run(["git", "rev-parse", f"{sha_from}^"],
                           cwd=repo_path, check=True, capture_output=True, encoding='utf-8', errors='replace')
            has_parent = True
        except:
            has_parent = False

        if has_parent:
            log_cmd = ["git", "log", f"{sha_from}..{sha_to}", "--format=%h|%cd|%an <%ae>|%s|%P", "--date=format:%d %b %Y", "--shortstat"]
        else:
            log_cmd = ["git", "log", sha_to, "--format=%h|%cd|%an <%ae>|%s|%P", "--date=format:%d %b %Y", "--shortstat"]

        result = subprocess.run(log_cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        commits = _parse_log_records(result.stdout)
        return _attach_full_messages(repo_path, commits, log_cmd)

    try:
        commits = _build(start_sha, end_sha)
        # If the requested direction has no commits but the reverse does, the user
        # chose a "newer" start; count the commits between the two instead of 0.
        if not commits and start_sha != end_sha:
            commits = _build(end_sha, start_sha)
        return commits
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch git history: {e.stderr}")


def get_branch_history(repo_path, branch, limit=None):
    """Fetches a branch's history (commits reachable from its tip).

    Args:
        repo_path: repository path.
        branch: branch name/ref.
        limit: max number of commits to return (None = unlimited).

    Returns parsed commit dicts in the same shape as get_git_history."""
    try:
        log_cmd = [
            "git", "log", branch,
            "--format=%h|%cd|%an <%ae>|%s|%P",
            "--date=format:%d %b %Y",
            "--shortstat"
        ]
        if limit is not None:
            log_cmd.append(f"-n{limit}")
        result = subprocess.run(log_cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        commits = _parse_log_records(result.stdout)
        return _attach_full_messages(repo_path, commits, log_cmd)
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch branch history: {e.stderr}")

def get_file_history(repo_path, filepath, limit=None, ref=None):
    """Fetches the history of a single file (commits that touched it).

    Uses ``git log --follow`` so the history persists across renames, and the
    ``--shortstat`` stats reflect only that file's changes per commit.

    Args:
        repo_path: repository path.
        filepath: repo-relative path of the file to browse.
        limit: max number of commits to return (None = unlimited).
        ref: ref/branch/SHA to scope the history to (None = HEAD).

    Returns parsed commit dicts in the same shape as get_git_history."""
    try:
        log_cmd = [
            "git", "log", "--follow",
            "--format=%h|%cd|%an <%ae>|%s|%P",
            "--date=format:%d %b %Y",
            "--shortstat"
        ]
        if ref:
            log_cmd.append(ref)
        if limit is not None:
            log_cmd.append(f"-n{limit}")
        log_cmd += ["--", filepath]
        result = subprocess.run(log_cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        commits = _parse_log_records(result.stdout)
        return _attach_full_messages(repo_path, commits, log_cmd)
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
