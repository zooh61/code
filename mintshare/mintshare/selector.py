"""Full-screen overlay for choosing a region / window, picking a colour or measuring (ruler)."""
import math

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo

from . import gfx

ACCENT = (0.20, 0.60, 1.0)


class Overlay(Gtk.Window):
    """mode: 'region' | 'window' | 'color' | 'ruler'.

    ``on_done(result)`` is called with a (x, y, w, h) tuple in virtual-screen coordinates for
    region/window, ``(r, g, b, x, y)`` for color, or None when cancelled.
    """

    def __init__(self, shot, windows, mode="region", on_done=None, cfg=None, initial_rect=None):
        super().__init__(type=Gtk.WindowType.POPUP)
        cfg = cfg or {}
        self.shot, self.windows, self.mode, self.on_done = shot, windows, mode, on_done
        self.snap = cfg.get("snap_to_windows", True) and mode in ("region", "window")
        self.show_magnifier = cfg.get("show_magnifier", True) or mode in ("color",)
        self.show_crosshair = cfg.get("show_crosshair", True)
        self.show_info = cfg.get("show_info", True)
        self.dim = cfg.get("dim", 0.45)
        self.ox, self.oy = shot.x, shot.y
        self.surface = gfx.pil_to_surface(shot.image)
        self.W, self.H = shot.image.width, shot.image.height
        self.px = self.py = 0
        self.start = None
        self.sel = None
        self.hover = None
        self.finished = False
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_keep_above(True)
        self.move(self.ox, self.oy)
        self.resize(self.W, self.H)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("draw", self._draw)
        self.connect("motion-notify-event", self._motion)
        self.connect("button-press-event", self._press)
        self.connect("button-release-event", self._release)
        self.connect("key-press-event", self._key)
        if initial_rect:
            self.sel = tuple(initial_rect)

    # ------------------------------------------------------------ lifecycle
    def run(self):
        self.show_all()
        win = self.get_window()
        cur = Gdk.Cursor.new_from_name(self.get_display(), "crosshair")
        win.set_cursor(cur)
        seat = self.get_display().get_default_seat()
        GLib.timeout_add(30, self._grab, seat, cur)
        _, self.px, self.py = win.get_device_position(seat.get_pointer())[0:3]

    def _grab(self, seat, cur):
        win = self.get_window()
        if win is None:
            return False
        seat.grab(win, Gdk.SeatCapabilities.ALL, True, cur, None, None)
        return False

    def finish(self, result):
        if self.finished:
            return
        self.finished = True
        try:
            self.get_display().get_default_seat().ungrab()
        except Exception:
            pass
        self.destroy()
        if self.on_done:
            GLib.idle_add(self.on_done, result)

    # ------------------------------------------------------------ geometry
    def _norm(self, a, b):
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        return (x0, y0, x1 - x0, y1 - y0)

    def _window_at(self, x, y):
        gx, gy = x + self.ox, y + self.oy
        for w in self.windows:
            if w.x <= gx < w.x + w.w and w.y <= gy < w.y + w.h:
                return w
        return None

    def _local(self, rect):
        return (rect[0] - self.ox, rect[1] - self.oy, rect[2], rect[3])

    # ------------------------------------------------------------ events
    def _motion(self, _w, ev):
        self.px, self.py = ev.x, ev.y
        if self.start is not None:
            self.sel = self._norm(self.start, (ev.x, ev.y))
        elif self.snap or self.mode == "window":
            w = self._window_at(ev.x, ev.y)
            self.hover = self._local(w.rect) if w else None
        self.queue_draw()

    def _press(self, _w, ev):
        if ev.button == 3:
            self.finish(None)
            return True
        if ev.button == 1:
            self.start = (ev.x, ev.y)
            self.sel = (ev.x, ev.y, 0, 0)
            self.press_time = ev.time
        return True

    def _release(self, _w, ev):
        if ev.button != 1 or self.start is None:
            return True
        if self.mode == "color":
            r, g, b = (int(v) for v in self.shot.image.getpixel((int(ev.x), int(ev.y)))[:3])
            self.finish((r, g, b, int(ev.x) + self.ox, int(ev.y) + self.oy))
            return True
        if self.mode == "ruler":
            self.start = None  # keep the measurement on screen
            return True
        x, y, w, h = self.sel or (0, 0, 0, 0)
        dragged = w > 3 and h > 3
        if not dragged:
            if self.hover and (self.snap or self.mode == "window"):
                x, y, w, h = self.hover
                self.finish((x + self.ox, y + self.oy, w, h))
            else:
                self.start, self.sel = None, None
            return True
        self.finish((x + self.ox, y + self.oy, w, h))
        return True

    def _key(self, _w, ev):
        k = ev.keyval
        if k == Gdk.KEY_Escape:
            self.finish(None)
        elif self.mode == "ruler" and k == Gdk.KEY_c and self.sel:
            gfx.copy_text(f"{int(self.sel[2])}x{int(self.sel[3])}")
        elif k in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down):
            dx = {Gdk.KEY_Left: -1, Gdk.KEY_Right: 1}.get(k, 0)
            dy = {Gdk.KEY_Up: -1, Gdk.KEY_Down: 1}.get(k, 0)
            seat = self.get_display().get_default_seat()
            self.get_display().warp_pointer(self.get_screen(), int(self.px) + self.ox + dx, int(self.py) + self.oy + dy)
        elif k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.sel and self.sel[2] > 3:
            x, y, w, h = self.sel
            self.finish((x + self.ox, y + self.oy, w, h))
        return True

    # ------------------------------------------------------------ drawing
    def _label(self, cr, text, x, y):
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription("Sans Bold 10"))
        layout.set_text(text, -1)
        tw, th = layout.get_pixel_size()
        x = min(max(4, x), self.W - tw - 12)
        y = min(max(4, y), self.H - th - 8)
        cr.set_source_rgba(0, 0, 0, 0.8)
        cr.rectangle(x - 4, y - 2, tw + 8, th + 4)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)

    def _draw(self, _w, cr):
        cr.set_source_surface(self.surface, 0, 0)
        cr.paint()
        sel = self.sel if (self.sel and self.sel[2] > 0 and self.sel[3] > 0) else None
        highlight = sel if (sel and self.mode != "ruler") else (self.hover if self.mode != "color" else None)
        if self.mode in ("region", "window") and self.dim:
            cr.set_source_rgba(0, 0, 0, self.dim)
            cr.paint()
            if highlight:
                cr.save()
                cr.rectangle(*highlight)
                cr.clip()
                cr.set_source_surface(self.surface, 0, 0)
                cr.paint()
                cr.restore()
        if highlight and self.mode != "ruler":
            cr.set_line_width(2 if sel else 3)
            cr.set_source_rgb(*ACCENT)
            x, y, w, h = highlight
            cr.rectangle(x + 1, y + 1, w - 2, h - 2)
            cr.stroke()
            if self.show_info:
                self._label(cr, f"{int(w)} × {int(h)}   ({int(x + self.ox)}, {int(y + self.oy)})", x, y - 26 if y > 30 else y + 4)
        if self.mode == "ruler":
            self._draw_ruler(cr)
        if self.show_crosshair and self.start is None and self.mode in ("region", "color"):
            cr.set_line_width(1)
            cr.set_source_rgba(1, 1, 1, 0.55)
            cr.set_dash([4, 4])
            cr.move_to(self.px + .5, 0); cr.line_to(self.px + .5, self.H)
            cr.move_to(0, self.py + .5); cr.line_to(self.W, self.py + .5)
            cr.stroke()
            cr.set_dash([])
        if self.show_magnifier:
            self._draw_loupe(cr)

    def _draw_ruler(self, cr):
        if not self.sel:
            self._label(cr, "Drag to measure • C copies size • Esc closes", 20, 20)
            return
        x, y, w, h = self.sel
        s = self.start or (x, y)
        end = (self.px, self.py) if self.start else (x + w, y + h)
        a = s if self.start else (x, y)
        cr.set_source_rgb(*ACCENT)
        cr.set_line_width(2)
        cr.rectangle(x + .5, y + .5, w, h)
        cr.stroke()
        cr.set_source_rgba(1, 0.3, 0.3, 0.9)
        cr.move_to(*a); cr.line_to(*end)
        cr.stroke()
        dist = math.hypot(w, h)
        ang = math.degrees(math.atan2(-(end[1] - a[1]), end[0] - a[0]))
        self._label(cr, f"W {int(w)}  H {int(h)}  Δ {dist:.1f}px  ∠ {ang:.1f}°", x, y + h + 8)

    def _draw_loupe(self, cr):
        zoom, half = 8, 9
        size = (half * 2 + 1) * zoom
        lx = self.px + 24
        ly = self.py + 24
        if lx + size > self.W:
            lx = self.px - size - 24
        if ly + size + 30 > self.H:
            ly = self.py - size - 40
        cr.save()
        cr.rectangle(lx, ly, size, size)
        cr.clip()
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        cr.translate(lx, ly)
        cr.scale(zoom, zoom)
        cr.translate(half - int(self.px), half - int(self.py))
        cr.set_source_surface(self.surface, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        cr.restore()
        cr.set_source_rgb(*ACCENT)
        cr.set_line_width(2)
        cr.rectangle(lx, ly, size, size)
        cr.stroke()
        cr.set_source_rgb(1, 0.2, 0.2)
        cr.set_line_width(1)
        cx = lx + half * zoom
        cr.rectangle(cx + .5, ly + half * zoom + .5, zoom - 1, zoom - 1)
        cr.stroke()
        try:
            r, g, b = self.shot.image.getpixel((int(self.px), int(self.py)))[:3]
            self._label(cr, f"#{r:02X}{g:02X}{b:02X}  rgb({r},{g},{b})  [{int(self.px + self.ox)},{int(self.py + self.oy)}]",
                        lx, ly + size + 4)
        except Exception:
            pass
