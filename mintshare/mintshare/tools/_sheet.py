from PIL import Image, ImageDraw
from .. import effects


def _fmt(t):
    t = int(t)
    return f"{t // 3600:d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def contact_sheet(frames, columns, title, duration, pad=8, header=56):
    if not frames:
        raise RuntimeError("No frames could be extracted")
    w, h = frames[0][1].size
    rows = (len(frames) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * (w + pad) + pad, header + rows * (h + pad) + pad), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 10), title, fill=(240, 240, 240), font=effects._font(18))
    d.text((pad, 34), f"Duration {_fmt(duration)} · {frames[0][1].width}px frames", fill=(160, 160, 170), font=effects._font(13))
    for i, (t, fr) in enumerate(frames):
        x, y = pad + (i % columns) * (w + pad), header + pad + (i // columns) * (h + pad)
        sheet.paste(fr, (x, y))
        d.rectangle((x, y + h - 20, x + 64, y + h), fill=(0, 0, 0))
        d.text((x + 4, y + h - 18), _fmt(t), fill=(255, 255, 255), font=effects._font(13))
    return sheet
