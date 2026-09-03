import re
import subprocess

from .core import _git_capture, _pad_diff_separators


def get_staged_diff(repo_path):
    """Returns the diff of all staged changes."""
    try:
        cmd = ["git", "diff", "--cached"]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True,
                                encoding='utf-8', errors='replace')
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to get staged diff: {e.stderr}")


def get_merge_base(repo_path, ref):
    """Returns the merge-base of HEAD with *ref* (e.g. 'origin/main').

    Returns None when the branches share no common ancestor. A genuine git
    failure (anything but the 'no common ancestor' exit code 1) raises an
    Exception carrying git's stderr."""
    try:
        cmd = ["git", "merge-base", "HEAD", ref]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        sha = result.stdout.strip()
        return sha if sha else None
    except subprocess.CalledProcessError as e:
        if e.returncode == 1:
            return None
        raise Exception(f"Failed to find merge-base: {e.stderr}")


def get_diff_between(repo_path, start_sha, end_sha):
    """Fetches the combined diff of all changes between *start_sha* and *end_sha*."""
    try:
        cmd = ["git", "diff", start_sha, end_sha]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to fetch branch diff: {e.stderr}")


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
    return _pad_diff_separators(
        _git_capture(repo_path, ["git", "diff", start_sha, end_sha, "--", filepath],
                     "Failed to get file diff"))


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
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"[git_helpers] get_file_stats_between: git diff --numstat failed between {start_sha} and {end_sha}: {err}")
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
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"[git_helpers] get_unstaged_file_stats: git diff --numstat failed: {err}")
        return {}


def get_staged_file_stats(repo_path):
    """Returns a dict mapping filepath -> (added_lines, deleted_lines) for staged changes."""
    try:
        cmd = ["git", "diff", "--cached", "--numstat"]
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
    except subprocess.CalledProcessError as exc:
        err = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"[git_helpers] get_staged_file_stats: git diff --cached --numstat failed: {err}")
        return {}


def get_unstaged_file_diff(repo_path, filepath):
    """Returns the diff for a single file's unstaged changes."""
    return _pad_diff_separators(
        _git_capture(repo_path, ["git", "diff", "--", filepath],
                     "Failed to get unstaged file diff"))


def get_staged_file_diff(repo_path, filepath):
    """Returns the diff for a single file's staged changes."""
    return _pad_diff_separators(
        _git_capture(repo_path, ["git", "diff", "--cached", "--", filepath],
                     "Failed to get staged file diff"))


def _get_git_version(repo_path):
    """Returns (major, minor, patch) tuple of the git version, or (0,0,0)."""
    try:
        result = subprocess.run(
            ["git", "version"],
            cwd=repo_path, capture_output=True, text=True,
            encoding='utf-8', errors='replace')
        # "git version 2.46.0" or "git version 2.46.0.windows.1"
        import re
        m = re.search(r'(\d+)\.(\d+)\.(\d+)', result.stdout)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        pass
    return (0, 0, 0)


def get_difftool_name(repo_path):
    """Returns the configured diff.tool name, or None if not set."""
    try:
        ver = _get_git_version(repo_path)
        if ver >= (2, 46, 0):
            cmd = ["git", "config", "get", "diff.tool"]
        else:
            cmd = ["git", "config", "--get", "diff.tool"]
        result = subprocess.run(
            cmd, cwd=repo_path, capture_output=True, text=True,
            encoding='utf-8', errors='replace')
        name = result.stdout.strip()
        return name if name else None
    except Exception:
        return None


def is_file_unchanged_between(repo_path, filepath, commit_sha, head_sha):
    """Returns True if *filepath* has not changed between *commit_sha* and *head_sha*."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", commit_sha, head_sha, "--", filepath],
            cwd=repo_path, capture_output=True, text=True,
            encoding='utf-8', errors='replace')
        return not result.stdout.strip()
    except Exception:
        return False


def is_file_working_tree_clean(repo_path, filepath):
    """Returns True if *filepath* has no staged or unstaged changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", filepath],
            cwd=repo_path, capture_output=True, text=True,
            encoding='utf-8', errors='replace')
        return not result.stdout.strip()
    except Exception:
        return False


def run_difftool_temp_files(repo_path, source_sha, source_file, dest_sha, dest_file):
    """Extract both file versions to temp files and open the configured difftool.

    Returns (ok, message) where message is an error description on failure."""
    import os
    import tempfile
    try:
        # Extract source version
        result = subprocess.run(
            ["git", "show", f"{source_sha}:{source_file}"],
            cwd=repo_path, capture_output=True, text=True,
            encoding='utf-8', errors='replace')
        if result.returncode != 0:
            print(f"[difftool] Failed to extract source: {result.stderr}")
            return False, f"Could not extract source file: {result.stderr}"
        src_data = result.stdout

        # Extract destination version
        result = subprocess.run(
            ["git", "show", f"{dest_sha}:{dest_file}"],
            cwd=repo_path, capture_output=True, text=True,
            encoding='utf-8', errors='replace')
        if result.returncode != 0:
            print(f"[difftool] Failed to extract dest: {result.stderr}")
            return False, f"Could not extract destination file: {result.stderr}"
        dst_data = result.stdout

        # Write to temp files (separate dirs to avoid same-basename collision)
        src_tmp = tempfile.mkdtemp(prefix="git-difftool-src-")
        dst_tmp = tempfile.mkdtemp(prefix="git-difftool-dst-")
        src_path = os.path.join(src_tmp, os.path.basename(source_file))
        dst_path = os.path.join(dst_tmp, os.path.basename(dest_file))
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(src_data)
        with open(dst_path, 'w', encoding='utf-8') as f:
            f.write(dst_data)

        # Run difftool
        cmd = ["git", "difftool", "--no-index", "--", src_path, dst_path]
        print(f"[difftool] Running: {' '.join(cmd)}")
        subprocess.Popen(cmd, cwd=repo_path)
        return True, ""
    except Exception as e:
        print(f"[difftool] Exception: {e}")
        return False, str(e)


def run_difftool_direct(repo_path, source_sha, source_file, dest_sha, dest_file,
                        source_is_head=False):
    """Run configured difftool comparing two file versions.

    When source_is_head is True and source == HEAD, uses the actual repo file
    (working tree) as source and only extracts the destination to a temp file.
    Otherwise falls back to git difftool between two commits.

    Returns (ok, message) where message is an error description on failure."""
    import os
    import shlex
    import tempfile
    from PySide6.QtCore import QSettings
    try:
        settings = QSettings("git-interactive-rebase-gui-tool", "config")
        mode = settings.value("difftool/mode", "none")
        custom_cmd = settings.value("difftool/command", "") if mode == "custom" else ""

        if source_is_head:
            # Source is the working tree file — extract only dest
            result = subprocess.run(
                ["git", "show", f"{dest_sha}:{dest_file}"],
                cwd=repo_path, capture_output=True, text=True,
                encoding='utf-8', errors='replace')
            if result.returncode != 0:
                return False, f"Could not extract destination file: {result.stderr}"
            dst_tmp = tempfile.mkdtemp(prefix="git-difftool-dst-")
            dst_path = os.path.join(dst_tmp, os.path.basename(dest_file))
            with open(dst_path, 'w', encoding='utf-8') as f:
                f.write(result.stdout)
            src_path = os.path.join(repo_path, source_file)

            if custom_cmd:
                args_template = settings.value("difftool/args", "{file1} {file2}")
                if not args_template or "{file1}" not in args_template:
                    args_template = "{file1} {file2}"
                args_str = args_template.replace("{file1}", src_path).replace("{file2}", dst_path)
                cmd_parts = shlex.split(custom_cmd) + shlex.split(args_str)
            else:
                cmd_parts = ["git", "difftool", "--no-index", "--", src_path, dst_path]
            print(f"[direct] Running: {' '.join(cmd_parts)}")
            subprocess.Popen(cmd_parts, cwd=repo_path)
        else:
            cmd = ["git", "difftool", source_sha, dest_sha, "--", source_file]
            print(f"[direct] Running: {' '.join(cmd)}")
            subprocess.Popen(cmd, cwd=repo_path)
        return True, ""
    except Exception as e:
        return False, str(e)


def run_configured_difftool(repo_path, source_sha, source_file, dest_sha, dest_file):
    """Run the user-configured difftool (Git or custom) on two file versions.

    Reads the difftool configuration from QSettings. If custom command is set,
    extracts files to temp and runs the custom command. Otherwise falls back to
    git difftool.

    Returns (ok, message) where message is an error description on failure.
    """
    from PySide6.QtCore import QSettings
    settings = QSettings("git-interactive-rebase-gui-tool", "config")
    mode = settings.value("difftool/mode", "none")
    command = settings.value("difftool/command", "")
    print(f"[configured-difftool] mode={mode}, command={command!r}")

    if mode == "custom" and command:
        print(f"[configured-difftool] using custom: {command}")
        return _run_custom_difftool(
            repo_path, command, settings.value("difftool/args", "{file1} {file2}"),
            source_sha, source_file, dest_sha, dest_file)

    # Fall back to git difftool
    print("[configured-difftool] falling back to git difftool")
    return run_difftool_temp_files(repo_path, source_sha, source_file, dest_sha, dest_file)


def _run_custom_difftool(repo_path, command, args_template,
                          source_sha, source_file, dest_sha, dest_file):
    """Run a custom diff tool command on two extracted file versions."""
    import os
    import shlex
    import tempfile
    try:
        # Extract source version
        result = subprocess.run(
            ["git", "show", f"{source_sha}:{source_file}"],
            cwd=repo_path, capture_output=True, text=True,
            encoding='utf-8', errors='replace')
        if result.returncode != 0:
            return False, f"Could not extract source file: {result.stderr}"
        src_data = result.stdout

        # Extract destination version
        result = subprocess.run(
            ["git", "show", f"{dest_sha}:{dest_file}"],
            cwd=repo_path, capture_output=True, text=True,
            encoding='utf-8', errors='replace')
        if result.returncode != 0:
            return False, f"Could not extract destination file: {result.stderr}"
        dst_data = result.stdout

        # Write to temp files (separate dirs to avoid same-basename collision)
        src_tmp = tempfile.mkdtemp(prefix="git-difftool-src-")
        dst_tmp = tempfile.mkdtemp(prefix="git-difftool-dst-")
        src_path = os.path.join(src_tmp, os.path.basename(source_file))
        dst_path = os.path.join(dst_tmp, os.path.basename(dest_file))
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(src_data)
        with open(dst_path, 'w', encoding='utf-8') as f:
            f.write(dst_data)

        # Build command
        if not args_template or "{file1}" not in args_template:
            args_template = "{file1} {file2}"
        args_str = args_template.replace("{file1}", src_path).replace("{file2}", dst_path)
        cmd_parts = shlex.split(command) + shlex.split(args_str)
        print(f"[custom-difftool] Running: {' '.join(cmd_parts)}")
        subprocess.Popen(cmd_parts, cwd=repo_path)
        return True, ""
    except Exception as e:
        return False, str(e)
