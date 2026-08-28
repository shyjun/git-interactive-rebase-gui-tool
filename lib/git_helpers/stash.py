import os
import subprocess
from datetime import datetime


# Sentinel returned by stash_changes when there was nothing to stash (a no-op),
# as opposed to None which indicates a genuine failure.
STASH_NOTHING_STASHED = object()


def stash_changes(repo_path, message=None):
    """Stashes unstaged changes in the repository.

    Returns a (result, detail) tuple where result is:
      - the new stash SHA if a stash was created,
      - STASH_NOTHING_STASHED if there was nothing to stash (a no-op),
      - None if the operation failed (detail then carries the git error text)."""
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

        # After stashing, check if refs/stash has changed or been created.
        # A successful push (rc 0) with no resulting refs/stash means there was
        # nothing to stash and no pre-existing stash list, i.e. a no-op, not a
        # failure (STASH_NOTHING_STASHED).
        result = subprocess.run(["git", "rev-parse", "refs/stash"], cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode == 0:
            new_stash_sha = result.stdout.strip()
            if new_stash_sha != old_stash_sha:
                return new_stash_sha, ""
        return STASH_NOTHING_STASHED, ""
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"[git_helpers] git stash push failed: {err}")
        return None, err

def discard_changes(repo_path):
    """Discards all unstaged changes in tracked files (git checkout .).

    Returns (True, "") on success, or (False, detail) where detail carries the
    git error text."""
    try:
        subprocess.run(["git", "checkout", "."], cwd=repo_path, check=True, capture_output=True, text=True)
        return True, ""
    except subprocess.CalledProcessError as e:
        err = e.stderr if isinstance(e.stderr, str) else e.stderr.decode('utf-8')
        return False, err

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
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else ""
        return False, err or "git stash pop failed"

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
            print(f"[git_helpers] get_stash_status: 'git log refs/stash' failed (rc={result.returncode}): {result.stderr.strip()}")
            return ("ERROR", None)
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
    except Exception as exc:
        print(f"[git_helpers] get_stash_status raised: {exc}")
        return ("ERROR", None)

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

    Uses only 'git stash apply' (never 'pop') and creates the merged stash
    BEFORE dropping either source stash, so no stash is removed until the merge
    has completed successfully. On failure the repository is restored to its
    original state and the original app-created stash is left untouched.

    Returns the new app-created stash SHA on success, or None on failure."""
    def log(msg):
        print(f"[stash-merge] {msg}")

    temp_stash_sha = None
    try:
        # Step 1: temporary stash of the current unstaged changes
        log("Creating temporary stash...")
        now = datetime.now()
        temp_stash_sha, temp_stash_err = stash_changes(
            repo_path,
            message=f"git-interactive-rebase-gui-tool: temp merge stash ({now.strftime('%H:%M:%S %Y-%m-%d')})")
        if temp_stash_sha is None:
            log(f"Failed to create temporary stash: {temp_stash_err}")
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

        # Step 4: create a new stash from the combined working tree changes,
        # BEFORE dropping either source stash. If this step fails, both source
        # stashes are still intact and the working tree changes are restored
        # by _rollback_merge, so the app-managed stash can never be lost.
        log("Creating merged app-created stash...")
        now = datetime.now()
        new_stash_sha, new_stash_err = stash_changes(
            repo_path,
            message=f"git-interactive-rebase-gui-tool: merged app stash ({now.strftime('%H:%M:%S %Y-%m-%d')})")
        if new_stash_sha is None or new_stash_sha is STASH_NOTHING_STASHED:
            log(f"Failed to create merged app-created stash: {new_stash_err}")
            _rollback_merge(repo_path, temp_stash_sha)
            return None

        # Step 5: the merged stash now exists, so the sources can be replaced
        # (best-effort - a leftover entry is logged, never treated as failure).
        log("Dropping app-created stash...")
        if not stash_drop(repo_path, existing_stash_sha):
            log(f"WARNING: failed to drop original app-created stash {existing_stash_sha[:8]}; "
                "it may still be in the stash list.")
        log("Dropping temporary stash...")
        if not stash_drop(repo_path, temp_stash_sha):
            log(f"WARNING: failed to drop temporary stash {temp_stash_sha[:8]}; "
                "it may still be in the stash list.")

        log("Merge completed successfully.")
        return new_stash_sha
    except Exception as e:
        log(f"Unexpected error during merge: {e}")
        if temp_stash_sha:
            _rollback_merge(repo_path, temp_stash_sha)
        return None
