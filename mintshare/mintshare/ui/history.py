"""History browser (captures, uploads, recordings)."""
import os
import time
from datetime import datetime

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from .. import gfx
from . import common as C

IMG = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff")


class HistoryView(Gtk.Box):
    def __init__(self, app):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.app = app
        self.set_border_width(8)
        bar = Gtk.Box(spacing=6)
        self.search = Gtk.SearchEntry(placeholder_text="Search name, URL, host…")
        self.search.connect("search-changed", lambda *_: self.reload())
        self.kind = Gtk.ComboBoxText()
        for k in ("All", "image", "text", "file", "video", "url"):
            self.kind.append_text(k)
        self.kind.set_active(0)
        self.kind.connect("changed", lambda *_: self.reload())
        self.only_up = Gtk.CheckButton(label="Uploaded only")
        self.only_up.connect("toggled", lambda *_: self.reload())
        bar.pack_start(self.search, True, True, 0)
        bar.pack_start(self.kind, False, False, 0)
        bar.pack_start(self.only_up, False, False, 0)
        self.pack_start(bar, False, False, 0)
        self.store = Gtk.ListStore(object, GdkPixbufType(), str, str, str, str, str)  # entry, thumb, name, date, host, url, size
        tv = Gtk.TreeView(model=self.store)
        tv.set_headers_visible(True)
        tv.set_rules_hint(True)
        pr = Gtk.CellRendererPixbuf()
        c = Gtk.TreeViewColumn("", pr, pixbuf=1)
        tv.append_column(c)
        for i, t in ((2, "Name"), (3, "Date"), (4, "Host"), (6, "Size"), (5, "URL")):
            col = Gtk.TreeViewColumn(t, Gtk.CellRendererText(ellipsize=3), text=i)
            col.set_resizable(True)
            col.set_expand(i in (2, 5))
            tv.append_column(col)
        tv.connect("row-activated", self._activated)
        tv.connect("button-press-event", self._button)
        self.tv = tv
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.add(tv)
        self.pack_start(sw, True, True, 0)
        row = Gtk.Box(spacing=6)
        for label, cb in (("Copy URL", self.copy_url), ("Open", self.open_item), ("Show in folder", self.show_folder),
                          ("Edit image", self.edit), ("Re-upload", self.reupload), ("Remove entry", self.remove),
                          ("Clear all", self.clear)):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, c=cb: c())
            row.pack_start(b, False, False, 0)
        self.pack_start(row, False, False, 0)
        self._gen = 0
        self.reload()

    def _selected(self):
        m, it = self.tv.get_selection().get_selected()
        return m[it][0] if it else None

    def reload(self, *_):
        self._gen += 1
        gen = self._gen
        self.store.clear()
        kind = self.kind.get_active_text()
        rows = self.app.history.list(self.search.get_text(), None if kind == "All" else kind, self.only_up.get_active(), 400)
        pending = []
        for e in rows:
            size = f"{e['size'] / 1024:.0f} KB" if e["size"] else ""
            it = self.store.append((e, None, e["filename"], datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d %H:%M"),
                                    e["host"], e["url"], size))
            if e["filepath"].lower().endswith(IMG) and os.path.exists(e["filepath"]):
                pending.append((it, e["filepath"]))

        def load():
            if gen != self._gen:
                return False
            for _ in range(6):
                if not pending:
                    return False
                it, p = pending.pop(0)
                pb = gfx.thumbnail_pixbuf(p, 40)
                if pb and self.store.iter_is_valid(it):
                    self.store.set_value(it, 1, pb)
            return True
        GLib.idle_add(load)

    # actions
    def _activated(self, *_):
        self.open_item()

    def _button(self, tv, ev):
        if ev.button == 3:
            path = tv.get_path_at_pos(int(ev.x), int(ev.y))
            if path:
                tv.get_selection().select_path(path[0])
                m = Gtk.Menu()
                for label, cb in (("Copy URL", self.copy_url), ("Open", self.open_item), ("Show in folder", self.show_folder),
                                  ("Edit image", self.edit), ("Re-upload", self.reupload), ("Remove entry", self.remove)):
                    it = Gtk.MenuItem(label=label)
                    it.connect("activate", lambda _i, c=cb: c())
                    m.append(it)
                m.show_all()
                m.popup_at_pointer(ev)
                return True

    def copy_url(self):
        e = self._selected()
        if e:
            gfx.copy_text(e["url"] or e["filepath"])

    def open_item(self):
        e = self._selected()
        if e:
            if e["filepath"] and os.path.exists(e["filepath"]):
                self.app.open_path(e["filepath"])
            elif e["url"]:
                self.app.open_url(e["url"])

    def show_folder(self):
        e = self._selected()
        if e and e["filepath"]:
            self.app.open_path(os.path.dirname(e["filepath"]))

    def edit(self):
        e = self._selected()
        if e and e["filepath"].lower().endswith(IMG) and os.path.exists(e["filepath"]):
            from PIL import Image
            self.app.open_editor(Image.open(e["filepath"]).convert("RGBA"))

    def reupload(self):
        e = self._selected()
        if e and e["filepath"] and os.path.exists(e["filepath"]):
            self.app.upload_files([e["filepath"]])

    def remove(self):
        e = self._selected()
        if e:
            self.app.history.delete(e["id"])
            self.reload()

    def clear(self):
        if C.ask(self.get_toplevel(), "Clear the whole history?", "Files on disk are not deleted."):
            self.app.history.clear()
            self.reload()


def GdkPixbufType():
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    return GdkPixbuf.Pixbuf


class HistoryWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="MintShare – History")
        self.set_default_size(980, 560)
        self.set_icon_name("applets-screenshooter")
        self.view = HistoryView(app)
        self.add(self.view)
        self.show_all()
