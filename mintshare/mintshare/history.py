"""Upload / capture history stored in SQLite."""
import os
import sqlite3
import threading
import time

from . import paths

SCHEMA = """CREATE TABLE IF NOT EXISTS history(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, filename TEXT, filepath TEXT,
  url TEXT, thumb_url TEXT, delete_url TEXT, host TEXT, title TEXT, size INTEGER)"""


class History:
    def __init__(self, path=None, max_entries=5000):
        self.path = path or paths.HISTORY_DB
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.max_entries = max_entries
        self.lock = threading.Lock()
        with self._conn() as c:
            c.execute(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.path, timeout=10)

    def add(self, kind, filename="", filepath="", url="", thumb_url="", delete_url="", host="", title=""):
        size = os.path.getsize(filepath) if filepath and os.path.exists(filepath) else 0
        with self.lock, self._conn() as c:
            cur = c.execute(
                "INSERT INTO history(ts,kind,filename,filepath,url,thumb_url,delete_url,host,title,size)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (time.time(), kind, filename, filepath, url, thumb_url, delete_url, host, title, size))
            c.execute("DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT ?)",
                      (self.max_entries,))
            return cur.lastrowid

    def list(self, search="", kind=None, only_uploaded=False, limit=1000):
        q = "SELECT id,ts,kind,filename,filepath,url,thumb_url,delete_url,host,title,size FROM history WHERE 1=1"
        args = []
        if search:
            q += " AND (filename LIKE ? OR url LIKE ? OR title LIKE ? OR host LIKE ?)"
            args += [f"%{search}%"] * 4
        if kind:
            q += " AND kind=?"
            args.append(kind)
        if only_uploaded:
            q += " AND url<>''"
        q += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            cols = ["id", "ts", "kind", "filename", "filepath", "url", "thumb_url", "delete_url", "host", "title", "size"]
            return [dict(zip(cols, r)) for r in c.execute(q, args)]

    def delete(self, entry_id):
        with self.lock, self._conn() as c:
            c.execute("DELETE FROM history WHERE id=?", (entry_id,))

    def clear(self):
        with self.lock, self._conn() as c:
            c.execute("DELETE FROM history")
