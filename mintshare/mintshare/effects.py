"""Pure-PIL image effects used by the after-capture pipeline, the editor and the image tools."""
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


def _rgba(img):
    return img if img.mode == "RGBA" else img.convert("RGBA")


def resize_percent(img, pct):
    if pct == 100:
        return img
    w, h = img.size
    return img.resize((max(1, int(w * pct / 100)), max(1, int(h * pct / 100))), Image.LANCZOS)


def add_border(img, size, color="#000000"):
    if size <= 0:
        return img
    img = _rgba(img)
    out = Image.new("RGBA", (img.width + 2 * size, img.height + 2 * size), ImageColor.getrgb(color) + (255,))
    out.paste(img, (size, size))
    return out


def rounded_corners(img, radius):
    if radius <= 0:
        return img
    img = _rgba(img)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius, fill=255)
    out = img.copy()
    out.putalpha(ImageChops.multiply(img.getchannel("A"), mask))
    return out


def drop_shadow(img, offset=6, blur=8, color=(0, 0, 0, 160), margin=None):
    img = _rgba(img)
    m = margin if margin is not None else blur * 2 + offset
    canvas = Image.new("RGBA", (img.width + 2 * m, img.height + 2 * m), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    block = Image.new("RGBA", img.size, color)
    block.putalpha(ImageChops.multiply(img.getchannel("A"), Image.new("L", img.size, color[3])))
    shadow.paste(block, (m + offset, m + offset))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas = Image.alpha_composite(canvas, shadow)
    canvas.alpha_composite(img, (m, m))
    return canvas


def _font(size):
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Ubuntu-R.ttf", "NotoSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _place(base_size, item_size, position, pad=12):
    bw, bh = base_size
    iw, ih = item_size
    v, _, h = position.partition("-")
    x = {"left": pad, "center": (bw - iw) // 2, "right": bw - iw - pad}.get(h or "center", pad)
    y = {"top": pad, "middle": (bh - ih) // 2, "center": (bh - ih) // 2, "bottom": bh - ih - pad}.get(v, pad)
    if position == "center":
        x, y = (bw - iw) // 2, (bh - ih) // 2
    return x, y


def watermark_text(img, text, opacity=0.5, position="bottom-right", size=None, color=(255, 255, 255)):
    img = _rgba(img)
    size = size or max(12, img.width // 40)
    font = _font(size)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, t, r, b = tmp.textbbox((0, 0), text, font=font)
    layer = Image.new("RGBA", (r - l + 8, b - t + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = int(255 * opacity)
    d.text((5, 5), text, font=font, fill=(0, 0, 0, a))
    d.text((4 - l, 4 - t), text, font=font, fill=color + (a,))
    out = img.copy()
    out.alpha_composite(layer, _place(img.size, layer.size, position))
    return out


def watermark_image(img, wm_path, opacity=0.5, position="bottom-right", max_frac=0.25):
    img = _rgba(img)
    wm = _rgba(Image.open(wm_path))
    scale = min(1.0, img.width * max_frac / wm.width)
    wm = wm.resize((max(1, int(wm.width * scale)), max(1, int(wm.height * scale))), Image.LANCZOS)
    wm.putalpha(wm.getchannel("A").point(lambda v: int(v * opacity)))
    out = img.copy()
    out.alpha_composite(wm, _place(img.size, wm.size, position))
    return out


def grayscale(img):
    a = _rgba(img).getchannel("A")
    out = ImageOps.grayscale(img.convert("RGB")).convert("RGBA")
    out.putalpha(a)
    return out


def invert(img):
    a = _rgba(img).getchannel("A")
    out = ImageOps.invert(img.convert("RGB")).convert("RGBA")
    out.putalpha(a)
    return out


def sepia(img):
    a = _rgba(img).getchannel("A")
    g = ImageOps.grayscale(img.convert("RGB"))
    out = ImageOps.colorize(g, "#2b1a05", "#f3e2c0").convert("RGBA")
    out.putalpha(a)
    return out


def brightness(img, f):
    return ImageEnhance.Brightness(_rgba(img)).enhance(f)


def contrast(img, f):
    return ImageEnhance.Contrast(_rgba(img)).enhance(f)


def saturation(img, f):
    return ImageEnhance.Color(_rgba(img)).enhance(f)


def blur(img, radius):
    return _rgba(img).filter(ImageFilter.GaussianBlur(radius))


def sharpen(img):
    return _rgba(img).filter(ImageFilter.SHARPEN)


def pixelate(img, block):
    img = _rgba(img)
    block = max(2, int(block))
    small = img.resize((max(1, img.width // block), max(1, img.height // block)), Image.BILINEAR)
    return small.resize(img.size, Image.NEAREST)


def blur_region(img, box, radius=8):
    img = _rgba(img).copy()
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, x1 = sorted((max(0, x0), min(img.width, x1)))
    y0, y1 = sorted((max(0, y0), min(img.height, y1)))
    if x1 - x0 < 1 or y1 - y0 < 1:
        return img
    pad = int(radius * 3)
    ex = (max(0, x0 - pad), max(0, y0 - pad), min(img.width, x1 + pad), min(img.height, y1 + pad))
    part = img.crop(ex).filter(ImageFilter.GaussianBlur(radius))
    img.paste(part.crop((x0 - ex[0], y0 - ex[1], x1 - ex[0], y1 - ex[1])), (x0, y0))
    return img


def pixelate_region(img, box, block=10):
    img = _rgba(img).copy()
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, x1 = sorted((max(0, x0), min(img.width, x1)))
    y0, y1 = sorted((max(0, y0), min(img.height, y1)))
    if x1 - x0 < 1 or y1 - y0 < 1:
        return img
    img.paste(pixelate(img.crop((x0, y0, x1, y1)), block), (x0, y0))
    return img


def spotlight(img, box, dim=0.6):
    img = _rgba(img)
    dark = ImageEnhance.Brightness(img).enhance(1 - dim)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rectangle([int(v) for v in box], fill=255)
    return Image.composite(img, dark, mask)


def rotate(img, deg):
    return _rgba(img).rotate(-deg, expand=True)


def flip(img, horizontal=True):
    return ImageOps.mirror(img) if horizontal else ImageOps.flip(img)


def trim_whitespace(img, tol=8):
    img = _rgba(img)
    bg = Image.new("RGBA", img.size, img.getpixel((0, 0)))
    diff = ImageChops.difference(img, bg).convert("L").point(lambda v: 255 if v > tol else 0)
    box = diff.getbbox()
    return img.crop(box) if box else img


def combine(images, vertical=True, spacing=0, align="start", bg=(0, 0, 0, 0)):
    images = [_rgba(i) for i in images]
    if not images:
        raise ValueError("no images")
    if vertical:
        w = max(i.width for i in images)
        h = sum(i.height for i in images) + spacing * (len(images) - 1)
    else:
        w = sum(i.width for i in images) + spacing * (len(images) - 1)
        h = max(i.height for i in images)
    out = Image.new("RGBA", (w, h), bg)
    pos = 0
    for i in images:
        if vertical:
            x = {"start": 0, "center": (w - i.width) // 2, "end": w - i.width}[align]
            out.alpha_composite(i, (x, pos))
            pos += i.height + spacing
        else:
            y = {"start": 0, "center": (h - i.height) // 2, "end": h - i.height}[align]
            out.alpha_composite(i, (pos, y))
            pos += i.width + spacing
    return out


def split(img, rows, cols):
    img = _rgba(img)
    pw, ph = img.width // cols, img.height // rows
    return [img.crop((c * pw, r * ph, (c + 1) * pw if c < cols - 1 else img.width,
                      (r + 1) * ph if r < rows - 1 else img.height))
            for r in range(rows) for c in range(cols)]


def thumbnail(img, width=None, height=None):
    img = _rgba(img)
    if width and not height:
        height = int(img.height * width / img.width)
    elif height and not width:
        width = int(img.width * height / img.height)
    return img.resize((max(1, width), max(1, height)), Image.LANCZOS)


def apply_configured(img, cfg):
    """Apply the effect chain from settings ``effects.*`` (a dict) in ShareX order."""
    e = cfg
    if e.get("resize_enabled"):
        img = resize_percent(img, e.get("resize_percent", 100))
    if e.get("grayscale"):
        img = grayscale(img)
    if e.get("rounded", 0):
        img = rounded_corners(img, int(e["rounded"]))
    if e.get("border", 0):
        img = add_border(img, int(e["border"]), e.get("border_color", "#000000"))
    if e.get("watermark_enabled"):
        if e.get("watermark_image"):
            img = watermark_image(img, e["watermark_image"], e.get("watermark_opacity", 0.5),
                                  e.get("watermark_position", "bottom-right"))
        elif e.get("watermark_text"):
            img = watermark_text(img, e["watermark_text"], e.get("watermark_opacity", 0.5),
                                 e.get("watermark_position", "bottom-right"))
    if e.get("shadow"):
        img = drop_shadow(img, int(e.get("shadow_offset", 6)), int(e.get("shadow_blur", 8)))
    return img
