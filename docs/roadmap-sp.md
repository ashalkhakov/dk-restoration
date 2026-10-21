# Roadmap: Daikatana single player and coop

Deathmatch works today: skeletal characters, Doom 3 physics and collision, ladders, swimming, bots on AAS and
ragdolls. Single player needs much more. This page plans how to get there: what to take from Doom 3, RTCW and Quake 2/DK,
and in what order, so that each step can be played and tested.

The standing rules shape every choice: Doom 3's approaches first, and Quake 3, RTCW and JKA subsystems where they fit
Spearmint better. The game is written in C, the menus and HUD in scripts, the data in defs. Daikatana's own data
(maps, models, sounds, its AI tables and scripts) is converted, not shipped. The DK 1.2 source is a reference for
behaviour only: nothing is copied from it.

## What Daikatana's single player is

From the DK 1.2 source (`dlls/world`, `base/physics`); details in the survey notes:

- **Monsters.** About 80 types over four episodes. Their stats are in `AIData.csv`, their animations in per-monster
  frame CSVs. The AI is a goal stack of task queues (about 80 goal and 250 task types), with C++ per monster.
  Monsters find their way on a node graph per map (`*.nod`), which has door, platform, train, ladder, jump and
  sidekick nodes.
- **Sidekicks.** Superfly and Mikiko follow, stay, attack, back off, come and fetch on 7 commands. They pick up
  their own weapons, health and armor, show on the HUD, earn XP, and some level exits wait for them.
- **Inventory and keys.** A selectable item sack, key and quest items (cards, keystones, runes, purifier shards…),
  and doors and triggers locked by a `keyname`. Each save costs a save gem.
- **Levels.** A level is several maps (`e1m1a`–`e`). Changelevels carry the player, the sidekicks and some
  entities across, cross-level triggers set flags, and saves are Quake 2 style.
- **Scripts and cutscenes.** There are three layers:
  - camera-shot cinematics (`cin/scripts/*.script`: spline cameras, actors, fades, sounds);
  - AI scripts (`cin/aiscripts/<map>.sca`: animate, move, face, say, use, attack…);
  - full-motion video.
  
  Subtitles come from the sound's name.
- **XP.** Five stats (power, attack, speed, acro, vita), raised by levelling up.
- **Trucks.** Most likely `func_train`s on `path_corner_train`s; there are no drivable vehicles. That is an inference
  from the code, not checked in the maps.

mint-arena has none of this beyond Quake 3's holdables, triggers and movers. `misc_character` (a skeletal model with
hitboxes) and the AAS worlds (standard, large, xxl) are the starting points.

## 1. Networking: Doom 3's entity snapshots

Today every entity is one `entityState_t`, whose fields the game lists (`bg_entityStateFields`, delta-compressed by
the engine). That fits Quake 3's players, items and missiles. It doesn't fit a ragdoll's 11 bodies, a truck's
wheels, or a monster's animation channels, IK and sidekick status. Doom 3 lets each entity class write its own
state (`WriteToSnapshot`/`ReadFromSnapshot`, `idBitMsgDelta` against what the client last acknowledged).

**Done (first form).** `entityState_t` ends in 16 snapshot words (512 bits). An entity's class writes its own state
there as a bit message (`bitMsg_t`, Doom 3's `idBitMsg`, in `bg_snapshot.c`); the first byte says what it is. The
engine already delta-codes array fields word by word, so the engine is unchanged, and an entity at rest sends
nothing. The first user is the server's ragdolls (`g_ragdoll.c`): a `misc_character` that dies goes limp on the
server. Its first body's origin goes in `pos` and every body's orientation goes in the words, 30 bits a body. That
is enough, since the figure's joint mods are orientation only. Clients pose the model from that, interpolating
between snapshots (`CG_ServerRagdoll`). Hits push the corpse (`g_ragdollPush`).

**Entity events (done).** Doom 3's `ServerSendEvent` is `G_ServerSendEvent` (`g_netevent.c`). An entity's event
carries up to 128 bytes of bit-message parameters and the time it happened. It goes out as a reliable server
command (`eev`). The client queues it and runs it when its own time gets there (`cg_netevent.c`,
`ClientProcessEntityNetworkEventQueue`). Saved events go again to players who begin later, until their entity is
freed. The first common event is `ENTEV_STARTSOUND`, Doom 3's `EVENT_STARTSOUNDSHADER`: a sound shader by index,
a channel and a volume. Ragdolls use it to thud when they hit something (`snd_bounce`). `cg_debugEvents 1` prints the
events as they run.

**Still to do.** A bigger, variable-length state for what doesn't fit in 512 bits (the plan below), when
monsters or vehicles need it.

**Plan.** Keep `entityState_t` as the header every entity has, so Quake 3's entities keep working. Add Doom 3's
per-entity state after it:

- **Game.** A new export writes an entity's extra state (up to a few hundred bytes) in a `bitMsg`, by entity type,
  as Doom 3's classes do. Physics objects write their own: the AF bodies' positions and orientations, a rigid body's
  state, a vehicle's wheels.
- **Engine.** It stores each entity's bytes in the snapshot alongside its `entityState_t`. It deltas them per client
  against the last acknowledged snapshot, with Doom 3's byte delta and Spearmint's existing baselines and
  fragmenting. `playerState_t` and prediction stay as they are.
- **Cgame.** A new import reads the bytes by entity type (`ReadFromSnapshot`), interpolating between snapshots as
  Doom 3's clients do.
- **Events.** Doom 3's entity events (`ServerSendEvent`) are added next to Quake 3's `EV_*`, for one-off things
  with parameters (a monster's line, a door's sound).

**Unlocks:** the server runs articulated figures (dead monsters' ragdolls that everyone sees the same, shots pushing
corpses), vehicles, and monsters with Doom 3's animation channels. Client-side ragdolls stay for deathmatch, where
Doom 3 kept them too.

## 2. The single-player game

**Base: RTCW's single player.** It is Quake 3's code grown into a single-player game, so it ports to Spearmint far
more easily than Doom 3's C++ or Quake 2's (iortcw, GPL). Doom 3 supplies the data-driven parts: defs, inventory,
objectives, AF physics. Quake 2 and DK are a reference for how Daikatana behaves.

| System | From | Notes |
| --- | --- | --- |
| Save and load | RTCW `g_save.c` | Field tables and a function-pointer registry. Entity, AI and script state; save gems are a rule on top. |
| Levels of several maps | Quake 2 units on RTCW's changelevel | Keep each map of a level when leaving it (Quake 2's level files) so you can go back. Carry the player, sidekicks and inventory across; cross-level flags. |
| Triggers and movers | DK's set on Quake 3's | changelevel, counter, relay, secret, crosslevel, script, sidekick, inventory removal; doors, trains with rotation, explosive walls, `func_monitor`, etc. As defs where possible. |
| Inventory and keys | Doom 3's `idInventory` | Items and keys are defs. `keyname` locks with use-once and unlock. The item sack, inventory and objectives are script menus. |
| Objectives | Doom 3 (PDA) / RTCW (notebook) | DK has none: add them, as defs set by scripts, shown in a script menu. |
| Monsters | RTCW AI Cast | AAS movement, sight and hearing, attacks, and scripted actions. Each DK monster is a def (stats from `AIData.csv`, animations, attacks) plus C where it needs its own behaviour. Ragdoll deaths. |
| Sidekicks | AI Cast | Follow, stay, attack, back off, come, get; pick up their own items; HUD status (script). Level exits that need them. |
| Scripts | RTCW `.ai` scripts | DK's `.sca` converted to them; actions mapped (animate, moveto, face, say, use, attack, spawn…). |
| Cutscenes | Doom 3 cinematic mode + RTCW camera splines | DK's `.script` shots converted to camera paths with actors. Letterbox, skip, and fades in scripts. |
| Dialogue and subtitles | Doom 3 sound shaders | Subtitles per line (DK names them by sound), shown by the HUD script; sidekick banter on nodes, as areas or triggers. |
| XP | DK's rules | Five stats in the persistent player state, level-up menu in script, stat tables in defs. |
| Coop | DK's coop on the above | Character select (Hiro, Mikiko, Superfly), shared progress, per-player inventory, respawn at checkpoints. |

**Rebalancing.** Monsters should be fun to fight, not DK's hit-scan swarms. Their stats, ranges, reaction times and
attack rates live in defs. Each monster gets Doom 3-style telegraphs (wind-ups, sounds) and a test map. Episode 1 is
tuned first.

## 3. Vehicles: the dump trucks

The trucks drive in cutscenes, simulated rather than animated, and could be drivable later.

- **Doom 3** builds vehicles as articulated figures: `idAFEntity_VehicleSimple`, and the four-wheeled kinds with
  `idAFConstraint_Suspension` and `HingeSteering`. We have the AF port now, so a truck is a chassis body, wheel
  bodies, suspension and steering, plus two more constraint types (a few hundred lines). The server runs it,
  networked as in §1. A script or a path follower drives it in cutscenes; a player can sit in it and drive later.
- **q3rally** (GPL) is an arcade car built for Quake 3, with a predicted client and its own spring physics. Its
  feel and HUD are worth reading, but its physics would duplicate the AF's.

**Recommendation:** Doom 3's AF vehicles. Read q3rally for handling if driving needs it.

## Order

Each step ends with something to play:

1. **Entity snapshots** (§1). Server-side ragdolls for a test monster (`misc_character` dying) prove them. AF self
   collision goes in here too.
2. **The SP gametype's frame:** save and load, levels of several maps with the player carried across, DK's triggers
   and movers, keys and the inventory. Played through e1m1a–c with no monsters.
3. **The first monsters:** AI Cast ported, one easy and one ranged e1 monster as defs, ragdoll deaths. Then e1's
   roster, tuned.
4. **Scripts and cutscenes:** `.sca` and `.script` converted, cinematic mode, subtitles. e1's intro and its scenes.
5. **Sidekicks:** Superfly first, his commands and HUD.
6. **XP and the HUD and menus** for inventory, objectives and stats.
7. **The trucks**, simulated in their cutscenes, then drivable.
8. **Coop.**
9. Episodes 2–4: monsters, scripts, tuning.

## Decisions

- **RTCW's single-player source:** iortcw (GPLv3) is cloned next to the repositories, at `../iortcw`, as the base
  for steps 2–4.
- **q3rally's source:** download it as a handling reference for step 7, or skip it.
- **Converting DK's data** (`AIData.csv`, monster frame CSVs, `.sca`, `.script`, `.nod`) from the user's paks into
  defs and scripts. These are tools, like the map and model converters, and the results aren't shipped.
