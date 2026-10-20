// Daikatana's menu look, shared by every menu.
//
// Daikatana lays its menus out at 640x480: a column of plaques on the right
// (the main menu) and the open sub-menu in the panel on the left. Panels are
// menus of their own, at DK_PANEL_X/Y, and the item rects inside them are
// relative to that corner.

#define DK_TS				.375		// text scale: the fonts' own 18 pixels
#define DK_TS_SMALL			.3
#define DK_GOLD				.81 .61 .39 1	// int_font's colour
#define DK_BRIGHT			1 1 1 1		// int_font_bright
#define DK_DIM				.75 .75 .75 1	// a plaque not under the mouse
#define DK_SELECT			.8 .1 .1 .3		// list selections

#define DK_PANEL_X			80
#define DK_PANEL_Y			90
#define DK_PANEL_W			410
#define DK_PANEL_H			380

#define DK_SND_HOVER		"sounds/menus/button_003.wav"
#define DK_SND_PRESS		"sounds/menus/button_006.wav"
#define DK_SND_ROTATE		"sounds/menus/600ms rotate ascend_001.wav"

// close every panel, before one opens
#define DK_CLOSE_PANELS		close dk_multiplayer ; close dk_join ; close dk_host ; close dk_sound ; \
							close dk_video ; close dk_mouse ; close dk_keyboard ; close dk_options ; \
							close dk_credits ; close dk_quit

// the plaques of the column on the right: Daikatana's 3D buttons. Each is
// models/interface/ib_button in Daikatana's menu view at (35 -3.3 Z), turned
// 210 degrees and scaled 1.09; Z drops 1.165 a row. Y is the top of the row's
// mouse area, where that plaque shows: 67 + 27.6 a row.
#define DK_PLAQUE( NAME, Y, Z, SKIN, ACTIONS ) \
	itemDef { \
		name NAME \
		type ITEM_TYPE_PLAQUE \
		rect 506 Y 130 27 \
		plaque_model "models/interface/ib_button" \
		plaque_skin SKIN \
		plaque_origin 35 -3.3 Z \
		plaque_angles 0 210 0 \
		plaque_scale 1.09 \
		visible 1 \
		action { ACTIONS } \
	}

// a plaque for a menu that isn't there: dark, and the mouse does nothing
#define DK_PLAQUE_OFF( NAME, Y, Z, SKIN ) \
	itemDef { \
		name NAME \
		type ITEM_TYPE_PLAQUE \
		rect 506 Y 130 27 \
		plaque_model "models/interface/ib_button" \
		plaque_skin SKIN \
		plaque_origin 35 -3.3 Z \
		plaque_angles 0 210 0 \
		plaque_scale 1.09 \
		plaque_disabled \
		visible 1 \
	}

// a panel: one of the sub-menus that open over the main menu
#define DK_PANEL( NAME ) \
	name NAME \
	rect DK_PANEL_X DK_PANEL_Y DK_PANEL_W DK_PANEL_H \
	fullScreen MENU_FALSE \
	visible MENU_FALSE \
	focusColor DK_BRIGHT \
	onEsc { close NAME }

// plain text
#define DK_LABEL( X, Y, TEXT ) \
	itemDef { \
		rect X Y 300 18 \
		text TEXT \
		textaligny 14 \
		textscale DK_TS \
		forecolor DK_GOLD \
		decoration \
		visible 1 \
	}

#define DK_LABEL_BRIGHT( X, Y, TEXT ) \
	itemDef { \
		rect X Y 300 18 \
		text TEXT \
		textaligny 14 \
		textscale DK_TS \
		forecolor DK_BRIGHT \
		decoration \
		visible 1 \
	}

// a picture, drawn as it is
#define DK_PIC( X, Y, W, H, SHADER ) \
	itemDef { \
		rect X Y W H \
		style WINDOW_STYLE_SHADER \
		background SHADER \
		decoration \
		visible 1 \
	}

// buttons: Daikatana's button face with the label on it
#define DK_BUTTON( X, Y, W, MIDDLE, FACE, LABEL, ACTIONS ) \
	DK_PIC( X, Y, W, 20, FACE ) \
	itemDef { \
		type ITEM_TYPE_BUTTON \
		rect X Y W 20 \
		text LABEL \
		textalign ITEM_ALIGN_CENTER \
		textalignx MIDDLE \
		textaligny 15 \
		textscale DK_TS \
		forecolor DK_GOLD \
		visible 1 \
		action { play DK_SND_PRESS ; ACTIONS } \
	}

#define DK_BUTTON_SMALL( X, Y, LABEL, ACTIONS )		DK_BUTTON( X, Y, 62, 31, "ui/assets/dk/buttons/small_up", LABEL, ACTIONS )
#define DK_BUTTON_MEDIUM( X, Y, LABEL, ACTIONS )	DK_BUTTON( X, Y, 105, 52, "ui/assets/dk/buttons/medium_up", LABEL, ACTIONS )
#define DK_BUTTON_LONG( X, Y, LABEL, ACTIONS )		DK_BUTTON( X, Y, 200, 100, "ui/assets/dk/buttons/long_up", LABEL, ACTIONS )

// the back arrow
#define DK_BACK( X, Y, ACTIONS ) \
	DK_PIC( X, Y, 20, 20, "ui/assets/dk/buttons/back_up" ) \
	itemDef { \
		type ITEM_TYPE_BUTTON \
		rect X Y 20 20 \
		visible 1 \
		action { play DK_SND_PRESS ; ACTIONS } \
	}

// a radio button (Daikatana's on/off toggles)
#define DK_YESNO( X, Y, LABEL, CVAR ) \
	itemDef { \
		type ITEM_TYPE_YESNO \
		text LABEL \
		cvar CVAR \
		rect X Y 190 18 \
		textaligny 14 \
		textscale DK_TS \
		forecolor DK_GOLD \
		visible 1 \
	}

// a picker: a label and a value cycling through a list
#define DK_MULTI( X, Y, LABEL, CVAR, LIST ) \
	itemDef { \
		type ITEM_TYPE_MULTI \
		text LABEL \
		cvar CVAR \
		cvarFloatList LIST \
		rect X Y 300 18 \
		textaligny 14 \
		textscale DK_TS \
		forecolor DK_GOLD \
		visible 1 \
	}

// a slider with its label above (at LABELY), as Daikatana draws them
#define DK_SLIDER( X, Y, LABELY, LABEL, CVAR, DEF, MIN, MAX ) \
	DK_LABEL( X, LABELY, LABEL ) \
	itemDef { \
		type ITEM_TYPE_SLIDER \
		cvarfloat CVAR DEF MIN MAX \
		rect X Y 210 20 \
		textscale DK_TS \
		forecolor DK_GOLD \
		visible 1 \
	}

// a text field on Daikatana's wide field picture
#define DK_FIELD( X, Y, CVAR, MAXCHARS ) \
	DK_PIC( X, Y, 161, 20, "ui/assets/dk/buttons/field_wide" ) \
	itemDef { \
		type ITEM_TYPE_EDITFIELD \
		cvar CVAR \
		maxChars MAXCHARS \
		maxPaintChars 16 \
		rect X Y 161 20 \
		textalignx 6 \
		textaligny 15 \
		textscale DK_TS \
		forecolor DK_BRIGHT \
		visible 1 \
	}

// a key binding row
#define DK_BIND( X, Y, LABEL, COMMAND ) \
	itemDef { \
		type ITEM_TYPE_BIND \
		text LABEL \
		cvar COMMAND \
		rect X Y 195 16 \
		textaligny 13 \
		textscale DK_TS_SMALL \
		forecolor DK_GOLD \
		visible 1 \
	}
