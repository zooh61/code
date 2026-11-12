"""PIL <-> GdkPixbuf <-> cairo helpers and clipboard utilities."""
import io

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from PIL import Image


def pil_to_pixbuf(img: Image.Image) -> GdkPixbuf.Pixbuf:
    img = img.convert("RGBA")
    data = GLib.Bytes.new(img.tobytes())
    return GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, True, 8, img.width, img.height, img.width * 4)


def pixbuf_to_pil(pb: GdkPixbuf.Pixbuf) -> Image.Image:
    mode = "RGBA" if pb.get_has_alpha() else "RGB"
    n = 4 if pb.get_has_alpha() else 3
    w, h, stride = pb.get_width(), pb.get_height(), pb.get_rowstride()
    raw = pb.get_pixels()
    if stride != w * n:
        img = Image.frombuffer(mode, (w, h), raw, "raw", mode, stride, 1)
    else:
        img = Image.frombytes(mode, (w, h), raw)
    return img.convert("RGBA")


def pil_to_surface(img: Image.Image):
    return Gdk.cairo_surface_create_from_pixbuf(pil_to_pixbuf(img), 1, None)


def surface_to_pil(surface) -> Image.Image:
    surface.flush()
    w, h, stride = surface.get_width(), surface.get_height(), surface.get_stride()
    return Image.frombuffer("RGBa", (w, h), bytes(surface.get_data()), "raw", "BGRa", stride, 1).convert("RGBA")


def clipboard():
    return Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)


def copy_text(text: str):
    cb = clipboard()
    cb.set_text(text, -1)
    cb.store()


def copy_image(img: Image.Image):
    cb = clipboard()
    cb.set_image(pil_to_pixbuf(img))
    cb.store()


def paste_image():
    pb = clipboard().wait_for_image()
    return pixbuf_to_pil(pb) if pb else None


def paste_text():
    return clipboard().wait_for_text()


def paste_uris():
    cb = clipboard()
    uris = cb.wait_for_uris()
    if uris:
        return [GLib.filename_from_uri(u)[0] for u in uris if u.startswith("file://")]
    return []


def thumbnail_pixbuf(path, size=96):
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
    except GLib.Error:
        return None


def parse_color(s: str):
    c = Gdk.RGBA()
    c.parse(s)
    return c


def rgba_hex(c: Gdk.RGBA) -> str:
    return "#%02x%02x%02x" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255))
