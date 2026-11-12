"""Floating control bar shown while recording."""
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk


class RecordingBar(Gtk.Window):
    def __init__(self, on_stop, rect=None, gif=False):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.on_stop, self.t0 = on_stop, time.time()
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_resizable(False)
        box = Gtk.Box(spacing=10)
        box.set_border_width(8)
        self.dot = Gtk.Label(label="●")
        self.dot.get_style_context().add_class("recdot")
        css = Gtk.CssProvider()
        css.load_from_data(b".recdot{color:#e74c3c;font-size:18px} window{background:#222;color:#eee;border-radius:8px}")
        Gtk.StyleContext.add_provider_for_screen(self.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.lbl = Gtk.Label(label="REC GIF 00:00" if gif else "REC 00:00")
        btn = Gtk.Button(label="■ Stop")
        btn.connect("clicked", lambda *_: self._stop())
        box.pack_start(self.dot, False, False, 0)
        box.pack_start(self.lbl, False, False, 0)
        box.pack_start(btn, False, False, 0)
        self.add(box)
        self.show_all()
        # place outside the recorded rectangle when there is room
        scr = self.get_screen()
        sw, sh = scr.get_width(), scr.get_height()
        _, nat = self.get_preferred_size()
        if rect:
            x, y, w, h = rect
            px = min(max(0, x + w // 2 - nat.width // 2), sw - nat.width)
            py = y - nat.height - 6 if y > nat.height + 10 else (y + h + 6 if y + h + nat.height + 10 < sh else y + 6)
            self.move(px, max(0, py))
        else:
            self.move(sw // 2 - nat.width // 2, 6)
        self.gif = gif
        self.timer = GLib.timeout_add(500, self._tick)

    def _tick(self):
        s = int(time.time() - self.t0)
        self.lbl.set_text(f"REC {'GIF ' if self.gif else ''}{s // 60:02d}:{s % 60:02d}")
        self.dot.set_opacity(1.0 if s % 2 == 0 else 0.35)
        return True

    def _stop(self):
        GLib.source_remove(self.timer)
        cb, self.on_stop = self.on_stop, None
        self.destroy()
        if cb:
            cb()

    def close_silently(self):
        try:
            GLib.source_remove(self.timer)
        except Exception:
            pass
        self.on_stop = None
        self.destroy()
