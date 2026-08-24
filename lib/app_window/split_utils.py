import re


def parse_hunks(diff_text):
    """
    Parse a unified diff (for one file) into a list of (header_line, body_text) tuples.
    header_line: the '@@ … @@' line (stripped)
    body_text:   the context/+/- lines that follow, as a single string
    """
    hunks = []
    current_header = None
    current_body_lines = []
    for line in diff_text.splitlines():
        if line.startswith("@@"):
            if current_header is not None:
                hunks.append((current_header, "\n".join(current_body_lines)))
            current_header = line
            current_body_lines = []
        elif current_header is not None:
            current_body_lines.append(line)
    if current_header is not None:
        hunks.append((current_header, "\n".join(current_body_lines)))
    return hunks


def patch_has_changes(patch_text):
    """Return True if the patch still contains any added/removed content lines."""
    for line in patch_text.splitlines():
        if line.startswith(('+++', '---')):
            continue
        if line.startswith(('+', '-')):
            return True
    return False


def rebuild_patch(diff_header_text, all_hunks, kept_indices):
    """
    Build a minimal unified-diff patch string that contains only the kept hunks.
    Recalculates the +line offsets so 'git apply' accepts the patch cleanly.

    diff_header_text: the part of the diff before the first @@ (diff --git / --- / +++)
    all_hunks:        list of (header_line, body_text) for ALL hunks
    kept_indices:     indices into all_hunks that should appear in the result
    """
    if not kept_indices:
        return ""

    patch_parts = [diff_header_text]
    cumulative_offset = 0
    for idx in kept_indices:
        orig_hdr, body = all_hunks[idx]
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", orig_hdr)
        if not m:
            patch_parts.append(orig_hdr)
            patch_parts.append(body)
            continue

        minus_start = int(m.group(1))
        plus_start  = int(m.group(3))
        orig_plus_count = int(m.group(4)) if m.group(4) is not None else 1
        tail        = m.group(5)

        new_plus_start = plus_start + cumulative_offset

        body_lines = body.split("\n")
        if body_lines and body_lines[-1] == "":
            body_lines = body_lines[:-1]

        real_plus_count = sum(1 for l in body_lines if not l.startswith('-'))
        real_minus_count = sum(1 for l in body_lines if not l.startswith('+'))

        new_hdr = f"@@ -{minus_start},{real_minus_count} +{new_plus_start},{real_plus_count} @@{tail}"
        body_text = "\n".join(body_lines) + "\n"

        patch_parts.append(new_hdr)
        patch_parts.append(body_text)

        cumulative_offset += (real_plus_count - orig_plus_count)

    return "".join(f"{p}\n" if not p.endswith("\n") else p for p in patch_parts)
