# Monsters

Monsters are Doom 3's kind (idAI): a character entity whose behaviour is its script. The game (mint-arena
`g_monster.c`) moves it, sees for it, hurts and kills it; its script object decides what it does, in states.
Humans and sidekicks, which play more like bots, are to come another way (RTCW's AI Cast).

Episode 1's, all of the first level's (`def/dk_monsters_e1.def`, `script/ai/`): the Froginator, the Slaughter
Skeet, the Crox, the Protopod, the Skinny Worker, the Cambot, the Rockgat and the Thunderskeet, and the fireflies.
The campaign spawns them where Daikatana's maps put them, and `target_monster_spawn` when it's used.

Their numbers are Daikatana's `AIData.csv`; their animations and sounds come from its per-monster tables,
`sounds/e1/m_*.vsc` (each byte XORed with 0x96 gives the CSV: per animation its sounds and the frames they play on,
the attack frame, loop or once).

## A monster

Its def (`"spawnclass" "monster"`) names its model def (the mesh and its animations), its script object and its
numbers, Daikatana's `AIData.csv` at medium skill:

- `health`, `modelscale`; `mins`, `maxs` (its box, to move with; the model def's, if it has none); `run_speed` (its moves' speed), `turn_rate` (degrees a second);
- `fov`, `sight_range`: whom it sees;
- `melee_range`: how far past its box a bite reaches (a damage def's `range` overrides it);
- `fly` 1: it flies, at `fly_speed`, its thrust changing its velocity by `fly_accel` a second at most, `fly_offset`
  above what it flies at, bobbing `fly_bob`;
- `impact_speed`, `impact_damage`, `impact_bounce`: hitting the world faster than `impact_speed` (a frog's leap,
  a skeet's crash) bounces it off with that much of its speed and hurts it `impact_damage` per 100 u/s more;
- `snd_*`: its sound shaders (`sound/dk_monsters_e1.sndshd`), for its script's `startSound()`.

Both die to one hit (health 1): they're small, fast and hard to see. In the campaign, Daikatana's skill scales
its health and speeds: x0.75 on easy, x1.25 on hard
(`"skill_scale" "0"` keeps them).

A damage def (`damage_frog_bite`) has `damage`, `damage_random` (more, at most; Daikatana's), `range` and
`push` (how fast it knocks you back).

A monster has two boxes, as Doom 3's clip model and render model. It moves with one (`mins`/`maxs`), and it bumps into
others with that one too. Shots meet the other (the model def's `hit_mins`/`hit_maxs`, then its hit boxes, joint by
joint): a skeet's wings reach well past the body it flies with, and a shot should hit them, but skeets in a narrow way
shouldn't jostle on them. Quake 3 links an entity with one box, so the game links the small one, and a shot
(`G_TraceShot`) also looks along its way for monsters whose models reach past their boxes.

A melee attack reaches when the gap between its box and its enemy's is within its `range` (Doom 3's `TestMelee`), in
front of it and seen; `testMeleeAttack()` asks whether it would.

Their models are rigged from their animations alone by `tools/rig/creature_rig.py` (`./dk rig froginator
slaughterskeet`): no template, so any creature. It splits the mesh into the pieces that move rigidly over the
frames, merges those that move alike (to a budget of bones), links them into a skeleton from the body out, puts
each joint where the two pieces' motions agree, and names the bones by where they are (Body, Head, Tail, L/R
fore and hind limbs, wings). It measures both boxes from the mesh: the one it moves
with, of all but its wings as it idles, square (Quake 3's boxes don't turn); the one shots meet, of all of it over its
looping animations, as far as it reaches whichever way it faces. It writes the IQM, a model def (`def/rig_*.def`, in place of the md3's in
`dk_monsters_e1.def`, the same animation names) and a ragdoll (`af/monster_*.af`), so a monster goes limp when it
dies. The frog's tongue stretches tenfold to spit, which a rigid bone can't: it only slides out (joint scale is to
come).

Every other monster is rigged too, by `./dk rig` from `RIG_MODELS` in `dk` (docs/auto-rigging.md has the table, the
settings and how well each fits): the humanoids (the Mishima workers and guards, the prisoners, the centurion, the
knights, the gangs and the SEALs, Kage, Mikiko as Kage's…) on Doom 3's human joints, with extra bones for capes, wings
and swords; the rest (the Sludge Minion, the Ragemaster, the Battle Boar, the Crox, the spiders, Medusa, Cerberus, the
griffon, the dragon, the turrets, the rats and fish) on their own bones. Each is `model_<name>` (the classname without
`monster_`) in `def/rig_<name>.def`, with its animations at Daikatana's 10 frames a second, hitboxes, both boxes,
`anim_speed` for its walks and runs, its hardpoints as joints (`hr_muzzle`: where the shots leave), a ragdoll
(`af/monster_<name>.af`) and, for Daikatana's robots, `"surface" "metal"`: hits spark white, as Daikatana's did, instead
of bleeding. Their monster defs (behaviour, AIData's values) are still to be written, as the frog's and the
skeet's are.

## Its script

`script/ai/monster_base.script` is what every monster's object has:

- the fields the game keeps each think: `AI_ONGROUND`, `AI_PAIN` (hurt since its last think), `AI_DEAD`,
  `AI_ENEMY_VISIBLE`, `AI_ENEMY_IN_FOV`, `AI_MOVE_DONE`, `AI_BLOCKED` (its move got nowhere), `AI_IMPACT` (it hit
  the world hard), `AI_LEAP_HIT` (its leap met someone), `AI_IN_WATER`; and `skill`;
- `state_Idle` (until it sees someone or is hurt), `state_Combat`, `state_Killed` (its death animation).

`setState( "state_X" )` and its `state_X()` runs from its next think, in its own thread, as straight-line code that
waits for what it waits for. The game runs that thread as it thinks, before it moves it (Doom 3's
`idActor::UpdateScript`).

- **Froginator** (`monster_froginator.script`): it gets about by leaping. It hops after you (`hop_min` to
  `hop_max` a hop, short of what's in the way, crouching a moment between), and nearer than `leap_range` it leaps at
  where you'll be. A leap that meets you hurts (`leap_damage`, once a leap), knocks you back, and it bounces off; one
  that comes down on your head slides off. Up close it bites; in water it swims; with no room to hop it goes on foot.
  A leap is a throw: `getJumpVelocity` gives the arc that lands it there, or none if something's in its way (Doom 3's),
  and one into a wall hurts it (kills it, at one health). Its spit at range is to come, with a projectile of its own.
- **Slaughter Skeet** (`monster_slaughterskeet.script`): skeets crowd over you, each circling at its own height,
  angle and way round (70 to 130 away, 30 to 80 over your head), darting down to bite now and then (once it's in reach)
  and back to their circle, and dodging aside when you hold your aim on them a moment (as Fallout's bloodbugs do): a
  reaction's worth (0.2 to 0.4 s), not just after a dodge, and not every time, more often on hard. In a narrow way
  they circle as far as there's room, round the side that's open.

  Daikatana's were always in the air; these land, as insects do. Left alone, a skeet perches on a wall or a ceiling
  near it (the floor if there's nothing else), its wings raised, and waits: it sees all round from there, and takes
  off at you when you come within 300, aim at it or hurt it, an ambush. Now and then in a fight it rests on a wall a
  moment, off again when you aim at it. `perch( pos, normal )` lands a flyer: its belly to the surface, its head up a
  wall (turned a little to one side) or as it faced, its boxes turned with it; told to move, it pushes off.
  `isPerched()` asks. Its perched pose is the rig's `perch` animation: Daikatana never made one, so the rigger
  picks the frame of its idling and flying where its wings reach out least (raised over its back). Out of sight or far off, they find
  their way to you through the air. It flies as a drone: momentum, banking into turns, bouncing off
  walls (a hard crash hurts it).

## Flying: routes through the air

A flyer flies straight at where it goes when its box gets there in a line; else it takes a route through the air,
as Doom 3's flyers do (`idAASLocal::FlyPathToGoal`), on the map's AAS (`maps/<map>.aas`, made by `./dk aas`). The
game reads it (mint-arena `g_airnav.c`): its areas cover the air as well as the floors, and they're linked through
the faces between them (Doom 3's fly reachabilities). A route is A* from area to area, no liquid, through the faces'
middles, pulled straight with the flyer's box; it's planned again as what it goes to moves, and a flyer heads for
the farthest waypoint it sees. A map with no AAS has its flyers fly straight. The AAS is made for a player's box,
so routes keep that far from the walls. `g_debugMove 1` prints the routes and the flight.

A monster that starts in something (a map's skeet in a physics prop) or flies into something is moved out of it,
to the nearest place its box fits.

The events a monster has (Doom 3's names): `setState`, `getState`; `findEnemy`, `setEnemy`, `clearEnemy`,
`getEnemy`, `enemyRange`, `enemyRange2D`, `getEnemyPos`, `canSee`; `moveToEnemy`, `moveToPosition`,
`moveToEntity`, `wander`, `stopMove`, `moveStatus`, `setMoveSpeed`; `faceEnemy`, `faceEntity`, `turnTo`,
`turnToPos`, `getCurrentYaw`, `facingIdeal`; `setFlySpeed`, `setFlyOffset`, `enableGravity`, `disableGravity`,
`allowMovement`; `perch`, `isPerched`; `getJumpVelocity`; `testMeleeAttack`, `attackMelee`, `directDamage`; `playAnim`, `playCycle`, `animDone`, `hasAnim`; `startSound`. And
an entity's: `setLinearVelocity` throws it (a leap), `getHealth`...

- **Crox** (`monster_crox.script`, crox.cpp): a robot crocodile. It runs at you on land and swims at you in water,
  biting (`damage_crox_bite`, on its attack's 13th frame), on land `atakc`/`atakd`, in water `ataka`/`atakb`; a hit
  makes it flinch one time in five; it gives up on you while you're over 100 above or below it.
- **Protopod** (`monster_protopod.script`, protopod.cpp): a pod that hatches its `hatch_monster` (a slaughter skeet)
  after you when it sees you within `hatch_range` (or by chance within `maybe_range`), then lies open.
- **Skinny Worker** (`monster_skinnyworker.script`, skinnyworker.cpp): harmless. Hurt or alarmed, he runs from you
  for ten seconds and cowers, runs again if you come within 300, and goes back to work when you're gone.
- **Cambot** (`monster_cambot.script`, cambot.cpp): a flying camera on patrol along the `monster_path_corner`s it
  targets. Seeing you (75 degrees either side) it sounds the alarm, `alertMonsters( alarm_range )`: the monsters that
  hear it within 1024 come for you. Then it follows you, `near` to `far` away and 72 above. It never attacks.
- **Rockgat** (`monster_rockgat.script`, rockgat.cpp): a chaingun turret in the rock. It rises when it sees you
  within its `range`, and a second later fires (`attackWeapon`, a hitscan weapon def) about eight a second while
  you're within 20 degrees of level.
- **Thunderskeet** (`monster_thunderskeet.script`, thunderskeet.cpp): flies at you, 96 above; within 600 it hovers,
  charges and fires two slow balls of lightning that bounce about until they touch someone (40 within 256), then darts
  at you or flies off. On e1m1b `target_monster_spawn` brings it, and its death opens the way on and leaves a mega
  shield.
- **Fireflies** (`monster_firefly`, cgame `cg_fireflies.c`): only looks, a swarm of glowing flares on a leash.

What scripts have for these: `attackWeapon( def, offset )` fires a weapon def's shots (hitscan or projectiles, drawn
as the weapon's) from an offset at the enemy, so a monster's weapon is a weapon def no player gets (`weapon_slot`
99, keeping the players' weapons' numbers); `alertMonsters( range )`; `playModelFx( "death" )` plays the model def's
`fx_death` (or `fx_muzzle`, `fx_attack`, `fx_special`). A robot's death is `playModelFx( "death" )`, `hide()`,
`remove()`. Daikatana's map keys on a monster: `deathtarget` is used when it dies, `spawnname` an item it leaves.

## Frame commands

Daikatana's per-monster sound tables (`sounds/e1/m_*.vsc`, each byte XORed with 0x96) say which sound plays on which
frame of each animation, and the attack frames. `./dk` turns them into Doom 3 frame commands
(`tools/vsc/vsc_frames.py`), a def `model_<name>_frames` that the model def of that name takes its frame commands
from, the md3's or the rigged one's (`bg_model.c`). The cgame plays the `sound`s and `fx`; the game runs `melee
<damage def>`, `weapon <weapon def>` (from the monster's `muzzle`) and `call <function>` of its script object as the
animation passes the frame. Each attack frame is `call attackFrame`: the crox's bite and the frog's are their
`attackFrame()`, not a timed guess. Several commands on a frame go in one key, `;` between them.

## What's to come

Ground paths (the frog goes straight at you), the frog's spit, the skeet's hatching animation, the rockgat
lowering (its model has only the rising), the rest of episode 1's monsters, and their getting noticed (an effect
that makes them stand out).
