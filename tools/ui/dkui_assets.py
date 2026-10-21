#!/usr/bin/env python3
"""Makes the menu art for the Quake 3 (Team Arena style) menus from Daikatana's data.

- fonts: each .dkf bitmap font becomes fonts/dk/<name>.tga plus the glyph table
  fonts/dk/<name>_<height>.dat that Spearmint loads for registerFont.
- widgets: every glyph of the int_buttons font (button faces, arrows, slider,
  edit fields) becomes ui/assets/dk/buttons/<glyph>.tga; the arrow toenails
  get int_font's arrow on them.
- background: the six 256x256 tiles of the menu backdrop become one
  640x480 ui/assets/dk/background.tga, cut the way Daikatana draws them.
- console: the console's six tiles (pics/loadscreens/con_0..5) become one
  640x480 ui/assets/dk/console.tga, laid out the way Daikatana draws them.
- the status bar icons become ui/assets/dk/hud/<name>.tga.
- the slider, scroll bar and arrow pictures the menu code loads by fixed
  name (ui/assets/slider2.tga and so on) get Daikatana's glyphs, and the
  cursor its first frame.

Daikatana's 8-bit art uses magenta (palette index 255) for transparent.
Needs ImageMagick's `magick` on the path.

usage: dkui_assets.py <dkres dir>
"""

import os
import struct
import subprocess
import sys

TRANSPARENT = "#FF00FF"

# fonts the menus and the hud use
FONTS = ["int_font", "int_font_bright", "statbar_font", "scr_cent", "con_font", "mainnums", "mainnumsred"]

# int_buttons glyphs (Daikatana's dk_menup.h), name -> code
BUTTON_GLYPHS = {
    "small_disabled": 0x01, "small_up": 0x02, "small_down": 0x03,
    "medium_disabled": 0x04, "medium_up": 0x05, "medium_down": 0x06,
    "long_disabled": 0x07, "long_up": 0x08, "long_down": 0x09,
    "slider_bar": 0x0A, "slider_thumb": 0x0B,
    "field_short": 0x0C, "field_wide": 0x0D,
    "up_disabled": 0x0E, "up_off": 0x0F, "up_on": 0x10,
    "down_disabled": 0x11, "down_off": 0x12, "down_on": 0x13,
    "left_disabled": 0x14, "left_off": 0x15, "left_on": 0x16,
    "right_disabled": 0x17, "right_off": 0x18, "right_on": 0x19,
    "back_disabled": 0x20, "back_up": 0x21, "back_down": 0x22,
}

# the arrows Daikatana prints over the toenails (l__language.h ARROW_*), in
# int_font, int_font_bright for the lit one
ARROW_GLYPHS = {"up": 0x81, "down": 0x8D, "left": 0x80, "right": 0x8E}

GLYPH_INFO = struct.Struct("<7i4fi32s")	# Spearmint 0.2 glyphInfo_t


def magick(*args):
    subprocess.run(["magick", *args], check=True)


def read_dkf(path):
    data = open(path, "rb").read()
    if data[:4] != b"dkf ":
        raise ValueError("%s is not a dkf font" % path)
    height = struct.unpack_from("<i", data, 8)[0]
    widths = data[12:12 + 256]
    xs = data[12 + 256:12 + 512]
    ys = data[12 + 512:12 + 768]
    return height, widths, xs, ys


def image_size(path):
    out = subprocess.run(["magick", "identify", "-format", "%w %h", path],
                         check=True, capture_output=True, text=True).stdout
    w, h = out.split()
    return int(w), int(h)


def to_tga(src, dst):
    """8-bit art to RGBA, magenta made transparent."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    magick(src, "-alpha", "set", "-fill", "none", "-opaque", TRANSPARENT, "-define", "tga:alpha", dst)


def write_font(dkres, name):
    src = os.path.join(dkres, "fonts", name + ".font.bmp")
    dkf = os.path.join(dkres, "fonts", name + ".dkf")
    if not os.path.exists(src) or not os.path.exists(dkf):
        print("skipping font", name)
        return
    height, widths, xs, ys = read_dkf(dkf)
    shader = "fonts/dk/" + name
    to_tga(src, os.path.join(dkres, shader + ".tga"))
    w, h = image_size(src)

    # the baseline sits a fifth of the way up the cell
    top = height - max(2, height // 5)

    out = bytearray()
    for c in range(256):
        cw = widths[c]
        if c == 0x20:
            cw = max(cw, height // 2)	# Daikatana's space is half the height
        if cw == 0:
            out += GLYPH_INFO.pack(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, b"")
            continue
        if c == 0x20:
            # space only advances
            out += GLYPH_INFO.pack(height, top, 0, 0, cw + 1, 0, 0, 0, 0, 0, 0, 0, shader.encode())
            continue
        s, t = xs[c] / w, ys[c] / h
        s2, t2 = (xs[c] + widths[c]) / w, (ys[c] + height) / h
        out += GLYPH_INFO.pack(height, top, 0, widths[c], cw + 1, widths[c], height,
                               s, t, s2, t2, 0, shader.encode())
    # text drawn at scale 1 is 48 points tall, as for Team Arena's fonts
    out += struct.pack("<f", 48.0 / height)
    out += ("fonts/dk/%s_%d.dat" % (name, height)).encode().ljust(64, b"\0")
    out += struct.pack("<ii", height, 0)

    dat = os.path.join(dkres, "fonts", "dk", "%s_%d.dat" % (name, height))
    open(dat, "wb").write(out)
    print("font", name, height, "->", dat)


def write_buttons(dkres):
    src = os.path.join(dkres, "fonts", "int_buttons.font.bmp")
    height, widths, xs, ys = read_dkf(os.path.join(dkres, "fonts", "int_buttons.dkf"))
    outdir = os.path.join(dkres, "ui", "assets", "dk", "buttons")
    os.makedirs(outdir, exist_ok=True)
    for name, c in BUTTON_GLYPHS.items():
        if not widths[c]:
            continue
        dst = os.path.join(outdir, name + ".tga")
        magick(src, "-crop", "%dx%d+%d+%d" % (widths[c], height, xs[c], ys[c]), "+repage",
               "-alpha", "set", "-fill", "none", "-opaque", TRANSPARENT, "-define", "tga:alpha", dst)

        # a toenail gets its arrow on it, as Daikatana's list arrows have;
        # the bare one is kept for the scroll bar's thumb
        way, _, state = name.partition("_")
        if name == "up_off":
            magick(dst, "-define", "tga:alpha", os.path.join(outdir, "toenail.tga"))
        if way in ARROW_GLYPHS:
            font = "int_font_bright" if state == "on" else "int_font"
            fh, fwidths, fxs, fys = read_dkf(os.path.join(dkres, "fonts", font + ".dkf"))
            g = ARROW_GLYPHS[way]
            if fwidths[g]:
                magick(dst, "(", os.path.join(dkres, "fonts", font + ".font.bmp"),
                       "-crop", "%dx%d+%d+%d" % (fwidths[g], fh, fxs[g], fys[g]), "+repage",
                       "-alpha", "set", "-fill", "none", "-opaque", TRANSPARENT, ")",
                       "-gravity", "center", "-composite", "-define", "tga:alpha", dst)
    print("buttons ->", outdir)


def write_background(dkres):
    tiles = os.path.join(dkres, "pics", "interface")
    rows = []
    for row in ("0", "1"):
        rows.append(["%s/back%s%d.bmp" % (tiles, row, col) for col in range(3)])
    dst = os.path.join(dkres, "ui", "assets", "dk", "background.tga")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    # 3x2 tiles of 256 make 768x512; Daikatana shows its top left 640x480
    magick("(", *rows[0], "+append", ")", "(", *rows[1], "+append", ")", "-append",
           "-crop", "640x480+0+0", "+repage", dst)
    print("background ->", dst)


def write_console(dkres):
    tiles = os.path.join(dkres, "pics", "loadscreens")
    row0 = ["%s/con_%d.bmp" % (tiles, i) for i in range(3)]
    row1 = ["%s/con_%d.bmp" % (tiles, i) for i in range(3, 6)]
    dst = os.path.join(dkres, "ui", "assets", "dk", "console.tga")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    # tiles 256, 256 and 128 wide make 640; Daikatana draws the second row
    # 224 below the first (console.cpp Con_DrawConsolePic), over its bottom
    magick("(", *row0, "+append", "-crop", "640x224+0+0", "+repage", ")",
           "(", *row1, "+append", ")", "-append", dst)
    print("console ->", dst)


# fixed asset names of the menu code (ui_shared.h) -> int_buttons glyph
FIXED_ASSETS = {
    "slider2": "slider_bar",
    "sliderbutt_1": "slider_thumb",
    "scrollbar_arrow_up_a": "up_on",
    "scrollbar_arrow_dwn_a": "down_on",
    "scrollbar_arrow_left": "left_on",
    "scrollbar_arrow_right": "right_on",
}


def write_fixed_assets(dkres):
    buttons = os.path.join(dkres, "ui", "assets", "dk", "buttons")
    assets = os.path.join(dkres, "ui", "assets")
    for name, glyph in FIXED_ASSETS.items():
        magick(os.path.join(buttons, glyph + ".tga"), "-define", "tga:alpha", os.path.join(assets, name + ".tga"))
    # the scroll bar track and thumb: the slider's bar and the plain "off" toenail
    magick(os.path.join(buttons, "slider_bar.tga"), "-rotate", "90", "-define", "tga:alpha",
           os.path.join(assets, "scrollbar.tga"))
    magick(os.path.join(buttons, "toenail.tga"), "-define", "tga:alpha", os.path.join(assets, "scrollbar_thumb.tga"))
    magick(os.path.join(dkres, "pics", "interface", "cursor_01.tga"), "-define", "tga:alpha",
           os.path.join(assets, "dk", "cursor.tga"))
    print("fixed assets ->", assets)


# the status bar's icons, 8-bit pictures with magenta for transparent
HUD_ICONS = ["armoricon", "healthicon", "ammoicon", "fragicon", "explevicon"]


def write_hud_icons(dkres):
    outdir = os.path.join(dkres, "ui", "assets", "dk", "hud")
    for name in HUD_ICONS:
        to_tga(os.path.join(dkres, "pics", "statusbar", name + ".bmp"), os.path.join(outdir, name + ".tga"))
    print("hud icons ->", outdir)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    dkres = sys.argv[1]
    for name in FONTS:
        write_font(dkres, name)
    write_buttons(dkres)
    write_fixed_assets(dkres)
    write_background(dkres)
    write_console(dkres)
    write_hud_icons(dkres)


if __name__ == "__main__":
    main()
