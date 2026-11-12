"""Global hotkeys. Backends: Cinnamon custom keybindings (gsettings) or a generic X11 grab (python3-xlib)."""
import os
import shlex
import shutil
import subprocess
import sys
import threading
import json

from . import paths

BACKUP_FILE = os.path.join(paths.CONFIG_DIR, "cinnamon-keybindings-backup.json")
MEDIA_SCHEMA = "org.cinnamon.desktop.keybindings.media-keys"
CIN_SCHEMA = "org.cinnamon.desktop.keybindings"
CIN_KB = "org.cinnamon.desktop.keybindings.custom-keybinding"
PREFIX = "mintshare-"
MEDIA_KEYS = ["screenshot", "screenshot-clip", "area-screenshot", "area-screenshot-clip", "window-screenshot",
              "window-screenshot-clip", "screencast"]


def launcher_command():
    exe = shutil.which("mintshare")
    return shlex.quote(exe) if exe else f"{shlex.quote(sys.executable)} -m mintshare"


def is_cinnamon():
    return "cinnamon" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower() and shutil.which("gsettings") is not None


def _gs(*args):
    return subprocess.run(["gsettings", *args], capture_output=True, text=True)


def _parse_list(out):
    import ast
    out = out.strip()
    if out.startswith("@as"):
        out = out[3:].strip()
    try:
        return list(ast.literal_eval(out))
    except (ValueError, SyntaxError):
        return []


# ---------------------------------------------------------------- Cinnamon backend
def _save_backup(freed):
    """Remember the original built-in bindings (once) so they can be restored exactly."""
    if os.path.exists(BACKUP_FILE):
        data = json.load(open(BACKUP_FILE))
    else:
        data = {"media_keys": {}}
    data["media_keys"].update({k: v for k, v in freed.items() if k not in data["media_keys"]})
    os.makedirs(os.path.dirname(BACKUP_FILE), exist_ok=True)
    with open(BACKUP_FILE, "w") as f:
        json.dump(data, f, indent=1)


def plan_cinnamon(workflows, take_over_print=True):
    """Return a human-readable list of what apply_cinnamon would change (nothing is changed)."""
    lines = []
    for w in workflows:
        if w.get("hotkey"):
            lines.append(f"add custom shortcut  {w['hotkey']:<22} -> MintShare: {w['name']}")
    if take_over_print:
        wanted = {w["hotkey"] for w in workflows if w.get("hotkey")}
        for key in MEDIA_KEYS:
            cur_b = _parse_list(_gs("get", MEDIA_SCHEMA, key).stdout)
            hit = [b for b in cur_b if b in wanted or b.replace("<Primary>", "<Control>") in wanted]
            if hit:
                lines.append(f"clear Cinnamon's own '{key}' shortcut {hit} (a backup is kept; undo with --remove-hotkeys)")
    return lines


def apply_cinnamon(workflows, take_over_print=True):
    cur = _parse_list(_gs("get", CIN_SCHEMA, "custom-list").stdout)
    keep = [c for c in cur if not c.startswith(PREFIX)]
    for old in cur:
        if old.startswith(PREFIX):
            _gs("reset", f"{CIN_KB}:/org/cinnamon/desktop/keybindings/custom-keybindings/{old}/", "binding")
    mine = []
    for i, w in enumerate(workflows):
        if not w.get("hotkey"):
            continue
        ident = f"{PREFIX}{i}"
        path = f"{CIN_KB}:/org/cinnamon/desktop/keybindings/custom-keybindings/{ident}/"
        _gs("set", path, "name", f"MintShare: {w['name']}")
        _gs("set", path, "command", f"{launcher_command()} --workflow {shlex.quote(w['name'])}")
        _gs("set", path, "binding", str([w["hotkey"]]))
        mine.append(ident)
    _gs("set", CIN_SCHEMA, "custom-list", str(keep + mine))
    if take_over_print:
        wanted = {w["hotkey"] for w in workflows if w.get("hotkey")}
        freed = {}
        for key in MEDIA_KEYS:
            cur_b = _parse_list(_gs("get", MEDIA_SCHEMA, key).stdout)
            if any(b in wanted or b.replace("<Primary>", "<Control>") in wanted for b in cur_b):
                freed[key] = cur_b
        if freed:
            _save_backup(freed)                      # backup first, then clear
            for key in freed:
                _gs("set", MEDIA_SCHEMA, key, "[]")
    return len(mine)


def clear_cinnamon():
    """Undo everything apply_cinnamon did: remove our shortcuts and restore Cinnamon's original bindings."""
    cur = _parse_list(_gs("get", CIN_SCHEMA, "custom-list").stdout)
    for old in cur:
        if old.startswith(PREFIX):
            _gs("reset", f"{CIN_KB}:/org/cinnamon/desktop/keybindings/custom-keybindings/{old}/", "binding")
    _gs("set", CIN_SCHEMA, "custom-list", str([c for c in cur if not c.startswith(PREFIX)]))
    restored = []
    if os.path.exists(BACKUP_FILE):
        try:
            for key, val in json.load(open(BACKUP_FILE)).get("media_keys", {}).items():
                _gs("set", MEDIA_SCHEMA, key, str(val))
                restored.append(key)
            os.remove(BACKUP_FILE)
        except (OSError, ValueError):
            pass
    return restored


# ---------------------------------------------------------------- generic X11 backend
class XlibHotkeys:
    """Grabs keys on the root window; calls ``callback(workflow_name)`` (from a worker thread)."""

    def __init__(self, callback):
        self.callback = callback
        self.thread = None
        self.stop_flag = threading.Event()
        self.error = None

    def start(self, workflows):
        self.stop()
        self.error = None
        try:
            import Xlib  # noqa: F401
        except ImportError:
            self.error = "Global hotkeys need python3-xlib: sudo apt install python3-xlib"
            return False
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self._run, args=(list(workflows),), daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.stop_flag.set()
        if self.thread:
            self.thread.join(timeout=1.5)
        self.thread = None

    def _run(self, workflows):
        import select

        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, Gtk
        from Xlib import X, display

        d = display.Display()
        root = d.screen().root
        grabbed = {}
        ignore = [0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask]
        for w in workflows:
            acc = w.get("hotkey")
            if not acc:
                continue
            keyval, mods = Gtk.accelerator_parse(acc)
            if not keyval:
                continue
            code = d.keysym_to_keycode(keyval)
            if not code:
                continue
            mask = 0
            if mods & Gdk.ModifierType.CONTROL_MASK: mask |= X.ControlMask
            if mods & Gdk.ModifierType.SHIFT_MASK: mask |= X.ShiftMask
            if mods & Gdk.ModifierType.MOD1_MASK: mask |= X.Mod1Mask
            if mods & Gdk.ModifierType.SUPER_MASK: mask |= X.Mod4Mask
            for extra in ignore:
                root.grab_key(code, mask | extra, True, X.GrabModeAsync, X.GrabModeAsync)
            grabbed[(code, mask)] = w["name"]
        d.sync()
        wanted_mask = X.ControlMask | X.ShiftMask | X.Mod1Mask | X.Mod4Mask
        while not self.stop_flag.is_set():
            r, _, _ = select.select([d.fileno()], [], [], 0.25)
            if not r:
                continue
            while d.pending_events():
                ev = d.next_event()
                if ev.type == X.KeyPress:
                    name = grabbed.get((ev.detail, ev.state & wanted_mask))
                    if name:
                        self.callback(name)
        try:
            for (code, mask) in grabbed:
                for extra in ignore:
                    root.ungrab_key(code, mask | extra)
            d.sync()
            d.close()
        except Exception:
            pass


def accelerator_label(acc):
    if not acc:
        return ""
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    k, m = Gtk.accelerator_parse(acc)
    return Gtk.accelerator_get_label(k, m) if k else acc


if __name__ == "__main__":      # works without GTK: python3 -m mintshare.hotkeys --remove | --status
    import argparse
    ap = argparse.ArgumentParser(prog="mintshare.hotkeys")
    ap.add_argument("--remove", action="store_true", help="remove MintShare shortcuts and restore Cinnamon's originals")
    ap.add_argument("--status", action="store_true", help="show what MintShare changed")
    a = ap.parse_args()
    if not is_cinnamon():
        print("Not a Cinnamon session: MintShare did not change any desktop shortcuts.")
    elif a.remove:
        r = clear_cinnamon()
        print("MintShare shortcuts removed." + (f" Restored: {', '.join(r)}." if r else ""))
    else:
        cur = _parse_list(_gs("get", CIN_SCHEMA, "custom-list").stdout)
        print("MintShare shortcuts:", [c for c in cur if c.startswith(PREFIX)] or "none")
        print("Backup of original bindings:", "present" if os.path.exists(BACKUP_FILE) else "none")
