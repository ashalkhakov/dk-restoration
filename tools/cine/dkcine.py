#!/usr/bin/env python3
"""
Reads a Daikatana cinematic script (cin/scripts/*.script, written by the
in-game cinescriptor, gce.dll) and dumps it as JSON.

A script is a list of shots, played one after another. Each shot holds:
 - the camera's path: a string of points the camera's position goes through
   and a string of angles (pitch, yaw, roll) it turns through, one cubic per
   segment between two points and axis, with the segment's time in seconds
   and what the FOV, the game's timescale and the screen's fade colour do
   along it;
 - whether the camera looks along those angles or at an entity;
 - when the shot ends (the path's time, or when an entity is done) and the
   time it waits before and after the path;
 - sounds started at a time from the shot's start;
 - the actors (entities by classname and unique id) and their tasks: spawn,
   move, turn, play an animation, ... each at a time from the shot's start;
 - the FOV at the start of the shot and the sky to use.
Everything is little endian: 32 bit ints and floats, 1 byte bools and fixed
size, zero padded strings, no padding between the fields. The format is
described in full in dk-cinematic-format.md (the side session's notes).

	python3 tools/cine/dkcine.py <file.script> [--json out.json] [--summary]
(no --json: the JSON goes to stdout; --summary prints a few lines a shot
instead.) It fails if the file has bytes left over after the last shot.
"""
import json
import struct
import sys

LATEST_VERSION = 15		# what DK 1.2 writes; all the shipped scripts are this

# the task types, in the order of their enum (the number is what's stored)
TASK_TYPES = [
	"none",
	"move_to",				# walk/run to destination (animation: the moving animation to use, if any)
	"turn",					# face direction's yaw
	"move_and_turn",		# move to destination, then face direction's yaw
	"attribute_backup",		# save walk/run/yaw speeds
	"attribute_restore",	# put them back
	"attribute_run_speed",	# attribute_value
	"attribute_walk_speed",	# attribute_value
	"attribute_yaw_speed",	# attribute_value
	"wait",					# attribute_value seconds
	"teleport",				# put it at destination, facing direction (not queued)
	"start_running",
	"start_walking",		# (animation: the walking animation, if any)
	"trigger_brush_use",	# use the entity named use_entity
	"head_script",			# turn the head along headscript's angles (not queued)
	"play_animation",		# animation
	"set_idle_animation",	# animation
	"play_sound",			# sound for sound_duration seconds
	"spawn_entity",			# spawn the actor (its name is the classname) at destination, facing direction
	"remove_entity",
	"clear_goals",
]
CAMERA_TARGETS = [ "sequence", "entity" ]	# look along the angle splines, or at entity_camera_target
SHOT_ENDS = [ "sequence", "entity" ]		# end with the path's time, or when entity_shot_end is done
END_VELOCITIES = [ "default", "zero" ]		# the path's speed at its start and end: the computed one, or still
TT_HEAD_SCRIPT = 14

def short_float( x ):
	# the shortest decimal that reads back as the same 32 bit float
	if x != x or x in ( float( "inf" ), float( "-inf" ) ):
		return repr( x )
	packed = struct.pack( "<f", x )
	for digits in range( 6, 10 ):
		y = float( "%.*g" % ( digits, x ) )
		if struct.pack( "<f", y ) == packed:
			return y
	return x

def name_of( names, n ):
	return names[n] if 0 <= n < len( names ) else "unknown_%d" % n

class Reader:
	def __init__( self, data ):
		self.data = data
		self.pos = 0

	def take( self, n ):
		if self.pos + n > len( self.data ):
			raise ValueError( "file ends at %d, wanted %d bytes more at %d" % ( len( self.data ), n, self.pos ) )
		b = self.data[self.pos:self.pos + n]
		self.pos += n
		return b

	def int( self ):
		return struct.unpack( "<i", self.take( 4 ) )[0]

	def float( self ):
		return short_float( struct.unpack( "<f", self.take( 4 ) )[0] )

	def floats( self, n ):
		return [ short_float( v ) for v in struct.unpack( "<%df" % n, self.take( 4 * n ) ) ]

	def bool( self ):
		return self.take( 1 )[0] != 0

	def string( self, size ):
		# a fixed size buffer, cut at its first zero (what follows is old junk)
		return self.take( size ).split( b"\0", 1 )[0].decode( "latin-1" )

	def count( self, what, most = 100000 ):
		n = self.int()
		if n < 0 or n > most:
			raise ValueError( "bad %s count %d at %d" % ( what, n, self.pos - 4 ) )
		return n

def read_component( r ):
	# one string of points (positions, or angles in degrees) and the cubics through them:
	# value(t) = a t^3 + b t^2 + c t + d, t the seconds into the segment, for x, y and z
	n = r.count( "point" )
	points = []
	for i in range( n ):
		p = r.floats( 3 )
		vdir = r.floats( 3 )		# the direction of the path's velocity at the point (normalised)
		speed = r.float()			# and its size, units (or degrees) a second
		points.append( { "point": p, "velocity_dir": vdir, "speed": speed } )
	splines = []
	for i in range( n - 1 ):
		c = r.floats( 12 )
		splines.append( { "x": c[0:4], "y": c[4:8], "z": c[8:12] } )	# a, b, c, d
	return { "points": points, "splines": splines }

def read_segment( r, version ):
	# what happens along one segment of the camera's path
	s = { "time": r.float() }
	s["have_start_fov"] = r.bool()
	s["have_end_fov"] = r.bool()
	s["start_fov"] = r.float()
	s["end_fov"] = r.float()
	if version >= 11:
		s["have_start_timescale"] = r.bool()
		s["have_end_timescale"] = r.bool()
		s["start_timescale"] = r.float()
		s["end_timescale"] = r.float()
	s["have_start_color"] = r.bool()
	s["have_end_color"] = r.bool()
	s["start_color"] = r.floats( 4 )	# r g b a, 0 to 255
	s["end_color"] = r.floats( 4 )
	return s

def read_sequence( r, version ):
	n = r.int()
	if version < 6:
		# the old layout: position and angle data interleaved a point
		pos = { "points": [], "splines": [] }
		ang = { "points": [], "splines": [] }
		for i in range( n ):
			for comp in ( pos, ang ):
				comp["points"].append( { "point": r.floats( 3 ), "velocity_dir": r.floats( 3 ), "speed": r.float() } )
		segments = []
		for i in range( n - 1 ):
			segments.append( { "time": r.float() } )
			for comp in ( pos, ang ):
				c = r.floats( 12 )
				comp["splines"].append( { "x": c[0:4], "y": c[4:8], "z": c[8:12] } )
	else:
		pos = read_component( r )
		ang = read_component( r )
		if version < 9:
			segments = [ { "time": r.float() } for i in range( n - 1 ) ]
		else:
			segments = [ read_segment( r, version ) for i in range( r.count( "segment" ) ) ]
	seq = {
		"num_points": n,
		"position": pos,
		"angle": ang,
		"segments": segments,
	}
	seq["velocity_start"] = name_of( END_VELOCITIES, r.int() )
	seq["velocity_end"] = name_of( END_VELOCITIES, r.int() )
	seq["total_time"] = r.float()
	return seq

def read_sound( r, version ):
	s = { "file": r.string( 64 ) }
	s["loop"] = r.bool() if version >= 11 else False
	s["channel"] = r.int() if version >= 15 else 2		# the mp3 channel (wavs ignore it)
	s["time"] = r.float()
	return s

def read_task( r, version ):
	t = { "type": name_of( TASK_TYPES, r.int() ) }
	tnum = TASK_TYPES.index( t["type"] ) if t["type"] in TASK_TYPES else -1
	t["time"] = r.float()			# seconds from the shot's start (-1: straight after the previous one)
	t["destination"] = r.floats( 3 )
	t["direction"] = r.floats( 3 )	# angles: pitch, yaw, roll
	if version < 4:
		t["destination"][2] -= 22	# the old ones were at the camera's height
	t["attribute_value"] = r.float() if version >= 5 else 0.0
	if version >= 7 and tnum == TT_HEAD_SCRIPT:
		t["headscript"] = read_component( r )	# angles 0.2 seconds apart, relative to the body
	if version >= 8:
		t["animation"] = r.string( 16 )
		t["use_entity"] = r.string( 16 )
	if version >= 12:
		t["sound"] = r.string( 16 )
	if version >= 13:
		t["sound_duration"] = r.float()
	if version >= 15:
		t["uniqueid"] = r.string( 32 )
	return t

def read_entity( r, version ):
	e = { "name": r.string( 32 ) if version >= 3 else r.string( 16 ) }	# a classname (or "player")
	if version >= 15:
		e["uniqueid"] = r.string( 32 )		# which one of them: the spawned actor's script name
	e["tasks"] = [ read_task( r, version ) for i in range( r.count( "task" ) ) ]
	return e

def read_shot( r, version ):
	s = { "sequence": read_sequence( r, version ) }
	s["camera_target"] = name_of( CAMERA_TARGETS, r.int() )
	s["end"] = name_of( SHOT_ENDS, r.int() )
	s["extra_time_start"] = r.float()
	s["extra_time_end"] = r.float()
	s["sounds"] = [ read_sound( r, version ) for i in range( r.count( "sound" ) ) ] if version >= 1 else []
	s["entities"] = [ read_entity( r, version ) for i in range( r.count( "entity" ) ) ] if version >= 2 else []
	if version >= 3:
		s["entity_camera_target"] = r.string( 16 )
		s["entity_shot_end"] = r.string( 16 )
	if version >= 10:
		s["have_start_fov"] = r.bool()
		s["start_fov"] = r.float()
	if version >= 14:
		s["sky"] = r.int()
	s["total_time"] = short_float( s["extra_time_start"] + s["sequence"]["total_time"] + s["extra_time_end"] )
	return s

def read_script( data ):
	r = Reader( data )
	version = r.int()
	if version < 0 or version > LATEST_VERSION:
		raise ValueError( "unknown version %d" % version )
	shots = [ read_shot( r, version ) for i in range( r.count( "shot" ) ) ]
	if r.pos != len( data ):
		raise ValueError( "%d bytes left over at %d" % ( len( data ) - r.pos, r.pos ) )
	return { "version": version, "shots": shots }

def summary( script, out ):
	out.write( "version %d, %d shots\n" % ( script["version"], len( script["shots"] ) ) )
	for i, s in enumerate( script["shots"] ):
		seq = s["sequence"]
		out.write( "shot %d: %g s (%g + %g path + %g), %d points, camera %s%s, ends by %s%s, sky %s\n" % (
			i, s["total_time"], s["extra_time_start"], seq["total_time"], s["extra_time_end"], seq["num_points"],
			s["camera_target"], " " + s.get( "entity_camera_target", "" ) if s["camera_target"] == "entity" else "",
			s["end"], " " + s.get( "entity_shot_end", "" ) if s["end"] == "entity" else "", s.get( "sky" ) ) )
		for snd in s["sounds"]:
			out.write( "\tsound %g: %s%s\n" % ( snd["time"], snd["file"], " (loop)" if snd["loop"] else "" ) )
		for e in s["entities"]:
			tasks = []
			for t in e["tasks"]:
				# the editor leaves the other buffers filled (with the classname, cut): show the one the type uses
				arg = ""
				if t["type"] in ( "move_to", "start_walking", "play_animation", "set_idle_animation" ):
					arg = t.get( "animation", "" )
				elif t["type"] == "play_sound":
					arg = "%s %gs" % ( t.get( "sound", "" ), t.get( "sound_duration", 0 ) )
				elif t["type"] == "trigger_brush_use":
					arg = t.get( "use_entity", "" )
				elif t["type"] in ( "wait", "attribute_run_speed", "attribute_walk_speed", "attribute_yaw_speed" ):
					arg = "%g" % t["attribute_value"]
				tasks.append( "%g %s%s" % ( t["time"], t["type"], " " + arg if arg else "" ) )
			out.write( "\t%s/%s: %s\n" % ( e["name"], e.get( "uniqueid", "" ), ", ".join( tasks ) ) )

def main( argv ):
	args = argv[1:]
	jsonPath = None
	brief = False
	if "--json" in args:
		k = args.index( "--json" )
		jsonPath = args[k + 1]
		del args[k:k + 2]
	if "--summary" in args:
		args.remove( "--summary" )
		brief = True
	if len( args ) != 1:
		sys.stderr.write( __doc__ )
		return 2
	with open( args[0], "rb" ) as f:
		data = f.read()
	try:
		script = read_script( data )
	except ValueError as err:
		sys.stderr.write( "%s: %s\n" % ( args[0], err ) )
		return 1
	if jsonPath:
		with open( jsonPath, "w" ) as f:
			json.dump( script, f, indent = "\t" )
			f.write( "\n" )
	if brief:
		summary( script, sys.stdout )
	elif not jsonPath:
		json.dump( script, sys.stdout, indent = "\t" )
		sys.stdout.write( "\n" )
	return 0

if __name__ == "__main__":
	sys.exit( main( sys.argv ) )
