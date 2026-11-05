import re
import subprocess
from lib.logger import _log


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
    """Parse ``git log --format=...%x1f%B%x1f%D%x1e --shortstat`` in one pass.

    Returns (commits, tag_map) where tag_map maps commit sha to a list of tag
    names extracted from the ``%D`` decorator field.
    """
    stat_re = re.compile(
        r'\s*\d+\s+files?\s+changed(?:,\s+(\d+)\s+insertions?\(\+\))?(?:,\s+(\d+)\s+deletions?\(-\))?'
    )

    commits = []
    tag_map = {}

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
        # Split all \x1f-separated fields.  Format is:
        #   sha (in pre) | full_sha | date | author | subject | parents | body | decorate\x1e...
        # So after splitting post on \x1f we get:
        #   [full_sha, date, author, subject, parents, body, decorate\x1e...]
        all_fields = post.split('\x1f')
        if len(all_fields) < 6:
            continue

        sha = pre.strip().split('\n')[-1].strip()
        if not sha or len(sha) < 7:
            continue

        full_sha = all_fields[0].strip()  # %H: full 40-char SHA
        date = all_fields[1].strip()
        author = all_fields[2].strip()
        subject = all_fields[3].strip()
        parents = all_fields[4].strip()
        # Body is field 5; may span multiple lines
        body = all_fields[5].strip() if len(all_fields) > 5 else ""
        # Decorate is field 6 (after body, before \x1e)
        decorate = ""
        if len(all_fields) > 6:
            decorate = all_fields[6].split('\x1e')[0].strip().split('\n')[0].strip()

        # Parse tags from decorate string
        if decorate:
            for part in decorate.split(','):
                part = part.strip()
                if part.startswith('tag: '):
                    tag_map.setdefault(sha, []).append(part[5:])

        # Attach the stat extracted from this chunk's leading lines to the
        # PREVIOUS commit (chunk N's stat belongs to chunk N-1's commit).
        if commits and (added + deleted > 0):
            commits[-1]["added"] = added
            commits[-1]["deleted"] = deleted

        commits.append({
            "sha": sha,
            "full_sha": full_sha or sha,  # fall back to short sha if %H absent
            "date": date,
            "author": author,
            "message": body if body else subject,
            "parents": parents,
            "added": 0,
            "deleted": 0,
            "raw_text": f"{sha} {subject}",
        })

    return commits, tag_map


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

def _git_capture(repo_path, cmd, error_msg, timeout=15):
    """Run git *cmd* in *repo_path*, returning stdout decoded as UTF-8 text.

    On a non-zero exit or timeout, raises an Exception carrying git's stderr."""
    try:
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True,
                                check=True, encoding='utf-8', errors='replace', timeout=timeout)
        return result.stdout
    except subprocess.TimeoutExpired:
        raise Exception(f"{error_msg}: command timed out after {timeout}s")
    except subprocess.CalledProcessError as e:
        raise Exception(f"{error_msg}: {e.stderr}")


def _pad_diff_separators(diff_text):
    """Insert a blank line before each 'diff --git' block (except at the start)."""
    return re.sub(r'(\n)(diff --git )', r'\1\n\2', diff_text)


def _parse_numstat_z(output):
    """Parse ``git <show|diff> --numstat -z`` output into records.

    Returns a list of ``(added, deleted, old_path, path)`` tuples where
    ``added``/``deleted`` are ints (``None`` for binary files, reported as
    ``-``), ``old_path`` is the source path for renames (``None`` otherwise)
    and ``path`` is the destination path.

    Record layouts (each NUL-terminated):

    - regular: ``added<TAB>deleted<TAB>path<NUL>``
    - rename:  ``added<TAB>deleted<TAB><NUL>old<NUL>new<NUL>``

    The NUL directly after the second TAB is the rename marker.  Splitting on
    NUL first (rather than on tabs) keeps paths containing tabs intact.
    """

    def count(value):
        try:
            return int(value)
        except ValueError:
            return None  # binary files report '-'

    records = []
    fields = output.split("\0")
    i, n = 0, len(fields)
    while i < n:
        field = fields[i]
        if not field:
            i += 1
            continue
        parts = field.split("\t")
        if len(parts) < 3:
            i += 1
            continue  # not a numstat header; ignore defensively
        if len(parts) == 3 and parts[2] == "":
            # rename marker; old and new paths follow as NUL-separated fields
            if i + 2 < n and fields[i + 1]:
                records.append((count(parts[0]), count(parts[1]),
                                fields[i + 1], fields[i + 2]))
                i += 3
            else:
                i += 1
        else:
            records.append((count(parts[0]), count(parts[1]), None,
                            "\t".join(parts[2:])))
            i += 1
    return records


def _stats_from_numstat(records, old_size_fn, new_size_fn):
    """Turn numstat *records* into the stats dict the UI reads.

    Returns ``(stats, binary_paths)``:

    - text files are keyed by path: ``(added, deleted, 0, 0)``
    - renames are keyed BOTH by the UI contract ``"old => new"`` (what every
      file-list lookup builds) and by the new path, with identical values
    - binary renames get ``(0, 0, old_size, new_size)`` resolved through the
      size callbacks; plain binary paths are returned in *binary_paths* for
      the caller to fill in
    """
    stats = {}
    binary_paths = []
    for added, deleted, old_path, path in records:
        if old_path:
            if added is None:  # binary rename
                value = (0, 0, old_size_fn(old_path), new_size_fn(path))
            else:
                value = (added, deleted, 0, 0)
            stats[f"{old_path} => {path}"] = value
            stats[path] = value
        elif added is None:
            binary_paths.append(path)
        else:
            stats[path] = (added, deleted, 0, 0)
    return stats, binary_paths


def _apply_mode_changes(stats, mode_map, records):
    """Merge ``(old_mode, new_mode)`` pairs into *stats* (in place).

    Keys are paths, so renames need extra care: the mode map carries the old
    and new path of a rename, but the stats dict keys renames by contract and
    new path only.  The old path is skipped (its rename keys are stamped
    instead), and mode changes on a new path are also applied to the
    ``"old => new"`` contract key so both keys stay identical.
    """
    contract_by_new = {new: f"{old} => {new}"
                       for _, _, old, new in records if old}
    old_paths = {old for _, _, old, _ in records if old}
    for filepath, (old_mode, new_mode) in mode_map.items():
        if filepath not in stats and filepath in old_paths:
            continue  # rename source; stamp the rename keys below
        s = stats.get(filepath)
        if s:
            stats[filepath] = (s[0], s[1], s[2], s[3], old_mode, new_mode)
        else:
            stats[filepath] = (0, 0, 0, 0, old_mode, new_mode)
        contract = contract_by_new.get(filepath)
        if contract and contract in stats:
            c = stats[contract]
            stats[contract] = (c[0], c[1], c[2], c[3], old_mode, new_mode)
