# Cinematics

Cutscenes are Doom 3's: a script puts every player's view on a camera, moves its actors and plays its sounds, then
gives the players their eyes back. The cameras are RTCW's spline cameras, in C (mint-arena `bg_camera.c`), with a
keyframe kind of our own for Daikatana's shots. Daikatana's 62 cinematics are converted into these, as text we
edit: the story may change.

## Cinematic mode (Doom 3's)

- `sys.setCamera( $cam )`: every player sees from the camera (a cinematic) until `sys.firstPerson()`. Meanwhile they
  are hidden, frozen and unhurt, and their view is letterboxed to Daikatana's 1.85:1, with no HUD or weapon.
- **Skipping:** attack, use or jump skips. The scripts' waits end at once, cameras run out, and actors' moves,
  turns and animations end where they would, so the cutscene's script runs to its end at once (Doom 3 ran whole
  frames on quickly instead). `sys.skippingCinematic()` says so.
- **Fades:** `sys.fadeIn( color, secs )`, `fadeOut` and `fadeTo( color, alpha, secs )`.
- **Sounds:** `sys.startGlobalSound( "sounds/..." )` plays a line or a noise to every player, from no place.
  `startGlobalLoop` plays a loop at the camera until `stopGlobalLoops()`.
- **Cameras:**
  - `func_cameraspline` plays `cameras/<camera>.camera`. It starts when it becomes the view (or on `start()`), and
    `sys.waitFor( cam )` waits for it to end. When it ends, its targets are used. The view stays on its last frame
    until the script cuts to another camera or calls `firstPerson()`.
  - `func_cameraview` is Doom 3's fixed view, at its `angles` or looking at its `cameraTarget`, with a `fov`.
- **What clients get:** the camera and when it started (`CS_CINEMATIC`). Each client works out the view itself
  every frame, so it's smooth. The server works it out too, and sends what the camera sees through a portal
  entity at each player, as RTCW did.

## Camera files

`cameras/<name>.camera` are text, RTCW's `cameraPathDef`:

- `time`: the seconds its path takes.
- The camera's path:
  - `camera_fixed { pos ( x y z ) }`
  - `camera_interpolated { startPos ( ) endPos ( ) }`
  - `camera_spline { target { granularity g ( x y z ) ... } }`: a B-spline near its points.
- What it looks at: `target_*` blocks of the same kinds.
- `event { type n param "..." time ms }`:
  - 1: wait, param seconds;
  - 4: look at a target, param its name;
  - 6: FOV, param "fov secs";
  - 9: stop;
  - 11: fade out;
  - 12: fade in;
  - 13: feather, easing in and out.
- `fov { fov f startFOV f endFOV f time ms }`.

Paths may also be **keyframes**, Daikatana's kind of shot:

```
cameraPathDef {
	camera_keys {
		name e1m1_cinestart_02
		key { time 0 pos ( 1598 -2756 1053 ) angles ( 2 89.9 0 ) fade ( 0 0 0 1 ) }
		key { time 4 pos ( 1590 -2723 1183 ) angles ( 80 90.9 0 ) fade ( 0 0 0 0 ) }
		key { time 6 pos ( 1590 -2723 1183 ) angles ( 80 90.9 0 ) fov 70 }
	}
}
```

- **Keys:** the camera passes through each key's `pos` and view `angles` at its `time` (seconds), on cubic
  Hermite curves. Angles go the short way round.
- **Velocities:**
  - a key may give how fast it passes: `vel ( )` and `avel ( )` in units and degrees a second, or `velIn` and
    `avelIn` for a different speed arriving;
  - a key without them is smooth through its neighbours (Daikatana's editor's rule);
  - the first and last keys are still, unless `easeIn 0` or `easeOut 0`.
- **FOV and fade:** a key's `fov` and `fade ( r g b a )` (0..1) are reached at its time, linearly from the key before
  that sets them.

The view at any time is a function of the time. Nothing is stepped frame by frame, so the server and every client
agree, and a cutscene can be skipped or started from its middle.

## Daikatana's cinematics, converted

`./dk cine` converts `cin/scripts/*.script` (Daikatana's cinematic editor's binary files; `tools/cine/dkcine.py`
reads them, `tools/cine/cine_convert.py` converts them) into `out/cine`:

- **Cameras:** `cameras/<name>_NN.camera`, one per shot. Each is a keyframe camera that gives every key's
  velocities, so it plays exactly as Daikatana's curves did, with the shot's FOV and fades.
- **Scripts:** `script/<name>.script`, holding `namespace <name> { ... play() }`:
  - each shot is a function: it cuts to its camera, starts its actors' threads, and plays its sounds at their
    times;
  - each actor's tasks are in its thread: spawn, play an animation, set its idle, move, turn, teleport, use a
    door, remove;
  - a task runs once its time comes, after the ones before it. An actor's tasks from one shot stop when the next
    shot starts.
- **Actors:** `def/cine_actors.def`.
- **Maps:** `maps/<map>.script` includes the cinematics that map starts. The game compiles it with the map's own
  script; all the cinematics at once would be more than the scripts' memory.

`script/cine_base.script` holds the helpers they use (`cine_camera`, `cine_spawn`, `cine_play`, `cine_playMove`,
`cine_move`, `cine_turn`, `cine_use`, `cine_start`/`cine_finish`) and `cine_actor`, a character with no mind of its
own.

**How maps start them.** As Daikatana's maps do: in the campaign, worldspawn's `"cinematic_intro" "<name>"`
starts `<name>::play` as the map starts. Daikatana's `trigger_changelevel` `"cinematic"` and `trigger_script`
`"cinescript"` are still to do.

**Editing.** The converted files aren't committed: they're Daikatana's data. Ours are, in the repository's
`cine/`:

- `cine/script/<name>.script` replaces the converted cinematic of that name;
- `cine/cameras/<name>.camera` replaces a shot's camera, or is a new one;
- a new cinematic is a new script there.

`./dk` assembles the converted files, then ours over them by name, so reconverting keeps our changes. To change a
cutscene, copy its script (or a camera) from `out/cine` into `cine/` and edit it there. An in-game editor
(scrubbing, flying a camera, dropping its keys and saving them) is to come. The game can already write a camera
back (`BG_WriteCamera`).

## Actors: our characters, movement apart

Daikatana's cutscenes used a separate model of each character for each map (`models/cinematic/c_hiro_e1m1`...),
holding that map's cutscene animations, with the walking and the faces baked in. We use one model per character,
the one that plays, and keep movement and faces apart:

- **The animations move onto our rigs.** `tools/rig/retarget.py` fits our character's skeleton to each cinematic
  model's frames, matching vertices by where they sit on the shared textures. The result is skeletal animations of
  our Hiro, Mikiko and Superfly: `models/rigged/<character>_<map>.iqm`, which also holds the character's own
  animations, and a `.json` (made by `./dk cine`; not shipped).
  - Fit errors are under a unit on average (Hiro e1m1: 1.0).
  - Facial motion falls away: the head moves as one bone. Faces get a system of their own (to come).
- **The travel is taken out.** The root's horizontal travel and turn are taken out of each animation, which then
  plays in place; the `.json` keeps what was taken. A converted task whose animation travelled plays it with
  `cine_playMove`: in place, while the game carries the actor along the travel. A character that walks is walked
  by the game.
- **Monsters:** a `monster_*` actor (e1m1's workers) is its rigged model (`def/rig_<name>.def`, `./dk rig`) playing
  its own animations.
- **Walking:** a move task walks the actor there at its `walk_speed`, playing its walk (`walka`), or runs it with
  `runa` after a `start_running`, then it stands (`cine_move`).
- **Actors without rigs:** characters not rigged yet stay on Daikatana's models, with their animations as they
  are.
