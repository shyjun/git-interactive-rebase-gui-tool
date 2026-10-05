"""The one QSettings store the tool uses.

Historically there were three: a prototype-era "shyjun/GitInteractiveRebase"
(core UI prefs), "git-interactive-rebase-gui-tool/config" (Configure dialog:
difftool + update check), and "git-interactive-rebase-gui-tool/settings"
(theme reads). The theme was written to the first and read from the third,
so it never persisted across restarts. All code now goes through
tool_settings(); on first run migrate_legacy_settings() copies the old keys
into the one store and deletes the old files.
"""
import os

from PySide6.QtCore import QSettings

ORG = "git-interactive-rebase-gui-tool"
APP = "config"

_LEGACY = (
    ("shyjun", "GitInteractiveRebase"),
    (ORG, "settings"),
)
_MIGRATED_KEY = "legacy_settings_migrated"


def tool_settings():
    """The canonical store: ~/.config/git-interactive-rebase-gui-tool/config.conf."""
    return QSettings(ORG, APP)


def migrate_legacy_settings():
    """One-time: copy the old stores into the canonical one, then delete them.

    Never raises - settings trouble must not prevent startup. Runs fine under
    the screenshots robot's XDG_CONFIG_HOME, where it migrates the robot's
    seeded legacy files (the robot re-seeds them every run).
    """
    try:
        dest = tool_settings()
        if dest.value(_MIGRATED_KEY, False, type=bool):
            return
        for org, app in _LEGACY:
            src = QSettings(org, app)
            for key in src.allKeys():
                if not dest.contains(key):
                    dest.setValue(key, src.value(key))
            src.clear()
            src.sync()
            try:
                os.remove(src.fileName())
            except FileNotFoundError:
                pass
        dest.setValue(_MIGRATED_KEY, True)
        dest.sync()
    except Exception:
        pass


def clear_all_settings():
    """Reset Preferences: wipe the canonical store and any legacy leftovers."""
    for org, app in ((ORG, APP),) + _LEGACY:
        s = QSettings(org, app)
        s.clear()
        s.sync()
        try:
            os.remove(s.fileName())
        except FileNotFoundError:
            pass
