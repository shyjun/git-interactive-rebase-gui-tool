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

def _parse_combined_log(stdout):
    """Parse ``git log --format=...%x1f%B%x1e --shortstat`` in one pass.

    Combines the old _parse_log_records + _attach_full_messages into a single
    subprocess call.  Format fields are separated by ``\\x1f``; records are
    terminated by ``\\x1e``; shortstat lines appear between records.

    Chunk layout after splitting on ``\\x1e`` (for N commits):
      chunk 0: ``sha\\x1fdate\\x1fauthor\\x1fsubject\\x1fparents\\x1fbody``
      chunk 1..N-1: ``\\n\\n<shortstat for prev>\\n<next_sha>\\x1f...``
      chunk N: ``\\n\\n<shortstat for last>``

    The shortstat in chunk N belongs to the commit parsed from chunk N-1.
    """
    stat_re = re.compile(
        r'\s*\d+\s+files?\s+changed(?:,\s+(\d+)\s+insertions?\(\+\))?(?:,\s+(\d+)\s+deletions?\(-\))?'
    )

    commits = []

    chunks = stdout.split('\x1e')

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        added, deleted = 0, 0

        # ---- extract shortstat from leading lines (before first \x1f) ----
        has_fields = '\x1f' in chunk
        if has_fields:
            pre, post = chunk.split('\x1f', 1)
        else:
            pre, post = chunk, ""

        for line in pre.split('\n'):
            m = stat_re.search(line)
            if m:
                added = int(m.group(1)) if m.group(1) else 0
                deleted = int(m.group(2)) if m.group(2) else 0

        if not has_fields:
            # Trailing shortstat-only chunk — applies to the last commit
            if commits and added + deleted > 0:
                commits[-1]["added"] = added
                commits[-1]["deleted"] = deleted
            continue

        # ---- we have format fields — this is a new commit ----
        fields = post.split('\x1f')
        # fields: [date, author, subject, parents, body…]
        if len(fields) < 5:
            continue

        # SHA is the last token on the last line before the first \x1f
        sha = pre.strip().split('\n')[-1].strip()
        if not sha or len(sha) < 7:
            continue

        date = fields[0].strip()
        author = fields[1].strip()
        subject = fields[2].strip()
        parents = fields[3].strip()
        body = '\x1f'.join(fields[4:]).strip()

        commits.append({
            "sha": sha,
            "date": date,
            "author": author,
            "message": body if body else subject,
            "parents": parents,
            "added": 0,  # filled from next chunk's pending_stat
            "deleted": 0,
            "raw_text": f"{sha} {subject}",
        })

        # Now attach the stat extracted above to the *previous* commit
        # (chunk N's leading stat belongs to the commit parsed in chunk N-1)
        if len(commits) > 1 and (added + deleted > 0):
            commits[-2]["added"] = added
            commits[-2]["deleted"] = deleted

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
