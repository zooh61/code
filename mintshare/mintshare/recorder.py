"""Screen recording (MP4/WebM/MKV) and GIF capture through ffmpeg x11grab."""
import os
import shutil
import subprocess
import tempfile
import threading
import time

from . import naming


class RecorderError(Exception):
    pass


def have_ffmpeg():
    return shutil.which("ffmpeg") is not None


def build_command(rect, out, fps=30, draw_cursor=True, audio=False, audio_source="default", codec="libx264",
                  crf=23, display=None):
    x, y, w, h = [int(v) for v in rect]
    w -= w % 2
    h -= h % 2
    if w < 16 or h < 16:
        raise RecorderError("The recording area is too small.")
    display = display or os.environ.get("DISPLAY", ":0")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "x11grab", "-framerate", str(fps),
           "-draw_mouse", "1" if draw_cursor else "0", "-video_size", f"{w}x{h}", "-i", f"{display}+{x},{y}"]
    if audio:
        cmd += ["-f", "pulse", "-i", audio_source]
    ext = os.path.splitext(out)[1].lower()
    if ext == ".webm":
        cmd += ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(crf + 8), "-deadline", "realtime", "-cpu-used", "8"]
        if audio:
            cmd += ["-c:a", "libopus"]
    else:
        cmd += ["-c:v", codec, "-preset", "ultrafast", "-crf", str(crf), "-pix_fmt", "yuv420p"]
        if audio:
            cmd += ["-c:a", "aac", "-b:a", "160k"]
    cmd.append(out)
    return cmd


def gif_command(src, out, fps=15, max_width=960):
    vf = (f"fps={fps},scale='min({max_width},iw)':-1:flags=lanczos,split[s0][s1];"
          "[s0]palettegen=stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4")
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-vf", vf, "-loop", "0", out]


class Recorder:
    def __init__(self):
        self.proc = None
        self.out = None
        self.gif = False
        self.started = 0.0
        self._tmp = None

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    @property
    def elapsed(self):
        return time.time() - self.started if self.running else 0.0

    def start(self, rect, rec_cfg: dict, gif=False, title=""):
        if not have_ffmpeg():
            raise RecorderError("ffmpeg is not installed. Run: sudo apt install ffmpeg")
        if self.running:
            raise RecorderError("Already recording.")
        self.gif = gif
        outdir = rec_cfg.get("_dir")
        os.makedirs(outdir, exist_ok=True)
        base = naming.format_name(rec_cfg.get("filename", "Recording_%y-%mo-%d_%h-%mi-%s"), title)
        ext = "gif" if gif else rec_cfg.get("container", "mp4")
        self.out = naming.unique_path(os.path.join(outdir, f"{base}.{ext}"))
        if gif:
            self._tmp = tempfile.mkdtemp(prefix="mintshare-gif-")
            rec_path = os.path.join(self._tmp, "raw.mkv")
            cmd = build_command(rect, rec_path, fps=max(rec_cfg.get("gif_fps", 15), 15),
                                draw_cursor=rec_cfg.get("draw_cursor", True), codec="libx264", crf=18)
            self._raw = rec_path
        else:
            cmd = build_command(rect, self.out, rec_cfg.get("fps", 30), rec_cfg.get("draw_cursor", True),
                                rec_cfg.get("audio", False), rec_cfg.get("audio_source", "default"),
                                rec_cfg.get("codec", "libx264"), rec_cfg.get("crf", 23))
        self._cfg = rec_cfg
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
        self.started = time.time()
        time.sleep(0.4)
        if self.proc.poll() is not None:
            err = self.proc.stderr.read().decode(errors="replace")[-400:]
            self.proc = None
            raise RecorderError("ffmpeg failed to start: " + err)

    def stop(self):
        """Stop recording and return the output path (for GIFs this blocks while converting)."""
        if self.proc is None:
            return None
        p, self.proc = self.proc, None
        try:
            p.stdin.write(b"q")
            p.stdin.flush()
        except (OSError, ValueError):
            pass
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.terminate()
            p.wait(timeout=5)
        if self.gif:
            try:
                r = subprocess.run(gif_command(self._raw, self.out, self._cfg.get("gif_fps", 15),
                                               self._cfg.get("gif_max_width", 960)), capture_output=True, timeout=600)
                if r.returncode:
                    raise RecorderError("GIF conversion failed: " + r.stderr.decode(errors="replace")[-300:])
            finally:
                shutil.rmtree(self._tmp, ignore_errors=True)
        if not os.path.exists(self.out) or os.path.getsize(self.out) == 0:
            raise RecorderError("The recording is empty (was it stopped immediately?).")
        return self.out
