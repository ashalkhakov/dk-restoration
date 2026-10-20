// debug drawing, translucent and seen from both sides (cg_drawAAS)
debug/aas
{
	cull none
	nopicmip
	polygonOffset
	{
		map $whiteimage
		blendFunc GL_SRC_ALPHA GL_ONE_MINUS_SRC_ALPHA
		rgbGen vertex
		alphaGen vertex
	}
}
