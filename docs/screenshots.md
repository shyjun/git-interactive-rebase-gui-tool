# Screenshots & Feature Guide

Visual documentation for the Git Interactive Rebase GUI Tool. Each section showcases a feature with a screenshot and brief description.

**Note:** [Vim official repository](https://github.com/vim/vim) is used for demonstration purposes.

---

## Table of Contents

1. [Launch](#1-launch)
2. [Main Interface](#2-main-interface)
3. [Context Menu](#3-context-menu)
4. [Search & Filter](#4-search--filter)
5. [Themes (Light / Dark)](#5-themes-light--dark)
6. [Zoom Controls](#6-zoom-controls)
7. [Mark / Unmark Commit](#7-mark--unmark-commit)
8. [Show Local Branches](#8-show-local-branches)
9. [Copy to Clipboard](#9-copy-to-clipboard)
10. [Diff Viewer](#10-diff-viewer)
11. [File-wise Diff Viewer](#11-file-wise-diff-viewer)
12. [Rephrase Commit](#12-rephrase-commit)
13. [Drop Commit](#13-drop-commit)
14. [Drag to Reorder](#14-drag-to-reorder)
15. [Squash Commits](#15-squash-commits)
16. [Split Dialog](#16-split-dialog)
17. [Reset Options](#17-reset-options)
18. [Rebase Options](#18-rebase-options)

---

## 1. Launch

Launch the application with options to choose the number of commits to view.

### Option 1: Show commits since a specific commit (provide SHA as argument)
View only the most recent N commits in the current branch. You can specify the number of commits using `~N` or `^^^...` (each `^` represents one commit).

```bash
python3 git_interactive_rebase.py <commit-sha>
python3 git_interactive_rebase.py HEAD~N
python3 git_interactive_rebase.py HEAD^^^
```

**Screenshot:** `screenshots/head-commits.png`

![Launch with HEAD commits](screenshots/head-commits.png)

**Description:** The screenshot above shows the result of running `python3 git_interactive_rebase.py HEAD~6`.

### Option 2: Auto-detect branch base (shows commits from where current branch diverged)
When no commit SHA is provided, the tool automatically detects the base branch (e.g., main/master) and displays commits since that point. If detection fails, it falls back to showing the 200 most recent commits from HEAD.

**Screenshot:** `screenshots/selected_commits_history.png`

![Launch with Selected History](screenshots/selected_commits_history.png)

---

## 2. Main Interface

The main window displays your commit history in an interactive list with action controls.

**Screenshot:** `screenshots/main-interface.png`

![Main Interface](screenshots/main-interface.png)

**Description:** The main window shows the commit list with SHA, message, and branch indicators. The details panel displays commit metadata (SHA, author, date, changed files). The right side pane shows diffs in plain view or file-wise view. The top toolbar includes search, theme toggle, zoom controls, and reset options. Right-click any commit to access the context menu with all rebase actions.

---

## 3. Context Menu

Access all commit actions via right-click menu.

**Screenshot:** `screenshots/context-menu.png`

![Context Menu](screenshots/context-menu.png)

**Description:** Right-click any commit to see the context menu with all available actions:
- View full commit
- Copy SHA / Copy Message / Copy Both
- Squash with above
- Rephrase
- Drop
- Split
- Mark / Unmark commit
- Reset hard to this commit

---

## 4. Search & Filter

Instantly find commits by SHA or message.

**Screenshot:** `screenshots/search-filter.png`

![Search & Filter](screenshots/search-filter.png)

**Description:** Click the search bar or press `/` to focus it. Type to filter commits live. Press `Esc` to clear the search and return to the full history. Filtering works as you type.

---

## 5. Themes (Light / Dark)

Toggle between light and dark themes for comfortable viewing.

**Screenshot:** `screenshots/light-theme.png`

![Light Theme](screenshots/light-theme.png)

**Screenshot:** `screenshots/dark-theme.png`

![Dark Theme](screenshots/dark-theme.png)

**Description:** Switch between light and dark themes to suit your preference. Light theme (default) provides a clean, high-contrast interface for daytime use. Dark theme features a VS Code-inspired charcoal palette that is easy on the eyes. Click the theme toggle (sun/moon icon) to switch. Theme preference is automatically saved across sessions.

---

## 6. Zoom Controls

Adjust the font size for better readability.

**Screenshot:** `screenshots/zoom-controls.png`

![Zoom Controls](screenshots/zoom-controls.png)

**Description:** Use the zoom controls (+/- buttons) in the toolbar to increase or decrease the font size. Font size preference is automatically saved across sessions.

---

## 7. Mark / Unmark Commit

Mark commits for easy identification.

**Screenshot:** `screenshots/mark-commits.png`

![Mark / Unmark Commit](screenshots/mark-commits.png)

**Description:** Right-click any commit and select "Mark / Unmark commit" to toggle a mark. Marked commits display with a distinct background color for easy identification. This helps you keep track of important commits like releases, milestones, or commits that need further attention. Right-click again to unmark.

**Note:** In the screenshot, the 2nd and 4th commits are already marked.

---

## 8. Show Local Branches

Display local and remote branch names alongside commits.

**Screenshot:** `screenshots/show-local-branches.png`

![Show Local Branches](screenshots/show-local-branches.png)

**Description:** Toggle the "show local branches" checkbox to display branch names next to commits. Local branches are shown in green, and remote branches (e.g., origin/main, origin/master) are shown in orange. This helps you identify which branch a commit belongs to or originated from, making it easier to understand the commit's context and lineage.

**Note:** In the screenshot, local branches feat1, master, and memleak_fix are visible.

---

## 9. Copy to Clipboard

**Screenshot:** `screenshots/copy-commit-details.png`

![Copy to Clipboard](screenshots/copy-commit-details.png)

**Description:** Right-click any commit and select "Copy SHA", "Copy Message", or "Copy Both" to copy to clipboard. A "Copied!" notification appears briefly to confirm the action.

---

## 10. Diff Viewer

View code changes with syntax highlighting for added and removed lines.

**Screenshot:** `screenshots/diff-viewer.png`

![Diff Viewer](screenshots/diff-viewer.png)

**Description:** Click any commit to view its diff in the right panel. Added lines are highlighted in green, removed lines in red. The diff is displayed in a scrollable view with line numbers.

---

## 11. File-wise Diff Viewer

Browse commit changes file by file.

**Screenshot:** `screenshots/file-wise-diff-viewer.png`

![File-wise Diff Viewer](screenshots/file-wise-diff-viewer.png)

**Description:** Click the "File-wise View" button to open a dialog listing all changed files. Select any file to view its specific diff. This makes it easy to understand what each file contributed to the commit.

---

## 12. Rephrase Commit

Update the commit message without changing the commit contents.

**Screenshot:** `screenshots/rephrase-commit.png`

![Rephrase Commit](screenshots/rephrase-commit.png)

**Description:** Right-click a commit and select "Rephrase" to open the rephrase dialog. Edit the commit message and click "Confirm" to apply the new message.

---

## 13. Drop Commit

Remove a commit entirely from the history.

**Screenshot:** `screenshots/drop-commit.png`

![Drop Commit](screenshots/drop-commit.png)

**Description:** Right-click a commit and select "Drop" to see a confirmation dialog. Confirm to remove the commit from the history. This action is irreversible without resetting.

---

## 14. Drag to Reorder

Drag commits up or down to change their order in the history.

**Screenshot:** `screenshots/drag-reorder.png`

![Drag to Reorder](screenshots/drag-reorder.png)

**Description:** Click and hold on any commit item, then drag it to a new position. A visual indicator shows where the commit will be placed. Drop to confirm the reorder.

---

## 15. Squash Commits

Combine multiple commits into one.

### Option 1: Squash Commit with above / below commit
Squash a commit with its immediate neighbor (above or below).

**Screenshot:** `screenshots/squash-context-menu.png` (context menu)

![Squash Context Menu](screenshots/squash-context-menu.png)

**Screenshot:** `screenshots/squash-dialogue.png` (dialog)

![Squash Dialog](screenshots/squash-dialogue.png)

**Description:** Right-click a commit and select "Squash with above" or "Squash with below" to open the squash dialog. You can either select a commit message from one of the commits being squashed, or enter your own custom commit message. Click "Confirm" to apply.

### Option 2: Select multiple commits and squash them together
Squash multiple adjacent commits at once.

**Screenshot:** `screenshots/multi-squash.png`

![Multi Squash](screenshots/multi-squash.png)

**Description:** Switch to multiple commit selection mode using the highlighted button in the toolbar (or via the context menu), then select multiple adjacent commits by clicking on them. Once selected, click the "Squash selected commits" button (or use the context menu) to open the squash dialog. Edit the combined commit message in the dialog and click "Confirm" to apply.

To exit multi-selection mode without squashing, click the cancel multi-selection button (or use the context menu) to deselect and return to normal mode.

---

## 16. Split Dialog

Break a commit into multiple smaller commits by file or change.

**Screenshot:** `screenshots/split-context-menu.png`

![Split Context Menu](screenshots/split-context-menu.png)

### Option 1: Move single file changes out of a commit
Move changes of a specific file to a separate commit (only for commits with multiple file changes).

**Screenshot:** `screenshots/split-move-single-file-1.png`

![Split Move Single File 1](screenshots/split-move-single-file-1.png)

**Screenshot:** `screenshots/split-move-single-file-2.png`

![Split Move Single File 2](screenshots/split-move-single-file-2.png)

### Option 2: Split each file changes to separate commits
Available only in commits with multiple file changes. Creates one commit per changed file.

**Screenshot:** `screenshots/split-each-to-separate.png`

![Split Each to Separate](screenshots/split-each-to-separate.png)

### Option 3: Split all changes in one file to separate commits
Breaks all changes in a single file into individual commits per file change. Available only in commits with single file changes.

**Screenshot:** `screenshots/split-all-to-separate.png`

![Split All to Separate](screenshots/split-all-to-separate.png)

---

## 17. Reset Options

Fail-safe options to reset your branch to a safe state.

**Screenshot:** `screenshots/reset-options.png`

![Reset Options](screenshots/reset-options.png)

**Description:** Use the "Reset" menu to access fail-safe options:
- **Reset to Best Commit ID**: Reset to a user-defined safe commit. To set the Best Commit ID, right-click any commit and select "Set Best Commit ID"
- **Reset to Start Time Head**: Reset to the commit state when the app launched
- **Reset to Custom Commit**: Choose any commit to reset to

---

## 18. Rebase Options

Rebase your commits onto a different branch.

**Screenshot:** `screenshots/rebase-options.png`

![Rebase Options](screenshots/rebase-options.png)

**Description:** Click "Rebase" to open the rebase dialog. Choose to rebase onto:
- master
- main
- A custom branch

The rebase runs in the background without blocking the UI.

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `/` | Focus search bar |
| `Esc` | Clear search / Close dialog |
| `F5` | Refresh commit list |