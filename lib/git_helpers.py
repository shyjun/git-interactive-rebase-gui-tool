
if __name__ == "__main__":
    import sys
    print("Please run the main app: git_interactive_rebase.py")
    sys.exit(1)

import subprocess

def get_git_history(repo_path, commit_sha):
    """Fetches git history from HEAD down to commit_sha inclusive."""
    try:
        # Check if commit_sha has a parent
        has_parent = False
        try:
            subprocess.run(["git", "rev-parse", f"{commit_sha}^"], 
                           cwd=repo_path, check=True, capture_output=True)
            has_parent = True
        except:
            has_parent = False

        if has_parent:
            # Inclusive range: parent..HEAD shows commit_sha and its descendants
            cmd = ["git", "log", f"{commit_sha}^..HEAD", "--oneline"]
        else:
            # Root commit case: show everything reachable from HEAD
            cmd = ["git", "log", "HEAD", "--oneline"]
        
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return [line for line in result.stdout.strip().split('\n') if line.strip()]
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch git history: {e.stderr}")

def get_current_branch(repo_path):
    """Fetches current branch name."""
    try:
        cmd = ["git", "branch", "--show-current"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return result.stdout.strip() or "DETACHED"
    except:
        return "Unknown"

def get_head_sha(repo_path):
    """Fetches current HEAD SHA (short)."""
    try:
        cmd = ["git", "rev-parse", "--short", "HEAD"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except:
        return "Unknown"

def get_root_commit(repo_path):
    """Fetches the very first commit SHA in the repository."""
    try:
        cmd = ["git", "rev-list", "--max-parents=0", "HEAD"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n')[0]
    except Exception as e:
        raise Exception(f"Failed to find root commit: {e}")

def get_commit_diff(repo_path, commit_sha):
    """Fetches the diff for a specific commit."""
    try:
        cmd = ["git", "show", commit_sha, "--format="]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch diff: {e.stderr}")

def get_full_commit_message(repo_path, commit_sha):
    """Fetches the full (multi-line) commit message."""
    try:
        cmd = ["git", "log", "-1", "--format=%B", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch commit message: {e.stderr}")

def get_commit_metadata(repo_path, commit_sha):
    """Fetches author name, email, and date for a commit."""
    try:
        # %an = author name, %ae = author email, %ad = author date (human-readable)
        cmd = ["git", "log", "-1", "--format=%an <%ae>, %ad", "--date=format:%d %b %Y %H:%M", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return "Unknown author"

def get_commit_files(repo_path, commit_sha):
    """Returns a list of file paths changed by a given commit."""
    try:
        cmd = ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", commit_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return [f for f in result.stdout.strip().split('\n') if f.strip()]
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to list commit files: {e.stderr}")

def get_file_diff_in_commit(repo_path, commit_sha, filepath):
    """Returns the diff for a single file within a commit."""
    try:
        cmd = ["git", "show", commit_sha, "--", filepath]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get file diff: {e.stderr}")

def has_uncommitted_changes(repo_path):
    """Returns True if there are uncommitted changes in the repository."""
    try:
        cmd = ["git", "status", "--porcelain", "--untracked-files=no"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True)
        return bool(result.stdout.strip())
    except subprocess.CalledProcessError:
        return False



