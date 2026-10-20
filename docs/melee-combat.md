# Melee and sword combat: survey and design

The goal is to make katana fighting a core part of the game, with the daikatana as the centrepiece. This note looks at three
earlier systems: Jedi Academy's sabers (OpenJK), what Doom 3 (dhewm3) offers, and what Daikatana itself did. It then proposes a
design for mint-arena and an order to build it in.

Sources:
- OpenJK `codemp/` (paths below are relative to it)
- dhewm3 `neo/`
- the Daikatana source in `dlls/weapons` and `base/client`

## 1. Jedi Academy (OpenJK)

### Moves

The move table drives everything.

- `saberMoveData[]` (`game/bg_saber.c:148`) gives each move:
  - an animation
  - a start and end *quadrant* on an 8-point compass around the body (`Q_BR..Q_B`, `bg_public.h:1474`)
  - a blocking class (`BLK_NO/TIGHT/WIDE`)
  - `chain_idle` (next move with the button released) and `chain_attack` (next move with it held)
  - a trail length
- Families of moves, all generated from the quadrants:
  - starts `LS_S_*`, attacks `LS_A_*`, returns `LS_R_*`
  - transitions `LS_T1_<from>_<to>` (`transitionMove[8][8]`, `:383`)
  - bounces, deflections, parries, broken parries, knockaways
- `PM_SaberAnimTransitionAnim` (`:427`) inserts the start, return or transition move needed between two moves.
- `PM_SaberAttackForMovement` (`:2182`) picks the attack from the movement keys held when attack is pressed:
  - right+forward slashes top-left to bottom-right, forward alone is an overhead, and so on
  - special moves sit on top: lunge, death-from-above, cartwheel, backstab
- Styles (fast, medium, strong, dual, staff) reuse the same table with an animation offset. A style limits how long a chain
  can run (`PM_SaberKataDone`, `:747`). Strong chains only when the swing keeps its momentum, i.e. the chain angle is
  135–215°.
- Timing is just the animation length: `weaponTime = torsoTimer` (`:3721`).

### Prediction

- The whole state machine runs in `bg` pmove, so it's predicted.
- Its "random" choices are seeded from `cmd.serverTime` (`PM_irand_timesync`, `:38`), so client and server agree.

### Hits

Hit detection is server-only (`game/w_saber.c`).

- The blade is a Ghoul2 bolt on the hand. The server evaluates every player's skeleton every frame
  (`G2API_GetBoltMatrix`, `:8892`).
- Each server frame (40 Hz) it sweeps old→new blade:
  - sub-arcs every ~33° of turn, points every 8 units along the blade
  - each trace refined by per-triangle model collision for hit locations and dismemberment (`G_SPSaberDamageTraceLerped`,
    `:5252`)
- Damage scales with the swept length of each trace (`:4065`). That makes it frame-rate dependent.

### Blocking

Blocking is mostly *not* geometric.

- A body hit is auto-blocked if the defender is idle (not attacking) and the point is inside a facing cone (`InFront`, 0.9 /
  0.6 / 0.3 by defence level, `WP_SaberCanBlock`, `:9282`). The sabers never actually meet in that case.
- When blades do meet (`CONTENTS_LIGHTSABER` boxes), the result comes from strength numbers plus `Q_irand` (`:4831-5242`):
  - attack power = style level + how far the blade base moved
  - possible results: lock chance, bounce or deflect by quadrant difference, knockaway, broken parry
- The server writes `saberBlocked` / `saberMove` into the player state. The next pmove turns that into the reaction move.
  Clients only learn of it a round trip later, so animations snap.

### Saber locks

- Start: both players on the ground, facing each other, within 8–80 units (`WP_SabersCheckLock`, `:1459`).
- Struggle: button mashing adds `saberLockHits`, which moves a shared animation frame toward one end
  (`PM_SaberLocked`, `bg_saber.c:1343`).
- End: winning means reaching the animation's end, then a super-break or knockdown.

### Data

- `.sab` files (`bg_saberLoad.c`) define:
  - blades: count, length, radius, colour
  - sounds and effects
  - tuning: damage, knockback, lock, parry and break-parry scales
  - move overrides: kata, lunge, jump attacks
  - flags: throwable, lockable, no dismemberment, …
- Hilts are models with `*blade1..N` bolts.

### Drawing

- The cgame clips the blade against walls (sparks, burn marks).
- The trail is a quad from old base/tip to new base/tip on a blur shader, faded over `trailLength`.
- `CG_SaberCompWork` fakes continuous hits between server frames.

### What it teaches

- **Keep:**
  - the quadrant move graph (believable connected swings from few animations)
  - attack direction from movement keys
  - predicted, deterministic move logic
  - blade trails
  - one data file per weapon
- **Avoid:**
  - server-side skeletons
  - many traces per frame
  - frame-rate dependent power and damage
  - outcomes decided by dice rather than geometry
  - outcomes that arrive a round trip late

## 2. Doom 3 (dhewm3)

### Melee in Doom 3 is minimal

- `idWeapon::Event_Melee` (`game/Weapon.cpp:3001`) is one server-side `TracePoint` along the view. It applies a push
  impulse and a damage def, then plays surface sounds, decals and smoke.
- The fists time the hit with `sys.wait(0.1)` in script.
- It passes the clip id instead of the joint, so damage zones never apply (`:3055`; projectiles convert it,
  `Projectile.cpp:594`).
- AI melee (`FC_MELEE` frame command) is a range box test.

### The collision model is the real prize, and mint-arena already has it

- `CollisionModel_rotate.cpp` rotates a convex trace model through the world *exactly*:
  - analytic edge–edge (Plücker) and vertex–polygon solutions, `Rotation180` at `:1251`
  - about any axis through any point (`rorg`)
- A blade moving between two poses is a screw motion: a rotation about an axis plus a slide along it (Chasles' theorem).
  - The pivot `c` solves `(I−R)c = t⊥`.
  - One `Rotation` about `c`, then a short `Translation` along the axis, sweeps a thin box blade from pose A to pose B with
    no sub-steps. It reports the exact fraction and contact point, normal and material.
- `idClip::Motion` can't be used for this, because its pivot must be the start point. Use `Rotation` / `RotationModel`
  directly.
- Trace models allow a box (8 verts) or a flat polygon blade.

### Animation frame commands

- Defined in `game/anim/Anim_Blend.cpp:290`: sound, fx, event, `melee`, `start_attack`, `end_attack`.
- They fire for every frame crossed, never skipped (`:669`), including in client prediction (`Weapon.cpp:3198`).
- `frame 7 event bladeOn` is the natural way to author hit windows.

### Hit volumes and reactions

- **Damage zones:** `damage_zone <group>` joint lists with `damage_scale` (`Actor.cpp:2321`), and pain animations per zone
  (`pain_<group>`, `:2262`).
- **Articulated figures (AF):** their bodies are trace-model clip models posed to the current animation
  (`AF.cpp:232` `SetupPose`). A blade can be swept against each body with `RotationModel` without linking anything. That
  gives exact per-limb hits.
- **Impulses:** `idAF::ApplyImpulse` at the contact point gives physical hit reactions.

### Doom 3 has no lag compensation

Melee is server-authoritative, and the server keeps no pose history. A multiplayer sword game must add that.

### What it teaches

- Sweep a blade shape exactly with the rotational collision sweep, instead of sampling rays.
- Time the hit with frame commands.
- Hit compound per-limb volumes, with damage zones, pain per zone and impulses at the contact.

## 3. Daikatana

- **Only one sword was built.** `weapon_daikatana` (`daikatana.cpp`) is the only live sword. The special powers (banish,
  barrier, dance, possession, proteus) are empty stubs, so there is no design to recover beyond their names.
- **Attacks:**
  - Six attacks A–G in `meleeInfo[]` (`:253`), each with:
    - a damage frame and a follow-through frame
    - a start/end arc in forward/right/up × range
    - a scorch decal orientation
    - a "can be followed by" bitmask (`DK_AFTER_A` …), i.e. a combo graph
  - Selection is random. A pitch-based choice was written and then commented out.
  - Holding attack chains automatically.
- **Hit test:** at the damage frame the whole arc is swept *at that instant*.
  - 5 radii × 2 box traces of ±16, from the body origin, not the eye.
  - The first hit takes all the damage.
- **Damage:** 40 + 10 per level. Backstab doubles it. Sword against sword (a player or an `IS_SWORD` monster) clanks and
  halves it. There is no knockback at all.
- **Levels:**
  - The sword levels up from its own kills: 0/250/750/1500/3000 experience.
  - Each level brings faster swings (0.036 → 0.02 s per frame), longer combos (2 × level swings), +10 damage and a louder
    ambient hum.
  - Each level escalates the glow on the client (`TrackEntFX_Daikatana`, `cl_tent.cpp:3704`): handle flare, travelling
    flare, lightning from handle to tip, and at level 5 a "negative light" that darkens the surroundings.
  - Level-ups spawn rising rings.
  - Kills play a vanquish spiral.
- **Weak spots:**
  - no swing trail
  - blood that traces back toward the attacker, so it's basically broken
  - bots always hit with the disruptor glove and silverclaw
- **Other melee weapons:**
  - **Disruptor glove:** one ray of 80, 60 damage with inertial knockback, blue sparks.
  - **Gas hands:** the glove powered up: 1000 damage, a timed pickup in single player, lasts until death in deathmatch.
  - **Hammer (E2):** charge while held, release to strike. A full charge on the ground causes an earthquake and radius damage.
  - **Silverclaw (E3):** like the glove, plus claw-mark decals.
- **What it teaches:**
  - The combo graph with damage and follow-through frames is compact and good.
  - The levelling sword is the weapon's identity.
  - Backstab and sword-clash modifiers.
  - Swing-oriented slash decals.

## 4. What mint-arena has today

- **Collision:** a Doom 3 collision model in the engine (spearmint `code/cm2`), including the exact rotational sweep. The
  game also has a C port of `idClip` (`code/game/g_clip.c`), so `ClipRotation` and `ClipRotationModel` are there.
- **Data:** Doom 3-style entity defs (`DEFS.md`, `bg_defs.c`).
  - Weapons are defs.
  - `"melee"` is a stand-in: a hitscan trace of `range` on the fire frame.
- **Animation:**
  - Prediction runs pmove; weapon animations go through `WP_ANIM_*` in the player state.
  - First-person md3 models play named frame groups (`anim_fire "ataka"`).
- **Lag compensation:** `g_unlagged.c` already keeps position history per player.
- **Hit volumes:** player hit volumes are boxes. Compound convex volumes are being added for props (trees), and the same
  code can give bodies a few boxes.
- **Effects:** `.efx` files, decals, dynamic lights.

## 5. Proposed design

### Data

Each sword is a weapon def. Its moves are defs too, in the spirit of JKA's table and DK's `meleeInfo`:

```
entityDef weapon_daikatana {
	"weapon_slot"		"7"
	"melee"				"1"
	"def_blade"			"blade_daikatana"
	"moves"				"dk_a dk_b dk_c dk_e dk_f dk_g"
	"levels"			"0 250 750 1500 3000"	// experience for levels 2..5
	"level_speed"		"0.1"					// per level: 10% faster swings
	"level_damage"		"10"
	"level_chain"		"2"						// chain length = 2 × level
	...
}

entityDef blade_daikatana {
	"length"			"40"
	"width"				"2"						// the swept box: length × width × thickness
	"thickness"			"0.5"
	"tag_base"			"tag_blade"				// on the world model, or "offset"/"dir" from tag_weapon
	"fx_clash"			"dk/sword_clash"
	"fx_trail"			"dk/sword_trail"
	"mtr_slash"			"dk/slash"
}

entityDef dk_a {
	"anim"				"ataka"
	"quad_start"		"R"						// JKA quadrants: where the blade starts and ends
	"quad_end"			"FL"
	"blade_on"			"5"						// frames the blade cuts
	"blade_off"			"9"
	"follow_through"	"11"					// the frame a chained move may start from
	"next"				"dk_f dk_c dk_e dk_g"	// DK's "can follow with"
	"damage"			"40"
	"knockback"			"60"
	"block"				"wide"					// blocking class while this plays
	"input"				"right"					// chosen with this movement held
}
```

### Where the blade is

The blade's path is data, sampled once, not a skeleton evaluated on the server. For each move frame, store the blade's base
and tip relative to the player's origin and view angles:

- either authored as DK-style arcs (start/end vectors per swipe, interpolated)
- or baked by the converter from the third-person model's tag on each frame

Then pmove, game and cgame all compute the same blade pose from (move, frame time, origin, view angles). That's
deterministic and cheap, and it's how DK thought of it. It's also what removes JKA's server/client mismatch.

### Sweeping

- Each pmove step (not each server frame, so it's frame-rate independent like Doom 3's frame commands), build the screw
  motion from the previous to the current blade pose.
- Sweep a thin box trace model with `ClipRotation` / `ClipTranslation` against:
  - the world: sparks, a slash decal oriented to the swing, and on stone a bounce for heavy moves
  - other players' hit volumes: a few convex boxes per body (head, torso, arms, legs), rewound by `g_unlagged`
  - other blades
- Damage once per victim per move, scaled by zone. There's no frame-rate dependent "swept length" damage.

### Clashes and blocking

Blocking is geometric where it can be:

- **Blade meets blade:** a real clash. The outcome comes from the two moves' classes:
  - attack vs a guard or parry: the attacker bounces (JKA's quadrant bounce or deflect table)
  - attack vs attack: both bounce
  - heavy vs light: a broken parry
  - plus a lock chance when both are straight on
- **Guard stance (hold alt-attack):** keeps the blade in a block pose aimed by the view, the "parry position" the moves'
  quadrants describe. A strike that meets it is a geometric clash. A strike that lands behind or around it is a hit.
  There's no dice and no facing cone. A short perfect-parry window at the start of a guard gives a riposte.
- **Locks:** JKA-style, as a later stage. Pmove moves a shared frame by button presses, with deterministic outcomes.

### Prediction and networking

- The move state machine lives in bg pmove, like JKA: attack choice from movement keys, chains, guard. Any randomness is
  seeded from `serverTime`.
- The attacker's own hits on the world (sparks, trails) are predicted.
- Damage and clashes against others are server-authoritative, with victims rewound to the attacker's view (unlagged).
- The player state needs: `swordMove`, `swordMoveTime`, `swordChain`, `swordBlocked` (a reaction the server forces, like
  `saberBlocked`), and the sword level.

### Feel

- **Hit-stop:** a few frames' pause for attacker and victim on a hit or clash.
- **Pain and knockback:** pain animations by zone and knockback from the move.
- **Trail and clash effects:**
  - a cgame trail ribbon from the sampled base/tip, data in `fx_trail`
  - clash sparks at the exact contact point
- **DK flavour:**
  - levels from sword kills: faster, longer chains, more damage, hum
  - the level glow: flares, lightning, dark light at level 5, as `.efx`
  - vanquish and level-up effects
  - backstab ×2

### Bots

- Bots pick moves from range, angle and the enemy's guard.
- No guaranteed hits like DK's bots had: they swing like players.

## 6. Order of work

1. **Moves without collision.**
   - Move defs, the predicted pmove state machine, chains, and attack direction from movement keys.
   - View model animations per move.
   - Damage by a stand-in short sweep at `blade_on`.
   - Daikatana with levels and its hum.
2. **Blade paths and exact sweeps.**
   - Blade pose tables (authored arcs first, baked from models later).
   - The screw-motion sweep against the world and per-player compound boxes, rewound by unlagged.
   - Slash decals, sparks and trails.
3. **Clashes and guard.**
   - Blade-vs-blade sweeps, the bounce/deflect/broken-parry reactions through a predicted `swordBlocked`.
   - Guard stance on alt-attack, perfect-parry riposte, hit-stop.
4. **Locks.** Lock detection, the struggle, and break outcomes.
5. **Reactions and polish.**
   - Pain per zone and knockback.
   - Articulated-figure (ragdoll) impulses on kills.
   - DK's level glow and vanquish effects.
   - Bot sword AI.

## 7. Questions for you

- **Attack choice:** directional from movement keys (JKA), view pitch, or DK's random chains? Or directional with DK's
  follow-on graph?
- **Blocking:** a guard button (alt-attack while holding the sword), or JKA's automatic block when idle?
- **Daikatana levels:** keep DK's per-life experience in deathmatch (reset on death), or per match?
- **Other weapons:** should the gloves, gas hands, hammer and silverclaw share the move system? This design covers all of
  them, but they could stay simple traces.
- **Third-person bodies:** player hit zones as a few boxes per body part, or swept against the animated model like Ghoul2?
  The boxes fit the collision model and are cheap.
