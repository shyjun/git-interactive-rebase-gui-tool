import re
import subprocess


def _parse_log_records(stdout):
    """Parses `git log --shortstat` output (pipe-separated records) into commit dicts."""
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
        # --shortstat corrupts the \x1e record boundaries (its lines land on the
        # next record's SHA key), so drop it before building the message-only command.
        msg_cmd = [arg for arg in log_cmd if arg != "--shortstat"]
        if "--" in msg_cmd:
            idx = msg_cmd.index("--")
            msg_cmd = msg_cmd[:idx] + ["--format=%h%x1f%B%x1e"] + msg_cmd[idx:]
        else:
            msg_cmd += ["--format=%h%x1f%B%x1e"]
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

def _parse_reflog_records(stdout):
    """Parses ``git reflog --format="%h|%gd|%gs"`` output into commit-like dicts.

    Each output line has the shape ``sha|selector|subject`` (e.g.
    ``c9bbbc4|HEAD@{0}|commit: Fix bug``). Returns a list of dicts matching the
    shape used by the commit list widget, with the SHA as the first token of
    ``raw_text`` so existing SHA-extraction logic keeps working.
    """
    commits = []
    for line in stdout.split('\n'):
        line = line.strip()
        if not line:
            continue
        parts = line.split('|', 2)
        if len(parts) < 3:
            continue
        sha, selector, subject = parts
        commits.append({
            "sha": sha,
            "selector": selector,
            "message": subject,
            "date": "",
            "author": "",
            "parents": "",
            "added": 0,
            "deleted": 0,
            "raw_text": f"{sha} {selector}: {subject}",
        })
    return commits

def _parse_stash_records(stdout):
    """Parses ``git stash list --format="%H|%gd|%gs"`` output into commit-like
    dicts.

    Each output line has the shape ``sha|selector|subject`` (e.g.
    ``9705acdffbaa2148e4a2462140c7380d474b3b33|stash@{0}|On master: wip feature``).
    Returns a list of dicts matching the shape used by the commit list widget,
    with the stash SHA as the first token of ``raw_text`` so existing SHA-
    extraction logic keeps working.
    """
    commits = []
    for line in stdout.split('\n'):
        line = line.strip()
        if not line:
            continue
        parts = line.split('|', 2)
        if len(parts) < 3:
            continue
        sha, selector, subject = parts
        commits.append({
            "sha": sha,
            "selector": selector,
            "message": subject,
            "date": "",
            "author": "",
            "parents": "",
            "added": 0,
            "deleted": 0,
            "raw_text": f"{sha} {selector}: {subject}",
        })
    return commits

def _git_capture(repo_path, cmd, error_msg):
    """Run git *cmd* in *repo_path*, returning stdout decoded as UTF-8 text.

    On a non-zero exit, raises an Exception carrying git's stderr, mirroring
    the historical behavior of the diff helpers."""
    try:
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True,
                                check=True, encoding='utf-8', errors='replace')
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise Exception(f"{error_msg}: {e.stderr}")


def _pad_diff_separators(diff_text):
    """Insert a blank line before each 'diff --git' block (except at the start)."""
    return re.sub(r'(\n)(diff --git )', r'\1\n\2', diff_text)
