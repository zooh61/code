"""Screen / window / monitor capture on X11 through GDK (no external helper needed)."""
import os
import subprocess
from dataclasses import dataclass, field

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk
from PIL import Image

from . import gfx

try:
    gi.require_version("GdkX11", "3.0")
    from gi.repository import GdkX11
except (ValueError, ImportError):  # pragma: no cover
    GdkX11 = None


@dataclass
class WindowInfo:
    x: int
    y: int
    w: int
    h: int
    title: str = ""
    process: str = ""
    xid: int = 0

    @property
    def rect(self):
        return (self.x, self.y, self.w, self.h)


@dataclass
class Shot:
    image: Image.Image
    x: int = 0
    y: int = 0
    title: str = ""
    process: str = ""
    kind: str = "screen"
    meta: dict = field(default_factory=dict)
    scale: float = 1.0      # device pixels per logical (GDK) pixel, e.g. 2.0 on a 200% HiDPI desktop


def scale_factor() -> int:
    """GDK window scale (1 normally, 2 on HiDPI). Screen coordinates from GDK are logical; X11 / ffmpeg use device pixels."""
    try:
        return max(1, Gdk.Display.get_default().get_monitor(0).get_scale_factor())
    except Exception:
        return 1


def to_device(rect):
    k = scale_factor()
    return tuple(int(round(v * k)) for v in rect)


def virtual_screen():
    """(x, y, w, h) of the bounding box of every monitor."""
    d = Gdk.Display.get_default()
    xs, ys, xe, ye = [], [], [], []
    for i in range(d.get_n_monitors()):
        g = d.get_monitor(i).get_geometry()
        xs.append(g.x); ys.append(g.y); xe.append(g.x + g.width); ye.append(g.y + g.height)
    if not xs:
        root = Gdk.get_default_root_window()
        return (0, 0, root.get_width(), root.get_height())
    return (min(xs), min(ys), max(xe) - min(xs), max(ye) - min(ys))


def monitors():
    d = Gdk.Display.get_default()
    out = []
    for i in range(d.get_n_monitors()):
        m = d.get_monitor(i)
        g = m.get_geometry()
        out.append({"index": i, "name": m.get_model() or f"Monitor {i + 1}", "x": g.x, "y": g.y, "w": g.width,
                    "h": g.height, "primary": m.is_primary()})
    return out


def pointer_position():
    seat = Gdk.Display.get_default().get_default_seat()
    _, x, y = seat.get_pointer().get_position()
    return x, y


def monitor_at_pointer():
    px, py = pointer_position()
    for m in monitors():
        if m["x"] <= px < m["x"] + m["w"] and m["y"] <= py < m["y"] + m["h"]:
            return m
    return monitors()[0]


def _draw_cursor(img, x, y, w_logical):
    try:
        d = Gdk.Display.get_default()
        cur = Gdk.Cursor.new_for_display(d, Gdk.CursorType.LEFT_PTR).get_image()
        if cur is None:
            return img
        k = img.width / max(1, w_logical)
        px, py = pointer_position()
        c = gfx.pixbuf_to_pil(cur)
        hx = int(cur.get_option("x_hot") or 0)
        hy = int(cur.get_option("y_hot") or 0)
        pos = (int((px - x) * k) - hx, int((py - y) * k) - hy)
        img = img.copy()
        if 0 <= pos[0] < img.width and 0 <= pos[1] < img.height:
            img.alpha_composite(c, pos, (0, 0, min(c.width, img.width - pos[0]), min(c.height, img.height - pos[1])))
    except Exception:
        pass
    return img


def grab_rect(x, y, w, h, cursor=False) -> Image.Image:
    """Grab a rectangle (in virtual-screen coordinates)."""
    root = Gdk.get_default_root_window()
    rw, rh = root.get_width(), root.get_height()
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(rw, x + w), min(rh, y + h)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("The capture area is outside the screen.")
    pb = Gdk.pixbuf_get_from_window(root, x0, y0, x1 - x0, y1 - y0)
    if pb is None:
        raise RuntimeError("Could not read the screen (is this an X11 session?).")
    img = gfx.pixbuf_to_pil(pb)
    return _draw_cursor(img, x0, y0, x1 - x0) if cursor else img


def grab_fullscreen(cursor=False) -> Shot:
    x, y, w, h = virtual_screen()
    img = grab_rect(x, y, w, h, cursor)
    return Shot(img, x, y, "Desktop", "", "fullscreen", scale=img.width / max(1, w))


def grab_monitor(index=None, cursor=False) -> Shot:
    m = monitor_at_pointer() if index is None else monitors()[index]
    img = grab_rect(m["x"], m["y"], m["w"], m["h"], cursor)
    return Shot(img, m["x"], m["y"], m["name"], "", "monitor", scale=img.width / max(1, m["w"]))


def _xprop_name(xid):
    try:
        return subprocess.run(["xdotool", "getwindowname", str(xid)], capture_output=True, text=True,
                              timeout=2).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _process_name(xid):
    try:
        pid = subprocess.run(["xdotool", "getwindowpid", str(xid)], capture_output=True, text=True,
                             timeout=2).stdout.strip()
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _info(win: Gdk.Window, with_names=True):
    fr = win.get_frame_extents()
    xid = win.get_xid() if hasattr(win, "get_xid") else 0
    wi = WindowInfo(fr.x, fr.y, fr.width, fr.height, xid=xid)
    if with_names and xid:
        wi.title, wi.process = _xprop_name(xid), _process_name(xid)
    return wi


def list_windows(with_names=False):
    """Visible top-level windows, topmost first."""
    screen = Gdk.Screen.get_default()
    stack = screen.get_window_stack() or []
    out = []
    for win in reversed(stack):
        try:
            if not win.is_visible() or win.get_state() & Gdk.WindowState.ICONIFIED:
                continue
            if win.get_type_hint() in (Gdk.WindowTypeHint.DESKTOP, Gdk.WindowTypeHint.DOCK,
                                       Gdk.WindowTypeHint.TOOLTIP, Gdk.WindowTypeHint.NOTIFICATION,
                                       Gdk.WindowTypeHint.DND, Gdk.WindowTypeHint.POPUP_MENU):
                continue
            wi = _info(win, with_names)
            if wi.w > 8 and wi.h > 8:
                out.append(wi)
        except Exception:
            continue
    return out


def active_window():
    screen = Gdk.Screen.get_default()
    win = screen.get_active_window()
    if win is None:
        return None
    wi = _info(win)
    return wi if wi.w > 0 else None


def grab_window(wi: WindowInfo, cursor=False) -> Shot:
    img = grab_rect(wi.x, wi.y, wi.w, wi.h, cursor)
    return Shot(img, wi.x, wi.y, wi.title, wi.process, "window", scale=img.width / max(1, wi.w))


def grab_active_window(cursor=False) -> Shot:
    wi = active_window()
    if wi is None:
        return grab_monitor(cursor=cursor)
    return grab_window(wi, cursor)


def grab_region(x, y, w, h, cursor=False) -> Shot:
    img = grab_rect(x, y, w, h, cursor)
    return Shot(img, x, y, "Region", "", "region", scale=img.width / max(1, w))


def pixel_at(img: Image.Image, x, y):
    x = max(0, min(img.width - 1, x))
    y = max(0, min(img.height - 1, y))
    return img.getpixel((x, y))[:3]


def webpage_capture(url, width=1366, height=768, full_page=False, timeout=60) -> Image.Image:
    """Headless browser screenshot using chromium/chrome or firefox, whichever is installed."""
    import shutil
    import tempfile
    out = os.path.join(tempfile.mkdtemp(prefix="mintshare-web-"), "page.png")
    if not url.startswith(("http://", "https://", "file://")):
        url = "https://" + url
    for exe in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "brave-browser"):
        path = shutil.which(exe)
        if path:
            cmd = [path, "--headless=new", "--no-sandbox", "--hide-scrollbars", f"--window-size={width},{height}",
                   f"--screenshot={out}", url]
            subprocess.run(cmd, capture_output=True, timeout=timeout)
            if os.path.exists(out):
                return Image.open(out).convert("RGBA")
    path = shutil.which("firefox")
    if path:
        subprocess.run([path, "--headless", "--screenshot", out, f"--window-size={width},{height}", url],
                       capture_output=True, timeout=timeout, cwd=os.path.dirname(out))
        if os.path.exists(out):
            return Image.open(out).convert("RGBA")
    raise RuntimeError("Webpage capture needs Chromium, Google Chrome or Firefox to be installed.")
