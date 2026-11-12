"""Image editor with annotation tools (shapes, arrows, text, step numbers, blur, pixelate, spotlight, crop)."""
import math
import os

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo
from PIL import Image

from .. import effects, gfx

TOOLS = [
    ("move", "Pan / select", "input-mouse-symbolic"),
    ("rect", "Rectangle", "media-playback-stop-symbolic"),
    ("ellipse", "Ellipse", "media-record-symbolic"),
    ("line", "Line", "list-remove-symbolic"),
    ("arrow", "Arrow", "go-next-symbolic"),
    ("pen", "Freehand pen", "document-edit-symbolic"),
    ("highlight", "Highlighter", "format-text-underline-symbolic"),
    ("text", "Text", "insert-text-symbolic"),
    ("step", "Step number", "emblem-ok-symbolic"),
    ("blur", "Blur", "view-reveal-symbolic"),
    ("pixelate", "Pixelate", "view-grid-symbolic"),
    ("spotlight", "Spotlight", "weather-clear-symbolic"),
    ("crop", "Crop", "transform-crop-symbolic"),
]


def draw_shape(cr, tool, p0, p1, pts, color, width, fill):
    """Draw a vector annotation onto a cairo context in image coordinates."""
    r, g, b, a = color
    cr.set_line_width(width)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    x0, y0 = p0
    x1, y1 = p1
    if tool == "rect":
        cr.rectangle(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
        if fill:
            cr.set_source_rgba(r, g, b, a * 0.35)
            cr.fill_preserve()
        cr.set_source_rgba(r, g, b, a)
        cr.stroke()
    elif tool == "ellipse":
        w, h = abs(x1 - x0) / 2, abs(y1 - y0) / 2
        if w > 0 and h > 0:
            cr.save()
            cr.translate((x0 + x1) / 2, (y0 + y1) / 2)
            cr.scale(w, h)
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()
            if fill:
                cr.set_source_rgba(r, g, b, a * 0.35)
                cr.fill_preserve()
            cr.set_source_rgba(r, g, b, a)
            cr.stroke()
    elif tool in ("line", "arrow"):
        cr.set_source_rgba(r, g, b, a)
        cr.move_to(x0, y0)
        cr.line_to(x1, y1)
        cr.stroke()
        if tool == "arrow" and (x0, y0) != (x1, y1):
            ang = math.atan2(y1 - y0, x1 - x0)
            head = max(14, width * 4.5)
            for s in (-1, 1):
                cr.move_to(x1, y1)
                cr.line_to(x1 - head * math.cos(ang - s * 0.45), y1 - head * math.sin(ang - s * 0.45))
            cr.stroke()
            cr.move_to(x1, y1)
            cr.line_to(x1 - head * math.cos(ang - 0.45), y1 - head * math.sin(ang - 0.45))
            cr.line_to(x1 - head * math.cos(ang + 0.45), y1 - head * math.sin(ang + 0.45))
            cr.close_path()
            cr.fill()
    elif tool in ("pen", "highlight") and pts:
        if tool == "highlight":
            cr.set_line_width(max(width * 4, 14))
            cr.set_line_cap(cairo.LINE_CAP_SQUARE)
            cr.set_source_rgba(r, g, b, 0.38)
        else:
            cr.set_source_rgba(r, g, b, a)
        cr.move_to(*pts[0])
        for p in pts[1:]:
            cr.line_to(*p)
        if len(pts) == 1:
            cr.line_to(pts[0][0] + .01, pts[0][1])
        cr.stroke()


def draw_text(cr, x, y, text, color, size, background=False):
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription(f"Sans Bold {size}"))
    layout.set_text(text, -1)
    w, h = layout.get_pixel_size()
    r, g, b, a = color
    if background:
        cr.set_source_rgba(r, g, b, 0.9)
        cr.rectangle(x - 6, y - 4, w + 12, h + 8)
        cr.fill()
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        cr.set_source_rgba(0, 0, 0, 1) if lum > 0.6 else cr.set_source_rgba(1, 1, 1, 1)
    else:
        # thin outline for legibility on busy screenshots
        cr.move_to(x, y)
        PangoCairo.layout_path(cr, layout)
        cr.set_source_rgba(1, 1, 1, 0.9) if (0.299 * r + 0.587 * g + 0.114 * b) < 0.6 else cr.set_source_rgba(0, 0, 0, 0.7)
        cr.set_line_width(max(2, size / 6))
        cr.stroke()
        cr.set_source_rgba(r, g, b, a)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)


def draw_step(cr, x, y, n, color, radius):
    r, g, b, a = color
    cr.arc(x, y, radius, 0, 2 * math.pi)
    cr.set_source_rgba(r, g, b, a)
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, 1)
    cr.set_line_width(max(2, radius / 7))
    cr.stroke()
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription(f"Sans Bold {int(radius * 0.95)}"))
    layout.set_text(str(n), -1)
    w, h = layout.get_pixel_size()
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    cr.set_source_rgba(0, 0, 0, 1) if lum > 0.65 else cr.set_source_rgba(1, 1, 1, 1)
    cr.move_to(x - w / 2, y - h / 2)
    PangoCairo.show_layout(cr, layout)


class Editor(Gtk.Window):
    MAX_UNDO = 30

    def __init__(self, img, title="", on_done=None, app=None):
        super().__init__(title="MintShare – Image editor")
        self.img = img.convert("RGBA")
        self.on_done, self.app = on_done, app
        self.undo_stack, self.redo_stack = [], []
        self.tool = "rect"
        self.zoom = 1.0
        self.step_n = 1
        self.drag = None
        self.pts = []
        self.cursor = (0, 0)
        self.finished = False
        self.set_default_size(1100, 760)
        self.set_icon_name("applets-screenshooter")
        self._build()
        self._refresh_surface()
        self.connect("delete-event", self._on_close)
        self.connect("key-press-event", self._on_key)
        GLib.idle_add(self._fit)

    # ------------------------------------------------------------ UI
    def _build(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)
        tb = Gtk.Toolbar()
        tb.set_icon_size(Gtk.IconSize.SMALL_TOOLBAR)
        tb.set_style(Gtk.ToolbarStyle.BOTH_HORIZ)
        vbox.pack_start(tb, False, False, 0)
        group = None
        self.tool_buttons = {}
        for key, label, icon in TOOLS:
            b = Gtk.RadioToolButton.new_from_widget(group) if group else Gtk.RadioToolButton()
            group = group or b
            b.set_label(label)
            b.set_tooltip_text(label)
            b.set_icon_name(icon)
            b.set_is_important(False)
            b.connect("toggled", self._tool_toggled, key)
            tb.insert(b, -1)
            self.tool_buttons[key] = b
        self.tool_buttons["rect"].set_active(True)

        # second row: style options + actions
        row = Gtk.Box(spacing=8)
        row.set_border_width(4)
        vbox.pack_start(row, False, False, 0)
        self.color_btn = Gtk.ColorButton.new_with_rgba(gfx.parse_color("#ff3b30"))
        self.color_btn.set_use_alpha(True)
        row.pack_start(Gtk.Label(label="Color"), False, False, 0)
        row.pack_start(self.color_btn, False, False, 0)
        self.width_spin = Gtk.SpinButton.new_with_range(1, 40, 1)
        self.width_spin.set_value(4)
        row.pack_start(Gtk.Label(label="Width"), False, False, 0)
        row.pack_start(self.width_spin, False, False, 0)
        self.size_spin = Gtk.SpinButton.new_with_range(8, 120, 1)
        self.size_spin.set_value(24)
        row.pack_start(Gtk.Label(label="Text size"), False, False, 0)
        row.pack_start(self.size_spin, False, False, 0)
        self.fill_chk = Gtk.CheckButton(label="Fill / label box")
        row.pack_start(self.fill_chk, False, False, 0)
        self.amount_spin = Gtk.SpinButton.new_with_range(2, 60, 1)
        self.amount_spin.set_value(10)
        row.pack_start(Gtk.Label(label="Blur/pixel"), False, False, 0)
        row.pack_start(self.amount_spin, False, False, 0)

        def btn(text, cb, tip=None, pack_end=False):
            b = Gtk.Button(label=text)
            b.connect("clicked", lambda *_: cb())
            if tip:
                b.set_tooltip_text(tip)
            (row.pack_end if pack_end else row.pack_start)(b, False, False, 0)
            return b

        if self.on_done:
            btn("✔ Done", self.done, "Continue with this image (Ctrl+Enter)", True).get_style_context().add_class("suggested-action")
        btn("Upload", self.upload, None, True)
        btn("Copy", self.copy, "Copy to clipboard (Ctrl+C)", True)
        btn("Save as…", self.save_as, "Ctrl+S", True)
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        row.pack_end(sep, False, False, 4)
        btn("Fit", self._fit, None, True)
        btn("100%", lambda: self.set_zoom(1.0), None, True)
        btn("Flip ↔", lambda: self._transform(lambda i: effects.flip(i, True)), None, True)
        btn("Rotate ⟳", lambda: self._transform(lambda i: effects.rotate(i, 90)), None, True)
        btn("Redo", self.redo, "Ctrl+Y", True)
        btn("Undo", self.undo, "Ctrl+Z", True)

        sw = Gtk.ScrolledWindow()
        sw.set_hexpand(True)
        sw.set_vexpand(True)
        self.scroller = sw
        self.canvas = Gtk.DrawingArea()
        self.canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                               Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK)
        self.canvas.connect("draw", self._draw)
        self.canvas.connect("button-press-event", self._press)
        self.canvas.connect("button-release-event", self._release)
        self.canvas.connect("motion-notify-event", self._motion)
        self.canvas.connect("scroll-event", self._scroll)
        sw.add(self.canvas)
        vbox.pack_start(sw, True, True, 0)
        self.status = Gtk.Label(xalign=0)
        self.status.set_margin_start(8)
        vbox.pack_start(self.status, False, False, 2)
        self._update_status()

    def _tool_toggled(self, b, key):
        if b.get_active():
            self.tool = key
            cur = {"move": "default", "text": "text"}.get(key, "crosshair")
            w = getattr(self, "canvas", None) and self.canvas.get_window()
            if w:
                w.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), cur))

    def _color(self):
        c = self.color_btn.get_rgba()
        return (c.red, c.green, c.blue, c.alpha)

    # ------------------------------------------------------------ model
    def _refresh_surface(self):
        self.surface = gfx.pil_to_surface(self.img)
        self.canvas.set_size_request(int(self.img.width * self.zoom), int(self.img.height * self.zoom))
        self.canvas.queue_draw()
        self._update_status()

    def _push_undo(self):
        self.undo_stack.append((self.img.copy(), self.step_n))
        del self.undo_stack[:-self.MAX_UNDO]
        self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append((self.img, self.step_n))
            self.img, self.step_n = self.undo_stack.pop()
            self._refresh_surface()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append((self.img, self.step_n))
            self.img, self.step_n = self.redo_stack.pop()
            self._refresh_surface()

    def _transform(self, fn):
        self._push_undo()
        self.img = fn(self.img)
        self._refresh_surface()

    def _with_cairo(self, fn):
        surf = gfx.pil_to_surface(self.img)
        cr = cairo.Context(surf)
        fn(cr)
        self.img = gfx.surface_to_pil(surf)

    def commit(self, tool, p0, p1, pts):
        x0, y0 = p0
        x1, y1 = p1
        w = self.width_spin.get_value()
        box = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        big = (box[2] - box[0] >= 2 and box[3] - box[1] >= 2)
        if tool in ("blur", "pixelate", "spotlight", "crop") and not big:
            return
        if tool in ("rect", "ellipse", "line", "arrow") and (abs(x1 - x0) + abs(y1 - y0)) < 2:
            return
        self._push_undo()
        amount = self.amount_spin.get_value()
        if tool == "blur":
            self.img = effects.blur_region(self.img, box, amount)
        elif tool == "pixelate":
            self.img = effects.pixelate_region(self.img, box, amount)
        elif tool == "spotlight":
            self.img = effects.spotlight(self.img, box, 0.6)
        elif tool == "crop":
            self.img = self.img.crop(tuple(int(v) for v in (max(0, box[0]), max(0, box[1]),
                                                             min(self.img.width, box[2]), min(self.img.height, box[3]))))
            GLib.idle_add(self._fit)
        else:
            self._with_cairo(lambda cr: draw_shape(cr, tool, p0, p1, pts, self._color(), w, self.fill_chk.get_active()))
        self._refresh_surface()

    def ask_text(self):
        d = Gtk.Dialog(title="Text", transient_for=self, modal=True)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Add", Gtk.ResponseType.OK)
        tv = Gtk.TextView()
        tv.set_size_request(380, 110)
        tv.set_wrap_mode(Gtk.WrapMode.WORD)
        d.get_content_area().pack_start(tv, True, True, 8)
        d.set_default_response(Gtk.ResponseType.OK)
        d.show_all()
        text = None
        if d.run() == Gtk.ResponseType.OK:
            b = tv.get_buffer()
            text = b.get_text(b.get_start_iter(), b.get_end_iter(), False)
        d.destroy()
        return text

    # ------------------------------------------------------------ canvas events
    def _pt(self, ev):
        return (ev.x / self.zoom, ev.y / self.zoom)

    def _press(self, _w, ev):
        if ev.button != 1:
            return
        p = self._pt(ev)
        if self.tool == "text":
            t = self.ask_text()
            if t:
                self._push_undo()
                self._with_cairo(lambda cr: draw_text(cr, p[0], p[1], t, self._color(), self.size_spin.get_value(),
                                                      self.fill_chk.get_active()))
                self._refresh_surface()
            return
        if self.tool == "step":
            self._push_undo()
            n, rad = self.step_n, 12 + self.width_spin.get_value() * 2.5
            self._with_cairo(lambda cr: draw_step(cr, p[0], p[1], n, self._color(), rad))
            self.step_n += 1
            self._refresh_surface()
            return
        if self.tool == "move":
            adj = (self.scroller.get_hadjustment(), self.scroller.get_vadjustment())
            self.drag = ("pan", ev.x_root, ev.y_root, adj[0].get_value(), adj[1].get_value())
            return
        self.drag = ("draw", p, p)
        self.pts = [p]

    def _motion(self, _w, ev):
        p = self._pt(ev)
        self.cursor = p
        if self.drag:
            if self.drag[0] == "pan":
                _, rx, ry, hx, vy = self.drag
                self.scroller.get_hadjustment().set_value(hx - (ev.x_root - rx))
                self.scroller.get_vadjustment().set_value(vy - (ev.y_root - ry))
            else:
                self.drag = ("draw", self.drag[1], p)
                if self.tool in ("pen", "highlight"):
                    self.pts.append(p)
                self.canvas.queue_draw()
        self._update_status()

    def _release(self, _w, ev):
        if ev.button != 1 or not self.drag:
            return
        d, self.drag = self.drag, None
        if d[0] == "draw":
            p0, p1 = d[1], self._pt(ev)
            pts = self.pts + [p1] if self.tool in ("pen", "highlight") else []
            self.commit(self.tool, p0, p1, pts)
            self.pts = []
        self.canvas.queue_draw()

    def _scroll(self, _w, ev):
        if ev.state & Gdk.ModifierType.CONTROL_MASK:
            if ev.direction == Gdk.ScrollDirection.UP:
                self.set_zoom(self.zoom * 1.15)
            elif ev.direction == Gdk.ScrollDirection.DOWN:
                self.set_zoom(self.zoom / 1.15)
            return True
        return False

    def _on_key(self, _w, ev):
        ctrl = ev.state & Gdk.ModifierType.CONTROL_MASK
        k = Gdk.keyval_name(ev.keyval)
        if ctrl and k == "z":
            self.undo()
        elif ctrl and k in ("y", "Z"):
            self.redo()
        elif ctrl and k == "s":
            self.save_as()
        elif ctrl and k == "c" and not isinstance(self.get_focus(), Gtk.Editable):
            self.copy()
        elif ctrl and k in ("Return", "KP_Enter") and self.on_done:
            self.done()
        elif k == "Escape":
            self.close()
        else:
            return False
        return True

    # ------------------------------------------------------------ drawing
    def set_zoom(self, z):
        self.zoom = max(0.05, min(16.0, z))
        self.canvas.set_size_request(int(self.img.width * self.zoom), int(self.img.height * self.zoom))
        self.canvas.queue_draw()
        self._update_status()

    def _fit(self):
        alloc = self.scroller.get_allocation()
        if alloc.width < 50:
            return False
        self.set_zoom(min(1.0, (alloc.width - 4) / self.img.width, (alloc.height - 4) / self.img.height))
        return False

    def _draw(self, _w, cr):
        cr.set_source_rgb(0.18, 0.18, 0.2)
        cr.paint()
        cr.scale(self.zoom, self.zoom)
        cr.set_source_surface(self.surface, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST if self.zoom >= 2 else cairo.FILTER_BILINEAR)
        cr.paint()
        if self.drag and self.drag[0] == "draw":
            _, p0, p1 = self.drag
            if self.tool in ("blur", "pixelate", "spotlight", "crop"):
                cr.set_source_rgba(0.2, 0.6, 1, 0.25)
                cr.rectangle(min(p0[0], p1[0]), min(p0[1], p1[1]), abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))
                cr.fill_preserve()
                cr.set_source_rgba(0.2, 0.6, 1, 1)
                cr.set_line_width(1 / self.zoom)
                cr.set_dash([6 / self.zoom, 4 / self.zoom])
                cr.stroke()
            else:
                draw_shape(cr, self.tool, p0, p1, self.pts, self._color(), self.width_spin.get_value(),
                           self.fill_chk.get_active())

    def _update_status(self):
        self.status.set_text(f"{self.img.width} × {self.img.height}px   zoom {self.zoom * 100:.0f}%   "
                             f"cursor {int(self.cursor[0])}, {int(self.cursor[1])}   "
                             f"undo {len(self.undo_stack)}")

    # ------------------------------------------------------------ actions
    def save_as(self):
        dlg = Gtk.FileChooserDialog(title="Save image", parent=self, action=Gtk.FileChooserAction.SAVE)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        dlg.set_do_overwrite_confirmation(True)
        dlg.set_current_name("image.png")
        for name, pat in (("PNG", "*.png"), ("JPEG", "*.jpg"), ("WebP", "*.webp"), ("BMP", "*.bmp")):
            f = Gtk.FileFilter()
            f.set_name(name)
            f.add_pattern(pat)
            dlg.add_filter(f)
        if dlg.run() == Gtk.ResponseType.OK:
            p = dlg.get_filename()
            ext = os.path.splitext(p)[1].lower()
            im = self.img.convert("RGB") if ext in (".jpg", ".jpeg", ".bmp") else self.img
            im.save(p)
        dlg.destroy()

    def copy(self):
        gfx.copy_image(self.img)

    def upload(self):
        if self.app:
            self.app.upload_image(self.img)

    def done(self):
        self.finished = True
        cb, self.on_done = self.on_done, None
        self.destroy()
        if cb:
            cb(self.img)

    def _on_close(self, *_):
        if not self.finished and self.on_done:
            cb, self.on_done = self.on_done, None
            self.finished = True
            GLib.idle_add(cb, None)
        return False
