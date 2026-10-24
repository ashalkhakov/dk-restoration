// skeletal characters (characters/)

characters/test/testchar
{
	{
		map characters/test/testchar.tga
		rgbGen lightingDiffuse
	}
}

// the skinny worker's PDA (characters/props/pda.iqm, tools/models/make_pda.py):
// lit by the room, its screen glowing green over it, a faint flicker
characters/props/pda
{
	{
		map characters/props/pda.tga
		rgbGen lightingDiffuse
	}
	{
		map characters/props/pda_glow.tga
		blendFunc GL_ONE GL_ONE
		rgbGen wave noise 0.9 0.1 0 8
	}
}
