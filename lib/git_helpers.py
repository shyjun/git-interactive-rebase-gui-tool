
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py (git-interactive-rebase-gui-tool)")
    sys.exit(1)

import subprocess

def get_git_history(repo_path, commit_sha):
    """Fetches git history from HEAD down to commit_sha inclusive."""
    try:
        # Check if commit_sha has a parent
        has_parent = False
        try:
            subprocess.run(["git", "rev-parse", f"{commit_sha}^"], 
                           cwd=repo_path, check=True, capture_output=True, encoding='utf-8', errors='replace')
            has_parent = True
        except:
            has_parent = False

        if has_parent:
            # Inclusive range: parent..HEAD shows commit_sha and its descendants
            cmd = ["git", "log", f"{commit_sha}^..HEAD", "--oneline"]
        else:
            # Root commit case: show everything reachable from HEAD
            cmd = ["git", "log", "HEAD", "--oneline"]
        
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return [line for line in result.stdout.strip().split('\n') if line.strip()]
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch git history: {e.stderr}")

def get_current_branch(repo_path):
    """Fetches current branch name."""
    try:
        cmd = ["git", "branch", "--show-current"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip() or "DETACHED"
    except:
        return "Unknown"

def get_local_branches_map(repo_path):
    """Returns a dict mapping short_sha to a list of branch names (local + specific remotes)."""
    try:
        # Get current branch to include its remote counterpart
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

def get_commit_diff(repo_path, commit_sha):
    """Fetches the diff for a specific commit."""
    try:
        cmd = ["git", "show", commit_sha, "--format="]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout
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

def get_file_diff_in_commit(repo_path, commit_sha, filepath):
    """Returns the diff for a single file within a commit."""
    try:
        cmd = ["git", "show", commit_sha, "--", filepath]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get file diff: {e.stderr}")

def get_file_diff_only_in_commit(repo_path, commit_sha, filepath):
    """Returns the diff for a single file within a commit, excluding the commit message header."""
    try:
        # Use --format= to suppress the commit log/header
        cmd = ["git", "show", "--format=", commit_sha, "--", filepath]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get file diff: {e.stderr}")

def has_uncommitted_changes(repo_path):
    """Returns True if there are uncommitted changes in the repository."""
    try:
        # Check all changes
        cmd_all = ["git", "status", "--porcelain", "--untracked-files=no"]
        result_all = subprocess.run(cmd_all, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        changes_all = set(result_all.stdout.strip().split('\n')) if result_all.stdout.strip() else set()

        # Check excluding submodules
        cmd_ignored = ["git", "status", "--porcelain", "--untracked-files=no", "--ignore-submodules=all"]
        result_ignored = subprocess.run(cmd_ignored, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        changes_ignored_list = result_ignored.stdout.strip().split('\n') if result_ignored.stdout.strip() else []
        changes_ignored = set(changes_ignored_list)

        submodule_changes = changes_all - changes_ignored
        for sc in submodule_changes:
            parts = sc.strip().split()
            if len(parts) >= 2:
                print(f"change in submodule {parts[1]} is detected, but continuing")

        return bool(changes_ignored_list)
    except subprocess.CalledProcessError:
        return False

from datetime import datetime
def stash_changes(repo_path, message=None):
    if message is None:
        now = datetime.now()
        message = f"git-interactive-rebase-gui-tool: Pre-start stash ({now.strftime('%H:%M:%S %Y-%m-%d')})"
    """Stashes unstaged changes in the repository."""
    try:
        cmd = ["git", "stash", "push", "-m", message]
        subprocess.run(cmd, cwd=repo_path, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
        return True
    except subprocess.CalledProcessError:
        return False

def stash_pop(repo_path):
    """Pops the latest stash in the repository."""
    try:
        cmd = ["git", "stash", "pop"]
        subprocess.run(cmd, cwd=repo_path, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
        return True
    except subprocess.CalledProcessError:
        return False

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
def get_unstaged_files(repo_path):
    """Returns a list of file paths that have unstaged changes."""
    try:
        cmd = ["git", "status", "--porcelain", "--untracked-files=no"]
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
    except subprocess.CalledProcessError:
        return False

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
