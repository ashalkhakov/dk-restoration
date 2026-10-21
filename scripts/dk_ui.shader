// Daikatana's menu plaques: models/interface/ib_button with the label skins
// skins/ib_*.tga, darkened through the entity colour when unavailable.

ui/dk/plaque_singleplay
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_singleplay.tga
		rgbGen entity
	}
}

ui/dk/plaque_multi
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_multi.tga
		rgbGen entity
	}
}

ui/dk/plaque_loadgame
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_loadgame.tga
		rgbGen entity
	}
}

ui/dk/plaque_savegame
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_savegame.tga
		rgbGen entity
	}
}

ui/dk/plaque_sound
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_sound.tga
		rgbGen entity
	}
}

ui/dk/plaque_video
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_video.tga
		rgbGen entity
	}
}

ui/dk/plaque_mouse
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_mouse.tga
		rgbGen entity
	}
}

ui/dk/plaque_keyboard
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_keyboard.tga
		rgbGen entity
	}
}

ui/dk/plaque_joystick
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_joystick.tga
		rgbGen entity
	}
}

ui/dk/plaque_options
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_options.tga
		rgbGen entity
	}
}

ui/dk/plaque_config
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_config.tga
		rgbGen entity
	}
}

ui/dk/plaque_credits
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_credits.tga
		rgbGen entity
	}
}

ui/dk/plaque_resume
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_resume.tga
		rgbGen entity
	}
}

ui/dk/plaque_quit
{
	nopicmip
	nomipmaps
	cull none
	{
		map skins/ib_quit.tga
		rgbGen entity
	}
}

// Daikatana's loading bar, drawn over the levelshot while a map loads
gfx/2d/loadingbar
{
	nopicmip
	nomipmaps
	{
		map pics/loadbar.tga
		blendFunc blend
		rgbGen vertex
	}
}

gfx/2d/loadingblock
{
	nopicmip
	nomipmaps
	{
		map pics/loadblock.tga
		blendFunc blend
		rgbGen vertex
	}
}

// the console: Daikatana's picture (its con_0..5 tiles, tools/ui), slid
// down from the top as the console opens (cg_console.c draws its bottom part)
dk/console
{
	nopicmip
	nomipmaps
	{
		clampmap ui/assets/dk/console.tga
	}
}

// what a player looks at and can take or use, lit up over its model (g_frob.c,
// cg_ents.c): The Dark Mod's frob highlight, a pulsing shell
frobHighlight
{
	deformVertexes wave 100 sin 0.5 0 0 0
	{
		map $whiteimage
		blendFunc GL_ONE GL_ONE
		rgbGen wave sin 0.12 0.08 0 0.8
	}
}
