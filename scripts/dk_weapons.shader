// Daikatana's weapon sprites (models/e1/we_*.sp2), for effects/dk: an .sp2
// is a list of frame images, each frame a shader here; colour and alpha
// come from the effect.

// ion blaster bolt flare
dkfx/ionbf
{
	cull none
	{
		map skins/we_ionbf.tga
		blendFunc blend
		rgbGen vertex
		alphaGen vertex
	}
}

// ion blaster bolt dissipating: 5 frames at Daikatana's 10 a second, from
// when the particle appears (the effect's setShaderTime)
dkfx/ionexpl
{
	cull none
	{
		animMap 10 skins/we_ionexpl0001.tga skins/we_ionexpl0003.tga skins/we_ionexpl0005.tga skins/we_ionexpl0007.tga skins/we_ionexpl0009.tga
		blendFunc blend
		rgbGen vertex
		alphaGen vertex
	}
}

// Daikatana's flare sprites (models/global/e_flyellow.sp2, e_flgreen.sp2):
// the thunderskeet's shot and its charge
dkfx/flyellow
{
	cull none
	{
		map skins/e_flyellow.tga
		blendFunc add
		rgbGen vertex
	}
}

dkfx/flgreen
{
	cull none
	{
		map skins/e_flgreen.tga
		blendFunc add
		rgbGen vertex
	}
}

// Daikatana's muzzle flash sprite (me_mflash): a rockgat firing; its alpha
// cuts the fire's shape out of the square
dkfx/mflash
{
	cull none
	{
		map skins/me_mflash.tga
		blendFunc GL_SRC_ALPHA GL_ONE
		rgbGen vertex
		alphaGen vertex
	}
}

// Daikatana's e_flare.sp2: a firefly (cg_fireflies.c), coloured and faded by it
dkfx/flare
{
	cull none
	{
		map skins/e_flare.tga
		blendFunc GL_SRC_ALPHA GL_ONE
		rgbGen vertex
		alphaGen vertex
	}
}

// Daikatana's e_flare4+.sp2: a firefly (cg_fireflies.c), coloured and faded by it
dkfx/flare4+
{
	cull none
	{
		map skins/e_flare4+.tga
		blendFunc GL_SRC_ALPHA GL_ONE
		rgbGen vertex
		alphaGen vertex
	}
}

// Daikatana's e_flare4+o.sp2: a firefly (cg_fireflies.c), coloured and faded by it
dkfx/flare4+o
{
	cull none
	{
		map skins/e_flare4+o.tga
		blendFunc GL_SRC_ALPHA GL_ONE
		rgbGen vertex
		alphaGen vertex
	}
}

// Daikatana's e_flare4x.sp2: a firefly (cg_fireflies.c), coloured and faded by it
dkfx/flare4x
{
	cull none
	{
		map skins/e_flare4x.tga
		blendFunc GL_SRC_ALPHA GL_ONE
		rgbGen vertex
		alphaGen vertex
	}
}

// Daikatana's e_flare8+.sp2: a firefly (cg_fireflies.c), coloured and faded by it
dkfx/flare8+
{
	cull none
	{
		map skins/e_flare8+.tga
		blendFunc GL_SRC_ALPHA GL_ONE
		rgbGen vertex
		alphaGen vertex
	}
}

// Daikatana's e_flare8+o.sp2: a firefly (cg_fireflies.c), coloured and faded by it
dkfx/flare8+o
{
	cull none
	{
		map skins/e_flare8+o.tga
		blendFunc GL_SRC_ALPHA GL_ONE
		rgbGen vertex
		alphaGen vertex
	}
}

// Daikatana's e_flareo.sp2: a firefly (cg_fireflies.c), coloured and faded by it
dkfx/flareo
{
	cull none
	{
		map skins/e_flareo.tga
		blendFunc GL_SRC_ALPHA GL_ONE
		rgbGen vertex
		alphaGen vertex
	}
}

// Daikatana's lightning bolts (effect_lightning): a flat glow, coloured by
// the effect
dkfx/bolt
{
	cull none
	{
		map $whiteimage
		blendFunc GL_SRC_ALPHA GL_ONE
		rgbGen vertex
		alphaGen vertex
	}
}

// Daikatana's cambot flares (models/e1/me_cambotf.sp2, models/global/
// e_sflred.sp2): its lamp at its hardpoint, yellow as it searches, red when
// it has seen you (cg_character.c, "light_flare"); their alpha their shape
dkfx/cambotf
{
	cull none
	{
		map skins/me_cambotf.tga
		blendFunc GL_SRC_ALPHA GL_ONE
		rgbGen vertex
		alphaGen vertex
	}
}

dkfx/sflred
{
	cull none
	{
		map skins/e_sflred.tga
		blendFunc GL_SRC_ALPHA GL_ONE
		rgbGen vertex
		alphaGen vertex
	}
}

// a lamp's beam through the air (gfx/fx/lampbeam.tga, tools/models/
// make_lampbeam.py): soft across, its colour and fading the vertexes'
// (cg_character.c, "light_beam")
dkfx/lampbeam
{
	cull none
	nopicmip
	{
		map gfx/fx/lampbeam.tga
		blendFunc add
		rgbGen vertex
	}
}
