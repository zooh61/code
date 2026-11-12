"""Stitch successive scroll captures into one tall image (exact-overlap matching)."""
from PIL import Image


def _rows(img):
    img = img.convert("RGB")
    w = img.width * 3
    raw = img.tobytes()
    return [raw[i * w:(i + 1) * w] for i in range(img.height)]


def find_shift(prev, new, min_overlap_frac=0.08):
    """Return d such that prev[d:] == new[:H-d] (new content starts at row H-d of ``new``),
    0 if the frames are identical (end of page), or None if no reliable overlap was found."""
    h = prev.height
    rp, rn = _rows(prev), _rows(new)
    if rp == rn:
        return 0
    min_overlap = max(4, int(h * min_overlap_frac))
    for d in range(1, h - min_overlap + 1):
        if rp[d] != rn[0]:
            continue
        if rp[d:] == rn[:h - d]:
            return d
    return None


class Stitcher:
    def __init__(self, first):
        self.parts = [first.convert("RGBA")]
        self.last = first.convert("RGBA")
        self.height = first.height

    def add(self, frame):
        """Append a frame. Returns 'added', 'end' (no more scrolling) or 'nomatch'."""
        frame = frame.convert("RGBA")
        if frame.size != self.last.size:
            return "nomatch"
        d = find_shift(self.last, frame)
        if d == 0:
            return "end"
        if d is None:
            return "nomatch"
        new_rows = d
        self.parts.append(frame.crop((0, frame.height - new_rows, frame.width, frame.height)))
        self.last = frame
        return "added"

    def result(self):
        total = sum(p.height for p in self.parts)
        out = Image.new("RGBA", (self.parts[0].width, total))
        y = 0
        for p in self.parts:
            out.paste(p, (0, y))
            y += p.height
        return out
