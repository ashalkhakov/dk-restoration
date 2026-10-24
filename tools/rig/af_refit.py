#!/usr/bin/env python3
"""
A character's ragdoll (af/<name>.af) refitted to its installed rig: each
body an oriented box about its bone's vertexes, everything else in the file
kept as it is (its joints, "mod", the constraints and their limits: the AF is
the authority, edited by hand: Toshiro's "mod both").

autorig's ragdoll_af boxes the torso and the head along the model's axes by
the vertexes their bones carry, and makes a limb a bone shape between its
joints; on Toshiro (his right elbow's joint out at his shoulder, his neck's
bone carrying his upper chest) the bodies came out small, off and stuck out.
Here each body is the box about its vertexes along their own axes (their
principal ones, the longest first), turned by the body's "angles":
	- the waist (the pelvis, no vertex of its own): the torso between the
	  hips' joint and the waist's, no arm's or leg's vertexes;
	- the chest: the waist's, the chest's and the neck's bones;
	- the head: its own bone's;
	- an upper arm or a thigh its bone's; a forearm with its hand's, a shin
	  with its ankle's.
A vertex counts for the bone it's on; an extra bone's (a robe's, a point's)
and a prop's for none: the body, not its clothes. "mod both" keeps each joint
where it is on its body, so a body needn't lie between its joints.

	python3 tools/rig/af_refit.py model_toshiro

writes out/rig/af/<name>.af, for the user to validate (./dk viewer shows it
beside the kept one) and copy over.
"""
import math
import os
import re
import sys

sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
import rigcheck as rc
import autorig as ar

ROOT = os.path.normpath( os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), "..", ".." ) )
TEMPLATE = ( "origin", "Body", "Hips", "Lupleg", "Lloleg", "Lankle_r", "Rupleg", "Rloleg", "Rankle_r", "Waist", "Chest",
			 "Loneck", "Head", "Luparm", "Lloarm", "Lhand", "Ruparm", "Rloarm", "Rhand" )
# each body's bones, by the body's name (autorig's ragdoll_af names them so)
BONES = { "chest": ( "Waist", "Chest", "Loneck" ), "head": ( "Head", ) }
for s_ in "LR":
	BONES[s_ + "uparm"] = ( s_ + "uparm", )
	BONES[s_ + "loarm"] = ( s_ + "loarm", s_ + "hand" )
	BONES[s_ + "upleg"] = ( s_ + "upleg", )
	BONES[s_ + "loleg"] = ( s_ + "loleg", s_ + "ankle_r" )

def cross( a, b ):
	return ( a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0] )

def obb( ps ):
	"""the box about the points along their principal axes: its centre, its
	half sizes and its axes (forward, left, up: right-handed, the longest
	first)"""
	c = [ sum( p[k] for p in ps ) / len( ps ) for k in range( 3 ) ]
	cov = [ [ sum( ( p[r] - c[r] ) * ( p[s] - c[s] ) for p in ps ) for s in range( 3 ) ] for r in range( 3 ) ]
	vals, vecs = ar.eigen3( cov )
	order = sorted( range( 3 ), key = lambda k: -vals[k] )
	f, l = vecs[order[0]], vecs[order[1]]
	u = cross( f, l )
	axes = ( f, l, u )
	lo, hi = [], []
	for a in axes:
		ts = [ sum( ( p[k] - c[k] ) * a[k] for k in range( 3 ) ) for p in ps ]
		lo.append( min( ts ) )
		hi.append( max( ts ) )
	centre = [ c[k] + sum( 0.5 * ( lo[i] + hi[i] ) * axes[i][k] for i in range( 3 ) ) for k in range( 3 ) ]
	half = [ max( 1.0, 0.5 * ( hi[i] - lo[i] ) ) for i in range( 3 ) ]
	return centre, half, axes

def angles_of( axes ):
	"""pitch, yaw, roll whose AnglesToAxis (Quake's: forward, left, up) are
	the axes"""
	f, l, u = axes
	pitch = math.degrees( math.asin( max( -1.0, min( 1.0, -f[2] ) ) ) )
	yaw = math.degrees( math.atan2( f[1], f[0] ) )
	roll = math.degrees( math.atan2( l[2], u[2] ) )
	return pitch, yaw, roll

def axes_of( angles ):
	"""Quake's AnglesToAxis: forward, left, up"""
	p, y, r = [ math.radians( a ) for a in angles ]
	sp, cp, sy, cy, sr, cr = math.sin( p ), math.cos( p ), math.sin( y ), math.cos( y ), math.sin( r ), math.cos( r )
	f = ( cp * cy, cp * sy, -sp )
	right = ( -sr * sp * cy + cr * sy, -sr * sp * sy - cr * cy, -sr * cp )
	u = ( cr * sp * cy + sr * sy, cr * sp * sy - sr * cy, cr * cp )
	return f, tuple( -x for x in right ), u

def main( defName ):
	info = rc.model_info( defName )
	if not info:
		sys.exit( "%s: no rigged model def" % defName )
	defDir = os.path.join( ROOT, "def" )
	defFile = [ f for f in os.listdir( defDir ) if f.endswith( ".def" )
				and re.search( r"entityDef\s+%s\b" % re.escape( defName ), open( os.path.join( defDir, f ), encoding = "latin-1" ).read() ) ][0]
	afName = re.search( r'"ragdoll"\s+"([^"]+)"', open( os.path.join( defDir, defFile ), encoding = "latin-1" ).read() ).group( 1 )
	af = open( os.path.join( ROOT, "af", afName + ".af" ) ).read()

	rig = rc.load_rig( info )
	q = rig.q
	names = [ j.name for j in q.joints ]
	bind = []
	for j, jt in enumerate( q.joints ):
		local = ( rc.mat( jt.rotate, jt.scale ), jt.translate )
		bind.append( local if jt.parent < 0 else rc.compose( bind[jt.parent], local ) )
	P = { n: bind[i][1] for i, n in enumerate( names ) }
	owner = [ names[rig.bi[v][max( range( 4 ), key = lambda c: rig.bw[v][c] )]] for v in range( len( rig.pos ) ) ]
	owner = [ o if o in TEMPLATE else None for o in owner ]
	pts = lambda ns: [ rig.pos[v] for v in range( len( rig.pos ) ) if owner[v] in ns ]
	limbs = [ s_ + n for s_ in "LR" for n in ( "uparm", "loarm", "hand", "upleg", "loleg", "ankle_r" ) ]
	trunk = [ rig.pos[v] for v in range( len( rig.pos ) ) if owner[v] and owner[v] not in limbs ]

	def body_points( bname ):
		if bname == "waist":
			z0, z1 = sorted( ( P["Hips"][2], P["Waist"][2] ) )
			return [ p for p in trunk if z0 <= p[2] <= z1 ]
		return pts( BONES.get( bname, ( bname, ) ) )

	report = []
	out, pos = [], 0
	for m in re.finditer( r'\tbody "(\w+)" \{.*?\n\t\}', af, re.S ):
		block, bname = m.group( 0 ), m.group( 1 )
		out.append( af[pos:m.start()] )
		ps = body_points( bname )
		if len( ps ) >= 4:
			c, h, axes = obb( ps )
			ang = angles_of( axes )
			back = axes_of( ang )
			assert max( abs( back[i][k] - axes[i][k] ) for i in range( 3 ) for k in range( 3 ) ) < 1e-6, bname
			old = re.search( r"\t\tmodel [^\n]*", block ).group( 0 )
			block = block.replace( old, "\t\tmodel box( ( %.2f, %.2f, %.2f ), ( %.2f, %.2f, %.2f ) )" % ( -h[0], -h[1], -h[2], h[0], h[1], h[2] ) )
			block = re.sub( r"\t\torigin \([^)]*\)", "\t\torigin ( %.2f, %.2f, %.2f )" % tuple( c ), block, count = 1 )
			block = re.sub( r"\t\tangles \([^)]*\)\n", "", block )
			block = block.replace( "\t\torigin (", "\t\tangles ( %.1f, %.1f, %.1f )\n\t\torigin (" % ang, 1 )
			report.append( "  %-7s %3d vertexes: %.1f x %.1f x %.1f, angles ( %.0f %.0f %.0f )   (was %s)"
						   % ( bname, len( ps ), 2 * h[0], 2 * h[1], 2 * h[2], *ang, old.strip() ) )
		else:
			report.append( "  %-7s %d vertexes: kept" % ( bname, len( ps ) ) )
		out.append( block )
		pos = m.end()
	out.append( af[pos:] )
	dst = os.path.join( ROOT, "out", "rig", "af", afName + ".af" )
	os.makedirs( os.path.dirname( dst ), exist_ok = True )
	with open( dst, "w" ) as fp:
		fp.write( "".join( out ) )
	print( "%s (%s):" % ( afName, info[0] ) )
	print( "\n".join( report ) )
	print( "  wrote %s" % os.path.relpath( dst, ROOT ) )

if __name__ == "__main__":
	if len( sys.argv ) != 2:
		print( __doc__ )
		sys.exit( 1 )
	main( sys.argv[1] )
