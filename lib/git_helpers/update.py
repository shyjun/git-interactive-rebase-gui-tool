import os
import glob
import shlex
import logging
import subprocess

_log = logging.getLogger(__name__)

GIT_REPO_URL = "git+https://github.com/shyjun/git-interactive-rebase-gui-tool.git"

# Default timeout (seconds) for all network-facing subprocess calls.
_NET_TIMEOUT = 60


def _run_capture(cwd, args, timeout=_NET_TIMEOUT):
    """Run a command, returning (ok, stdout, stderr).

    Never raises; a timeout or OS error is returned as an error tuple.
    """
    try:
        result = subprocess.run(
            args, cwd=cwd,
            capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            timeout=timeout,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s: {' '.join(str(a) for a in args)}"
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
        _log.debug("_read_version_sha: reading %s", path)
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
                sha = data.get("sha")
                _log.debug("_read_version_sha: found sha=%s", sha)
                return sha
        _log.debug("_read_version_sha: file not found")
    except Exception as e:
        _log.debug("_read_version_sha: error: %s", e)
    return None


def _write_app_version(sha):
    """Write a minimal app_version.json into the installed assets directory.
    Uses get_assets_path() to find the correct location."""
    import json
    from datetime import datetime, timezone
    from lib.utils import get_assets_path
    assets_dir = get_assets_path()
    os.makedirs(assets_dir, exist_ok=True)
    data = {
        "sha": sha,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "repo": "https://github.com/shyjun/git-interactive-rebase-gui-tool",
    }
    # BUG-4 fix: always write UTF-8, regardless of system locale.
    with open(os.path.join(assets_dir, "app_version.json"), "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def _detect_default_branch(repo_path):
    """Returns (remote_name, branch_name) for the default branch.
    Prefers the remote pointing to the canonical repo URL."""
    remotes = []
    canonical_remote = None

    # BUG-6 fix: do NOT use check=True; check returncode manually so that
    # a non-zero exit from 'git remote -v' doesn't silently discard the
    # canonical-remote detection via the outer except-block fallback.
    r = subprocess.run(
        ["git", "remote", "-v"],
        cwd=repo_path, capture_output=True, text=True,
        encoding='utf-8', errors='replace',
    )
    if r.returncode == 0:
        seen = set()
        for line in r.stdout.strip().split('\n'):
            parts = line.split()
            if parts and parts[0] not in seen:
                seen.add(parts[0])
                if "shyjun/git-interactive-rebase-gui-tool" in line:
                    canonical_remote = parts[0]
                remotes.append(parts[0])
    else:
        _log.debug("_detect_default_branch: git remote -v failed: %s", r.stderr.strip())
        remotes = ["origin"]

    # BUG-10 fix: deduplicate while preserving priority order so that the
    # canonical remote is tried once (first), not twice.
    seen_order: dict[str, None] = {}
    for remote in ([canonical_remote] if canonical_remote else []) + remotes + ["origin"]:
        if remote:
            seen_order[remote] = None
    ordered = list(seen_order.keys())

    for remote in ordered:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", f"{remote}/HEAD"],
                cwd=repo_path, capture_output=True, text=True,
                encoding='utf-8', errors='replace', check=True,
            )
            branch = r.stdout.strip()
            if branch.startswith(f"{remote}/"):
                return remote, branch.split("/", 1)[1]
            return remote, "master"
        except subprocess.CalledProcessError:
            for candidate in ("master", "main"):
                try:
                    subprocess.run(
                        ["git", "rev-parse", f"{remote}/{candidate}"],
                        cwd=repo_path, capture_output=True, text=True, check=True,
                    )
                    return remote, candidate
                except subprocess.CalledProcessError:
                    continue
    return "origin", "master"


def build_update_command(tool_dir, is_pip=False):
    """Returns the command line to run for the tool's self-update."""
    if is_pip:
        return "git_interactive_rebase --update"
    script = os.path.join(tool_dir, "git_interactive_rebase.py")
    # BUG-16 fix: quote the path so spaces in tool_dir don't break the command.
    return f"python3 {shlex.quote(script)} --update"


def perform_self_update(tool_dir):
    """Updates the tool's own installation in place.

    Returns (ok, message). For git-clone installs the working tree must be
    clean, otherwise the update is aborted without making any changes.
    """
    if not _is_git_install(tool_dir):
        old_sha = _read_version_sha()
        _log.info("perform_self_update: pip path, tool_dir=%s, old_sha=%s", tool_dir, old_sha)
        if not old_sha:
            _log.info("perform_self_update: no version info, installing fresh")
            ok, stdout, stderr = _run_capture(tool_dir, ["pip", "install", "--force-reinstall", "--no-deps", GIT_REPO_URL])
            if ok:
                ls_url = GIT_REPO_URL.removeprefix("git+")
                ok2, stdout2, _ = _run_capture(tool_dir, ["git", "ls-remote", ls_url, "HEAD"])
                sha = stdout2.split()[0] if ok2 and stdout2.strip() else "unknown"
                _write_app_version(sha)
                return True, "Update complete. The tool has been upgraded via pip."
            return False, f"pip install failed:\n{stderr.strip() or stdout.strip() or 'unknown error'}"

        # Fetch remote SHA for up-to-date check
        ls_url = GIT_REPO_URL.removeprefix("git+")
        _log.debug("perform_self_update: ls_url=%s", ls_url)
        ok, stdout, stderr = _run_capture(tool_dir, ["git", "ls-remote", ls_url, "HEAD"])
        _log.debug("perform_self_update: ls-remote ok=%s stdout=%s stderr=%s", ok, stdout.strip()[:80], stderr.strip()[:80])
        if not ok or not stdout.strip():
            return False, f"Could not check remote version:\n{stderr.strip() or stdout.strip() or 'unknown error'}"
        remote_sha = stdout.split()[0]
        _log.info("perform_self_update: local=%s remote=%s match=%s",
                  old_sha[:8] if old_sha else "?", remote_sha[:8], old_sha == remote_sha)

        if old_sha == remote_sha:
            return True, f"You are already using the latest version. ({old_sha[:8]})"

        _log.info("perform_self_update: running pip install --force-reinstall --no-deps")
        ok, stdout, stderr = _run_capture(
            tool_dir,
            ["pip", "install", "--force-reinstall", "--no-deps", GIT_REPO_URL],
            timeout=300,  # pip installs can take longer
        )
        _log.info("perform_self_update: pip install ok=%s", ok)
        if ok:
            # BUG-7 fix: clean stale .pyc files from the ENTIRE installation
            # subtree, not just the top-level script's __pycache__.
            from lib.utils import get_assets_path
            assets_dir = get_assets_path()
            site_packages_dir = os.path.dirname(assets_dir)
            removed = 0
            for pyc in glob.glob(os.path.join(site_packages_dir, "**", "*.pyc"), recursive=True):
                try:
                    os.remove(pyc)
                    removed += 1
                    _log.debug("perform_self_update: removed stale pyc: %s", pyc)
                except OSError:
                    pass
            _log.info("perform_self_update: removed %d stale .pyc files", removed)
            new_sha = remote_sha
            _write_app_version(new_sha)
            _log.info("perform_self_update: new_sha=%s", new_sha)
            return True, f"Update complete.\n\nOld: {old_sha[:8]}\nNew: {new_sha[:8]}"
        return False, f"pip install failed:\n{stderr.strip() or stdout.strip() or 'unknown error'}"

    # git-clone install
    git_remote, default_branch = _detect_default_branch(tool_dir)

    ok, stdout, stderr = _run_capture(tool_dir, ["git", "status", "--porcelain"])
    if not ok:
        return False, f"Could not check working tree status:\n{stderr.strip()}"
    if stdout.strip():
        return False, (
            "The tool's local clone has uncommitted changes, so it was not updated.\n\n"
            "Please commit or stash them and try again."
        )

    ok, _, stderr = _run_capture(tool_dir, ["git", "fetch", git_remote])
    if not ok:
        return False, f"git fetch failed:\n{stderr.strip()}"

    ok, stdout, stderr = _run_capture(tool_dir, ["git", "rev-parse", "HEAD"])
    local_sha = stdout.strip() if ok else ""

    # BUG-2 fix: validate remote_sha before allowing git reset --hard.
    ok, stdout, stderr = _run_capture(tool_dir, ["git", "rev-parse", f"{git_remote}/{default_branch}"])
    if not ok or not stdout.strip():
        return False, (
            f"Could not resolve remote ref '{git_remote}/{default_branch}'.\n"
            f"The fetch may have succeeded but the branch tracking ref is missing.\n"
            f"{stderr.strip()}"
        )
    remote_sha = stdout.strip()

    if local_sha and local_sha == remote_sha:
        return True, f"You are already using the latest version. ({local_sha[:8]})"

    ok, _, stderr = _run_capture(tool_dir, ["git", "reset", "--hard", f"{git_remote}/{default_branch}"])
    if not ok:
        return False, f"git reset --hard failed:\n{stderr.strip()}"

    ok, stdout, _ = _run_capture(tool_dir, ["git", "rev-parse", "HEAD"])
    new_sha = stdout.strip() if ok else "?"
    return True, f"Update complete.\n\nOld: {local_sha[:8] if local_sha else '?'}\nNew: {new_sha[:8]}"
