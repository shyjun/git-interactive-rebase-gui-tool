# Git Interactive Rebase GUI Tool 🚀

🌐 **Live Demo / Project Page:** https://shyjun.github.io/git-interactive-rebase-gui-tool/

**A clean visual GUI for `git rebase -i`** — reorder, squash, split, rephrase, drop, and refine commit history with an intuitive interface.

A Python-based Git Interactive Rebase GUI tool to visually manage commit history. Built with **PySide6**, this tool simplifies the complex process of rewriting Git history with a faster and more visual workflow.

**Keywords:** git rebase gui, interactive rebase tool, git history editor, git squash commits gui

## ✨ Key Features

### 🛠️ Interactive History Rewriting

* **Visual Reordering**: Drag and drop commits to reorder your history.
* **Interactive Squash**: Select neighbor messages or edit your own in a dedicated dialog with real-time feedback.
* **Smart Rephrase**: Effortlessly update commit messages without leaving the app.
* **Instant Drop**: Remove unwanted commits with a single click.
* **Reset Hard**: Quickly reset your branch to a specific commit.
* **Refine Changes in File**: Selectively keep or drop specific changes/hunks inside a single file within a commit before finalizing commit history.
* **Move Changes to New Commit**: Move selected changes/hunks from a single file within a commit into a separate commit. Useful when a change accidentally landed in the wrong commit — move it out, place it correctly, and squash it with the intended commit.
* **Edit Hunk**: Edit a selected hunk inside a single file within a commit using a lightweight patch editor.
* **Copy Hunk**: Quickly copy a hunk patch to clipboard.

### 🔍 Discovery & Navigation

* **Live Search & Filter**: Instantly find any commit by searching its **SHA** or **Message**. Filtering is live while you type.

### ⌨️ Keyboard Shortcuts

| Shortcut | Action                      |
| -------- | --------------------------- |
| `/`      | Focus search bar            |
| `Esc`    | Clear search / Close dialog |
| `F5`     | Refresh commit history      |

### 🎨 Premium User Experience

* **Adaptive Themes**: Seamlessly toggle between a refined **Dark Theme** (VS Code inspired charcoal palette) and a clean **Light Theme**.
* **Global Consistency**: Every button, scrollbar, and dialog follows your chosen theme.
* **Persistent Settings**: Your theme preference and font size are automatically saved across sessions.
* **Visual Feedback**: Instant "Copied" notifications for clipboard actions (SHA, Message, or both).

### ⚡ Power User Efficiency

* **Inclusive Range History**: View and edit history all the way down to the root commit or a specific parent.
* **Headless Execution**: Rebase operations run in the background without blocking or spawning external editors.
* **Clean Startup**: Defaults to Light Theme on the first run with optimized loading to prevent flickering.
* **Recovery Friendly**: Operations log important commit SHAs, making it easy to reset back to earlier states if needed.

---

## 📸 Screenshots

See the [Screenshots & Feature Guide](docs/screenshots.md) for visual documentation of all features.

---

## 🎥 Demo Video

Coming soon... (Recording in progress)

---

## 🤔 Why this tool?

Interactive rebasing in Git is powerful, but repeatedly editing raw rebase todo files can become tedious during commit cleanup workflows.

This tool is designed as a lightweight visual helper around Git interactive rebase, especially useful while cleaning up a feature branch before raising a PR.

Useful when a commit accidentally contains mixed changes — for example:
feature work + debug code, code + documentation, or unrelated edits inside the same file.

### Why it is different

* **Uses native Git under the hood**

  All operations are executed using standard Git commands.
  No custom Git implementation or hidden logic.

  This also means that when Git itself improves or adds new capabilities, the tool automatically benefits from them.

* **Lightweight setup**

  No heavy installation or large Git client required.

* **Focused specifically on interactive rebase**

  Instead of being a full Git client, the tool focuses only on commit history cleanup workflows:

  * reorder commits
  * squash commits
  * split commits
  * rephrase commits
  * refine file changes
  * move changes to new commits
  * clean up history before PR creation

**Key Strength:** Uses **native Git under the hood** — all operations are executed using standard Git commands.

---

## 🚀 Technical Details

* **Core**: Python 3.x
* **GUI Framework**: PySide6 (Qt)
* **Styling**: Global QSS with dynamic color mapping.
* **Git Integration**: Direct subprocess communication with the Git CLI.
* **Persistence**: `QSettings` for storing theme, font size, and UI preferences across sessions.

---

## 🛠️ Requirements & Usage

### Prerequisites

* Python 3.10+
* Git CLI installed and available in PATH (`git --version` should work).
* `PySide6` installed (`pip install PySide6`).

---

## 📦 Installation (Recommended)

```bash
pip install git+https://github.com/shyjun/git-interactive-rebase-gui-tool.git
```

Then run:

```bash
git_interactive_rebase
```

---

## 🧪 Running Without Installation

If you prefer to run directly from source:

```bash
python3 git_interactive_rebase.py
```

---

## ⚙️ Command Line Arguments

You can pass optional arguments when running the script:

Run from a specific commit:

```bash
python3 git_interactive_rebase.py <commit-sha>
```

Specify a different repository location:

```bash
python3 git_interactive_rebase.py -C /path/to/repo
```

---

## 🔄 Staying Updated

This project is actively under development, with new features and improvements added regularly.

To get the latest enhancements and fixes, update your installation from time to time using the steps below.

### If installed via pip

```bash
pip uninstall git-interactive-rebase-gui-tool
pip install git+https://github.com/shyjun/git-interactive-rebase-gui-tool.git
```

### If installed by cloning repository

```bash
git pull
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

⭐ If this tool helps you, consider starring the repository!
