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
   - the crotch, going down, where a gap first opens between the legs: no triangle crosses the middle there
     (going up from the feet stops where the knees touch, and a low-poly trunk's big triangles span the middle
     without a vertex there)
   - the shoulders, from the body's width there
   - the hands, at the arms' outermost points (the right one at the gun hardpoint)
2. **Segments.** Each vertex starts on the nearest bone. Each bone's rigid motion is then fitted to every frame (Horn's
   quaternion method), and each vertex moves to the neighbouring bone whose motion carries it best. A term for nearness
   keeps parts that move together (chest and neck) from trading vertices at random. A vertex its bone carries badly
   (over 4 units off on average) tries every bone: a hip vertex the hanging hand took at first can't reach the leg
   through neighbours. Repeat until stable, usually 3–4 rounds.
3. **Joints.** Each joint goes to the point that moves least between the parent's and the child's segments over the
   frames, by least squares, but only along the directions the motion pins down. A hinge (knee, elbow) agrees all
   along its axis, and there the template's place stays. A joint moves at most a tenth of the height, and the legs'
   joints keep the template's heights (the knee halfway from crotch to floor): the walk IK bends the leg at them.
4. **Weights.** Each vertex blends its own bone with a neighbouring one where that fits the frames better (two weights a
   vertex), never one leg with the other: the walk IK moves them apart.
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
| Hiro | 726 | 1394 | 82 | 0.29 | 6 | 54 |
| Mikiko | 637 | 1259 | 78 | 0.27 | 15 | 58 |
| Superfly | 709 | 1263 | 77 | 0.31 | 7 | 54 |

The error is how far each skinned vertex lands from Daikatana's, over all frames. In game the rigged and original models
look the same frame for frame (`cg_drawSkeleton 1` shows the joints, 2 without the mesh; `def/char_hiro_md3.def` plays
the original to compare:
`spawncharacter model_hiro run -4 30; spawncharacter model_hiro_md3 run -4 -30`).

A few vertexes go off (6–15 units) on a few frames: parts that move in ways no single limb does, such as hair, cloth,
or the neck during the death animations. `RIG_WORST=1 ./dk rig` lists the worst, with the animation and the bones.

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
  sits at the hand turned as the torso aims, not as the hand is. The held weapon is the `a_*` model's frame 4, as
  Daikatana draws it (`cl_ents.cpp`): grip at the origin, along x (the weapon def's `model_world_frame`). The
  weapon picks the player animations by its type, as Daikatana's `CLIENT_SelectAnimationPerWeaponType` does: the
  weapon def's `player_anim_suffix` (`b` for the rifles and shoulder weapons) plays `atakb`, `runb`… where the
  character has them, the glove's plain `atak` the punch.
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
  the knee bends only forward, and the bones turn without twisting about their length (`bg_ik.c`).
- **Licensing.** Doom 3's retail animations and meshes can't be shipped. Matching its skeleton is for tooling and for
  animations of our own or freely licensed ones.
