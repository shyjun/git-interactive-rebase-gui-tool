#!/usr/bin/env python3
"""Bisect the 'Show unstaged changes' segfault (crash at dlg.exec()).

Each variant runs in its OWN subprocess so a segfault in one variant does not
kill the rest. Last line of the summary table shows which minimal setup dies.

Usage:
    python3 scripts/crash_bisect.py [repo_path] [variant ...]

Variants:
    ctor-only        construct UnstagedDiffDialog, never show it (test parity)
    show-nostyle     show() with no app stylesheet
    show-style       show() with the real global theme stylesheet
    exec-style       exec() with the real global theme stylesheet
    exec-parent      exec() with stylesheet + live UnstagedChangesDialog parent
    nested           exact crash path: parent dialog in exec(),
                     button click -> show_unstaged_changes() -> child exec()
"""
import os
import subprocess
import sys

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

VARIANTS = (
    "ctor-only",
    "show-nostyle",
    "show-style",
    "exec-style",
    "exec-parent",
    "nested",
)


def _child(variant, repo):
    """Run one variant in this (sub)process. Segfault here = rc -11/139."""
    import faulthandler
    faulthandler.enable()

    sys.path.insert(0, HERE)
    # Match the app/test import order (see tests/test_drag_drop.py header).
    import lib.app_window.helpers  # noqa: F401

    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication
    from lib.app_window.helpers import get_theme_stylesheet
    from lib.git_helpers import (
        get_current_branch,
        get_full_head_sha,
        get_unstaged_diff,
        get_unstaged_file_stats,
        get_unstaged_files,
    )

    app = QApplication([])
    style = variant not in ("ctor-only", "show-nostyle")
    if style:
        theme = QSettings("git-interactive-rebase-gui-tool", "settings").value(
            "theme", "light", type=str
        )
        app.setStyleSheet(get_theme_stylesheet(theme))

    files = get_unstaged_files(repo, ignore_submodules=True)
    if not files:
        print(f"[bisect] no unstaged files in {repo!r} — cannot test", flush=True)
        return 2
    diff_text = get_unstaged_diff(repo, ignore_submodules=True)
    file_stats = get_unstaged_file_stats(repo, ignore_submodules=True)
    branch = get_current_branch(repo) or "HEAD"
    head_sha = get_full_head_sha(repo)
    font_size = int(QSettings("shyjun", "GitInteractiveRebase").value("font_size", 10))

    from lib.dialogs.diff_dialogs import UnstagedDiffDialog

    holder = None
    if variant in ("exec-parent", "nested"):
        from lib.dialogs.unstaged_dialogs import UnstagedChangesDialog
        holder = UnstagedChangesDialog(
            len(files), repo_path=repo, unstaged_files=files
        )
        holder.show()

    # Safety net: never hang the runner.
    QTimer.singleShot(15000, lambda: os._exit(99))

    if variant == "nested":
        # Exact production path: modal parent in exec(), click the button.
        # On a crashing laptop the segfault lands between click and the 6s
        # marker; on a healthy laptop we os._exit(0) to skip nested-loop
        # teardown (closing modal-inside-modal widgets reliably is fiddly).
        QTimer.singleShot(700, holder.view_changes_btn.click)
        QTimer.singleShot(6000, lambda: (
            print("[bisect] SURVIVED nested (alive 6s after button click)",
                  flush=True),
            os._exit(0),
        ))
        print("[bisect] variant=nested entering parent exec()", flush=True)
        holder.exec()
        print("[bisect] nested parent exec() returned unexpectedly", flush=True)
        return 0

    dlg = UnstagedDiffDialog(
        repo, files, diff_text, file_stats, branch, head_sha,
        font_size, None, holder,
    )
    print(f"[bisect] variant={variant} constructed ok", flush=True)

    if variant == "ctor-only":
        print("[bisect] SURVIVED ctor-only", flush=True)
        return 0

    if variant.startswith("exec"):
        QTimer.singleShot(4000, lambda: (
            print(f"[bisect] still alive after 4s, closing ({variant})", flush=True),
            dlg.close(),
        ))
        dlg.exec()
        print(f"[bisect] SURVIVED {variant} (exec returned)", flush=True)
        return 0

    dlg.show()
    QTimer.singleShot(4000, lambda: (
        print(f"[bisect] still alive after 4s ({variant})", flush=True),
        dlg.close(),
        holder and holder.close(),
        app.quit(),
    ))
    app.exec()
    print(f"[bisect] SURVIVED {variant}", flush=True)
    return 0


def _run_one(variant, repo):
    print(f"\n=== variant: {variant} " + "=" * max(1, 40 - len(variant)), flush=True)
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--child", variant, repo]
    )
    rc = proc.returncode
    if rc == -11 or rc == 139:
        verdict = "SEGFAULT (SIGSEGV)"
    elif rc == 99:
        verdict = "HUNG (15s timeout)"
    elif rc == -6 or rc == 134:
        verdict = "ABORT (SIGABRT)"
    elif rc == 0:
        verdict = "survived"
    else:
        verdict = f"failed rc={rc}"
    return rc, verdict


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        variant, repo = sys.argv[2], sys.argv[3]
        sys.exit(_child(variant, repo))

    repo = os.getcwd()
    wanted = VARIANTS
    args = [a for a in sys.argv[1:]]
    if args and not os.path.isdir(args[0]):
        pass
    if args:
        if os.path.isdir(args[0]):
            repo = args[0]
            args = args[1:]
        wanted = tuple(args) or VARIANTS

    import PySide6
    print(f"python {sys.version.split()[0]} | PySide6 {PySide6.__version__} | "
          f"repo={repo}", flush=True)

    results = []
    for variant in wanted:
        results.append((variant,) + _run_one(variant, repo))

    print("\n=== summary " + "=" * 55, flush=True)
    for variant, rc, verdict in results:
        print(f"  {variant:<15} {verdict}", flush=True)


if __name__ == "__main__":
    main()
