# Skeletal characters, rigged automatically

Daikatana's characters are vertex-animated: each `.dkm` (converted to `.md3`) stores every vertex on every frame.
Hitboxes and sword combat need skeletons. `tools/rig/autorig.py` recovers a skeleton and skinning weights from those
frames, so nobody has to rig in Blender, and it keeps Daikatana's own animations.

```
./dk rig                 # hiro and mikiko, into dkres/models/rigged/, their model defs into def/
./dk rig hiro            # one
```

Each character takes about 20 seconds in plain Python. numpy isn't needed. It would only matter for a heavier solve or
for converting every character in a batch.

## How it works

This is a small form of skinning decomposition, after Le & Deng's SSDR (2012/2014), which Electronic Arts' Dem Bones
implements.

1. **Skeleton.** The joints are Doom 3's: its human rig's names and hierarchy (`origin`, `Body`, `Hips`, `Lupleg`,
   `Lloleg`, `Lankle_r`, `Waist`, `Chest`, `Loneck`, `Head`, `Luparm`, `Lloarm`, `Lhand`, and the right side), so tools and
   animations made for Doom 3 skeletons line up. Where the joints go is measured from the mesh, because Daikatana's
   characters aren't built like Doom 3's:
   - the neck, where the body narrows into the head
   - the crotch, where mesh first appears between the legs
   - the shoulders, from the body's width there
   - the hands, at the arms' outermost points (the right one at the gun hardpoint)
2. **Segments.** Each vertex starts on the nearest bone. Each bone's rigid motion is then fitted to every frame (Horn's
   quaternion method), and each vertex moves to the neighbouring bone whose motion carries it best. A term for nearness
   keeps parts that move together (chest and neck) from trading vertices at random. Repeat until stable, usually 3–4
   rounds.
3. **Joints.** Each joint goes to the point that moves least between the parent's and the child's segments over the
   frames, by least squares.
4. **Weights.** Each vertex blends its own bone with a neighbouring one where that fits the frames better (two weights a
   vertex).
5. **Rest orientations.** Each joint rests along its bone (x toward the child), so hitboxes fitted in its space hug the
   limb.
6. **Hardpoints.** Daikatana's `hp_gun` and `ctf_flag` triangles become rigid attachment joints, `WEAPON_ATTACHER` and
   `FLAG_ATTACHER`, as Doom 3 has `*_ATTACHER` joints.
7. **Output.**
   - An IQM: the first frame as the rest pose, every frame as a pose, and the frame names (`run01`…) giving the
     animations (`amb`, `walk`, `run`, `atak`, `die`…), the idle and moving ones looping.
   - A model def with a hitbox per bone: the box around the bone's vertices in the joint's space, zoned
     `head` (×2), `torso`, `arms` and `legs` (×0.75).

## Results

| Character | Vertexes | Frames | Animations | Average error | Worst vertex | Height |
| --- | --- | --- | --- | --- | --- | --- |
| Hiro | 726 | 1394 | 82 | 0.35 | 28 | 54 |
| Mikiko | 637 | 1259 | 78 | 0.42 | 31 | 58 |

The error is how far each skinned vertex lands from Daikatana's, over all frames. In game the rigged and original models
look the same frame for frame (`cg_drawSkeleton 1` shows the joints, 2 without the mesh; `def/char_hiro_md3.def` plays
the original to compare:
`spawncharacter model_hiro run -4 30; spawncharacter model_hiro_md3 run -4 -30`).

A few vertexes go far off (28–31 units) on a few frames. They're parts that move in ways no single limb does, such as
hair, cloth, or the body during the death animations.

## Limits and what's next

- **More bones.** Hands and feet are one bone each, and there are no fingers, toes, hair or cloth. More bones, or a
  joint placed automatically wherever the error stays high, would bring down the worst vertexes.
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
  sits at the hand turned as the torso aims, not as the hand is. Daikatana has no held weapon models for players,
  though: the `a_*` models are pickups lying flat around their middle, so they sit oddly in the hand. Its only held
  ones are the soldiers' `hw_pistol` and `hw_shotgun` (grip at the origin, barrel along x) and the sword
  `ws_daikatana`.
- **Sounds and footsteps.** The rigger also writes each character's voice (Daikatana's, `sound/char_<name>.sndshd`
  sound shaders named by the def's `snd_*` keys) and footstep frames: where each ankle comes down in the run
  animations (full volume) and the walk ones (0.4; Daikatana and Quake 3 were silent walking). The defs inherit
  `character_base` (`def/dk_characters.def`), whose `snd_footstep_<type>` name Daikatana's footstep sounds per surface;
  the converted maps keep Daikatana's surface types (wood, metal, stone, ice…) as Doom 3's in their surface flags.
- **Feet on the floor.** Doom 3's walk IK plants the feet on stairs and slopes (`character_base`'s `ik_*` keys, the
  rig's Doom 3 joint names; the ankle stands in for the missing ball joint).
- **Licensing.** Doom 3's retail animations and meshes can't be shipped. Matching its skeleton is for tooling and for
  animations of our own or freely licensed ones.
