#!/usr/bin/env python3
"""A converted map's entities for q3map2 -light, and back.

  bsp_lights.py bake[-direct] <map.bsp> <dk.bsp> <out.bsp> <shaders> [cap scale [default cap [sky scale]]]
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
      the whole sky, as radiosity's sky. See-through faces (as their
      generated shaders draw them, scripts/*_gen.shader beside dk.bsp's
      maps/) cast no shadow, alpha-tested ones only where they're solid.
      bake-direct: the point lights alone (their direct light, the part
      the game draws dynamically: no surface lights or sky).
  bsp_lights.py subtract <a.bsp> <b.bsp> [<a lightmaps> <b lightmaps>]
      a.bsp's lightmaps less b.bsp's, laid out the same (q3map2
      -nocollapse): all the light less the point lights' direct light;
      external lightmaps (lm_NNNN.tga) in the folders given too.
  bsp_lights.py restore <map.bsp> <lit.bsp> [bounce]
      lit.bsp's entities and baking shaders back to map.bsp's (the game's
      again, after the bake); "bounce" marks the worldspawn
      "_bounceLightmaps", the point lights' direct light being left to the
      game.
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
    and its entity, brush entities casting no shadow"""
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
        # brush entities' faces lit as the world's, as Daikatana's qrad
        # lit them, casting no shadow
        lines.append("%d\n{\n\tentity 0\n" % i)
        if surfEntity.get(i, 0):
            lines.append("\tcastShadows 0\n")
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


def generated_shaders(dkBsp):
    """the converter's shaders (scripts/*_gen.shader), name: body"""
    import glob, os
    shaders = {}
    scripts = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(dkBsp))), "scripts")
    for path in glob.glob(os.path.join(scripts, "*_gen.shader")):
        text = open(path, encoding="latin-1").read()
        i = 0
        while True:
            m = re.compile(r"(\S+)\s*\{").search(text, i)
            if not m:
                break
            depth, j = 1, m.end()
            while depth and j < len(text):
                depth += {"{": 1, "}": -1}.get(text[j], 0)
                j += 1
            shaders[m.group(1).lower()] = text[m.end():j - 1]
            i = j
    return shaders


def surface_lights(lumps, dkBsp, shaderPath, skyScale, surfaceLights=True):
    """the bake's own shaders, "<shader>__lb...": surface lights (and the
    sky's), see-through faces casting no shadow (alpha-tested ones only
    where solid); restore() puts the surfaces back on theirs. Without
    surfaceLights the same shaders give no light, so that q3map2 lays the
    lightmaps out the same (it sorts by shader)"""
    names = shader_names(lumps)
    generated = generated_shaders(dkBsp)
    lights = dk_face_lights(dkBsp)
    added = {}
    text = []
    for face in range(len(lumps[13]) // 104):
        shader = struct.unpack_from("<i", lumps[13], face * 104)[0]
        body = generated.get(names[shader].lower(), "")
        lowered = body.lower()
        kind = "a" if "alphafunc" in lowered else "t" if "blendfunc" in lowered and "skyparms" not in lowered else ""
        light = lights.get(face)
        if not kind and not light:
            continue
        name = names[shader] + "__lb" + ("_lv%d" % light[2] if light else "") + ("_" + kind if kind else "")
        if name not in added:
            added[name] = len(names)
            names.append(name)
            lumps[1] += name.encode("latin-1").ljust(64, b"\0")[:64] + lumps[1][shader * 72 + 64:shader * 72 + 72]
            lines = []
            if light:
                texture, flags, value = light
                lines.append("\tq3map_lightImage textures/%s.tga\n" % texture)
                if flags & SURF_SKY:
                    if surfaceLights:
                        lines.append("\tq3map_skyLight %g 3\n" % (value * skyScale))
                    lines += ["\tsurfaceparm sky\n", "\tsurfaceparm noimpact\n", "\tsurfaceparm nolightmap\n"]
                elif surfaceLights:
                    lines.append("\tq3map_surfaceLight %d\n" % value)
                    if not body:
                        lines.append("\t{\n\t\tmap textures/%s.tga\n\t}\n" % texture)
            if kind == "t":
                lines += ["\tsurfaceparm trans\n", "\tsurfaceparm nolightmap\n"]
            elif kind == "a":
                lines += ["\tsurfaceparm trans\n", "\tq3map_alphaShadow\n"]
            text.append("%s\n{\n%s%s\n}\n" % (name, "".join(lines), body))
        struct.pack_into("<i", lumps[13], face * 104, added[name])
    open(shaderPath, "w").write("".join(text))
    return len(added)


def bake(src, dkBsp, dst, shaderPath, capScale=1.0, defaultCap=0.0, skyScale=1.0, direct=False):
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
    surfaceShaders = surface_lights(lumps, dkBsp, shaderPath, skyScale, not direct)
    write_bsp(dst, version, lumps)
    surface_file(lumps, ents, dst[:-4] + ".srf")
    print("%s: %d lights, %d surface light shaders" % (dst, len(lights), surfaceShaders))


def subtract(a, b, aDir=None, bDir=None):
    import os
    version, la = read_bsp(a)
    _, lb = read_bsp(b)
    # the same layout: each surface's lightmap and its vertexes' places in it
    for i in range(len(la[13]) // 104):
        if la[13][i * 104 + 28:i * 104 + 48] != lb[13][i * 104 + 28:i * 104 + 48]:
            sys.exit("%s and %s: surface %d's lightmaps differ in place" % (a, b, i))
    for v in range(len(la[10]) // 44):
        if la[10][v * 44 + 20:v * 44 + 28] != lb[10][v * 44 + 20:v * 44 + 28]:
            sys.exit("%s and %s: vertex %d's lightmap place differs" % (a, b, v))
    la[14] = bytes(max(0, x - y) for x, y in zip(la[14], lb[14]))
    write_bsp(a, version, la)
    if aDir and os.path.isdir(aDir):
        for f in sorted(os.listdir(aDir)):
            if not f.endswith(".tga"):
                continue
            da = open(os.path.join(aDir, f), "rb").read()
            db = open(os.path.join(bDir, f), "rb").read()
            if len(da) != len(db):
                sys.exit("%s: sizes differ" % f)
            open(os.path.join(aDir, f), "wb").write(da[:18] + bytes(max(0, x - y) for x, y in zip(da[18:], db[18:])))


def restore(src, dst, bounce=False):
    _, orig = read_bsp(src)
    version, lumps = read_bsp(dst)
    lumps[0] = orig[0]
    if bounce and b"_bounceLightmaps" not in orig[0]:
        text = orig[0].decode("latin-1").rstrip("\0")
        brace = text.index("{") + 1
        lumps[0] = (text[:brace] + '\n"_bounceLightmaps" "1"' + text[brace:] + "\0").encode("latin-1")
    # the baking shaders' surfaces back on theirs
    names = shader_names(lumps)
    origNames = shader_names(orig)
    lumps[13] = bytearray(lumps[13])
    for i in range(len(lumps[13]) // 104):
        shader = struct.unpack_from("<i", lumps[13], i * 104)[0]
        if "__lb" in names[shader]:
            want = origNames[struct.unpack_from("<i", orig[13], i * 104)[0]]
            if want not in names:
                names.append(want)
                lumps[1] += orig[1][origNames.index(want) * 72:origNames.index(want) * 72 + 72]
            struct.pack_into("<i", lumps[13], i * 104, names.index(want))
    write_bsp(dst, version, lumps)


if __name__ == "__main__":
    if len(sys.argv) in (6, 7, 8, 9) and sys.argv[1] in ("bake", "bake-direct"):
        bake(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], *[float(a) for a in sys.argv[6:]],
             direct=sys.argv[1] == "bake-direct")
    elif len(sys.argv) in (4, 6) and sys.argv[1] == "subtract":
        subtract(*sys.argv[2:])
    elif len(sys.argv) in (4, 5) and sys.argv[1] == "restore":
        restore(sys.argv[2], sys.argv[3], len(sys.argv) == 5 and sys.argv[4] == "bounce")
    else:
        sys.exit(__doc__)
