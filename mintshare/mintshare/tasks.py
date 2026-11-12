"""After-capture / after-upload pipeline (runs in a worker thread, UI work is delegated to ``ui``)."""
import io
import logging
import os
import tempfile
import threading
import traceback

from PIL import Image

from . import effects, naming, uploaders

log = logging.getLogger("mintshare")

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".ico"}
TEXT_EXT = {".txt", ".md", ".log", ".json", ".xml", ".csv", ".py", ".sh", ".c", ".h", ".cpp", ".js", ".html", ".css",
            ".yml", ".yaml", ".ini", ".conf", ".java", ".rs", ".go", ".ts"}


class NullUI:
    """Interface the pipeline uses; the GTK app implements these on the main thread."""
    def edit(self, img, title=""): return img          # returns edited image or None if cancelled
    def copy_image(self, img): pass
    def copy_text(self, text): pass
    def pin(self, img): pass
    def show_text(self, title, text): pass
    def show_qr(self, text): pass
    def print_image(self, img): pass
    def save_as(self, suggested): return suggested
    def open_path(self, path): pass
    def open_url(self, url): pass
    def notify(self, title, body="", path=None, url=None, error=False): pass
    def play_sound(self): pass
    def ocr(self, img): return ""
    def busy(self, delta): pass


def encode_image(img: Image.Image, fmt: str, cfg: dict) -> tuple[bytes, str]:
    fmt = fmt.lower()
    buf = io.BytesIO()
    if fmt in ("jpg", "jpeg"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").getchannel("A"))
        bg.save(buf, "JPEG", quality=int(cfg.get("jpg_quality", 90)), optimize=True)
        ext = "jpg"
    elif fmt == "webp":
        img.save(buf, "WEBP", quality=int(cfg.get("webp_quality", 90)))
        ext = "webp"
    elif fmt == "bmp":
        img.convert("RGB").save(buf, "BMP"); ext = "bmp"
    elif fmt in ("tif", "tiff"):
        img.save(buf, "TIFF"); ext = "tiff"
    elif fmt == "gif":
        img.convert("P", palette=Image.ADAPTIVE).save(buf, "GIF"); ext = "gif"
    else:
        img.save(buf, "PNG", optimize=True); ext = "png"
    data = buf.getvalue()
    limit = int(cfg.get("auto_jpg_over_kb", 0) or 0)
    if ext == "png" and limit and len(data) > limit * 1024:
        return encode_image(img, "jpg", cfg)
    return data, ext


class Pipeline:
    def __init__(self, config, history, ui):
        self.config, self.history, self.ui = config, history, ui

    # ------------------------------------------------------------ public entry points (thread-safe)
    def run_async(self, fn, *a, **kw):
        def worker():
            self.ui.busy(+1)
            try:
                fn(*a, **kw)
            except uploaders.UploadError as e:
                self.ui.notify("Upload failed", str(e), error=True)
            except Exception as e:  # noqa
                log.error("task failed: %s", traceback.format_exc())
                self.ui.notify("MintShare error", f"{type(e).__name__}: {e}", error=True)
            finally:
                self.ui.busy(-1)
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return t

    # ------------------------------------------------------------ images
    def process_image(self, img, title="", process="", overrides=None, kind="image"):
        s = self.config.effective(overrides)
        ac, au, icfg = s["after_capture"], s["after_upload"], s["image"]
        self.ui.play_sound()
        if ac.get("effects"):
            img = effects.apply_configured(img, s["effects"])
        if ac.get("editor"):
            img = self.ui.edit(img, title)
            if img is None:
                return None
        name = naming.format_name(icfg["filename"], title, process)
        data, ext = encode_image(img, icfg.get("format", "png"), icfg)
        filename = f"{name}.{ext}"
        if ac.get("copy_image"):
            self.ui.copy_image(img)
        path = None
        if ac.get("save_as"):
            chosen = self.ui.save_as(os.path.join(self.config.save_dir(), filename))
            if chosen:
                path = chosen
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "wb").write(data)
        if ac.get("save") and not path:
            d = os.path.join(self.config.save_dir(), naming.format_name(icfg.get("subfolder", ""), title, process)
                             if icfg.get("subfolder") else "")
            os.makedirs(d, exist_ok=True)
            path = naming.unique_path(os.path.join(d, filename))
            with open(path, "wb") as f:
                f.write(data)
        result = None
        tmp = None
        if ac.get("upload"):
            send = path
            if not send:
                tmp = os.path.join(tempfile.mkdtemp(prefix="mintshare-"), filename)
                open(tmp, "wb").write(data)
                send = tmp
            result = self._upload_path(send, filename, "image", s, au)
        if ac.get("pin"):
            self.ui.pin(img)
        if ac.get("print"):
            self.ui.print_image(img)
        if ac.get("ocr"):
            text = self.ui.ocr(img)
            if text:
                self.ui.copy_text(text)
        if ac.get("open_file") and path:
            self.ui.open_path(path)
        if ac.get("open_folder") and path:
            self.ui.open_path(os.path.dirname(path))
        if tmp:
            _rm(tmp)
        if ac.get("delete_after_upload") and result and path:
            _rm(path, keep_dir=True)
            path = None
        self._record(kind, filename, path or "", result, title)
        self._finish(result, path, filename, "Screenshot")
        return path, result

    # ------------------------------------------------------------ files / text / url
    def process_file(self, path, overrides=None):
        s = self.config.effective(overrides)
        ext = os.path.splitext(path)[1].lower()
        cat = "image" if ext in IMAGE_EXT else "text" if ext in TEXT_EXT else "file"
        filename = os.path.basename(path)
        result = self._upload_path(path, filename, cat, s, s["after_upload"])
        self._record(cat, filename, path, result)
        self._finish(result, path, filename, "Upload")
        return result

    def process_text(self, text, overrides=None, filename=None):
        s = self.config.effective(overrides)
        name = filename or naming.format_name(s["image"]["text_filename"]) + ".txt"
        d = tempfile.mkdtemp(prefix="mintshare-")
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            result = self._upload_path(p, name, "text", s, s["after_upload"])
            self._record("text", name, "", result)
            self._finish(result, None, name, "Text upload")
            return result
        finally:
            _rm(p)

    def shorten_url(self, url, overrides=None):
        s = self.config.effective(overrides)
        short = self._shorten(url, s)
        self._after_url(short, s["after_upload"], shorten=False)
        self.history.add("url", filename=url, url=short, host="shortener") if self.config.get("history.enabled") else None
        self.ui.notify("URL shortened", short, url=short)
        return short

    def process_video(self, path, overrides=None):
        s = self.config.effective(overrides)
        ar = s["recording"]["after_record"]
        result = None
        if ar.get("copy_path"):
            self.ui.copy_text(path)
        if ar.get("upload"):
            result = self._upload_path(path, os.path.basename(path), "file", s, s["after_upload"])
        if ar.get("open_folder"):
            self.ui.open_path(os.path.dirname(path))
        self._record("video", os.path.basename(path), path, result)
        self._finish(result, path, os.path.basename(path), "Recording saved")

    # ------------------------------------------------------------ internals
    def _upload_path(self, path, filename, category, s, au):
        dest = s["destinations"].get({"image": "image", "text": "text", "file": "file"}[category])
        up = uploaders.get(dest, s)
        res = up.upload(path, filename)
        res.host = res.host or up.name
        self._after_url(res, au, shorten=au.get("shorten"), settings=s)
        return res

    def _shorten(self, url, s):
        return uploaders.get(s["destinations"]["url_shortener"], s).shorten(url)

    def _after_url(self, res, au, shorten=False, settings=None):
        is_res = hasattr(res, "url")
        url = res.url if is_res else res
        if shorten and url:
            try:
                short = self._shorten(url, settings or self.config.data)
                if is_res:
                    res.url = short
                url = short
            except uploaders.UploadError as e:
                self.ui.notify("URL shortener failed", str(e), error=True)
        if au.get("copy_url") and url:
            self.ui.copy_text(url)
        if au.get("open_url") and url:
            self.ui.open_url(url)
        if au.get("show_qr") and url:
            self.ui.show_qr(url)

    def _record(self, kind, filename, path, result, title=""):
        if not self.config.get("history.enabled", True):
            return
        self.history.add(kind, filename=filename, filepath=path or "", url=result.url if result else "",
                         thumb_url=result.thumb_url if result else "", delete_url=result.delete_url if result else "",
                         host=result.host if result else "", title=title)

    def _finish(self, result, path, filename, title):
        if result:
            self.ui.notify(f"{title} uploaded", result.url, path=path, url=result.url)
        elif path:
            self.ui.notify(f"{title} saved", path, path=path)
        else:
            self.ui.notify(f"{title} done", filename)


def _rm(p, keep_dir=False):
    try:
        os.remove(p)
        if not keep_dir:
            os.rmdir(os.path.dirname(p))
    except OSError:
        pass
