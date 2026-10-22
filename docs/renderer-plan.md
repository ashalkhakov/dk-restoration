# Renderer plan: The Dark Mod's renderer in Spearmint

Status: agreed direction, not started (2026-10-22).

## Why

- **Light has to be dynamic.** Cambots carry lamps, and parts of the game should be sneaked through. Shadows from moving lights matter, and so does how lit the player is.
- **Daikatana's lightmaps can't stay.** The compiler that made them is gone, and they are too coarse for today.
- **Its fog is half missing.**
  - The global distance fog works: `fog_start`, `fog_end`, `fog_color` and `fog_value` reach the game as Spearmint's global fog.
  - The volume fog brushes (`SURF_FOGPLANE`, drawn by `gl_fogsurf.cpp` from the brush's hull) are dropped by our converter (`VIEWFOGS 0` in `bsp-sekai/code/bsp_dk.c`). The swamp's fog is missing.
- **We keep moving to Doom 3's subsystems,** and the renderer and its materials are next.

## What we looked at

| Renderer | Shadows | Static light | Fog | GL | Notes |
|---|---|---|---|---|---|
| Spearmint renderergl2 (in use, `RENDERER=opengl2`) | Sun cascades only; dlight cube shadows broken (`r_dlightMode 2`) | Lightmaps, light grid | Q3 fog volumes, global fog; per vertex | GL 2/3 | 32 point dlights at most, immediate-mode API |
| dhewm3 | Stencil volumes only | None, all per-pixel lights | Fog/blend lights, fixed function | GL 1.x + ARB programs | No GLSL, so its backend would need rewriting |
| The Dark Mod | **Shadow-map atlas (6 faces a light, sized by screen size), PCSS soft shadows**, stencil as well | None (ambient lights, SSAO) | **Fog lights in GLSL** with fog-entry math | **GL 3.3 core**, FBOs, UBO, instancing | Light gem, volumetric lights, HDR; ~93k lines; heavy coupling; no macOS build |
| RBDOOM-3-BFG | Shadow atlas, sun cascades | **Baked light grid + irradiance probes** | Doom 3's | NVRHI (DX12/Vulkan) | Too far from GL to port; we take its light grid idea |

We take The Dark Mod's renderer and the light grid idea from RBDOOM-3-BFG.

## Target

1. **World:** Daikatana BSP → Doom 3 `.map` (bsp-sekai) → TDM's dmap → `.proc` (areas, portals, surfaces) and `.cm` (collision; `cm2` already loads Doom 3 collision models).
2. **Renderer:** TDM's, as a new Spearmint renderer module, in C++. It sits on idLib and a framework shim over qcommon, with its reach-ins to TDM's game code cut.
3. **Materials replace shaders:**
   - Daikatana's conversion writes materials directly.
   - A shader → material upgrader serves Quake 3 assets and other mods.
4. **Lighting:**
   - Direct light comes from Doom 3 lights, shadow-mapped.
   - Fill and bounce light comes from a light grid with irradiance probes, baked in the engine (RBDOOM-3-BFG's approach).
   - No lightmaps.
5. **Fog:**
   - Daikatana's fog brushes become fog lights.
   - Its global fog becomes a global fog stage.
6. **Stealth:** TDM's light gem and CPU light query read both lights and grid.

## Phases

Each phase ends with something we can run and screenshot through `./dk`, and is committed and pushed.

### Phase 1: Doom 3 maps from Daikatana's (bsp-sekai, dk)

**Writer:** `bsp-sekai` gets a `.map` writer next to the Quake 3 BSP one (e.g. `-format d3map`).
- **Brushes:** from the brush and brush-side lumps (`bsp_dk.c` already reads them, at 4521), world and brush models alike.
- **Bevels:** the axial bevel planes qbsp added are among the brush sides, with no flag. Drop a side when its plane is axial, it carries no face of its own, and the brush stays the same without it (test by clipping). Hint, skip and clip sides become `textures/common/*` materials.
- **Texture alignment:** Daikatana's texinfo vectors become `brushDef3` texture matrices (as q3map2's `-convert` does for brush primitives).
- **Entities:**
  - As written now: `.ent` overrides, gametype keys and Daikatana's classnames.
  - **Lights:** `light` entities, which the original BSPs keep (e1m1a about 82, e1m1b 216), become Doom 3 lights:
    - `light` → `light_radius`; `_color` → color; Daikatana's `cap` is noted;
    - a `bake` key (1: the light grid only; 0: dynamic) is guessed first: big, dim and uncapped lights become fill.
  - **Fog:** the fog brushes become fog light entities (their box, `fog_color`, density from the texinfo value).
  - **Sky and sun:** worldspawn `ambient`, sky and sun become a parallel light and the grid's sky term.

**dmap:** TDM's dmap (`darkmod_src/tools/compilers/dmap`, ~12.7k lines) built as a standalone tool, `tools/dmap`, on the same idLib and shim as phase 2.
- `./dk convert` writes `maps/<map>.map`, `.proc` and `.cm`.
- **During the move,** `./dk convert` keeps writing the Quake 3 BSP:
  - `bspc` builds the AAS (bot and monster navigation) from it;
  - the current renderer keeps working until phase 3.

**Done when:**
- e1m1a, e1m1b and e1m1c dmap without leaks;
- the `.proc` area count is sane;
- `.cm` collision plays the same as the BSP's (`./dk test`).

### Phase 2: idLib and the framework shim (spearmint)

- **idLib:** TDM's `idlib/` (~116k lines with math, containers, Lexer/Parser, Dict, Str, Heap, ParallelJobList, Thread) added to spearmint as a C++ library. CMake and the Makefile learn C++; macOS arm64 first.
- **Shim** (`spearmint/code/renderer_d3/framework/`): small implementations of the interfaces the renderer calls, over qcommon:
  - `common` (Printf, Warning, Error → Com_*);
  - `cvarSystem` and `idCVar` (→ Cvar_*);
  - `cmdSystem` (→ Cmd_*);
  - `fileSystem` (→ FS_*, pk3-aware);
  - `declManager` for the decls the renderer uses: material, skin, particle, table, plus fx if needed.

  Each grows only as far as the renderer needs. A link test ("every symbol the renderer wants") tracks progress.
- **Left out:** Session (the frontend thread starts single-threaded), the GUI system (`tr_guisurf`), demo files, Tracy, RenderDoc.

**Done when:** dmap (phase 1) builds and runs on this idLib and shim.

### Phase 3: the renderer module (spearmint)

- **Code:** TDM's `renderer/` (frontend, backend and stages, resources, glprogs) as `renderer_d3`, loaded through `com_renderer d3`.
- **Cut the reach-ins to TDM's game:**
  - `gameLocal` in `tr_subview.cpp` (light gem, grabber), `RenderWorld*.cpp` and `Model_prt.cpp` become callbacks the cgame registers.
  - TDM-only features we don't want (xray, frob outline stage) are left out until wanted.
- **API** (`tr_public.h`, a new version):
  - **2D, HUD and menus:** the existing `refexport_t` 2D calls (DrawStretchPic, fonts, `RegisterShader` → material).
  - **World:** retained, in Doom 3's style:
    - `LoadWorld(.proc)`;
    - `AddEntityDef/UpdateEntityDef/FreeEntityDef`, `AddLightDef/UpdateLightDef/FreeLightDef`;
    - `RenderScene(view)`;
    - area and portal state for doors (`SetPortalState`).
- **mint-arena's cgame** keeps a handle per entity and updates it when it changes:
  - `CG_Character`, `CG_Item`, movers, effects (`cg_fx.c`), local entities.
  - The 41 `trap_R_*` calls in `cg_syscalls.c` are mapped one by one. Dlights become light defs (the cambot's lamp is a spotlight with a projection image).
- **Models:** md3 and iqm through TDM's model loaders (md3 exists there; iqm is new, or our skeletal path as a dynamic model); md5 comes for free.
- **macOS:** core profile 4.1. The stencil-texturing and buffer-storage paths are off; GLAD loader; SDL context in place of GLFW.

**Done when:**
- e1m1a renders with `com_renderer d3`: world, characters, items, HUD and menus;
- `./dk test` passes on both renderers;
- screenshots compared side by side.

### Phase 4: materials

- **Daikatana:** bsp-sekai and our asset conversion write `materials/*.mtr` instead of `scripts/*.shader`:
  - surface flags → material flags: `SURF_FLOWING` → translate, `SURF_FULLBRIGHT`, translucency, sky;
  - Daikatana's surface types are already Doom 3's surface types (47dc4d9);
  - normal and specular maps get generated or hand-made later.
- **The upgrader** (`tools/shader2mtr`, also usable in-engine for unknown shaders), Quake 3 shader → Doom 3 material:

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
| `deformVertexes autosprite/autosprite2/wave/move` | `deform sprite/tube/turbulent/move` |
| `surfaceparm`, `cull`, `polygonOffset`, `sort` | flags |
| lightmap stages | dropped; the base texture becomes the `diffusemap` |
| `fogParms` | a fog material for a fog light |
| `skyParms` | a skybox material |

  Anything unmapped is written as a comment and reported.
- **Done when:** every Daikatana surface has a material, and the upgrader converts `baseq3`-style shaders well enough that a Quake 3 map's world looks right.

### Phase 5: lights, shadows, light grid

- **Dynamic lights:** TDM's shadow-map atlas and PCSS as they are. `r_maxShadowMapLight` tuned for Daikatana's light sizes.
- **Light grid:** after RBDOOM-3-BFG.
  - **Bake:** a command, `bakeLightGrid <map>`:
    - a grid per area, from the `.proc`'s area bounds;
    - at each point, a cubemap rendered with the `bake 1` lights and the sky;
    - each cubemap folded into L2 spherical harmonics;
    - saved as `maps/<map>.lightgrid`.
  - **Use:** an ambient stage in the interaction pass samples it per pixel for the world and per entity for models.
  - **Probes:** environment probes for specular follow the same way.
  - **Workflow:** bakes are part of `./dk convert` (headless, e.g. a hidden window).
- **Sun:** parallel lights get cascades. TDM leaves parallel lights to stencil, so this is new code, after rend2's cascades or RBDOOM's.
- **Cambot:** its lamp is a shadow-casting spotlight.
- **Done when:** e1m1a and e1m1b lit, side by side with Daikatana's screenshots; the frame time on this Mac is noted.

### Phase 6: fog

- Fog lights from Daikatana's fog brushes (phase 1) drawn by TDM's GLSL fog: the swamp's fog, from inside and outside.
- A global fog stage for worldspawn fog (linear, `fog_start` / `fog_end`, a sky distance), or a map-sized fog light if that looks right.
- **Done when:** e1m1a's swamp compared with Daikatana's.

### Phase 7: stealth hooks

- **Light gem:** TDM's (a 64×64 subview, async readback), including the light grid.
- **CPU light query:** for monsters ("can I see the player in this light"), as script events.
- **HUD:** a gem drawn from the `.menu` HUD.
- The stealth AI itself is its own plan, after TDM.

### Phase 8: retire the old path

- **Navigation:** AAS from dmap's output (Doom 3's AAS compiler) or from the Quake 3 BSP kept as a by-product; decided then.
- **Old renderers:** renderergl1 and renderergl2 kept for other mods, or dropped.

## Risks and open questions

- **Bevels:** dropping bevel planes wrongly makes broken brushes. The test is that dmap gives no leaks and `.cm` collision equals the BSP's.
- **Coupling:** cutting TDM's coupling can grow. If the shim gets large, take more of TDM's framework rather than writing it.
- **Cost of lights:** e1m1b has 216 lights. The bake/dynamic split and the atlas budget decide the frame rate. The converter's guess has to be good, and tuning is per map.
- **Apple's OpenGL** is frozen at 4.1 and deprecated. Metal (e.g. through a translation layer) is a later question.
- **Model formats:** iqm in TDM's model system, versus keeping our skeletal code and feeding it as a dynamic model.
- **Licence:** The Dark Mod is GPL v3; Spearmint and mint-arena are GPL v3 with Doom 3's additional terms. Fine, but keep notices on what we take.

## Reference

- `darkmod_src/`: `renderer/` (frontend, backend/stages, resources, glprogs), `tools/compilers/dmap`, `idlib/`, `game/LightGem.*`, `frontend/LightQuerySystem.*`.
- `../dhewm3-debugger/neo/renderer`: the original Doom 3 renderer, for comparison.
- RBDOOM-3-BFG (GitHub `RobertBeckebans/RBDOOM-3-BFG`): the light grid bake and irradiance volumes.
- Daikatana (`atsb/daikatana-restoration-project`): `base/ref_gl/gl_rmain.cpp` (global fog), `gl_fogsurf.cpp` (volume fog), `dlls/world/world.cpp` (worldspawn fog keys).
