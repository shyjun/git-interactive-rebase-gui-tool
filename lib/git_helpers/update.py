import os
import glob
import subprocess


GIT_REPO_URL = "git+https://github.com/shyjun/git-interactive-rebase-gui-tool.git"


def _run_capture(cwd, args):
    """Run a command, returning (ok, stdout, stderr)."""
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as exc:
        return False, "", str(exc)


def _is_git_install(tool_dir):
    """True if the tool lives in a git clone or worktree (has a .git directory or file)."""
    dot_git = os.path.join(tool_dir, ".git")
    if os.path.isdir(dot_git):
        return True
    if os.path.isfile(dot_git):
        try:
            with open(dot_git, encoding='utf-8') as f:
                return f.read().strip().startswith("gitdir:")
        except OSError:
            pass
    return False


def _read_version_sha():
    """Reads the SHA from app_version.json in the installed assets directory.
    Returns the SHA string or None if not found."""
    try:
        from lib.utils import get_assets_path
        import json
        path = os.path.join(get_assets_path(), "app_version.json")
        print(f"[_read_version_sha] reading {path}")
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
                sha = data.get("sha")
                print(f"[_read_version_sha] found sha={sha}")
                return sha
        print("[_read_version_sha] file not found")
    except Exception as e:
        print(f"[_read_version_sha] error: {e}")
    return None


def _write_app_version(tool_dir, sha):
    """Write a minimal app_version.json into the installed assets directory."""
    import json
    from datetime import datetime, timezone
    assets_dir = os.path.join(tool_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    data = {
        "sha": sha,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "repo": "https://github.com/shyjun/git-interactive-rebase-gui-tool",
    }
    with open(os.path.join(assets_dir, "app_version.json"), "w") as f:
        json.dump(data, f, indent=2)


def _detect_default_branch(repo_path):
    """Returns the default branch name (e.g. 'master' or 'main') of 'origin'."""
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "origin/HEAD"],
                           cwd=repo_path, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', check=True)
        branch = r.stdout.strip()
        if branch.startswith("origin/"):
            return branch.split("/", 1)[1]
        return "master"
    except subprocess.CalledProcessError:
        for candidate in ("master", "main"):
            try:
                subprocess.run(["git", "rev-parse", f"origin/{candidate}"],
                               cwd=repo_path, capture_output=True, text=True, check=True)
                return candidate
            except subprocess.CalledProcessError:
                continue
        return "master"


def build_update_command(tool_dir, is_pip=False):
    """Returns the command line to run for the tool's self-update."""
    if is_pip:
        return "git_interactive_rebase --update"
    script = os.path.join(tool_dir, "git_interactive_rebase.py")
    return f"python3 {script} --update"


def perform_self_update(tool_dir):
    """Updates the tool's own installation in place.

    Returns (ok, message). For git-clone installs the working tree must be
    clean, otherwise the update is aborted without making any changes.
    """
    if not _is_git_install(tool_dir):
        old_sha = _read_version_sha()
        print(f"[perform_self_update] pip path, tool_dir={tool_dir}, old_sha={old_sha}")
        if not old_sha:
            print("[perform_self_update] no version info, installing fresh")
            ok, stdout, stderr = _run_capture(tool_dir, ["pip", "install", "--force-reinstall", "--no-deps", GIT_REPO_URL])
            if ok:
                ls_url = GIT_REPO_URL.removeprefix("git+")
                ok2, stdout2, _ = _run_capture(tool_dir, ["git", "ls-remote", ls_url, "HEAD"])
                sha = stdout2.split()[0] if ok2 and stdout2.strip() else "unknown"
                _write_app_version(tool_dir, sha)
                return True, "Update complete. The tool has been upgraded via pip."
            return False, f"pip install failed:\n{stderr.strip() or stdout.strip() or 'unknown error'}"

        # Fetch remote SHA for up-to-date check
        ls_url = GIT_REPO_URL.removeprefix("git+")
        print(f"[perform_self_update] ls_url={ls_url}")
        ok, stdout, stderr = _run_capture(tool_dir, ["git", "ls-remote", ls_url, "HEAD"])
        print(f"[perform_self_update] ls-remote ok={ok}, stdout={stdout.strip()[:80]}, stderr={stderr.strip()[:80]}")
        if not ok or not stdout.strip():
            return False, f"Could not check remote version:\n{stderr.strip() or stdout.strip() or 'unknown error'}"
        remote_sha = stdout.split()[0]
        print(f"[perform_self_update] local={old_sha[:8] if old_sha else '?'} remote={remote_sha[:8]} match={old_sha == remote_sha}")

        if old_sha == remote_sha:
            return True, f"You are already using the latest version. ({old_sha[:8]})"

        print("[perform_self_update] running pip install --force-reinstall --no-deps")
        ok, stdout, stderr = _run_capture(tool_dir, ["pip", "install", "--force-reinstall", "--no-deps", GIT_REPO_URL])
        print(f"[perform_self_update] pip install ok={ok}")
        if ok:
            # Remove stale .pyc files so the updated .py is used on next launch.
            for pyc in glob.glob(os.path.join(tool_dir, "__pycache__", "git_interactive_rebase*.pyc")):
                try:
                    os.remove(pyc)
                    print(f"[perform_self_update] removed stale pyc: {pyc}")
                except OSError:
                    pass
            new_sha = remote_sha
            _write_app_version(tool_dir, new_sha)
            print(f"[perform_self_update] new_sha={new_sha}")
            return True, f"Update complete.\n\nOld: {old_sha[:8]}\nNew: {new_sha[:8]}\n\nPlease restart the tool for changes to take effect."
        return False, f"pip install failed:\n{stderr.strip() or stdout.strip() or 'unknown error'}"

    # git-clone install
    default_branch = _detect_default_branch(tool_dir)

    ok, stdout, stderr = _run_capture(tool_dir, ["git", "status", "--porcelain"])
    if not ok:
        return False, f"Could not check working tree status:\n{stderr.strip()}"
    if stdout.strip():
        return False, ("The tool's local clone has uncommitted changes, so it was not updated.\n\n"
                       "Please commit or stash them and try again.")

    ok, _, stderr = _run_capture(tool_dir, ["git", "fetch", "origin"])
    if not ok:
        return False, f"git fetch failed:\n{stderr.strip()}"

    ok, stdout, stderr = _run_capture(tool_dir, ["git", "rev-parse", "HEAD"])
    local_sha = stdout.strip() if ok else ""
    ok, stdout, stderr = _run_capture(tool_dir, ["git", "rev-parse", f"origin/{default_branch}"])
    remote_sha = stdout.strip() if ok else ""

    if local_sha and local_sha == remote_sha:
        return True, f"You are already using the latest version. ({local_sha[:8]})"

    ok, _, stderr = _run_capture(tool_dir, ["git", "reset", "--hard", f"origin/{default_branch}"])
    if not ok:
        return False, f"git reset --hard failed:\n{stderr.strip()}"

    ok, stdout, _ = _run_capture(tool_dir, ["git", "rev-parse", "HEAD"])
    new_sha = stdout.strip() if ok else "?"
    return True, f"Update complete.\n\nOld: {local_sha[:8] if local_sha else '?'}\nNew: {new_sha[:8]}"
