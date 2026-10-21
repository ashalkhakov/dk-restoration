#!/usr/bin/env python3
"""Writes shaders for the model skins with see-through texels.

Daikatana draws its models alpha tested: a skin's palette index 255 is a
hole (leaves, fences, hair). The skins exported from its .wal files keep
those texels at alpha 0, but a Quake 3 renderer only tests alpha when a
shader says so. Every skin under skins/ (and models/) with a texel of alpha 0
gets one: alpha tested, drawn from both sides (as foliage is).

usage: skin_shaders.py <dkres> <out.shader>
"""

import os
import struct
import sys


def tga_has_holes(path):
    d = open(path, "rb").read()
    if len(d) < 18:
        return False
    idlen, cmtype, itype = d[0], d[1], d[2]
    w, h = struct.unpack_from("<HH", d, 12)
    bpp = d[16]
    if bpp != 32 or itype not in (2, 10):
        return False
    p = 18 + idlen + (struct.unpack_from("<H", d, 5)[0] * ((d[7] + 7) // 8) if cmtype else 0)
    n = w * h
    if itype == 2:
        return any(d[p + 4 * i + 3] < 128 for i in range(n))
    seen = 0
    while seen < n and p < len(d):
        c = d[p]
        p += 1
        k = (c & 0x7f) + 1
        if c & 0x80:
            if d[p + 3] < 128:
                return True
            p += 4
        else:
            for j in range(k):
                if d[p + 4 * j + 3] < 128:
                    return True
            p += 4 * k
        seen += k
    return False


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    root, out = sys.argv[1:]
    names = []
    for top in ("skins", "models"):
        for dirpath, _, files in os.walk(os.path.join(root, top)):
            for f in files:
                if f.lower().endswith(".tga"):
                    path = os.path.join(dirpath, f)
                    if tga_has_holes(path):
                        names.append(os.path.relpath(path, root).replace(os.sep, "/"))
    names.sort()
    with open(out, "w") as fp:
        fp.write("// made by tools/models/skin_shaders.py: Daikatana's model skins with holes, alpha tested\n\n")
        for n in names:
            base = n[:-4]
            fp.write("%s\n{\n\tcull none\n\t{\n\t\tmap %s\n\t\talphaFunc GE128\n\t\trgbGen lightingDiffuse\n\t}\n}\n\n" % (base, n))
    print("%d skins with holes" % len(names))


if __name__ == "__main__":
    main()
