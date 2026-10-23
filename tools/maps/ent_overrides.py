#!/usr/bin/env python3
"""A converted map's entities changed by hand: maps/<map>.ent in the
repository, applied by ./dk convert to the map as the converter wrote it.
The converter turns Daikatana's entities into ours; what a map needs beyond
that (a body where a cinematic shows it, an entity taken out) is written
here, not taught to the converter.

  ent_overrides.py <map.bsp> <map.ent>

The file is entity blocks, as a map's, // comments. A block is one of:

  an addition: no "_match" keys; the block is the new entity
      { "classname" "misc_character" "origin" "1 2 3" ... }

  a change: "_match <key>" keys find the entity (all must be equal; exactly
  one entity must have them); the other keys are set on it, a key set to
  "" taken off
      { "_match classname" "misc_gamemodel" "_match model" "models/x.md3"
        "angle" "90" }

  a deletion: the same, with "_delete" "1"
      { "_match classname" "misc_gamemodel" "_match model" "models/x.md3"
        "_delete" "1" }

The blocks apply in order. One that finds no entity, or more than one, is an
error: the map has changed under it.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bsp_lights as bsp  # noqa: E402


def blocks(path):
    text = re.sub(r"//[^\n]*", "", open(path).read())
    out = []
    for n, body in enumerate(re.findall(r"\{([^{}]*)\}", text), 1):
        pairs = re.findall(r'"([^"]*)"\s+"([^"]*)"', body)
        out.append((n, pairs))
    return out


def apply(bspPath, entPath):
    version, lumps = bsp.read_bsp(bspPath)
    ents = bsp.parse_entities(lumps[0].decode("latin-1").rstrip("\0"))
    added = changed = deleted = 0
    for n, pairs in blocks(entPath):
        match = {k[len("_match "):]: v for k, v in pairs if k.startswith("_match ")}
        delete = any(k == "_delete" and v not in ("", "0") for k, v in pairs)
        keys = [(k, v) for k, v in pairs if not k.startswith("_match ") and k != "_delete"]
        if not match:
            if delete:
                sys.exit("%s: block %d deletes without \"_match\" keys" % (entPath, n))
            ents.append(dict(keys))
            added += 1
            continue
        found = [e for e in ents if all(e.get(k) == v for k, v in match.items())]
        if len(found) != 1:
            sys.exit("%s: block %d matches %d entities, not one: %s" % (entPath, n, len(found), match))
        e = found[0]
        if delete:
            ents.remove(e)
            deleted += 1
            continue
        for k, v in keys:
            if v == "":
                e.pop(k, None)
            else:
                e[k] = v
        changed += 1
    lumps[0] = bsp.entities_text(ents).encode("latin-1")
    bsp.write_bsp(bspPath, version, lumps)
    print("%s: %d added, %d changed, %d deleted (%s)" % (os.path.basename(bspPath), added, changed, deleted,
                                                         os.path.basename(entPath)))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    apply(sys.argv[1], sys.argv[2])
