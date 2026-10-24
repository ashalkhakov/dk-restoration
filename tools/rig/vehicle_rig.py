#!/usr/bin/env python3
"""
A Daikatana vehicle (a still md3: the dump truck, d1_deathtruck) as a
skeletal IQM a Doom 3 vehicle drives (idAFEntity_VehicleSixWheels, the
game's g_vehicle.c): its wheels joints of their own, the rest the body's.

How:
 1. The wheels: the mesh's pieces (triangles joined, vertexes in one place
    one) that sit on the ground (their bottom the model's) and are round
    from the side (as long as they're high, from their middle up to where a
    fender hides them). Each is a joint at its middle, on "origin".
 2. Named by where they are: front (toward --front: the cab), middle and
    rear, left (+y) and right; the front ones on a suspension arm each
    (wheel_fl_arm: no vertexes, the AF's body between the wheel and the
    body, the steering hinge's), inboard of the wheel.
 3. "eyes": where the driver sits (--eyes), the view from the cab; --sounds
    start,idle,stop: the engine's (getting in, while he's in, getting out);
    --parts cab,bed_left,...: joints with no vertexes for the AF's bodies
    held to the body (a trace model is convex: a dump truck's bed is walls);
    --full-wheels: a wheel modelled only up to its fender a whole one's copy;
    --wheel-scale 0.66: the wheels smaller, their axles lowered to the ground.
 4. <out base>.iqm (one frame, "idle"), and def/vehicle_<name>.def's model
    def: the mesh, the wheels' radius and joints, the AF (af/vehicle_<name>.af,
    written by hand: the authority).

	python3 tools/rig/vehicle_rig.py --name deathtruck --front -x --eyes -64,10,44 dkres/models/e1/d1_deathtruck.md3 dkres/models/rigged/deathtruck
"""
import os
import sys

sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
from md3 import MD3, Surface  # noqa: E402
import autorig as A  # noqa: E402

def pieces( s ):
	"""a surface's pieces: [ [ vertex ] ]"""
	par = list( range( s.numVerts ) )
	def find( a ):
		while par[a] != a:
			par[a] = par[par[a]]
			a = par[a]
		return a
	for t in s.triangles:
		par[find( t[0] )] = find( t[1] )
		par[find( t[1] )] = find( t[2] )
	place = {}
	for v in range( s.numVerts ):
		k = tuple( round( c, 2 ) for c in s.frames[0][v] )
		if k in place:
			par[find( v )] = find( place[k] )
		else:
			place[k] = v
	out = {}
	for v in range( s.numVerts ):
		out.setdefault( find( v ), [] ).append( v )
	return list( out.values() )

def full_wheels( m, wheels, radius ):
	"""--full-wheels: a wheel the model has only up to where a fender hides it
	(the dump truck's rear ones), which shows as it turns, a copy of a whole one
	on its side instead (the front ones, as big): the surfaces with the part
	wheels' triangles out, and the copies as surfaces of their own. Returns
	( surfaces, [ ( its wheel's index, its surface's index ) ] )"""
	whole = [ w for w in wheels if max( m.surfaces[w[0]].frames[0][v][2] for v in w[1] )
			  - min( m.surfaces[w[0]].frames[0][v][2] for v in w[1] ) >= 1.8 * w[3] ]
	part = [ i for i, w in enumerate( wheels ) if w not in whole ]
	if not whole or not part:
		return m.surfaces, []
	gone = {}		# surface -> its part wheels' vertexes
	for i in part:
		gone.setdefault( wheels[i][0], set() ).update( wheels[i][1] )
	out = []
	for si, s in enumerate( m.surfaces ):
		t = Surface()
		t.name, t.shader, t.numVerts, t.st, t.frames = s.name, s.shader, s.numVerts, s.st, s.frames
		t.triangles = [ tri for tri in s.triangles if not ( set( tri ) & gone.get( si, set() ) ) ]
		out.append( t )
	added = []
	for i in part:
		si, vs, centre, r = wheels[i]
		tsi, tvs, tcentre, tr = min( whole, key = lambda w: ( ( w[2][1] > 0 ) != ( centre[1] > 0 ), abs( w[2][0] - centre[0] ) ) )
		src = m.surfaces[tsi]
		idx = { v: k for k, v in enumerate( sorted( tvs ) ) }
		d = [ centre[k] - tcentre[k] for k in range( 3 ) ]
		c = Surface()
		c.name, c.shader, c.numVerts = "%s_wheel%d" % ( src.name, i ), src.shader, len( idx )
		c.st = [ src.st[v] for v in sorted( tvs ) ]
		c.frames = [ [ tuple( src.frames[0][v][k] + d[k] for k in range( 3 ) ) for v in sorted( tvs ) ] ]
		c.triangles = [ tuple( idx[v] for v in tri ) for tri in src.triangles if tri[0] in idx and tri[1] in idx and tri[2] in idx ]
		out.append( c )
		added.append( ( i, len( out ) - 1 ) )
	return out, added

def main( md3Path, outBase, name, front, eyes, sounds = (), parts = (), fullWheels = False, wheelScale = 1.0 ):
	m = MD3( md3Path )
	ground = min( p[2] for s in m.surfaces for p in s.frames[0] )
	fx = -1.0 if front == "-x" else 1.0

	# 1. the wheels
	wheels = []		# ( surface index, vertexes, centre, radius )
	for si, s in enumerate( m.surfaces ):
		for vs in pieces( s ):
			P = [ s.frames[0][v] for v in vs ]
			lo = [ min( p[k] for p in P ) for k in range( 3 ) ]
			hi = [ max( p[k] for p in P ) for k in range( 3 ) ]
			radius = ( hi[0] - lo[0] ) * 0.5
			if lo[2] - ground > 1.0 or radius < 6.0 or hi[1] - lo[1] > radius:
				continue
			if hi[2] - lo[2] < radius * 1.2:
				continue	# (round from the side: at least up to past its middle)
			centre = ( ( lo[0] + hi[0] ) * 0.5, ( lo[1] + hi[1] ) * 0.5, ground + radius )
			wheels.append( ( si, vs, centre, radius ) )
	if len( wheels ) not in ( 4, 6 ):
		sys.exit( "%s: %d wheels found, a vehicle has 4 or 6" % ( md3Path, len( wheels ) ) )
	# --wheel-scale: smaller (or bigger) about their middles, the axles moved
	# so they're still on the ground (a delivery truck's, not a dump truck's)
	moved = {}		# old centre -> ( new centre, scale )
	for k, ( si, vs, centre, r ) in enumerate( wheels ):
		nc = ( centre[0], centre[1], ground + r * wheelScale )
		moved[centre] = ( nc, wheelScale )
		wheels[k] = ( si, vs, centre, r )

	# 2. their names, front to back
	axles = sorted( set( round( w[2][0] ) for w in wheels ), key = lambda x: x * fx, reverse = True )
	rows = [ "front", "middle", "rear" ] if len( axles ) == 3 else [ "front", "rear" ]
	joints = [ { "name": "origin", "parent": None, "parentIndex": -1, "zone": None, "pos": ( 0.0, 0.0, 0.0 ) } ]
	owner = {}		# ( surface, vertex ) -> joint
	radius = 0.0
	keys = []
	wheels.sort( key = lambda w: ( -w[2][0] * fx, -w[2][1] ) )
	wheelNames = []
	for si, vs, centre, r in wheels:
		row = rows[axles.index( round( centre[0] ) )]
		side = "left" if centre[1] * fx > 0 else "right"		# (facing +x, +y is the left; facing -x, the right)
		jname = "wheel_%s%s" % ( row[0], side[0] )
		wheelNames.append( jname )
		joints.append( { "name": jname, "parent": "origin", "parentIndex": 0, "zone": None, "pos": moved[centre][0],
						 "wheelFrom": centre } )
		for v in vs:
			owner[( si, v )] = len( joints ) - 1
		keys.append( ( "wheelJoint%s%s" % ( row.capitalize(), side.capitalize() ), jname ) )
		keys.append( ( "wheelBody%s%s" % ( row.capitalize(), side.capitalize() ), jname ) )	# (the AF's bodies are named so)
		if row == "front":
			keys.append( ( "steeringHinge%s%s" % ( row.capitalize(), side.capitalize() ), "steering_%s%s" % ( row[0], side[0] ) ) )
		radius = max( radius, r * wheelScale )
		if row == "front":
			arm = ( centre[0], centre[1] * 0.45, moved[centre][0][2] )		# its pivot, inboard
			joints.append( { "name": jname + "_arm", "parent": "origin", "parentIndex": 0, "zone": None, "pos": arm } )
		print( "  %s at %s, radius %.1f, %d vertexes" % ( jname, tuple( round( c, 1 ) for c in moved[centre][0] ), r * wheelScale, len( vs ) ) )

	# 3. the driver's view, and the body's other parts (--parts: the AF's
	# bodies held to it, a cab, a bed's walls: no vertexes of their own)
	joints.append( { "name": "eyes", "parent": "origin", "parentIndex": 0, "zone": None, "pos": eyes } )
	for part in parts:
		joints.append( { "name": part, "parent": "origin", "parentIndex": 0, "zone": None, "pos": ( 0.0, 0.0, 0.0 ) } )

	# 4. the IQM (with whole wheels for part ones, --full-wheels)
	surfaces, added = full_wheels( m, wheels, radius ) if fullWheels else ( m.surfaces, [] )
	copies = {}		# a copy's vertex -> the middle it's about (its wheel's)
	for i, si in added:
		jname = wheelNames[i]
		for v in range( surfaces[si].numVerts ):
			owner[( si, v )] = next( k for k, j in enumerate( joints ) if j["name"] == jname )
			copies[( si, v )] = wheels[i][2]
		print( "  %s a whole wheel's copy (it's modelled only up to its fender)" % jname )
	body, verts, rest, weights = [], [], [], []
	for si, s in enumerate( surfaces ):
		body.append( s )
		for v in range( s.numVerts ):
			verts.append( ( len( body ) - 1, v ) )
			j = owner.get( ( si, v ), 0 )
			p = tuple( s.frames[0][v] )
			if "wheelFrom" in joints[j]:
				# (a wheel's: scaled about its middle, the middle moved)
				fc, tc = joints[j]["wheelFrom"], joints[j]["pos"]
				if ( si, v ) in copies:
					fc = copies[( si, v )]
				p = tuple( tc[k] + ( p[k] - fc[k] ) * wheelScale for k in range( 3 ) )
			rest.append( p )
			weights.append( ( j, j, 1.0 ) )
	class Still:
		numFrames = 1
		def animations( self ):
			return [ ( "idle", 0, 1 ) ]
	motion = { j: { 0: ( A.IDENT, ( 0.0, 0.0, 0.0 ) ) } for j in range( len( joints ) ) }
	A.write_iqm( Still(), body, verts, rest, joints, motion, weights, outBase )

	lines = [ "// made by tools/rig/vehicle_rig.py from %s" % A.gamePath( md3Path ),
			  "entityDef model_vehicle_%s {" % name,
			  "\t\"mesh\"\t\t\t\t\"%s.iqm\"" % A.meshPath( outBase ),
			  "\t\"anim idle\"\t\t\t\"idle\"",
			  "\t\"ragdoll\"\t\t\t\"vehicle_%s\"\t// af/vehicle_%s.af, its articulated figure" % ( name, name ),
			  "\t\"wheel_joints\"\t\t\"%s\"\t// turned by the cgame as they go" % " ".join( j["name"] for j in joints if j["name"].startswith( "wheel_" ) and not j["name"].endswith( "_arm" ) ),
			  "\t\"wheel_radius\"\t\t\"%.1f\"" % radius,
			  "}", "",
			  "// the vehicle (g_vehicle.c, Doom 3's idAFEntity_VehicleSixWheels): its",
			  "// AF af/vehicle_%s.af, written by hand" % name,
			  "entityDef vehicle_%s {" % name,
			  "\t\"spawnclass\"\t\t\"vehicle\"",
			  "\t\"model\"\t\t\t\t\"model_vehicle_%s\"" % name,
			  "\t\"eyesJoint\"\t\t\t\"eyes\"",
			  "\t\"wheelRadius\"\t\t\"%.1f\"" % radius ]
	lines += [ "\t\"%s\"\t\"%s\"" % kv for kv in keys ]
	for key, snd in zip( ( "snd_start", "snd_idle", "snd_stop" ), sounds ):
		if snd:
			lines.append( "\t\"%s\"\t\t\"%s\"" % ( key, snd ) )
	lines += [ "}", "" ]
	os.makedirs( os.path.join( A.STAGE or ".", "def" ), exist_ok = True )
	defPath = os.path.join( A.STAGE or ".", "def", "vehicle_%s.def" % name )
	with open( defPath, "w" ) as fp:
		fp.write( "\n".join( lines ) )
	print( "  wrote %s" % defPath )

if __name__ == "__main__":
	args = sys.argv[1:]
	opts = { "--name": None, "--front": "+x", "--eyes": "0,0,40", "--sounds": "", "--parts": "" }
	opts["--wheel-scale"] = "1"
	fullWheels = "--full-wheels" in args
	if fullWheels:
		args.remove( "--full-wheels" )
	for o in list( opts ):
		if o in args:
			i = args.index( o )
			opts[o] = args[i + 1]
			args = args[:i] + args[i + 2:]
	if len( args ) != 2 or not opts["--name"]:
		print( __doc__ )
		sys.exit( 1 )
	main( args[0], args[1], opts["--name"], opts["--front"], tuple( float( c ) for c in opts["--eyes"].split( "," ) ),
		  opts["--sounds"].split( "," ) if opts["--sounds"] else (), opts["--parts"].split( "," ) if opts["--parts"] else (), fullWheels,
		  float( opts["--wheel-scale"] ) )
