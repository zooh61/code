#!/usr/bin/env python3
"""Generate the "Venster" xfwm4 window-border theme.

The theme draws flat, light title bars with wide caption buttons
(minimise, maximise, close) on the right, the way people know from
Windows 10/11. Every image is written as an XPM file, which is the format
xfwm4 reads. No image library is needed.

Usage: make-xfwm4-theme.py <output-directory>
"""
import os
import sys

TITLE_HEIGHT = 32
BORDER = 4            # width of the left, right and bottom borders
BUTTON_WIDTH = 46
GLYPH = 10            # size of the minimise/maximise/close glyphs

COLORS = {
    "active": {
        "bg": "#FFFFFF",
        "line": "#5B7DB1",        # 1px outline around the window
        "glyph": "#1A1A1A",
    },
    "inactive": {
        "bg": "#F3F3F3",
        "line": "#B4B4B4",
        "glyph": "#9A9A9A",
    },
}
HOVER_BG = "#E5E5E5"
PRESSED_BG = "#CCCCCC"
CLOSE_HOVER_BG = "#E81123"
CLOSE_PRESSED_BG = "#F1707A"
WHITE = "#FFFFFF"


def write_xpm(path, pixels):
    """Write a 2D list of '#RRGGBB' strings as an XPM image."""
    height = len(pixels)
    width = len(pixels[0])
    palette = {}
    symbols = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    for row in pixels:
        for color in row:
            if color not in palette:
                palette[color] = symbols[len(palette)]
    name = os.path.splitext(os.path.basename(path))[0].replace("-", "_")
    lines = [
        "/* XPM */",
        f"static char * {name}[] = {{",
        f'"{width} {height} {len(palette)} 1",',
    ]
    for color, symbol in palette.items():
        lines.append(f'"{symbol}\tc {color}",')
    rows = ['"' + "".join(palette[c] for c in row) + '"' for row in pixels]
    lines.append(",\n".join(rows))
    lines.append("};")
    with open(path, "w") as handle:
        handle.write("\n".join(lines) + "\n")


def canvas(width, height, color):
    return [[color] * width for _ in range(height)]


def draw_glyph(pixels, kind, color):
    """Draw a caption-button glyph centred in the button."""
    height = len(pixels)
    width = len(pixels[0])
    left = (width - GLYPH) // 2
    top = (height - GLYPH) // 2 + 1
    if kind == "hide":                      # minimise: one horizontal line
        for x in range(GLYPH):
            pixels[top + GLYPH // 2][left + x] = color
    elif kind == "maximize":                # maximise: one square outline
        for i in range(GLYPH):
            pixels[top][left + i] = color
            pixels[top + GLYPH - 1][left + i] = color
            pixels[top + i][left] = color
            pixels[top + i][left + GLYPH - 1] = color
    elif kind == "maximize-toggled":        # restore: two overlapping squares
        size = GLYPH - 2
        front_top, front_left = top + 2, left
        for i in range(size):
            pixels[front_top][front_left + i] = color
            pixels[front_top + size - 1][front_left + i] = color
            pixels[front_top + i][front_left] = color
            pixels[front_top + i][front_left + size - 1] = color
        back_top, back_left = top, left + 2
        for i in range(size):
            pixels[back_top][back_left + i] = color
            pixels[back_top + i][back_left + size - 1] = color
    elif kind == "close":                   # close: a diagonal cross
        for i in range(GLYPH):
            pixels[top + i][left + i] = color
            pixels[top + i][left + GLYPH - 1 - i] = color


def with_top_line(pixels, color):
    for x in range(len(pixels[0])):
        pixels[0][x] = color
    return pixels


def make_button(kind, state, variant):
    colors = COLORS[variant]
    background = colors["bg"]
    glyph = colors["glyph"]
    if state == "prelight":
        background = CLOSE_HOVER_BG if kind == "close" else HOVER_BG
        glyph = WHITE if kind == "close" else COLORS["active"]["glyph"]
    elif state == "pressed":
        background = CLOSE_PRESSED_BG if kind == "close" else PRESSED_BG
        glyph = WHITE if kind == "close" else COLORS["active"]["glyph"]
    width = BUTTON_WIDTH
    if kind in ("menu", "shade", "shade-toggled", "stick", "stick-toggled"):
        width = TITLE_HEIGHT - 4
    pixels = canvas(width, TITLE_HEIGHT, background)
    if kind in ("hide", "maximize", "maximize-toggled", "close"):
        draw_glyph(pixels, kind, glyph)
    return with_top_line(pixels, colors["line"])


def build(out_dir):
    xfwm_dir = os.path.join(out_dir, "xfwm4")
    os.makedirs(xfwm_dir, exist_ok=True)

    for variant, colors in COLORS.items():
        bg, line = colors["bg"], colors["line"]

        # Title bar pieces (tiled horizontally).
        for n in range(1, 6):
            write_xpm(os.path.join(xfwm_dir, f"title-{n}-{variant}.xpm"),
                      with_top_line(canvas(4, TITLE_HEIGHT, bg), line))

        # Top corners: outline on the outer edge and the top.
        top_left = with_top_line(canvas(BORDER, TITLE_HEIGHT, bg), line)
        top_right = with_top_line(canvas(BORDER, TITLE_HEIGHT, bg), line)
        for y in range(TITLE_HEIGHT):
            top_left[y][0] = line
            top_right[y][BORDER - 1] = line
        write_xpm(os.path.join(xfwm_dir, f"top-left-{variant}.xpm"), top_left)
        write_xpm(os.path.join(xfwm_dir, f"top-right-{variant}.xpm"), top_right)

        # Side borders.
        left = canvas(BORDER, 8, bg)
        right = canvas(BORDER, 8, bg)
        for y in range(8):
            left[y][0] = line
            right[y][BORDER - 1] = line
        write_xpm(os.path.join(xfwm_dir, f"left-{variant}.xpm"), left)
        write_xpm(os.path.join(xfwm_dir, f"right-{variant}.xpm"), right)

        # Bottom border and corners.
        bottom = canvas(8, BORDER, bg)
        for x in range(8):
            bottom[BORDER - 1][x] = line
        write_xpm(os.path.join(xfwm_dir, f"bottom-{variant}.xpm"), bottom)

        bottom_left = canvas(BORDER * 3, BORDER, bg)
        bottom_right = canvas(BORDER * 3, BORDER, bg)
        for x in range(BORDER * 3):
            bottom_left[BORDER - 1][x] = line
            bottom_right[BORDER - 1][x] = line
        for y in range(BORDER):
            bottom_left[y][0] = line
            bottom_right[y][BORDER * 3 - 1] = line
        write_xpm(os.path.join(xfwm_dir, f"bottom-left-{variant}.xpm"), bottom_left)
        write_xpm(os.path.join(xfwm_dir, f"bottom-right-{variant}.xpm"), bottom_right)

        # Caption buttons.
        for kind in ("hide", "maximize", "maximize-toggled", "close", "menu",
                     "shade", "shade-toggled", "stick", "stick-toggled"):
            base = make_button(kind, "normal", variant)
            write_xpm(os.path.join(xfwm_dir, f"{kind}-{variant}.xpm"), base)
            if variant == "active":
                for state in ("prelight", "pressed"):
                    write_xpm(os.path.join(xfwm_dir, f"{kind}-{state}.xpm"),
                              make_button(kind, state, variant))

    with open(os.path.join(xfwm_dir, "themerc"), "w") as handle:
        handle.write("\n".join([
            "active_text_color=#1A1A1A",
            "inactive_text_color=#8A8A8A",
            "full_width_title=true",
            "title_alignment=left",
            "title_horizontal_offset=8",
            "title_vertical_offset_active=1",
            "title_vertical_offset_inactive=1",
            "title_shadow_active=false",
            "title_shadow_inactive=false",
            "button_offset=0",
            "button_spacing=0",
            "show_app_icon=true",
            "maximized_offset=0",
            "shadow_delta_height=2",
            "shadow_delta_width=0",
            "shadow_delta_x=0",
            "shadow_delta_y=-4",
            "shadow_opacity=35",
            "",
        ]))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(sys.argv[1])
