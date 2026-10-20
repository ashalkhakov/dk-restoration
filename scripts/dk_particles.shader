// Daikatana's particle sprites, one shader per cell of the 256x128 atlas
// (cells from ref_gl/gl_particle.cpp R_InitParticles). The effects in
// effects/dk use them; colour and alpha come from the effect.

dkfx/smoke
{
	cull none
	{
		map pics/particles/particles.tga
		tcMod transform 0.25 0 0 0.5 0.25 0
		blendFunc blend
		rgbGen vertex
		alphaGen vertex
	}
}

dkfx/fire
{
	cull none
	{
		map pics/particles/particles.tga
		tcMod transform 0.25 0 0 0.5 0.75 0
		blendFunc blend
		rgbGen vertex
		alphaGen vertex
	}
}

dkfx/cp4
{
	cull none
	{
		map pics/particles/particles.tga
		tcMod transform 0.125 0 0 0.25 0.875 0.75
		blendFunc blend
		rgbGen vertex
		alphaGen vertex
	}
}

dkfx/spark
{
	cull none
	{
		map pics/particles/particles.tga
		tcMod transform 0.0625 0 0 0.125 0.5625 0.875
		blendFunc blend
		rgbGen vertex
		alphaGen vertex
	}
}

dkfx/sparkle1
{
	cull none
	{
		map pics/particles/particles.tga
		tcMod transform 0.125 0 0 0.25 0.125 0.75
		blendFunc blend
		rgbGen vertex
		alphaGen vertex
	}
}

dkfx/sparkle2
{
	cull none
	{
		map pics/particles/particles.tga
		tcMod transform 0.125 0 0 0.25 0.25 0.75
		blendFunc blend
		rgbGen vertex
		alphaGen vertex
	}
}

dkfx/blood2
{
	cull none
	{
		map pics/particles/particles.tga
		tcMod transform 0.0625 0 0 0.125 0.5 0.75
		blendFunc blend
		rgbGen vertex
		alphaGen vertex
	}
}

dkfx/blood3
{
	cull none
	{
		map pics/particles/particles.tga
		tcMod transform 0.0625 0 0 0.125 0.5625 0.75
		blendFunc blend
		rgbGen vertex
		alphaGen vertex
	}
}

dkfx/blood4
{
	cull none
	{
		map pics/particles/particles.tga
		tcMod transform 0.0625 0 0 0.125 0.4375 0.875
		blendFunc blend
		rgbGen vertex
		alphaGen vertex
	}
}

dkfx/blood5
{
	cull none
	{
		map pics/particles/particles.tga
		tcMod transform 0.0625 0 0 0.125 0.5 0.875
		blendFunc blend
		rgbGen vertex
		alphaGen vertex
	}
}

// PARTICLE_BEAM_SPARKS are short beams with this texture, added
dkfx/beamspark
{
	cull none
	{
		map pics/misc/beamspark.tga
		blendFunc add
		rgbGen vertex
	}
}
