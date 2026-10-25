# Quests and the player's screen

Fallout 4 style quests, each with objectives, shown on a tabbed player screen: Status, Inventory, Quests.

| | From | Here |
| --- | --- | --- |
| Objectives: incomplete, complete or failed, shown or hidden; what finishing one fires | The Dark Mod (`MissionData.cpp`), Doom 3's objectives | `g_quests.c`, `target_setobjective` |
| Quests sent to the client as a command, announced, read by the screen | OpenJK's datapad objectives | `cg_quests.c`, `ui_quests.c` |
| Tabs, a figure of the player, what they wear and carry | Fallout 4's Pip-Boy | `ui/dk_status.menu`, `ui/dk_inventory.menu`, `ui/dk_quests.menu` |

## A quest

A quest is a def in `def/dk_quests.def`:

| Key | |
| --- | --- |
| `title` | its name |
| `desc` | a line under it |
| `obj<n>` | objective n's text, from 1 (at most 8) |
| `obj<n>_target_complete`, `obj<n>_target_failed` | entities used when objective n is done or failed |
| `target_complete`, `target_failed` | the same, for the quest itself |

A player can have up to 16 quests. Every player has them alike (the campaign's coop). They go with the
player from map to map and into saves.

The quest is given the first time anything sets one of its objectives; its objectives start hidden.
Each change is announced in the middle of the screen with a sound: "New quest", "New objective",
"Done", "Failed", "Quest complete", "Quest failed". The Quests tab is marked with a star until it's
looked at.

## Setting objectives

From a map, `target_setobjective` (put in `maps/<map>.ent`):

| Key | |
| --- | --- |
| `quest` | the quest's def |
| `objective` | its number; 0 is the quest itself |
| `state` | `incomplete`, `complete` or `failed`; none leaves it |
| `visible` | 1 shows it, 0 hides it; a state shows it too |
| `only_if` | only when it is in this state now, e.g. `incomplete`, so a failed one isn't then completed |

It fires its own `target`s after.

What uses one:
- **Anything that fires targets:** triggers, buttons, a monster's `deathtarget`.
- **A spawn point's `target`:** fired when the player spawns there, after what they carry is loaded.
- **A monster's `sight_target`:** fired the first time it sees an enemy (`monster_base.script`).
- **A `trigger_changelevel`'s `target_leave`:** fired as the player leaves that way, before what they
  carry is saved. It does not fire when the next map isn't there.

From a script (`script/dk_events.script`):

```
$player1.setObjectiveState( "quest_e1_fortress", 1, "complete" );
$player1.setObjectiveVisible( "quest_e1_fortress", 2, 1 );
string s = $player1.getObjectiveState( "quest_e1_fortress", 1 );	// "incomplete", "complete", "failed", "hidden", "active", or "" without the quest
```

## Episode 1

`quest_e1_fortress`, "Get into Mishima's fortress":
- **e1m1a:** the first spawn point gives it, with "Go through the swamp entrance".
- **e1m1b, the boss fight:** the boss sequence (`doitall`, set off by a cambot's death) spawns the
  thunderskeet (`tskeetspawn`), which fails the swamp entrance. Killing it (`tskeetdead`) shows "Go
  through the Sewer System".
- **e1m1c, the swamp entrance:** leaving through it to e1m2a completes the swamp entrance, unless it was
  failed, and shows "Go through the Sewer System".

## The screen

Keys: `i` inventory, `j` quests, `p` status (`mint/default.cfg`). They are also in the controls menu.
On the screen, a tab's key goes to that tab, or closes the screen when that tab is already shown.

An existing `config.cfg` keeps its old binds; rebind there or in the controls menu.

| Command | Opens |
| --- | --- |
| `inventory` | the Inventory tab |
| `quests` | the Quests tab |
| `character` | the Status tab (`status` and `stats` were taken) |

Menu hooks for modders (`ui/menudef.h`):
- **Switching tabs:** `uiScript PdaTab <character | inventory | quests>`.
- **Owner draws:**
  - `UI_QUEST_LIST`: the quests, newest first, objectives under each.
  - `UI_STATUS_MODEL`: the player's own model, in its idle, turning.
  - `UI_STATUS_NAME`, `UI_STATUS_PLACE`.
  - `UI_STATUS_HEALTH`, `UI_STATUS_ARMOR`: bars.
  - `UI_STATUS_WEAPON`, `UI_STATUS_BOOSTS`.
- **Visibility flag:** `UI_SHOW_QUESTS_NEW`, for the tab's star (cvar `ui_questsNew`).
- **Shared macros:** in `ui/dk_defs.h`: `DK_PDA_PANEL`, `DK_PDA_TABS_STATUS`, `DK_PDA_TABS_INVENTORY`,
  `DK_PDA_TABS_QUESTS`.
