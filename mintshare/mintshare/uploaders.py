"""Upload destinations: built-in hosts, FTP/SFTP/WebDAV/S3/Dropbox, URL shorteners and
ShareX-compatible custom uploaders (.sxcu)."""
import base64
import datetime as _dt
import hashlib
import hmac
import json
import mimetypes
import os
import re
import shutil
import subprocess
import urllib.parse
from dataclasses import dataclass

import requests

from . import paths

UA = "MintShare/1.0 (+https://github.com/zooh61/code)"
TIMEOUT = 120


class UploadError(Exception):
    pass


@dataclass
class UploadResult:
    url: str
    thumb_url: str = ""
    delete_url: str = ""
    host: str = ""


def _mime(name):
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _check(resp, what=""):
    if resp.status_code >= 400:
        raise UploadError(f"{what or 'Server'} returned HTTP {resp.status_code}: {resp.text[:300]}")
    return resp


class Uploader:
    id = ""
    name = ""
    categories = ("image", "file")        # image | text | file | shortener
    fields = []                            # (key, label, kind[, default])
    help = ""

    def __init__(self, cfg=None):
        self.cfg = dict(cfg or {})

    def opt(self, key, default=""):
        for f in self.fields:
            if f[0] == key and len(f) > 3 and key not in self.cfg:
                return f[3]
        return self.cfg.get(key, default)

    def need(self, *keys):
        missing = [k for k in keys if not self.opt(k)]
        if missing:
            raise UploadError(f"{self.name}: please fill in {', '.join(missing)} under Destinations.")

    def upload(self, path, filename=None) -> UploadResult:
        raise NotImplementedError

    def upload_bytes(self, data: bytes, filename: str) -> UploadResult:
        import tempfile
        d = tempfile.mkdtemp(prefix="mintshare-")
        p = os.path.join(d, filename)
        with open(p, "wb") as f:
            f.write(data)
        try:
            return self.upload(p, filename)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def shorten(self, url) -> str:
        raise UploadError(f"{self.name} cannot shorten URLs")


# ---------------------------------------------------------------- public hosts
class Imgur(Uploader):
    id, name, categories = "imgur", "Imgur", ("image",)
    fields = [("client_id", "Client ID (register an app at api.imgur.com)", "text"),
              ("access_token", "Access token (optional, uploads to your account)", "password")]

    def upload(self, path, filename=None):
        self.need("client_id")
        filename = filename or os.path.basename(path)
        headers = {"Authorization": f"Client-ID {self.opt('client_id')}", "User-Agent": UA}
        if self.opt("access_token"):
            headers["Authorization"] = f"Bearer {self.opt('access_token')}"
        r = requests.post("https://api.imgur.com/3/image", headers=headers,
                          files={"image": (filename, _read(path), _mime(filename))}, timeout=TIMEOUT)
        _check(r, "Imgur")
        d = r.json()["data"]
        return UploadResult(d["link"], delete_url=f"https://imgur.com/delete/{d.get('deletehash', '')}", host="Imgur")


class Catbox(Uploader):
    id, name, categories = "catbox", "Catbox.moe (anonymous)", ("image", "text", "file")
    fields = [("userhash", "User hash (optional)", "text")]

    def upload(self, path, filename=None):
        filename = filename or os.path.basename(path)
        r = requests.post("https://catbox.moe/user/api.php",
                          data={"reqtype": "fileupload", "userhash": self.opt("userhash")},
                          files={"fileToUpload": (filename, _read(path), _mime(filename))},
                          headers={"User-Agent": UA}, timeout=TIMEOUT)
        _check(r, "Catbox")
        if not r.text.startswith("http"):
            raise UploadError("Catbox: " + r.text[:200])
        return UploadResult(r.text.strip(), host="Catbox")


class Litterbox(Uploader):
    id, name, categories = "litterbox", "Litterbox (temporary)", ("image", "text", "file")
    fields = [("time", "Keep for", "choice:1h,12h,24h,72h", "24h")]

    def upload(self, path, filename=None):
        filename = filename or os.path.basename(path)
        r = requests.post("https://litterbox.catbox.moe/resources/internals/api.php",
                          data={"reqtype": "fileupload", "time": self.opt("time", "24h")},
                          files={"fileToUpload": (filename, _read(path), _mime(filename))},
                          headers={"User-Agent": UA}, timeout=TIMEOUT)
        _check(r, "Litterbox")
        return UploadResult(r.text.strip(), host="Litterbox")


class ZeroX0(Uploader):
    id, name, categories = "0x0.st", "0x0.st", ("image", "text", "file")

    def upload(self, path, filename=None):
        filename = filename or os.path.basename(path)
        r = requests.post("https://0x0.st", files={"file": (filename, _read(path), _mime(filename))},
                          headers={"User-Agent": UA}, timeout=TIMEOUT)
        _check(r, "0x0.st")
        return UploadResult(r.text.strip(), host="0x0.st")


class PasteRs(Uploader):
    id, name, categories = "paste.rs", "paste.rs", ("text",)

    def upload(self, path, filename=None):
        r = requests.post("https://paste.rs", data=_read(path), headers={"User-Agent": UA}, timeout=TIMEOUT)
        _check(r, "paste.rs")
        return UploadResult(r.text.strip(), host="paste.rs")


class Dpaste(Uploader):
    id, name, categories = "dpaste", "dpaste.org", ("text",)
    fields = [("expires", "Expire after (seconds)", "int", 86400 * 7)]

    def upload(self, path, filename=None):
        r = requests.post("https://dpaste.org/api/", data={"content": _read(path).decode("utf-8", "replace"),
                          "expiry_days": max(1, int(self.opt("expires", 604800)) // 86400)},
                          headers={"User-Agent": UA}, timeout=TIMEOUT)
        _check(r, "dpaste")
        return UploadResult(r.text.strip().strip('"'), host="dpaste.org")


class Pastebin(Uploader):
    id, name, categories = "pastebin", "Pastebin.com", ("text",)
    fields = [("dev_key", "API dev key", "password"), ("user_key", "User key (optional)", "password"),
              ("private", "Visibility", "choice:public,unlisted,private", "unlisted"),
              ("expire", "Expire", "choice:N,10M,1H,1D,1W,2W,1M,6M,1Y", "N")]

    def upload(self, path, filename=None):
        self.need("dev_key")
        vis = {"public": "0", "unlisted": "1", "private": "2"}[self.opt("private", "unlisted")]
        data = {"api_dev_key": self.opt("dev_key"), "api_option": "paste", "api_paste_private": vis,
                "api_paste_expire_date": self.opt("expire", "N"),
                "api_paste_name": filename or os.path.basename(path),
                "api_paste_code": _read(path).decode("utf-8", "replace")}
        if self.opt("user_key"):
            data["api_user_key"] = self.opt("user_key")
        r = requests.post("https://pastebin.com/api/api_post.php", data=data, timeout=TIMEOUT)
        _check(r, "Pastebin")
        if not r.text.startswith("http"):
            raise UploadError("Pastebin: " + r.text[:200])
        return UploadResult(r.text.strip(), host="Pastebin")


class Gist(Uploader):
    id, name, categories = "gist", "GitHub Gist", ("text",)
    fields = [("token", "Personal access token (gist scope)", "password"),
              ("public", "Public gist", "bool", False)]

    def upload(self, path, filename=None):
        self.need("token")
        filename = filename or os.path.basename(path)
        r = requests.post("https://api.github.com/gists", timeout=TIMEOUT,
                          headers={"Authorization": f"Bearer {self.opt('token')}", "User-Agent": UA},
                          json={"description": "Uploaded with MintShare", "public": bool(self.opt("public", False)),
                                "files": {filename: {"content": _read(path).decode("utf-8", "replace")}}})
        _check(r, "GitHub")
        j = r.json()
        return UploadResult(j["html_url"], delete_url=j["url"], host="GitHub Gist")


class Dropbox(Uploader):
    id, name, categories = "dropbox", "Dropbox", ("image", "text", "file")
    fields = [("token", "Access token", "password"), ("folder", "Folder", "text", "/MintShare"),
              ("direct", "Direct link (raw=1)", "bool", True)]

    def upload(self, path, filename=None):
        self.need("token")
        filename = filename or os.path.basename(path)
        folder = "/" + self.opt("folder", "/MintShare").strip("/")
        target = (folder if folder != "/" else "") + "/" + filename
        auth = {"Authorization": f"Bearer {self.opt('token')}"}
        r = requests.post("https://content.dropboxapi.com/2/files/upload", timeout=TIMEOUT, data=_read(path),
                          headers={**auth, "Content-Type": "application/octet-stream",
                                   "Dropbox-API-Arg": json.dumps({"path": target, "mode": "add", "autorename": True})})
        _check(r, "Dropbox")
        real = r.json()["path_display"]
        r = requests.post("https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings", headers=auth,
                          json={"path": real}, timeout=TIMEOUT)
        if r.status_code == 409 and "shared_link_already_exists" in r.text:
            r = requests.post("https://api.dropboxapi.com/2/sharing/list_shared_links", headers=auth,
                              json={"path": real, "direct_only": True}, timeout=TIMEOUT)
            url = _check(r, "Dropbox").json()["links"][0]["url"]
        else:
            url = _check(r, "Dropbox").json()["url"]
        if self.opt("direct", True):
            url = re.sub(r"[?&]dl=0", "", url) + ("&" if "?" in url else "?") + "raw=1"
        return UploadResult(url, host="Dropbox")


# ---------------------------------------------------------------- self-hosted
class LocalFolder(Uploader):
    id, name, categories = "folder", "Copy to folder (NAS / web root)", ("image", "text", "file")
    fields = [("dir", "Folder", "text"), ("url_base", "Public URL prefix (optional)", "text")]

    def upload(self, path, filename=None):
        self.need("dir")
        filename = filename or os.path.basename(path)
        os.makedirs(self.opt("dir"), exist_ok=True)
        dest = os.path.join(self.opt("dir"), filename)
        shutil.copyfile(path, dest)
        base = self.opt("url_base")
        url = base.rstrip("/") + "/" + urllib.parse.quote(filename) if base else "file://" + urllib.parse.quote(dest)
        return UploadResult(url, host="Folder")


class FTP(Uploader):
    id, name, categories = "ftp", "FTP / FTPS", ("image", "text", "file")
    fields = [("host", "Host", "text"), ("port", "Port", "int", 21), ("user", "Username", "text", "anonymous"),
              ("password", "Password", "password"), ("tls", "Use FTPS (explicit TLS)", "bool", False),
              ("passive", "Passive mode", "bool", True), ("remote_dir", "Remote folder", "text", "/"),
              ("url_base", "Public URL prefix (e.g. https://example.com/s/)", "text")]

    def upload(self, path, filename=None):
        import ftplib
        self.need("host")
        filename = filename or os.path.basename(path)
        cls = ftplib.FTP_TLS if self.opt("tls", False) else ftplib.FTP
        try:
            with cls() as ftp:
                ftp.connect(self.opt("host"), int(self.opt("port", 21)), timeout=30)
                ftp.login(self.opt("user", "anonymous"), self.opt("password"))
                if self.opt("tls", False):
                    ftp.prot_p()
                ftp.set_pasv(bool(self.opt("passive", True)))
                rd = self.opt("remote_dir", "/") or "/"
                if rd.startswith("/"):
                    ftp.cwd("/")
                for part in [p for p in rd.split("/") if p]:
                    try:
                        ftp.cwd(part)
                    except ftplib.error_perm:
                        ftp.mkd(part)
                        ftp.cwd(part)
                with open(path, "rb") as f:
                    ftp.storbinary("STOR " + filename, f)
        except (OSError, ftplib.Error) as e:
            raise UploadError(f"FTP: {e}")
        base = self.opt("url_base")
        url = base.rstrip("/") + "/" + urllib.parse.quote(filename) if base else \
            f"ftp://{self.opt('host')}/{rd.strip('/')}/{filename}".replace("//" + filename, "/" + filename)
        return UploadResult(url, host="FTP")


class SFTP(Uploader):
    id, name, categories = "sftp", "SFTP (SSH)", ("image", "text", "file")
    fields = [("host", "Host", "text"), ("port", "Port", "int", 22), ("user", "Username", "text"),
              ("password", "Password (needs python3-paramiko)", "password"),
              ("key_file", "Private key file (optional)", "text"),
              ("remote_dir", "Remote folder", "text", "."), ("url_base", "Public URL prefix", "text")]

    def upload(self, path, filename=None):
        self.need("host", "user")
        filename = filename or os.path.basename(path)
        rd = self.opt("remote_dir", ".") or "."
        host, port, user = self.opt("host"), int(self.opt("port", 22)), self.opt("user")
        try:
            import paramiko
        except ImportError:
            paramiko = None
        if paramiko:
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(host, port, user, self.opt("password") or None,
                               key_filename=self.opt("key_file") or None, timeout=30)
                sftp = client.open_sftp()
                cur = ""
                for part in [p for p in rd.split("/") if p and p != "."]:
                    cur = (cur + "/" if cur or rd.startswith("/") else "") + part
                    try:
                        sftp.stat(cur)
                    except IOError:
                        sftp.mkdir(cur)
                sftp.put(path, rd.rstrip("/") + "/" + filename)
                client.close()
            except Exception as e:
                raise UploadError(f"SFTP: {e}")
        else:
            if self.opt("password"):
                raise UploadError("SFTP password login needs: sudo apt install python3-paramiko "
                                  "(or use a private key file).")
            cmd = ["scp", "-P", str(port), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
            if self.opt("key_file"):
                cmd += ["-i", self.opt("key_file")]
            cmd += [path, f"{user}@{host}:{rd.rstrip('/')}/{filename}"]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
            if p.returncode:
                raise UploadError("scp: " + p.stderr.strip()[:300])
        base = self.opt("url_base")
        return UploadResult(base.rstrip("/") + "/" + urllib.parse.quote(filename) if base
                            else f"sftp://{host}/{rd.strip('/')}/{filename}", host="SFTP")


class WebDAV(Uploader):
    id, name, categories = "webdav", "WebDAV / Nextcloud / ownCloud", ("image", "text", "file")
    fields = [("server", "WebDAV base URL (…/remote.php/dav/files/USER)", "text"), ("user", "Username", "text"),
              ("password", "Password / app password", "password"), ("remote_dir", "Folder", "text", "MintShare"),
              ("nextcloud_share", "Create Nextcloud public share link", "bool", False),
              ("url_base", "Public URL prefix (if not using Nextcloud share)", "text")]

    def upload(self, path, filename=None):
        self.need("server", "user")
        filename = filename or os.path.basename(path)
        auth = (self.opt("user"), self.opt("password"))
        base = self.opt("server").rstrip("/")
        rd = self.opt("remote_dir", "").strip("/")
        cur = base
        for part in [p for p in rd.split("/") if p]:
            cur += "/" + urllib.parse.quote(part)
            requests.request("MKCOL", cur, auth=auth, timeout=30)
        target = cur + "/" + urllib.parse.quote(filename)
        r = requests.put(target, data=_read(path), auth=auth, timeout=TIMEOUT, headers={"User-Agent": UA})
        _check(r, "WebDAV")
        if self.opt("nextcloud_share", False):
            m = re.match(r"(https?://[^/]+(?:/[^/]+)*?)/remote\.php/", base)
            root = m.group(1) if m else base.split("/remote.php")[0]
            rel = "/" + (rd + "/" if rd else "") + filename
            o = requests.post(root + "/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json", auth=auth,
                              headers={"OCS-APIRequest": "true"}, data={"path": rel, "shareType": 3}, timeout=30)
            _check(o, "Nextcloud share")
            return UploadResult(o.json()["ocs"]["data"]["url"], host="Nextcloud")
        pub = self.opt("url_base")
        return UploadResult(pub.rstrip("/") + "/" + urllib.parse.quote(filename) if pub else target, host="WebDAV")


def sigv4_signature(secret_key, day, region, string_to_sign, service="s3"):
    k = hmac.new(("AWS4" + secret_key).encode(), day.encode(), hashlib.sha256).digest()
    for part in (region, service, "aws4_request"):
        k = hmac.new(k, part.encode(), hashlib.sha256).digest()
    return hmac.new(k, string_to_sign.encode(), hashlib.sha256).hexdigest()


class S3(Uploader):
    id, name, categories = "s3", "Amazon S3 / S3-compatible (MinIO, Backblaze, R2…)", ("image", "text", "file")
    fields = [("endpoint", "Endpoint", "text", "https://s3.amazonaws.com"), ("region", "Region", "text", "us-east-1"),
              ("bucket", "Bucket", "text"), ("access_key", "Access key", "text"), ("secret_key", "Secret key", "password"),
              ("prefix", "Key prefix", "text", "mintshare/"), ("path_style", "Path-style addressing", "bool", True),
              ("public_read", "Set public-read ACL", "bool", False), ("url_base", "Public URL prefix", "text")]

    def build_request(self, data: bytes, filename: str, now=None):
        """Return (url, headers) for a SigV4-signed PUT (separated out so it can be unit tested)."""
        ep = urllib.parse.urlparse(self.opt("endpoint", "https://s3.amazonaws.com"))
        bucket, region = self.opt("bucket"), self.opt("region", "us-east-1")
        key = (self.opt("prefix", "") + filename).lstrip("/")
        if self.opt("path_style", True):
            host, uri = ep.netloc, "/" + bucket + "/" + urllib.parse.quote(key)
        else:
            host, uri = bucket + "." + ep.netloc, "/" + urllib.parse.quote(key)
        now = now or _dt.datetime.utcnow()
        amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        payload = hashlib.sha256(data).hexdigest()
        h = {"host": host, "x-amz-content-sha256": payload, "x-amz-date": amz, "content-type": _mime(filename)}
        if self.opt("public_read", False):
            h["x-amz-acl"] = "public-read"
        signed = ";".join(sorted(h))
        canon = "PUT\n" + uri + "\n\n" + "".join(f"{k}:{h[k]}\n" for k in sorted(h)) + "\n" + signed + "\n" + payload
        scope = f"{day}/{region}/s3/aws4_request"
        sts = f"AWS4-HMAC-SHA256\n{amz}\n{scope}\n{hashlib.sha256(canon.encode()).hexdigest()}"
        sig = sigv4_signature(self.opt("secret_key"), day, region, sts)
        h["Authorization"] = (f"AWS4-HMAC-SHA256 Credential={self.opt('access_key')}/{scope}, "
                              f"SignedHeaders={signed}, Signature={sig}")
        return f"{ep.scheme}://{host}{uri}", h, key

    def upload(self, path, filename=None):
        self.need("bucket", "access_key", "secret_key")
        filename = filename or os.path.basename(path)
        data = _read(path)
        url, headers, key = self.build_request(data, filename)
        r = requests.put(url, data=data, headers={k: v for k, v in headers.items() if k != "host"}, timeout=TIMEOUT)
        _check(r, "S3")
        pub = self.opt("url_base")
        return UploadResult(pub.rstrip("/") + "/" + urllib.parse.quote(key) if pub else url, host="S3")


# ---------------------------------------------------------------- shorteners
class IsGd(Uploader):
    id, name, categories = "is.gd", "is.gd", ("shortener",)
    base = "https://is.gd/create.php"

    def shorten(self, url):
        r = requests.get(self.base, params={"format": "simple", "url": url}, headers={"User-Agent": UA}, timeout=30)
        _check(r, self.name)
        if not r.text.startswith("http"):
            raise UploadError(f"{self.name}: {r.text[:200]}")
        return r.text.strip()


class VGd(IsGd):
    id, name, base = "v.gd", "v.gd", "https://v.gd/create.php"


class TinyUrl(Uploader):
    id, name, categories = "tinyurl", "TinyURL", ("shortener",)

    def shorten(self, url):
        r = requests.get("https://tinyurl.com/api-create.php", params={"url": url}, headers={"User-Agent": UA}, timeout=30)
        return _check(r, "TinyURL").text.strip()


# ---------------------------------------------------------------- ShareX custom uploaders (.sxcu)
_TOKEN = re.compile(r"\$([^$\n]+?)\$")


def _json_path(obj, path):
    cur = obj
    for tok in re.findall(r"[^.\[\]]+|\[\d+\]", path.lstrip("$.")):
        if tok.startswith("["):
            cur = cur[int(tok[1:-1])]
        elif isinstance(cur, list) and tok.isdigit():
            cur = cur[int(tok)]
        else:
            cur = cur[tok]
    return cur


def expand_response(template, text, headers=None, resp_url=""):
    """Expand ShareX response syntax: $json:a.b$, $response$, $responseurl$, $header:X$, $regex:re|n$, $xml:xpath$."""
    headers = headers or {}
    parsed = None

    def sub(m):
        nonlocal parsed
        tok = m.group(1)
        try:
            if tok == "response":
                return text
            if tok == "responseurl":
                return resp_url
            if tok.startswith("json:"):
                if parsed is None:
                    parsed = json.loads(text)
                v = _json_path(parsed, tok[5:])
                return v if isinstance(v, str) else json.dumps(v)
            if tok.startswith("header:"):
                return headers.get(tok[7:], "")
            if tok.startswith("regex:"):
                pat, _, grp = tok[6:].rpartition("|")
                if not pat:
                    pat, grp = grp, "1"
                mm = re.search(pat, text, re.S)
                if not mm:
                    return ""
                return mm.group(int(grp) if grp.isdigit() else grp)
            if tok.startswith("xml:"):
                import xml.etree.ElementTree as ET
                node = ET.fromstring(text).find("." + tok[4:] if tok[4:].startswith("/") else tok[4:])
                return node.text if node is not None and node.text else ""
        except (ValueError, KeyError, IndexError, TypeError, re.error, Exception):
            return ""
        return m.group(0)

    return _TOKEN.sub(sub, template)


def expand_request(value, filename="", input_text="", data: bytes | None = None):
    """Expand request-side variables ($filename$, $input$, $base64$, $random:a|b$, $date:fmt$)."""
    if not isinstance(value, str):
        return value

    def sub(m):
        t = m.group(1)
        if t == "filename": return filename
        if t == "input": return input_text
        if t == "base64": return base64.b64encode(data or b"").decode()
        if t.startswith("random:"):
            import random
            return random.choice(t[7:].split("|"))
        if t.startswith("date:"):
            return _dt.datetime.now().strftime(re.sub(r"yyyy", "%Y", t[5:]))
        return m.group(0)

    return _TOKEN.sub(sub, value)


class CustomUploader(Uploader):
    def __init__(self, sxcu: dict, cfg=None, path=""):
        super().__init__(cfg)
        self.sxcu, self.path = sxcu, path
        self.name = sxcu.get("Name") or os.path.splitext(os.path.basename(path))[0] or "Custom"
        self.id = "custom:" + self.name
        dest = sxcu.get("DestinationType", "ImageUploader, TextUploader, FileUploader")
        cats = []
        for key, c in (("ImageUploader", "image"), ("TextUploader", "text"), ("FileUploader", "file"),
                       ("URLShortener", "shortener")):
            if key in dest:
                cats.append(c)
        self.categories = tuple(cats) or ("image", "text", "file")

    def _request(self, filename, data, input_text=""):
        s = self.sxcu
        method = s.get("RequestMethod", "POST").upper()
        url = expand_request(s.get("RequestURL", ""), filename, input_text, data)
        params = {k: expand_request(v, filename, input_text, data) for k, v in (s.get("Parameters") or {}).items()}
        headers = {k: expand_request(v, filename, input_text, data) for k, v in (s.get("Headers") or {}).items()}
        headers.setdefault("User-Agent", UA)
        args = {k: expand_request(v, filename, input_text, data) for k, v in (s.get("Arguments") or {}).items()}
        body = s.get("Body") or ("MultipartFormData" if s.get("FileFormName") else "NoBody")
        kw = {"headers": headers, "params": params, "timeout": TIMEOUT}
        if s.get("Data"):
            kw["data"] = expand_request(s["Data"], filename, input_text, data).encode()
            if body == "JSON":
                headers.setdefault("Content-Type", "application/json")
            elif body == "XML":
                headers.setdefault("Content-Type", "application/xml")
        elif body == "MultipartFormData":
            kw["data"] = args
            if data is not None and s.get("FileFormName"):
                kw["files"] = {s["FileFormName"]: (filename, data, _mime(filename))}
            elif not args:
                kw["files"] = {"_": ("", b"")}
        elif body == "FormURLEncoded":
            kw["data"] = args
        elif body == "JSON":
            kw["json"] = args
        elif body == "Binary":
            kw["data"] = data
            headers.setdefault("Content-Type", _mime(filename))
        r = requests.request(method, url, **kw)
        return r

    def _parse(self, r, key, default=""):
        tpl = self.sxcu.get(key) or default
        return expand_response(tpl, r.text, r.headers, r.url).strip() if tpl else ""

    def upload(self, path, filename=None):
        filename = filename or os.path.basename(path)
        r = self._request(filename, _read(path))
        if r.status_code >= 400:
            msg = self._parse(r, "ErrorMessage") or r.text[:300]
            raise UploadError(f"{self.name}: HTTP {r.status_code} {msg}")
        url = self._parse(r, "URL", "$response$")
        if not url:
            raise UploadError(f"{self.name}: could not read a URL from the response: {r.text[:200]}")
        return UploadResult(url, self._parse(r, "ThumbnailURL"), self._parse(r, "DeletionURL"), self.name)

    def shorten(self, url):
        r = self._request("", None, input_text=url)
        if r.status_code >= 400:
            raise UploadError(f"{self.name}: HTTP {r.status_code} {r.text[:200]}")
        return self._parse(r, "URL", "$response$")


def load_custom_uploaders(directory=None):
    d = directory or paths.CUSTOM_UPLOADERS_DIR
    out = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith((".sxcu", ".json")):
                p = os.path.join(d, fn)
                try:
                    with open(p, encoding="utf-8") as f:
                        out.append(CustomUploader(json.load(f), path=p))
                except (OSError, ValueError):
                    continue
    return out


def import_sxcu(src, directory=None):
    d = directory or paths.CUSTOM_UPLOADERS_DIR
    os.makedirs(d, exist_ok=True)
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    if "RequestURL" not in data:
        raise UploadError("This file is not a valid .sxcu custom uploader (no RequestURL).")
    dest = os.path.join(d, re.sub(r"[^\w.-]+", "_", data.get("Name") or os.path.basename(src)) .removesuffix(".sxcu") + ".sxcu")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return CustomUploader(data, path=dest)


BUILTIN = [Imgur, Catbox, Litterbox, ZeroX0, PasteRs, Dpaste, Pastebin, Gist, Dropbox, LocalFolder, FTP, SFTP, WebDAV, S3,
           IsGd, VGd, TinyUrl]


def all_uploaders(settings: dict | None = None, custom_dir=None):
    """Return {id: instance} of every destination (built-in + custom)."""
    cfgs = (settings or {}).get("uploaders", {})
    out = {cls.id: cls(cfgs.get(cls.id, {})) for cls in BUILTIN}
    for c in load_custom_uploaders(custom_dir):
        out[c.id] = c
    return out


def choices(category, settings=None, custom_dir=None):
    return [(u.id, u.name) for u in all_uploaders(settings, custom_dir).values() if category in u.categories]


def get(uploader_id, settings=None, custom_dir=None):
    ups = all_uploaders(settings, custom_dir)
    if uploader_id not in ups:
        raise UploadError(f"Unknown destination '{uploader_id}'. Pick one under Destinations.")
    return ups[uploader_id]
