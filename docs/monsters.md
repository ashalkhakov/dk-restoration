# Monsters

Monsters are Doom 3's kind (idAI): a character entity whose behaviour is its script. The game (mint-arena
`g_monster.c`) moves it, sees for it, hurts and kills it; its script object decides what it does, in states.
Humans and sidekicks, which play more like bots, are to come another way (RTCW's AI Cast).

So far: the Froginator and the Slaughter Skeet, episode 1's (`def/dk_monsters_e1.def`, `script/ai/`). The
campaign spawns them where Daikatana's maps put them.

## A monster

Its def (`"spawnclass" "monster"`) names its model def (the mesh and its animations), its script object and its
numbers, Daikatana's `AIData.csv` at medium skill:

- `health`, `mins`, `maxs`, `modelscale`; `run_speed` (its moves' speed), `turn_rate` (degrees a second);
- `fov`, `sight_range`: whom it sees;
- `melee_range`: how far past its box a bite reaches (a damage def's `range` overrides it);
- `fly` 1: it flies, at `fly_speed`, its thrust changing its velocity by `fly_accel` a second at most, `fly_offset`
  above what it flies at, bobbing `fly_bob`;
- `impact_speed`, `impact_damage`, `impact_bounce`: hitting the world faster than `impact_speed` (a frog's leap,
  a skeet's crash) bounces it off with that much of its speed and hurts it `impact_damage` per 100 u/s more;
- `snd_*`: its sound shaders (`sound/dk_monsters_e1.sndshd`), for its script's `startSound()`.

In the campaign, Daikatana's skill scales its health and speeds: x0.75 on easy, x1.25 on hard
(`"skill_scale" "0"` keeps them).

A damage def (`damage_frog_bite`) has `damage`, `damage_random` (more, at most; Daikatana's) and `range`.

The models are the md3s for now, their animations named as their frames are (`"anim runa" "runa 15 loop"`). Rigged
IQMs keep those names and take their place in the model defs; a model def with a ragdoll (`af/`) makes its
monster go limp when it dies.

## Its script

`script/ai/monster_base.script` is what every monster's object has:

- the fields the game keeps each think: `AI_ONGROUND`, `AI_PAIN` (hurt since its last think), `AI_DEAD`,
  `AI_ENEMY_VISIBLE`, `AI_ENEMY_IN_FOV`, `AI_MOVE_DONE`, `AI_BLOCKED` (its move got nowhere), `AI_IMPACT` (it hit
  the world hard), `AI_IN_WATER`; and `skill`;
- `state_Idle` (until it sees someone or is hurt), `state_Combat`, `state_Killed` (its death animation).

`setState( "state_X" )` and its `state_X()` runs from its next think, in its own thread, as straight-line code that
waits for what it waits for. The game runs that thread as it thinks, before it moves it (Doom 3's
`idActor::UpdateScript`).

- **Froginator** (`monster_froginator.script`): runs at you (it swims in water), bites in reach and, on hard,
  leaps at you from 200 to 500 away. A leap is a throw: the game flies it on its arc, and one into a wall hurts it.
  Its spit at range is to come, with a projectile of its own.
- **Slaughter Skeet** (`monster_slaughterskeet.script`): closes in from above, darts at you half as fast again,
  bites, flies off up and away, and comes again. It flies as a drone: momentum, banking into turns, bouncing off
  walls (a hard crash hurts it).

The events a monster has (Doom 3's names): `setState`, `getState`; `findEnemy`, `setEnemy`, `clearEnemy`,
`getEnemy`, `enemyRange`, `enemyRange2D`, `getEnemyPos`, `canSee`; `moveToEnemy`, `moveToPosition`,
`moveToEntity`, `wander`, `stopMove`, `moveStatus`, `setMoveSpeed`; `faceEnemy`, `faceEntity`, `turnTo`,
`turnToPos`, `getCurrentYaw`, `facingIdeal`; `setFlySpeed`, `setFlyOffset`, `enableGravity`, `disableGravity`,
`allowMovement`; `attackMelee`, `directDamage`; `playAnim`, `playCycle`, `animDone`, `hasAnim`; `startSound`. And
an entity's: `setLinearVelocity` throws it (a leap), `getHealth`...

## What's to come

Paths (it goes straight at you now: AAS routes are next), the frog's spit, the skeet hatching from a protopod,
pain reactions on the other monsters, their rigged models and ragdolls.
