# Git History Explorer 🚀

A premium, user-friendly GUI for Git interactive rebasing. Built with **PySide6**, this tool simplifies the complex process of rewriting git history with a visual, intuitive interface.

## ✨ Key Features

### 🛠️ Interactive History Rewriting
- **Visual Reordering**: Drag and drop commits to reorder your history.
- **Interactive Squash**: Select neighbor messages or edit your own in a dedicated dialog with real-time feedback.
- **Smart Rephrase**: Effortlessly update commit messages without leaving the app.
- **Instant Drop**: Remove unwanted commits with a single click.
- **Reset Hard**: Quickly reset your branch to a specific commit.

### 🔍 Discovery & Navigation
- **Live Search & Filter**: Instantly find any commit by searching its **SHA** or **Message**. Filtering is live while you type.
- **Deep Diff Viewer**: Double-click any commit to view a color-coded, syntax-highlighted diff of all changes.

### 🎨 Premium User Experience
- **Adaptive Themes**: Seamlessly toggle between a refined **Dark Theme** (VS Code inspired charcoal palette) and a clean **Light Theme**.
- **Global Consistency**: Every button, scrollbar, and dialog follows your chosen theme.
- **Persistent Settings**: Your theme preference and font size are automatically saved across sessions.
- **Visual Feedback**: Instant "Copied" notifications for clipboard actions (SHA, Message, or both).

### ⚡ Power User Efficiency
- **Inclusive Range History**: View and edit history all the way down to the root commit or a specific parent.
- **Headless Execution**: Rebase operations run in the background without blocking or spawning external editors.
- **Clean Startup**: Defaults to Light Theme on the first run with optimized loading to prevent flickering.

---

## 🚀 Technical Details

- **Core**: Python 3.x
- **GUI Framework**: PySide6 (Qt)
- **Styling**: Global QSS with dynamic color mapping.
- **Git Integration**: Direct subprocess communication with the Git CLI.
- **Persistence**: `QSettings` for cross-platform preference storage.

## 🛠️ Requirements & Usage

### Prerequisites
- Python 3.10+
- Git CLI installed and in your PATH.
- `PySide6` installed (`pip install PySide6`).

### Running the App
Navigate to the project directory and run:

```bash
python git_interactive_rebase.py <commit-sha>
```

Optional: Specify a different location:
```bash
python git_interactive_rebase.py <commit-sha> -C /path/to/repo
```

---

## 📄 License
This project is open-source. Feel free to contribute or adapt it for your own Git workflows!
