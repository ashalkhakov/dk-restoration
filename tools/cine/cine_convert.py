#!/usr/bin/env python3
"""cine_convert.py -- Daikatana's cinematics (cin/scripts/*.script) as ours:
camera files, Doom 3 scripts and actor defs, made to be edited

	python3 tools/cine/cine_convert.py <dkres> <out> [name...]

For each cinematic <name> (all of them, or those named):

	<out>/cameras/<name>_NN.camera	its shots: keyframe cameras (camera_keys,
									bg_camera.c), each key with the exact
									velocities of Daikatana's curves, its FOV
									and fade
	<out>/script/<name>.script		namespace <name> { ... play() }: the shots
									one after another, cut, each starting its
									actors' threads and its sounds, as
									Daikatana's player did
	<out>/maps/<map>.script			what a map includes: the cinematics it
									starts (the game compiles it with the
									map's script; all of them at once would be
									more than the scripts' memory)
	<out>/def/cine_actors.def		the actors: each a cinematic character
									(scriptobject cine_actor). One of our rigged
									characters (Hiro, Mikiko, Superfly) is that
									character, with the map's cinematic
									animations moved onto its rig, in place
									(models/rigged/<character>_<map>.iqm, by
									tools/rig/retarget.py, ./dk cine); the
									travel taken out of them is the game's to
									do (cine_playMove). Any other is on
									Daikatana's model for now.

A map starts one as Daikatana's did: its worldspawn's "cinematic_intro". Our
own versions of a cinematic or a shot go in the repository's cine/ (its
script/ and cameras/), in place of these by name (./dk assembles them).
"""

import glob
import json
import math
import os
import re
import sys

sys.path.insert( 0, os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), "..", "rig" ) )
sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
from md3 import MD3
import dkcine

# the monsters a cinematic uses, their models (Daikatana's monster table)
MONSTER_MODELS = {
	"monster_fatworker":	"models/e1/m_mwfaty",
	"monster_skinnyworker":	"models/e1/m_mwskny",
	"monster_buboid":		"models/e3/m_buboid",
	"monster_rocketdude":	"models/e4/m_rockgang",
	"monster_uzigang":		"models/e4/m_uzi",		# (Daikatana names m_uzigng.dkm; the file is m_uzi)
	"monster_gharroth":		"models/e3/m_gharroth",
}

# their walk and run speeds (Daikatana's AIData.csv): they walk at these, their
# legs' animation keeping up (the game plays it faster)
MONSTER_SPEEDS = {
	"fatworker": ( 35, 74 ), "skinnyworker": ( 35, 150 ), "buboid": ( 65, 80 ),
	"rocketdude": ( 53, 250 ), "uzigang": ( 45, 250 ), "gharroth": ( 80, 250 ),
}

def def_anim_speeds( path ):
	"""a model def's walk and run speeds over the ground (its "anim_speed
	walka", "runa"), or None for those it hasn't"""
	if not os.path.exists( path ):
		return ( None, None )
	text = open( path ).read()
	speeds = []
	for anim in ( "walka", "runa" ):
		m = re.search( r'"anim_speed %s"\s+"([0-9.]+)"' % anim, text )
		speeds.append( float( m.group( 1 ) ) if m else None )
	return tuple( speeds )

# a cinematic's walk: Daikatana's actors walked about 35 a second (Hiro and
# Toshiro out of the dojo, shots 27 and 28 of the intro), their walks drawn
# at 10 frames a second for slower (Hiro's 10, Toshiro's 5): the game plays
# the legs up to legs_rate_max faster to keep up, not more (faster looks
# hurried; a little slide less so)
CINE_WALK = 35
CINE_LEGS_RATE_MAX = 2

def actor_entity_def( fp, defname, model, speeds ):
	walk, run = speeds
	fp.write( "entityDef %s {\n\t\"spawnclass\"\t\"monster\"\n\t\"model\"\t\t\"%s\"\n"
			  "\t\"scriptobject\"\t\"cine_actor\"\n\t\"health\"\t\"100000\"\n\t\"skill_scale\"\t\"0\"\n"
			  "\t\"run_speed\"\t\"%g\"\n\t\"walk_speed\"\t\"%g\"\n\t\"legs_rate_max\"\t\"%g\"\n"
			  "\t\"unstick\"\t\"0\"\t// where Daikatana's stood, our box or not (Hiro at the dojo door)\n"
			  "\t\"turn_rate\"\t\"360\"\n\t\"fov\"\t\t\"360\"\n}\n"
			  % ( defname, model, run or 220, walk or CINE_WALK, CINE_LEGS_RATE_MAX ) )

# a cinematic character's model: its prefix, then the first four letters of
# the map's name (Daikatana's cinematic_character_init)
CINE_PREFIX = {
	"cine_gharroth": "c_ghar_", "cine_pgharroth": "c_pghar_", "cine_hiro": "c_hiro_", "cine_phiro": "c_phiro_",
	"cine_mikiko": "c_mikiko_", "cine_smikiko": "c_smikiko_", "cine_mikikofly": "c_mikikofly_",
	"cine_priest": "c_priest_", "cine_superfly": "c_super_", "cine_super": "c_super_", "cine_toshiro": "c_tosh_",
	"cine_tatsuo": "c_tatsuo_", "cine_kage": "c_kage_", "cine_casseti": "c_casseti_", "cine_fmg": "c_fmg_",
	"cine_osaka": "c_osaka_", "cine_usagi": "c_usagi_", "cine_gusagi": "c_gusagi_", "cine_suagis": "c_suagis_",
	"cine_ninja": "c_ninja_", "cine_inshiro": "c_inshiro_", "cine_fatworker": "c_fat_", "cine_thinworker": "c_thin_",
	"cine_drug1": "c_drug1_", "cine_drug2": "c_drug2_", "cine_charon": "c_char_", "c_charon": "c_char_",
	"cine_mwguard": "c_mwguard_", "cien_hiro": "c_hiro_",
}

# our rigged characters, and their cinematic models' prefix
RIGGED = {
	"cine_hiro": ( "hiro", "c_hiro_" ), "cien_hiro": ( "hiro", "c_hiro_" ),
	"cine_mikiko": ( "mikiko", "c_mikiko_" ),
	"cine_superfly": ( "superfly", "c_super_" ), "cine_super": ( "superfly", "c_super_" ),
	# the intro's, and Kage Mishima's fights (e1m7, e4m6)
	"cine_inshiro": ( "inshiro", "c_inshiro_" ), "cine_toshiro": ( "toshiro", "c_tosh_" ),
	"cine_ninja": ( "ninja", "c_ninja_" ), "cine_osaka": ( "osaka", "c_osaka_" ),
	"cine_usagi": ( "usagi", "c_usagi_" ), "cine_tatsuo": ( "tatsuo", "c_tatsuo_" ),
	"cine_kage": ( "kage", "c_kage_" ),
}

def rigs_of_cinematic_models():
	"""the cinematic models rigged as themselves (./dk rig: def/rig_*.def and
	def/char_*.def, made "from models/cinematic/<model>.md3"; Hiro in his gi,
	the intro's people): model name -> its rig's def. Such a rig's own
	animations are Daikatana's frames as they were, travel and all, so its
	actors play them as they are, as a monster plays its own"""
	rigs = {}
	for path in glob.glob( os.path.join( "def", "rig_*.def" ) ) + glob.glob( os.path.join( "def", "char_*.def" ) ):
		text = open( path ).read()
		m = re.match( r"// made by tools/rig/autorig\.py from models/cinematic/(\S+)\.md3", text )
		d = re.search( r"entityDef\s+(\S+)", text )
		if m and d:
			rigs[m.group( 1 )] = path
	return rigs

RIGGED_MODELS = rigs_of_cinematic_models()

def monster_rig( classname, model = None, dkres = None ):
	"""a monster's rigged model def (def/rig_<name>.def, ./dk rig), or a
	cinematic model's rigged as itself (RIGGED_MODELS): ( model def name, its
	animations, what autorig --root-out took out of them (its IQM's .json:
	{ animation: { "start", "move", "turn", "frames", "fps" } }, or {}) ), or
	None"""
	if model and os.path.basename( model ) in RIGGED_MODELS:
		path = RIGGED_MODELS[os.path.basename( model )]
	elif classname.startswith( "monster_" ):
		path = os.path.join( "def", "rig_%s.def" % classname[8:] )
	else:
		return None
	if not os.path.exists( path ):
		return None
	text = open( path ).read()
	m = re.search( r"entityDef\s+(\S+)", text )
	if not m:
		return None
	moves = {}
	mesh = re.search( r'"mesh"\s+"(\S+)\.iqm"', text )
	if dkres and mesh and os.path.exists( os.path.join( dkres, mesh.group( 1 ) + ".json" ) ):
		moves = json.load( open( os.path.join( dkres, mesh.group( 1 ) + ".json" ) ) )["anims"]
	return ( m.group( 1 ), set( re.findall( r'"anim (\S+)"', text ) ), moves )

def rigged( dkres, classname, model ):
	"""our character's cinematic animations for that model: ( character, tag,
	the retargeting's JSON ), or None"""
	if classname not in RIGGED or not model or os.path.basename( model ) in RIGGED_MODELS:
		return None
	char, prefix = RIGGED[classname]
	tag = os.path.basename( model )[len( prefix ):]
	path = os.path.join( dkres, "models", "rigged", "%s_%s.json" % ( char, tag ) )
	if not os.path.exists( path ):
		return None
	return ( char, tag, json.load( open( path ) ) )

def fmt( v ):
	return " ".join( "%g" % ( round( x, 4 ) + 0.0 ) for x in v )		# (+ 0.0: no "-0")

def ident( s ):
	"""a name a script can use"""
	s = re.sub( r"[^A-Za-z0-9_]", "_", s )
	return s if re.match( r"[A-Za-z_]", s ) else "_" + s

def map_cinematics( dkres ):
	"""which map starts each cinematic, and how: from the maps' entities"""
	uses = {}
	mapdir = os.path.join( dkres, "maps" )
	for f in sorted( os.listdir( mapdir ) ):
		if not f.endswith( ".bsp" ):
			continue
		data = open( os.path.join( mapdir, f ), "rb" ).read().decode( "latin-1" )
		for key, val in re.findall( r'"(cinematic_intro|cinematic|cinescript)"\s+"([^"]+)"', data ):
			uses.setdefault( val.lower(), [] ).append( ( f[:-4], key ) )
	return uses

# ---------------------------------------------------------------------------
# cameras

def cubic( c, t ):
	return ( ( c[0] * t + c[1] ) * t + c[2] ) * t + c[3]

def dcubic( c, t ):
	return ( 3 * c[0] * t + 2 * c[1] ) * t + c[2]

def write_camera( path, name, shot, src ):
	seq = shot["sequence"]
	n = seq["num_points"]
	segs = seq["segments"]
	lines = [ "// %s: a shot of Daikatana's cin/scripts/%s.script, converted by tools/cine/cine_convert.py" % ( name, src ),
			  "// (keys pass through their positions and angles at their times, at the velocities given; a key",
			  "// without them is smooth through its neighbours)",
			  "cameraPathDef {", "\tcamera_keys {", "\t\tname %s" % name ]
	if n == 0:
		return False
	nseg = max( 0, n - 1 )
	times = [ 0.0 ]
	for i in range( nseg ):
		times.append( times[-1] + segs[i]["time"] )
	pspl = seq["position"]["splines"]
	aspl = seq["angle"]["splines"]
	fov = {}
	fade = {}
	if shot.get( "have_start_fov" ):
		fov[0] = shot["start_fov"]
	for i in range( nseg ):
		s = segs[i]
		if s["have_start_fov"]:
			fov[i] = s["start_fov"]
		if s["have_end_fov"]:
			fov.setdefault( i + 1, s["end_fov"] )
		if s["have_start_color"]:
			fade[i] = [ x / 255.0 for x in s["start_color"] ]
		if s["have_end_color"]:
			fade.setdefault( i + 1, [ x / 255.0 for x in s["end_color"] ] )
	for i in range( n ):
		if i < nseg:
			ps, as_, t = pspl[i], aspl[i], 0.0
		else:
			ps, as_, t = pspl[nseg - 1], aspl[nseg - 1], segs[nseg - 1]["time"] if nseg else 0.0
		if nseg == 0:
			pos = seq["position"]["points"][0]["point"]
			ang = seq["angle"]["points"][0]["point"]
		else:
			pos = [ cubic( ps[a], t ) for a in "xyz" ]
			ang = [ cubic( as_[a], t ) for a in "xyz" ]
		key = "\t\tkey { time %g pos ( %s ) angles ( %s )" % ( round( times[i], 4 ), fmt( pos ), fmt( ang ) )
		if 0 < i:
			T = segs[i - 1]["time"]
			vin = [ dcubic( pspl[i - 1][a], T ) for a in "xyz" ]
			ain = [ dcubic( aspl[i - 1][a], T ) for a in "xyz" ]
		if i < nseg:
			vout = [ dcubic( pspl[i][a], 0 ) for a in "xyz" ]
			aout = [ dcubic( aspl[i][a], 0 ) for a in "xyz" ]
			key += " vel ( %s ) avel ( %s )" % ( fmt( vout ), fmt( aout ) )
			if 0 < i and ( max( abs( x - y ) for x, y in zip( vin, vout ) ) > 0.01 or max( abs( x - y ) for x, y in zip( ain, aout ) ) > 0.01 ):
				key += " velIn ( %s ) avelIn ( %s )" % ( fmt( vin ), fmt( ain ) )
		elif 0 < i:
			key += " velIn ( %s ) avelIn ( %s )" % ( fmt( vin ), fmt( ain ) )
		if i in fov:
			key += " fov %g" % round( fov[i], 2 )
		if i in fade:
			key += " fade ( %s )" % fmt( fade[i] )
		lines.append( key + " }" )
	lines += [ "\t}", "}", "" ]
	with open( path, "w" ) as fp:
		fp.write( "\n".join( lines ) )
	return True

# ---------------------------------------------------------------------------
# actors

def actor_model( dkres, classname, mapname ):
	"""its model's path (no extension), or None"""
	if classname in MONSTER_MODELS:
		base = MONSTER_MODELS[classname]
	elif classname in CINE_PREFIX:
		base = "models/cinematic/" + CINE_PREFIX[classname] + mapname[:4]
		if not os.path.exists( os.path.join( dkres, base + ".md3" ) ):
			# none for this map (Daikatana had none either): one of another's
			others = sorted( f for f in os.listdir( os.path.join( dkres, "models", "cinematic" ) )
							 if f.startswith( CINE_PREFIX[classname] ) and f.endswith( ".md3" ) )
			if others:
				base = "models/cinematic/" + others[0][:-4]
	else:
		return None
	return base if os.path.exists( os.path.join( dkres, base + ".md3" ) ) else None

def write_actor_def( fp, dkres, defname, model ):
	if isinstance( model, str ) and model.startswith( "model_" ):
		# a rigged monster, as it is, at Daikatana's speeds
		actor_entity_def( fp, defname, model, MONSTER_SPEEDS.get( defname[5:], ( None, None ) ) )
		return
	if isinstance( model, tuple ):
		# our character, with this map's cinematic animations
		char, tag, rig = model
		fp.write( "entityDef model_%s {\n\t\"inherit\"\t\"model_%s\"\n\t\"mesh\"\t\t\"models/rigged/%s_%s.iqm\"\n" % ( defname, char, char, tag ) )
		for name in sorted( rig["anims"] ):
			if " " in rig["anims"][name].get( "iqm_name", name ) or not name.strip():
				continue		# (Daikatana's leftovers, "copy of ...": a def's key can't name them)
			fp.write( "\t\"anim %s\"\t\"%s\"\n" % ( rig["anims"][name].get( "iqm_name", name ), rig["anims"][name].get( "iqm_name", name ) ) )
	else:
		m = MD3( os.path.join( dkres, model + ".md3" ) )
		fp.write( "entityDef model_%s {\n\t\"mesh\"\t\t\"%s.md3\"\n" % ( defname, model ) )
		for a in m.animations():
			if " " in a[0] or not a[0].strip():
				continue
			fp.write( "\t\"anim %s\"\t\"%s 10%s\"\n" % ( a[0], a[0], " loop" if a[0].startswith( "amb" ) else "" ) )
	fp.write( "}\n" )
	# our character at its own walk's and run's speeds; Daikatana's model at the defaults
	speeds = def_anim_speeds( os.path.join( "def", "char_%s.def" % model[0] ) ) if isinstance( model, tuple ) else ( None, None )
	actor_entity_def( fp, defname, "model_" + defname, speeds )

# ---------------------------------------------------------------------------
# the script

def sound_path( f ):
	f = f.replace( "\\", "/" )
	return f if f.lower().startswith( ( "sounds/", "data/" ) ) else "sounds/" + f

gaits = {}		# an actor's way of moving, from its last start_walking / start_running

def task_lines( task, dkvar, actors, var, owner ):
	"""a task of Daikatana's entity dkvar, as script lines, for its actor var
	(that of owner, the entity that spawned it)"""
	ty = task["type"]
	rig = actors[dkvar][2]
	if ty == "start_running":
		gaits[dkvar] = "runa"
		return [ "// start_running" ]
	if ty == "start_walking":
		gaits[dkvar] = "walka"
		return [ "// start_walking%s" % ( ( " (Daikatana's " + task["animation"] + ")" ) if task["animation"] else "" ) ]
	if rig and ty in ( "play_animation", "set_idle_animation" ):
		a = rig["anims"].get( task["animation"] )
		if a is None:
			return [ "// %s: %s (no such animation of %s's)" % ( ty, task["animation"], rig["character"] ) ]
		name = a.get( "iqm_name", task["animation"] )
		if ty == "set_idle_animation":
			return [ "%s.playCycle( ANIMCHANNEL_LEGS, \"%s\" );" % ( var, name ) ]
		move, turn, start = a.get( "move", [ 0, 0 ] ), a.get( "turn", 0 ), a.get( "start", [ 0, 0 ] )
		if math.hypot( start[0], start[1] ) > 2:
			# it starts away from where the character is (its rig plays it over
			# the origin: autorig --root-out): drawn there, as Daikatana's was
			return [ "cine_playFrom( %s, \"%s\", '%s 0', '%s 0', %g, %g );" % ( var, name, fmt( start ), fmt( move ), round( turn, 2 ),
																		 round( a["frames"] / float( a.get( "fps", 10 ) ), 3 ) ) ]
		if math.hypot( move[0], move[1] ) > 2 or abs( turn ) > 3:
			# it moved the character: in place now, the game moves it
			return [ "cine_playMove( %s, \"%s\", '%s 0', %g, %g );" % ( var, name, fmt( move ), round( turn, 2 ),
																		 round( a["frames"] / float( a.get( "fps", 10 ) ), 3 ) ) ]
		return [ "cine_play( %s, \"%s\" );" % ( var, name ) ]
	dest = "'%s'" % fmt( task["destination"] )
	yaw = round( task["direction"][1], 2 )
	if ty == "spawn_entity":
		return [ "%s = cine_enter( %s, \"%s\", %s, %g, \"%s\", \"%s\" );" % ( var, var, actors[dkvar][1], dest, yaw, var, dkvar ) ]
	if ty == "play_animation":
		return [ "cine_play( %s, \"%s\" );" % ( var, task["animation"] ) ]
	if ty == "set_idle_animation":
		return [ "cine_idle( %s, \"%s\" );" % ( var, task["animation"] ) ]
	if ty == "move_to":
		return [ "cine_move( %s, %s, \"%s\" );" % ( var, dest, gaits.get( dkvar, "walka" ) ) ]
	if ty == "move_and_turn":
		return [ "cine_move( %s, %s, \"%s\" );" % ( var, dest, gaits.get( dkvar, "walka" ) ), "cine_turn( %s, %g );" % ( var, yaw ) ]
	if ty == "turn":
		return [ "cine_turn( %s, %g );" % ( var, yaw ) ]
	if ty == "teleport":
		return [ "cine_place( %s, %s, %g );" % ( var, dest, yaw ) ]
	if ty == "trigger_brush_use":
		return [ "cine_use( \"%s\", %s );" % ( task["use_entity"], var ) ]
	if ty == "remove_entity":
		return [ "cine_exit( %s, \"%s\" );" % ( var, owner ) ]
	if ty == "clear_goals":
		return [ "%s.stopMove();" % var ]
	if ty == "none":
		return []
	return [ "// %s (not converted)" % ty ]

def actor_slots( data, actors ):
	"""Daikatana's entities -> our actors: an actor a character (a def), its
	entities one after another taking it, so it's one Hiro, one Toshiro in
	the whole cinematic; a second only for an entity that acts while another
	of the same character is still about (two ninjas fighting). An entity is
	about from its spawning's shot to its removal's (the end, without one);
	a shot that only removes it doesn't count, the next one entering takes
	the actor from it then."""
	end = len( data["shots"] )
	acts, removed, spawned = {}, {}, {}		# var -> shots it does something in; its removal's shot; its spawning's
	for si, shot in enumerate( data["shots"] ):
		for e in shot["entities"]:
			var = ident( e["uniqueid"] or e["name"] )
			types = set( t["type"] for t in e["tasks"] )
			if "spawn_entity" in types:
				spawned.setdefault( var, si )
			if "remove_entity" in types:
				removed[var] = si
			if types - { "remove_entity", "none" }:
				acts.setdefault( var, [] ).append( si )
	span = {}
	for var in actors:
		a = acts.get( var, [ 0 ] )
		r = removed.get( var )
		if r is None:
			last = end
		elif r in a:
			last = r
		else:
			last = max( a[-1], r - 1 )
		span[var] = [ a[0], last ]
	# one never spawned (Daikatana's intro has oka1 spawned, then osa1 acting
	# and removed) is the one of its character spawned last before it: its
	# actor, its removal that one's
	owners = dict( ( v, v ) for v in actors )
	for var in actors:
		if var in spawned or var not in acts:
			continue
		before = [ v for v in spawned if actors[v][1] == actors[var][1] and spawned[v] <= acts[var][0] ]
		if before:
			owners[var] = max( before, key = lambda v: spawned[v] )
			o = span[owners[var]]
			o[1] = max( o[1], span[var][1] )
	slots, taken = {}, {}		# taken: def -> [ ( slot, last shot ) ]
	for var in sorted( span, key = lambda v: ( span[v][0], v ) ):
		if owners[var] != var:
			continue
		d = actors[var][1]
		base = ident( re.sub( r"^cine_", "", d ) )
		have = taken.setdefault( d, [] )
		for i, ( slot, last ) in enumerate( have ):
			if last < span[var][0]:
				have[i] = ( slot, span[var][1] )
				break
		else:
			slot = base if not have else "%s_%d" % ( base, len( have ) + 1 )
			have.append( ( slot, span[var][1] ) )
		slots[var] = slot
	for var in actors:
		slots[var] = slots[owners[var]]
	return slots, owners

def write_script( path, name, data, src, mapname, cams, dkres, actorDefs ):
	ns = ident( name )
	gaits.clear()
	actors = {}		# var -> ( dk classname, def name, our character's cinematic animations or None )
	for shot in data["shots"]:
		for e in shot["entities"]:
			var = ident( e["uniqueid"] or e["name"] )
			if var in actors:
				continue
			model = actor_model( dkres, e["name"], mapname )
			rig = rigged( dkres, e["name"], model )
			mrig = monster_rig( e["name"], model, dkres )
			if mrig:
				defname = "cine_%s" % mrig[0][6:]
				actorDefs[defname] = mrig[0]
				rig = { "character": mrig[0][6:], "anims": dict( ( a, mrig[2].get( a, {} ) ) for a in mrig[1] ) }
			elif rig:
				defname = "cine_%s_%s" % ( rig[0], rig[1] )
				actorDefs[defname] = rig
				rig = rig[2]
			elif model:
				defname = "cine_%s_%s" % ( re.sub( r"^(cine|monster|c)_", "", e["name"] ), mapname[:4] )
				actorDefs[defname] = model
			else:
				defname = None
			actors[var] = ( e["name"], defname or "cine_missing", rig )

	slots, owners = actor_slots( data, actors )
	out = [ "// %s.script -- Daikatana's cinematic cin/scripts/%s.script, converted by" % ( name, src ),
			"// tools/cine/cine_convert.py. Its shots' cameras are cameras/%s_NN.camera." % name,
			"// To change it, copy this file (or a camera) to the repository's cine/script/",
			"// (cine/cameras/): yours takes its place.",
			"", "namespace %s {" % ns, "" ]
	for slot in sorted( set( slots.values() ) ):
		dks = sorted( v for v in slots if slots[v] == slot )
		cls, d, rig = actors[dks[0]]
		out.append( "entity\t%s;\t\t// %s%s: Daikatana's %s" % ( slot, cls, " (no model found)" if d == "cine_missing" else
												  ( " (our %s)" % rig["character"] if rig else "" ), ", ".join( dks ) ) )
	out += [ "float\tshot;\t\t// the shot playing: an actor's tasks of an earlier one stop", "float\tshotStart;", "" ]

	shotFuncs = []
	for si, shot in enumerate( data["shots"] ):
		num = si + 1
		# the actors' threads
		threads = []
		for e in shot["entities"]:
			var = ident( e["uniqueid"] or e["name"] )
			body = []
			# after a wait, the shot may have changed: then it's not this shot's
			# to do (Daikatana's tasks past a shot's end never ran: the intro's
			# shot 81 removes Hiro and Toshiro after its cut, and they talk on
			# to shot 96)
			guard = "if ( shot != %d ) { return; }" % num
			for task in e["tasks"]:
				lines = task_lines( task, var, actors, slots[var], owners[var] )
				if not lines:
					continue
				if task["time"] >= 0:
					body.append( "cine_until( shotStart + %g );" % round( task["time"], 3 ) )
					body.append( guard )
				elif body and body[-1].startswith( ( "cine_play", "cine_move", "cine_turn" ) ):
					body.append( guard )
				body += lines
			if not any( not l.startswith( ( "//", "if" ) ) for l in body ):
				continue
			fn = "%s_shot%d" % ( var, num )
			threads.append( fn )
			out.append( "void %s() {" % fn )
			out += [ "\t" + l for l in body ]
			out += [ "}", "" ]
		# the shot
		fn = "shot%d" % num
		shotFuncs.append( fn )
		out += [ "void %s() {" % fn, "\tentity cam;", "",
				 "\tcam = cine_camera( \"%s\" );" % cams[si] if cams[si] else "\tcam = $null_entity;",
				 "\tshot = %d;" % num, "\tshotStart = sys.getTime();" ]
		if cams[si]:
			out.append( "\tsys.setCamera( cam );" )
		for t in threads:
			out.append( "\tthread %s();" % t )
		at = 0.0
		for snd in sorted( shot["sounds"], key = lambda s: s["time"] ):
			if snd["time"] > at:
				out.append( "\tsys.wait( %g );" % round( snd["time"] - at, 3 ) )
				at = snd["time"]
			if snd["loop"]:
				out.append( "\tsys.startGlobalLoop( \"%s\" );" % sound_path( snd["file"] ) )
			else:
				out.append( "\tsys.startGlobalSound( \"%s\" );" % sound_path( snd["file"] ) )
		if cams[si]:
			out.append( "\tsys.waitFor( cam );" )
		else:
			out.append( "\tsys.wait( %g );" % round( max( 0, shot["total_time"] - at ), 3 ) )
		if any( s["loop"] for s in shot["sounds"] ):
			out.append( "\tsys.stopGlobalLoops();" )
		out += [ "}", "" ]

	# cine_firstShot n starts it at its nth shot (for looking at one; its
	# actors spawned before then are missing)
	out += [ "/*", "================", "%s::play" % ns, "================", "*/", "void play() {",
			 "\tfloat first;", "", "\tfirst = sys.strToFloat( sys.getcvar( \"cine_firstShot\" ) );", "\tcine_start();" ]
	out += [ "\tif ( first <= %d ) { %s(); }" % ( i + 1, f ) for i, f in enumerate( shotFuncs ) ]
	out += [ "\tcine_finish();" ]
	for slot in sorted( set( slots.values() ) ):
		out.append( "\tcine_remove( %s );" % slot )
	out += [ "}", "", "}", "" ]
	with open( path, "w" ) as fp:
		fp.write( "\n".join( out ) )

# ---------------------------------------------------------------------------

def main( argv ):
	if len( argv ) < 2:
		print( __doc__ )
		return 1
	dkres, outdir = argv[0], argv[1]
	names = [ n.lower() for n in argv[2:] ]
	srcdir = os.path.join( dkres, "cin", "scripts" )
	for d in ( "cameras", "script", "def", "maps" ):
		os.makedirs( os.path.join( outdir, d ), exist_ok = True )
	uses = map_cinematics( dkres )
	actorDefs = {}
	done = 0
	for f in sorted( os.listdir( srcdir ) ):
		name, ext = os.path.splitext( f )
		name = name.lower()
		if ext.lower() != ".script" or ( names and name not in names ):
			continue
		data = dkcine.read_script( open( os.path.join( srcdir, f ), "rb" ).read() )
		maps = uses.get( name, [] )
		mapname = maps[0][0] if maps else name.split( "_" )[0]
		cams = []
		for si, shot in enumerate( data["shots"] ):
			cname = "%s_%02d" % ( name, si + 1 )
			ok = write_camera( os.path.join( outdir, "cameras", cname + ".camera" ), cname, shot, name )
			cams.append( cname if ok else None )
		write_script( os.path.join( outdir, "script", name + ".script" ), name, data, name, mapname, cams, dkres, actorDefs )
		done += 1
		print( "  %s: %d shots%s" % ( name, len( data["shots"] ), ( ", from " + ", ".join( "%s (%s)" % m for m in maps ) ) if maps else ", no map starts it" ) )

	# each map's cinematics
	maps = {}
	for name, used in uses.items():
		if os.path.exists( os.path.join( outdir, "script", name + ".script" ) ):
			for m, key in used:
				maps.setdefault( m, set() ).add( name )
	for m, names in sorted( maps.items() ):
		with open( os.path.join( outdir, "maps", m + ".script" ), "w" ) as fp:
			fp.write( "// %s's cinematics, by tools/cine/cine_convert.py\n" % m )
			for name in sorted( names ):
				fp.write( "#include \"cine/%s.script\"\n" % name )

	path = os.path.join( outdir, "def", "cine_actors.def" )
	with open( path, "w" ) as fp:
		fp.write( "// the cinematics' actors: made by tools/cine/cine_convert.py from Daikatana's models\n\n" )
		for defname in sorted( actorDefs ):
			write_actor_def( fp, dkres, defname, actorDefs[defname] )
	print( "%d cinematics, %d actors" % ( done, len( actorDefs ) ) )
	return 0

if __name__ == "__main__":
	sys.exit( main( sys.argv[1:] ) )
