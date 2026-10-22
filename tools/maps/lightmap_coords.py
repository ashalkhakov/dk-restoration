#!/usr/bin/env python3
"""Where a map's baked lightmaps go on it, kept apart from Daikatana's map
(lightmaps/<map>.lmcoords in the repository, beside the lightmaps
themselves, lightmaps/<map>/lm_NNNN), so a map converted again gets its
light back without baking again.

  lightmap_coords.py save <map.bsp> <out.lmcoords>
      the baked map's: each surface's lightmap and place in it, each
      vertex's lightmap coordinates and colour, its light grid lump, and a
      fingerprint of the geometry they belong to
  lightmap_coords.py apply <map.bsp> <in.lmcoords>
      those into the map converted again, its lightmaps external (rend2
      loads maps/<map>/lm_NNNN by itself), when its geometry is the same;
      worldspawn "_bounceLightmaps" as the bake left it
"""
import hashlib
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bsp_lights as bsp  # noqa: E402

MAGIC = b"DKLC"
VERSION = 1
SURFACE_SIZE = 104
VERTEX_SIZE = 44


def fingerprint(lumps):
    """the geometry the light belongs to: vertex positions and surfaces'
    layouts (not their lightmaps)"""
    h = hashlib.sha1()
    verts = lumps[10]
    for v in range(len(verts) // VERTEX_SIZE):
        h.update(verts[v * VERTEX_SIZE:v * VERTEX_SIZE + 12])
    surfaces = lumps[13]
    for i in range(len(surfaces) // SURFACE_SIZE):
        h.update(surfaces[i * SURFACE_SIZE + 8:i * SURFACE_SIZE + 28])
    return h.digest()


def chunks(blobs):
    return b"".join(struct.pack("<I", len(b)) + b for b in blobs)


def unchunk(data):
    blobs, i = [], 0
    while i < len(data):
        n = struct.unpack_from("<I", data, i)[0]
        blobs.append(data[i + 4:i + 4 + n])
        i += 4 + n
    return blobs


def save(src, dst):
    _, lumps = bsp.read_bsp(src)
    surfaces, verts = lumps[13], lumps[10]
    places = b"".join(surfaces[i * SURFACE_SIZE + 28:i * SURFACE_SIZE + 96]
                      for i in range(len(surfaces) // SURFACE_SIZE))
    vertexLight = b"".join(verts[v * VERTEX_SIZE + 20:v * VERTEX_SIZE + 28] + verts[v * VERTEX_SIZE + 40:v * VERTEX_SIZE + 44]
                           for v in range(len(verts) // VERTEX_SIZE))
    if lumps[14]:
        sys.exit("%s: its lightmaps are in it, not external (q3map2 -external)" % src)
    bounce = b"1" if b'"_bounceLightmaps" "1"' in lumps[0] else b"0"
    body = chunks([fingerprint(lumps), bounce, lumps[15], places, vertexLight])
    open(dst, "wb").write(MAGIC + struct.pack("<i", VERSION) + zlib.compress(body, 9))
    print("%s: %d KB" % (dst, os.path.getsize(dst) // 1024))


def apply(dstBsp, src):
    data = open(src, "rb").read()
    if data[:4] != MAGIC or struct.unpack_from("<i", data, 4)[0] != VERSION:
        sys.exit("%s: not lightmap coordinates of this version" % src)
    finger, bounce, grid, places, vertexLight = unchunk(zlib.decompress(data[8:]))
    version, lumps = bsp.read_bsp(dstBsp)
    if fingerprint(lumps) != finger:
        sys.exit("%s: the map's geometry has changed since it was baked; bake it again (./dk lightmaps)" % src)
    lumps[14], lumps[15] = b"", grid
    surfaces, verts = bytearray(lumps[13]), bytearray(lumps[10])
    for i in range(len(surfaces) // SURFACE_SIZE):
        surfaces[i * SURFACE_SIZE + 28:i * SURFACE_SIZE + 96] = places[i * 68:i * 68 + 68]
    for v in range(len(verts) // VERTEX_SIZE):
        verts[v * VERTEX_SIZE + 20:v * VERTEX_SIZE + 28] = vertexLight[v * 12:v * 12 + 8]
        verts[v * VERTEX_SIZE + 40:v * VERTEX_SIZE + 44] = vertexLight[v * 12 + 8:v * 12 + 12]
    lumps[13], lumps[10] = bytes(surfaces), bytes(verts)
    if bounce == b"1" and b"_bounceLightmaps" not in lumps[0]:
        text = lumps[0].decode("latin-1").rstrip("\0")
        brace = text.index("{") + 1
        lumps[0] = (text[:brace] + '\n"_bounceLightmaps" "1"' + text[brace:] + "\0").encode("latin-1")
    bsp.write_bsp(dstBsp, version, lumps)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "save":
        save(*sys.argv[2:])
    elif len(sys.argv) == 4 and sys.argv[1] == "apply":
        apply(*sys.argv[2:])
    else:
        sys.exit(__doc__)
