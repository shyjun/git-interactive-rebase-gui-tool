import re
import subprocess
from datetime import datetime


def _parse_blame_porcelain(stdout):
    """Parse ``git blame --porcelain`` output into a list of blame records.

    Each record is a dict with keys:
        sha, line_no, author, author_time, author_tz, summary, code
    """
    records = []
    current = None

    for raw_line in stdout.split("\n"):
        m = re.match(r"^([0-9a-f]{40})\s+(\d+)\s+(\d+)\s*(.*)$", raw_line)
        if m:
            if current is not None:
                records.append(current)
            current = {
                "sha": m.group(1),
                "orig_line": int(m.group(2)),
                "line_no": int(m.group(3)),
                "count": int(m.group(4)) if m.group(4) else 1,
                "author": "",
                "author_time": 0,
                "author_tz": "",
                "summary": "",
                "code": "",
            }
            continue

        if current is None:
            continue

        if raw_line.startswith("author "):
            current["author"] = raw_line[len("author "):]
        elif raw_line.startswith("author-time "):
            try:
                current["author_time"] = int(raw_line[len("author-time "):])
            except ValueError:
                pass
        elif raw_line.startswith("author-tz "):
            current["author_tz"] = raw_line[len("author-tz "):]
        elif raw_line.startswith("summary "):
            current["summary"] = raw_line[len("summary "):]
        elif raw_line.startswith("\t"):
            current["code"] = raw_line[1:]

    if current is not None:
        records.append(current)

    for rec in records:
        try:
            dt = datetime.fromtimestamp(rec["author_time"])
            rec["date"] = dt.strftime("%d %b %Y %H:%M")
        except Exception:
            rec["date"] = ""

    return records


def get_git_blame(repo_path, filepath, ref=None):
    """Run ``git blame --porcelain`` on *filepath* and return parsed records."""
    cmd = ["git", "blame", "--porcelain"]
    if ref:
        cmd.append(ref)
    cmd.extend(["--", filepath])

    result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise Exception(f"git blame failed: {result.stderr.strip()}")
    return _parse_blame_porcelain(result.stdout)
