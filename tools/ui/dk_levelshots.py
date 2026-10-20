#!/usr/bin/env python3
"""Makes Quake 3 levelshots from Daikatana's loading screens.

Quake 3 shows levelshots/<map> while a map loads and levelshots/<map>_small
in the map lists. Daikatana keeps its loading screens as six 8-bit tiles,
pics/loadscreens/<name>_0..5.bmp (256, 256 and 128 pixels wide, 256 high,
for cards that couldn't take bigger textures), drawn in two rows at y 0 and
224 of its 640x480 screen. This puts each map's tiles together into one
640x480 picture.

Which screen a map gets is Daikatana's choice (cl_main.cpp, console.cpp):
the first part of a level ("e1m1a") shows the screen its worldspawn names
with "loadscreen", or "gen" without one; every other map shows "con".

Needs ImageMagick's `magick` on the path.

usage: dk_levelshots.py <dkres dir>
"""

import os
import re
import struct
import subprocess
import sys

TILE_X = (0, 256, 512)
TILE_Y = (0, 224)
SMALL = "128x96"


def worldspawn_key(bsp_path, key):
    data = open(bsp_path, "rb").read()
    if data[:4] != b"IBSP":
        return None
    ofs, length = struct.unpack_from("<ii", data, 8)	# lump 0: entities
    ents = data[ofs:ofs + length].decode("latin1")
    world = re.search(r"\{[^{}]*\}", ents)
    if not world:
        return None
    m = re.search(r'"%s"\s+"([^"]*)"' % re.escape(key), world.group(0))
    return m.group(1) if m else None


def screen_for_map(dkres, mapname):
    def exists(name):
        return os.path.exists(os.path.join(dkres, "pics", "loadscreens", "%s_0.bmp" % name))

    if not mapname.endswith("a"):
        return "con"
    name = worldspawn_key(os.path.join(dkres, "maps", mapname + ".bsp"), "loadscreen")
    if name and exists(name):
        return name
    return "gen"


def compose(dkres, screen, dst):
    args = ["-size", "640x480", "xc:black"]
    index = 0
    for y in TILE_Y:
        for x in TILE_X:
            tile = os.path.join(dkres, "pics", "loadscreens", "%s_%d.bmp" % (screen, index))
            index += 1
            if os.path.exists(tile):
                args += [tile, "-geometry", "+%d+%d" % (x, y), "-composite"]
    subprocess.run(["magick", *args, "-type", "TrueColor", dst], check=True)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    dkres = sys.argv[1]
    outdir = os.path.join(dkres, "levelshots")
    os.makedirs(outdir, exist_ok=True)

    made = {}
    for name in sorted(os.listdir(os.path.join(dkres, "maps"))):
        if not name.endswith(".bsp"):
            continue
        mapname = name[:-4]
        screen = screen_for_map(dkres, mapname)
        if screen not in made:
            made[screen] = os.path.join(outdir, "_%s.tga" % screen)
            compose(dkres, screen, made[screen])
        dst = os.path.join(outdir, mapname + ".tga")
        subprocess.run(["magick", made[screen], dst], check=True)
        subprocess.run(["magick", made[screen], "-resize", SMALL + "!", os.path.join(outdir, mapname + "_small.tga")],
                       check=True)
        print(mapname, "->", screen)
    for path in made.values():
        os.remove(path)


if __name__ == "__main__":
    main()
