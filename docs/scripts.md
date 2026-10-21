# Scripts: Doom 3's script system

The game runs Doom 3's scripts: its language, compiler, interpreter and threads, ported to C in mint-arena
(`code/game/g_script*.c`). A script is straight-line code in a thread. `sys.wait( 2 )` or `sys.waitFor( $door )`
pauses the thread while the game goes on, so "go here, then do that" needs no state machine.

```
void main() {
	$door1.open();
	sys.waitFor( $door1 );		// until it's open
	sys.wait( 1.5 );
	sys.trigger( $relay_alarm );
}
```

The language is Doom 3's as it is: `float`, `vector`, `string`, `entity`, `boolean`, `void`; `object`s with fields
and methods and inheritance; `namespace`s; `thread f( ... )` to start a thread; `if`, `while`, `for`, `do`;
`#define` and `#include`. Doom 3's own documentation and scripts are a guide; the events are this game's (below).

## The files

- `script/dk_main.script`: the game's script, compiled as the game starts. It includes `dk_events.script`; what it
  includes, every map's script knows. `dk_main()` runs as each map starts, before its entities spawn.
- `script/dk_defs.script`: constants (`true`, `false`, `CHAN_*`, `CONTENTS_*`, `MASK_*`). The compiler includes it
  first in every script, so it has only `#define`s.
- `script/dk_events.script`: the events, declared as `scriptEvent`s. The compiler checks each declaration against
  the game's own, so a wrong argument type or count is a compile error.
- `maps/<map>.script`: a map's own script, kept in this repository's `maps/` and copied next to the converted maps by
  `./dk`. Worldspawn compiles it, then `main()` runs in a thread from the first frame. A worldspawn `call` key
  names more functions to run that way.

## Entities

- `$name` is the entity of that `targetname`; `$player1`, `$player2`… are the players, `$world` the world,
  `$null_entity` none. `sys.getEntity( "name" )` looks one up at run time (`"*123"` by number).
- `"call" "function"` on an entity runs that function in a thread whenever the entity fires its targets
  (Doom 3's `idTrigger::CallScript`): triggers, buttons, doors reaching their end, relays.
- `"scriptobject" "type"` on an entity (or in its def) gives it a script object of that type: its fields, with
  the entity as the methods' `self`. Its `init()` runs in a thread as it spawns, its `destroy()` as it's removed.
- `target_callobjectfunction` calls the method its `call` key names on each of its targets' script objects.

## Items

An item def can have a `scriptobject`. Its methods, all of them optional:

- `boolean canPickup( entity player )`: false keeps the player from picking it up.
- `void pickup( entity player )`: runs as the player picks it up, after the game gives what the def says.

An item def with a `scriptobject` and none of the `inv_*` keys is a script item (`IT_SCRIPT`): its `pickup()` is
all it gives, and it comes back after its `respawn` seconds (`0`: never). The client doesn't predict its pickup;
the script decides.

```
entityDef item_vial {
	"spawnclass"	"item"
	"inv_name"		"Vial"
	"model"			"models/global/a_hlth.md3"
	"scriptobject"	"item_vial"
	"respawn"		"0"
}
```

```
object item_vial {
	boolean		canPickup( entity player );
	void		pickup( entity player );
};

boolean item_vial::canPickup( entity player ) {
	return player.getHealth() < player.getMaxHealth();
}

void item_vial::pickup( entity player ) {
	float i;

	player.centerPrint( "The vial warms you" );
	for ( i = 0; i < 5; i++ ) {		// 25 health over a second
		player.setHealth( player.getHealth() + 5 );
		sys.wait( 0.2 );
	}
}
```

## The events

`script/dk_events.script` lists them all. Those of sys (`sys.wait()`…) are Doom 3's `idThread` events; they're
in `g_script_thread.c`. An entity's (`$door.open()`…) are in `g_script_events.c`.

- **sys:** `wait`, `waitFrame`, `waitFor` (a mover until it stops), `waitForThread`, `terminate`, `killthread`,
  `threadname`, `pause`; `print`, `println`, `say`, `error`, `warning`, `assert`; `trigger`; `setcvar`,
  `getcvar`; `random`, `getTime`, `getFrameTime`, `getTicsPerSecond`; `getEntity`, `spawn` with `setSpawnArg` and
  `SpawnString`/`Float`/`Vector`; vector math (`vecLength`, `vecNormalize`, `DotProduct`, `CrossProduct`,
  `VecToAngles`, `angToForward`/`Right`/`Up`, `sin`, `cos`, `sqrt`); `trace`, `tracePoint` (with `CONTENTS_RENDERMODEL`, as a shot: hit boxes) and the `getTrace*`
  results; strings (`strLength`, `strLeft`, `strRight`, `strSkip`, `strMid`, `strToFloat`); `music`;
  `isMultiplayer`, `isClient`.
- **an entity:** `getName`, `setName`, `remove`, `activate`, `activateTargets`, `numTargets`, `getTarget`,
  `randomTarget`; `getOrigin`/`setOrigin` (and `World`), `getAngles`/`setAngles`, `getLinearVelocity`/`set…`,
  `getSize`/`setSize`, `getMins`, `getMaxs`; `hide`, `show`, `isHidden`, `touches`, `distanceTo`,
  `distanceToPoint`; `getKey`, `getIntKey`, `getFloatKey`, `getVectorKey`, `getEntityKey`, `setKey`;
  `startSoundShader`; `getHealth`, `setHealth`; `wait`, `waitFrame`; `hasFunction`, `callFunction`.
- **a player:** `getMaxHealth`, `giveInventoryItem`, `removeInventoryItem`, `hasInventoryItem`, `centerPrint`.
- **a mover** (door, plat, button): `open`, `close`, `isOpen`, `isMoving`.
- **a monster**: its states, enemy, moves, facing, flight, attacks, animations and sounds (`monsters.md`).

A script's numbers are floats. `sys.trace()`'s contents mask is therefore numbered as Doom 3's (low bits, which a
float holds exactly), and the game translates it.

New events go in a table of `g_script_thread.c` or `g_script_events.c` and a line of `dk_events.script`.

## Saved games

A saved game has the scripts' state as Doom 3 saves it: the variables that changed since they were compiled,
every thread (its stack, its call stack and what it waits for), each entity's script object and spawn args. It
loads only into the same scripts: if the code changed (its checksum), the threads the map started keep running and
the console says the scripts' state wasn't loaded.

## Testing and debugging

- `script <statements>` at the console compiles them into a function and runs it, e.g.
  `script sys.println( "health " + $player1.getHealth() )`. The console splits commands at `;`, so give it one
  statement at a time.
- `listThreads` lists the threads and where each is.
- `g_debugScript 1` prints each line as it runs, and threads as they start and end. `g_disasm 1` writes the
  compiled code to `script/disasm.txt`.
- A script error stops the map with the file and line, and the thread's call stack.

### The debugger

The game has dhewm3's script debugger server, with the protocol 2 of
[ashalkhakov/dhewm3](https://github.com/ashalkhakov/dhewm3)'s `script-debugger-protocol`: breakpoints, step
over, into and out (a step stays in its thread), every thread's call stack and variables (a caller's too, and a
method's object's fields), an entity's spawn args and script object, setting a variable, going on from another
line, stopping at script errors and warnings. Its clients are dhewm3's: UDQuakeTools' Quarry and its
`udscript-dap`, which speak to it as they do to dhewm3.

- Start the game with `+set com_enableDebuggerServer 1` (`com_dbgClientAdr`, `localhost` by default, is where the
  client is). The server listens on UDP 27980 and finds the client on 27981, as dhewm3's does.
- The client's source root is the game's folder (the one with `maps/` and `script/`): the scripts' files are
  named as the game reads them, `maps/e1m1a.script`, `script/dk_main.script`.
- While a thread is stopped the whole game waits, as in dhewm3.
- The game starts anew with each map; the connection and the breakpoints go on to the next map
  (`debugger.state` in the game's folder), so a breakpoint in a map's `main()` stops it as it starts.
- macOS and Linux builds (it isn't in a Windows or QVM build).

## What differs from Doom 3

- The parser is the botlib precompiler Doom 3's `idParser` grew from (`idlib/l_precomp.c`), changed as Doom 3's
  behaves: a `$` that isn't a `$evalint`-style directive is a token of its own (`$name`), and a `#define` ends
  with the file it's in.
- A thread runs when its time comes at the start of a frame, as Doom 3's `EV_Thread_Execute` events do.
- No signals (`onSignal`), cameras, fades or debug drawing yet.
