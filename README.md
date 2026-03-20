# Git Interactive Rebase GUI Tool 🚀

🌐 Live Demo / Project Page: https://shyjun.github.io/git-interactive-rebase-gui-tool/

A Python-based Git Interactive Rebase GUI tool to visually reorder, squash, edit, and manage Git commit history. Built with **PySide6**, this tool simplifies the complex process of rewriting git history with a visual, intuitive interface.

**Keywords:** git rebase gui, interactive rebase tool, git history editor, git squash commits gui

## ✨ Key Features

### 🛠️ Interactive History Rewriting

* **Visual Reordering**: Drag and drop commits to reorder your history.
* **Interactive Squash**: Select neighbor messages or edit your own in a dedicated dialog with real-time feedback.
* **Smart Rephrase**: Effortlessly update commit messages without leaving the app.
* **Instant Drop**: Remove unwanted commits with a single click.
* **Reset Hard**: Quickly reset your branch to a specific commit.

### 🔍 Discovery & Navigation

* **Live Search & Filter**: Instantly find any commit by searching its **SHA** or **Message**. Filtering is live while you type.

  * **Shortcut ****`/`**: Focus search bar.
  * **Shortcut ****`Esc`**: Clear search and return to full history.

### 🎨 Premium User Experience

* **Adaptive Themes**: Seamlessly toggle between a refined **Dark Theme** (VS Code inspired charcoal palette) and a clean **Light Theme**.
* **Global Consistency**: Every button, scrollbar, and dialog follows your chosen theme.
* **Persistent Settings**: Your theme preference and font size are automatically saved across sessions.
* **Visual Feedback**: Instant "Copied" notifications for clipboard actions (SHA, Message, or both).

### ⚡ Power User Efficiency

* **Inclusive Range History**: View and edit history all the way down to the root commit or a specific parent.
* **Headless Execution**: Rebase operations run in the background without blocking or spawning external editors.
* **Clean Startup**: Defaults to Light Theme on the first run with optimized loading to prevent flickering.

---

## 📸 Screenshot

---

## 🎥 Demo Video

Coming soon...

---

## 🤔 Why this tool?

Interactive rebasing in Git is powerful but error-prone when editing raw todo files.
This tool provides a visual interface to simplify and safely manage commit history.

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

Install the latest version directly from GitHub:

```bash
pip install git+https://github.com/shyjun/git-interactive-rebase-gui-tool.git
```

Run the application:

```bash
git-interactive-rebase
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

This project is actively under development.

### If installed via pip (GitHub method)

```bash
pip uninstall git-interactive-rebase-gui-tool
pip install git+https://github.com/shyjun/git-interactive-rebase-gui-tool.git
```

### If installed by clonning repository

```bash
git pull
```


---

## 📄 License

This project is open-source. Feel free to contribute or adapt it for your own Git workflows!
