# Renderer plan: dynamic lights, fog, material features

Status: agreed scope, not started (2026-10-22).

## Scope

We improve Spearmint's renderergl2 (rend2, the renderer `./dk` runs) in three places, porting from Doom 3 or The Dark Mod where they do it better:

1. dynamic lights;
2. fog;
3. the material features we actually need.

Everything else stays as it is: Quake 3 BSP maps with their lightmaps, the shader system, models, 2D. The engine, renderer and game stay C; what we take from Doom 3 or TDM (C++) is translated, using mint-arena's C idLib ports (`q_extramath`, `polylib`, `q_containers`...) where they help.

Out of scope for now (looked at, set aside): Doom 3 maps and dmap, `.proc` worlds, replacing shaders with materials, the light grid bake, the light gem.

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

## Order

Each step is built, tested with `./dk`, committed and pushed before the next.

1. Fog per pixel (small, and fixes visible smearing now).
2. Volume fog and the Daikatana conversion.
3. Dynamic lights per pixel everywhere, and the 32-light limit.
4. Light shaders, expressions and tables; spot lights; the cambot's lamp.
5. The shadow-map atlas with PCSS.

## Reference

- `spearmint/code/renderergl2`: `tr_shade.c` (`ForwardDlight`, the fog pass), `tr_shader.c`, `tr_glsl.c`, `tr_fbo.c`, `glsl/`.
- `darkmod_src/renderer`: `backend/stages/ShadowMapStage.cpp`, `frontend/tr_light.cpp` (atlas pages), `glprogs/tdm_shadowmaps.glsl`, `glprogs/stages/light_passes/fog_light.frag.glsl`, `resources/Material.cpp` (light shaders, expressions).
- `../dhewm3-debugger/neo/renderer`: Doom 3's light and fog model, for comparison.
- Daikatana (`atsb/daikatana-restoration-project`): `base/ref_gl/gl_rmain.cpp` (global fog), `gl_fogsurf.cpp` (volume fog), `dlls/world/world.cpp` (worldspawn fog keys).
