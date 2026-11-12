"""Small GTK helpers shared by the dialogs."""
import threading

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from .. import gfx


def message(parent, text, kind=Gtk.MessageType.INFO, secondary=None):
    d = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=kind, buttons=Gtk.ButtonsType.OK, text=text)
    if secondary:
        d.format_secondary_text(secondary)
    d.run()
    d.destroy()


def error(parent, text, secondary=None):
    message(parent, text, Gtk.MessageType.ERROR, secondary)


def ask(parent, text, secondary=None):
    d = Gtk.MessageDialog(transient_for=parent, modal=True, message_type=Gtk.MessageType.QUESTION,
                          buttons=Gtk.ButtonsType.YES_NO, text=text)
    if secondary:
        d.format_secondary_text(secondary)
    r = d.run() == Gtk.ResponseType.YES
    d.destroy()
    return r


IMAGE_FILTER = [("Images", ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.webp", "*.tif", "*.tiff"])]
VIDEO_FILTER = [("Video", ["*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.gif", "*.flv", "*.wmv"])]


def choose_files(parent, title="Choose file", multiple=False, folder=False, save=False, filters=None, name=None):
    action = (Gtk.FileChooserAction.SELECT_FOLDER if folder else
              Gtk.FileChooserAction.SAVE if save else Gtk.FileChooserAction.OPEN)
    d = Gtk.FileChooserDialog(title=title, parent=parent, action=action)
    d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
    d.set_select_multiple(multiple)
    if save:
        d.set_do_overwrite_confirmation(True)
        if name:
            d.set_current_name(name)
    for label, pats in (filters or []):
        f = Gtk.FileFilter()
        f.set_name(label)
        for p in pats:
            f.add_pattern(p)
        d.add_filter(f)
    res = None
    if d.run() == Gtk.ResponseType.OK:
        res = d.get_filenames() if multiple else d.get_filename()
    d.destroy()
    return res


def grid(rows, parent=None, spacing=8):
    """rows: list of (label_text_or_None, widget). Returns a Gtk.Grid."""
    g = Gtk.Grid(row_spacing=spacing, column_spacing=12)
    g.set_border_width(12)
    for i, (label, w) in enumerate(rows):
        if label is None:
            g.attach(w, 0, i, 2, 1)
        else:
            l = Gtk.Label(label=label, xalign=0, wrap=True, max_width_chars=44)
            g.attach(l, 0, i, 1, 1)
            if isinstance(w, (Gtk.Entry, Gtk.ComboBoxText)):
                w.set_size_request(230, -1)
            w.set_hexpand(False)
            w.set_halign(Gtk.Align.START if isinstance(w, (Gtk.Switch, Gtk.SpinButton, Gtk.Button, Gtk.ColorButton)) else Gtk.Align.FILL)
            g.attach(w, 1, i, 1, 1)
    return g


def window(title, child, w=520, h=0, parent=None):
    win = Gtk.Window(title=title)
    win.set_default_size(w, h)
    win.set_icon_name("applets-screenshooter")
    if parent:
        win.set_transient_for(parent)
    win.add(child)
    win.show_all()
    return win


def background(fn, done, *args):
    """Run fn(*args) in a thread; call done(result, error) on the GTK main loop."""
    def work():
        try:
            r, e = fn(*args), None
        except Exception as ex:  # noqa
            r, e = None, ex
        GLib.idle_add(done, r, e)
    threading.Thread(target=work, daemon=True).start()


def pixbuf_image(img, max_w=420, max_h=320):
    from PIL import Image
    im = img.copy()
    im.thumbnail((max_w, max_h), Image.LANCZOS)
    return Gtk.Image.new_from_pixbuf(gfx.pil_to_pixbuf(im))


def monospace_view(text="", w=520, h=240):
    tv = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
    tv.get_buffer().set_text(text)
    sw = Gtk.ScrolledWindow()
    sw.set_size_request(w, h)
    sw.add(tv)
    return sw, tv
