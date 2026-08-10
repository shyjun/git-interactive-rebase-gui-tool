
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

import os
import subprocess
import tempfile

def _parse_log_records(stdout):
    """Parses `git log --shortstat` output (pipe-separated records) into commit dicts."""
    import re
    stat_pattern = re.compile(r'\s*\d+\s+files?\s+changed,\s+(\d+)\s+insertions?\(\+\),\s+(\d+)\s+deletions?\(-\)')
    stat_pattern_ins_only = re.compile(r'\s*\d+\s+files?\s+changed,\s+(\d+)\s+insertions?\(\+\)')
    stat_pattern_del_only = re.compile(r'\s*\d+\s+files?\s+changed,\s+(\d+)\s+deletions?\(-\)')

    commits = []
    current_commit = None

    for line in stdout.split('\n'):
        line = line.strip()
        if not line:
            continue

        # format pipe boundary: shastring|datestring|authorstring|messagestring|parents
        if '|' in line and (line.split('|', 4)[0].isalnum() and len(line.split('|', 4)[0]) >= 7):
            parts = line.split('|', 4)
            if current_commit:
                commits.append(current_commit)
            current_commit = {
                "sha": parts[0],
                "date": parts[1],
                "author": parts[2] if len(parts) > 2 else "",
                "message": parts[3] if len(parts) > 3 else "",
                "parents": parts[4] if len(parts) > 4 else "",
                "added": 0,
                "deleted": 0,
                "raw_text": f"{parts[0]} {parts[3] if len(parts) > 3 else ''}"
            }
        else:
            # It must be a shortstat line
            if current_commit:
                m = stat_pattern.search(line)
                if m:
                    current_commit["added"] = int(m.group(1))
                    current_commit["deleted"] = int(m.group(2))
                else:
                    m2 = stat_pattern_ins_only.search(line)
                    if m2:
                        current_commit["added"] = int(m2.group(1))
                    else:
                        m3 = stat_pattern_del_only.search(line)
                        if m3:
                            current_commit["deleted"] = int(m3.group(1))

    if current_commit:
        commits.append(current_commit)

    return commits

def _attach_full_messages(repo_path, commits, log_cmd):
    """Batch-fetches full commit messages (subject + body) and fills them into commits."""
    try:
        msg_cmd = list(log_cmd) + ["--format=%h%x1f%B%x1e"]
        msg_result = subprocess.run(msg_cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        full_msgs = {}
        for record in msg_result.stdout.split('\x1e'):
            record = record.strip('\x1f')
            if '\x1f' in record:
                rec_sha, body = record.split('\x1f', 1)
                full_msgs[rec_sha.strip()] = body.strip()
        for commit in commits:
            commit["message"] = full_msgs.get(commit["sha"], commit.get("message", ""))
    except subprocess.CalledProcessError:
        pass  # fall back to subject-only messages
    return commits


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

def get_current_branch(repo_path):
    """Fetches current branch name."""
    try:
        cmd = ["git", "branch", "--show-current"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip() or "DETACHED"
    except:
        return "Unknown"

def get_local_branches_map(repo_path, current_branch=None):
    """Returns a dict mapping short_sha to a list of branch names (local + specific remotes)."""
    try:
        # Get current branch to include its remote counterpart
        if current_branch is None:
            current_branch = get_current_branch(repo_path)
        
        # for-each-ref with multiple patterns. %(refname:short) for remotes is origin/branch.
        cmd = ["git", "for-each-ref", "--format=%(objectname:short) %(refname:short)", 
               "refs/heads/", "refs/remotes/origin/"]
        
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        
        target_remotes = ["origin/master", "origin/main"]
        if current_branch and current_branch != "DETACHED":
            target_remotes.append(f"origin/{current_branch}")
            
        branch_map = {}
        for line in result.stdout.strip().split('\n'):
            if not line.strip(): continue
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                sha, branch = parts
                # If it's a remote, only include it if it's one of our targets
                if branch.startswith("origin/"):
                    if branch not in target_remotes:
                        continue
                branch_map.setdefault(sha, []).append(branch)
        return branch_map
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
    Returns the SHA of the commit 'count' steps back from HEAD.
    If history is shorter than 'count', returns the root commit.
    """
    try:
        cmd = ["git", "rev-list", "--max-count=1", f"--skip={count}", "HEAD"]
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

    except Exception:
        return None, None

def get_commit_diff(repo_path, commit_sha):
    """Fetches the diff for a specific commit."""
    try:
        cmd = ["git", "show", commit_sha, "--format="]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        
        # Inject a newline before every 'diff --git' block (except the very first if it's at start)
        diff_text = result.stdout
        import re
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
    except Exception:
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
    except subprocess.CalledProcessError:
        return {}


def get_file_diff_in_commit(repo_path, commit_sha, filepath):
    """Returns the diff for a single file within a commit."""
    try:
        cmd = ["git", "show", commit_sha, "--", filepath]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        diff_text = result.stdout
        # Inject separator padding
        import re
        diff_text = re.sub(r'(\n)(diff --git )', r'\1\n\2', diff_text)
        return diff_text
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get file diff: {e.stderr}")

def get_file_diff_only_in_commit(repo_path, commit_sha, filepath):
    """Returns the diff for a single file within a commit, excluding the commit message header."""
    try:
        cmd = ["git", "show", "--format=", commit_sha, "--", filepath]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        diff_text = result.stdout
        # Inject separator padding
        import re
        diff_text = re.sub(r'(\n)(diff --git )', r'\1\n\2', diff_text)
        return diff_text
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get file diff: {e.stderr}")

def has_uncommitted_changes(repo_path):
    """Returns True if there are uncommitted changes in the repository."""
    try:
        # Check excluding submodules to avoid recursive deep checks
        cmd_ignored = ["git", "status", "--porcelain", "--untracked-files=no", "--ignore-submodules=all"]
        result = subprocess.run(cmd_ignored, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return bool(result.stdout.strip())
    except subprocess.CalledProcessError:
        return False

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
    except subprocess.CalledProcessError:
        return False, False

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

from datetime import datetime

# Sentinel returned by stash_changes when there was nothing to stash (a no-op),
# as opposed to None which indicates a genuine failure.
STASH_NOTHING_STASHED = object()


def stash_changes(repo_path, message=None):
    """Stashes unstaged changes in the repository.
    Returns the new stash SHA if a stash was created, STASH_NOTHING_STASHED if there was
    nothing to stash, or None if the operation failed."""
    if message is None:
        now = datetime.now()
        message = f"git-interactive-rebase-gui-tool: Pre-start stash ({now.strftime('%H:%M:%S %Y-%m-%d')})"
    try:
        # Before stashing, get the current top stash SHA (if any)
        old_stash_sha = None
        try:
            result = subprocess.run(["git", "rev-parse", "refs/stash"], cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode == 0:
                old_stash_sha = result.stdout.strip()
        except:
            pass

        cmd = ["git", "stash", "push", "-m", message]
        subprocess.run(cmd, cwd=repo_path, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
        
        # After stashing, check if refs/stash has changed or been created
        result = subprocess.run(["git", "rev-parse", "refs/stash"], cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode == 0:
            new_stash_sha = result.stdout.strip()
            if new_stash_sha != old_stash_sha:
                return new_stash_sha
            return STASH_NOTHING_STASHED
        return None
    except subprocess.CalledProcessError:
        return None

def discard_changes(repo_path):
    """Discards all unstaged changes in tracked files (git checkout .).
    Returns True if successful, otherwise False."""
    try:
        subprocess.run(["git", "checkout", "."], cwd=repo_path, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        return False

def get_stash_subject(repo_path, stash_sha=None):
    """Returns the subject (message) of a stash. If stash_sha is provided, resolves that
    specific stash, otherwise the top one. Returns the subject string or None."""
    try:
        target = "stash@{0}"
        if stash_sha:
            cmd_list = ["git", "log", "--format=%H", "-g", "refs/stash"]
            result = subprocess.run(cmd_list, cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode == 0:
                shas = result.stdout.strip().split('\n')
                try:
                    idx = shas.index(stash_sha)
                    target = f"stash@{{{idx}}}"
                except ValueError:
                    return None
            else:
                return None
        result = subprocess.run(["git", "log", "-1", "--format=%s", target],
                                cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except:
        return None

def stash_pop(repo_path, stash_sha=None):
    """Pops a stash from the repository. If stash_sha is provided, pops that specific stash.
    Returns (success, message)."""
    try:
        target = "stash@{0}"
        if stash_sha:
            # Find the index of the stash with this SHA
            cmd_list = ["git", "log", "--format=%H", "-g", "refs/stash"]
            result = subprocess.run(cmd_list, cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode == 0:
                shas = result.stdout.strip().split('\n')
                try:
                    idx = shas.index(stash_sha)
                    target = f"stash@{{{idx}}}"
                except ValueError:
                    # SHA not found in stash list
                    return False, ""
            else:
                return False, ""

        # Get message of the stash before popping it
        message = ""
        try:
            cmd_msg = ["git", "log", "-1", "--format=%s", target]
            result_msg = subprocess.run(cmd_msg, cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result_msg.returncode == 0:
                message = result_msg.stdout.strip()
        except:
            pass

        cmd = ["git", "stash", "pop", target]
        subprocess.run(cmd, cwd=repo_path, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
        return True, message
    except subprocess.CalledProcessError:
        return False, ""

def stash_pop_can_apply(repo_path, stash_sha):
    """Performs a non-mutating dry-run of 'git stash pop' using git merge-tree
    (affects objects only, never the working tree). Returns (True, '') if the
    stash can be applied cleanly, (False, detail) otherwise."""
    try:
        base = subprocess.run(
            ["git", "rev-parse", f"{stash_sha}^"],
            cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        if base.returncode != 0:
            return False, "Could not resolve the stash base."
        base_sha = base.stdout.strip()

        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        if head.returncode != 0:
            return False, "Could not resolve HEAD."
        head_sha = head.stdout.strip()

        result = subprocess.run(
            ["git", "merge-tree", base_sha, head_sha, stash_sha],
            cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        output = result.stdout
        if "<<<<<<<" in output or "=======" in output or "CONFLICT" in output:
            return False, "Merging this stash would produce conflicts."
        return True, ""
    except Exception:
        return False, "Could not check if the stash can be applied."

def get_stash_status(repo_path, stash_sha):
    """Determines where the managed stash sits in the stash list.
    Returns one of:
      ('NOT_FOUND', None)   - the stash is not in the list (or the list is empty)
      ('AT_HEAD', 0)        - the stash is the latest / only entry
      ('NOT_HEAD', idx)     - the stash is present but not at the head position"""
    try:
        result = subprocess.run(["git", "log", "--format=%H", "-g", "refs/stash"],
                                cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            return ("NOT_FOUND", None)
        shas = result.stdout.strip().split('\n') if result.stdout.strip() else []
        if not shas:
            return ("NOT_FOUND", None)
        try:
            idx = shas.index(stash_sha)
        except ValueError:
            return ("NOT_FOUND", None)
        if idx == 0:
            return ("AT_HEAD", 0)
        return ("NOT_HEAD", idx)
    except Exception:
        return ("NOT_FOUND", None)

def _stash_index(repo_path, stash_sha):
    """Resolves a stash SHA to its stash@{idx} target. Returns None if not found."""
    try:
        result = subprocess.run(["git", "log", "--format=%H", "-g", "refs/stash"],
                                cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            return None
        shas = result.stdout.strip().split('\n')
        try:
            idx = shas.index(stash_sha)
        except ValueError:
            return None
        return f"stash@{{{idx}}}"
    except Exception:
        return None

def stash_apply(repo_path, stash_sha):
    """Applies a stash without removing it (git stash apply).
    Returns (success, error_detail). Logs the failed command details."""
    try:
        target = _stash_index(repo_path, stash_sha)
        if target is None:
            print(f"[stash-merge] FAILED: could not resolve stash {stash_sha[:8]} in stash list")
            return False, f"Stash {stash_sha[:8]} not found in the stash list."
        cmd = ["git", "stash", "apply", target]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode == 0:
            return True, ""
        print(f"[stash-merge] FAILED: {cmd[0]} {' '.join(cmd[1:])}")
        print(f"[stash-merge] Command: {' '.join(cmd)}")
        print(f"[stash-merge] Return code: {result.returncode}")
        print(f"[stash-merge] stdout: {result.stdout.strip()}")
        print(f"[stash-merge] stderr: {result.stderr.strip()}")
        return False, result.stderr.strip() or "git stash apply failed"
    except Exception as e:
        print(f"[stash-merge] FAILED: git stash apply raised: {e}")
        return False, str(e)

def stash_drop(repo_path, stash_sha):
    """Drops a specific stash (git stash drop stash@{idx}). Returns True on success."""
    try:
        target = _stash_index(repo_path, stash_sha)
        if target is None:
            print(f"[stash-merge] FAILED: could not resolve stash {stash_sha[:8]} in stash list")
            return False
        cmd = ["git", "stash", "drop", target]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode != 0:
            print(f"[stash-merge] FAILED: {cmd[0]} {' '.join(cmd[1:])}")
            print(f"[stash-merge] Command: {' '.join(cmd)}")
            print(f"[stash-merge] Return code: {result.returncode}")
            print(f"[stash-merge] stdout: {result.stdout.strip()}")
            print(f"[stash-merge] stderr: {result.stderr.strip()}")
            return False
        return True
    except Exception as e:
        print(f"[stash-merge] FAILED: git stash drop raised: {e}")
        return False

def _rollback_merge(repo_path, temp_stash_sha):
    """Restores the repository after a failed stash merge. The working tree is reset
    and the original unstaged changes are recovered from the temporary stash, which is
    then dropped. The original app-created stash is left untouched."""
    print("[stash-merge] Rolling back failed merge (git reset --hard HEAD)...")
    subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
    print("[stash-merge] Restoring changes from temporary stash...")
    stash_apply(repo_path, temp_stash_sha)
    print("[stash-merge] Dropping temporary stash...")
    stash_drop(repo_path, temp_stash_sha)

def merge_into_stash(repo_path, existing_stash_sha):
    """Merges the current unstaged changes into the existing app-created stash.

    Uses only 'git stash apply' (never 'pop') so no stash is removed until the merge
    has completed successfully. On failure the repository is restored to its original
    state and the original app-created stash is left untouched.

    Returns the new app-created stash SHA on success, or None on failure."""
    def log(msg):
        print(f"[stash-merge] {msg}")

    temp_stash_sha = None
    try:
        # Step 1: temporary stash of the current unstaged changes
        log("Creating temporary stash...")
        now = datetime.now()
        temp_stash_sha = stash_changes(
            repo_path,
            message=f"git-interactive-rebase-gui-tool: temp merge stash ({now.strftime('%H:%M:%S %Y-%m-%d')})")
        if temp_stash_sha is None:
            log("Failed to create temporary stash.")
            return None
        if temp_stash_sha is STASH_NOTHING_STASHED:
            # Nothing to merge (no tracked changes); the existing stash stays as managed
            log("No changes to merge; keeping existing app-created stash.")
            return existing_stash_sha

        # Step 2: apply the existing app-created stash
        log("Applying app-created stash...")
        ok, err = stash_apply(repo_path, existing_stash_sha)
        if not ok:
            log(f"Applying app-created stash failed: {err}")
            _rollback_merge(repo_path, temp_stash_sha)
            return None

        # Step 3: apply the temporary stash
        log("Applying temporary stash...")
        ok, err = stash_apply(repo_path, temp_stash_sha)
        if not ok:
            log(f"Applying temporary stash failed: {err}")
            _rollback_merge(repo_path, temp_stash_sha)
            return None

        # Step 4: drop the original app-created stash and the temporary stash
        log("Dropping app-created stash...")
        stash_drop(repo_path, existing_stash_sha)
        log("Dropping temporary stash...")
        stash_drop(repo_path, temp_stash_sha)

        # Step 5: create a new stash from the combined working tree changes
        log("Creating merged app-created stash...")
        now = datetime.now()
        new_stash_sha = stash_changes(
            repo_path,
            message=f"git-interactive-rebase-gui-tool: merged app stash ({now.strftime('%H:%M:%S %Y-%m-%d')})")
        if new_stash_sha is None or new_stash_sha is STASH_NOTHING_STASHED:
            log("Failed to create merged app-created stash.")
            return None

        log("Merge completed successfully.")
        return new_stash_sha
    except Exception as e:
        log(f"Unexpected error during merge: {e}")
        if temp_stash_sha:
            _rollback_merge(repo_path, temp_stash_sha)
        return None

def branch_exists(repo_path, branch_name):
    """Checks if a local or remote branch exists."""
    try:
        # Check local branch
        cmd = ["git", "show-ref", "--verify", f"refs/heads/{branch_name}"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True)
        if result.returncode == 0:
            return True
        # Check remote branch (origin)
        cmd = ["git", "show-ref", "--verify", f"refs/remotes/origin/{branch_name}"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, encoding='utf-8', errors='replace')
        return result.returncode == 0
    except:
        return False

def get_remote_head_sha(repo_url):
    """Fetches the current HEAD SHA from the remote repository without fetching objects."""
    try:
        cmd = ["git", "ls-remote", repo_url, "HEAD"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.split()[0]
        return None
    except:
        return None
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
                files.append(parts[1])
        return files
    except:
        return []

def commit_file(repo_path, filepath, message):
    """Stages and commits a single file."""
    try:
        # Stage the file
        subprocess.run(["git", "add", filepath], cwd=repo_path, check=True, capture_output=True)
        # Commit the file
        subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode('utf-8') if e.stderr else str(e)
        print(f"Git commit failed for {filepath}: {err}")
        return False

def get_revert_commit_message(repo_path, commit_sha):
    """Generates the default git revert commit message for a given SHA."""
    try:
        # Get the subject line only
        cmd_subject = ["git", "log", "-1", "--format=%s", commit_sha]
        result_subject = subprocess.run(cmd_subject, cwd=repo_path, capture_output=True,
                                        text=True, check=True, encoding='utf-8', errors='replace')
        subject = result_subject.stdout.strip()

        # Get the full SHA for the body line
        cmd_full_sha = ["git", "rev-parse", commit_sha]
        result_full_sha = subprocess.run(cmd_full_sha, cwd=repo_path, capture_output=True,
                                         text=True, check=True, encoding='utf-8', errors='replace')
        full_sha = result_full_sha.stdout.strip()

        return f'Revert "{subject}"\n\nThis reverts commit {full_sha}.'
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to generate revert message: {e.stderr}")

def bulk_commit_all(repo_path, message):
    """Stages all modified files and commits them as a single bulk commit."""
    try:
        # Stage all changes (excluding untracked files as per --untracked-files=no in checks)
        subprocess.run(["git", "add", "-u"], cwd=repo_path, check=True, capture_output=True)
        # Commit
        subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def amend_with_head(repo_path):
    """Stages all modified files and amends them into the current HEAD commit."""
    try:
        before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["git", "add", "-u"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "--amend", "--no-edit"], cwd=repo_path, check=True, capture_output=True)
        after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True, check=True).stdout.strip()
        print(f"Amended HEAD: {before[:8]} -> {after[:8]}")
        return True
    except subprocess.CalledProcessError:
        return False


def stage_files(repo_path, files):
    """Stages only the given files (never 'git add .'). Returns True on success."""
    if not files:
        return True
    try:
        subprocess.run(["git", "add", "--"] + list(files), cwd=repo_path,
                       check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode('utf-8') if e.stderr else str(e)
        print(f"git add failed: {err}")
        return False


def commit_staged(repo_path, message):
    """Commits the currently staged changes with the given message. Returns True on success."""
    try:
        subprocess.run(["git", "commit", "-m", message], cwd=repo_path,
                       check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode('utf-8') if e.stderr else str(e)
        print(f"git commit failed: {err}")
        return False


def amend_staged(repo_path, message):
    """Amends HEAD with the currently staged changes using the given message.

    Unlike amend_with_head(), this does NOT run 'git add -u' - the caller is
    responsible for staging exactly the changes that should be amended."""
    msg_fd, msg_path = tempfile.mkstemp(prefix='git_amend_msg_', text=True)
    with os.fdopen(msg_fd, 'w', encoding='utf-8') as f:
        f.write(message)
    try:
        try:
            subprocess.run(["git", "commit", "--amend", "-F", msg_path],
                           cwd=repo_path, check=True, capture_output=True)
        finally:
            try:
                os.unlink(msg_path)
            except OSError:
                pass
        return True
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode('utf-8') if e.stderr else str(e)
        print(f"git commit --amend failed: {err}")
        return False


def apply_patch_to_index(repo_path, patch_text):
    """Stages the given unified-diff patch with 'git apply --cached',
    so only the hunks present in the patch reach the index.

    On failure the index is reset to HEAD ("git reset -q") so a partial/erroneous
    apply can never leave the index in a half-staged state, then re-raises."""
    if not patch_text.strip():
        return
    patch_fd, patch_path = tempfile.mkstemp(prefix='git_selective_', suffix='.patch', text=True)
    with os.fdopen(patch_fd, 'w', encoding='utf-8') as pf:
        pf.write(patch_text)
    try:
        subprocess.run(["git", "apply", "--cached", "--ignore-whitespace", patch_path],
                       cwd=repo_path, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        subprocess.run(["git", "reset", "-q"], cwd=repo_path)
        err = e.stderr.decode('utf-8') if e.stderr else str(e)
        raise Exception(f"Failed to stage patch: {err}")
    finally:
        try:
            os.unlink(patch_path)
        except OSError:
            pass


def get_merge_base(repo_path, ref):
    """Returns the merge-base of HEAD with *ref* (e.g. 'origin/main')."""
    try:
        cmd = ["git", "merge-base", "HEAD", ref]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        sha = result.stdout.strip()
        return sha if sha else None
    except subprocess.CalledProcessError:
        return None


def get_diff_between(repo_path, start_sha, end_sha):
    """Fetches the combined diff of all changes between *start_sha* and *end_sha*."""
    try:
        cmd = ["git", "diff", start_sha, end_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch branch diff: {e.stderr}")


def get_diff_stat_between(repo_path, start_sha, end_sha):
    """Fetches the --stat summary of all changes between *start_sha* and *end_sha*."""
    try:
        cmd = ["git", "diff", "--stat", start_sha, end_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch branch diff stats: {e.stderr}")


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
    try:
        cmd = ["git", "diff", start_sha, end_sha, "--", filepath]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        diff_text = result.stdout
        # Inject separator padding
        import re
        diff_text = re.sub(r'(\n)(diff --git )', r'\1\n\2', diff_text)
        return diff_text
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get file diff: {e.stderr}")


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
    except subprocess.CalledProcessError:
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
        import re
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
    except subprocess.CalledProcessError:
        return {}


def get_unstaged_file_diff(repo_path, filepath):
    """Returns the diff for a single file's unstaged changes."""
    try:
        cmd = ["git", "diff", "--", filepath]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        diff_text = result.stdout
        # Inject separator padding
        import re
        diff_text = re.sub(r'(\n)(diff --git )', r'\1\n\2', diff_text)
        return diff_text
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get unstaged file diff: {e.stderr}")


def resolve_ref(repo_path, ref):
    """Resolves a git ref/SHA (e.g. 'HEAD~3', 'origin/main', a full/short SHA) to a full SHA."""
    try:
        cmd = ["git", "rev-parse", ref]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None
