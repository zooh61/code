"""Standard locations (XDG) used by MintShare."""
import os

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), "mintshare")
DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.join(HOME, ".local", "share")), "mintshare")
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.join(HOME, ".cache")), "mintshare")
CUSTOM_UPLOADERS_DIR = os.path.join(CONFIG_DIR, "uploaders")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
HISTORY_DB = os.path.join(DATA_DIR, "history.db")
AUTOSTART_FILE = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), "autostart", "mintshare.desktop")


def pictures_dir():
    d = os.environ.get("XDG_PICTURES_DIR")
    if d:
        return d
    try:
        cfg = os.path.join(HOME, ".config", "user-dirs.dirs")
        for line in open(cfg, encoding="utf-8"):
            if line.startswith("XDG_PICTURES_DIR"):
                return line.split("=", 1)[1].strip().strip('"').replace("$HOME", HOME)
    except OSError:
        pass
    return os.path.join(HOME, "Pictures")


def videos_dir():
    try:
        cfg = os.path.join(HOME, ".config", "user-dirs.dirs")
        for line in open(cfg, encoding="utf-8"):
            if line.startswith("XDG_VIDEOS_DIR"):
                return line.split("=", 1)[1].strip().strip('"').replace("$HOME", HOME)
    except OSError:
        pass
    return os.path.join(HOME, "Videos")


def ensure(*dirs):
    for d in dirs:
        os.makedirs(d, exist_ok=True)
