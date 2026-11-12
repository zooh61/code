"""Settings window, generated from field descriptions, plus destination and hotkey editors."""
import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from .. import actions, hotkeys, paths, uploaders
from ..tools import core
from . import common as C

# (path, label, kind, extra)
GENERAL = [
    ("general.notifications", "Show desktop notifications", "bool", None),
    ("general.play_sound", "Play shutter sound", "bool", None),
    ("general.tray_icon", "Show tray icon", "bool", None),
    ("general.start_minimized", "Start hidden in tray", "bool", None),
    ("general.autostart", "Start MintShare when I log in", "bool", None),
    ("general.take_over_print_screen", "Free up the Print Screen key from the desktop's own screenshot tool", "bool", None),
    ("general.language_ocr", "OCR language (Tesseract code, e.g. eng, nld, eng+nld)", "text", None),
    ("history.enabled", "Keep history", "bool", None),
    ("history.max_entries", "History size", "int", (50, 100000)),
]
CAPTURE = [
    ("capture.show_cursor", "Include mouse cursor in screenshots", "bool", None),
    ("capture.delay", "Delay before capture (seconds)", "float", (0, 60, 0.5)),
    ("capture.snap_to_windows", "Region capture: click a window to snap to it", "bool", None),
    ("capture.show_magnifier", "Region capture: magnifier with color under cursor", "bool", None),
    ("capture.show_crosshair", "Region capture: crosshair lines", "bool", None),
    ("capture.show_info", "Region capture: show size and position", "bool", None),
    ("capture.dim", "Region capture: dim background", "float", (0, 0.9, 0.05)),
    ("capture.scroll_delay", "Scrolling capture: wait between scrolls (s)", "float", (0.1, 3, 0.05)),
    ("capture.scroll_max_steps", "Scrolling capture: maximum scroll steps", "int", (2, 400)),
    ("capture.scroll_amount", "Scrolling capture: mouse-wheel clicks per step", "int", (1, 30)),
    ("capture.auto_interval", "Auto capture: interval (seconds)", "float", (0.5, 86400, 0.5)),
    ("capture.auto_count", "Auto capture: number of shots (0 = until stopped)", "int", (0, 100000)),
    ("capture.webpage_width", "Webpage capture: width", "int", (320, 7680)),
    ("capture.webpage_height", "Webpage capture: height", "int", (240, 20000)),
]
IMAGE = [
    ("image.format", "Image format", "choice", ["png", "jpg", "webp", "bmp", "gif", "tiff"]),
    ("image.jpg_quality", "JPEG quality", "int", (1, 100)),
    ("image.webp_quality", "WebP quality", "int", (1, 100)),
    ("image.auto_jpg_over_kb", "Use JPEG instead of PNG above N KB (0 = never)", "int", (0, 100000)),
    ("image.save_dir", "Screenshots folder (empty = ~/Pictures/MintShare)", "folder", None),
    ("image.subfolder", "Sub-folder pattern", "text", None),
    ("image.filename", "File name pattern", "text", None),
    ("image.text_filename", "Text upload name pattern", "text", None),
]
EFFECTS = [
    ("effects.resize_enabled", "Resize", "bool", None), ("effects.resize_percent", "Resize to (%)", "float", (1, 800, 1)),
    ("effects.grayscale", "Grayscale", "bool", None), ("effects.rounded", "Rounded corners radius (px)", "int", (0, 500)),
    ("effects.border", "Border size (px)", "int", (0, 200)), ("effects.border_color", "Border color", "color", None),
    ("effects.shadow", "Drop shadow", "bool", None), ("effects.shadow_offset", "Shadow offset", "int", (0, 100)),
    ("effects.shadow_blur", "Shadow blur", "int", (0, 100)),
    ("effects.watermark_enabled", "Watermark", "bool", None), ("effects.watermark_text", "Watermark text", "text", None),
    ("effects.watermark_image", "Watermark image (overrides text)", "file", None),
    ("effects.watermark_opacity", "Watermark opacity", "float", (0.05, 1, 0.05)),
    ("effects.watermark_position", "Watermark position", "choice",
     ["top-left", "top-center", "top-right", "middle-left", "center", "middle-right", "bottom-left", "bottom-center", "bottom-right"]),
]
RECORD = [
    ("recording.area", "Recording area", "choice", ["region", "fullscreen", "monitor", "window"]),
    ("recording.container", "Video container", "choice", ["mp4", "webm", "mkv"]),
    ("recording.codec", "Video codec (mp4/mkv)", "choice", ["libx264", "libx265"]),
    ("recording.fps", "Frames per second", "int", (5, 120)),
    ("recording.crf", "Quality (CRF, lower = better)", "int", (10, 45)),
    ("recording.draw_cursor", "Record mouse cursor", "bool", None),
    ("recording.audio", "Record audio (PulseAudio / PipeWire)", "bool", None),
    ("recording.audio_source", "Audio source (see: pactl list short sources)", "text", None),
    ("recording.gif_fps", "GIF frames per second", "int", (3, 50)),
    ("recording.gif_max_width", "GIF maximum width", "int", (100, 4000)),
    ("recording.dir", "Video folder (empty = ~/Videos/MintShare)", "folder", None),
    ("recording.filename", "Video name pattern", "text", None),
    ("recording.after_record.copy_path", "After recording: copy file path", "bool", None),
    ("recording.after_record.upload", "After recording: upload file", "bool", None),
    ("recording.after_record.open_folder", "After recording: open folder", "bool", None),
]


def build_field(cfg, path, label, kind, extra, on_change=None):
    val = cfg.get(path)
    if kind == "bool":
        w = Gtk.Switch(active=bool(val), halign=Gtk.Align.START, valign=Gtk.Align.CENTER)
        w.connect("notify::active", lambda s, _p: cfg.set(path, s.get_active(), save=False))
    elif kind in ("int", "float"):
        lo, hi, *step = extra
        w = Gtk.SpinButton.new_with_range(lo, hi, step[0] if step else 1)
        w.set_digits(0 if kind == "int" else 2)
        w.set_value(val or 0)
        w.connect("value-changed", lambda s: cfg.set(path, int(s.get_value()) if kind == "int" else s.get_value(), save=False))
    elif kind == "choice":
        w = Gtk.ComboBoxText()
        for c in extra:
            w.append_text(c)
        if val in extra:
            w.set_active(extra.index(val))
        w.connect("changed", lambda s: cfg.set(path, s.get_active_text(), save=False))
    elif kind == "color":
        w = Gtk.ColorButton.new_with_rgba(Gdk.RGBA() if not val else _rgba(val))
        w.connect("color-set", lambda s: cfg.set(path, _hex(s.get_rgba()), save=False))
    elif kind in ("folder", "file"):
        w = Gtk.Box(spacing=4)
        e = Gtk.Entry(text=val or "", hexpand=True)
        e.connect("changed", lambda s: cfg.set(path, s.get_text(), save=False))
        b = Gtk.Button(label="…")

        def pick(_b):
            p = C.choose_files(w.get_toplevel(), "Choose", folder=(kind == "folder"),
                               filters=C.IMAGE_FILTER if kind == "file" else None)
            if p:
                e.set_text(p)
        b.connect("clicked", pick)
        w.pack_start(e, True, True, 0)
        w.pack_start(b, False, False, 0)
    else:
        w = Gtk.Entry(text=str(val or ""))
        w.connect("changed", lambda s: cfg.set(path, s.get_text(), save=False))
    return w


def _rgba(h):
    c = Gdk.RGBA()
    c.parse(h)
    return c


def _hex(c):
    return "#%02x%02x%02x" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255))


def form_page(cfg, fields):
    rows = [(label, build_field(cfg, p, label, k, e)) for p, label, k, e in fields]
    g = C.grid(rows)
    sw = Gtk.ScrolledWindow()
    sw.add(g)
    return sw


class SettingsWindow(Gtk.Window):
    def __init__(self, app, page=0):
        super().__init__(title="MintShare – Settings")
        self.app, self.cfg = app, app.config
        self.set_default_size(760, 600)
        self.set_icon_name("applets-screenshooter")
        nb = Gtk.Notebook(tab_pos=Gtk.PositionType.LEFT)
        self.nb = nb
        nb.append_page(form_page(self.cfg, GENERAL), Gtk.Label(label="General"))
        nb.append_page(form_page(self.cfg, CAPTURE), Gtk.Label(label="Capture"))
        nb.append_page(self._after_page(), Gtk.Label(label="After capture"))
        nb.append_page(form_page(self.cfg, IMAGE), Gtk.Label(label="Image & files"))
        nb.append_page(form_page(self.cfg, EFFECTS), Gtk.Label(label="Effects"))
        nb.append_page(form_page(self.cfg, RECORD), Gtk.Label(label="Recording"))
        nb.append_page(DestinationsPage(self), Gtk.Label(label="Destinations"))
        nb.append_page(HotkeysPage(self), Gtk.Label(label="Hotkeys & workflows"))
        self.add(nb)
        self.connect("delete-event", self._close)
        self.show_all()
        nb.set_current_page(page)

    def _after_page(self):
        rows = [(None, Gtk.Label(label="<b>After capture</b>", use_markup=True, xalign=0))]
        rows += [(label, build_field(self.cfg, f"after_capture.{k}", label, "bool", None)) for k, label in actions.AFTER_CAPTURE]
        rows.append((None, Gtk.Label(label="<b>After upload</b>", use_markup=True, xalign=0)))
        rows += [(label, build_field(self.cfg, f"after_upload.{k}", label, "bool", None)) for k, label in actions.AFTER_UPLOAD]
        sw = Gtk.ScrolledWindow()
        sw.add(C.grid(rows))
        return sw

    def _close(self, *_):
        self.cfg.save()
        self.app.settings_changed()
        return False


class DestinationsPage(Gtk.ScrolledWindow):
    def __init__(self, win):
        super().__init__()
        self.win, self.cfg = win, win.cfg
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.box.set_border_width(12)
        self.add(self.box)
        self._build()

    def _build(self):
        for c in self.box.get_children():
            self.box.remove(c)
        ups = uploaders.all_uploaders(self.cfg.data)
        self.ups = ups
        grid = Gtk.Grid(row_spacing=8, column_spacing=12)
        self.box.pack_start(Gtk.Label(label="<b>Where should things go?</b>", use_markup=True, xalign=0), False, False, 0)
        self.box.pack_start(grid, False, False, 0)
        for i, (cat, label) in enumerate((("image", "Images"), ("text", "Text"), ("file", "Other files"), ("url_shortener", "URL shortener"))):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
            combo = Gtk.ComboBoxText(hexpand=True)
            ids = []
            for uid, name in uploaders.choices("shortener" if cat == "url_shortener" else cat, self.cfg.data):
                combo.append_text(name)
                ids.append(uid)
            cur = self.cfg.get(f"destinations.{cat}")
            if cur in ids:
                combo.set_active(ids.index(cur))
            combo.connect("changed", lambda c, cat=cat, ids=ids: self.cfg.set(f"destinations.{cat}", ids[c.get_active()], save=False))
            grid.attach(combo, 1, i, 1, 1)
        self.box.pack_start(Gtk.Separator(), False, False, 6)
        self.box.pack_start(Gtk.Label(label="<b>Configure a destination</b>", use_markup=True, xalign=0), False, False, 0)
        self.sel = Gtk.ComboBoxText()
        self.cfg_ids = [u.id for u in ups.values() if getattr(u, "fields", None)]
        for uid in self.cfg_ids:
            self.sel.append_text(ups[uid].name)
        self.sel.connect("changed", self._show_form)
        self.box.pack_start(self.sel, False, False, 0)
        self.form = Gtk.Box()
        self.box.pack_start(self.form, False, False, 0)
        self.sel.set_active(0)
        self.box.pack_start(Gtk.Separator(), False, False, 6)
        self.box.pack_start(Gtk.Label(label="<b>Custom uploaders (ShareX .sxcu files)</b>", use_markup=True, xalign=0), False, False, 0)
        names = ", ".join(u.name for u in ups.values() if u.id.startswith("custom:")) or "none yet"
        self.box.pack_start(Gtk.Label(label=f"Installed: {names}", xalign=0, wrap=True), False, False, 0)
        row = Gtk.Box(spacing=6)
        for label, cb in (("Import .sxcu…", self._import), ("Remove…", self._remove), ("Open folder", lambda: self.win.app.open_path(paths.CUSTOM_UPLOADERS_DIR))):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, c=cb: c())
            row.pack_start(b, False, False, 0)
        self.box.pack_start(row, False, False, 0)
        self.box.show_all()

    def _show_form(self, combo):
        for c in self.form.get_children():
            self.form.remove(c)
        i = combo.get_active()
        if i < 0:
            return
        u = self.ups[self.cfg_ids[i]]
        rows = []
        for f in u.fields:
            key, label, kind = f[:3]
            default = f[3] if len(f) > 3 else ""
            path = f"uploaders.{u.id}.{key}"
            if self.cfg.get(path) is None and default != "":
                self.cfg.set(path, default, save=False)
            k, extra = ("choice", kind.split(":")[1].split(",")) if kind.startswith("choice:") else \
                (("int", (0, 65535)) if kind == "int" else (kind, None))
            w = build_field(self.cfg, path, label, "text" if k == "password" else k, extra)
            if k == "password":
                w.set_visibility(False)
            rows.append((label, w))
        self.form.pack_start(C.grid(rows), True, True, 0)
        self.form.show_all()

    def _import(self):
        p = C.choose_files(self.win, "Import custom uploader", filters=[("ShareX custom uploader", ["*.sxcu", "*.json"])])
        if p:
            try:
                u = uploaders.import_sxcu(p)
                C.message(self.win, f"Imported “{u.name}”", f"It can be used for: {', '.join(u.categories)}.")
            except Exception as e:
                C.error(self.win, "Import failed", str(e))
            self._build()

    def _remove(self):
        customs = [u for u in self.ups.values() if u.id.startswith("custom:")]
        if not customs:
            return
        d = Gtk.Dialog(title="Remove custom uploader", transient_for=self.win, modal=True)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Remove", Gtk.ResponseType.OK)
        combo = Gtk.ComboBoxText()
        for u in customs:
            combo.append_text(u.name)
        combo.set_active(0)
        d.get_content_area().pack_start(combo, True, True, 12)
        d.show_all()
        if d.run() == Gtk.ResponseType.OK:
            try:
                os.remove(customs[combo.get_active()].path)
            except OSError:
                pass
        d.destroy()
        self._build()


class HotkeysPage(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.win, self.cfg = win, win.cfg
        self.set_border_width(12)
        self.pack_start(Gtk.Label(label="Each workflow is a hotkey that runs one job, optionally with its own after-capture "
                                        "settings (for example “Region + upload”).", wrap=True, xalign=0), False, False, 0)
        self.store = Gtk.ListStore(str, str, str, str)
        tv = Gtk.TreeView(model=self.store)
        for i, t in enumerate(("Name", "Job", "Hotkey", "Overrides")):
            col = Gtk.TreeViewColumn(t, Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            tv.append_column(col)
        tv.connect("row-activated", lambda *_: self._edit())
        self.tv = tv
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.add(tv)
        self.pack_start(sw, True, True, 0)
        row = Gtk.Box(spacing=6)
        for label, cb in (("Add", self._add), ("Edit…", self._edit), ("Remove", self._remove), ("Reset defaults", self._reset)):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, c=cb: c())
            row.pack_start(b, False, False, 0)
        ap = Gtk.Button(label="Apply hotkeys")
        ap.get_style_context().add_class("suggested-action")
        ap.connect("clicked", lambda *_: self._apply())
        row.pack_end(ap, False, False, 0)
        self.pack_start(row, False, False, 0)
        self.status = Gtk.Label(xalign=0, wrap=True)
        self.pack_start(self.status, False, False, 0)
        self._fill()

    def _wf(self):
        return self.cfg.get("workflows")

    def _fill(self):
        self.store.clear()
        for w in self._wf():
            ov = ", ".join(f"{k}.{kk}={'on' if vv else 'off'}" for k, v in (w.get("overrides") or {}).items() for kk, vv in v.items())
            self.store.append((w["name"], actions.ACTIONS.get(w["job"], (w["job"],))[0], hotkeys.accelerator_label(w.get("hotkey", "")), ov))

    def _index(self):
        m, it = self.tv.get_selection().get_selected()
        return m.get_path(it).get_indices()[0] if it else None

    def _add(self):
        w = {"name": "New workflow", "job": "region", "hotkey": "", "overrides": {}}
        if self._dialog(w):
            self._wf().append(w)
            self._fill()

    def _edit(self):
        i = self._index()
        if i is not None and self._dialog(self._wf()[i]):
            self._fill()

    def _remove(self):
        i = self._index()
        if i is not None:
            del self._wf()[i]
            self._fill()

    def _reset(self):
        from ..config import DEFAULT_WORKFLOWS
        import copy
        self.cfg.set("workflows", copy.deepcopy(DEFAULT_WORKFLOWS), save=False)
        self._fill()

    def _apply(self):
        self.cfg.save()
        self.status.set_text(self.win.app.apply_hotkeys())

    def _dialog(self, w):
        d = Gtk.Dialog(title="Workflow", transient_for=self.win, modal=True)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        name = Gtk.Entry(text=w["name"])
        job = Gtk.ComboBoxText()
        for j in actions.JOBS:
            job.append_text(actions.ACTIONS[j][0])
        job.set_active(actions.JOBS.index(w["job"]) if w["job"] in actions.JOBS else 0)
        hk = Gtk.Button(label=hotkeys.accelerator_label(w.get("hotkey")) or "Click, then press keys…")
        state = {"acc": w.get("hotkey", "")}

        def capture(_b):
            hk.set_label("Press the key combination… (Esc = none)")
            dlg_key = {}

            def on_key(_w, ev):
                if ev.keyval in (Gdk.KEY_Control_L, Gdk.KEY_Control_R, Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Super_L, Gdk.KEY_Super_R):
                    return True
                if ev.keyval == Gdk.KEY_Escape:
                    state["acc"] = ""
                else:
                    mods = ev.state & Gtk.accelerator_get_default_mod_mask()
                    state["acc"] = Gtk.accelerator_name(ev.keyval, mods)
                hk.set_label(hotkeys.accelerator_label(state["acc"]) or "none")
                d.disconnect(dlg_key["id"])
                return True
            dlg_key["id"] = d.connect("key-press-event", on_key)
        hk.connect("clicked", capture)
        ov = w.get("overrides", {})
        combos = {}
        rows = [("Name", name), ("Job", job), ("Hotkey", hk)]
        rows.append((None, Gtk.Label(label="<b>Override after-capture settings for this workflow</b>", use_markup=True, xalign=0)))
        for section, lst in (("after_capture", actions.AFTER_CAPTURE), ("after_upload", actions.AFTER_UPLOAD)):
            for k, label in lst:
                c = Gtk.ComboBoxText()
                for o in ("(default)", "on", "off"):
                    c.append_text(o)
                v = ov.get(section, {}).get(k)
                c.set_active(0 if v is None else 1 if v else 2)
                combos[(section, k)] = c
                rows.append((label, c))
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(520, 480)
        sw.add(C.grid(rows))
        d.get_content_area().pack_start(sw, True, True, 0)
        d.show_all()
        ok = d.run() == Gtk.ResponseType.OK
        if ok:
            w["name"] = name.get_text() or "Workflow"
            w["job"] = actions.JOBS[job.get_active()]
            w["hotkey"] = state["acc"]
            ovr = {}
            for (section, k), c in combos.items():
                i = c.get_active()
                if i > 0:
                    ovr.setdefault(section, {})[k] = (i == 1)
            w["overrides"] = ovr
        d.destroy()
        return ok
