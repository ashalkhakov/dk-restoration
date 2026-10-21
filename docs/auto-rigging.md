# Skeletal characters, rigged automatically

Daikatana's characters are vertex-animated: each `.dkm` (converted to `.md3`) stores every vertex on every frame.
Hitboxes and sword combat need skeletons. `tools/rig/autorig.py` recovers a skeleton and skinning weights from those
frames, so nobody has to rig in Blender, and it keeps Daikatana's own animations. Every character and monster is
rigged so, one skeletal model each that does everything, in game and in the cinematics (see
[Every character and monster](#every-character-and-monster)): the humanoids on Doom 3's human joints, the others
(`tools/rig/creature_rig.py`) on bones found from their animations.

```
./dk rig                 # all of RIG_MODELS, into dkres/models/rigged/, their defs into def/, ragdolls into af/
./dk rig hiro kage       # some
./dk rigshots kage harpy # them in e1m1a, three to a screenshot (out/shots/rig/)
```

A character takes about 10 to 20 seconds in plain Python (numpy isn't needed), a humanoid more than twice that (it's
rigged with its legs placed and fitted, then again the better way); the batch of 97 models about four minutes, 12 at
a time.

## How it works

This is a small form of skinning decomposition, after Le & Deng's SSDR (2012/2014), which Electronic Arts' Dem Bones
implements.

1. **Skeleton.** The joints are Doom 3's: its human rig's names and hierarchy (`origin`, `Body`, `Hips`, `Lupleg`,
   `Lloleg`, `Lankle_r`, `Waist`, `Chest`, `Loneck`, `Head`, `Luparm`, `Lloarm`, `Lhand`, and the right side), so tools and
   animations made for Doom 3 skeletons line up. Where the joints go is measured from the mesh, because Daikatana's
   characters aren't built like Doom 3's:
   - the neck, where the body narrows into the head
   - the crotch, going down, where a gap first opens between the legs: no triangle crosses the middle there
     (going up from the feet stops where the knees touch, and a low-poly trunk's big triangles span the middle
     without a vertex there)
   - the shoulders, from the body's width there
   - the hands, at the arms' outermost points (the right one at the gun hardpoint)
   - the legs, along each leg's own line: a character's first frame is often a stance, not an A- or T-pose (Hiro's:
     legs apart, one forward and both bent), so a leg's joints aren't at heights. The hips level with the pelvis, in
     toward the feet as Doom 3's legs splay (half as far out as the ankles), not by the side's vertexes at the
     crotch's height, where the hanging hands are (the fat worker's hip was in his hand, and the walk IK dragged his
     body out). Each knee where its leg bends, 30% to 60% of the way down: the slabs of the leg that stand farthest
     forward of the line from hip to ankle (the kneecap; lower, a coat's hem or a boot's top stands out), and there
     the middle of the leg's outline where the mesh is cut, not the cap. Each ankle on its shin's line: the middles of
     the shin's outline higher up, clear of the foot, carried down to the ankle's height (a low-poly shin has hardly a
     vertex between the ankle and the knee, and a slanted shin over the foot is behind its ankle). The motion then
     leaves them there. Where the animations do bend the knees (the skinny worker's), the motion knows them better:
     every humanoid is rigged both ways, its legs placed so and as the motion fits them (the rigger as it was), and
     keeps the one that carries Daikatana's frames better (`legs placed` or `legs fitted` in its log). 31 of the 59
     keep the placed legs, Hiro, Mikiko and Superfly among them; none fits worse than before, and on average they fit
     0.38 units off, 0.47 before.
2. **Segments.** Each vertex starts on the nearest bone. Each bone's rigid motion is then fitted to every frame (Horn's
   quaternion method), and each vertex moves to the neighbouring bone whose motion carries it best. A term for nearness
   keeps parts that move together (chest and neck) from trading vertices at random. A vertex its bone carries badly
   (over 4 units off on average) tries every bone: a hip vertex the hanging hand took at first can't reach the leg
   through neighbours. Repeat until stable, usually 3–4 rounds. Then a leg's vertices go by where they are along
   it: the animations hardly bend the knees, so the motion can't tell a thigh from its shin, but the walk IK bends
   them. One no leg bone carries well (a hand hanging against the thigh) goes back to the bone that does.
3. **Joints.** Each joint goes to the point that moves least between the parent's and the child's segments over the
   frames, by least squares, but only along the directions the motion pins down. A hinge (knee, elbow) agrees all
   along its axis, and there the template's place stays. A joint moves at most a tenth of the height, and the legs'
   joints keep the template's heights (the knee halfway from crotch to floor): the walk IK bends the leg at them.
4. **Weights.** Each vertex blends its own bone with a neighbouring one where that fits the frames better (two weights a
   vertex), never one leg with the other (the walk IK moves them apart), and along a leg only near the joint between
   the two bones. The knees and the elbows go by place instead: across each, the vertexes of the two bones blend
   smoothly over a band about the joint (30% of the shorter bone either side), as Doom 3's rigs are weighted.
   Daikatana's frames hardly bend them, so a blend fitted to them lands off the joint (on Hiro's lower thigh) and the
   limb thins where the walk IK or a retargeted animation bends it: bent 110°, the thinnest tenth of Mikiko's knee
   keeps 43% of its thickness (19% fitted), Hiro's elbow 18% (6%). Linear blending still pinches the inside of a deep
   bend; dual-quaternion skinning in the renderer is what holds volume (to come). Seams are welded: vertices of different surfaces in one place (Hiro's head on his neck) take
   the same weights, whichever carries the group best, or a pose the animations never had (the head pitched to aim)
   opens a hole between the surfaces. The rigger also reports the triangles that turn over (culled, so a hole) in
   some frames against Daikatana's; `RIG_FLIPS=<n>` lists more of them.
5. **Rest orientations.** Each joint rests along its bone (x toward the child), so hitboxes fitted in its space hug the
   limb.
6. **Hair.** A ponytail gets its own little spine: the head surface's vertices behind the back of the skull are hair,
   and up to three bones (`Ponytail1`…, one per six vertices) run down its middle from the root, parented to `Head`.
   They carry only the hair, which may also stay on the head or neck, and have no hitboxes. Hiro's hangs from the
   back of his head, Mikiko's from her crown; Superfly has none.
7. **Hardpoints.** Daikatana's hardpoints are surfaces of one triangle. They become rigid attachment joints: `hp_gun`
   and `ctf_flag` are `WEAPON_ATTACHER` and `FLAG_ATTACHER` on the right hand and the chest, as Doom 3 has `*_ATTACHER`
   joints. The monsters' (`hr_muzzle`, `hp_head`, `eye1`, `sword1`…) keep their names, each on the bone whose motion
   carries its triangle best: where the muzzle flash, the eyes' glow or the sword's trail goes.
8. **Output.**
   - An IQM: the first frame as the rest pose, every frame as a pose, and the frame names (`run01`…) giving the
     animations (`amb`, `walk`, `run`, `atak`, `die`…), the idle and moving ones looping.
   - A model def with a hitbox per bone: the box around the bone's vertices in the joint's space, zoned
     `head` (×2), `torso`, `arms` and `legs` (×0.75).

Daikatana's meshes have a few holes: one missing triangle each in Hiro (the back of his neck, beside the ponytail),
Mikiko and Superfly, which the original's culling shows as well. The rigger caps them: a loop of three open edges in a
surface gets a triangle wound like its neighbours.

## The player characters

| Character | Vertexes | Frames | Animations | Average error | Worst vertex | Height |
| --- | --- | --- | --- | --- | --- | --- |
| Hiro | 726 | 1394 | 82 | 0.18 | 8 | 54 |
| Mikiko | 637 | 1259 | 78 | 0.19 | 8 | 58 |
| Superfly | 709 | 1263 | 77 | 0.38 | 10 | 54 |

The error is how far each skinned vertex lands from Daikatana's, over all frames. In game the rigged and original models
look the same frame for frame (`cg_drawSkeleton 1` shows the joints, 2 without the mesh; `def/char_hiro_md3.def` plays
the original to compare:
`spawncharacter model_hiro run -4 30; spawncharacter model_hiro_md3 run -4 -30`).

A few vertices go off (8–9 units) on a few frames: parts that move in ways no single limb does, such as the tip of
Mikiko's ponytail, or the body during the death animations. `RIG_WORST=1 ./dk rig` lists the worst, with the
animation and the bones.

**The skin table.** The rigger writes `dkres/models/rigged/<name>_skin.txt`: a line per vertex with its surface and
index, its bone, the bone it blends with and the weight, how far it lands from Daikatana's (on average and at worst),
and where it rests. Where the rigger gets one wrong, `tools/rig/skin/<name>.txt` pins it to a bone by hand
(`<surface>:<index> <bone> [<blend bone> <weight>]`). The table stays in `dkres` (it holds Daikatana's positions);
the pins are only numbers and names, so they're committed.

## Every character and monster

`./dk rig` rigs every model of `RIG_MODELS` in `dk`, a table with a line a model:

```
# name           rigger    model (under dkres/models)  [bones=N] [extra=N] [fps=N] [iqm=name]
fatworker        human     e1/m_mwfaty
froginator       creature  e1/m_frog              bones=16
priest           human     cinematic/c_priest_e3m1  iqm=priest
```

- **name**: the monster's classname without `monster_` (Daikatana's `AIData.csv` and its monster table,
  `monster_fatworker` → `models/e1/m_mwfaty`), or the character's. The model def is `model_<name>`.
- **rigger**: `player` (autorig, a player character: `def/char_<name>.def`, `af/char_<name>.af`, player animations,
  a voice), `human` (autorig, a monster or another character: `def/rig_<name>.def`, `af/monster_<name>.af`), `lying`
  (autorig `--lying`, a body lying on its back) or `creature` (`creature_rig.py`, its own bones).
- **bones=** the most bones a creature gets; **extra=** the most extra bones a humanoid gets (8 by default; the
  players none, so their joints stay as they were); **fps=** the animations' rate (10 by default, a server frame
  each, as Daikatana plays its monsters; the players' 20); **iqm=** the IQM's name (by default the model's file name
  without `m_`, `dkres/models/rigged/mwfaty.iqm`).
- `RIG_ANIMS_<name>` (`"<anim> <fps> [loop];..."`) sets animations one by one; otherwise the idle (`amba`) and the
  ways of getting about (`walk*`, `run*`, `swim*`, `fly*`, `hover*`, `row*`) loop.

The batch runs `$JOBS` at a time, each one's output in `dkres/models/rigged/<name>.log` (the IQMs and the skin tables
stay there, not committed). It ends with `dkres/models/rigged/results.txt`, a line a model with its fit, which the table
below is. `./dk rigshots [name...]` spawns them in e1m1a, three to a screenshot (`out/shots/rig/`, `DEAD=1` kills the
middle one to see its ragdoll).

Which rigger: a model with two legs, two arms and a head is a humanoid, on Doom 3's joints, so the walk IK, the head's
look-at and a face (a jaw to come), and retargeting (`tools/rig/retarget.py`) work on it as on Hiro. The rest (blobs,
robots, beasts, turrets, fish) get their own bones; the creature rigger names one `Head` when a branch reaches ahead.
Both riggers were run on every candidate and the error compared: the creature rigger, with more bones, fits humanoids a
little better, but without Doom 3's names; the template fits the non-humanoids (the Sludge Minion 1.9, the Ragemaster
0.9) much worse than their own bones do (0.12, 0.05).

### What the batch added to the riggers

- **Extra bones** (autorig `--extra N`). The template has no bone for a cape, wings, a held sword or more arms. The
  vertexes no template bone carries well (over 2% of the height off, on average) are grouped by the mesh into pieces,
  each split by its motion until it moves rigidly (two seeds far apart, each vertex to the half that carries it best),
  the biggest first; each piece becomes a bone (`<parent>_<n>`, `Chest_1`) on the bone it meets most, with the
  vertexes it carries at least twice as well. A separate piece of mesh (a prop) can be one from a triangle, otherwise
  eight vertexes. An extra bone leaves its parent's rest orientation alone, so the template bones' hitboxes don't
  turn. Kage 1.00 → 0.49, Gharroth 1.10 → 0.66 (worst 85 → 33), the prisoner 0.73 → 0.25.
- **The neck** (monsters only, the players keep theirs). A helmet, a mane or a raised arm made the width test put the
  neck at the very top. The head hardpoint (`hp_head`) gives it where there is one; otherwise a head under 8% of the
  height goes by Doom 3's proportions (13% below the top of the head: the highest place near the body's axis with a
  head's worth of mesh, not a raised sword). A head that never turns on its body (a helmet), which the motion can't tell
  from the chest, is the mesh over the neck. The Mishima guard 0.37 → 0.20.
- **Hardpoints** of any name (above), on the bone that carries them, in both riggers.
- **Ground speed** of the creatures' walks and runs (`anim_speed`): what's on the ground goes back as fast as the
  creature goes forward (the median over the frames of the lowest vertexes' backward speed).
- **Unique names**: two forks of a creature's skeleton could come to the same bone name (the Death Sphere's
  `Head4b`), and its ragdoll wouldn't load.
- **The game's limits**: mint-arena kept 63 model defs and 16 articulated figures; now 255 and 128
  (`MAX_MODEL_DEFS`, `AF_MAX_DECLS`).

### Results

The error is how far the skinned vertexes land from Daikatana's over every frame, in units; the size is the height
(humanoids) or the biggest extent (creatures). Joints count the origin and the hardpoints.

| Model | Rigger | From | Vertexes | Frames | Animations | Joints | Average error | Worst | Size | Extra bones, hardpoints |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hiro | player | global/m_hiro | 726 | 1394 | 82 | 24 | 0.182 | 8.46 | 54 | WEAPON_ATTACHER on Rhand, FLAG_ATTACHER on Chest |
| mikiko | player | global/m_mikiko | 637 | 1259 | 78 | 23 | 0.192 | 7.67 | 58 | WEAPON_ATTACHER on Rhand, FLAG_ATTACHER on Chest |
| superfly | player | global/m_superfly | 709 | 1263 | 77 | 21 | 0.376 | 9.86 | 54 | FLAG_ATTACHER on Chest, WEAPON_ATTACHER on Rhand |
| dead | lying | e1/m_dead | 239 | 10 | 1 | 19 | 0.664 | 23.39 | 60 |  |
| fatworker | human | e1/m_mwfaty | 449 | 793 | 36 | 19 | 0.330 | 7.60 | 53 | 2 extra |
| skinnyworker | human | e1/m_mwskny | 473 | 1123 | 73 | 23 | 0.250 | 7.74 | 57 | 4 extra |
| surgeon | human | e1/m_mwsurgeon | 372 | 646 | 44 | 20 | 0.280 | 8.58 | 57 | 1 extra |
| labworker | human | e1/m_labworker | 603 | 231 | 11 | 22 | 0.285 | 7.68 | 61 | 3 extra |
| mishimaguard | human | e1/m_mwguard | 431 | 374 | 33 | 23 | 0.222 | 6.11 | 57 | 3 extra; hp_head on Loneck, hr_muzzle on Waist |
| cryotech | human | e1/m_cryotech | 688 | 539 | 30 | 28 | 0.411 | 47.63 | 60 | 8 extra; hr_muzzle on Rupleg_2 |
| prisoner | human | e1/m_priza | 503 | 280 | 14 | 27 | 0.253 | 11.27 | 61 | 8 extra |
| prisonerb | human | e1/m_prizb | 523 | 296 | 19 | 19 | 0.205 | 4.88 | 59 | 2 extra |
| torture1 | human | e1/m_torture1 | 241 | 81 | 4 | 19 | 0.363 | 5.15 | 59 |  |
| torture2 | human | e1/m_torture2 | 298 | 29 | 1 | 21 | 0.460 | 7.74 | 58 | 1 extra; trans66 on Lloleg |
| inmater | human | e1/m_inmater | 803 | 231 | 10 | 28 | 0.201 | 9.38 | 86 | 8 extra; hr_muzzle on Lhand |
| froginator | creature | e1/m_frog | 465 | 190 | 11 | 17 | 0.223 | 35.60 | 31 | Head |
| slaughterskeet | creature | e1/m_skeeter | 334 | 170 | 8 | 7 | 0.333 | 8.14 | 45 | Head |
| thunderskeet | creature | e1/m_tskeet | 485 | 102 | 6 | 11 | 1.414 | 25.08 | 277 | Head |
| venomvermin | creature | e1/m_vermin | 419 | 167 | 9 | 14 | 0.207 | 4.50 | 53 | Head |
| sludgeminion | creature | e1/m_sludgeminion | 781 | 285 | 10 | 22 | 0.118 | 7.90 | 105 |  |
| ragemaster | creature | e1/m_ragemaster | 579 | 276 | 10 | 24 | 0.051 | 31.61 | 87 | Head |
| psyclaw | creature | e1/m_psyclaw | 637 | 170 | 9 | 19 | 0.368 | 11.56 | 101 | Head |
| battleboar | creature | e1/m_bboar | 689 | 253 | 12 | 23 | 0.143 | 6.07 | 53 | hr_muzzle on Head2, hr_muzzle1 on Head2b; Head |
| crox | creature | e1/m_croco | 496 | 226 | 13 | 12 | 0.847 | 10.30 | 144 | Head |
| protopod | creature | e1/m_proto | 320 | 23 | 2 | 13 | 0.814 | 16.43 | 10 | Head |
| cambot | creature | e1/m_cambot | 470 | 32 | 3 | 6 | 0.017 | 0.05 | 88 | hr_light on Tail1 |
| deathsphere | creature | e1/m_dsphere | 500 | 270 | 7 | 21 | 0.381 | 15.62 | 49 | hr_muzzle0 on Head3b, hr_muzzle1 on Head4bb, hr_muzzle2 on Tail1, hr_muzzle3 on Head3; Head |
| lasergat | creature | e1/m_lasergat | 432 | 19 | 5 | 18 | 0.003 | 0.02 | 24 | hr_muzzle1 on Lwingb3b, hr_muzzle2 on Head; Head |
| trackattack | creature | e1/m_trakatak | 393 | 6 | 1 | 12 | 0.004 | 0.04 | 33 | hr_muzzle1 on Headb1, hr_muzzle2 on Body; Head |
| rockgat | creature | e1/m_gatguns | 164 | 12 | 2 | 10 | 0.020 | 0.17 | 53 | Head |
| centurion | human | e2/m_centurion | 535 | 172 | 9 | 24 | 0.760 | 27.44 | 76 | 5 extra |
| satyr | human | e2/m_satyr | 503 | 291 | 11 | 24 | 0.312 | 8.71 | 59 | 5 extra |
| skeleton | human | e2/m_skeleton | 311 | 319 | 18 | 21 | 0.471 | 53.33 | 54 | 2 extra |
| thief | human | e2/m_thief | 445 | 246 | 10 | 25 | 0.238 | 11.29 | 34 | 6 extra |
| ferryman | human | e2/m_ferryman | 452 | 256 | 11 | 19 | 0.233 | 19.05 | 63 |  |
| harpy | human | e2/m_harpy | 559 | 342 | 13 | 24 | 0.578 | 27.42 | 52 | 6 extra |
| cyclops | human | e2/m_cyclops | 472 | 305 | 11 | 20 | 0.701 | 62.25 | 79 | 4 extra |
| minotaur | human | e2/m_minotaur | 2538 | 183 | 6 | 27 | 0.654 | 83.78 | 95 | 8 extra |
| kingminos | human | e2/m_kminos | 265 | 210 | 7 | 20 | 0.256 | 8.52 | 48 | 1 extra |
| column | creature | e2/m_column | 487 | 216 | 11 | 15 | 0.373 | 10.42 | 79 | Head |
| medusa | creature | e2/m_medusa | 603 | 251 | 10 | 20 | 0.854 | 21.31 | 192 | eye2 on Head4, eye1 on Head4; Head |
| cerberus | creature | e2/m_cerberus | 575 | 196 | 10 | 20 | 0.464 | 10.25 | 76 | Head |
| griffon | creature | e2/m_griffon | 530 | 333 | 16 | 16 | 1.154 | 61.21 | 173 | Head |
| spider | creature | e2/m_spider | 412 | 149 | 8 | 20 | 0.806 | 17.41 | 114 | Head |
| smallspider | creature | e2/m_sspid | 538 | 177 | 9 | 22 | 0.831 | 15.17 | 114 | Head |
| buboid | human | e3/m_buboid | 524 | 361 | 13 | 19 | 0.342 | 64.57 | 50 |  |
| priest | human | cinematic/c_priest_e3m1 | 443 | 320 | 13 | 19 | 0.123 | 5.08 | 57 |  |
| dwarf | human | e3/m_dwarf | 525 | 292 | 12 | 27 | 0.279 | 14.28 | 43 | 8 extra |
| fletcher | human | e3/m_fletcher | 595 | 279 | 10 | 19 | 0.312 | 15.72 | 72 | 1 extra |
| lycanthir | human | e3/m_lycanthir | 478 | 341 | 15 | 20 | 0.443 | 13.74 | 54 | 1 extra |
| knight1 | human | e3/m_knight1 | 524 | 285 | 10 | 21 | 0.272 | 13.26 | 54 | hr_muzzle1 on Rhand, hr_muzzle2 on Rhand |
| knight2 | human | e3/m_knight2 | 448 | 245 | 10 | 21 | 0.229 | 11.27 | 63 | hr_muzzle1 on Rloarm, hr_muzzle2 on Rloarm |
| garroth | human | e3/m_gharroth | 549 | 254 | 11 | 21 | 0.991 | 51.73 | 101 | 1 extra |
| nharre | human | e3/m_nharre | 661 | 242 | 8 | 27 | 0.357 | 20.80 | 56 | 8 extra |
| stavros | human | e3/m_stavros | 607 | 136 | 5 | 24 | 0.478 | 15.24 | 64 | 5 extra |
| wyndrax | human | e3/m_wyndrax | 839 | 294 | 15 | 27 | 0.446 | 43.21 | 59 | 8 extra |
| wizard | human | e3/m_wizard | 510 | 325 | 13 | 21 | 1.067 | 85.10 | 86 | 2 extra |
| togadude | human | e3/m_toga_dude | 378 | 1 | 1 | 19 | 0.000 | 0.00 | 38 |  |
| togagirl | human | e3/m_toga_girl | 422 | 1 | 1 | 19 | 0.000 | 0.00 | 54 |  |
| plague_rat | creature | e3/m_prat | 284 | 238 | 13 | 15 | 0.319 | 4.63 | 55 |  |
| rotworm | creature | e3/m_rotworm | 258 | 151 | 8 | 13 | 0.254 | 4.17 | 30 | Head |
| doombat | creature | e3/m_doombat | 384 | 80 | 6 | 17 | 0.635 | 10.99 | 48 | Head |
| dragon | creature | e3/m_dragon | 1265 | 164 | 6 | 25 | 3.188 | 54.13 | 527 | hr_muzzle on Head2; Head |
| blackprisoner | human | e4/m_bpris | 441 | 439 | 15 | 22 | 0.407 | 5.36 | 70 | 3 extra |
| whiteprisoner | human | e4/m_wpris | 437 | 391 | 13 | 19 | 0.487 | 5.47 | 70 |  |
| chaingang | human | e4/m_chgang | 564 | 525 | 24 | 24 | 0.392 | 16.20 | 63 | 1 extra; hr_muzzle on Rupleg |
| femgang | human | e4/m_femgang | 539 | 211 | 10 | 19 | 0.141 | 4.00 | 54 | 2 extra |
| rocketdude | human | e4/m_rockgang | 524 | 300 | 11 | 22 | 0.364 | 24.09 | 65 | 2 extra; hr_muzzle on Rhand_1 |
| uzigang | human | e4/m_uzi | 553 | 245 | 11 | 21 | 0.303 | 8.66 | 58 | 2 extra |
| rocketmp | human | e4/m_rocketmp | 525 | 192 | 9 | 21 | 0.573 | 32.90 | 62 | 2 extra; hr_muzzle1 on Loneck, hr_muzzle2 on Loneck |
| sealcommando | human | e4/m_scomndo | 588 | 265 | 10 | 21 | 0.216 | 4.73 | 58 | hr_muzzle1 on Rloarm, hr_muzzle2 on Lloarm |
| sealcaptain | human | e4/m_sealcap | 700 | 250 | 10 | 20 | 0.246 | 8.07 | 63 | 1 extra; hr_muzzle1 on Lhand |
| sealgirl | human | e4/m_sgirl | 481 | 263 | 10 | 20 | 0.654 | 50.82 | 53 | hr_muzzle1 on Lloarm |
| sealdiver | human | e4/m_sdiver | 588 | 244 | 11 | 20 | 0.254 | 29.97 | 53 | 1 extra |
| labmonkey | human | e4/m_labmonkey | 473 | 386 | 16 | 23 | 0.482 | 23.22 | 39 | 4 extra |
| kage | human | e4/m_kage | 845 | 347 | 16 | 31 | 0.480 | 35.74 | 58 | 8 extra; sword1 on Rupleg, sword2 on Lloarm, eye1 on Loneck, eye2 on Loneck |
| drugdealer | human | e4/m_drug | 369 | 1 | 1 | 19 | 0.000 | 0.00 | 56 |  |
| alien | creature | e4/m_alien | 429 | 114 | 6 | 10 | 0.547 | 12.03 | 88 | Head |
| piperat | creature | e4/m_piperat | 287 | 238 | 13 | 13 | 0.346 | 4.63 | 55 |  |
| shark | creature | e4/m_shark | 335 | 168 | 8 | 7 | 0.647 | 14.03 | 156 | Head |
| ghost | creature | e4/we_kage | 337 | 89 | 4 | 16 | 0.848 | 10.91 | 118 | left_hand on Lfore2, right_hand on Rfore1, tail on Head; Head |
| goldfish | creature | global/e_goldfish | 45 | 102 | 4 | 3 | 0.140 | 1.24 | 23 |  |
| greyfish | creature | global/e_greyfish | 44 | 61 | 3 | 3 | 0.257 | 3.11 | 19 |  |
| guppy | creature | global/e_guppy | 13 | 41 | 3 | 2 | 0.277 | 2.06 | 8 |  |
| guppy2 | creature | global/e_guppy2 | 13 | 41 | 3 | 2 | 0.294 | 2.36 | 9 |  |
| seagull | creature | e4/d4_gull | 67 | 80 | 2 | 4 | 0.764 | 8.60 | 51 |  |
| dopefish | creature | global/dopefish | 245 | 74 | 7 | 13 | 0.238 | 3.71 | 45 | Head |
| mikikomonster | human | global/m_smikiko | 694 | 154 | 8 | 25 | 0.246 | 6.79 | 58 | eye2 on Head, eye1 on Head, sword1 on Rloarm, sword2 on Loneck |
| mikikofly | creature | global/m_mikikofly | 1349 | 241 | 12 | 27 | 0.249 | 19.75 | 54 | hp_gun on Headb4, ctf_flag on Headb3, hp_gun2 on Headb3c, ctf_flag2 on Headb1; Head |
| casseti | human | cinematic/c_casseti_e4m1 | 458 | 271 | 8 | 23 | 0.217 | 7.05 | 58 | 4 extra |
| gusagi | human | cinematic/c_gusagi_e2m3 | 551 | 643 | 24 | 20 | 0.828 | 27.35 | 47 | 2 extra |
| usagi | human | cinematic/c_usagi_intr | 554 | 550 | 23 | 20 | 0.967 | 30.23 | 47 | 2 extra |
| inshiro | human | cinematic/c_inshiro_intr | 634 | 297 | 10 | 19 | 0.749 | 23.61 | 50 |  |
| ninja | human | cinematic/c_ninja_intr | 345 | 248 | 14 | 24 | 0.712 | 27.31 | 41 | 1 extra |
| osaka | human | cinematic/c_osaka_intr | 523 | 140 | 6 | 19 | 0.108 | 3.36 | 58 |  |
| tatsuo | human | cinematic/c_tatsuo_e4m4 | 638 | 338 | 11 | 19 | 0.186 | 49.49 | 61 |  |
| toshiro | lying | cinematic/c_tosh_intr | 366 | 515 | 24 | 19 | 1.139 | 42.78 | 47 |  |

The one-frame models (the toga people in e3, the drug dealer) have no motion to fit: their joints are the template's
placed in the mesh, each vertex on the nearest bone, so they can be posed and go limp but their error says nothing.
The priest's own model (`m_priest`) is one frame too; the cinematic one (`c_priest_e3m1`) is the same mesh with 320
frames, and is the priest's model. The seagull is e4's (`e4/d4_gull`): the global one is too few vertexes for its wings
to come apart from its body.

**The worst ones**, and why:

- **Deforming parts.** A rigid bone can't follow what stretches: the Cryotech's `shinya` (its blast, 34 to 100 across),
  the Fletcher's bowstring (50), the Harpy's wing membrane, the Griffon's (61) and the dragon's wings (3.2 on average
  over 527 across, 54 at worst), the Froginator's tongue (36). Joint scale (IQM has it) would.
- **Hidden parts.** Tatsuo's few vertexes collapsed to a point at rest and shown in one frame (49); Daikatana hid
  things so. A joint scaled to nothing would.
- **Deaths.** The skeleton falls apart (42), the Lycanthir (52) and Wyndrax (43) die in ways no limb moves.
- **Small heads.** The Centurion, the Harpy, the thief, the lab monkey, the Lycanthir and Gharroth keep fewer than 15
  vertexes on `Head`; their heads move with the neck or the chest. Toshiro lies in his coffin (`lying`) and his head is
  on `Loneck`.
- **Dead knees.** A low-poly leg is rings of vertexes at the hip, the knee and the ankle, so the shin has none of its
  own: the cyclops, the lab worker, the fat and the skinny workers, the priest, the SEAL girl and torture1 have a
  `Lloleg` or `Rloleg` with fewer than four vertexes. It moves with the thigh, the ankle bone carries the shin and the
  foot, and the joints' local translations swing a few units as they walk (bones stretch). The skinned mesh is still
  Daikatana's (the fat worker's walk, skinned from its IQM as the renderer does, is 0.24 units off on average, Hiro's
  0.23), but the skeleton doesn't bend where the legs do, which the walk IK and retargeting need. Turning each bone
  about its joint wherever its parent carries it (so bones keep their length) made the fit 1.5 to 5 units off, as the
  joints are only roughly placed: solving the joints and the bones' turns together (a constrained SSDR) is what's
  needed.
- Some hardpoints land on surprising bones (Kage's `sword1` on a thigh, the chain gang's muzzle on a thigh): the bone
  whose motion carries the triangle best, which is where Daikatana's frames have it.

**Not rigged**, and why:

| Model | Why |
| --- | --- |
| e3 `m_lybits1`…`10` | the Lycanthir's gibs: one rigid piece and one frame each, debris for physics |
| e1 `m_gatmid`, `m_gattop`, `m_tatakmid`, `m_tataktop` | turret parts Daikatana turns in code; the moving part of each turret is rigged (`rockgat`, `trackattack`, `lasergat`). One model of a whole turret, a joint a part (base, yaw, pitch), needs the parts joined first: a turret tool |
| e4 `m_chopper` | a helicopter's rotor (2 units thick), a prop |
| global `m_hiro2`, `m_ashtest` | tests: Hiro's hardpoints, a copy of Mikiko's mesh |
| global `m_croco` | an older Crox; e1's is the monster's |
| global `m_box`, `m_box2`, `m_cyl`, `m_sphere`, `m_jtree1` | test shapes and a tree |
| `models/cinematic/c_*` of Hiro, Mikiko, Superfly, Kage, the Mishima guard, the ferryman (`c_char`), Gharroth (`c_ghar`, `c_pghar`), Mikiko as Kage's | motion only: `tools/rig/retarget.py` moves it onto the rigged model |
| `monster_firefly`, `monster_wisp` | sprites (`.sp2`), not meshes |

Characters only the cinematics have (Casseti, Gusagi, Usagi, Inshiro, the ninja, Osaka, Tatsuo, Toshiro) are rigged
from their richest cinematic model, the one with the most frames; their other maps' models are motion for
`retarget.py` as Hiro's are.

## Limits and what's next

- **More bones.** Hands and feet are one bone each, and there are no fingers, toes, hair or cloth. The monsters get
  extra bones where the error stays high (above); the players don't yet, to keep their joints as they are.
- **Rest orientations.** The joints rest along their bones, as Half-Life's and Doom 3's do: x down the bone, z as near up as
  it can be. So the hitboxes, fitted in each joint's space, hug the limbs, and they are oriented boxes that turn with the
  joints. Retargeting Doom 3 animations still needs its exact axis convention per joint, a fixed rotation a joint, worked
  out once.
- **Animation blending.** Done, after Doom 3's `idAnimator`/`idAnimBlend`: animations play on channels (legs, torso
  from `Waist`, head from `Head`), each over the ones before it, and cross-fade over `blend_time`. The game and the cgame
  blend the same joints the same way (so hitboxes follow what's drawn), and the renderer skins the IQM from the joint
  matrices the cgame hands it (`trap_R_BlendSkeleton`, `trap_R_AddSkeletonToScene`). Try
  `spawncharacter model_hiro walk; characteranim all torso atak`. Eyes and syncing a channel's timing to another's are
  still Doom 3's alone.
- **Players.** The model defs map Quake 3's player animations (pmove's) to Daikatana's (`player_anim`, from
  `PLAYER_ANIMS` in `autorig.py`), so `model hiro` (the default) or `model mikiko` plays them as players, with hitboxes;
  `addbot Hiro` and `addbot Mikiko` (`scripts/dk.bot`) as bots. The weapon goes on `WEAPON_ATTACHER`, the gun
  hardpoint. Daikatana's hardpoints are points (its renderer's `R_GetModelHardpoint` gives a position), so the weapon
  sits at the hand turned as the torso aims, not as the hand is. The held weapon is the `a_*` model's frame 4, as
  Daikatana draws it (`cl_ents.cpp`): grip at the origin, along x (the weapon def's `model_world_frame`). The
  weapon picks the player animations by its type, as Daikatana's `CLIENT_SelectAnimationPerWeaponType` does: the
  weapon def's `player_anim_suffix` (`b` for the rifles and shoulder weapons) plays `atakb`, `runb`… where the
  character has them, the glove's plain `atak` the punch.
- **Animation speed.** The IQM plays the animations at 20 frames a second, as Daikatana plays its characters'
  (`FRAMETIME_FPS20`: `client_init.cpp`, `bot.cpp`). They're paced like people: Hiro's run covers about 100 units a
  second and his walk 36 (he's 54 tall, so a unit is about 3.3 cm), while the player runs at 320 as in Daikatana and
  Quake, whose feet slid too. So the characters run at 130 (`character_base`'s `run_speed`, near their own runs:
  at 170 the legs raced) and walk at 35% of it, and the rigger measures each move animation's speed over the ground
  (`anim_speed`, from how far each sole reaches forward and back a cycle): the legs play that much faster or slower,
  Hiro's run at 1.13×, Mikiko's and Superfly's at about 0.9×.
- **Swimming.** `swim` is a breaststroke lying down: the hands sweep out and back (frames 0–8, the pull) and come
  forward again. The rigger writes where the swimming body's middle is (`swim_center`); the game puts it in the
  middle of the player's box, lies the body along the stroke and times the animation by pmove's stroke. Daikatana
  has nothing for wading or shallow water: wading walks.
- **Ladders.** `ladderup` and `ladderdn` are the climbing (`LEGS_CLIMB`, `LEGS_CLIMBDOWN`). They climb in place; the
  rigger measures how far a cycle climbs (the body rises as fast as the holding hands and feet go down: Hiro 26,
  e1m1a's rungs are 12 apart) and how far ahead the hands hold, `ladder_climb` and `ladder_reach`. Daikatana has no
  animations for taking hold of a ladder or letting go.
- **The player's box.** The rigger measures each character's collision box, Doom 3's `mins`/`maxs`: the idle pose's
  legs, torso and head (the arms are the hitboxes' business), square about the origin as the box doesn't turn;
  `crouch_height` from the crouched idle and `eye_height`/`crouch_eye_height` a little under the top. Pmove sizes a
  player by the model the server gave it (`BG_PlayerBox`), so the client predicts the same box whatever it draws.
  Hiro comes out 32 wide like Daikatana's player, Superfly 38. The bots' AAS is still the standard 30-wide world.
- **Sounds and footsteps.** The rigger also writes each character's voice (Daikatana's, `sound/char_<name>.sndshd`
  sound shaders named by the def's `snd_*` keys) and footstep frames: where each sole (the ankle bone's lowest vertex)
  comes down in the run
  animations (full volume) and the walk ones (0.4; Daikatana and Quake 3 were silent walking). The defs inherit
  `character_base` (`def/dk_characters.def`), whose `snd_footstep_<type>` name Daikatana's footstep sounds per surface;
  the converted maps keep Daikatana's surface types (wood, metal, stone, ice…) as Doom 3's in their surface flags.
- **Feet on the floor.** Doom 3's walk IK plants the feet on stairs and slopes (`character_base`'s `ik_*` keys, the
  rig's Doom 3 joint names; the ankle stands in for the missing ball joint). Unlike Doom 3, a foot moves at most a
  step (18), a foot over no floor stays as animated, a target out of reach is pulled in rather than folding the leg,
  the knee bends only forward, and the bones turn without twisting about their length (`bg_ik.c`). The rigger sets each character's
  `ik_minWaistAnkleDist` (Doom 3's) to 85% of its standing waist-to-ankle height: on a slope the box stands on its
  uphill edge, and a waist dropping all the way to the feet below folds the other leg into a squat.
- **Ragdolls.** A dead player goes limp, with Doom 3's articulated figures (`idPhysics_AF`, ported to C in mint-arena's
  `bg_af.c`, its LCP solver in `bg_lcp.c`). The rigger writes each character's figure in Doom 3's `.af` syntax,
  `af/char_<name>.af`, and the model def names it (`ragdoll`). The figure is made in the IQM's bind pose. It has boxes
  for the waist, the chest and the head, and bones for the upper arms, the forearms with the hands, the thighs and
  the shins with the feet. Each limb is sized from its own vertexes. The waist, the neck, the shoulders and the hips
  are universal joints with cone limits; the elbows and the knees are hinges that bend one way. As in Doom 3's
  multiplayer, each client simulates the dead players itself (`cg_ragdoll.c`). The ragdoll starts from the pose
  and velocity the player had, collides with the world and the movers, and is passed to the corpse the body queue
  leaves behind. `cg_ragdoll 0` turns it off. `cg_drawRagdolls 1` draws the bodies, the joints and the contacts.
  `damage <amount>` (a cheat) hurts you without gibbing you, to test it. The server runs figures too: a `misc_character` that dies goes limp on the server
  (`g_ragdoll.c`, Doom 3's `idActor::StartRagdoll`), sent to the clients in its entity snapshot
  (`bg_snapshot.c`), and hits push it (`g_ragdollPush`). `damage <amount> <entity | aim>` kills one, and
  `spawncharacter` prints its number. The bodies collide with each other too (Doom 3's self collision), except those a
  joint holds together: each body traces against the others' trace models. A body that hits something hard thuds
  (`snd_bounce`, `dk_bodyhit`); the server's ragdolls send it as an entity event. Not done yet: a client-side
  ragdoll isn't pushed by shots.
- **Dead bodies.** Daikatana's dead bodies (`deadguy`, `models/e1/m_dead`) are one mesh in 10 lying poses, its
  frames. `autorig.py --lying` rigs such a body stood up (head up, facing +x, so the template fits). It turns
  everything it writes back to lying: the mesh, the root joints, and the ragdoll's points, directions and boxes.
  The poses differ enough for the bones to be fitted from them. `./dk rig` rigs the bodies of `RIG_BODIES`
  (`dead`). The converter makes each `deadguy` deco a `misc_character` of `model_dead` with `ragdoll 1`.
  The deco's `frame` is the pose the character starts in, and its `scale` is the `modelscale`. The
  character goes limp as soon as it spawns, a server ragdoll, and settles on what's under it: e1m1a's bodies on
  their coffins. Articulated figures take the model's scale (`BG_AFLoad`): the bodies and joints are that much
  bigger, and the pose goes back to the model's size for the renderer, which draws it scaled.
- **Licensing.** Doom 3's retail animations and meshes can't be shipped. Matching its skeleton is for tooling and for
  animations of our own or freely licensed ones.
