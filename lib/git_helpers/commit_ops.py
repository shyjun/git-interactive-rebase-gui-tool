import os
import subprocess
import tempfile


def commit_file(repo_path, filepath, message):
    """Stages and commits a single file.

    Returns (True, "") on success, or (False, detail) where detail carries the
    git error text."""
    try:
        # Stage the file
        subprocess.run(["git", "add", filepath], cwd=repo_path, check=True, capture_output=True)
        # Commit the file
        subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True, capture_output=True)
        return True, ""
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode('utf-8') if e.stderr else str(e)
        print(f"Git commit failed for {filepath}: {err}")
        return False, err

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
    """Stages all modified files and commits them as a single bulk commit.

    Returns (True, "") on success, or (False, detail) where detail carries the
    git error text."""
    try:
        # Stage all changes (excluding untracked files as per --untracked-files=no in checks)
        subprocess.run(["git", "add", "-u"], cwd=repo_path, check=True, capture_output=True)
        # Commit
        subprocess.run(["git", "commit", "-m", message], cwd=repo_path, check=True, capture_output=True)
        return True, ""
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
        return False, err


def amend_with_head(repo_path):
    """Stages all modified files and amends them into the current HEAD commit.

    Returns (True, "") on success, or (False, detail) where detail carries the
    git error text."""
    try:
        before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["git", "add", "-u"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "--amend", "--no-edit"], cwd=repo_path, check=True, capture_output=True)
        after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True, check=True).stdout.strip()
        print(f"Amended HEAD: {before[:8]} -> {after[:8]}")
        return True, ""
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
        return False, err


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
    try:
        with os.fdopen(msg_fd, 'w', encoding='utf-8') as f:
            f.write(message)
        subprocess.run(["git", "commit", "--amend", "-F", msg_path],
                       cwd=repo_path, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode('utf-8') if e.stderr else str(e)
        print(f"git commit --amend failed: {err}")
        return False
    finally:
        try:
            os.unlink(msg_path)
        except OSError:
            pass


def apply_patch_to_index(repo_path, patch_text):
    """Stages the given unified-diff patch with 'git apply --cached',
    so only the hunks present in the patch reach the index.

    On failure the index is reset to HEAD ("git reset -q") so a partial/erroneous
    apply can never leave the index in a half-staged state, then re-raises."""
    if not patch_text.strip():
        return
    patch_fd, patch_path = tempfile.mkstemp(prefix='git_selective_', suffix='.patch', text=True)
    try:
        with os.fdopen(patch_fd, 'w', encoding='utf-8') as pf:
            pf.write(patch_text)
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


def _parse_patch_commit_message(patch_path):
    """Extracts the commit subject (and optional body) from a unified-diff /
    format-patch file. Returns (subject, body) where body may be empty."""
    import re
    default_subject = "Apply patch"
    try:
        with open(patch_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError:
        return default_subject, ""

    lines = content.splitlines()
    subject = None
    body_lines = []
    in_body = False
    for line in lines:
        if line.lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
            subject = re.sub(r'^\[PATCH[^\]]*\]\s*', '', subject).strip()
            in_body = True
            continue
        if in_body and line == "---":
            break
        if in_body:
            body_lines.append(line)

    if subject:
        body = "\n".join(body_lines).strip()
        return subject, body

    body = "\n".join(body_lines).strip()
    if body:
        first = body.splitlines()[0].strip()
        if not first.startswith("diff "):
            return first, "\n".join(body.splitlines()[1:]).strip()
    return default_subject, ""


def _count_format_patch_sections(patch_path):
    """Counts the number of format-patch sections in a file by looking for
    'From ' lines at the start of a line (the format-patch envelope header)."""
    count = 0
    try:
        with open(patch_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith("From ") and " Mon Sep 17 " in line:
                    count += 1
    except OSError:
        pass
    return count


def apply_patch_file(repo_path, patch_path, commit_wanted):
    """Applies a unified-diff patch file to the repository.

    If the patch contains multiple format-patch sections (consolidated patch),
    uses 'git am' to create individual commits for each section, preserving
    each commit's message, author, and date.

    If the patch is a single section, uses 'git apply' with 'git apply --check'
    as a dry run so a failing patch never leaves the repository in a
    partially-applied state.

    If *commit_wanted* is False (single patch only), changes are left unstaged.
    Returns a (ok, detail) tuple; on failure *detail* holds the git error text."""
    if not patch_path or not os.path.isfile(patch_path):
        return False, "Patch file does not exist."

    num_sections = _count_format_patch_sections(patch_path)

    if num_sections > 1 and commit_wanted:
        # Multiple format-patch sections: use git am to create individual commits.
        # git am is safe on failure — nothing is committed until all patches apply.
        try:
            result = subprocess.run(["git", "am", patch_path],
                                    cwd=repo_path, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace')
            if result.returncode != 0:
                subprocess.run(["git", "am", "--abort"], cwd=repo_path,
                               capture_output=True, text=True)
                return False, (result.stderr or "Patch could not be applied.").strip()
        except subprocess.SubprocessError as e:
            subprocess.run(["git", "am", "--abort"], cwd=repo_path,
                           capture_output=True, text=True)
            return False, str(e)
        return True, f"Applied {num_sections} commits from patch."

    # Single patch section (or commit_wanted=False): use git apply
    try:
        check = subprocess.run(["git", "apply", "--check", "--ignore-whitespace", patch_path],
                               cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if check.returncode != 0:
            return False, (check.stderr or "Patch does not apply cleanly.").strip()
        apply = subprocess.run(["git", "apply", "--ignore-whitespace", patch_path],
                               cwd=repo_path, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if apply.returncode != 0:
            return False, (apply.stderr or "Patch could not be applied.").strip()
    except subprocess.SubprocessError as e:
        return False, str(e)

    if not commit_wanted:
        return True, "Changes left unstaged in the working tree."

    try:
        subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True,
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    except subprocess.CalledProcessError as e:
        return False, f"Patch applied but could not stage changes: {e.stderr}"

    subject, body = _parse_patch_commit_message(patch_path)
    msg_fd, msg_path = tempfile.mkstemp(prefix='git_apply_patch_', text=True)
    try:
        with os.fdopen(msg_fd, 'w', encoding='utf-8') as f:
            f.write(subject + ("\n\n" + body if body else ""))
        try:
            subprocess.run(["git", "commit", "-F", msg_path], cwd=repo_path, check=True,
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        except subprocess.CalledProcessError as e:
            return False, f"Patch applied but could not commit: {e.stderr}"
    finally:
        try:
            os.unlink(msg_path)
        except OSError:
            pass
    return True, f"Changes committed with message: {subject}"
