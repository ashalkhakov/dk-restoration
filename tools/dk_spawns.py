#!/usr/bin/env python3
"""Prints the spawn points of a Quake 3 BSP, one "x y z yaw" a line.

The dk script uses them to place the camera for screenshots and tests.

usage: dk_spawns.py <map.bsp> [count]
"""

import re
import struct
import sys

CLASSES = ("info_player_deathmatch", "info_player_start")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    data = open(sys.argv[1], "rb").read()
    ofs, length = struct.unpack_from("<ii", data, 8)	# lump 0: entities
    ents = data[ofs:ofs + length].decode("latin1")

    found = 0
    for ent in re.findall(r"\{[^{}]*\}", ents):
        classname = re.search(r'"classname"\s+"([^"]*)"', ent)
        if not classname or classname.group(1) not in CLASSES:
            continue
        origin = re.search(r'"origin"\s+"([^"]*)"', ent)
        angle = re.search(r'"angle"\s+"([^"]*)"', ent)
        if not origin:
            continue
        print(origin.group(1), angle.group(1) if angle else "0")
        found += 1
        if found == count:
            break


if __name__ == "__main__":
    main()
