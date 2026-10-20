# Bot and monster navigation (AAS)

Bots find their way with Quake 3's AAS (area awareness system): a map's walkable space cut into convex areas, with
reachabilities (walk, jump, ladder, swim, teleport…) between them. Monsters will use it too. Like RTCW, which kept
Quake 3's AAS for its monsters, a map has an AAS world per creature size, each its own file:

| World | File | Box (Doom 3 would say `aas48`…) | For |
| --- | --- | --- | --- |
| standard | `maps/<map>.aas` | 30×30×56, crouched 30×30×40 | bots, and monsters the player's size |
| large | `maps/<map>_large.aas` | 64×64×96 | large monsters |
| xxl | `maps/<map>_xxl.aas` | 128×128×160 | the biggest |

The boxes and the movement settings are `tools/aas/<size>.cfg` (bspc configurations, Quake 3's defaults with
ladders allowed, which Daikatana's maps have, and the characters' speeds: running 130, crouching 33, swimming 65 —
the reachabilities, jumps above all, depend on them; rebuild the worlds when they change).

```
./dk build bspc       # once
./dk aas              # every map's worlds into out/maps (about 40 s a map)
./dk aas e1dm1        # one
```

`./dk aas` runs after `./dk convert`: it compiles the converted BSPs.

## In the game

The botlib (in mint-arena's game module) loads every world a map has. The standard one must be there for bots; the
others are optional, and Quake 3's own maps have only theirs. Entities are linked into every world. The AAS calls work on
the current world: `trap_AAS_SetCurrentWorld( AASWORLD_LARGE )` before a large monster's routing or movement,
`AASWORLD_STANDARD` after it (botlib/be_aas.h). A world's traces use its own box (`AAS_PresenceTypeBoundingBox` reads
the file's).

`addbot Hiro` / `addbot Mikiko` (`scripts/dk.bot`) play on every map with an AAS.

## Ladders

A ladder is only held when Use (`+use`, bound to E) is pressed, as in Resident Evil 2's remake. Walking into one
doesn't grab it. Facing one within reach, a prompt says `[E] Climb`. At the top of one, looking over the edge, it says
`[E] Climb down`, and Use lowers you onto it, facing it. While held, the player only climbs up and down
(forward or jump; back or crouch), and the view turns only so far. Use lets go. At the top the climber goes over onto the
ledge, crouched if the ceiling is low. At the foot, going down steps off.

bspc makes ladder reachabilities from the brush sides marked `SURF_LADDER`, as Daikatana's converted maps have them,
as well as from Quake 3's `common/ladder` shader. Before that fix, the maps had none (e1m1a now has 97, e4dm1 86, e1dm1 18,
e1m1b 12). A bot on a ladder reachability faces it, moves forward and presses Use until it holds the ladder
(`BotTravel_Ladder`). Each press is released before the next, since pmove only takes a new press.

To see a bot use a particular route, `botgoto <bot> <x> <y> <z>` (a server command) orders it there as a
camp order. For example, on e1dm1, `teleport Hiro -1395 -1612 121 270` and then `botgoto Hiro -1395 -1640 328` send it up the
ladder by the stairs: it takes hold, climbs and goes over the top. A nearby item can still lead it astray first.

## Seeing it

`cg_drawAAS 1` (2 large, 3 xxl) draws a world around you, after RaZeR-RBI's
[aas-playground](https://github.com/RaZeR-RBI/aas-playground) viewer (MIT), its colours and what it shows:

- ground faces grey (do-not-enter ones olive), their edges black
- water, slime and lava surfaces blue, green and red
- cluster portals magenta, cyan where they can be walked through
- reachabilities as arrows coloured by travel type: walk green, crouch dark green, barrier jump yellow, jump orange,
  ladder brown, walk off ledge cyan, swim blue, water jump light blue, teleport magenta, elevator purple, jump pad pink

`cg_drawAASRange` (1024) is how far from the view; `cg_drawAASShow` picks what, added up: 1 ground, 2 edges,
4 liquids, 8 portals, 16 reachabilities, 32 the grapple ones too (bspc makes thousands; 31 leaves them out). It's a
cheat. The cgame reads the `.aas` itself, so any client can look; that needs `vm_cgameHeapMegs` 24 and more
polygons (`r_maxpolys`, `r_maxpolyverts`), which `default.cfg` sets.

## bspc

The compiler is Spearmint's own (`code/bspc`), built by `./dk build bspc` from its Makefile. It links the AAS code in
Spearmint's `code/aas`, idlib's script parser and BSP loaders, and the old collision code (`code/cm1`);
`bspc/bspc_idlib.c` gives them what the engine would (idlib's import table over bspc's allocator and stdio, and the
zone).

## What's next

- Monsters: their AI choosing a world by size (RTCW's `AICast_SetAASIndex`).
- Daikatana's own movers and teleporters, checked against the reachabilities bspc finds.
