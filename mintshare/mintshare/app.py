"""MintShare application: wires captures, tools, uploads, tray, hotkeys and command line together."""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk
from PIL import Image

from . import APP_ID, __version__, actions, capture, gfx, hotkeys, paths, stitch, tasks, uploaders
from .config import Config
from .history import History
from .recorder import Recorder, RecorderError
from .selector import Overlay
from .tools import core
from .ui import common as C


# ------------------------------------------------------------------ main-thread bridge used by the pipeline
class AppUI(tasks.NullUI):
    def __init__(self, app):
        self.app = app
        self._busy = 0

    def call(self, fn, *a):
        """Run fn on the GTK main thread and return its result (blocks worker threads)."""
        if threading.current_thread() is threading.main_thread():
            return fn(*a)
        ev, out = threading.Event(), []

        def run():
            try:
                out.append(fn(*a))
            except Exception as e:  # noqa
                out.append(None)
                print("UI call failed:", e, file=sys.stderr)
            ev.set()
            return False
        GLib.idle_add(run)
        ev.wait()
        return out[0] if out else None

    def edit(self, img, title=""):
        ev, out = threading.Event(), []

        def open_it():
            from .ui.editor import Editor
            Editor(img, title, on_done=lambda r: (out.append(r), ev.set()), app=self.app).show_all()
            return False
        GLib.idle_add(open_it)
        ev.wait()
        return out[0] if out else None

    def copy_image(self, img): self.call(gfx.copy_image, img)
    def copy_text(self, text): self.call(gfx.copy_text, text)
    def pin(self, img): GLib.idle_add(self.app.pin_image, img)
    def show_text(self, title, text): GLib.idle_add(self.app.show_text, title, text)
    def show_qr(self, text): GLib.idle_add(self.app.show_qr, text)
    def print_image(self, img): self.call(self.app.print_image, img)
    def open_path(self, path): GLib.idle_add(self.app.open_path, path)
    def open_url(self, url): GLib.idle_add(self.app.open_url, url)
    def play_sound(self): self.app.play_sound()

    def save_as(self, suggested):
        def ask():
            return C.choose_files(None, "Save image as", save=True, name=os.path.basename(suggested))
        return self.call(ask)

    def notify(self, title, body="", path=None, url=None, error=False):
        GLib.idle_add(self.app.notify, title, body, path, url, error)

    def ocr(self, img):
        lang = self.app.config.get("general.language_ocr", "eng")
        text = core.ocr_image(img, lang)
        GLib.idle_add(self.app.show_text, "Recognized text", text or "(no text found)")
        return text

    def busy(self, delta):
        self._busy += delta
        GLib.idle_add(self.app.update_busy, self._busy)


# ------------------------------------------------------------------ application
class MintShare(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.config = None
        self.main = None
        self.tray = None
        self.recorder = Recorder()
        self.rec_bar = None
        self.rec_gif = False
        self.scroll_state = None
        self.auto_state = None
        self.xhotkeys = None
        self.minimized = False
        self.windows = {}

    # ---------------------------------------------------------- lifecycle
    def do_startup(self):
        Gtk.Application.do_startup(self)
        paths.ensure(paths.CONFIG_DIR, paths.DATA_DIR, paths.CUSTOM_UPLOADERS_DIR)
        self.config = Config()
        self.history = History(max_entries=self.config.get("history.max_entries", 5000))
        self.ui = AppUI(self)
        self.pipeline = tasks.Pipeline(self.config, self.history, self.ui)
        act = Gio.SimpleAction.new("open", GLib.VariantType.new("s"))
        act.connect("activate", lambda _a, p: self._open_target(p.get_string()))
        self.add_action(act)
        if self.config.get("general.tray_icon", True):
            self._make_tray()
        self.hold()
        GLib.idle_add(self._autoapply_hotkeys)

    def do_activate(self):
        if not self.minimized:
            self.show_main()

    def do_command_line(self, cl):
        args = cl.get_arguments()[1:]
        self.minimized = ("--minimized" in args or "-m" in args or
                          bool(self.config.get("general.start_minimized") and not args and self.main is None
                               and self.tray is not None))
        args = [a for a in args if a not in ("--minimized", "-m")]
        self._autostart_sync()
        if not args:
            self.do_activate_once()
            return 0
        if self.main is None and not self.minimized and False:
            pass
        i = 0
        files = []
        status = 0
        while i < len(args):
            a = args[i]
            if a in ("--list-actions", "-l"):
                cl.print_literal("\n".join(f"{k:18} {v[0]}" for k, v in actions.ACTIONS.items()) + "\n")
            elif a in ("--version", "-v"):
                cl.print_literal(f"MintShare {__version__}\n")
            elif a == "--apply-hotkeys":
                cl.print_literal(self.apply_hotkeys() + "\n")
            elif a == "--remove-hotkeys":
                if self.xhotkeys:
                    self.xhotkeys.stop()
                self.config.set("general.hotkeys_applied", False)
                r = hotkeys.clear_cinnamon() if hotkeys.is_cinnamon() else []
                cl.print_literal("Hotkeys removed" + (f"; restored Cinnamon bindings: {', '.join(r)}" if r else "") + "\n")
            elif a == "--show-hotkey-changes":
                cl.print_literal("\n".join(hotkeys.plan_cinnamon(self.config.get("workflows", []),
                                 self.config.get("general.take_over_print_screen", True)) or ["(nothing)"]) + "\n")
            elif a == "--workflow" and i + 1 < len(args):
                i += 1
                if not self.run_workflow(args[i]):
                    cl.printerr_literal(f"No workflow named '{args[i]}'\n")
                    status = 1
            elif a == "--action" and i + 1 < len(args):
                i += 1
                self.run_action(args[i])
            elif a in ("--upload", "-u"):
                files += [x for x in args[i + 1:] if os.path.exists(x)]
                self.upload_files(files)
                break
            elif a in ("--edit", "-e") and i + 1 < len(args):
                i += 1
                self.open_editor(Image.open(args[i]).convert("RGBA"))
            elif a in actions.ACTIONS:
                self.run_action(a)
            elif os.path.exists(a):
                files.append(a)
            else:
                cl.printerr_literal(f"Unknown argument: {a}\n")
                status = 2
            i += 1
        if files and "--upload" not in args and "-u" not in args:
            self.upload_files(files)
        return status

    def do_activate_once(self):
        if self.minimized:
            return
        self.show_main()

    # ---------------------------------------------------------- windows
    def show_main(self):
        from .ui.main import MainWindow
        if self.main is None:
            self.main = MainWindow(self)
            self.main.connect("destroy", lambda *_: setattr(self, "main", None))
            self.add_window(self.main)
        self.main.present()

    def _singleton(self, key, factory, *a):
        w = self.windows.get(key)
        if w is not None and w.get_realized():
            w.present()
            return w
        w = factory(*a)
        self.windows[key] = w
        self.add_window(w)
        return w

    def show_settings(self, page=0):
        from .ui.settings import SettingsWindow
        w = self.windows.get("settings")
        if w is not None and w.get_realized():
            w.nb.set_current_page(page)
            w.present()
        else:
            w = SettingsWindow(self, page)
            self.windows["settings"] = w
            self.add_window(w)

    def settings_changed(self):
        self._autostart_sync()
        if self.config.get("general.tray_icon", True) and not self.tray:
            self._make_tray()
        elif not self.config.get("general.tray_icon", True) and self.tray:
            self.tray.destroy()
            self.tray = None
        elif self.tray:
            self.tray.rebuild()

    def update_busy(self, n):
        if self.main:
            self.main.set_status("Working…" if n else "Ready")

    # ---------------------------------------------------------- helpers
    def notify(self, title, body="", path=None, url=None, error=False):
        if self.main:
            self.main.set_status(f"{title}: {body}"[:120])
        if not (self.config.get("general.notifications", True) or error):
            return
        n = Gio.Notification.new(title)
        n.set_body(body)
        n.set_priority(Gio.NotificationPriority.HIGH if error else Gio.NotificationPriority.NORMAL)
        if path and os.path.splitext(path)[1].lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
            n.set_icon(Gio.FileIcon.new(Gio.File.new_for_path(path)))
        else:
            n.set_icon(Gio.ThemedIcon.new("dialog-error" if error else "applets-screenshooter"))
        target = url or path
        if target:
            try:
                n.set_default_action_and_target_value("app.open", GLib.Variant.new_string(target))
            except AttributeError:
                try:
                    n.set_default_action_and_target("app.open", "s", target)
                except Exception:
                    n.set_default_action("app.open")
        self.send_notification(None, n)

    def _open_target(self, t):
        (self.open_url if t.startswith(("http://", "https://")) else self.open_path)(t)

    def open_path(self, path):
        try:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def play_sound(self):
        if not self.config.get("general.play_sound", True):
            return
        for cmd in (["canberra-gtk-play", "-i", "camera-shutter"],
                    ["paplay", "/usr/share/sounds/freedesktop/stereo/camera-shutter.oga"]):
            if shutil.which(cmd[0]):
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return

    def show_text(self, title, text):
        from .ui.toolwins import show_text
        show_text(title, text, self)

    def show_qr(self, text):
        from .ui.toolwins import QRWindow
        self._singleton("qr", QRWindow, self, text).entry.get_buffer().set_text(text)

    def pin_image(self, img, x=None, y=None, scale=None):
        from .ui.toolwins import PinWindow
        PinWindow(img, x, y, scale if scale else 1.0 / capture.scale_factor())

    def print_image(self, img):
        op = Gtk.PrintOperation()
        op.set_n_pages(1)
        pb = gfx.pil_to_surface(img)

        def draw(_op, ctx, _n):
            cr = ctx.get_cairo_context()
            s = min(ctx.get_width() / img.width, ctx.get_height() / img.height, 1.0)
            cr.scale(s, s)
            cr.set_source_surface(pb, 0, 0)
            cr.paint()
        op.connect("draw-page", draw)
        op.run(Gtk.PrintOperationAction.PRINT_DIALOG, None)

    def open_editor(self, img, on_done=None):
        from .ui.editor import Editor
        e = Editor(img, on_done=on_done, app=self)
        self.add_window(e)
        e.show_all()
        return e

    # ---------------------------------------------------------- action dispatch
    def run_action(self, name, overrides=None):
        if name not in actions.ACTIONS:
            return False
        fn = getattr(self, "act_" + name, None)
        if fn is None:
            return False
        try:
            fn(overrides)
        except Exception as e:  # noqa
            self.notify("MintShare error", f"{type(e).__name__}: {e}", error=True)
        return True

    def run_workflow(self, name):
        for w in self.config.get("workflows", []):
            if w["name"].lower() == name.lower():
                return self.run_action(w["job"], w.get("overrides") or {})
        return False

    # ---------------------------------------------------------- capture plumbing
    def _hide_windows(self):
        hidden = []
        for w in Gtk.Window.list_toplevels():
            if w.get_visible() and w.get_window() is not None:
                hidden.append(w)
                w.set_opacity(0.0)
                w.hide()
        return hidden

    def _restore_windows(self, hidden):
        for w in hidden:
            try:
                w.set_opacity(1.0)
                w.show()
            except Exception:
                pass

    def _after_delay(self, fn, delay=None, hide=True):
        hidden = self._hide_windows() if hide else []
        d = self.config.get("capture.delay", 0) if delay is None else delay
        GLib.timeout_add(int(250 + d * 1000), lambda: (fn(hidden), False)[1])

    def _cursor(self):
        return bool(self.config.get("capture.show_cursor"))

    def _emit_shot(self, shot, overrides, hidden=()):
        self._restore_windows(hidden)
        self.pipeline.run_async(self.pipeline.process_image, shot.image, shot.title, shot.process, overrides)

    def _crop(self, shot, rect):
        x, y, w, h = [int(v) for v in rect]
        k = shot.scale
        lx, ly = int(round((x - shot.x) * k)), int(round((y - shot.y) * k))
        img = shot.image.crop((max(0, lx), max(0, ly), min(shot.image.width, lx + int(round(w * k))),
                               min(shot.image.height, ly + int(round(h * k)))))
        return capture.Shot(img, x, y, shot.title, shot.process, "region", scale=k)

    def _select(self, mode, done, delay=None, hide=True):
        """Freeze the screen and let the user pick; done(shot, rect, hidden) gets None rect when cancelled."""
        def go(hidden):
            try:
                shot = capture.grab_fullscreen(self._cursor())
            except Exception as e:  # noqa
                self._restore_windows(hidden)
                self.notify("Capture failed", str(e), error=True)
                return
            wins = capture.list_windows()

            def finished(rect):
                done(shot, rect, hidden)
            Overlay(shot, wins, mode, finished, self.config.get("capture"), None).run()
        self._after_delay(go, delay, hide)

    # ---------------------------------------------------------- capture actions
    def act_fullscreen(self, ov=None):
        self._after_delay(lambda h: self._emit_shot(capture.grab_fullscreen(self._cursor()), ov, h))

    def act_monitor(self, ov=None):
        self._after_delay(lambda h: self._emit_shot(capture.grab_monitor(None, self._cursor()), ov, h))

    def act_active_window(self, ov=None):
        wi = capture.active_window()
        if wi is None or wi.title.startswith("MintShare"):
            wi = next(iter(capture.list_windows(True)), None)
        self._after_delay(lambda h: self._emit_shot(capture.grab_window(wi, self._cursor()) if wi else
                                                    capture.grab_monitor(None, self._cursor()), ov, h))

    def act_region(self, ov=None, mode="region"):
        def done(shot, rect, hidden):
            self._restore_windows(hidden)
            if not rect:
                return
            self.config.set("capture.last_region", list(rect))
            s = self._crop(shot, rect)
            if mode == "window":
                for w in capture.list_windows(True):
                    if w.rect == tuple(int(v) for v in rect):
                        s.title, s.process = w.title, w.process
            self.pipeline.run_async(self.pipeline.process_image, s.image, s.title, s.process, ov)
        self._select(mode, done)

    def act_window(self, ov=None):
        self.act_region(ov, "window")

    def act_last_region(self, ov=None):
        r = self.config.get("capture.last_region")
        if not r:
            return self.act_region(ov)
        self._after_delay(lambda h: self._emit_shot(capture.grab_region(*r, cursor=self._cursor()), ov, h))

    def act_ocr(self, ov=None):
        def done(shot, rect, hidden):
            self._restore_windows(hidden)
            if rect:
                img = self._crop(shot, rect).image
                self.pipeline.run_async(self._ocr_job, img)
        self._select("region", done)

    def _ocr_job(self, img):
        text = self.ui.ocr(img)
        if text:
            self.ui.copy_text(text)
            self.ui.notify("Text copied", text[:120])
        else:
            self.ui.notify("OCR", "No text recognized", error=True)

    def act_webpage(self, ov=None):
        d = Gtk.Dialog(title="Webpage capture", transient_for=self.main, modal=True)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Capture", Gtk.ResponseType.OK)
        e = Gtk.Entry(placeholder_text="https://example.com", width_chars=48)
        d.get_content_area().pack_start(e, True, True, 12)
        d.set_default_response(Gtk.ResponseType.OK)
        e.set_activates_default(True)
        d.show_all()
        url = e.get_text().strip() if d.run() == Gtk.ResponseType.OK else ""
        d.destroy()
        if url:
            cfg = self.config.get("capture")

            def job():
                img = capture.webpage_capture(url, cfg["webpage_width"], cfg["webpage_height"])
                self.pipeline.process_image(img, url, "", ov)
            self.pipeline.run_async(job)

    # ---------------------------------------------------------- scrolling capture
    def act_scrolling(self, ov=None):
        if self.scroll_state:
            self.scroll_state["stop"] = True
            return

        def done(shot, rect, hidden):
            if not rect:
                self._restore_windows(hidden)
                return
            x, y, w, h = [int(v) for v in rect]
            cx, cy = x + w // 2, y + h // 2
            dx, dy = capture.to_device((cx, cy))
            subprocess.run(["xdotool", "mousemove", str(dx), str(dy)], capture_output=True)
            self.scroll_state = {"rect": (x, y, w, h), "stitch": None, "steps": 0, "stop": False, "hidden": hidden, "ov": ov}
            self.notify("Scrolling capture", "Keep the pointer over the content. Run “Scrolling capture” again to stop.")
            GLib.timeout_add(700, self._scroll_tick)
        self._select("region", done)

    def _scroll_tick(self):
        st = self.scroll_state
        if not st:
            return False
        cfg = self.config.get("capture")
        try:
            frame = capture.grab_rect(*st["rect"])
        except Exception as e:  # noqa
            return self._scroll_finish(f"capture failed: {e}")
        reason = None
        if st["stitch"] is None:
            st["stitch"] = stitch.Stitcher(frame)
        else:
            r = st["stitch"].add(frame)
            if r == "end":
                reason = "end of page"
            elif r == "nomatch":
                reason = "could not align next frame (animated or sticky content?)"
        st["steps"] += 1
        if st["stop"]:
            reason = "stopped"
        elif st["steps"] >= cfg["scroll_max_steps"]:
            reason = "step limit"
        if reason:
            return self._scroll_finish(reason)
        subprocess.run(["xdotool", "click", "--repeat", str(cfg["scroll_amount"]), "--delay", "20", "5"], capture_output=True)
        GLib.timeout_add(int(cfg["scroll_delay"] * 1000), self._scroll_tick)
        return False

    def _scroll_finish(self, reason):
        st, self.scroll_state = self.scroll_state, None
        self._restore_windows(st["hidden"])
        img = st["stitch"].result() if st["stitch"] else None
        if img is not None:
            self.notify("Scrolling capture finished", f"{img.width}×{img.height}px ({reason})")
            self.pipeline.run_async(self.pipeline.process_image, img, "Scrolling capture", "", st["ov"])
        return False

    # ---------------------------------------------------------- auto capture
    def act_auto_capture(self, ov=None):
        if self.auto_state:
            self._auto_stop()
            return
        cfg = self.config.get("capture")
        d = Gtk.Dialog(title="Auto capture", transient_for=self.main, modal=True)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Choose region and start", Gtk.ResponseType.OK)
        iv = Gtk.SpinButton.new_with_range(0.5, 86400, 0.5)
        iv.set_value(cfg["auto_interval"])
        cnt = Gtk.SpinButton.new_with_range(0, 100000, 1)
        cnt.set_value(cfg["auto_count"])
        full = Gtk.CheckButton(label="Whole screen instead of a region")
        d.get_content_area().pack_start(C.grid([("Interval (seconds)", iv), ("Number of shots (0 = until stopped)", cnt), (None, full)]), True, True, 0)
        d.show_all()
        ok = d.run() == Gtk.ResponseType.OK
        interval, count, whole = iv.get_value(), int(cnt.get_value()), full.get_active()
        d.destroy()
        if not ok:
            return
        self.config.set("capture.auto_interval", interval, save=False)
        self.config.set("capture.auto_count", count)

        def start(rect):
            self.auto_state = {"rect": rect, "n": 0, "max": count, "interval": interval, "ov": ov}
            self.notify("Auto capture started", "Choose “Auto capture” again (tray or hotkey) to stop.")
            self._auto_tick()
            self.auto_state["src"] = GLib.timeout_add(int(interval * 1000), self._auto_tick)
        if whole:
            start(capture.virtual_screen())
        else:
            self._select("region", lambda s, r, h: (self._restore_windows(h), r and start(tuple(int(v) for v in r))))

    def _auto_tick(self):
        st = self.auto_state
        if not st:
            return False
        try:
            shot = capture.grab_region(*st["rect"], cursor=self._cursor())
            self.pipeline.run_async(self.pipeline.process_image, shot.image, "Auto capture", "", st["ov"])
        except Exception as e:  # noqa
            self.notify("Auto capture", str(e), error=True)
        st["n"] += 1
        if st["max"] and st["n"] >= st["max"]:
            self._auto_stop()
            return False
        return True

    def _auto_stop(self):
        st, self.auto_state = self.auto_state, None
        if st and st.get("src"):
            GLib.source_remove(st["src"])
        if st:
            self.notify("Auto capture stopped", f"{st['n']} screenshots")

    # ---------------------------------------------------------- recording
    def act_record_screen(self, ov=None, gif=False):
        if self.recorder.running:
            return self._stop_recording()
        area = self.config.get("recording.area", "region")

        def start(rect, title=""):
            cfg = dict(self.config.get("recording"))
            cfg["_dir"] = self.config.video_dir()
            try:
                self.recorder.start(capture.to_device(rect), cfg, gif=gif, title=title)   # ffmpeg works in device pixels
            except RecorderError as e:
                self.notify("Recording failed", str(e), error=True)
                return
            from .ui.recbar import RecordingBar
            self.rec_gif = gif
            self.rec_ov = ov
            self.rec_bar = RecordingBar(self._stop_recording, rect, gif)
            if self.tray:
                self.tray.set_recording(True)
        if area == "fullscreen":
            self._after_delay(lambda h: (self._restore_windows(h), start(capture.virtual_screen())))
        elif area == "monitor":
            def mon(h):
                self._restore_windows(h)
                m = capture.monitor_at_pointer()
                start((m["x"], m["y"], m["w"], m["h"]))
            self._after_delay(mon)
        elif area == "window":
            wi = capture.active_window()
            self._after_delay(lambda h: (self._restore_windows(h), start(wi.rect if wi else capture.virtual_screen(), wi.title if wi else "")))
        else:
            self._select("region", lambda s, r, h: (self._restore_windows(h), r and start(tuple(int(v) for v in r))))

    def act_record_gif(self, ov=None):
        self.act_record_screen(ov, gif=True)

    def _stop_recording(self):
        if self.rec_bar:
            self.rec_bar.close_silently()
            self.rec_bar = None
        if self.tray:
            self.tray.set_recording(False)
        ov = getattr(self, "rec_ov", None)

        def job():
            path = self.recorder.stop()
            if path:
                self.pipeline.process_video(path, ov)
        self.pipeline.run_async(job)

    # ---------------------------------------------------------- upload actions
    def upload_image(self, img):
        self.pipeline.run_async(self.pipeline.process_image, img, "", "",
                                {"after_capture": {"upload": True, "editor": False, "copy_image": False}})

    def upload_files(self, files):
        def job():
            for f in files:
                self.pipeline.process_file(f)
        self.pipeline.run_async(job)

    def upload_text(self, text, filename=None):
        self.pipeline.run_async(self.pipeline.process_text, text, None, filename)

    def shorten_text(self, url):
        self.pipeline.run_async(self.pipeline.shorten_url, url)

    def act_upload_files(self, ov=None):
        files = C.choose_files(self.main, "Upload files", multiple=True)
        if files:
            self.upload_files(files)

    def act_upload_clipboard(self, ov=None):
        img = gfx.paste_image()
        if img is not None:
            return self.pipeline.run_async(self.pipeline.process_image, img, "Clipboard", "",
                                           {"after_capture": {"upload": True, "editor": False, "copy_image": False, "save": False}})
        files = gfx.paste_uris()
        if files:
            return self.upload_files(files)
        text = gfx.paste_text()
        if text:
            if text.strip().startswith(("http://", "https://")) and "\n" not in text.strip():
                return self.shorten_text(text.strip()) if C.ask(self.main, "Shorten this URL?", text.strip()) else self.upload_text(text)
            return self.upload_text(text)
        self.notify("Clipboard is empty", "Nothing to upload.", error=True)

    def act_upload_text(self, ov=None):
        d = Gtk.Dialog(title="Upload text", transient_for=self.main, modal=True)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Upload", Gtk.ResponseType.OK)
        tv = Gtk.TextView(monospace=True)
        sw = Gtk.ScrolledWindow()
        sw.set_size_request(520, 320)
        sw.add(tv)
        d.get_content_area().pack_start(sw, True, True, 8)
        d.show_all()
        text = None
        if d.run() == Gtk.ResponseType.OK:
            b = tv.get_buffer()
            text = b.get_text(b.get_start_iter(), b.get_end_iter(), False)
        d.destroy()
        if text and text.strip():
            self.upload_text(text)

    def _ask_line(self, title, placeholder):
        d = Gtk.Dialog(title=title, transient_for=self.main, modal=True)
        d.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
        e = Gtk.Entry(placeholder_text=placeholder, width_chars=52, activates_default=True)
        d.set_default_response(Gtk.ResponseType.OK)
        d.get_content_area().pack_start(e, True, True, 12)
        e.set_text(gfx.paste_text() or "" if (gfx.paste_text() or "").startswith("http") else "")
        d.show_all()
        v = e.get_text().strip() if d.run() == Gtk.ResponseType.OK else ""
        d.destroy()
        return v

    def act_upload_url(self, ov=None):
        url = self._ask_line("Upload from URL", "https://example.com/picture.png")
        if not url:
            return

        def job():
            import requests
            from urllib.parse import unquote, urlparse
            r = requests.get(url, timeout=60, headers={"User-Agent": uploaders.UA}, stream=True)
            r.raise_for_status()
            name = os.path.basename(unquote(urlparse(url).path)) or "download"
            d = tempfile.mkdtemp(prefix="mintshare-")
            p = os.path.join(d, name)
            with open(p, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
            try:
                self.pipeline.process_file(p)
            finally:
                shutil.rmtree(d, ignore_errors=True)
        self.pipeline.run_async(job)

    def act_shorten_url(self, ov=None):
        url = self._ask_line("Shorten URL", "https://example.com/very/long/link")
        if url:
            self.shorten_text(url)

    def act_drop_window(self, ov=None):
        from .ui.toolwins import DropWindow
        self._singleton("drop", DropWindow, self)

    # ---------------------------------------------------------- tools
    def pick_color(self, callback=None):
        def done(shot, res, hidden):
            self._restore_windows(hidden)
            if res:
                rgb = tuple(res[:3])
                hexv = core.color_formats(*rgb)["HEX"]
                gfx.copy_text(hexv)
                self.notify("Color picked", f"{hexv}  rgb{rgb} (copied)")
                (callback or self._color_into_window)(rgb)
        self._select("color", done, delay=0)

    def _color_into_window(self, rgb):
        from .ui.toolwins import ColorPickerWindow
        w = self._singleton("color", ColorPickerWindow, self)
        w.set_rgb(rgb)

    def act_color_picker(self, ov=None):
        self.pick_color()

    def act_color_window(self, ov=None):
        from .ui.toolwins import ColorPickerWindow
        self._singleton("color", ColorPickerWindow, self)

    def act_ruler(self, ov=None):
        self._select("ruler", lambda s, r, h: self._restore_windows(h), delay=0)

    def act_pin_region(self, ov=None):
        def done(shot, rect, hidden):
            self._restore_windows(hidden)
            if rect:
                s = self._crop(shot, rect)
                self.pin_image(s.image, s.x, s.y, 1.0 / s.scale)
        self._select("region", done)

    def act_pin_clipboard(self, ov=None):
        img = gfx.paste_image()
        if img:
            self.pin_image(img)
        else:
            self.notify("Clipboard has no image", "", error=True)

    def act_editor(self, ov=None):
        img = gfx.paste_image()
        if img is None or not C.ask(self.main, "Edit the image from the clipboard?", "Choose No to open a file instead."):
            p = C.choose_files(self.main, "Open image", filters=C.IMAGE_FILTER)
            if not p:
                return
            img = Image.open(p).convert("RGBA")
        self.open_editor(img)

    def _tool(self, key, mod, cls, *a):
        import importlib
        m = importlib.import_module("mintshare.ui." + mod)
        return self._singleton(key, getattr(m, cls), self, *a)

    def act_effects(self, ov=None):
        self._tool("effects", "toolwins", "EffectsWindow", gfx.paste_image())

    def act_combiner(self, ov=None): self._tool("combiner", "toolwins", "CombinerWindow")
    def act_splitter(self, ov=None): self._tool("splitter", "toolwins", "SplitterWindow")
    def act_thumbnailer(self, ov=None): self._tool("thumbnailer", "toolwins", "ThumbnailerWindow")
    def act_metadata(self, ov=None): self._tool("metadata", "toolwins", "MetaWindow")
    def act_video_converter(self, ov=None): self._tool("vconv", "toolwins", "VideoConvertWindow")
    def act_video_thumbs(self, ov=None): self._tool("vthumb", "toolwins", "VideoThumbWindow")
    def act_hash_check(self, ov=None): self._tool("hash", "toolwins", "HashWindow")
    def act_indexer(self, ov=None): self._tool("indexer", "toolwins", "IndexerWindow")
    def act_net_tools(self, ov=None): self._tool("net", "toolwins", "NetWindow")
    def act_monitor_test(self, ov=None): self._tool("mtest", "toolwins", "MonitorTest")

    def act_qr_generate(self, ov=None):
        t = gfx.paste_text() or ""
        self._tool("qr", "toolwins", "QRWindow", t[:2000])

    def act_qr_scan(self, ov=None):
        def done(shot, rect, hidden):
            self._restore_windows(hidden)
            if not rect:
                return
            img = self._crop(shot, rect).image

            def job():
                res = core.qr_decode(img)
                if res:
                    text = "\n".join(res)
                    self.ui.copy_text(text)
                    self.ui.notify("QR code read (copied)", text[:160])
                    self.ui.show_text("QR code content", text)
                else:
                    self.ui.notify("No QR code found", "", error=True)
            self.pipeline.run_async(job)
        self._select("region", done)

    # ---------------------------------------------------------- app actions
    def act_open_main(self, ov=None): self.show_main()
    def act_open_settings(self, ov=None): self.show_settings()

    def act_open_history(self, ov=None):
        from .ui.history import HistoryWindow
        self._singleton("history", HistoryWindow, self)

    def act_open_folder(self, ov=None):
        d = self.config.save_dir()
        os.makedirs(d, exist_ok=True)
        self.open_path(d)

    def act_quit(self, ov=None):
        if self.recorder.running:
            try:
                self.recorder.stop()
            except Exception:
                pass
        if self.xhotkeys:
            self.xhotkeys.stop()
        self.release()
        self.quit()

    # ---------------------------------------------------------- hotkeys
    def _autoapply_hotkeys(self):
        """Generic X11 hotkeys are activated automatically (they change no system settings);
        Cinnamon's own keybindings are only written when the user applies them."""
        backend = self.config.get("general.hotkey_backend", "auto")
        if backend == "auto":
            backend = "cinnamon" if hotkeys.is_cinnamon() else "xlib"
        if backend == "xlib":
            self._start_xlib()
        elif not self.config.get("general.hotkeys_applied"):
            self.notify("Set up hotkeys", "Open Settings → Hotkeys & workflows and press “Apply hotkeys”, "
                                           "or run: mintshare --apply-hotkeys")
        return False

    def _start_xlib(self):
        if self.xhotkeys is None:
            self.xhotkeys = hotkeys.XlibHotkeys(lambda name: GLib.idle_add(self.run_workflow, name))
        self.xhotkeys.start(self.config.get("workflows", []))

    def apply_hotkeys(self):
        wf = self.config.get("workflows", [])
        backend = self.config.get("general.hotkey_backend", "auto")
        if backend == "auto":
            backend = "cinnamon" if hotkeys.is_cinnamon() else "xlib"
        self.config.set("general.hotkeys_applied", True, save=False)
        self.config.set("general.hotkey_backend", backend)
        if backend == "cinnamon":
            n = hotkeys.apply_cinnamon(wf, self.config.get("general.take_over_print_screen", True))
            if self.xhotkeys:
                self.xhotkeys.stop()
            return f"{n} hotkeys registered with Cinnamon. They work even when the window is closed."
        ok = self._start_xlib()
        return (f"{sum(1 for w in wf if w.get('hotkey'))} hotkeys active while MintShare runs in the tray."
                if ok else (self.xhotkeys.error or "Hotkeys unavailable"))

    # ---------------------------------------------------------- tray menu & autostart
    def _make_tray(self):
        from .tray import Tray
        self.tray = Tray(self, self.build_menu)

    def build_menu(self):
        m = Gtk.Menu()

        def item(label, cb=None, parent=None):
            it = Gtk.MenuItem(label=label)
            if cb:
                it.connect("activate", lambda *_: cb())
            (parent or m).append(it)
            return it

        def sub(label):
            it = Gtk.MenuItem(label=label)
            s = Gtk.Menu()
            it.set_submenu(s)
            m.append(it)
            return s
        for cat in ("Capture", "Upload", "Tools"):
            s = sub(cat)
            for k, (label, c, _i) in actions.ACTIONS.items():
                if c == cat:
                    item(label, lambda k=k: self.run_action(k), s)
        for title, items, sect in (("After capture", actions.AFTER_CAPTURE, "after_capture"), ("After upload", actions.AFTER_UPLOAD, "after_upload")):
            s = sub(title)
            for k, label in items:
                ci = Gtk.CheckMenuItem(label=label)
                ci.set_active(bool(self.config.get(f"{sect}.{k}")))
                ci.connect("toggled", lambda w, p=f"{sect}.{k}": self.config.set(p, w.get_active()))
                s.append(ci)
        s = sub("Destinations")
        for cat, ucat, title in (("image", "image", "Images"), ("text", "text", "Text"), ("file", "file", "Files"), ("url_shortener", "shortener", "Shortener")):
            hdr = Gtk.MenuItem(label=f"— {title} —")
            hdr.set_sensitive(False)
            s.append(hdr)
            grp = None
            for uid, name in uploaders.choices(ucat, self.config.data):
                ri = Gtk.RadioMenuItem.new_with_label_from_widget(grp, name)
                grp = grp or ri
                ri.set_active(self.config.get(f"destinations.{cat}") == uid)
                ri.connect("toggled", lambda w, c=cat, u=uid: self.config.set(f"destinations.{c}", u) if w.get_active() else None)
                s.append(ri)
        m.append(Gtk.SeparatorMenuItem())
        item("Open screenshots folder", lambda: self.run_action("open_folder"))
        item("History", lambda: self.run_action("open_history"))
        item("Settings", lambda: self.run_action("open_settings"))
        item("Show MintShare", self.show_main)
        m.append(Gtk.SeparatorMenuItem())
        item("Quit", lambda: self.run_action("quit"))
        m.show_all()
        return m

    def _autostart_sync(self):
        want = self.config.get("general.autostart", False)
        f = paths.AUTOSTART_FILE
        if want:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f, "w") as fh:
                fh.write("[Desktop Entry]\nType=Application\nName=MintShare\nComment=Screenshot and upload tool\n"
                         f"Exec={hotkeys.launcher_command()} --minimized\nIcon=applets-screenshooter\n"
                         "X-GNOME-Autostart-enabled=true\nTerminal=false\n")
        elif os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass


def main(argv=None):
    app = MintShare()
    return app.run(argv if argv is not None else sys.argv)
