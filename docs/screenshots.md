# Screenshots & Feature Guide

Visual documentation for the Git Interactive Rebase GUI Tool. Each section showcases a feature with a screenshot and brief description.

**Note:** [Vim official repository](https://github.com/vim/vim) is used for demonstration purposes.

---

## Table of Contents

1. [Launch](#1-launch)
2. [Main Interface](#2-main-interface)
3. [Context Menu](#3-context-menu)
4. [Repo Menu](#4-repo-menu)
5. [Configure Menu](#5-configure-menu)
6. [Multi-Select Menu](#6-multi-select-menu)
7. [File-Operations menu](#7-file-operations-menu)
8. [Search & Filter](#8-search--filter)
9. [Diff Search Bar](#9-diff-search-bar)
10. [Diff Viewer](#10-diff-viewer)
11. [Diff Pane](#11-diff-pane)
12. [Rephrase Commit](#12-rephrase-commit)
13. [Drop Commit](#13-drop-commit)
14. [Reorder Commits](#14-reorder-commits)
15. [Multi-Select Actions](#15-multi-select-actions)
16. [Squash Commits](#16-squash-commits)
17. [Split Dialog](#17-split-dialog)
18. [Refine Changes in File](#18-refine-changes-in-file)
    - [18.1 Selectively Drop Changes / Hunks](#181-selectively-drop-changes--hunks)
    - [18.2 Keep Only Selected Changes / Hunks](#182-keep-only-selected-changes--hunks)
    - [18.3 Move Selected Changes to a Separate Commit](#183-move-selected-changes-to-a-separate-commit)
    - [18.4 Edit Hunk](#184-edit-hunk)
19. [Unstaged / Uncommitted Changes Handling](#19-unstaged--uncommitted-changes-handling)
    - [19.1 At Startup](#at-startup)
    - [19.2 During a Session: Rescan Repository](#during-a-session-rescan-repository)
    - [19.3 Commit Selectively](#commit-selectively)
        - [19.3.1 Hunk-level commit with git add -p](#hunk-level-commit-with-git-add--p)
20. [Reset Options](#20-reset-options)
21. [Rebase Options](#21-rebase-options)
22. [Browse Branch](#22-browse-branch)
23. [Browse File Log](#23-browse-file-log)
24. [Browse Log of a Commit](#24-browse-log-of-a-commit)
25. [Browse Reflog](#25-browse-reflog)
26. [Browse Stashes](#26-browse-stashes)
27. [PR Diff / PR Preview](#27-pr-diff--pr-preview)
28. [Consolidated Diff](#28-consolidated-diff)
29. [Find Merge-base](#29-find-merge-base)
30. [Cherry-pick](#30-cherry-pick)
31. [Apply Patch](#31-apply-patch)
32. [Create Patch](#32-create-patch)
33. [Viewer Mode](#33-viewer-mode)
34. [Themes (Light / Dark)](#34-themes-light--dark)
35. [Zoom Controls](#35-zoom-controls)
36. [Mark / Unmark Commit](#36-mark--unmark-commit)
37. [Show Local Branches](#37-show-local-branches)
38. [Copy to Clipboard](#38-copy-to-clipboard)
39. [Update the Tool](#39-update-the-tool)
40. [Tag Commit](#40-tag-commit)
41. [Blame a file](#41-blame-a-file)
42. [Browse Tags](#42-browse-tags)
43. [External Tools Dialog](#43-external-tools-dialog)
44. [Keyboard Shortcuts](#44-keyboard-shortcuts)

---

## 1. Launch

Launch the application by specifying a commit range, using the auto-detected branch base, or starting in read-only Viewer Mode.

### Option 1: Auto-detect branch base (default, recommended)

Just run the tool with **no commit argument** — it automatically detects the base branch (for example, `main` or `master`) and shows the commits since the branch divergence point.

This is the most useful way to launch: it shows **only your branch's changes**, i.e. everything you've done since the branch split from the base — ideal for reviewing and cleaning up your feature branch before raising a PR.

If detection fails, it falls back to displaying the **200 most recent commits from HEAD**. In this case, a **Load 100 more** button appears in the status bar and at the bottom of the commit list — click it to extend the view further back in history, 100 commits at a time, until the root commit is reached.

**Screenshot:** `screenshots/head-commits.webp`

![Launch Options](screenshots/head-commits.webp)

**Description:** The screenshot above shows the application launched using `python3 git_interactive_rebase.py HEAD~N` (where `N` is the number of commits to show).

### Option 2: Show commits since a specific commit (provide SHA as argument)

View commits starting from a specific commit SHA or relative HEAD reference.

You can specify commits using:

- A specific commit SHA
- `HEAD~N` to go back **N commits**
- `HEAD^^^...` where each `^` represents one commit

```bash
python3 git_interactive_rebase.py <commit-sha>
python3 git_interactive_rebase.py HEAD~N
python3 git_interactive_rebase.py HEAD^^^
```

### Option 3: Start in Viewer Mode (read-only)

Launch the tool with all history-modifying operations disabled. Useful for safely browsing a repository (see [Viewer Mode](#33-viewer-mode)).

```bash
python3 git_interactive_rebase.py --viewer-mode
```

### Option 4: Update the tool

Update to the latest version (git-clone installs refuse if the local clone has uncommitted changes) and exit:

```bash
python3 git_interactive_rebase.py --update
```

Print the tool's version (short git id) and exit:

```bash
python3 git_interactive_rebase.py --version
```

**Note:** If `git` is not installed or not in your PATH, the tool shows a "Git not found" dialog at startup and exits. If the current directory is not a valid git repository, a "Not a Git Repository" dialog is shown instead.

---

## 2. Main Interface

The main window displays your commit history in an interactive list with action controls.

**Screenshot:** `screenshots/main-interface.webp`

![Main Interface](screenshots/main-interface.webp)

**Description:** The main window shows the commit list with SHA, message, and branch indicators. The details panel displays commit metadata (SHA, author, date, changed files). A **diff pane** is docked on the right side (marked in the screenshot above) — click any commit to view its diff there (added lines in green, removed lines in red, with line numbers), in either **Plain Diff** or **File-wise Diff** mode (see [10](#10-diff-viewer) and [11](#11-diff-pane)). The top toolbar includes search, the **Search Options** dropdown (Match Case / Whole Word / Display Only Matching), theme toggle, zoom controls, a **Repo** menu (View PR Diff, View a Commit, Cherry-pick 1 Commit, Browse Branch, Browse File Log, Browse Log of a Commit, Browse Reflog, Browse Stashes, Find Merge-base), and reset options.

The status bar holds a **Configure** button whose **Show/Hide** menu lets you toggle which markers/columns and controls are visible — each choice is remembered across sessions:

- **Show Origin** → origin markers
- **Show Rebase** → rebase markers
- **Show Squash** → squash markers
- **Show Local Branches** → local/remote branch names next to commits
- **Show Tags** → tag names next to commits (purple `{tag}` labels)
- **Show Stats** → per-commit line stats
- **Show Date** → commit dates
- **Show Diffs** → the right-side diff pane

The status bar also shows the commit count. Right-click any commit to access the context menu with all rebase actions.

---

## 3. Context Menu

Access all commit actions via right-click menu.

**Screenshot:** `screenshots/context-menu.webp`

![Context Menu](screenshots/context-menu.webp)

**Description:** Right-click any commit to see the context menu with all available actions:

- Show / View commit {sha} (opens the tabbed Plain + File-wise viewer)
- Create Patch (save the commit as a format-patch file, re-appliable via Apply Patch)
- Tag (create a lightweight or annotated git tag on the commit)
- Mark / Unmark commit
- Copy SHA / Copy Message / Copy Both
- Reset hard to this commit
- Reset HEAD to here (keep changes unstaged)
- Set Best Commit ID
- Rephrase
- Drop
- Revert
- Squash commits (with above / below, or select multiple)
- Move Commit (up / down, or drag to reorder)
- Split Commit (drop file change, move file out, split to separate commits)
- Refine changes (hunk-level)
- Consolidated Diff (set start, diff to here, diff HEAD to here, git difftool)
- Browse file log

In the file-wise diff viewer and blame viewer, right-clicking a file also shows:

- Open → With System Default App
- Blame file
- Diff against a different version of this file (see [File-Operations menu](#7-file-operations-menu))

---

## 4. Repo Menu

The **Repo** button in the main window's toolbar groups the repository-wide tools in one menu.

**Screenshot:** `screenshots/repo-menu.webp`

![Repo Menu](screenshots/repo-menu.webp)

**Description:** Click **Repo** in the toolbar to open the menu. It offers:

- **View PR Diff** → Open a read-only **PR Preview** showing the combined branch diff versus its merge-base (see [PR Diff / PR Preview](#27-pr-diff--pr-preview))
- **View a Commit…** → Open any commit by SHA in a read-only tabbed viewer (Plain / File-wise diff)
- **Cherry-pick 1 Commit** → Cherry-pick a single commit by SHA (see [Cherry-pick](#30-cherry-pick))
- **Browse Branch** → Open a read-only window of another branch's history (see [Browse Branch](#22-browse-branch))
- **Browse File Log** → Open a read-only window of a single file's history (see [Browse File Log](#23-browse-file-log))
- **Browse Log of a Commit** → Open a read-only history window for any commit SHA or ref, prompted with the number of commits to show (see [Browse Log of a Commit](#24-browse-log-of-a-commit))
- **Browse Reflog** → Open a read-only window of the repository's HEAD reflog (see [Browse Reflog](#25-browse-reflog))
- **Browse Stashes** → Open a read-only window of the repository's stash list (see [Browse Stashes](#26-browse-stashes))
- **Browse Tags** → Open a read-only window listing all tags with their commit info (see [Browse Tags](#43-browse-tags))
- **Open File at Commit…** → Browse and open a file at any commit, branch, or tag with the system default app. Enter a SHA/branch/tag, type or browse for a file, and open that version of the file (see [Open with System Default App](#102-file-wise-diff))
- **Find Merge-base…** → Compute the merge-base between the current branch and another branch (see [Find Merge-base](#29-find-merge-base))

---

## 5. Configure Menu

The **Configure** button in the status bar controls which markers, columns, and panels are visible.

**Screenshot:** `screenshots/configure-menu.webp`

![Configure Menu](screenshots/configure-menu.webp)

**Description:** Click **Configure** in the status bar to open the menu. The **Show/Hide** submenu lets you toggle each item; the choices are remembered across sessions:

- **Show Origin** → origin markers
- **Show Rebase** → rebase markers (see [Rebase Options](#21-rebase-options))
- **Show Squash** → squash markers
- **Show Local Branches** → local/remote branch names next to commits (see [Show Local Branches](#37-show-local-branches))
- **Show Tags** → tag names next to commits (see [Tag Commit](#40-tag-commit))
- **Show Stats** → per-commit line stats
- **Show Date** → commit dates
- **Show Diffs** → the right-side diff pane (see [Diff Pane](#11-diff-pane))

The menu also includes:

- **External tools integration** → Configure diff tool (Not configured / Git configured / Custom command)
- **Help** → links to the demo video, README, and contact
- **Check for updates** → compares the running version against the remote
- **Check for updates at startup** → tickable option to auto-check on launch (default: enabled)

---

## 6. Multi-Select Menu

The **Perform action on selected commits** menu lists the actions that can be applied to the commits checked in multi-select mode.

**Screenshot:** `screenshots/multi-select-menu.webp`

![Multi-Select Menu](screenshots/multi-select-menu.webp)

**Description:** Enter multi-select mode with **Select multiple commits**, then open the **Perform action on selected commits** menu (next to the selection button). Each commit gets a tick box, and the menu offers the following actions based on how many commits are checked:

- **Squash selected commits** → Available when **2 or more** adjacent commits are checked (see [Squash Commits](#16-squash-commits))
- **Mark selected commits** → Available when **1 or more** commits are checked (see [Mark / Unmark Commit](#36-mark--unmark-commit))
- **Drop selected commits** → Available when **1 or more** commits are checked (see [Drop Commit](#13-drop-commit))
- **Move selected commits** → Shows a hint explaining that a contiguous (adjacent) block of checked commits can be dragged to a new position (see [Reorder Commits](#14-reorder-commits))

The actions are described in detail in [Multi-Select Actions](#15-multi-select-actions).

---

## 7. File-Operations menu

Right-click a file in the **File-wise Diff** tab for per-file actions.

**Screenshot:** `screenshots/file-wise-diff-viewer.webp`

![File-Operations menu](screenshots/file-wise-diff-viewer.webp)

**Description:** Right-click any file in the file-wise file list to open the context menu. The available actions depend on how the viewer was opened.

**Always available (all modes):**

- **Open → With System Default App** — opens the file using the system's default application. When the viewer is browsing a different branch or commit, the file is extracted via `git show` to a temp location first.
- **Blame file** → Opens a read-only blame viewer (see [Blame a file](#41-blame-a-file))
- **Diff against a different version of this file** → Opens a dialog to diff the file against a different commit, branch, or tag using `git difftool`. The dialog matches the "Open File at Commit" layout: ref combo on top, editable file path with Browse (resolves files at the selected ref, so renamed files are handled). Warns if no difftool is configured, verifies the file exists at the target ref before running, and shows a message if the file content is identical at both versions.
- **Copy filename to clipboard**
- **Copy fullpath to clipboard** — copies the full repository path of the file
- **Browse file log** → opens a read-only viewer of that file's history

**When the commit is in the current branch** (right-click **Show / View commit {sha}**, or double-click from the main list, and not in browse/viewer mode):

- **Move file changes out of this commit** (disabled when the commit has only one file)
- **Drop file changes from this commit** (disabled when the commit has only one file)
- **Remove file from this commit onwards**
- **Refine/Edit changes in selected file**

When the viewer was opened by SHA via **Repo → View a Commit…**, the commit may be arbitrary (even outside the current branch), so only the safe actions (**Open**, **Copy filename**, **Copy fullpath**, **Blame file**, **Browse file log**) are shown.

---

## 8. Search & Filter

Quickly locate commits using live search and advanced filtering options.

**Screenshot:** `screenshots/search-filter.webp`

![Search & Filter](screenshots/search-filter.webp)

**Description:** Click the search bar or press `/` to focus it. Type to filter commits live. Matching commits are shown instantly as you type.

Filtering supports the following modes (enable one or multiple at the same time for more precise searching):

- **Message / SHA** → Search by commit message text or SHA (short, partial, or full 40-character SHA-prefix)
- **Filenames** → Search commits that modified a specific file
- **Diff** → Search inside commit diff/content (runs in the background; requires at least **3 characters**)
- **Author** → Search by author name or email

**Search Options** (dropdown next to the search bar):

- **Match Case** → Match exact letter case
- **Whole Word** → Match complete words only (always starts **off** on each launch)
- **Display Only Matching** → Hide non-matching commits; matching commits are bolded when this is off

This is especially useful when trying to locate where a change was introduced and you only remember a filename, symbol, function name, commit message, or code snippet.

Press `Esc` to clear the search and return to the full commit history.

---

## 9. Diff Search Bar

Quickly search for text inside any displayed diff.

**Screenshot:** `screenshots/diff-search.webp`

![Diff Search Bar](screenshots/diff-search.webp)

**Description:** The diff search bar is a shared toolbar available in **every** diff view — the main window's **Plain Diff** / **File-wise Diff** tabs, the **View a Commit** viewer, **PR Diff / Unstaged Diff**, the **Split / Drop / Confirm** dialogs, and the **Commit Selectively** preview. It is visible by default; press `Ctrl+F` to focus it.

Search supports:

- **Match Case** → Match exact letter case
- **Whole Word** → Match complete words only
- **Previous / Next navigation (`<` / `>`)** → Jump between matches
- **Match counter** → Shows current match position (e.g., `2/10`)
- **Line-Num** → Highlight matching line numbers

Press `Esc` to clear the search.

---

## 10. Diff Viewer

The commit diff can be viewed in two modes (tabs):

- **Plain Diff** → the full commit diff in one scrollable view (see [10.1](#101-plain-diff))
- **File-wise Diff** → the commit's changes listed file by file (see [10.2](#102-file-wise-diff))

---

### 10.1 Plain Diff

Browse a commit's diff as a single combined view.

**Screenshot:** `screenshots/plain-diff.webp`

![Plain Diff](screenshots/plain-diff.webp)

**Description:** The **Plain Diff** tab shows the full commit diff in one scrollable, syntax-highlighted view with line numbers — useful for reviewing the complete change set at a glance.

---

### 10.2 File-wise Diff

Browse a commit's changes file by file.

**Description:** Switch to the **File-wise Diff** tab (in the right panel, or in the commit viewer) to list all changed files for the selected commit. Select any file to view its specific diff. This makes it easy to understand what each file contributed to the commit. Renames are shown as one `old => new` row. Deleted files are marked as `filename (Deleted)` and new files as `filename (Added new file)`. (Screenshot: same as [File-Operations menu](#7-file-operations-menu).)

Right-click a file in the file-wise file list for per-file actions — see [File-Operations menu](#7-file-operations-menu) for the full list of available actions.

---

## 11. Diff Pane

A diff viewer is docked at the right side of the main window.

**Description:** A diff viewer is docked towards the main window's right-side pane. Click any commit to view its diff there — added lines in green, removed lines in red, with line numbers. The pane offers two modes, **Plain Diff** and **File-wise Diff** (see [10](#10-diff-viewer)).

- **Configure → Show/Hide → Show Diffs** toggles the right-side diff pane; the choice is remembered across sessions.

---

## 12. Rephrase Commit
Update the commit message without changing the commit contents.

**Screenshot:** `screenshots/rephrase-commit.webp`

![Rephrase Commit](screenshots/rephrase-commit.webp)

**Description:** Right-click a commit and select "Rephrase" to open the rephrase dialog. Edit the commit message and click "Confirm" to apply the new message.

---

## 13. Drop Commit
Remove a commit entirely from the history.

**Screenshot:** `screenshots/drop-commit.webp`

![Drop Commit](screenshots/drop-commit.webp)

**Description:** Right-click a commit and select "Drop" to see a confirmation dialog. Confirm to remove the commit from the history. This action is irreversible without resetting.

---

## 14. Reorder Commits
Change commit order to organize history before rebasing.

**Screenshot:** `screenshots/drag-reorder.webp`

![Reorder Commits](screenshots/drag-reorder.webp)

**Description:** Reorder commits using either drag-and-drop or quick move actions from the context menu.

Available options include:

- **Drag to Reorder** → Click and drag a commit to a new position in the history
- **Move Up / Move Down** → Move a commit relative to nearby commits using the context menu
- **Swap with Above / Below Commit** → Quickly exchange positions with adjacent commits

A visual indicator shows where the commit will be placed before confirming the reorder.

In multi-select mode you can also drag a whole block of adjacent (contiguous) checked commits to a new position together (see [Multi-Select Actions](#15-multi-select-actions)).

---

## 15. Multi-Select Actions

Perform an action on multiple commits at once — squash an adjacent range, mark many commits, drop several in one go, or reorder a contiguous block. The **Perform action on selected commits** menu is shown in the [Multi-Select Menu](#6-multi-select-menu) screenshot.

Enter multi-selection mode with the **Select multiple commits** button in the toolbar (or via the context menu), then check the commits you want to act on. Each commit gets a tick box; the **Perform action on selected commits** menu (next to the selection button) offers the available actions based on how many commits are checked:

- **Squash selected commits** → Available when **2 or more** adjacent commits are checked. Opens the squash dialog to combine them into one (see [Squash Commits](#16-squash-commits))
- **Mark selected commits** → Available when **1 or more** commits are checked. Marks all checked commits at once (see [Mark / Unmark Commit](#36-mark--unmark-commit))
- **Drop selected commits** → Available when **1 or more** commits are checked. Drops the checked commits one by one, **newest first**. If a drop fails part-way through, you can **skip that commit and continue** with the remaining pending ones, or **stop** and handle it manually (see [Drop Commit](#13-drop-commit))
- **Move selected commits** → Available when **1 or more** commits are checked. Shows a hint explaining that a contiguous (adjacent) block of checked commits can be dragged to a new position to reorder them together (see [Reorder Commits](#14-reorder-commits)).
- **Create patch(s) from selected commits** → Available when **1 or more** commits are checked. Opens a submenu with two options:
  - **Consolidated single patch** → Combines all selected commits into one unified-diff file (requires **2 or more** commits). A save dialog lets you choose the output file.
  - **Multiple patches** → Creates one format-patch file per commit in a chosen folder (requires **1 or more** commits). Each patch carries the commit's own message, so it round-trips through [Apply Patch](#31-apply-patch).
- **Git Difftool (requires exactly 2 commits)** → Available when **exactly 2** commits are checked. Shows a confirmation dialog with the command, then runs `git difftool <sha1> <sha2>` to open your configured difftool.
- **Drag to reorder** → In multi-select mode you can also click and drag the checked commits as a group to a new position. The checked commits must form one **adjacent (contiguous) block**; dragging works like the normal reorder drag (see [Reorder Commits](#14-reorder-commits)). A confirmation dialog shows the range being moved before it is applied.

To leave selection mode without acting, click **Cancel multiple selection** (or press `Esc`, or use the context menu) to deselect everything and return to normal mode.

---

## 16. Squash Commits
Combine multiple commits into one.

### Option 1: Squash Commit with above / below commit

Squash a commit with its immediate neighbor (above or below).

**Screenshot:** `screenshots/squash-context-menu.webp` (context menu)

![Squash Context Menu](screenshots/squash-context-menu.webp)

**Screenshot:** `screenshots/squash-dialogue.webp` (dialog)

![Squash Dialog](screenshots/squash-dialogue.webp)

**Description:** Right-click a commit and select "Squash with above" or "Squash with below" to open the squash dialog. You can either select a commit message from one of the commits being squashed, or enter your own custom commit message. Click "Confirm" to apply.

### Option 2: Select multiple commits and squash them together

Squash multiple adjacent commits at once.

**Screenshot:** `screenshots/multi-squash.webp`

![Multi Squash](screenshots/multi-squash.webp)

**Description:** In multi-select mode (see [Multi-Select Actions](#15-multi-select-actions)), select multiple adjacent commits by clicking on them, then choose **Squash selected commits** from the **Perform action on selected commits** menu (or use the context menu) to open the squash dialog. Edit the combined commit message in the dialog and click "Confirm" to apply.

---

## 17. Split Dialog
Break a commit into multiple smaller commits by file or change.

**Screenshot:** `screenshots/split-context-menu.webp`

![Split Context Menu](screenshots/split-context-menu.webp)

### Option 1: Move single file changes out of a commit

Move changes of a specific file to a separate commit (only for commits with multiple file changes).

**Screenshot:** `screenshots/split-move-single-file-1.webp`

![Split Move Single File 1](screenshots/split-move-single-file-1.webp)

**Screenshot:** `screenshots/split-move-single-file-2.webp`

![Split Move Single File 2](screenshots/split-move-single-file-2.webp)

### Option 2: Split each file changes to separate commits

Available only in commits with multiple file changes. Creates one commit per changed file.

**Screenshot:** `screenshots/split-each-to-separate.webp`

![Split Each to Separate](screenshots/split-each-to-separate.webp)

### Option 3: Split all changes in one file to separate commits

Breaks all changes in a single file into individual commits per file change. Available only in commits with single file changes.

**Screenshot:** `screenshots/split-all-to-separate.webp`

![Split All to Separate](screenshots/split-all-to-separate.webp)

---

## 18. Refine Changes in File
Selectively refine changes/hunks inside a file within a commit.

This is useful when a file accidentally contains mixed changes such as feature work, debug code, documentation updates, or unrelated edits.

**Screenshot:** `screenshots/refine-changes-in-file.webp`

![Refine Changes in File](screenshots/refine-changes-in-file.webp)

**Description:** Select one or more hunks using the checkboxes. Use **Select All / Deselect All** to quickly adjust selection. Depending on the action chosen, selected or unselected hunks are retained, removed, or moved.

---

### 18.1 Selectively Drop Changes / Hunks

Drop only selected changes/hunks from a file while keeping the remaining changes in the commit intact.

**Description:** Select the hunks to remove and click **"Drop Selected Hunks"**.

- **Checked hunks** → Removed from the commit
- **Unchecked hunks** → Kept in the commit

Useful for removing accidental debug code, temporary changes, or unrelated edits.

---

### 18.2 Keep Only Selected Changes / Hunks

Keep only selected changes/hunks and drop everything else from the file within the commit.

**Description:** Select the hunks you want to retain and click **"Apply Only Selected Hunks"**.

- **Checked hunks** → Kept in the commit
- **Unchecked hunks** → Dropped from the commit

Useful when a commit contains mixed or unrelated changes and only part of it should remain.

---

### 18.3 Move Selected Changes to a Separate Commit

Move selected changes/hunks into a new separate commit.

**Description:** Select the hunks to move and click **"Move Selected Changes to New Commit"**.

- **Checked hunks** → Moved to a new commit
- **Unchecked hunks** → Remain in the current commit

Useful when a change accidentally landed in the wrong commit. Move it out, reorder the new commit, and squash it with the intended commit later.

---

### 18.4 Edit Hunk

Edit a selected hunk using a lightweight patch editor.

**Screenshot:** `screenshots/edit-hunk.webp`

![Edit Hunk](screenshots/edit-hunk.webp)

**Description:** Right-click a hunk and choose **"Edit Hunk"** to manually modify the patch content before applying changes.

The editor allows fine-grained cleanup of a hunk by directly editing the patch text.

Features include:

- **Editable patch content** → Modify added/removed lines directly
- **Reset to Original Hunk** → Restore the original patch if needed
- **Apply** → Save valid patch changes
- **Cancel** → Discard edits

> **Note:** Only valid patch/diff format edits are supported. Invalid edits may fail to apply.

Useful for quickly cleaning up accidental changes, temporary code, debug prints, small formatting fixes, or unwanted lines before finalizing commit history.

---

## 19. Unstaged / Uncommitted Changes Handling

Safely handle unstaged or uncommitted changes — both when launching the app and while it is already running.

When unstaged changes are detected, the tool pauses and provides multiple safe options before continuing.

### At Startup

**Screenshot:** `screenshots/unstaged-changes-warning.webp`

![Unstaged Changes Handling](screenshots/unstaged-changes-warning.webp)

**Description:** If unstaged or uncommitted changes are detected during launch, the tool shows a warning dialog and provides multiple ways to safely proceed.

Available options include:

- **Stash and proceed to app** → Temporarily stash current changes and launch the application. When exiting the app, if it was launched this way, you are prompted to directly **stash pop** and restore the changes. A **Pop Managed Stash** button appears in the toolbar while a stash exists.
- **Commit Selectively** → Choose which files (or diff hunks) to commit before starting the app (see [Commit Selectively](#commit-selectively))
- **Commit each file changes separately and start app** → Automatically create one commit per modified file before launch
- **Commit all unsaved changes to a single "bulk" commit** → Save all current changes into one temporary commit and continue
- **Amend all changes to the current `HEAD` commit** → Amend HEAD commit with the unstaged changes
- **Discard changes** → Discard the unstaged changes
- **Start in Viewer Mode** → Start the app in viewer mode. No history modifying operations will be allowed (see [Viewer Mode](#33-viewer-mode))
- **Exit** → Cancel launch and resolve changes manually

> **Note:** Untracked files are **not considered** during this process and are left untouched (not stashed or modified).

### During a Session: Rescan Repository

**Screenshot:** `screenshots/rescan-repository.webp`

![Rescan Repository for Changes](screenshots/rescan-repository.webp)

**Description:** The application can remain open while you continue working in your editor or terminal. If new unstaged or uncommitted changes are introduced outside the tool, use **Rescan Repository** to re-evaluate the repository state.

When changes are detected, the tool provides the same safe handling options available during startup, allowing you to:

- Stash changes and continue
- Commit Selectively (choose which files / hunks to commit)
- Commit each file separately
- Commit all changes into a single bulk commit
- Amend all changes to the current `HEAD` commit
- Discard the changes
- Switch to Viewer Mode
- Cancel and resolve changes manually

If an app-created stash already exists, new changes are **merged into the existing stash** rather than creating a second one. In **Viewer Mode**, history-modifying rescan options are disabled (see [Viewer Mode](#33-viewer-mode)).

This makes it easy to keep the application open throughout a development session while safely incorporating newly created changes into your interactive rebase workflow.

### Commit Selectively

Pick exactly which **files** — or even individual **hunks** — to commit, leaving the rest untouched for later. Ideal when your working tree holds a *mix* of unrelated changes.

**Screenshot:** `screenshots/commit-selectively.webp`

![Commit Selectively](screenshots/commit-selectively.webp)

**Description:** Open **Commit Selectively** from the unstaged-changes dialog (at startup or via **Rescan Repository**). A dialog lists every modified file with a checkbox and its `+N -M` stats; the bottom pane shows the **combined diff** of the checked files (with a separator before each file). Use **Select All / Deselect All** and the live counter to adjust quickly. Then choose:

- **Commit Selected Files** → Stage the checked files and commit them (a message dialog opens)
- **commit --amend selected files** → Stage the checked files and amend into HEAD (message pre-filled from HEAD, editable)
- **git add -p** → Drill into individual **hunks** of the checked files (see below)

Unchecked files stay completely untouched, and cancelling at any point leaves the repository unchanged.

#### Hunk-level commit with `git add -p`

Stage *parts* of a file — perfect when one file contains mixed edits (feature code + debug prints, real change + formatting churn).

**Screenshot:** `screenshots/git-add-p-hunks.webp`

![Git Add -p Hunk Selection](screenshots/git-add-p-hunks.webp)

**Description:** Click the orange **git add -p** button. Every hunk of the checked files is listed, **grouped under a per-file header**, each with its own checkbox showing the `Change N` label, diff header, line count, and syntax-coloured body. Then finish with:

- **git commit** → Stage only the *checked* hunks and commit with a new message
- **git commit --amend** → Stage only the checked hunks and amend into HEAD (message pre-filled, editable)

**What happens to the rest:**

- **Checked hunks** → staged and committed
- **Unchecked hunks** → stay untouched in the working tree, available for a later commit
- **Binary / no-hunk files** → a checked file with no parseable hunks is staged whole, so it is not silently lost

Cancelling at any point stages nothing, and a failed staging/commit resets the index so nothing is half-committed. Complements [Refine Changes in File](#18-refine-changes-in-file): refine mixed changes out of past commits, and use `git add -p` to keep future commits clean from the start.

---

## 20. Reset Options
Fail-safe options to reset your branch to a safe state.

**Screenshot:** `screenshots/reset-options.webp`

![Reset Options](screenshots/reset-options.webp)

**Description:** Use the "Reset" menu to access fail-safe options:

- **Reset to Best Commit ID**: Reset to a user-defined safe commit. To set the Best Commit ID, right-click any commit and select "Set Best Commit ID"
- **Reset to Start Time Head**: Reset to the commit state when the app launched
- **Reset to Custom Commit**: Choose any commit to reset to

Right-click a commit and select **"Reset HEAD to here (keep changes unstaged)"** to run `git reset --mixed` and reset HEAD to a commit while keeping all changes in your working directory as unstaged changes.

---

## 21. Rebase Options
Rebase your commits onto a different branch.

**Screenshot:** `screenshots/rebase-options.webp`

![Rebase Options](screenshots/rebase-options.webp)

**Description:** Click "Rebase" to open the rebase dialog. Choose to rebase onto:

- master
- main
- A custom branch

The rebase runs in the background without blocking the UI.

The Rebase button can be hidden or shown via **Configure → Show/Hide → Show Rebase** in the status bar (see [2. Main Interface](#2-main-interface)); the choice is remembered across sessions.

---

## 22. Browse Branch
Open any other branch's history in a separate read-only window.

**Screenshot:** `screenshots/browse-branch.webp`

![Browse Branch](screenshots/browse-branch.webp)

**Description:** Use **Repo → Browse Branch** and choose a branch (and how many commits to show). The branch history opens in a non-modal, read-only window — styled with a dimmed grey "viewer" overlay so you always know it is read-only and distinct from the main window. You can:

- Select a single commit, or check multiple commits in multi-select mode
- **Cherry-pick selected commit(s)** into your current branch (oldest-first order)
- Copy SHA / message to the clipboard
- Refresh the branch history

### Selecting Multiple Commits & Cherry-picking

Click **Select commits** to enter checkbox selection mode, then tick the commits you want to bring over. Click **Cherry-pick selected commit(s)** to apply them to your current branch:

- A confirmation dialog shows the exact apply order (oldest-first, matching the branch chronology) before anything is done.
- Commits are then cherry-picked one by one. If a pick fails, you choose how to proceed: **Undo entire cherry-pick** (reset back to the starting point), **Skip this and continue with the next**, or **Stop cherry-pick here** to finish manually.
- A final summary reports which commits were cherry-picked, skipped, or left unapplied.
- The main window's commit list refreshes automatically after the picks finish.
- **Cancel selection** exits selection mode without making any changes.

---

## 23. Browse File Log
View the complete history of a single file.

**Screenshot:** `screenshots/browse-file-log.webp`

![Browse File Log](screenshots/browse-file-log.webp)

**Description:** Use **Repo → Browse File Log**, or right-click a file in the file-wise diff viewer and choose **Browse file log**. A read-only window opens showing the history of that file (following renames via `git log --follow`), with the diff pane scoped to that file. Like Browse Branch, it uses a dimmed grey "viewer" overlay to distinguish it from the main window. Copy SHA / message to the clipboard directly from this window.

---

## 24. Browse Log of a Commit
Open a read-only history window for any commit.

**Screenshot:** `screenshots/browse-commit-log.webp`

![Browse Log of a Commit](screenshots/browse-commit-log.webp)

**Description:** Use **Repo → Browse Log of a Commit**, enter a commit SHA (or ref like `HEAD` or a branch name), and choose how many of the most recent commits to show. The commit is validated before opening, and its history opens in a read-only window (same style as Browse Branch / Browse File Log). Copy SHA / message to the clipboard directly from this window.

---

## 25. Browse Reflog
Open a read-only window of the repository's HEAD reflog.

**Screenshot:** `screenshots/browse-reflog.webp`

![Browse Reflog](screenshots/browse-reflog.webp)

**Description:** Use **Repo → Browse Reflog** to open a read-only window listing the most recent reflog entries (newest first, up to 50 by default). Each row shows the commit SHA, the reflog selector (`HEAD@{0}`, `HEAD@{1}`, …) and the reflog subject. Added/deleted stats are not shown (reflog entries don't carry that data). The diff pane is hidden in this window. Actions:

- **Copy SHA to clipboard** → Copy the selected entry's commit SHA
- **Show log** → Open a read-only history window for that entry's commit (asks how many commits to show, default 50)
- **Double-click** an entry → same as **Show log**

Right-click an entry for **Show log** / **Copy SHA to clipboard**.

---

## 26. Browse Stashes
Open a read-only window of the repository's stash list.

**Screenshot:** `screenshots/browse-stash.webp`

![Browse Stashes](screenshots/browse-stash.webp)

**Description:** Use **Repo → Browse Stashes** to open a read-only window listing the repository's stashes (newest first). Each row shows the stash SHA, the selector (`stash@{0}`, `stash@{1}`, …) and the stash subject. Unlike the reflog browser, the **diff pane is always visible** here, with both **Plain Diff** and **File-wise Diff** tabs (stashes are diffed against their base commit). The list refreshes automatically after any stash operation.

Toolbar buttons (also available via right-click):

- **Copy** → Copy the selected stash's SHA to the clipboard
- **Apply + Keep** → Apply the stash and keep it in the list (asks for confirmation first)
- **Apply + Drop** → Apply the stash, and drop it after a successful apply (asks for confirmation first)
- **Drop** → Drop the stash after a Yes/No confirmation

If an apply fails, the stash is **never dropped** and you are told so explicitly. Stash subjects are not commit messages, so the message-copy actions are intentionally omitted.

---

## 27. PR Diff / PR Preview
Preview the combined diff of your current branch against its merge-base.

**Screenshot:** `screenshots/pr-diff.webp`

![PR Diff / PR Preview](screenshots/pr-diff.webp)

**Description:** Use **Repo → View PR Diff** to open a read-only **PR Preview** showing the combined branch diff versus its merge-base — the same view a reviewer would see in a pull request.

When the tool is launched **without** a commit argument, it auto-detects your branch base (see [1. Launch](#1-launch)) and shows commits up to that point. This view is the same idea applied to the whole branch: it diffs your branch against its merge-base, so you can review everything you've changed relative to `main`/`master` in one place. Non-modal, so it stays open while you keep working.

---

## 28. Consolidated Diff
Diff any range of history in one combined view.

**Screenshot:** `screenshots/consolidated-diff.webp`

![Consolidated Diff](screenshots/consolidated-diff.webp)

**Description:** Use the **Consolidated Diff** context submenu on any commit:

- **Set start commit** → Mark the selected commit as the range start
- **Diff to here** → Show the combined diff from the start commit to the selected commit
- **Diff HEAD to here** → Show the combined diff from HEAD down to the selected commit
- **Git Difftool from \<start\> to Here** → Run `git difftool` between the start commit and the selected commit (disabled if no start SHA is set)
- **Git Difftool from HEAD to Here** → Run `git difftool` between HEAD and the selected commit

The result opens in a read-only combined view. You can also set the start commit by right-clicking **"Mark the selected from commit for consolidated diff"**.

---

## 29. Find Merge-base
Compute the merge-base between your current branch and any other branch.

**Screenshot:** `screenshots/find-merge-base.webp`

![Find Merge-base](screenshots/find-merge-base.webp)

**Description:** Use **Repo → Find Merge-base…**, pick another branch, and the tool shows the merge-base commit. Copy the SHA to the clipboard with one click.

---

## 30. Cherry-pick
Apply commits from another branch (or by SHA) onto your current branch.

**Description:** Cherry-pick in two ways:

- **Repo → Cherry-pick 1 Commit** → You will be asked to enter a commit SHA to apply
- **Browse Branch → Cherry-pick selected commit(s)** → Select one or more commits in a browse window and inject them (multi-commit picks apply **oldest-first** so history stays linear)

Before applying, a **pre-flight confirmation** shows the exact order the selected commits will be applied in (numbered, with subjects and target branch). If a commit fails, you are told why (conflict, already applied/no change, or other) with the conflicting files listed, and you can choose to **Undo the entire cherry-pick**, **Skip and continue**, or **Stop and handle manually**. A final summary shows how many commits were cherry-picked / skipped / not applied, with every SHA listed.

---

## 31. Apply Patch
Apply a unified-diff or format-patch file to your repository.

**Description:** Use **Repo → Apply Patch…** to apply a patch file, mirroring the browse-file-log workflow:

- **Browse** for a `.patch`/`.diff` file (or type its path)
- Toggle **Create a commit from the patch** to commit the changes using the patch's own commit message, or leave it unchecked to apply the changes **unstaged** in the working tree
- The patch is dry-run checked (`git apply --check`) before applying, so a failing patch never leaves the repository partially modified — you are shown the git error instead
- On success you are prompted to **Rescan Repo** to pick up the new changes
- The original patch file is **not modified or deleted**

---

## 32. Create Patch
Save any commit as a patch file from the context menu.

**Description:** Right-click a commit and choose **Create Patch** (right below **Show / View commit**) to export it as a format-patch file:

- A save dialog opens, defaulting to `<sha>-<subject>.patch`
- The patch is generated with `git format-patch` and carries the commit's own message, so it round-trips: re-apply it later via **Repo → Apply Patch…** (including as a commit)
- Works for every commit in the list, including root commits
- Greyed out in multi-select mode like the other single-commit actions

---

## 33. Viewer Mode
Run the tool as a read-only browser.

**Screenshot:** `screenshots/viewer-mode.webp`

![Viewer Mode](screenshots/viewer-mode.webp)

**Description:** Launch with `--viewer-mode` to disable all history-modifying operations (rebase, squash, rephrase, split, cherry-pick, reset, etc.). The tool highlights the **Exit Viewer Mode** button and shows a notice when entering Viewer Mode; press it to re-enable editing operations without restarting. Viewer windows (Browse Branch, Browse File Log, Browse Log of a Commit, Browse Reflog, Browse Stashes, PR Preview) open in Viewer Mode automatically.

---

## 34. Themes (Light / Dark)
Toggle between light and dark themes for comfortable viewing.

> **Note:** Most screenshots in this documentation use the **light theme (default)**.

**Screenshot:** `screenshots/dark-theme.webp`

![Dark Theme](screenshots/dark-theme.webp)

**Description:** Switch between light and dark themes to suit your preference. The light theme (default) provides a clean, high-contrast interface for daytime use, while the dark theme features a VS Code-inspired charcoal palette that is easy on the eyes during extended sessions. Click the theme toggle (sun/moon icon) to switch. Theme preference is automatically saved across sessions.

---

## 35. Zoom Controls
Adjust the font size for better readability.

**Description:** Use the zoom controls (+/- buttons) in the toolbar to increase or decrease the font size. Font size preference is automatically saved across sessions.

---

## 36. Mark / Unmark Commit
Mark commits for easy identification.

**Screenshot:** `screenshots/mark-commits.webp`

![Mark / Unmark Commit](screenshots/mark-commits.webp)

**Description:** Right-click any commit and select "Mark / Unmark commit" to toggle a mark. Marked commits display with a distinct background color for easy identification. This helps you keep track of important commits like releases, milestones, or commits that need further attention. Right-click again to unmark.

**Note:** In the screenshot, the 2nd and 4th commits are already marked.

---

## 37. Show Local Branches
Display local and remote branch names alongside commits.

**Description:** Toggle the "show local branches" option (via **Configure → Show/Hide → Show Local Branches** in the main window, see [2. Main Interface](#2-main-interface)) to display branch names next to commits. Local branches are shown in green, and remote branches (e.g., origin/main, origin/master) are shown in orange. This helps you identify which branch a commit belongs to or originated from, making it easier to understand the commit's context and lineage.

**Note:** In the screenshot, local branches feat1, master, and memleak_fix are visible.

---

## 38. Copy to Clipboard
Quickly copy commit details for sharing, debugging, or reference.

**Screenshot:** `screenshots/copy-commit-details.webp`

![Copy to Clipboard](screenshots/copy-commit-details.webp)

**Description:** Right-click any commit and select one of the following options:

- **Copy SHA** → Copy the commit SHA
- **Copy Message** → Copy the commit message
- **Copy Both** → Copy both SHA and commit message

A brief **"Copied!"** notification appears to confirm the action.

---

## 39. Update the Tool

**Screenshot:** `screenshots/update-available-dialog.webp`

![Update the Tool](screenshots/update-available-dialog.webp)

**Description:** When a newer version is available on GitHub, the app tells you about it (via **Configure → Check for updates**). The dialog offers:

- **Update Now** → Update the tool right away. A progress bar runs while the tool updates itself (via `git pull` for a cloned installation, or `pip` upgrade for a pip installation), then reports success or failure and asks you to restart the tool.
- **Copy to clipboard** → Copy the manual update command to run later.
- **Cancel** → Dismiss the dialog.

For a cloned installation, the update refuses to run if the local clone has uncommitted changes — commit or stash them and try again.

#### Startup update check

By default the tool automatically checks for updates in the background when it starts. If an update is available, an **Update(\<sha\>) available** label appears in the status bar next to the **Configure** button. Uncheck **Configure → Check for updates at startup** to disable this.

When running from a cloned repository, press **Ctrl+Shift+F5** after updating to restart with the latest code.

---

## 40. Tag Commit

**Screenshot:** `screenshots/tag-commit.webp`

![Tag Commit](screenshots/tag-commit.webp)

**Description:** Right-click a commit and select **Tag** to open the tagging dialog. Enter a tag name, optionally tick **Annotate** to create an annotated tag with a message, and click **Create Tag**. The new tag appears in the commit list when **Show Tags** is enabled (see [Configure Menu](#5-configure-menu)). Both lightweight and annotated tags are supported.

Use **Browse Tags** (Repo menu) to see all tags in the repository (see [Browse Tags](#43-browse-tags)).

---

## 41. Blame a file

Open a per-line blame viewer for any file in a commit, with search, filtering, and commit inspection.

**Screenshot:** `screenshots/blame-a-file.webp`

![Blame a file](screenshots/blame-a-file.webp)

**Description:** Right-click a file in the **File-wise Diff** tab (or any file list context menu) and select **Blame file** to open a read-only blame viewer styled with a dimmed grey overlay (matching the other browse windows). The viewer shows a table with columns:

- **Commit** — Short SHA (coloured dot, bold) — right-click for context menu
- **Author** — Commit author (hideable via **Show Author** checkbox)
- **Date** — Commit timestamp (hideable via **Show Date** checkbox)
- **Subject** — Commit summary (hideable via **Show Subject** checkbox)
- **Line** — Line number in the file
- **Code** — Line content (monospace, same zoom level as the main window)

Right-click any row to open the context menu:

- **View commit** → Opens the same tabbed diff viewer (Plain + File-wise) as the main window
- **Copy SHA to clipboard** → Copies the commit SHA
- **Blame before this** → Opens a new blame window showing the file as it was in the parent commit (useful for seeing what changed in the blamed line's commit). Shows a friendly message if the file didn't exist before that commit.

The bottom bar also includes **Always On Top**, **Show Author / Date / Subject** column toggles, **Refresh** (re-runs `git blame`), and **Exit**. The search bar supports filtering by **Author**, **Subject**, and **Code** via the **Search Options** dropdown.

---

## 42. Browse Tags

**Screenshot:** `screenshots/browse-tags.webp`

![Browse Tags](screenshots/browse-tags.webp)

**Description:** Open **Browse Tags** from the **Repo** menu to view all tags in the repository. The window shows a table with columns:

- **Tag** — Tag name
- **Commit** — Short SHA of the tagged commit (with coloured dot)
- **Subject** — Commit message summary
- **Date** — Commit timestamp

Right-click a tag to open its commit log or copy details. Double-click a tag to view the commit. The window supports search and filtering like other browse windows.

---

## 43. External Tools Dialog

**Screenshot:** `screenshots/external-tools-dialog.webp`

![External Tools Dialog](screenshots/external-tools-dialog.webp)

**Description:** Open **External tools integration** from the **Configure** menu to configure external diff tool integration. The dialog is organized with a **Diff tool** group box containing three modes:

- **Not configured** — External difftool integration is disabled.
- **Use Git configured difftool** — Uses the difftool configured in your Git settings (`diff.tool`). Shows the detected tool name and status.
- **Use custom command** — Specify a custom diff tool command and arguments (e.g. `kdiff3 {file1} {file2}`).

Click **Refresh** to re-detect the Git difftool, **Save** to persist the choice, or **Cancel** to dismiss. The preference is stored in QSettings and remembered across sessions.

---

## 44. Keyboard Shortcuts
Keyboard shortcuts for faster navigation and workflow.

| Shortcut | Action |
|----------|--------|
| `/` | Focus the commit search bar |
| `Esc` | Clear search, close dialogs, exit search mode, or exit multi-select mode |
| `Ctrl+F` | Focus the diff search bar (available in every diff view) |
| `Ctrl+Q` | Exit the application |
| `Ctrl+Z` | Undo the last operation (disabled while editing text) |
| `F5` | Refresh commit list |
| `Ctrl+Shift+F5` | Restart with latest code (cloned repos only, when update detected) |

**Notes:**

- `Esc` behaves contextually and may close dialogs, clear filters, exit search, or exit multi-select mode depending on the active state.
- `Ctrl+F` focuses the diff search bar, which is available in every diff view (see [Diff Search Bar](#9-diff-search-bar)).
