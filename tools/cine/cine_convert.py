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
}

def rigged( dkres, classname, model ):
	"""our character's cinematic animations for that model: ( character, tag,
	the retargeting's JSON ), or None"""
	if classname not in RIGGED or not model:
		return None
	char, prefix = RIGGED[classname]
	tag = os.path.basename( model )[len( prefix ):]
	path = os.path.join( dkres, "models", "rigged", "%s_%s.json" % ( char, tag ) )
	if not os.path.exists( path ):
		return None
	return ( char, tag, json.load( open( path ) ) )

def fmt( v ):
	return " ".join( "%g" % round( x, 4 ) for x in v )

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
	if isinstance( model, tuple ):
		# our character, with this map's cinematic animations
		char, tag, rig = model
		fp.write( "entityDef model_%s {\n\t\"inherit\"\t\"model_%s\"\n\t\"mesh\"\t\t\"models/rigged/%s_%s.iqm\"\n" % ( defname, char, char, tag ) )
		for name in sorted( rig["anims"] ):
			fp.write( "\t\"anim %s\"\t\"%s\"\n" % ( rig["anims"][name].get( "iqm_name", name ), rig["anims"][name].get( "iqm_name", name ) ) )
	else:
		m = MD3( os.path.join( dkres, model + ".md3" ) )
		fp.write( "entityDef model_%s {\n\t\"mesh\"\t\t\"%s.md3\"\n" % ( defname, model ) )
		for a in m.animations():
			fp.write( "\t\"anim %s\"\t\"%s 10%s\"\n" % ( a[0], a[0], " loop" if a[0].startswith( "amb" ) else "" ) )
	fp.write( "}\nentityDef %s {\n\t\"spawnclass\"\t\"monster\"\n\t\"model\"\t\t\"model_%s\"\n"
			  "\t\"scriptobject\"\t\"cine_actor\"\n\t\"health\"\t\"100000\"\n\t\"skill_scale\"\t\"0\"\n"
			  "\t\"run_speed\"\t\"220\"\n\t\"walk_speed\"\t\"90\"\n\t\"turn_rate\"\t\"360\"\n\t\"fov\"\t\t\"360\"\n}\n" % ( defname, defname ) )

# ---------------------------------------------------------------------------
# the script

def sound_path( f ):
	f = f.replace( "\\", "/" )
	return f if f.lower().startswith( ( "sounds/", "data/" ) ) else "sounds/" + f

def task_lines( task, var, actors ):
	"""a task, as script lines"""
	ty = task["type"]
	rig = actors[var][2]
	if rig and ty in ( "play_animation", "set_idle_animation" ):
		a = rig["anims"].get( task["animation"] )
		if not a:
			return [ "// %s: %s (no such animation of %s's)" % ( ty, task["animation"], rig["character"] ) ]
		name = a.get( "iqm_name", task["animation"] )
		if ty == "set_idle_animation":
			return [ "%s.playCycle( ANIMCHANNEL_LEGS, \"%s\" );" % ( var, name ) ]
		move, turn = a.get( "move", [ 0, 0 ] ), a.get( "turn", 0 )
		if math.hypot( move[0], move[1] ) > 2 or abs( turn ) > 3:
			# it moved the character: in place now, the game moves it
			return [ "cine_playMove( %s, \"%s\", '%s 0', %g, %g );" % ( var, name, fmt( move ), round( turn, 2 ),
																		 round( a["frames"] / float( a.get( "fps", 10 ) ), 3 ) ) ]
		return [ "cine_play( %s, \"%s\" );" % ( var, name ) ]
	dest = "'%s'" % fmt( task["destination"] )
	yaw = round( task["direction"][1], 2 )
	if ty == "spawn_entity":
		return [ "%s = cine_spawn( \"%s\", %s, %g, \"%s\" );" % ( var, actors[var][1], dest, yaw, var ) ]
	if ty == "play_animation":
		return [ "cine_play( %s, \"%s\" );" % ( var, task["animation"] ) ]
	if ty == "set_idle_animation":
		return [ "%s.playCycle( ANIMCHANNEL_LEGS, \"%s\" );" % ( var, task["animation"] ) ]
	if ty == "move_to":
		return [ "cine_move( %s, %s );" % ( var, dest ) ]
	if ty == "move_and_turn":
		return [ "cine_move( %s, %s );" % ( var, dest ), "cine_turn( %s, %g );" % ( var, yaw ) ]
	if ty == "turn":
		return [ "cine_turn( %s, %g );" % ( var, yaw ) ]
	if ty == "teleport":
		return [ "%s.setOrigin( %s );" % ( var, dest ), "%s.setAngles( '0 %g 0' );" % ( var, yaw ) ]
	if ty == "trigger_brush_use":
		return [ "cine_use( \"%s\", %s );" % ( task["use_entity"], var ) ]
	if ty == "remove_entity":
		return [ "%s.remove();" % var ]
	if ty == "clear_goals":
		return [ "%s.stopMove();" % var ]
	if ty in ( "start_running", "start_walking" ):
		return [ "// %s%s" % ( ty, ( " (" + task["animation"] + ")" ) if task["animation"] else "" ) ]
	if ty == "none":
		return []
	return [ "// %s (not converted)" % ty ]

def write_script( path, name, data, src, mapname, cams, dkres, actorDefs ):
	ns = ident( name )
	actors = {}		# var -> ( dk classname, def name, our character's cinematic animations or None )
	for shot in data["shots"]:
		for e in shot["entities"]:
			var = ident( e["uniqueid"] or e["name"] )
			if var in actors:
				continue
			model = actor_model( dkres, e["name"], mapname )
			rig = rigged( dkres, e["name"], model )
			if rig:
				defname = "cine_%s_%s" % ( rig[0], rig[1] )
				actorDefs[defname] = rig
				rig = rig[2]
			elif model:
				defname = "cine_%s_%s" % ( re.sub( r"^(cine|monster|c)_", "", e["name"] ), mapname[:4] )
				actorDefs[defname] = model
			else:
				defname = None
			actors[var] = ( e["name"], defname or "cine_missing", rig )

	out = [ "// %s.script -- Daikatana's cinematic cin/scripts/%s.script, converted by" % ( name, src ),
			"// tools/cine/cine_convert.py. Its shots' cameras are cameras/%s_NN.camera." % name,
			"// To change it, copy this file (or a camera) to the repository's cine/script/",
			"// (cine/cameras/): yours takes its place.",
			"", "namespace %s {" % ns, "" ]
	for var, ( cls, d, rig ) in sorted( actors.items() ):
		out.append( "entity\t%s;\t\t// %s%s" % ( var, cls, " (no model found)" if d == "cine_missing" else
												  ( " (our %s)" % rig["character"] if rig else "" ) ) )
	out += [ "float\tshot;\t\t// the shot playing: an actor's tasks of an earlier one stop", "float\tshotStart;", "" ]

	shotFuncs = []
	for si, shot in enumerate( data["shots"] ):
		num = si + 1
		# the actors' threads
		threads = []
		for e in shot["entities"]:
			var = ident( e["uniqueid"] or e["name"] )
			body = []
			for task in e["tasks"]:
				lines = task_lines( task, var, actors )
				if not lines:
					continue
				# after a wait, the shot may have changed: then it's not this shot's to do
				if task["time"] >= 0:
					body.append( "cine_until( shotStart + %g );" % round( task["time"], 3 ) )
					body.append( "if ( shot != %d ) { return; }" % num )
				elif body and body[-1].startswith( ( "cine_play", "cine_move", "cine_turn" ) ):
					body.append( "if ( shot != %d ) { return; }" % num )
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

	out += [ "/*", "================", "%s::play" % ns, "================", "*/", "void play() {", "\tcine_begin();" ]
	out += [ "\t%s();" % f for f in shotFuncs ]
	out += [ "\tcine_end();" ]
	for var in sorted( actors ):
		out.append( "\tif ( %s != $null_entity ) { %s.remove(); }" % ( var, var ) )
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
	for d in ( "cameras", "script", "def" ):
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

	path = os.path.join( outdir, "def", "cine_actors.def" )
	with open( path, "w" ) as fp:
		fp.write( "// the cinematics' actors: made by tools/cine/cine_convert.py from Daikatana's models\n\n" )
		for defname in sorted( actorDefs ):
			write_actor_def( fp, dkres, defname, actorDefs[defname] )
	print( "%d cinematics, %d actors" % ( done, len( actorDefs ) ) )
	return 0

if __name__ == "__main__":
	sys.exit( main( sys.argv[1:] ) )
