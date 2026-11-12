"""GUI-independent logic of the MintShare tools."""
import colorsys
import hashlib
import html
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import zlib
from datetime import datetime

from PIL import Image


# ---------------------------------------------------------------- colours
def color_formats(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    hh, ll, ss = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    k = 1 - max(r, g, b) / 255
    c = m = y = 0.0
    if k < 1:
        c, m, y = [(1 - x / 255 - k) / (1 - k) for x in (r, g, b)]
    return {
        "HEX": f"#{r:02X}{g:02X}{b:02X}",
        "RGB": f"rgb({r}, {g}, {b})",
        "HSL": f"hsl({hh * 360:.0f}, {ss * 100:.0f}%, {ll * 100:.0f}%)",
        "HSV": f"hsv({h * 360:.0f}, {s * 100:.0f}%, {v * 100:.0f}%)",
        "CMYK": f"cmyk({c * 100:.0f}%, {m * 100:.0f}%, {y * 100:.0f}%, {k * 100:.0f}%)",
        "Decimal": str((r << 16) + (g << 8) + b),
        "Android ARGB": f"0xFF{r:02X}{g:02X}{b:02X}",
    }


def parse_color(text):
    t = text.strip()
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", t)
    if m:
        v = int(m.group(1), 16)
        return (v >> 16, (v >> 8) & 255, v & 255)
    m = re.fullmatch(r"#?([0-9a-fA-F]{3})", t)
    if m:
        return tuple(int(c * 2, 16) for c in m.group(1))
    m = re.fullmatch(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", t)
    if m:
        return tuple(min(255, int(x)) for x in m.groups())
    raise ValueError("Unrecognised colour")


# ---------------------------------------------------------------- OCR
def ocr_languages():
    exe = shutil.which("tesseract")
    if not exe:
        return []
    out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True).stdout.splitlines()[1:]
    return [l.strip() for l in out if l.strip()]


def ocr_image(img: Image.Image, lang="eng"):
    exe = shutil.which("tesseract")
    if not exe:
        raise RuntimeError("OCR needs Tesseract: sudo apt install tesseract-ocr (add tesseract-ocr-nld for Dutch)")
    d = tempfile.mkdtemp(prefix="mintshare-ocr-")
    try:
        p = os.path.join(d, "in.png")
        big = img.convert("RGB")
        if big.width < 1000:  # tesseract does much better on larger text
            f = max(1, 1500 // big.width)
            big = big.resize((big.width * f, big.height * f), Image.LANCZOS)
        big.save(p)
        r = subprocess.run([exe, p, "stdout", "-l", lang, "--psm", "6"], capture_output=True, text=True, timeout=120)
        if r.returncode:
            raise RuntimeError(r.stderr.strip()[:300])
        return r.stdout.strip()
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------- QR
def qr_make(text, size=8, border=2, ec="M"):
    import qrcode
    lv = {"L": qrcode.constants.ERROR_CORRECT_L, "M": qrcode.constants.ERROR_CORRECT_M,
          "Q": qrcode.constants.ERROR_CORRECT_Q, "H": qrcode.constants.ERROR_CORRECT_H}[ec]
    q = qrcode.QRCode(error_correction=lv, box_size=size, border=border)
    q.add_data(text)
    q.make(fit=True)
    return q.make_image(fill_color="black", back_color="white").convert("RGBA")


def qr_decode(img: Image.Image):
    """Decode QR/bar codes from a PIL image using zbarimg, pyzbar or OpenCV (whichever exists)."""
    try:
        from pyzbar.pyzbar import decode
        res = [d.data.decode("utf-8", "replace") for d in decode(img.convert("RGB"))]
        if res:
            return res
    except ImportError:
        pass
    exe = shutil.which("zbarimg")
    if exe:
        d = tempfile.mkdtemp(prefix="mintshare-qr-")
        try:
            p = os.path.join(d, "q.png")
            img.convert("RGB").save(p)
            r = subprocess.run([exe, "-q", "--raw", p], capture_output=True, text=True, timeout=30)
            return [l for l in r.stdout.splitlines() if l]
        finally:
            shutil.rmtree(d, ignore_errors=True)
    try:
        import cv2
        import numpy as np
        val, _, _ = cv2.QRCodeDetector().detectAndDecode(np.array(img.convert("RGB")))
        return [val] if val else []
    except ImportError:
        raise RuntimeError("QR scanning needs a decoder: sudo apt install zbar-tools")


# ---------------------------------------------------------------- hashing
ALGOS = ["md5", "sha1", "sha256", "sha384", "sha512", "sha3_256", "blake2b", "crc32"]


def hash_file(path, algo="sha256", progress=None, chunk=1 << 20):
    size = os.path.getsize(path) or 1
    done = 0
    h = zlib.crc32(b"") if algo == "crc32" else hashlib.new(algo)
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h = zlib.crc32(b, h) if algo == "crc32" else (h.update(b) or h)
            done += len(b)
            if progress:
                progress(done / size)
    return f"{h & 0xffffffff:08x}" if algo == "crc32" else h.hexdigest()


def hash_text(text, algo="sha256"):
    if algo == "crc32":
        return f"{zlib.crc32(text.encode()) & 0xffffffff:08x}"
    return hashlib.new(algo, text.encode()).hexdigest()


# ---------------------------------------------------------------- directory indexer
def _human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def index_directory(root, fmt="html", recursive=True, include_hidden=False):
    root = os.path.abspath(root)
    rows = []
    for dp, dns, fns in os.walk(root):
        if not include_hidden:
            dns[:] = sorted(d for d in dns if not d.startswith("."))
            fns = [f for f in fns if not f.startswith(".")]
        else:
            dns.sort()
        depth = os.path.relpath(dp, root).count(os.sep) + (0 if dp == root else 1)
        if dp != root:
            rows.append((depth - 1, os.path.basename(dp), True, 0, dp))
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            rows.append((depth, fn, False, os.path.getsize(p), p))
        if not recursive:
            break
    if fmt == "txt":
        return "\n".join("  " * d + (n + "/" if isdir else f"{n}  ({_human(s)})") for d, n, isdir, s, _ in rows)
    if fmt == "md":
        return f"# Index of {os.path.basename(root)}\n\n" + "\n".join(
            "  " * d + "- " + (f"**{n}/**" if isdir else f"{n} — {_human(s)}") for d, n, isdir, s, _ in rows)
    items = "\n".join(
        f'<li style="margin-left:{d * 18}px">' + (f"<b>📁 {html.escape(n)}</b>" if isdir else
        f'📄 <a href="{html.escape(os.path.relpath(p, root))}">{html.escape(n)}</a> <small>{_human(s)}</small>') + "</li>"
        for d, n, isdir, s, p in rows)
    return (f"<!doctype html><meta charset=utf-8><title>Index of {html.escape(root)}</title>"
            f"<style>body{{font:15px system-ui;margin:2em}}li{{list-style:none;margin:3px 0}}small{{color:#888}}</style>"
            f"<h1>Index of {html.escape(os.path.basename(root))}</h1><ul>{items}</ul>")


# ---------------------------------------------------------------- metadata
def image_metadata(path):
    from PIL import ExifTags
    out = {}
    im = Image.open(path)
    out["Format"] = im.format or ""
    out["Size"] = f"{im.width} × {im.height}"
    out["Mode"] = im.mode
    out["File size"] = _human(os.path.getsize(path))
    out["Modified"] = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
    for k, v in (im.info or {}).items():
        if isinstance(v, (str, int, float)) and k not in ("exif",):
            out[f"Info: {k}"] = str(v)[:200]
    try:
        exif = im.getexif()
        for tag, val in exif.items():
            out["EXIF: " + ExifTags.TAGS.get(tag, str(tag))] = str(val)[:200]
        for tag, val in exif.get_ifd(0x8769).items():
            out["EXIF: " + ExifTags.TAGS.get(tag, str(tag))] = str(val)[:200]
    except Exception:
        pass
    return out


def strip_metadata(src, dst):
    im = Image.open(src)
    clean = Image.new(im.mode, im.size)
    clean.putdata(list(im.getdata()))
    clean.save(dst)


# ---------------------------------------------------------------- network
def ping(host, count=4, timeout=15):
    exe = shutil.which("ping")
    if not exe:
        raise RuntimeError("ping is not installed")
    r = subprocess.run([exe, "-c", str(count), "-W", "3", host], capture_output=True, text=True, timeout=timeout + count * 3)
    return (r.stdout + r.stderr).strip()


def dns_lookup(host):
    lines = []
    try:
        for fam, _, _, _, sa in socket.getaddrinfo(host, None):
            lines.append(f"{'IPv6' if fam == socket.AF_INET6 else 'IPv4'}  {sa[0]}")
        lines = sorted(set(lines))
    except socket.gaierror as e:
        lines.append(f"Lookup failed: {e}")
    dig = shutil.which("dig")
    if dig:
        for rtype in ("MX", "TXT", "NS"):
            r = subprocess.run([dig, "+short", rtype, host], capture_output=True, text=True, timeout=10)
            if r.stdout.strip():
                lines.append(f"\n{rtype}:\n" + r.stdout.strip())
    return "\n".join(dict.fromkeys(lines))


# ---------------------------------------------------------------- video
def _ff():
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg is not installed: sudo apt install ffmpeg")
    return exe


FORMATS = {
    "mp4 (H.264)": (".mp4", ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"]),
    "webm (VP9)": (".webm", ["-c:v", "libvpx-vp9", "-b:v", "0", "-c:a", "libopus"]),
    "mkv (H.264)": (".mkv", ["-c:v", "libx264", "-c:a", "aac"]),
    "gif": (".gif", ["-vf", "fps=15,scale='min(960,iw)':-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse", "-loop", "0"]),
    "mp3 (audio only)": (".mp3", ["-vn", "-c:a", "libmp3lame", "-q:a", "2"]),
    "wav (audio only)": (".wav", ["-vn"]),
}


def convert_video(src, fmt_name, out=None, crf=23, scale_width=None, progress_cb=None):
    ext, args = FORMATS[fmt_name]
    out = out or os.path.splitext(src)[0] + "_converted" + ext
    cmd = [_ff(), "-hide_banner", "-loglevel", "error", "-y", "-i", src]
    if ext in (".mp4", ".mkv"):
        cmd += ["-crf", str(crf)]
    if scale_width and ext != ".gif" and "-vn" not in args:
        cmd += ["-vf", f"scale={scale_width}:-2"]
    cmd += args + [out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[-400:])
    return out


def video_duration(src):
    r = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", src], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def video_thumbnails(src, count=9, columns=3, width=480):
    """Extract evenly spaced frames and return a contact-sheet PIL image."""
    from . import _sheet
    dur = video_duration(src) or 1
    frames = []
    d = tempfile.mkdtemp(prefix="mintshare-vt-")
    try:
        for i in range(count):
            t = dur * (i + 0.5) / count
            p = os.path.join(d, f"{i}.png")
            subprocess.run([_ff(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", src,
                            "-frames:v", "1", "-vf", f"scale={width}:-1", p], capture_output=True)
            if os.path.exists(p):
                frames.append((t, Image.open(p).convert("RGB").copy()))
        return _sheet.contact_sheet(frames, columns, os.path.basename(src), dur)
    finally:
        shutil.rmtree(d, ignore_errors=True)
