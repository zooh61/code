import json
import os
import threading
import http.server

import pytest
from PIL import Image

from mintshare import config, effects, history, naming, stitch, tasks, uploaders
from mintshare.tools import core


def test_naming_tokens():
    n = naming.format_name("S_%y-%mo-%d_%h-%mi-%s_%t_%pn", "Win/dow", "firefox")
    assert "/" not in n and n.endswith("Win_dow_firefox")
    assert len(naming.format_name("%ra6")) == 6
    assert naming.format_name("%rn4").isdigit()


def test_unique_path(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(b"x")
    assert naming.unique_path(str(p)).endswith("a (2).png")


def test_config_roundtrip(tmp_path):
    c = config.Config(str(tmp_path / "c.json"))
    c.set("capture.delay", 3)
    assert config.Config(str(tmp_path / "c.json")).get("capture.delay") == 3
    assert c.effective({"after_capture": {"upload": True}})["after_capture"]["upload"] is True
    assert c.get("after_capture.upload") is False


def test_effects():
    im = Image.new("RGBA", (100, 80), (10, 100, 200, 255))
    assert effects.add_border(im, 5).size == (110, 90)
    assert effects.drop_shadow(im).width > 100
    assert effects.combine([im, im], True, 4).size == (100, 164)
    assert len(effects.split(im, 2, 2)) == 4
    assert effects.rounded_corners(im, 20).getpixel((0, 0))[3] == 0
    assert effects.watermark_text(im, "hi").size == im.size
    px = effects.pixelate_region(im, (0, 0, 50, 50), 10)
    assert px.size == im.size


def test_stitch_reconstructs_page():
    page = Image.effect_noise((120, 700), 90).convert("RGB")
    frames = [page.crop((0, y, 120, y + 200)) for y in (0, 150, 300, 450, 500)]
    st = stitch.Stitcher(frames[0])
    assert [st.add(f) for f in frames[1:]] == ["added"] * 4
    assert st.add(frames[-1]) == "end"
    out = st.result().convert("RGB")
    assert out.size == (120, 700) and out.tobytes() == page.tobytes()


def test_sigv4_aws_example():
    # official AWS example "PUT Object" (docs: sigv4-header-based-auth)
    secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    canon = ("PUT\n/test%24file.text\n\ndate:Fri, 24 May 2013 00:00:00 GMT\nhost:examplebucket.s3.amazonaws.com\n"
             "x-amz-content-sha256:44ce7dd67c959e0d3524ffac1771dfbba87d2b6b4b4e99e42034a8b803f8b072\n"
             "x-amz-date:20130524T000000Z\nx-amz-storage-class:REDUCED_REDUNDANCY\n\n"
             "date;host;x-amz-content-sha256;x-amz-date;x-amz-storage-class\n"
             "44ce7dd67c959e0d3524ffac1771dfbba87d2b6b4b4e99e42034a8b803f8b072")
    import hashlib
    sts = "AWS4-HMAC-SHA256\n20130524T000000Z\n20130524/us-east-1/s3/aws4_request\n" + hashlib.sha256(canon.encode()).hexdigest()
    assert uploaders.sigv4_signature(secret, "20130524", "us-east-1", sts) == \
        "98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd"


def test_sxcu_syntax():
    f = uploaders.expand_response
    assert f("$json:data.files[1].name$", '{"data":{"files":[{"name":"a"},{"name":"b"}]}}') == "b"
    assert f("x$regex:id=(\\d+)|1$", "id=42") == "x42"
    assert f("$header:X-A$-$response$", "r", {"X-A": "h"}) == "h-r"
    assert uploaders.expand_request("$filename$/$input$", "f.png", "u") == "f.png/u"


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"url": "http://host/f", "has_file": b"filename=" in body}).encode())

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"http://short/1")

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_custom_uploader_and_pipeline(tmp_path, server):
    sxcu = {"Name": "T", "DestinationType": "ImageUploader, URLShortener", "RequestMethod": "POST",
            "RequestURL": server + "/u", "Body": "MultipartFormData", "FileFormName": "file",
            "URL": "$json:url$"}
    (tmp_path / "t.sxcu").write_text(json.dumps(sxcu))
    ups = uploaders.all_uploaders({}, str(tmp_path))
    assert "custom:T" in ups and "image" in ups["custom:T"].categories
    img = tmp_path / "a.png"
    Image.new("RGB", (4, 4)).save(img)
    r = ups["custom:T"].upload(str(img))
    assert r.url == "http://host/f"

    uploaders.paths.CUSTOM_UPLOADERS_DIR = str(tmp_path)
    cfg = config.Config(str(tmp_path / "c.json"))
    cfg.set("image.save_dir", str(tmp_path / "pics"))
    cfg.set("destinations.image", "custom:T")
    log = []

    class UI(tasks.NullUI):
        def copy_text(self, t): log.append(t)
    p = tasks.Pipeline(cfg, history.History(str(tmp_path / "h.db")), UI())
    path, res = p.process_image(Image.new("RGBA", (50, 50)), "x", "",
                                {"after_capture": {"upload": True}})
    assert os.path.exists(path) and res.url == "http://host/f" and log == ["http://host/f"]
    assert p.history.list()[0]["url"] == "http://host/f"


def test_tools_core(tmp_path):
    assert core.color_formats(255, 0, 0)["HEX"] == "#FF0000"
    assert core.parse_color("rgb(1, 2, 3)") == (1, 2, 3)
    assert core.hash_text("abc", "md5") == "900150983cd24fb0d6963f7d28e17f72"
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc")
    assert core.hash_file(str(f), "sha1") == "a9993e364706816aba3e25717850c26c9cd0d89d"
    assert core.qr_make("hello").size[0] > 50
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "z.txt").write_text("1")
    assert "z.txt" in core.index_directory(str(tmp_path), "html")


def test_recorder_commands():
    from mintshare import recorder
    cmd = recorder.build_command((10, 20, 801, 601), "/tmp/o.mp4", 30, True, True)
    assert "800x600" in cmd and ":0+10,20" in " ".join(cmd).replace(os.environ.get("DISPLAY", ":0"), ":0") and "pulse" in cmd
