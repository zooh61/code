"""Windows for the MintShare tools (colour picker, QR, hash, network, video, image tools, pin, drop zone…)."""
import os
import webbrowser

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk
from PIL import Image

from .. import effects, gfx
from ..tools import core
from . import common as C


# ---------------------------------------------------------------- text results
def show_text(title, text, app=None, w=560, h=320):
    sw, tv = C.monospace_view(text, w, h)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_border_width(10)
    box.pack_start(sw, True, True, 0)
    row = Gtk.Box(spacing=8)
    b = Gtk.Button(label="Copy")
    b.connect("clicked", lambda *_: gfx.copy_text(text))
    row.pack_start(b, False, False, 0)
    box.pack_start(row, False, False, 0)
    return C.window(title, box, w + 20, h + 60)


# ---------------------------------------------------------------- colour picker
class ColorPickerWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Color picker")
        self.app = app
        self.set_default_size(460, 0)
        self.set_icon_name("applets-screenshooter")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        self.add(box)
        self.swatch = Gtk.DrawingArea()
        self.swatch.set_size_request(-1, 70)
        self.rgb = (51, 153, 255)
        self.swatch.connect("draw", self._draw)
        box.pack_start(self.swatch, False, False, 0)
        row = Gtk.Box(spacing=8)
        b1 = Gtk.Button(label="🖱 Pick from screen")
        b1.connect("clicked", lambda *_: app.pick_color(self.set_rgb))
        b2 = Gtk.Button(label="Choose color…")
        b2.connect("clicked", self._dialog)
        self.entry = Gtk.Entry(placeholder_text="#RRGGBB or rgb(r,g,b)")
        self.entry.connect("activate", self._entered)
        row.pack_start(b1, False, False, 0)
        row.pack_start(b2, False, False, 0)
        row.pack_start(self.entry, True, True, 0)
        box.pack_start(row, False, False, 0)
        self.fmt_grid = Gtk.Grid(row_spacing=4, column_spacing=8)
        box.pack_start(self.fmt_grid, False, False, 0)
        box.pack_start(Gtk.Label(label="Recent colors", xalign=0), False, False, 4)
        self.recent = Gtk.FlowBox(max_children_per_line=14, selection_mode=Gtk.SelectionMode.NONE)
        box.pack_start(self.recent, False, False, 0)
        self.set_rgb(self.rgb, record=False)
        self.show_all()

    def _draw(self, w, cr):
        cr.set_source_rgb(*[c / 255 for c in self.rgb])
        cr.paint()

    def _dialog(self, *_):
        d = Gtk.ColorChooserDialog(title="Choose color", transient_for=self)
        d.set_rgba(Gdk.RGBA(*[c / 255 for c in self.rgb], 1))
        if d.run() == Gtk.ResponseType.OK:
            c = d.get_rgba()
            self.set_rgb((round(c.red * 255), round(c.green * 255), round(c.blue * 255)))
        d.destroy()

    def _entered(self, e):
        try:
            self.set_rgb(core.parse_color(e.get_text()))
        except ValueError:
            e.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, "dialog-error")

    def set_rgb(self, rgb, record=True):
        self.rgb = tuple(rgb)[:3]
        self.swatch.queue_draw()
        for c in self.fmt_grid.get_children():
            self.fmt_grid.remove(c)
        for i, (k, v) in enumerate(core.color_formats(*self.rgb).items()):
            self.fmt_grid.attach(Gtk.Label(label=k, xalign=0), 0, i, 1, 1)
            e = Gtk.Entry(text=v, editable=False, hexpand=True)
            self.fmt_grid.attach(e, 1, i, 1, 1)
            b = Gtk.Button.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.BUTTON)
            b.connect("clicked", lambda _b, val=v: gfx.copy_text(val))
            self.fmt_grid.attach(b, 2, i, 1, 1)
        self.fmt_grid.show_all()
        if record:
            gfx.copy_text(core.color_formats(*self.rgb)["HEX"])
            hexv = core.color_formats(*self.rgb)["HEX"]
            btn = Gtk.Button()
            btn.set_size_request(24, 24)
            css = Gtk.CssProvider()
            css.load_from_data(f"button {{ background: {hexv}; min-width:22px; min-height:22px; padding:0 }}".encode())
            btn.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            btn.set_tooltip_text(hexv)
            btn.connect("clicked", lambda *_: self.set_rgb(core.parse_color(hexv), record=False))
            self.recent.insert(btn, 0)
            btn.show()
        self.present()


# ---------------------------------------------------------------- QR code
class QRWindow(Gtk.Window):
    def __init__(self, app, text=""):
        super().__init__(title="QR code")
        self.app, self.qr = app, None
        self.set_icon_name("applets-screenshooter")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        self.add(box)
        self.entry = Gtk.TextView()
        self.entry.set_wrap_mode(Gtk.WrapMode.WORD)
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(420, 80)
        sw.add(self.entry)
        box.pack_start(Gtk.Label(label="Text or URL to encode", xalign=0), False, False, 0)
        box.pack_start(sw, False, False, 0)
        self.entry.get_buffer().connect("changed", self._regen)
        self.holder = Gtk.Box()
        self.holder.set_size_request(360, 360)
        box.pack_start(self.holder, True, True, 0)
        row = Gtk.Box(spacing=6)
        for label, cb in (("Copy image", self._copy), ("Save…", self._save), ("Scan region", lambda: app.run_action("qr_scan")),
                          ("Scan file…", self._scan_file), ("Scan clipboard", self._scan_clip)):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, c=cb: c())
            row.pack_start(b, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.entry.get_buffer().set_text(text)
        self.show_all()

    def _text(self):
        b = self.entry.get_buffer()
        return b.get_text(b.get_start_iter(), b.get_end_iter(), False)

    def _regen(self, *_):
        for c in self.holder.get_children():
            self.holder.remove(c)
        t = self._text()
        if t:
            try:
                self.qr = core.qr_make(t)
                self.holder.pack_start(C.pixbuf_image(self.qr, 340, 340), True, True, 0)
            except Exception as e:
                self.holder.pack_start(Gtk.Label(label=f"Cannot encode: {e}"), True, True, 0)
        self.holder.show_all()

    def _copy(self):
        if self.qr:
            gfx.copy_image(self.qr)

    def _save(self):
        p = C.choose_files(self, "Save QR code", save=True, name="qrcode.png")
        if p and self.qr:
            self.qr.save(p)

    def _scan(self, img):
        try:
            res = core.qr_decode(img)
        except RuntimeError as e:
            return C.error(self, "QR scan unavailable", str(e))
        if res:
            self.entry.get_buffer().set_text("\n".join(res))
            gfx.copy_text("\n".join(res))
        else:
            C.message(self, "No QR code found")

    def _scan_file(self):
        p = C.choose_files(self, "Choose image", filters=C.IMAGE_FILTER)
        if p:
            self._scan(Image.open(p))

    def _scan_clip(self):
        img = gfx.paste_image()
        if img:
            self._scan(img)


# ---------------------------------------------------------------- hash check
class HashWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Hash check")
        self.set_icon_name("applets-screenshooter")
        self.path = None
        self.algo = Gtk.ComboBoxText()
        for a in core.ALGOS:
            self.algo.append_text(a)
        self.algo.set_active(2)
        self.file_btn = Gtk.Button(label="Choose file…")
        self.file_btn.connect("clicked", self._choose)
        self.text_entry = Gtk.Entry(placeholder_text="…or type text to hash")
        self.result = Gtk.Entry(editable=False)
        self.compare = Gtk.Entry(placeholder_text="Paste expected hash to compare")
        self.compare.connect("changed", self._cmp)
        self.status = Gtk.Label(xalign=0)
        self.bar = Gtk.ProgressBar()
        go = Gtk.Button(label="Calculate")
        go.connect("clicked", self._go)
        self.add(C.grid([("File", self.file_btn), ("Text", self.text_entry), ("Algorithm", self.algo), (None, go),
                         (None, self.bar), ("Result", self.result), ("Compare", self.compare), (None, self.status)]))
        self.set_default_size(560, 0)
        self.show_all()

    def _choose(self, *_):
        p = C.choose_files(self, "Choose file")
        if p:
            self.path = p
            self.file_btn.set_label(os.path.basename(p))

    def _go(self, *_):
        algo = self.algo.get_active_text()
        if self.path and not self.text_entry.get_text():
            def prog(f):
                GLib.idle_add(self.bar.set_fraction, f)
            C.background(core.hash_file, self._done, self.path, algo, prog)
        else:
            self._done(core.hash_text(self.text_entry.get_text(), algo), None)

    def _done(self, r, e):
        if e:
            return C.error(self, "Hash failed", str(e))
        self.bar.set_fraction(1)
        self.result.set_text(r)
        self._cmp()

    def _cmp(self, *_):
        a, b = self.result.get_text().strip().lower(), self.compare.get_text().strip().lower()
        if a and b:
            self.status.set_markup('<span foreground="#2ecc71">✔ Hashes match</span>' if a == b else
                                   '<span foreground="#e74c3c">✘ Hashes differ</span>')
        else:
            self.status.set_text("")


# ---------------------------------------------------------------- ping / DNS
class NetWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Ping & DNS lookup")
        self.set_icon_name("applets-screenshooter")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        self.add(box)
        row = Gtk.Box(spacing=6)
        self.host = Gtk.Entry(text="example.com", hexpand=True)
        row.pack_start(self.host, True, True, 0)
        for label, fn in (("Ping", core.ping), ("DNS lookup", core.dns_lookup)):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, f=fn: self._run(f))
            row.pack_start(b, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.sw, self.tv = C.monospace_view("", 520, 260)
        box.pack_start(self.sw, True, True, 0)
        self.show_all()

    def _run(self, fn):
        self.tv.get_buffer().set_text("Working…")
        C.background(fn, lambda r, e: self.tv.get_buffer().set_text(r if not e else f"Error: {e}"), self.host.get_text().strip())


# ---------------------------------------------------------------- metadata
class MetaWindow(Gtk.Window):
    def __init__(self, app, path=None):
        super().__init__(title="Image metadata")
        self.set_icon_name("applets-screenshooter")
        self.path = path
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        self.add(box)
        row = Gtk.Box(spacing=6)
        b = Gtk.Button(label="Open image…")
        b.connect("clicked", lambda *_: self.load(C.choose_files(self, "Image", filters=C.IMAGE_FILTER)))
        s = Gtk.Button(label="Save copy without metadata…")
        s.connect("clicked", self._strip)
        row.pack_start(b, False, False, 0)
        row.pack_start(s, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.store = Gtk.ListStore(str, str)
        tv = Gtk.TreeView(model=self.store)
        for i, t in enumerate(("Property", "Value")):
            tv.append_column(Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i))
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(560, 340)
        sw.add(tv)
        box.pack_start(sw, True, True, 0)
        self.show_all()
        if path:
            self.load(path)

    def load(self, p):
        if not p:
            return
        self.path = p
        self.store.clear()
        try:
            for k, v in core.image_metadata(p).items():
                self.store.append((k, v))
        except Exception as e:
            C.error(self, "Cannot read image", str(e))

    def _strip(self, *_):
        if not self.path:
            return
        out = C.choose_files(self, "Save clean copy", save=True, name="clean_" + os.path.basename(self.path))
        if out:
            core.strip_metadata(self.path, out)


# ---------------------------------------------------------------- directory indexer
class IndexerWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Directory indexer")
        self.app = app
        self.set_icon_name("applets-screenshooter")
        self.folder = Gtk.Button(label="Choose folder…")
        self.folder.connect("clicked", self._pick)
        self.path = None
        self.fmt = Gtk.ComboBoxText()
        for f in ("html", "txt", "md"):
            self.fmt.append_text(f)
        self.fmt.set_active(0)
        self.rec = Gtk.CheckButton(label="Include sub-folders", active=True)
        self.hidden = Gtk.CheckButton(label="Include hidden files")
        go = Gtk.Button(label="Create index and save…")
        go.connect("clicked", self._go)
        up = Gtk.Button(label="Create index and upload")
        up.connect("clicked", self._upload)
        self.add(C.grid([("Folder", self.folder), ("Format", self.fmt), (None, self.rec), (None, self.hidden), (None, go), (None, up)]))
        self.set_default_size(420, 0)
        self.show_all()

    def _pick(self, *_):
        p = C.choose_files(self, "Folder", folder=True)
        if p:
            self.path = p
            self.folder.set_label(p)

    def _make(self):
        return core.index_directory(self.path, self.fmt.get_active_text(), self.rec.get_active(), self.hidden.get_active())

    def _go(self, *_):
        if not self.path:
            return
        ext = self.fmt.get_active_text()
        p = C.choose_files(self, "Save index", save=True, name=f"index.{ext}")
        if p:
            open(p, "w", encoding="utf-8").write(self._make())

    def _upload(self, *_):
        if self.path:
            self.app.upload_text(self._make(), filename=f"index.{self.fmt.get_active_text()}")


# ---------------------------------------------------------------- video tools
class VideoConvertWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Video converter")
        self.set_icon_name("applets-screenshooter")
        self.src = None
        self.file = Gtk.Button(label="Choose video…")
        self.file.connect("clicked", self._pick)
        self.fmt = Gtk.ComboBoxText()
        for f in core.FORMATS:
            self.fmt.append_text(f)
        self.fmt.set_active(0)
        self.crf = Gtk.SpinButton.new_with_range(10, 40, 1)
        self.crf.set_value(23)
        self.width = Gtk.SpinButton.new_with_range(0, 7680, 10)
        self.status = Gtk.Label(xalign=0)
        self.spin = Gtk.Spinner()
        go = Gtk.Button(label="Convert")
        go.connect("clicked", self._go)
        self.add(C.grid([("Input", self.file), ("Output format", self.fmt), ("Quality (CRF, lower=better)", self.crf),
                         ("Scale to width (0 = keep)", self.width), (None, go), (None, self.spin), (None, self.status)]))
        self.set_default_size(440, 0)
        self.show_all()

    def _pick(self, *_):
        p = C.choose_files(self, "Video", filters=C.VIDEO_FILTER)
        if p:
            self.src = p
            self.file.set_label(os.path.basename(p))

    def _go(self, *_):
        if not self.src:
            return
        self.spin.start()
        self.status.set_text("Converting…")
        C.background(core.convert_video, self._done, self.src, self.fmt.get_active_text(), None, int(self.crf.get_value()),
                     int(self.width.get_value()) or None)

    def _done(self, out, err):
        self.spin.stop()
        self.status.set_text(f"Error: {err}" if err else f"Saved: {out}")


class VideoThumbWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Video thumbnailer")
        self.app = app
        self.set_icon_name("applets-screenshooter")
        self.src = None
        self.sheet = None
        self.file = Gtk.Button(label="Choose video…")
        self.file.connect("clicked", self._pick)
        self.count = Gtk.SpinButton.new_with_range(1, 64, 1)
        self.count.set_value(9)
        self.cols = Gtk.SpinButton.new_with_range(1, 10, 1)
        self.cols.set_value(3)
        self.status = Gtk.Label(xalign=0)
        go = Gtk.Button(label="Create contact sheet")
        go.connect("clicked", self._go)
        save = Gtk.Button(label="Save…")
        save.connect("clicked", self._save)
        self.add(C.grid([("Input", self.file), ("Frames", self.count), ("Columns", self.cols), (None, go), (None, save), (None, self.status)]))
        self.set_default_size(400, 0)
        self.show_all()

    def _pick(self, *_):
        p = C.choose_files(self, "Video", filters=C.VIDEO_FILTER)
        if p:
            self.src = p
            self.file.set_label(os.path.basename(p))

    def _go(self, *_):
        if self.src:
            self.status.set_text("Working…")
            C.background(core.video_thumbnails, self._done, self.src, int(self.count.get_value()), int(self.cols.get_value()))

    def _done(self, img, err):
        if err:
            self.status.set_text(f"Error: {err}")
        else:
            self.sheet = img
            self.status.set_text(f"Sheet {img.width}×{img.height}")
            self.app.open_editor(img.convert("RGBA"))

    def _save(self, *_):
        if self.sheet:
            p = C.choose_files(self, "Save", save=True, name="thumbnails.png")
            if p:
                self.sheet.save(p)


# ---------------------------------------------------------------- image tools
class _ImageToolBase(Gtk.Window):
    def __init__(self, app, title):
        super().__init__(title=title)
        self.app = app
        self.set_icon_name("applets-screenshooter")
        self.result = None

    def send(self, img):
        """Open ``img`` in the editor / offer actions."""
        self.app.open_editor(img)


class EffectsWindow(_ImageToolBase):
    EFFECTS = ["Grayscale", "Invert", "Sepia", "Brightness", "Contrast", "Saturation", "Blur", "Sharpen", "Pixelate",
               "Border", "Drop shadow", "Rounded corners", "Resize %", "Rotate 90°", "Flip horizontal", "Flip vertical",
               "Trim whitespace", "Watermark text"]

    def __init__(self, app, img=None):
        super().__init__(app, "Image effects")
        self.orig = img
        self.cur = img
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(10)
        self.add(box)
        top = Gtk.Box(spacing=6)
        for label, cb in (("Open…", self._open), ("From clipboard", self._clip), ("Reset", self._reset)):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, c=cb: c())
            top.pack_start(b, False, False, 0)
        box.pack_start(top, False, False, 0)
        row = Gtk.Box(spacing=6)
        self.combo = Gtk.ComboBoxText()
        for e in self.EFFECTS:
            self.combo.append_text(e)
        self.combo.set_active(0)
        self.amount = Gtk.SpinButton.new_with_range(0.1, 500, 0.1)
        self.amount.set_value(10)
        self.text = Gtk.Entry(text="MintShare", width_chars=14)
        ap = Gtk.Button(label="Apply")
        ap.connect("clicked", lambda *_: self._apply())
        row.pack_start(self.combo, False, False, 0)
        row.pack_start(Gtk.Label(label="Amount"), False, False, 0)
        row.pack_start(self.amount, False, False, 0)
        row.pack_start(self.text, False, False, 0)
        row.pack_start(ap, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.holder = Gtk.Box()
        self.holder.set_size_request(560, 360)
        box.pack_start(self.holder, True, True, 0)
        bottom = Gtk.Box(spacing=6)
        for label, cb in (("Edit / annotate", lambda: self.cur and self.send(self.cur)), ("Copy", lambda: self.cur and gfx.copy_image(self.cur)),
                          ("Save…", self._save), ("Upload", lambda: self.cur and app.upload_image(self.cur))):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, c=cb: c())
            bottom.pack_start(b, False, False, 0)
        box.pack_start(bottom, False, False, 0)
        self._show()
        self.show_all()

    def _show(self):
        for c in self.holder.get_children():
            self.holder.remove(c)
        if self.cur:
            self.holder.pack_start(C.pixbuf_image(self.cur, 700, 420), True, True, 0)
        else:
            self.holder.pack_start(Gtk.Label(label="Open an image or paste from the clipboard"), True, True, 0)
        self.holder.show_all()

    def _open(self):
        p = C.choose_files(self, "Image", filters=C.IMAGE_FILTER)
        if p:
            self.orig = self.cur = Image.open(p).convert("RGBA")
            self._show()

    def _clip(self):
        img = gfx.paste_image()
        if img:
            self.orig = self.cur = img
            self._show()

    def _reset(self):
        self.cur = self.orig
        self._show()

    def _save(self):
        if self.cur:
            p = C.choose_files(self, "Save", save=True, name="image.png")
            if p:
                (self.cur.convert("RGB") if p.lower().endswith((".jpg", ".jpeg")) else self.cur).save(p)

    def _apply(self):
        if not self.cur:
            return
        e, a, im = self.combo.get_active_text(), self.amount.get_value(), self.cur
        table = {
            "Grayscale": lambda: effects.grayscale(im), "Invert": lambda: effects.invert(im), "Sepia": lambda: effects.sepia(im),
            "Brightness": lambda: effects.brightness(im, a / 10), "Contrast": lambda: effects.contrast(im, a / 10),
            "Saturation": lambda: effects.saturation(im, a / 10), "Blur": lambda: effects.blur(im, a),
            "Sharpen": lambda: effects.sharpen(im), "Pixelate": lambda: effects.pixelate(im, a),
            "Border": lambda: effects.add_border(im, int(a), "#000000"), "Drop shadow": lambda: effects.drop_shadow(im, int(a), int(a)),
            "Rounded corners": lambda: effects.rounded_corners(im, int(a)), "Resize %": lambda: effects.resize_percent(im, a),
            "Rotate 90°": lambda: effects.rotate(im, 90), "Flip horizontal": lambda: effects.flip(im, True),
            "Flip vertical": lambda: effects.flip(im, False), "Trim whitespace": lambda: effects.trim_whitespace(im),
            "Watermark text": lambda: effects.watermark_text(im, self.text.get_text(), 0.6),
        }
        self.cur = table[e]()
        self._show()


class CombinerWindow(_ImageToolBase):
    def __init__(self, app):
        super().__init__(app, "Image combiner")
        self.files = []
        self.store = Gtk.ListStore(str)
        tv = Gtk.TreeView(model=self.store, headers_visible=False)
        tv.append_column(Gtk.TreeViewColumn("File", Gtk.CellRendererText(), text=0))
        self.tv = tv
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(420, 180)
        sw.add(tv)
        add = Gtk.Button(label="Add images…")
        add.connect("clicked", self._add)
        up = Gtk.Button(label="▲")
        up.connect("clicked", lambda *_: self._move(-1))
        down = Gtk.Button(label="▼")
        down.connect("clicked", lambda *_: self._move(1))
        rm = Gtk.Button(label="Remove")
        rm.connect("clicked", self._rm)
        bar = Gtk.Box(spacing=6)
        for b in (add, up, down, rm):
            bar.pack_start(b, False, False, 0)
        self.vert = Gtk.ComboBoxText()
        for o in ("Vertical", "Horizontal"):
            self.vert.append_text(o)
        self.vert.set_active(0)
        self.align = Gtk.ComboBoxText()
        for o in ("start", "center", "end"):
            self.align.append_text(o)
        self.align.set_active(1)
        self.spacing = Gtk.SpinButton.new_with_range(0, 200, 1)
        go = Gtk.Button(label="Combine and open in editor")
        go.connect("clicked", self._go)
        self.add(C.grid([(None, bar), (None, sw), ("Direction", self.vert), ("Alignment", self.align), ("Spacing px", self.spacing), (None, go)]))
        self.show_all()

    def _add(self, *_):
        for p in C.choose_files(self, "Images", multiple=True, filters=C.IMAGE_FILTER) or []:
            self.files.append(p)
            self.store.append((os.path.basename(p),))

    def _sel(self):
        m, it = self.tv.get_selection().get_selected()
        return m.get_path(it).get_indices()[0] if it else None

    def _move(self, d):
        i = self._sel()
        if i is None or not 0 <= i + d < len(self.files):
            return
        self.files[i], self.files[i + d] = self.files[i + d], self.files[i]
        self.store.clear()
        for f in self.files:
            self.store.append((os.path.basename(f),))
        self.tv.get_selection().select_path(Gtk.TreePath(i + d))

    def _rm(self, *_):
        i = self._sel()
        if i is not None:
            del self.files[i]
            self.store.remove(self.store.get_iter(Gtk.TreePath(i)))

    def _go(self, *_):
        if self.files:
            img = effects.combine([Image.open(f) for f in self.files], self.vert.get_active_text() == "Vertical",
                                  int(self.spacing.get_value()), self.align.get_active_text())
            self.send(img)


class SplitterWindow(_ImageToolBase):
    def __init__(self, app):
        super().__init__(app, "Image splitter")
        self.path = None
        self.file = Gtk.Button(label="Choose image…")
        self.file.connect("clicked", self._pick)
        self.rows = Gtk.SpinButton.new_with_range(1, 50, 1)
        self.cols = Gtk.SpinButton.new_with_range(1, 50, 1)
        self.cols.set_value(2)
        self.status = Gtk.Label(xalign=0)
        go = Gtk.Button(label="Split into folder…")
        go.connect("clicked", self._go)
        self.add(C.grid([("Image", self.file), ("Rows", self.rows), ("Columns", self.cols), (None, go), (None, self.status)]))
        self.show_all()

    def _pick(self, *_):
        p = C.choose_files(self, "Image", filters=C.IMAGE_FILTER)
        if p:
            self.path = p
            self.file.set_label(os.path.basename(p))

    def _go(self, *_):
        if not self.path:
            return
        out = C.choose_files(self, "Output folder", folder=True)
        if out:
            parts = effects.split(Image.open(self.path), int(self.rows.get_value()), int(self.cols.get_value()))
            base = os.path.splitext(os.path.basename(self.path))[0]
            for i, p in enumerate(parts, 1):
                p.save(os.path.join(out, f"{base}_{i:02d}.png"))
            self.status.set_text(f"Saved {len(parts)} images to {out}")


class ThumbnailerWindow(_ImageToolBase):
    def __init__(self, app):
        super().__init__(app, "Image thumbnailer")
        self.files = []
        self.btn = Gtk.Button(label="Choose images…")
        self.btn.connect("clicked", self._pick)
        self.width = Gtk.SpinButton.new_with_range(16, 4096, 1)
        self.width.set_value(256)
        self.status = Gtk.Label(xalign=0)
        go = Gtk.Button(label="Create thumbnails…")
        go.connect("clicked", self._go)
        self.add(C.grid([("Images", self.btn), ("Width px", self.width), (None, go), (None, self.status)]))
        self.show_all()

    def _pick(self, *_):
        self.files = C.choose_files(self, "Images", multiple=True, filters=C.IMAGE_FILTER) or []
        self.btn.set_label(f"{len(self.files)} selected")

    def _go(self, *_):
        out = self.files and C.choose_files(self, "Output folder", folder=True)
        if out:
            for f in self.files:
                t = effects.thumbnail(Image.open(f), int(self.width.get_value()))
                t.save(os.path.join(out, os.path.splitext(os.path.basename(f))[0] + "_thumb.png"))
            self.status.set_text(f"Created {len(self.files)} thumbnails")


# ---------------------------------------------------------------- pin to screen
class PinWindow(Gtk.Window):
    """Borderless always-on-top image. Drag to move, wheel to zoom, Ctrl+wheel for opacity, double-click/Esc to close."""
    def __init__(self, img, x=None, y=None):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.img = img.convert("RGBA")
        self.scale = 1.0
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_app_paintable(True)
        self.set_visual(self.get_screen().get_rgba_visual())
        self.surface = gfx.pil_to_surface(self.img)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._press)
        self.connect("scroll-event", self._scroll)
        self.connect("key-press-event", lambda _w, e: self.destroy() if e.keyval == Gdk.KEY_Escape else None)
        self._resize()
        if x is not None:
            self.move(x, y)
        else:
            self.set_position(Gtk.WindowPosition.CENTER)
        self.show_all()

    def _resize(self):
        w, h = int(self.img.width * self.scale), int(self.img.height * self.scale)
        self.resize(max(16, w), max(16, h))
        self.set_size_request(max(16, w), max(16, h))
        self.queue_draw()

    def _draw(self, _w, cr):
        cr.scale(self.scale, self.scale)
        cr.set_source_surface(self.surface, 0, 0)
        cr.paint_with_alpha(self.get_opacity())
        cr.identity_matrix()
        cr.set_source_rgba(0.2, 0.6, 1, 0.9)
        cr.set_line_width(2)
        a = self.get_allocation()
        cr.rectangle(1, 1, a.width - 2, a.height - 2)
        cr.stroke()

    def _press(self, _w, ev):
        if ev.button == 1:
            if ev.type == Gdk.EventType._2BUTTON_PRESS:
                self.destroy()
            else:
                self.begin_move_drag(1, int(ev.x_root), int(ev.y_root), ev.time)
        elif ev.button == 3:
            m = Gtk.Menu()
            for label, cb in (("Copy", lambda: gfx.copy_image(self.img)), ("Reset zoom", lambda: self._set(1.0)),
                              ("Close", self.destroy)):
                it = Gtk.MenuItem(label=label)
                it.connect("activate", lambda _i, c=cb: c())
                m.append(it)
            m.show_all()
            m.popup_at_pointer(ev)

    def _set(self, s):
        self.scale = s
        self._resize()

    def _scroll(self, _w, ev):
        up = ev.direction == Gdk.ScrollDirection.UP
        if ev.state & Gdk.ModifierType.CONTROL_MASK:
            self.set_opacity(max(0.1, min(1.0, self.get_opacity() + (0.1 if up else -0.1))))
        else:
            self._set(max(0.1, min(8.0, self.scale * (1.1 if up else 1 / 1.1))))


# ---------------------------------------------------------------- drop zone & monitor test
class DropWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Drop files to upload")
        self.app = app
        self.set_keep_above(True)
        self.set_default_size(220, 160)
        self.set_icon_name("applets-screenshooter")
        lbl = Gtk.Label(label="⬆\nDrop files, text\nor links here")
        lbl.set_justify(Gtk.Justification.CENTER)
        self.add(lbl)
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_uri_targets()
        self.drag_dest_add_text_targets()
        self.connect("drag-data-received", self._drop)
        self.show_all()

    def _drop(self, _w, ctx, x, y, data, info, time):
        uris = data.get_uris()
        if uris:
            files = [GLib.filename_from_uri(u)[0] for u in uris if u.startswith("file://")]
            if files:
                self.app.upload_files(files)
        elif data.get_text():
            t = data.get_text()
            (self.app.shorten_text(t) if t.startswith(("http://", "https://")) and "\n" not in t.strip()
             else self.app.upload_text(t))
        ctx.finish(True, False, time)


class MonitorTest(Gtk.Window):
    COLORS = ["#000000", "#ffffff", "#ff0000", "#00ff00", "#0000ff", "#808080"]

    def __init__(self, app):
        super().__init__()
        self.i = 0
        self.fullscreen()
        self.set_app_paintable(True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.KEY_PRESS_MASK)
        self.connect("draw", self._draw)
        self.connect("button-press-event", self._next)
        self.connect("key-press-event", self._key)
        self.show_all()

    def _draw(self, w, cr):
        cr.set_source_rgba(*gfx.parse_color(self.COLORS[self.i]))
        cr.paint()
        cr.set_source_rgb(0.5, 0.5, 0.5)
        cr.move_to(20, 30)
        cr.show_text("Click: next color • Esc: exit (dead-pixel test)")

    def _next(self, *_):
        self.i = (self.i + 1) % len(self.COLORS)
        self.queue_draw()

    def _key(self, w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.destroy()
        else:
            self._next()
