"""ShareX-style file name patterns, e.g. ``Screenshot_%y-%mo-%d_%h-%mi-%s``."""
import getpass
import os
import random
import re
import socket
import string
import uuid
from datetime import datetime

_TOKEN = re.compile(r"%(guid|mon|mo|mi|ms|yy|y|w|pn|rn\d*|ra\d*|un|cn|d|h|s|t|i)")
_counter = {"n": 0}
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def format_name(pattern: str, title: str = "", process: str = "", now: datetime | None = None,
                counter: int | None = None) -> str:
    now = now or datetime.now()
    if counter is None:
        _counter["n"] += 1
        counter = _counter["n"]

    def sub(m):
        t = m.group(1)
        if t == "guid": return str(uuid.uuid4())
        if t == "mon": return now.strftime("%B")
        if t == "mo": return f"{now.month:02d}"
        if t == "mi": return f"{now.minute:02d}"
        if t == "ms": return f"{now.microsecond // 1000:03d}"
        if t == "yy": return f"{now.year % 100:02d}"
        if t == "y": return str(now.year)
        if t == "w": return now.strftime("%A")
        if t == "pn": return process or "Unknown"
        if t.startswith("rn"):
            n = int(t[2:] or 8)
            return "".join(random.choice(string.digits) for _ in range(n))
        if t.startswith("ra"):
            n = int(t[2:] or 8)
            return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(n))
        if t == "un": return getpass.getuser()
        if t == "cn": return socket.gethostname()
        if t == "d": return f"{now.day:02d}"
        if t == "h": return f"{now.hour:02d}"
        if t == "s": return f"{now.second:02d}"
        if t == "t": return title or "Screenshot"
        if t == "i": return str(counter)
        return m.group(0)

    return sanitize(_TOKEN.sub(sub, pattern))


def sanitize(name: str, maxlen: int = 120) -> str:
    name = _BAD.sub("_", name).strip().strip(".")
    return (name[:maxlen] or "file")


def unique_path(path: str) -> str:
    """Return ``path`` or ``path (2)`` etc. so nothing is overwritten."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"
