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
