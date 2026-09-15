from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

ICON_DIR = BASE_DIR / "icons"

SHORTCUTS_FILE = BASE_DIR / "config" / "shortcuts.json"

INSTANCE_LOCK_FILE = BASE_DIR / "dofus-focus-tray.lock"
