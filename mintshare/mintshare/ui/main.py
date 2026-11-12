"""Main window: sidebar with Capture / Upload / Tools / After capture / History."""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from .. import __version__, actions, uploaders
from .history import HistoryView
from .settings import build_field


class MainWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="MintShare")
        self.app = app
        w, h = app.config.get("main_window.width", 900), app.config.get("main_window.height", 600)
        self.set_default_size(w, h)
        self.set_icon_name("applets-screenshooter")
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)
        body = Gtk.Box()
        outer.pack_start(body, True, True, 0)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        side = Gtk.StackSidebar(stack=self.stack)
        side.set_size_request(170, -1)
        body.pack_start(side, False, False, 0)
        body.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        body.pack_start(self.stack, True, True, 0)
        for cat in ("Capture", "Upload", "Tools"):
            self.stack.add_titled(self._action_page(cat), cat.lower(), cat)
        self.stack.add_titled(self._after_page(), "after", "After capture")
        self.stack.add_titled(self._dest_page(), "dest", "Destinations")
        self.history = HistoryView(app)
        self.stack.add_titled(self.history, "history", "History")
        self.stack.add_titled(self._about_page(), "about", "About")
        bar = Gtk.Box(spacing=8)
        bar.set_border_width(8)
        s = Gtk.Button(label="Settings")
        s.connect("clicked", lambda *_: app.run_action("open_settings"))
        f = Gtk.Button(label="Open screenshots folder")
        f.connect("clicked", lambda *_: app.run_action("open_folder"))
        self.status = Gtk.Label(label="Ready", xalign=1)
        bar.pack_start(s, False, False, 0)
        bar.pack_start(f, False, False, 0)
        bar.pack_end(self.status, True, True, 0)
        outer.pack_start(Gtk.Separator(), False, False, 0)
        outer.pack_start(bar, False, False, 0)
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_uri_targets()
        self.connect("drag-data-received", self._drop)
        self.connect("delete-event", self._close)
        self.stack.connect("notify::visible-child-name", lambda *_: self.history.reload()
                           if self.stack.get_visible_child_name() == "history" else None)
        self.show_all()

    def _action_page(self, cat):
        sw = Gtk.ScrolledWindow()
        fb = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True, min_children_per_line=2,
                         max_children_per_line=4, row_spacing=10, column_spacing=10)
        fb.set_border_width(16)
        for key, (label, c, icon) in actions.ACTIONS.items():
            if c != cat:
                continue
            b = Gtk.Button()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.set_border_width(10)
            box.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.DIALOG), False, False, 0)
            lab = Gtk.Label(label=label, wrap=True, justify=Gtk.Justification.CENTER)
            lab.set_max_width_chars(16)
            box.pack_start(lab, False, False, 0)
            b.add(box)
            b.set_size_request(150, 110)
            b.connect("clicked", lambda _b, k=key: self.app.run_action(k))
            fb.add(b)
        sw.add(fb)
        return sw

    def _after_page(self):
        rows = Gtk.Grid(row_spacing=8, column_spacing=16)
        rows.set_border_width(16)
        r = 0
        for title, items, sect in (("After capture", actions.AFTER_CAPTURE, "after_capture"),
                                   ("After upload", actions.AFTER_UPLOAD, "after_upload")):
            rows.attach(Gtk.Label(label=f"<b>{title}</b>", use_markup=True, xalign=0), 0, r, 2, 1)
            r += 1
            for k, label in items:
                rows.attach(Gtk.Label(label=label, xalign=0, hexpand=True), 0, r, 1, 1)
                w = build_field(self.app.config, f"{sect}.{k}", label, "bool", None)
                w.connect("notify::active", lambda *_: self.app.config.save())
                rows.attach(w, 1, r, 1, 1)
                r += 1
        sw = Gtk.ScrolledWindow()
        sw.add(rows)
        return sw

    def _dest_page(self):
        g = Gtk.Grid(row_spacing=10, column_spacing=14)
        g.set_border_width(16)
        for i, (cat, label, ucat) in enumerate((("image", "Image uploader", "image"), ("text", "Text uploader", "text"),
                                                ("file", "File uploader", "file"), ("url_shortener", "URL shortener", "shortener"))):
            g.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
            combo = Gtk.ComboBoxText(hexpand=True)
            ids = []
            for uid, name in uploaders.choices(ucat, self.app.config.data):
                combo.append_text(name)
                ids.append(uid)
            cur = self.app.config.get(f"destinations.{cat}")
            if cur in ids:
                combo.set_active(ids.index(cur))
            combo.connect("changed", lambda c, cat=cat, ids=ids: (self.app.config.set(f"destinations.{cat}", ids[c.get_active()])
                                                                 if c.get_active() >= 0 else None))
            g.attach(combo, 1, i, 1, 1)
        b = Gtk.Button(label="Configure accounts, FTP, custom uploaders…")
        b.connect("clicked", lambda *_: self.app.show_settings(6))
        g.attach(b, 0, 4, 2, 1)
        return g

    def _about_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(24)
        l = Gtk.Label(use_markup=True, xalign=0, wrap=True, selectable=True)
        l.set_markup(f"<big><b>MintShare {__version__}</b></big>\n\nA ShareX-style screenshot, screen-recording and upload tool for "
                     "Linux Mint (Cinnamon, MATE and Xfce on X11).\n\n"
                     "• Hotkeys are set under Settings → Hotkeys &amp; workflows.\n"
                     "• Command line: <tt>mintshare region</tt>, <tt>mintshare --workflow \"Region + upload\"</tt>, "
                     "<tt>mintshare --upload file.png</tt>, <tt>mintshare --list-actions</tt>.\n"
                     "• Custom uploaders: import ShareX <tt>.sxcu</tt> files under Settings → Destinations.")
        box.pack_start(l, False, False, 0)
        return box

    def set_status(self, text):
        self.status.set_text(text)

    def _drop(self, _w, ctx, x, y, data, info, time):
        from gi.repository import GLib
        files = [GLib.filename_from_uri(u)[0] for u in data.get_uris() if u.startswith("file://")]
        if files:
            self.app.upload_files(files)
        ctx.finish(True, False, time)

    def _close(self, *_):
        w, h = self.get_size()
        self.app.config.set("main_window.width", w, save=False)
        self.app.config.set("main_window.height", h)
        if self.app.tray:
            self.hide()
            return True
        self.app.quit()
        return False
