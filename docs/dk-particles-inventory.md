# Daikatana particle systems: porting reference

Source: the Daikatana restoration project (base/client/cl_fx.cpp, cl_tent.cpp, cl_pv.cpp, cl_ents.cpp,
base/ref_gl/gl_particle.cpp, base/Projectile_fx.cpp, base/Artifact_fx.cpp, dlls/world/effects.cpp,
dlls/world/sfx_entities.cpp). Line numbers refer to that tree's HEAD.

Plan: express these as OpenJK-style .efx effects, with the OpenJK FX system ported into Spearmint,
so every effect is a data file and not cgame code.

## Core model

- Two pools of 4096 particles. The "simple" list integrates `org + vel*t + accel*t²`, with no 0.5 factor.
  The "complex" list integrates `org + vel*t + 0.5*accel*t²`.
- Gravity is -250. `alpha = alpha0 + t*alphavel`, clamped to 1. A particle dies at alpha <= 0, or at
  `die_time` when one is set.
- One atlas: `pics/particles/particles.tga`, 256x128, alpha-blended, with depth test on and depth
  writes off.
- A particle is drawn as one triangle, the upper-left half of its atlas cell, with side `fScale*scale`.
  `scale` is `pscale` if pscale > 1, otherwise `1 + dist*0.004` (1 when closer than 20 units).
- Vertex colour is `color_rgb` with alpha. Negative components clamp to 0, so (1,-1,-1) means pure red.
- `PARTICLE_BEAM_SPARKS` is drawn as a short view-aligned beam (`pics/misc/beamspark.tga`) from org to
  org + 2*(lastorg - org), radius pscale -> pscale*0.3.

## Atlas cells (pixels s1,t1-s2,t2; t from the top) and fScale

| type | cell | fScale |
|---|---|---|
| SNOW | 0,0-63,63 | 2.3 |
| RAIN | 225,32-255,63 | 2.0 (drawn as a 64x2.56 streak along the fall) |
| BLOOD..BLOOD3 | 112,96 / 128,96 / 144,96 (16x16) | 1.5 |
| BLOOD4, BLOOD5 | 112,112 / 128,112 (16x16) | 1.5 |
| BUBBLE | 0,64-31,95 | 1.5 |
| SMOKE | 64,0-127,64 | 7.0 |
| SPARKS (BEAM_SPARKS alias) | 144,112-159,127 | 1.5 (BIG_SPARKS 3.0) |
| BLUE_SPARKS | 96,112-111,127 | 3.0 |
| ICE | 192,64-255,127 | 3.0 |
| SPARKLE1, SPARKLE2 | 32,96-63,127 / 64,96-95,127 | 3.0 |
| DRIP_* | 96,96-111,111 | 3.0 |
| SPLASH1..3 | 96,64 / 128,64 / 160,64 (32x28) | 4.0 |
| FIRE (FIREFLY alias) | 192,0-255,63 | 3.0 |
| CRYOSPRAY | 160,96-191,127 | 1.0 |
| SPARK_1, SPARK_2 | 32,64-63,95 / 64,64-95,95 | 1.5 |
| SIMPLE | 48,48-63,63 | 1.0 |
| CP1..CP4 | 96,32 / 160,32 / 224,32 / 224,96 (32x32) | 1.5 |

## The generic emitter: CL_GenerateComplexParticle2 (about 80% of effects)

`(origin, Dir, Color, Alpha=(start, depletion, randDepletion), scale, count, spread_deg, maxvel, type, gravityVec)`.
For each particle:

- `pscale = scale*3`
- `alphavel = -(depletion + frand*randDepletion)`
- the direction is Dir with its yaw and pitch each jittered by `crand*spread`
- `speed = 0.55*maxvel + frand*0.45*maxvel`
- the xy origin is jittered by `frand*sp - sp/2`, where `sp = clamp(spread*0.18, 1, 10)`
- `accel = gravityVec`

`CL_GenerateComplexParticleRadius` places the particles on a ring of the given radius, with half the
spread.

## Effects used in deathmatch

- **Bullet impact.** TE_SMOKE (SMOKE, pscale .5, grey 0.2±0.1, alphavel -(1.4+0.2f), rising), plus 10
  BEAM_SPARKS at colour (1,1,.5), plus a ricochet sound.
- **TE_BLOOD.** `count = dmg & 63`.
  - 65%: BLOOD2..5 at colour (.8,0,0), falling.
  - 35%: CL_BloodThink puffs that grow ×1.10 and fade ×0.95 per frame, half CP4 and half red BLOOD2+.
- **TE_SPARKS.** BEAM_SPARKS with `count = ((rand&31)*(1+dmg))&63`. `vel = dir*dmg² + crand*100`.
  Optional smoke.
- **TE_SPARKLES.** 2 SPARKLE1/2 at colour (.45,.45,.65), Alpha (.65,.55,.25), scale .75, spread 7,
  maxvel 500.
- **Explosions (TE_POLYEXPLOSION, rockets, C4, sidewinder).**
  - BigExplosion: `int(64*scale)&255` BEAM_SPARKS at colour (1,.6,.3).
  - ExplosionParticles:
    - 5 CP4: colour (.65,.635,.15), Alpha (.75,.75,.1), scale 2+.75f, spread 35, maxvel 150;
    - 10 SMOKE: colour (.01,.01,.01), Alpha (.75,.65,.1), scale 5, spread 65, maxvel 150,
      gravity +50z.
- **TE_EXPLOSION_SMALL.** 16 BEAM_SPARKS at colour (1,.25,.25), ±32.
- **Projectile trails (TEF_PROJ table in Projectile_fx.cpp).**
  - Sidewinder: smoke in air, bubbles in water.
  - Ballista: fire and smoke.
  - Ion blaster: green beam sparks.
  - Venomous: CP4 and smoke.
  - Trident: blue sparks.
  - Kineticore: snow and ice.
- **Entity trails.**
  - Discus: EF_BEAMTRAIL smoke plus a beam trail.
  - Bolter: EF_BOLTTRAIL sparks (1,.4,1).
  - Stavros: EF_METEOR smoke and fire sparks.
  - Wyndrax wisp.
  - Sunflare and slugger grenade: EF_SMOKETRAIL.
  - Venomous: EF_POISON.
- **Item respawn (EF_RESPAWN).** 128 spiralling SPARKLE1/2 in a 64x64x32 box for 3 s.
- **Boost artifacts.** 12 SPARKLE1 one-frame particles around the item, coloured per boost.
- **Water.** Splash and swim bubbles: 40/25/3 BUBBLEs, vel.z 50, removed when they leave the water.

## Map emitters

- **effect_rain** (e1dm2 127, e1dm2a 58).
  - Brush volume, RAIN streaks at vel (0,0,-400), alpha .4.
  - Density `w*d*0.01` within 512 units, half that beyond.
  - SPLASH1/3 at the floor, 101 ms each.
- **effect_snow** (e3dm2 13, e3m1dm 168).
  - SNOW at vel (0,0,-50-(rand&10)), ±20 xy drift unless spawnflag 1.
  - Density `(w*d)>>12`.
- **effect_lightning** (e1dm2 3, slicedm1 2). A lightning beam, plus endpoint sparkles unless
  NO_SPARKS (0x100).
- **sfx_complex_particle** (e3m1dm 6). A CL_GenerateComplexParticle2 emitter.
  - Keys: count, velocity, spread, radius, gravity/gravitydir, target, scale, alpha_level, delta_alpha,
    emission, emissiontime, _color.
  - Type spawnflags: SIMPLE 1, CP3 2, RAIN 4, SMOKE 8, CP1 0x10, CP2 0x20, CP4 0x40, BUBBLE 0x80.
  - Toggle/random spawnflags: 0x100-0x800.
- **misc_hosportal / misc_fountain.** Spiral particles and an ART_FOUNTAIN burst when used.
- **effect_drip** has no spawn function in DK, so it is a no-op.

## Quirks to decide on when porting (faithful vs. better)

- Each sprite is half a triangle, so the original clips the lower-right half of every sprite. A full
  quad looks better.
- The rain streak direction is computed once on the first frame. Recompute it every frame.
- BloodThink, spirals and bubbles update per frame, and sfx_complex_particle emits per frame count.
  Make all of these time based.
