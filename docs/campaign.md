# The campaign: Daikatana's single player

The campaign is mint-arena's gametype 3 (`GT_CAMPAIGN`). It plays Daikatana's single player maps as Daikatana does:
a level is several maps (`e1m1a`, `e1m1b`, …) walked between by `trigger_changelevel`s, with the player's things
carried across, keys and an inventory, secrets and saved games, and Doom 3's scripts (`scripts.md`). Monsters,
sidekicks and cutscenes come later (see `roadmap-sp.md`).

## Playing it

From the menu: **Single Player**, then a difficulty: Ronin, Samurai or Shogun (`g_skill` 0, 1, 2). It starts
at `e1m1a`. **Load Game** in the main menu, and **Load Game** and **Save Game** in the menu during a game, use
the quick save or one of four slots.

From the console:

```
./dk run +set sv_cheats 1 +set g_gametype 3 +set g_skill 1 +devmap e1m1a
```

- `savegame [name]` saves to `save/<name>.svg` (`quick` by default). As in Daikatana, a save costs a Save Gem
  from the inventory (you carry three at most), unless `g_unlimitedSaves 1`.
- `loadgame [name]` goes back to a saved game, whether or not a map is running.
- `setviewpos -600 -1384 540 180` in e1m1a stands you in the changelevel to e1m1b.

## The maps

bsp-sekai keeps Daikatana's single player entities under their own classnames and keys, marked
`"gametype" "campaign"`, so the deathmatch game types never spawn them. Daikatana's "not in deathmatch"
spawnflag (0x8000) becomes the same. Its skill spawnflags (0x1000 not easy, 0x2000 not medium, 0x4000 not hard)
drop entities by `g_skill`.

What the campaign plays now (`g_campaign.c`):

- `trigger_changelevel` goes on to its `map`, starting at the spawn point named by its `target`: the
  `info_player_start` of that `targetname`, else the `info_player_coop` of it, else an unnamed start.
- `trigger_secret` (its `message` and `sound`), `trigger_relay` and `trigger_counter`, all with Quake 2's
  `delay`, `message` and `killtarget`.
- `func_wall` with Quake 2's trigger spawn, toggle and start on.
- `trigger_remove_inventory_item` (its `item`), and `info_player_coop`.
- Items with Doom 3's `inv_item` key go into the inventory (`IT_INVENTORY`), up to `inv_max`: the Save Gem
  and the keys (`def/dk_items.def`). A `keyname` on a mover or a changelevel locks it until you have that item,
  and says what's needed. Daikatana's key spawnflags: `KEY_USE_ONCE` uses the key up, `KEY_UNLOCK` leaves the
  lock open.
- Items picked up in the campaign don't come back.

The other Daikatana classes (monsters, path corners, scripts, health trees…) are kept in the maps and spawn
nothing yet (`developer 1` lists them).

## Carried across, and saved

RTCW's ways, in `g_save.c`:

- **Changing maps:** the changelevel writes `save/current.psw`, with each player's health, armor, weapons,
  ammo and inventory. The next map gives it back at their first spawn there (`G_SavePersistant`,
  `G_LoadPersistant`). Only a changelevel carries anything (`g_persistant`); a new game starts with nothing.
- **Saved games:** `save/<name>.svg` holds the map, the time, the level's secrets, every entity as it is, the
  scripts' variables and threads (`scripts.md`), and each player's place, view, health, armor, weapons, ammo,
  powerups and inventory. An entity's pointers are
  written as names and numbers: strings by their text, callbacks (`think`, `touch`, `use`…) by function name,
  entities by number and items by classname. The function names come from `g_funcs.h`, which
  `code/tools/extractfuncs.py` (RTCW's tool) writes at build time. A callback therefore can't be `static`, or
  it saves as nothing and the load warns.
- **Loading:** the engine's `loadgame` (Spearmint's `sv_ccmds.c`) reads the map, the time and the skill from the
  save's header. It starts the map at the saved time (`savegame_time`), so every time the save holds still holds.
  The game puts the saved entities back over the freshly spawned map once the first player is in
  (`G_LoadGame`). An entity keeps the map's own physics body where the map made the same thing; a ragdoll goes
  limp again from its last pose.

A save fits only the build whose entities it was made with: the header records `sizeof( gentity_t )`, and a
save from another layout is refused.
