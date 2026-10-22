# Renderer plan: dynamic lights, fog, material features

Status: agreed scope, not started (2026-10-22).

## Scope

We improve Spearmint's renderergl2 (rend2, the renderer `./dk` runs) in three places, porting from Doom 3 or The Dark Mod where they do it better:

1. dynamic lights;
2. fog;
3. the material features we actually need;
4. Doom 3's portal visibility (what `.proc` files give it), built from our own BSPs;
5. a light grid bake, since Daikatana's BSPs have no light grid.

Everything else stays as it is: Quake 3 BSP maps with their lightmaps, the shader system, models, 2D. The engine, renderer and game stay C; what we take from Doom 3 or TDM (C++) is translated, using mint-arena's C idLib ports (`q_extramath`, `polylib`, `q_containers`...) where they help.

Out of scope for now (looked at, set aside): Doom 3 maps and dmap, loading `.proc` files, replacing shaders with materials, the light gem.

## 1. Dynamic lights

**Today in rend2:**
- dlights are points (origin, radius, colour, intensity) at most 32 a frame, because surfaces mark them in 32-bit masks (`MAX_DLIGHTS`, `renderercommon/tr_types.h:36`; `dlightBits` in `tr_local.h`);
- `r_dlightMode 1` lights them per pixel with normal and specular maps (`ForwardDlight`, `tr_shade.c:886`), but only on single-stage `lightall` surfaces;
- point-light shadows (`r_dlightMode 2`, cube maps) are broken: a cube texture is bound to a 2D sampler (`tr_shade.c:1087`);
- the only working shadow maps are the sun's cascades and entity pshadows.

**Work, in order:**
1. **Per-pixel everywhere:** dlights lit per pixel on every opaque surface, not only single-stage `lightall` ones. Multi-stage shaders get the light added after their base stages, as Doom 3's interaction pass does after the depth pass. `r_dlightMode 1` becomes the default.
2. **More lights:** the 32 limit goes. Surfaces keep a per-view light list (indices) instead of a bit mask. The cap becomes a cvar budget (e.g. 128), sorted by screen size and intensity.
3. **Light shapes, from Doom 3:**
   - Point lights with a falloff image.
   - Projected (spot) lights: origin, target/right/up, a projection image, start and end.
   - The refexport gains `AddLightToSceneEx(refLight_t *)`. The old calls stay and make point lights.
   - The cambot's lamp becomes a spot light.
4. **Shadows, from TDM:**
   - a shadow-map atlas (one depth texture; six faces a point light, one a spot light; sizes from screen size);
   - one pass for all shadowed lights;
   - alpha-tested casters;
   - PCSS soft shadows.

   Ported from TDM's `ShadowMapStage`, the atlas page assignment in `frontend/tr_light.cpp`, and `glprogs/tdm_shadowmaps.glsl`, onto rend2's FBO and GLSL code. A light can say `noShadows`. This replaces the broken cube-map mode.
5. **Map lights:**
   - bsp-sekai passes Daikatana's `light` entities through (the original BSPs keep them: e1m1a about 82, e1m1b 216) with a key marking them as baked. They stay in the lightmaps and aren't drawn dynamically.
   - A map can add dynamic ones by its `.ent` overrides (e.g. a flickering lamp that should cast moving shadows).

**Done when:**
- e1m1a's cambots light the swamp with shadowed spot lamps;
- muzzle flashes and effects light everything they reach;
- 50+ dynamic lights on screen keep the frame time noted on this Mac;
- `./dk test` passes.

## 2. Fog

**Today:**
- **Daikatana has two fogs:**
  - global linear fog from the worldspawn (`fog_start`, `fog_end`, `fog_color`, `fog_value`; `gl_rmain.cpp`);
  - volume fog brushes (`SURF_FOGPLANE`): `gl_fogsurf.cpp` computes each vertex's density by tracing through the brush's hull, from inside or outside.
- **Ours:**
  - The global fog reaches rend2 as Spearmint's global fog (the skybox shader's `fogvars`, `CG_FogView`).
  - The volumes are dropped (`VIEWFOGS 0`, `bsp-sekai/code/bsp_dk.c`). The swamp's fog is missing.
- **rend2 computes all fog per vertex** (`CalcFog` in `fogpass_vp.glsl` and `generic_vp.glsl`), which smears on the big swamp polygons. Quake 3 fog volumes also want a single visible fog plane.

**Work:**
1. **Per pixel:** fog computed in the fragment shaders (the same maths as `CalcFog`, moved), for global fog and Quake 3 fog volumes alike.
2. **Volume fog like Doom 3's fog lights:** a fog volume is a convex brush (or box) with colour and distance.
   - Its pass draws the surfaces inside it and its back faces, with TDM's analytic fog-entry maths (`glprogs/stages/light_passes/fog_light.frag.glsl`).
   - That handles the camera inside or outside, and any number of planes, which is what Daikatana's hull fog needs.
   - It's new code beside the Quake 3 fog pass.
3. **Conversion:** bsp-sekai writes Daikatana's fog brushes as these fog volumes (their planes, `fog_color`, distance from the texinfo value) in place of `VIEWFOGS 0`.
4. **Global fog:** linear, with a separate sky distance (`fog_skyend`), checked against Daikatana's.

**Done when:** e1m1a's swamp fog, from inside and outside, is compared side by side with Daikatana's screenshots.

## 3. Material features we need

Added to rend2's shader system (`tr_shader.c`) as keywords, taken from Doom 3's material syntax so they read the same. Only what our content and the work above use:

- **Light shaders** (for part 1): a light's projection and falloff images (`lightFalloffImage`, the projection `map`), coloured and animated by its stages. This lets lights flicker and pulse, Daikatana's light styles included.
- **Expressions and tables** (Doom 3's `table` decls and stage expressions: `time`, `parm0..`, sin and tables): for flicker, pulse and blink on lights and surfaces. Quake 3 waves can't express these, and our scripts need to drive them through entity parms.
- **Fog volume shaders** (for part 2): colour and distance for the new volume fog.
- **`bumpmap`/`specularmap`/`diffusemap` stage names:** alias rend2's `normalMap`/`specularMap`, so assets from Doom 3 and TDM read as written.

Anything else waits until something needs it.

## 4. Portal visibility on our BSPs

**What it is:** Doom 3's `.proc` world gives its renderer areas joined by portal polygons.
- The view and each light flow through the portals, clipped to a shrinking frustum (`RenderWorld_portals.cpp`: `FlowViewThroughPortals`, `FloodViewThroughArea_r`, `FlowLightThroughPortals`).
- Entities and lights are culled per area; doors close portals.
- This is what keeps many dynamic lights cheap: a light only touches the surfaces its flow reaches, and only those cast its shadows.

**What we have:**
- Quake 3 BSPs carry PVS clusters, areas and area portals (doors already close them, `trap_AdjustAreaPortalState`), but no portal polygons.
- Daikatana's BSPs are the same (Quake 2 family).

**Work:**
1. **Portals from the BSP tree:** bsp-sekai cuts the BSP tree into leaf portals, as qbsp's `MakeTreePortals` does (the node planes clipped to each other), and merges leaves into clusters' convex areas. They're written beside the map as `maps/<map>.portals`: areas, portal windings, which area each leaf is in. `idlib/polylib.c` has the windings.
2. **Portal flow:** Doom 3's portal flow translated to C into rend2, run from the camera's leaf. It replaces the PVS test where the portals file exists, and falls back to the PVS where it doesn't. Area portals closed by doors close the matching portals.
3. **Per-light flow:** each dynamic light floods from its leaf through open portals within its radius or frustum. That gives the surfaces it lights and the casters for its shadow map (Doom 3's `tr_light`/`tr_lightrun`), cached until the light moves or a door changes. Part 1's lights and shadow atlas use these lists.

**Done when:**
- surfaces and entities drawn on e1m1b drop against the PVS (`r_speeds`), with no missing geometry seen in `./dk test` shots;
- many dynamic lights in separate rooms cost little.

## 5. Light grid bake

**Why:** models (characters, monsters, items) are lit from the BSP's light grid. Daikatana's BSPs have none; Daikatana lit a model from the lightmap of the floor under it.
- bsp-sekai makes one the same way (`InitLightGrid`, `bsp_dk.c:4394`): a cell every 128 units, coloured by the lightmap of the floor straight below (`RecursiveLightPoint`).
- There is no light direction (the directed part is left 0), so models look flat, and the 128-unit cells are coarse.

**The bake, after RBDOOM-3-BFG's**, in the engine with rend2, so it sees exactly what the player sees: Daikatana's lightmaps (its baked bounce included), the sky and emissive surfaces.
1. **Grid:** the map's bounds in steps of 64 (`gridsize` in the worldspawn overrides it). Points in solid are skipped, as rend2 already skips empty cells when lighting an entity.
2. **Capture:** at each point, a small cubemap (e.g. 6×32²) of the world with lightmaps only: no entities, dynamic lights or fog. Rend2's cubemap code (`R_RenderCubemapSide`) does the rendering.
3. **Fold:** each cubemap folded into L1 spherical harmonics (RBDOOM's irradiance code). From that come Quake 3's grid cell (ambient colour, directed colour, direction), so rend2's entity lighting uses it unchanged. The SH are kept too, for per-pixel model lighting later.
4. **Output:** `maps/<map>.lightgrid`, which rend2 loads in place of the BSP's grid lump when it exists. `bakeLightGrid` is a console command; `./dk convert` runs it headless after converting.

**As built** (spearmint `tr_lightgrid.c`, `./dk bakegrids`):
- **Rooms, after RBDOOM's grid an area.** Our BSPs' areas are too few and their clusters too many, so the rooms are found from the space itself: a watershed over 32-unit voxels of the open space. Each voxel's depth is its distance from the walls, and the voxels flood in from the deepest. Each room fills from its middle, and where floods meet at a narrow place (a doorway) is a border; floods meeting nearly as deep as the shallower (`r_roomSaddle`, 0.7) are one room. e1m1a has 25 rooms, e1m1b 40.
- **One lattice, every 64 units**, each open point labelled with its room. A model takes the light of the room of the nearest point it sees, from that room's points only, so no light comes through a wall.
- **Capture:** at each point a cube of 6×16² of the lightmaps alone (`r_lightmap 1`, no textures, entities, flow or lit fog), into a small float FBO, 4 points a pass.
- **Fold:** the ambient is the cube's average. The light comes the other way from where it lands, so a lit floor below is light from above, and walls lit all round cancel out. Then ambient + directed·max(0, n·d), with the same average and as much coming that way, in Quake 3's 8 bytes a point.
- **Output:** `maps/<map>.lightgrid` (the rooms and the light), loaded with the map; it comes before the BSP's grid.
- **Bake time:** e1m1a 6032 points in 20 s; e1m1b 21226 points in 79 s.

**Done when:**
- monsters and the player's view model on e1m1a and e1m1b are lit with a direction (bright on the side facing a lamp), compared with Daikatana's screenshots;
- the bake time per map is noted.

## 6. Lightmaps baked again

**Why:** Daikatana's lightmaps are a luxel every 16 units, and its light compiler is gone. Its BSPs still have what it lit from: the light entities (`light`, `_color`, and its own `cap`) and the faces' surface lights (SURF_LIGHT with a value, the sky's among them).

**As built** (`./dk lightmaps`, `tools/maps/bsp_lights.py`, q3map2 from NetRadiant built by `./dk build netradiant`):
- **Split:** the lightmaps keep the light that bounces, and the surface lights' and sky's; the light entities' direct light is drawn by the game as dynamic lights (worldspawn `_bounceLightmaps`). q3map2 can't leave a light's direct light out, so the map is baked twice, the same way: all of it, then the light entities' direct light alone (no bounce, no surface lights, same shaders so the lightmaps are laid out the same, `-nocollapse`), and the one less the other.
- **Dynamic lights:** each light entity a linear light (`trap_R_AddLinearLightToScene`, `REF_LINEAR_DLIGHT`): full until `cap` units from its edge, then linearly none at its `light`, qrad's `min( cap, light - distance )`, as bright as cap / 255 × `cg_staticLightScale`, on surfaces and models. Lights without a cap: 55.
- **Bake:** point lights linear, colour unnormalized (q3map2's `0.9375 × light − distance`), cap as a fade from cap × 1.25; surface lights on bake shaders of their own (`<shader>__lb…`, `q3map_surfaceLight`), the sky's as `q3map_skyLight`; see-through faces (from the generated shaders) cast no shadow, alpha-tested ones only where solid. The game's shaders and entities go back after.
- **Searched** on e1m1b's 8 spawn views at Daikatana's 16 units, against its lightmaps, by 32×20 luminance grids (mean |log ratio|): sky scale 0.25–2, bounce scale 1–3, light scale 0.4–1. Best: sky 0.5, `-bouncescale 2`, `cg_staticLightScale 0.6`: error 0.094 (about 10% a cell), brightness 1.02, views 0.04–0.13. More sky brightens the open views too much (0.36 at sky 2); more light scale the spots with lights close together.
- **Default:** those, at 8-unit luxels into 1024² external lightmaps (`maps/<map>/lm_NNNN.tga`, which rend2 loads by itself); `LIGHT_OPTIONS` for others (16 units as Daikatana: `-bounce 2 -bouncescale 2 -samples 2 -filter`).
- The light grids (`./dk bakegrids`) are baked after.

## Order

Each step is built, tested with `./dk`, committed and pushed before the next.

1. Fog per pixel (small, and fixes visible smearing now). Done: spearmint 654ab65b.
2. Volume fog and the Daikatana conversion. Done: `fogLight` fog shaders drawn per pixel through their hull (spearmint e6511988, `tr_fogvolume.c`, documented in `opengl2-readme.md`); bsp-sekai 72c2753 marks Daikatana's fogs.
3. Dynamic lights per pixel everywhere, and the 32-light limit. Done: spearmint (per-pixel by default, 64 lit of up to 256), mint-arena `testlight`.
4. Light shaders, expressions and tables; spot lights; the cambot's lamp.
5. Portals from the BSP and portal flow (view, then lights). View flow done: spearmint, `tr_portals.c` (portals cut at load in the renderer, not bsp-sekai; flow between clusters with screen rectangles). The lights' flow comes with the shadow maps.
6. The shadow-map atlas with PCSS, fed by the lights' flow. Done: spearmint `tr_dlightshadow.c`; the portal flow culls each face's casters. Lit fog done: dlights scattered in fog lights, two of them with their shadows.
7. The light grid bake. Done: spearmint `tr_lightgrid.c`, a grid a room; `./dk bakegrids`.
8. Lightmaps baked again with q3map2 from Daikatana's lights. Done: `./dk lightmaps`.

## Reference

- `spearmint/code/renderergl2`: `tr_shade.c` (`ForwardDlight`, the fog pass), `tr_shader.c`, `tr_glsl.c`, `tr_fbo.c`, `glsl/`.
- `darkmod_src/renderer`: `frontend/RenderWorld_portals.cpp` (portal flow), `frontend/tr_lightrun.cpp`, `backend/stages/ShadowMapStage.cpp`, `frontend/tr_light.cpp` (atlas pages), `glprogs/tdm_shadowmaps.glsl`, `glprogs/stages/light_passes/fog_light.frag.glsl`, `resources/Material.cpp` (light shaders, expressions).
- `../dhewm3-debugger/neo/renderer`: Doom 3's light and fog model, for comparison.
- Daikatana (`atsb/daikatana-restoration-project`): `base/ref_gl/gl_rmain.cpp` (global fog), `gl_fogsurf.cpp` (volume fog), `dlls/world/world.cpp` (worldspawn fog keys).
