"""JSON settings with defaults; dotted-path access, atomic saves."""
import copy
import json
import os
import threading

from . import paths

DEFAULT_WORKFLOWS = [
    {"name": "Capture entire screen", "job": "fullscreen", "hotkey": "Print", "overrides": {}},
    {"name": "Capture region", "job": "region", "hotkey": "<Control>Print", "overrides": {}},
    {"name": "Capture active window", "job": "active_window", "hotkey": "<Alt>Print", "overrides": {}},
    {"name": "Start/stop screen recording", "job": "record_screen", "hotkey": "<Shift>Print", "overrides": {}},
    {"name": "Start/stop GIF recording", "job": "record_gif", "hotkey": "<Control><Shift>Print", "overrides": {}},
    {"name": "Capture text (OCR)", "job": "ocr", "hotkey": "<Control><Shift>o", "overrides": {}},
    {"name": "Scrolling capture", "job": "scrolling", "hotkey": "", "overrides": {}},
    {"name": "Screen color picker", "job": "color_picker", "hotkey": "<Control><Shift>c", "overrides": {}},
    {"name": "Ruler", "job": "ruler", "hotkey": "", "overrides": {}},
    {"name": "Region + upload", "job": "region", "hotkey": "",
     "overrides": {"after_capture": {"upload": True}}},
    {"name": "Region + editor", "job": "region", "hotkey": "",
     "overrides": {"after_capture": {"editor": True}}},
]

DEFAULTS = {
    "general": {
        "notifications": True, "play_sound": True, "tray_icon": True, "start_minimized": False,
        "autostart": False, "take_over_print_screen": True, "language_ocr": "eng",
        "show_main_window_on_start": True,
    },
    "capture": {
        "show_cursor": False, "delay": 0.0, "snap_to_windows": True, "show_magnifier": True,
        "show_crosshair": True, "show_info": True, "dim": 0.45, "last_region": None,
        "include_window_shadow": False, "scroll_delay": 0.45, "scroll_max_steps": 40,
        "scroll_amount": 5, "auto_interval": 5.0, "auto_count": 0, "webpage_width": 1366,
        "webpage_height": 768,
    },
    "after_capture": {
        "effects": False, "editor": False, "copy_image": True, "print": False, "save": True,
        "save_as": False, "upload": False, "pin": False, "ocr": False,
        "delete_after_upload": False, "open_folder": False, "open_file": False,
    },
    "after_upload": {"shorten": False, "copy_url": True, "open_url": False, "show_qr": False},
    "image": {
        "format": "png", "jpg_quality": 90, "webp_quality": 90,
        "auto_jpg_over_kb": 0, "save_dir": "", "subfolder": "%y-%mo",
        "filename": "Screenshot_%y-%mo-%d_%h-%mi-%s", "text_filename": "Text_%y-%mo-%d_%h-%mi-%s",
        "clipboard_format": "png",
    },
    "effects": {
        "resize_enabled": False, "resize_percent": 100, "border": 0, "border_color": "#000000",
        "shadow": False, "shadow_offset": 6, "shadow_blur": 8, "rounded": 0,
        "watermark_enabled": False, "watermark_text": "MintShare", "watermark_opacity": 0.5,
        "watermark_position": "bottom-right", "watermark_image": "", "grayscale": False,
    },
    "destinations": {
        "image": "catbox", "text": "paste.rs", "file": "catbox", "url_shortener": "is.gd",
    },
    "uploaders": {},
    "recording": {
        "fps": 30, "gif_fps": 15, "gif_max_width": 960, "audio": False, "audio_source": "default",
        "draw_cursor": True, "codec": "libx264", "crf": 23, "container": "mp4", "dir": "",
        "filename": "Recording_%y-%mo-%d_%h-%mi-%s", "area": "region",
        "after_record": {"copy_path": False, "upload": False, "open_folder": False, "save": True},
    },
    "history": {"enabled": True, "max_entries": 5000},
    "workflows": DEFAULT_WORKFLOWS,
    "main_window": {"width": 900, "height": 600},
}


def _merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


class Config:
    def __init__(self, path: str | None = None):
        self.path = path or paths.SETTINGS_FILE
        self.lock = threading.RLock()
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                _merge(self.data, json.load(f))
        except (OSError, ValueError):
            pass

    def save(self):
        with self.lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)

    def get(self, dotted: str, default=None):
        cur = self.data
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def set(self, dotted: str, value, save: bool = True):
        with self.lock:
            parts = dotted.split(".")
            cur = self.data
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur[parts[-1]] = value
        if save:
            self.save()

    def effective(self, overrides: dict | None):
        """Return a copy of the settings with workflow overrides applied."""
        d = copy.deepcopy(self.data)
        if overrides:
            _merge(d, copy.deepcopy(overrides))
        return d

    # convenience
    def save_dir(self) -> str:
        return self.get("image.save_dir") or os.path.join(paths.pictures_dir(), "MintShare")

    def video_dir(self) -> str:
        return self.get("recording.dir") or os.path.join(paths.videos_dir(), "MintShare")
