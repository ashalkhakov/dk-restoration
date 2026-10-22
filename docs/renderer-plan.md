# Renderer plan: Doom 3 lighting in Spearmint's renderer

Status: agreed direction, not started (2026-10-22).

## Why

- **Light has to be dynamic.** Cambots carry lamps, and parts of the game should be sneaked through. Shadows from moving lights matter, and so does how lit the player is.
- **Daikatana's lightmaps can't stay.** The compiler that made them is gone, and they are too coarse for today.
- **Its fog is half missing.**
  - The global distance fog works: `fog_start`, `fog_end`, `fog_color` and `fog_value` reach the game as Spearmint's global fog.
  - The volume fog brushes (`SURF_FOGPLANE`, drawn by `gl_fogsurf.cpp` from the brush's hull) are dropped by our converter (`VIEWFOGS 0` in `bsp-sekai/code/bsp_dk.c`). The swamp's fog is missing.
- **We keep moving to Doom 3's subsystems,** and the renderer and its materials are next.

## Constraints

- **The renderer is C,** like Spearmint and mint-arena. Doom 3 code comes in translated to C, as `cm2` (Doom 3's collision models) and mint-arena's `idlib/` (C ports of idLib) did.
- **Reuse as much of the current renderer as possible,** and keep an upgrade path from Quake 3 assets and shaders to the new materials and lighting. Quake 3 content keeps working.

## What we looked at

| Renderer | Shadows | Static light | Fog | GL | Notes |
|---|---|---|---|---|---|
| Spearmint renderergl2 (in use, `RENDERER=opengl2`) | Sun cascades; pshadows; dlight cube shadows broken (`r_dlightMode 2`) | Lightmaps, light grid | Q3 fog volumes, global fog; per vertex | GL 2/3, GLSL | C, ~52k lines. Per-pixel dlights with normal/specular maps, HDR, tonemap, SSAO, cubemaps. 32 point dlights at most, immediate-mode API |
| dhewm3 | Stencil volumes only | None, all per-pixel lights | Fog/blend lights, fixed function | GL 1.x + ARB programs | Nothing to take that TDM doesn't do better |
| The Dark Mod | **Shadow-map atlas (6 faces a light, sized by screen size), PCSS soft shadows**, stencil as well | None (ambient lights, SSAO) | **Fog lights in GLSL** with fog-entry math | **GL 3.3 core** | C++, ~93k lines, heavily coupled. Light gem, volumetric lights |
| RBDOOM-3-BFG | Shadow atlas, sun cascades | **Baked light grid + irradiance probes** | Doom 3's | NVRHI (DX12/Vulkan) | We take its light grid idea |

**Decision:** grow renderergl2 into the new renderer. It is already C, already has the GLSL/FBO backend, images, models, skeletons, 2D, fonts, sky, HDR, cascades and the Quake 3 shader system.

We bring in from The Dark Mod, translated to C:
- the `.proc` world and portal visibility;
- Doom 3's lighting model (projected and point lights with falloff images, interactions);
- the shadow-map atlas and PCSS (its GLSL kept);
- fog lights;
- the light gem and light query.

From RBDOOM-3-BFG we take the light grid bake. Translating TDM whole would mean ~35–40k lines of C++ to C and replacing most of what rend2 already does; this way it's roughly half that.

## Target

1. **One renderer, two kinds of world:**
   - Quake 3 BSPs render as today (lightmaps, light grid, Quake 3 fog): the compatibility path.
   - Doom 3 `.proc` worlds render with dynamic lights, shadow maps, the light grid and fog lights.
   - Entities and dynamic lights use the new lighting in both kinds of world, so Quake 3 maps can gain it too.
2. **World:** Daikatana BSP → Doom 3 `.map` (bsp-sekai) → dmap → `.proc` (areas, portals, surfaces) and `.cm` (collision; `cm2` already loads Doom 3 collision models).
3. **Materials as the superset of shaders:**
   - rend2's shader system learns Doom 3's material syntax (`.mtr`).
   - A Quake 3 `.shader` is parsed into the same internal material, so every Quake 3 shader keeps working with no conversion.
   - An upgrader writes `.mtr` files from shaders for authors who want to edit them as materials.
   - Daikatana's conversion writes materials directly.
4. **Lighting:**
   - Direct light comes from Doom 3 lights, shadow-mapped.
   - Fill and bounce light comes from a light grid with irradiance probes baked in the engine (RBDOOM-3-BFG's approach).
   - No lightmaps in `.proc` worlds.
5. **Fog:**
   - Daikatana's fog brushes become fog lights.
   - Its global fog keeps using rend2's global fog, done per pixel.
6. **Stealth:** TDM's light gem and CPU light query read both lights and grid.

## What is reused, what comes in

| Area | Kept from renderergl2 / renderercommon | New (from TDM or RBDOOM, in C) |
|---|---|---|
| Backend | GLSL program manager (`tr_glsl.c`), FBOs (`tr_fbo.c`), VAOs/VBOs (`tr_vbo.c`), state (`tr_backend.c`), HDR/tonemap, SSAO, `qgl` | Stages: shadow-map atlas, interaction, fog light, blend light, light grid ambient, light gem; TDM's GLSL adapted to rend2's uniform/permutation scheme |
| World | Q3 BSP loading (`tr_bsp.c`), PVS, lightmaps, light grid | `.proc` loading, areas and portals, portal flow visibility, door portal state (`RenderWorld*`) |
| Surfaces | Surface types, sorting (`tr_main.c`, `tr_surface.c`), deforms (`tr_shade_calc.c`), flares | Light/surface interactions and culling (`tr_light`, `Interaction`), shadow bounds |
| Lights | dlights (become point lights without shadows), sun cascades (become parallel lights) | Light defs: point and projected, falloff and projection images, `noShadows`, `bake`; light materials with expressions |
| Shaders / materials | `tr_shader.c` parser, stages, `normalMap`/`specularMap`, `_n`/`_s` suffixes, `.mtr` override files | Doom 3 material keywords and stage expressions (`Material.cpp`: registers, tables, conditions), `diffusemap`/`bumpmap`/`specularmap`, light and fog materials |
| Images | Loaders (tga, jpg, png, dds), mipmaps, compression (`tr_image*.c`) | Image programs (`heightmap`, `addnormals`, `makeIntensity`...), falloff images, shadow atlas |
| Models | md3, iqm, mdr, skeletons (`tr_model*.c`, `tr_skeleton`) | md5 later if wanted; decals and overlays |
| 2D, fonts, sky, cinematics | All kept | — |
| Interface | `refexport_t` 2D and immediate scene calls (Quake 3 content and mods keep working) | Retained world calls: entity and light defs, `.proc` loading, portal state |
| Math | `q_math.c`, mint-arena's `q_extramath.c`, `polylib.c`, `surface.c`, `q_containers.c` | Frustum, render matrices, whatever the translated code still needs |

## Phases

Each phase ends with something we can run and screenshot through `./dk`, and is committed and pushed.

### Phase 1: Doom 3 maps from Daikatana's (bsp-sekai, dk)

**Writer:** `bsp-sekai` gets a `.map` writer next to the Quake 3 BSP one (e.g. `-format d3map`), on mint-arena's `idlib/mapfile.c` (idMapFile in C).
- **Brushes:** from the brush and brush-side lumps (`bsp_dk.c` already reads them, at 4521), world and brush models alike.
- **Bevels:** the axial bevel planes qbsp added are among the brush sides, with no flag. Drop a side when its plane is axial, it carries no face of its own, and the brush stays the same without it (test by clipping). Hint, skip and clip sides become `textures/common/*` materials.
- **Texture alignment:** Daikatana's texinfo vectors become `brushDef3` texture matrices.
- **Entities:**
  - As written now: `.ent` overrides, gametype keys and Daikatana's classnames.
  - **Lights:** `light` entities, which the original BSPs keep (e1m1a about 82, e1m1b 216), become Doom 3 lights:
    - `light` → `light_radius`; `_color` → color; Daikatana's `cap` is noted;
    - a `bake` key (1: the light grid only; 0: dynamic) is guessed first: big, dim and uncapped lights become fill.
  - **Fog:** the fog brushes become fog light entities (their box, `fog_color`, density from the texinfo value).
  - **Sky and sun:** worldspawn `ambient`, sky and sun become a parallel light and the grid's sky term.

**dmap:** an offline tool, `tools/dmap`, from TDM's (`darkmod_src/tools/compilers/dmap`, ~12.7k lines).
- First as C++ on TDM's idLib, to unblock everything else; it ships with no game.
- Translated to C later if the tools must be C too.
- **During the move,** `./dk convert` keeps writing the Quake 3 BSP:
  - `bspc` builds the AAS (bot and monster navigation) from it;
  - the game keeps running on it until phase 3.

**Done when:**
- e1m1a, e1m1b and e1m1c dmap without leaks;
- the `.proc` area count is sane;
- `.cm` collision plays the same as the BSP's (`./dk test`).

### Phase 2: materials in the shader system (spearmint renderergl2, tools)

- **Parser:** `tr_shader.c` parses Doom 3 material syntax as well as Quake 3's, into one internal `shader_t` that grows Doom 3's parts:
  - expression registers and ops (add, sub, mul, div, mod, table, compare, and/or);
  - stage conditions;
  - `diffusemap`/`bumpmap`/`specularmap` stages;
  - light and fog material flags.

  Translated from TDM's `Material.cpp` (3.4k lines), merged with what rend2 has. Tables (`table` decls) get a small C decl store.
- **Quake 3 shaders map onto the same structure** while parsing, so they render unchanged in Q3 worlds and lit in `.proc` worlds:

| Quake 3 shader | Doom 3 material |
|---|---|
| stages, `map`, `clampMap` | stages |
| `animMap` | a `map` indexed by a table over time |
| `blendFunc` | `blend` |
| `rgbGen`/`alphaGen` (wave → table expressions; `entity`/`vertex` → `colored`/`vertexColor`) | stage colour expressions |
| `alphaFunc` | `alphaTest` |
| `tcMod scroll/scale/rotate/stretch/transform` | `translate`/`scale`/`rotate`/expressions |
| `tcMod turb` | a sin table |
| `tcGen environment` | `texgen reflect` |
| `deformVertexes` | kept (rend2 has them all) |
| `surfaceparm`, `cull`, `polygonOffset`, `sort` | flags |
| lightmap stages | kept in Q3 worlds; in `.proc` worlds the base texture becomes the `diffusemap` and the lighting comes from lights |
| `normalMap`/`specularMap` (rend2) | `bumpmap`/`specularmap` |
| `fogParms` | a fog material (for a fog light in `.proc` worlds) |
| `skyParms` | kept |

- **Upgrader:** `tools/shader2mtr` writes that mapping out as `.mtr` text, for authors who want to work in materials. Anything unmapped is written as a comment and reported. The same code is the engine's parser, so the two can't drift apart.
- **Daikatana:** bsp-sekai and our asset conversion write `materials/*.mtr` instead of `scripts/*.shader`:
  - surface flags → material flags: `SURF_FLOWING` → translate, `SURF_FULLBRIGHT`, translucency, sky;
  - Daikatana's surface types are already Doom 3's surface types (47dc4d9).
- **Done when:**
  - Quake 3 maps and Daikatana's BSPs look the same as before (`./dk test` shots compared);
  - the upgrader round-trips our shaders to `.mtr` and back to the same render.

### Phase 3: `.proc` worlds and Doom 3 lights (spearmint renderergl2)

- **World:** `.proc` loading, areas, portals and portal-flow visibility translated to C from TDM's `RenderWorld_load`, `RenderWorld_portals` and `RenderWorld` (~4.8k lines).
  - It sits beside `tr_bsp.c`; the map's extension picks which.
  - Doors close portals through a new `SetPortalState`.
- **API** (`tr_public.h`, new calls alongside the existing ones):
  - `LoadWorld(.proc)`;
  - `AddEntityDef/UpdateEntityDef/FreeEntityDef`, `AddLightDef/UpdateLightDef/FreeLightDef`;
  - `SetPortalState`.

  The immediate calls (`AddRefEntityToScene`, `AddLightToScene`) still work: each frame's immediate entities and dlights are fed into the same lighting as temporary defs. Mods written for Quake 3 keep working.
- **Lighting:** Doom 3's light model, from `tr_light`, `tr_lightrun` and `Interaction` (~5k lines):
  - point and projected lights;
  - falloff and projection images;
  - per-surface interactions;
  - one interaction GLSL pass per light in rend2's program manager (`lightall` gains a Doom 3 interaction permutation, or a new program from TDM's `tdm_interaction.glsl`).
- **mint-arena's cgame:**
  - keeps a handle per entity in `.proc` worlds (`CG_Character`, `CG_Item`, movers, effects, local entities), updating it when it changes;
  - its dlights become light defs; the cambot's lamp is a projected light.
- **Order of work:** each step is renderable before the next.
  1. The `.proc` world unlit (ambient only).
  2. One light, no shadows.
  3. All lights.
  4. Entities.
- **Done when:**
  - e1m1a renders from its `.proc` with Daikatana's lights, no shadows yet;
  - Quake 3 maps are unchanged;
  - `./dk test` passes.

### Phase 4: shadow maps

- **Atlas:** TDM's shadow-map atlas (`FrameBufferManager`, `ShadowMapStage`, the atlas page assignment in `tr_light`), translated to C on rend2's FBO code:
  - six faces a point light, one for a projected light;
  - sizes from screen size;
  - one pass for all lights;
  - alpha-tested casters.
- **Soft shadows:** PCSS from `tdm_shadowmaps.glsl`.
- **Sun:** parallel lights use rend2's existing sun cascades, reworked to take the light def's direction.
- **In Q3 worlds:** dynamic lights cast shadows as well. This is the fix for the broken `r_dlightMode 2`.
- **Cambot:** its lamp casts shadows.
- **Done when:** e1m1a and e1m1b have shadowed lights; the frame time on this Mac is noted.

### Phase 5: the light grid

After RBDOOM-3-BFG.
- **Bake:** a command, `bakeLightGrid <map>`:
  - a grid per area, from the `.proc`'s area bounds;
  - at each point, a cubemap rendered with the `bake 1` lights and the sky (rend2's cubemap rendering, `R_RenderCubemapSide`);
  - each cubemap folded into L2 spherical harmonics;
  - saved as `maps/<map>.lightgrid`.
- **Use:** an ambient term in the interaction pass samples it per pixel for the world and per entity for models.
- **Probes:** environment probes for specular, building on rend2's cubemaps.
- **Workflow:** bakes are part of `./dk convert` (headless).
- **Done when:** e1m1a and e1m1b are lit by grid plus lights, compared side by side with Daikatana's screenshots.

### Phase 6: fog

- **Fog lights:** from Daikatana's fog brushes (phase 1), drawn with TDM's `fog_light` GLSL: the swamp's fog, from inside and outside.
- **Quake 3 fog volumes:** `fogParms` brushes keep rend2's fog in Q3 worlds.
- **Global fog:** rend2's global fog (`fogvars`, the refdef fog fields) moved from per vertex to per pixel, for both kinds of world.
- **Done when:** e1m1a's swamp compared with Daikatana's.

### Phase 7: stealth hooks

- **Light gem:** TDM's (a 64×64 subview, async readback), including the light grid.
- **CPU light query:** for monsters ("can I see the player in this light"), as script events.
- **HUD:** a gem drawn from the `.menu` HUD.
- The stealth AI itself is its own plan, after TDM.

### Phase 8: the rest

- **Navigation:** AAS from dmap's output (Doom 3's AAS compiler) or from the Quake 3 BSP kept as a by-product; decided then.
- **renderergl1:** kept for old hardware, or dropped.

## Risks and open questions

- **Bevels:** dropping bevel planes wrongly makes broken brushes. The test is that dmap gives no leaks and `.cm` collision equals the BSP's.
- **Two models in one shader system:** Quake 3 stage lighting (lightmaps, vertex colour) and Doom 3 interactions have to meet in one `shader_t`. The rule: which kind of world it is decides how a stage is lit, and the material decides what it looks like. Getting this boundary clean is the core of phase 2.
- **Translating to C** is still ~15–20k lines (world, lights, interactions, atlas, materials, light gem).
  - Two bug sources: idLib's operator-heavy math becoming function calls, and object lifetimes becoming explicit.
  - Keeping TDM's names and structure in the translated files keeps them reviewable.
  - The C idLib ports cover most of the math.
- **Cost of lights:** e1m1b has 216 lights. The bake/dynamic split and the atlas budget decide the frame rate. The converter's guess has to be good, and tuning is per map.
- **Apple's OpenGL** is frozen at 4.1 and deprecated. Metal is a later question.
- **dmap:** whether the offline tools may stay C++ (only the engine and game must be C) is still open.
- **Licence:** The Dark Mod is GPL v3; Spearmint and mint-arena are GPL v3 with Doom 3's additional terms. Fine, but keep notices on what we take.

## Reference

- `spearmint/code/renderergl2`, `renderercommon`: the renderer we grow.
- `mint-arena/code/idlib`: C ports of idLib (`q_extramath`, `polylib`, `surface`, `mapfile`, `q_containers`, `str`, `strpool`, `hashindex`, `dict`, `drawvert`, `lcp`).
- `darkmod_src/`: `renderer/` (frontend, backend/stages, resources/Material.cpp, glprogs), `tools/compilers/dmap`, `game/LightGem.*`, `frontend/LightQuerySystem.*`.
- `../dhewm3-debugger/neo/renderer`: the original Doom 3 renderer, for comparison.
- RBDOOM-3-BFG (GitHub `RobertBeckebans/RBDOOM-3-BFG`): the light grid bake and irradiance volumes.
- Daikatana (`atsb/daikatana-restoration-project`): `base/ref_gl/gl_rmain.cpp` (global fog), `gl_fogsurf.cpp` (volume fog), `dlls/world/world.cpp` (worldspawn fog keys).
