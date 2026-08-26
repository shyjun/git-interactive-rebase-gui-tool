import os
import subprocess


def get_current_branch(repo_path):
    """Fetches current branch name."""
    try:
        cmd = ["git", "branch", "--show-current"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip() or "DETACHED"
    except:
        return "Unknown"

def get_local_branches_map(repo_path, current_branch=None, extra_remotes=None):
    """Returns a dict mapping short_sha to a list of branch names (local + specific remotes).

    Queries only the local branches plus the 3 target remote refs (master,
    main, current_branch) instead of enumerating every origin/* tracking ref,
    which is much faster on repos with many remote branches.
    """
    try:
        if current_branch is None:
            current_branch = get_current_branch(repo_path)

        # Build the list of remote ref patterns to query
        remote_patterns = ["refs/remotes/origin/master", "refs/remotes/origin/main"]
        if current_branch and current_branch != "DETACHED":
            remote_patterns.append(f"refs/remotes/origin/{current_branch}")
        if extra_remotes:
            for r in extra_remotes:
                if r.startswith("origin/"):
                    remote_patterns.append(f"refs/remotes/{r}")

        cmd = ["git", "for-each-ref", "--format=%(objectname:short) %(refname:short)",
               "refs/heads/"] + remote_patterns

        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')

        branch_map = {}
        for line in result.stdout.strip().split('\n'):
            if not line.strip(): continue
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                sha, branch = parts
                branch_map.setdefault(sha, []).append(branch)
        return branch_map
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"[git_helpers] get_local_branches_map: git for-each-ref failed: {err}")
        return {}


def get_tags_map(repo_path):
    """Returns a dict mapping commit short_sha to a list of tag names.

    Handles both lightweight and annotated tags in a single pass by
    using %(*objectname:short) to dereference annotated tags to their
    underlying commit SHA.
    """
    try:
        # %(objectname:short) = tag object SHA (annotated) or commit SHA (lightweight)
        # %(*objectname:short) = commit SHA (annotated) or empty (lightweight)
        # %(refname:short)     = tag name
        cmd = ["git", "for-each-ref",
               "--format=%(objectname:short)\t%(*objectname:short)\t%(refname:short)",
               "refs/tags/"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True,
                                encoding='utf-8', errors='replace')
        tag_map = {}
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split('\t')
            if len(parts) != 3:
                continue
            obj_sha, deref_sha, tag = parts
            # Use dereferenced SHA for annotated tags, original for lightweight
            commit_sha = deref_sha if deref_sha else obj_sha
            if commit_sha:
                tag_map.setdefault(commit_sha, []).append(tag)
        return tag_map
    except subprocess.CalledProcessError:
        return {}


def get_head_sha(repo_path):
    """Fetches current HEAD SHA (short)."""
    try:
        cmd = ["git", "rev-parse", "--short", "HEAD"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip()
    except:
        return "Unknown"

def get_full_head_sha(repo_path):
    """Fetches current HEAD SHA (full)."""
    try:
        cmd = ["git", "rev-parse", "HEAD"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip()
    except:
        return "Unknown"

def get_root_commit(repo_path):
    """Fetches the very first commit SHA in the repository."""
    try:
        cmd = ["git", "rev-list", "--max-parents=0", "HEAD"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip().split('\n')[0]
    except Exception as e:
        raise Exception(f"Failed to find root commit: {e}")

def get_recent_history_start(repo_path, count=1000):
    """
    Returns the SHA of the commit 'count' first-parent steps back from HEAD.
    If history is shorter than 'count', returns the root commit.
    Uses --first-parent so the skip count matches the range count exactly,
    even in repos with many merge commits (e.g. the Linux kernel).
    """
    try:
        cmd = ["git", "rev-list", "--first-parent", "--max-count=1", f"--skip={count}", "HEAD"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
        sha = result.stdout.strip()
        if sha:
            return sha
        return get_root_commit(repo_path)
    except:
        return get_root_commit(repo_path)

def get_branch_base_info(repo_path):
    """
    Finds the merge-base of HEAD with the most likely upstream branch.
    Uses 'git merge-base HEAD <upstream>' which is immune to unrelated branches
    that happen to contain our commits somewhere in their history.
    Returns (base_sha, branch_name) or (None, None).
    """
    try:
        current = get_current_branch(repo_path)
        print(f"[get_branch_base_info] Current branch: {current}")

        if not current or current == "DETACHED":
            print("[get_branch_base_info] DETACHED HEAD state, cannot detect base")
            return None, None

        # Collect all local branches with their tip SHAs
        cmd_branches = ["git", "for-each-ref", "--format=%(objectname) %(refname:short)", "refs/heads/"]
        res_branches = subprocess.run(cmd_branches, cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
        head_sha = get_full_head_sha(repo_path)

        others = []
        for line in res_branches.stdout.strip().split('\n'):
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                tip_sha, branch = parts
                if branch == current:
                    continue
                if tip_sha == head_sha:
                    print(f"[get_branch_base_info] Skipping sibling branch '{branch}' (same tip as HEAD)")
                    continue
                others.append(branch)

        print(f"[get_branch_base_info] Found {len(others)} candidate upstream branch(es)")

        if not others:
            print("[get_branch_base_info] No other branches found to compare against")
            return None, None

        # Try candidates in priority order: master > main > anything else
        PREFERRED = ["master", "main"]
        candidates = [b for b in PREFERRED if b in others] + [b for b in others if b not in PREFERRED]

        for upstream in candidates:
            cmd_mb = ["git", "merge-base", "HEAD", upstream]
            res_mb = subprocess.run(cmd_mb, cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if res_mb.returncode == 0:
                base_sha = res_mb.stdout.strip()
                if base_sha:
                    # Sanity check: ensure there is at least 1 commit after the base
                    cmd_check = ["git", "rev-list", f"{base_sha}..HEAD"]
                    res_check = subprocess.run(cmd_check, cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
                    unique = [c for c in res_check.stdout.strip().split('\n') if c.strip()]
                    print(f"[get_branch_base_info] merge-base with '{upstream}': {base_sha[:8]}, unique commits: {len(unique)}")
                    if unique:
                        print(f"[get_branch_base_info] Detected base: SHA={base_sha[:8]}..., branch={upstream}")
                        return base_sha, upstream

        print("[get_branch_base_info] No diverging base found against any candidate upstream")
        return None, None

    except Exception as exc:
        print(f"[git_helpers] get_branch_base_info raised: {exc}")
        return None, None

def commit_exists(repo_path, commit_id):
    """Checks whether a commit-like revision (SHA, short SHA, or ref) resolves
    to an existing commit in the repository."""
    try:
        cmd = ["git", "rev-parse", "--verify", "--quiet", f"{commit_id}^{{commit}}"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, encoding='utf-8', errors='replace')
        return result.returncode == 0
    except Exception:
        return False

def branch_exists(repo_path, branch_name):
    """Checks if a local or remote branch exists.

    Accepts either a short name (``feature``) or an already-qualified remote
    name (``origin/feature``).
    """
    try:
        # Check local branch
        cmd = ["git", "show-ref", "--verify", f"refs/heads/{branch_name}"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True)
        if result.returncode == 0:
            return True
        # Check remote branch (origin) for a short name like "feature"
        cmd = ["git", "show-ref", "--verify", f"refs/remotes/origin/{branch_name}"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, encoding='utf-8', errors='replace')
        if result.returncode == 0:
            return True
        # Check an already-qualified remote name like "origin/feature"
        cmd = ["git", "show-ref", "--verify", f"refs/remotes/{branch_name}"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, encoding='utf-8', errors='replace')
        return result.returncode == 0
    except:
        return False


def normalize_branch_ref(repo_path, branch_name):
    """Converts a user-typed branch name into a ref that ``git log`` accepts.

    Returns the name unchanged when it resolves to a local or qualified
    remote ref; otherwise, if only ``origin/<name>`` exists, returns
    ``origin/<name>`` so the history loads deterministically instead of relying
    on git's DWIM guessing (which can be ambiguous with multiple remotes).
    """
    try:
        cmd = ["git", "show-ref", "--verify", f"refs/heads/{branch_name}"]
        if subprocess.run(cmd, cwd=repo_path, capture_output=True).returncode == 0:
            return branch_name
        cmd = ["git", "show-ref", "--verify", f"refs/remotes/{branch_name}"]
        if subprocess.run(cmd, cwd=repo_path, capture_output=True).returncode == 0:
            return branch_name
        cmd = ["git", "show-ref", "--verify", f"refs/remotes/origin/{branch_name}"]
        if subprocess.run(cmd, cwd=repo_path, capture_output=True).returncode == 0:
            return f"origin/{branch_name}"
    except Exception:
        pass
    return branch_name


def get_branch_names(repo_path, include_remote=True):
    """Returns branch display names (local ones, plus ``origin/...`` remote ones)."""
    try:
        patterns = ["refs/heads/"]
        if include_remote:
            patterns.append("refs/remotes/origin/")
        cmd = ["git", "for-each-ref", "--format=%(refname:short)"] + patterns
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True,
                                check=True, encoding='utf-8', errors='replace')
        names = []
        for line in result.stdout.strip().split('\n'):
            name = line.strip()
            if not name or name == "origin/HEAD" or name.endswith("/HEAD"):
                continue
            names.append(name)
        return names
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"[git_helpers] get_branch_names: git for-each-ref failed: {err}")
        return []

def resolve_ref(repo_path, ref):
    """Resolves a git ref/SHA (e.g. 'HEAD~3', 'origin/main', a full/short SHA) to a full SHA."""
    try:
        cmd = ["git", "rev-parse", ref]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None
