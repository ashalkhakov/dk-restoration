#!/usr/bin/env python3
"""A converted map's entities for q3map2 -light, and back.

  bsp_lights.py bake <map.bsp> <dk.bsp> <out.bsp> <shaders> [cap scale [default cap [sky scale]]]
      out.bsp with Daikatana's static lights as q3map2's: each constant,
      untargeted "dlight" the converter made of a "light" (bsp-sekai's
      dkent_light) gets a "light" beside it, falling off linearly as
      Daikatana's qrad did. And out.srf, the surfaces' lightmap axes and
      entities, which q3map2 -bsp would have written.
      A light's "cap" (Daikatana's, its most light anywhere, as it seems)
      is taken as q3map2's linear light starting at cap * cap scale (1 if
      not given; 0 ignores caps) and fading to 0 at its "light"; lights
      without one have the default cap, if given.
      And Daikatana's surface lights (its faces' SURF_LIGHT and value, from
      its own BSP, dk.bsp: the converter makes a surface of each face, in
      order): their surfaces get shaders of their own, "<shader>_lv<value>",
      written to the shader file given, with q3map_surfaceLight; the sky's
      as q3map_skyLight (value * sky scale, 1 if not given), light from
      the whole sky, as radiosity's sky.
  bsp_lights.py restore <map.bsp> <lit.bsp>
      lit.bsp's entities and surface light shaders back to map.bsp's (the
      game's again, after the bake).
"""
import re
import struct
import sys

NUM_LUMPS = 17


def read_bsp(path):
    data = open(path, "rb").read()
    ident, version = struct.unpack_from("<4si", data, 0)
    if ident != b"IBSP":
        sys.exit("%s: not a Quake 3 BSP" % path)
    lumps = []
    for i in range(NUM_LUMPS):
        ofs, length = struct.unpack_from("<ii", data, 8 + i * 8)
        lumps.append(data[ofs:ofs + length])
    return version, lumps


def write_bsp(path, version, lumps):
    out = bytearray(struct.pack("<4si", b"IBSP", version))
    out += bytes(NUM_LUMPS * 8)
    for i, lump in enumerate(lumps):
        while len(out) % 4:
            out += b"\0"
        struct.pack_into("<ii", out, 8 + i * 8, len(out), len(lump))
        out += lump
    open(path, "wb").write(out)


def parse_entities(text):
    return [dict(re.findall(r'"([^"]*)"\s+"([^"]*)"', body)) for body in re.findall(r"\{([^{}]*)\}", text)]


def entities_text(ents):
    return "".join("{\n" + "".join('"%s" "%s"\n' % kv for kv in e.items()) + "}\n" for e in ents) + "\0"


def surface_file(lumps, ents, path):
    """q3map2's .srf: each surface's lightmap axis (its plane's normal; a
    soup's average vertex normal; none for a patch, which q3map2 works out)
    and its entity"""
    models = {}
    for n, e in enumerate(ents):
        if e.get("model", "").startswith("*"):
            models[int(e["model"][1:])] = n
    surfEntity = {}
    for m in range(len(lumps[7]) // 40):
        first, count = struct.unpack_from("<ii", lumps[7], m * 40 + 24)
        for i in range(first, first + count):
            surfEntity[i] = models.get(m, 0)
    verts = lumps[10]
    lines = ["default\n{\n}\n"]
    for i in range(len(lumps[13]) // 104):
        f = struct.unpack_from("<12i12f2i", lumps[13], i * 104)
        stype, firstVert, numVerts = f[2], f[3], f[4]
        axis = None
        if stype == 1:
            axis = f[21:24]
        elif stype == 3:
            n = [0.0, 0.0, 0.0]
            for v in range(firstVert, firstVert + numVerts):
                vn = struct.unpack_from("<3f", verts, v * 44 + 28)
                n = [a + b for a, b in zip(n, vn)]
            length = sum(c * c for c in n) ** 0.5
            axis = [c / length for c in n] if length > 0 else None
        lines.append("%d\n{\n\tentity %d\n" % (i, surfEntity.get(i, 0)))
        if axis:
            lines.append("\tlightmapAxis ( %f %f %f )\n" % tuple(axis))
        lines.append("}\n")
    open(path, "w").write("".join(lines))


SURF_LIGHT = 1
SURF_SKY = 4


def dk_face_lights(path):
    """each face's (texture, flags, value) where it gives light, by face"""
    data = open(path, "rb").read()
    tofs, tlen = struct.unpack_from("<ii", data, 8 + 5 * 8)
    fofs, flen = struct.unpack_from("<ii", data, 8 + 6 * 8)
    lights = {}
    for i in range(flen // 20):
        texinfo = struct.unpack_from("<H", data, fofs + i * 20 + 10)[0]
        t = tofs + texinfo * 76
        flags, value = struct.unpack_from("<ii", data, t + 32)
        if flags & SURF_LIGHT and value > 0:
            lights[i] = (data[t + 40:t + 72].split(b"\0")[0].decode("latin-1"), flags, value)
    return lights


def shader_names(lumps):
    return [lumps[1][i:i + 64].split(b"\0")[0].decode("latin-1") for i in range(0, len(lumps[1]), 72)]


def surface_lights(lumps, dkBsp, shaderPath, skyScale):
    names = shader_names(lumps)
    added = {}
    text = []
    for face, (texture, flags, value) in sorted(dk_face_lights(dkBsp).items()):
        shader = struct.unpack_from("<i", lumps[13], face * 104)[0]
        name = "%s_lv%d" % (names[shader], value)
        if name not in added:
            added[name] = len(names)
            names.append(name)
            lumps[1] += lumps[1][shader * 72:shader * 72 + 64].replace(
                names[shader].encode("latin-1"), name.encode("latin-1")).ljust(64, b"\0")[:64]
            lumps[1] += lumps[1][shader * 72 + 64:shader * 72 + 72]
            body = ["\tq3map_lightImage textures/%s.tga\n" % texture]
            if flags & SURF_SKY:
                body += ["\tq3map_skyLight %g 3\n" % (value * skyScale),
                         "\tsurfaceparm sky\n", "\tsurfaceparm noimpact\n", "\tsurfaceparm nolightmap\n"]
            else:
                body += ["\tq3map_surfaceLight %d\n" % value, "\t{\n\t\tmap textures/%s.tga\n\t}\n" % texture]
            text.append("%s\n{\n%s}\n" % (name, "".join(body)))
        struct.pack_into("<i", lumps[13], face * 104, added[name])
    open(shaderPath, "w").write("".join(text))
    return len(added)


def bake(src, dkBsp, dst, shaderPath, capScale=1.0, defaultCap=0.0, skyScale=1.0):
    version, lumps = read_bsp(src)
    lumps[13] = bytearray(lumps[13])
    ents = parse_entities(lumps[0].decode("latin-1").rstrip("\0"))
    lights = []
    for e in ents:
        if e.get("classname") != "dlight" or e.get("stylestring", "a") != "a":
            continue
        if e.get("targetname") or e.get("style"):
            continue		# switched or flickering: stays dynamic
        # linear, the colour as it is: 0.9375 * light - distance * fade
        # (q3map2's pointScale / linearScale), as qrad's light - distance
        reach = float(e.get("light", "300"))
        light = {"classname": "light", "origin": e["origin"], "light": "%g" % reach,
                 "_color": e.get("color", "1 1 1"), "spawnflags": "33"}
        cap = float(e.get("cap", defaultCap)) * capScale
        if cap > 0 and cap < reach:
            light["light"] = "%g" % ( cap / 0.9375 )
            light["fade"] = "%g" % ( cap / reach )
        lights.append(light)
    lumps[0] = entities_text(ents + lights).encode("latin-1")
    surfaceShaders = surface_lights(lumps, dkBsp, shaderPath, skyScale)
    write_bsp(dst, version, lumps)
    surface_file(lumps, ents, dst[:-4] + ".srf")
    print("%s: %d lights, %d surface light shaders" % (dst, len(lights), surfaceShaders))


def restore(src, dst):
    _, orig = read_bsp(src)
    version, lumps = read_bsp(dst)
    lumps[0] = orig[0]
    # the surface lights' surfaces back on their shaders
    names = shader_names(lumps)
    origNames = shader_names(orig)
    lumps[13] = bytearray(lumps[13])
    for i in range(len(lumps[13]) // 104):
        shader = struct.unpack_from("<i", lumps[13], i * 104)[0]
        if re.search(r"_lv\d+$", names[shader]):
            want = origNames[struct.unpack_from("<i", orig[13], i * 104)[0]]
            if want not in names:
                names.append(want)
                lumps[1] += orig[1][origNames.index(want) * 72:origNames.index(want) * 72 + 72]
            struct.pack_into("<i", lumps[13], i * 104, names.index(want))
    write_bsp(dst, version, lumps)


if __name__ == "__main__":
    if len(sys.argv) in (6, 7, 8, 9) and sys.argv[1] == "bake":
        bake(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], *[float(a) for a in sys.argv[6:]])
    elif len(sys.argv) == 4 and sys.argv[1] == "restore":
        restore(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
