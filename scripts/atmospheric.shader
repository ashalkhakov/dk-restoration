gfx/misc/particles
{
	cull none
	entityMergable		// allow all the sprites to be merged together
	{
        map pics/particles/particles.tga
		blendFunc GL_SRC_ALPHA GL_ONE_MINUS_SRC_ALPHA
		rgbGen		vertex
		alphaGen	vertex
	}
}