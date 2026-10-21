# The inventory

Daikatana picks things up by walking over them. The port takes them by looking at them and pressing
use, into a System Shock 2 style inventory grid, and uses them from it; armor is worn, one suit at a
time, Fallout 4 style. It holds in every game type, deathmatch too.

It is built on what Doom 3 and The Dark Mod do:

| | From | Here |
| --- | --- | --- |
| Items as defs with `inv_*` keys | Doom 3 (`idInventory`, `def/items.def`) | `def/dk_items.def`, `def/dk_weapons_e1.def` |
| Looking at a thing and using it | The Dark Mod's frob (`PerformFrobCheck`, `PerformFrob`) | `g_frob.c` |
| Categories, stacks, an item's own state, dropping | The Dark Mod's `CInventory` | `bg_inventory.c`, `g_inventory.c` |
| A screen the game feeds, sending commands back | Doom 3's PDA GUI, The Dark Mod's inventory grid GUI | `ui/dk_inventory.menu`, `ui_inventory.c` |

Neither has a space limit or armor that is worn; those are this port's.

## Taking things

Looking at an item within reach (`frob_distance`, 80 units, Daikatana's use reach) and near the
middle of the view picks it. It's lit up, and the HUD says `[E] Take Plasteel Armor`, in red
`No room for ...` when it won't fit. Use (`+use`, E) takes it. Walking over items does nothing;
`g_touchPickup 1` brings that back. Bots still take things by touch, wear the best suit, use health
when hurt and artifacts at once.

A map entity made `"frobable" "1"` is used the same way: its script's `frob( player )`, its `use`, or
its targets.

## The grid

Each player has a grid, the `player` def's `inv_grid` (10 by 6 cells). Each item takes its def's
`inv_size` cells; a slot holds a stack of up to `inv_stack` of one item. An item goes in the first
place it fits, reading row by row; when there is none, everything is packed again, biggest first,
and only then is it refused. Players don't arrange it.

Everything goes in it: weapons (owning one is having it in the grid), ammo (a weapon's ammo is its
ammo item's stacks; firing takes from them), health, armor, artifacts, keys, quest items.

## The belt

The HUD's weapon windows are a quick-use belt, as Deus Ex's: keys 1 to 9 and 0 each hold an item.
Pressing the key takes a weapon in hand or uses anything else (a health kit, an artifact). A weapon
newly carried goes on the key of its `weapon_slot` when that is free, health and artifacts on the
first free key; an item no longer carried leaves the belt. On the inventory screen, pressing a belt
key puts the selected item on it, or takes it off when it is there already. The belt shows for
`cg_weaponSelectTime` after a change, always with `cg_drawBelt 1`, and while the inventory is open.

## Armor

A suit (`inv_armor` points, `armor_absorb` its share of the damage) is worn from the inventory,
one at a time. It takes its share of each hit, never all of it, and is gone at 0. Taken off or
dropped it keeps the points it has left. Daikatana's values:

| Suit | Points | Takes |
| --- | --- | --- |
| Plasteel | 200 | 75% |
| Chromatic | 100 | 50% |
| Silver | 150 | 65% |
| Gold | 200 | 75% |
| Chainmail | 125 | 50% |
| Black Adamant | 250 | 80% |
| Kevlar | 100 | 40% |
| Ebonite | 200 | 75% |

## Commands and keys

| Command | Key | |
| --- | --- | --- |
| `+use` | E | take or use what's looked at |
| `inventory` | I | open or close the inventory screen |
| `invquick <category>` | H: `health` | use the best item of a category |
| `invuse <slot or def>` | | use: drink, turn on, wear, take in hand |
| `invwear <slot or def>` | | wear a suit; the one worn goes back in the grid |
| `invremove` | | take off the suit worn |
| `invdrop <slot or def> [count]` | | drop (all of the stack without a count) |
| `invdropworn` | | drop the suit worn |
| `invlist` | | print the grid and the belt |
| `belt <key>` | 1 to 9, 0 | the belt's item on that key: take the weapon in hand, use anything else |
| `invbelt <key> <slot or def>`, `invunbelt <key>` | | put an item on a key of the belt, empty a key |
| `spawnitem <def>`, `hurt <n>` | | cheats, for trying it |

## The screen

`ui/dk_inventory.menu` is a menu script; everything on it can be moved and restyled there. The game
goes on behind it. Its pieces (`ui/menudef.h`):

| | |
| --- | --- |
| `UI_INV_GRID` | the grid, each item its world model framed in its cells; its `background`, if any, is each cell's picture; a click selects, a double click or enter uses, the arrows move |
| `UI_INV_SELNAME`, `UI_INV_SELINFO`, `UI_INV_SELDESC` | the selected item's name, numbers and `inv_desc` |
| `UI_INV_WORN`, `UI_INV_ROOM` | the suit worn; the cells used |
| `CG_BELT_ITEM`, `CG_BELT_COUNT`, `CG_BELT_SELECTED` | in the HUD's `weaponselect_menu`, a belt key's (the item's `special`) item, its ammo or count, and the background when it's the weapon in hand |
| `uiScript InvCommand <command>` | a button's: the command for the selected item |
| `UI_SHOW_INV_SELECTED`, `_USABLE`, `_WEARABLE`, `_DROPPABLE`, `_WORN` | `ownerdrawflag`s showing buttons when they apply |

The HUD's hint is `CG_FROB_HINT` in `ui/dk_hud.menu`; its `ownerDrawParam` says it (`%k` the key, `%a`
the action, `%n` the thing), and `CG_SHOW_FROB_ROOM` / `CG_SHOW_FROB_NOROOM` pick its look. The
highlight is the `frobHighlight` shader (`scripts/dk_ui.shader`).

## Trying it

    ./dk invtest            take, wear, hurt, use, fill until refused, weapons and ammo, drop
    HUD=1 ./dk invtest      with screenshots of the hint and the screen (out/test-home/dkres/screenshots)
    ./dk script <map> ...   any console commands on a map (BOTS=1, GAMETYPE=3 the campaign)

## Later

- Audio logs and readables: a category that takes no room, on Doom 3's `pda`/`audio` decls and The
  Dark Mod's `xdata` readables, with a tab of their own.
- Weight, as Fallout 4 and Stalker have, beside the grid or instead of it (`inv_weight`).
- Moving items in the grid by hand, if players want it (the cells are in the playerState already).
