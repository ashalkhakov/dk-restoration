#!/usr/bin/env python3
"""Writes a map's textured ladders' rungs: maps/<map>.ladders.

Some of Daikatana's ladders draw their rungs with an alpha tested texture on
a flat face (e1m1b's "ladderm"): no trace can find them, so the game reads
them from this file to put a climber's hands and feet on them. Every drawn
face with an alpha tested texture drawn on a ladder brush is read: the
texture's opaque rows (or columns) that cross it are rungs, mapped through
the face's texture coordinates to world heights.

A line a face:
    <normal x y z> <mins x y z> <maxs x y z> <rung height>...

usage: ladder_rungs.py <map.bsp> <shader dir> <texture root> <out.ladders>
"""

import math
import os
import re
import struct
import sys

SURF_LADDER = 0x8
MST_PLANAR = 1
OPAQUE = 128            # alphaFunc GE128
RUNG_FILL = 0.6         # of a row's texels opaque for it to be a rung's


def read_tga_alpha(path):
    """A TGA's alpha as rows of 0..255 (top row first), or None."""
    d = open(path, "rb").read()
    idlen, cmtype, itype = d[0], d[1], d[2]
    w, h = struct.unpack_from("<HH", d, 12)
    bpp, desc = d[16], d[17]
    if bpp != 32 or itype not in (2, 10):
        return None
    p = 18 + idlen + (struct.unpack_from("<H", d, 5)[0] * ((d[7] + 7) // 8) if cmtype else 0)
    px = []
    if itype == 2:
        px = [d[p + 4 * i + 3] for i in range(w * h)]
    else:
        while len(px) < w * h:
            c = d[p]
            p += 1
            n = (c & 0x7f) + 1
            if c & 0x80:
                px += [d[p + 3]] * n
                p += 4
            else:
                px += [d[p + 4 * k + 3] for k in range(n)]
                p += 4 * n
    rows = [px[y * w:(y + 1) * w] for y in range(h)]
    if not desc & 0x20:     # bottom-up
        rows.reverse()
    return rows


def alpha_shaders(shader_dir):
    """Shader name -> the image of its alpha tested stage."""
    out = {}
    for name in os.listdir(shader_dir):
        if not name.endswith(".shader"):
            continue
        text = open(os.path.join(shader_dir, name), encoding="latin-1").read()
        for m in re.finditer(r"^(\S+)\s*\{(.*?)^\}", text, re.M | re.S):
            body = m.group(2)
            if re.search(r"alphaFunc", body, re.I):
                image = re.search(r"\bmap\s+(\S+)", body)
                if image:
                    out[m.group(1).lower()] = image.group(1)
    return out


def rung_centres(alpha, by_rows):
    """Where across the texture (0..1) its rungs' middles are: runs of rows
    (or columns) mostly opaque."""
    lines = alpha if by_rows else [list(c) for c in zip(*alpha)]
    n = len(lines)
    solid = [sum(1 for a in line if a >= OPAQUE) >= RUNG_FILL * len(line) for line in lines]
    if all(solid) or not any(solid):
        return []
    out, start = [], None
    for i in range(n + 1):
        s = i < n and solid[i]
        if s and start is None:
            start = i
        elif not s and start is not None:
            out.append((start + i) / 2.0 / n)
            start = None
    return out


def main():
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    bsp, shader_dir, root, out_path = sys.argv[1:]
    d = open(bsp, "rb").read()
    lumps = [struct.unpack_from("<2i", d, 8 + 8 * i) for i in range(17)]
    so, sl = lumps[1]
    shaders = [struct.unpack_from("<64s2i", d, so + 72 * i) for i in range(sl // 72)]
    names = [s[0].split(b"\0")[0].decode("latin-1").lower() for s in shaders]
    po, _ = lumps[2]
    bo, bl = lumps[8]
    sdo, _ = lumps[9]
    vo, _ = lumps[10]
    sfo, sfl = lumps[13]

    # the ladder brushes' bounds
    ladders = []
    for b in range(bl // 12):
        fs, ns, sh = struct.unpack_from("<3i", d, bo + 12 * b)
        sides = [struct.unpack_from("<2i", d, sdo + 8 * (fs + k)) for k in range(ns)]
        if not any(shaders[s][1] & SURF_LADDER for p, s in sides):
            continue
        lo, hi = [-1e9] * 3, [1e9] * 3
        for pl, s in sides:
            nx, ny, nz, dist = struct.unpack_from("<4f", d, po + 16 * pl)
            for c, v in enumerate((nx, ny, nz)):
                if abs(abs(v) - 1) < 1e-3:
                    if v > 0:
                        hi[c] = min(hi[c], dist)
                    else:
                        lo[c] = max(lo[c], -dist)
        ladders.append((lo, hi))

    images = alpha_shaders(shader_dir)
    alphas = {}
    lines = []
    for k in range(sfl // 104):
        sh, fog, typ, fv, nv = struct.unpack_from("<5i", d, sfo + 104 * k)
        if typ != MST_PLANAR or nv < 3 or names[sh] not in images:
            continue
        verts = [struct.unpack_from("<3f2f", d, vo + 44 * (fv + j)) for j in range(nv)]
        lo = [min(v[c] for v in verts) for c in range(3)]
        hi = [max(v[c] for v in verts) for c in range(3)]
        # drawn on a ladder brush (a fence or grate beside one isn't one)
        if not any(all(l[0][c] - 1 <= lo[c] and hi[c] <= l[1][c] + 1 for c in range(3)) for l in ladders):
            continue
        normal = struct.unpack_from("<3f", d, sfo + 104 * k + 84)
        if abs(normal[2]) > 0.5:
            continue        # a ladder's rungs are on a wall, not a floor
        image = images[names[sh]]
        if image not in alphas:
            path = os.path.join(root, os.path.splitext(image)[0] + ".tga")
            alphas[image] = read_tga_alpha(path) if os.path.exists(path) else None
        alpha = alphas[image]
        if not alpha:
            continue

        # z as an affine function of (s, t), from three of the face's corners
        a, b, c = verts[0], verts[1], verts[2]
        det = (b[3] - a[3]) * (c[4] - a[4]) - (c[3] - a[3]) * (b[4] - a[4])
        if abs(det) < 1e-9:
            continue
        dzds = ((b[2] - a[2]) * (c[4] - a[4]) - (c[2] - a[2]) * (b[4] - a[4])) / det
        dzdt = ((c[2] - a[2]) * (b[3] - a[3]) - (b[2] - a[2]) * (c[3] - a[3])) / det
        by_rows = abs(dzdt) >= abs(dzds)      # rungs across the way up the texture
        centres = rung_centres(alpha, by_rows)
        if not centres:
            continue
        coords = [v[4] if by_rows else v[3] for v in verts]
        other = [v[3] if by_rows else v[4] for v in verts]
        cmin, cmax = min(coords), max(coords)
        omid = 0.5 * (min(other) + max(other))
        grad = dzdt if by_rows else dzds
        ograd = dzds if by_rows else dzdt
        za = a[2] - dzds * a[3] - dzdt * a[4]
        rungs = []
        for tile in range(math.floor(cmin), math.ceil(cmax) + 1):
            for f in centres:
                t = tile + f
                if cmin <= t <= cmax:
                    rungs.append(round(za + grad * t + ograd * omid, 1))
        if rungs:
            if os.environ.get("LADDER_DEBUG"):
                print(names[sh], ["%.0f" % x for x in lo + hi], sorted(rungs)[:4])     # which faces, which rungs
            lines.append(" ".join("%.3f" % x for x in normal) + " " + " ".join("%.1f" % x for x in lo + hi)
                         + " " + " ".join("%.1f" % z for z in sorted(rungs)))
    with open(out_path, "w") as fp:
        fp.write("".join(line + "\n" for line in lines))
    print("%d textured ladder faces" % len(lines))


if __name__ == "__main__":
    main()
