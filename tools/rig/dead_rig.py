#!/usr/bin/env python3
"""
Daikatana's dead bodies (models/e1/m_dead.md3) rigged from joints placed by
hand (tools/rig/joints/dead.txt).

The model is one of its kind: ten bodies lying anyhow, each frame a pose of
its own, and so low-poly (239 vertexes) that a leg is a ring at the hip and
one at the ankle with nothing between. autorig places a joint by the mesh and
moves a bone by the vertexes it carries; here most bones carry a ring or
two, and a thigh fitted to its hip's ring alone points anywhere. So the
joints are where the file puts them, each vertex goes to the bone it's
nearest, and each bone is fitted, a pose at a time, to its vertexes and to
the joint at its end where its child's vertexes put it: a thigh reaches its
knee in every pose, the ragdoll's bodies (autorig's ragdoll_af, on these
joints) lying where the limbs do.

	python3 tools/rig/dead_rig.py dkres/models/e1/m_dead.md3 dkres/models/rigged/dead tools/rig/joints/dead.txt

writes <out>.iqm (a one-frame animation a pose, named by the frame),
def/char_dead.def (RIG_STAGE's def/ under ./dk rig) and af/char_dead.af
(out/rig/af/ if af/ has one: that one's the authority).
"""
import math
import os
import re
import sys

sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
import autorig as ar
from autorig import vadd, vsub, vscale, vdot, vlen, vnorm, vcross, mvec, mmul, mtrans, xform, rigid_fit, IDENT
from md3 import MD3

ZONES = { name: zone for name, parent, p, zone in ar.D3_TEMPLATE }
PULL = 0.1		# a joint's weight in a bone's fit, of its vertexes'


def load_joints( path ):
	"""the joints (name, parent, place in the model as it lies) and the
	limbs' ends"""
	joints, ends, twists = [], {}, {}
	for line in open( path ):
		w = line.split( "#" )[0].split()
		if not w:
			continue
		if w[0] == "end":
			ends[w[1]] = tuple( float( x ) for x in w[2:5] )
		elif w[0] == "twist":
			joints.append( ( w[1], w[2], tuple( float( x ) for x in w[3:6] ) ) )
			twists[w[1]] = float( w[6] )
		else:
			joints.append( ( w[0], w[1], tuple( float( x ) for x in w[2:5] ) ) )
	return joints, ends, twists

def seg_dist( p, a, b ):
	d = vsub( b, a )
	t = max( 0.0, min( 1.0, vdot( vsub( p, a ), d ) / max( 1e-9, vdot( d, d ) ) ) )
	return vlen( vsub( p, vadd( a, vscale( d, t ) ) ) )

def turn( a, b ):
	"""the least rotation taking direction a to direction b"""
	a, b = vnorm( a ), vnorm( b )
	c = max( -1.0, min( 1.0, vdot( a, b ) ) )
	axis = vcross( a, b )
	s = vlen( axis )
	if s < 1e-9:
		return IDENT
	x, y, z = vscale( axis, 1.0 / s )
	C = 1.0 - c
	return [ [ c + x * x * C, x * y * C - z * s, x * z * C + y * s ],
			 [ y * x * C + z * s, c + y * y * C, y * z * C - x * s ],
			 [ z * x * C - y * s, z * y * C + x * s, c + z * z * C ] ]

def main( md3Path, outBase, jointsPath ):
	ar.TO_MODEL = ar.lie_down		# rigged stood up, as autorig --lying: written back lying
	m = MD3( md3Path )
	F = m.numFrames
	m.animations = lambda: [ ( n, i, 1 ) for i, n in enumerate( m.frameNames ) ]
	body = [ s for s in m.surfaces if not ar.is_hardpoint( s ) ]
	verts = [ ( si, vi ) for si, s in enumerate( body ) for vi in range( s.numVerts ) ]
	N = len( verts )
	frames = [ [ ar.stand_up( body[si].frames[f][vi] ) for si, vi in verts ] for f in range( F ) ]
	rest = frames[0]
	print( "%s: %d vertexes, %d poses" % ( md3Path, N, F ) )

	# the joints, stood up; origin and Body by the hips (the root under the
	# pelvis on the floor its back lies on, as the ragdoll's pelvis body
	# moves the origin joint: Doom 3's AF)
	placed, ends, twists = load_joints( jointsPath )
	pos = { n: ar.stand_up( p ) for n, parent, p in placed }
	hips = pos["Hips"]
	floor = min( v[0] for v in rest )
	joints = [ { "name": "origin", "parent": None, "parentIndex": -1, "zone": None, "pos": ( floor, hips[1], hips[2] ) },
			   { "name": "Body", "parent": "origin", "parentIndex": 0, "zone": None, "pos": hips } ]
	for n, parent, p in placed:
		joints.append( { "name": n, "parent": parent, "zone": ZONES.get( n, ZONES.get( parent, "torso" ) ), "pos": pos[n],
						 "extra": n in twists } )
	J = { j["name"]: i for i, j in enumerate( joints ) }
	for j in joints[1:]:
		j["parentIndex"] = J[j["parent"]]
	nj = len( joints )
	kids = { i: [ k for k in range( nj ) if joints[k]["parentIndex"] == i ] for i in range( nj ) }
	bones = [ i for i in range( nj ) if joints[i]["zone"] ]
	def bone_end( i ):
		if joints[i]["name"] in ends:
			return ar.stand_up( ends[joints[i]["name"]] )
		ks = [ k for k in kids[i] if k in bones and not joints[k]["extra"] ]
		if not ks:
			return joints[i]["pos"]		# a twist joint: a point
		return vscale( ( sum( joints[k]["pos"][0] for k in ks ), sum( joints[k]["pos"][1] for k in ks ),
						 sum( joints[k]["pos"][2] for k in ks ) ), 1.0 / len( ks ) )
	segs = { i: ( joints[i]["pos"], bone_end( i ) ) for i in bones }

	# each vertex the bone it's nearest, or a twist joint's within its reach
	# (a ring Daikatana's poses turn on their own: the left forearm's
	# middle, its every pose sculpted anew)
	limbs = [ b for b in bones if not joints[b]["extra"] ]
	assign = []
	for v in rest:
		tw = [ b for b in bones if joints[b]["extra"] and vlen( vsub( v, joints[b]["pos"] ) ) <= twists[joints[b]["name"]] ]
		assign.append( tw[0] if tw else min( limbs, key = lambda b: seg_dist( v, *segs[b] ) ) )
	own = { b: [ i for i in range( N ) if assign[i] == b ] for b in bones }
	print( "  bones: %s" % ", ".join( "%s %d" % ( joints[b]["name"], len( own[b] ) ) for b in bones ) )

	# where each joint is in each pose: one with a ring about it (a hip, an
	# ankle, an elbow) where its ring's motion takes it; one with none (a
	# knee: the leg's a straight tube from the hip's ring to the ankle's)
	# between its neighbours, as far along as it is lying in dead000
	def parent_bone( b ):
		p = joints[b]["parentIndex"]
		while p >= 0 and p not in bones:
			p = joints[p]["parentIndex"]
		return p
	fit = { b: { f: rigid_fit( [ rest[i] for i in own[b] ], [ frames[f][i] for i in own[b] ] ) for f in range( F ) }
			for b in bones if len( own[b] ) >= 3 }
	RING = 3.0		# a joint further than this from its bones' vertexes has no ring
	land = {}		# joint (or ( joint, "end" )): its place in each pose
	def ring_of( p, cands ):
		best = None
		for c in cands:
			if c in fit:
				d = min( vlen( vsub( rest[i], p ) ) for i in own[c] )
				if best is None or d < best[0]:
					best = ( d, c )
		return best
	loose = []
	for j in bones:
		r = ring_of( joints[j]["pos"], [ j, parent_bone( j ) ] )
		if r and r[0] <= RING:
			land[j] = [ xform( fit[r[1]][f], joints[j]["pos"] ) for f in range( F ) ]
		else:
			loose.append( j )
	for j in bones:
		if joints[j]["name"] in ends:
			e = ar.stand_up( ends[joints[j]["name"]] )
			r = ring_of( e, [ j ] )
			if r:
				land[( j, "end" )] = [ xform( fit[r[1]][f], e ) for f in range( F ) ]
	for j in loose:
		p, ks = parent_bone( j ), [ k for k in kids[j] if k in land ]
		if p in land and ks:
			a0, b0 = joints[p]["pos"], joints[ks[0]]["pos"]
			d = vsub( b0, a0 )
			t = vdot( vsub( joints[j]["pos"], a0 ), d ) / max( 1e-9, vdot( d, d ) )
			land[j] = [ vadd( land[p][f], vscale( vsub( land[ks[0]][f], land[p][f] ), t ) ) for f in range( F ) ]
	print( "  joints between their neighbours: %s" % ( ", ".join( joints[j]["name"] for j in loose if j in land ) or "none" ) )

	# each bone fitted to its vertexes and, lightly, its joints there (PULL
	# of all its vertexes, three at least: held to them, Daikatana's poses,
	# sculpted, drag the vertexes off; free, a thigh spins on its ring); the
	# pelvis, no vertex of its own, to its hips and the waist
	motion = {}
	for b in bones:
		src = [ rest[i] for i in own[b] ]
		wts = [ 1.0 ] * len( src )
		tg = { f: [ frames[f][i] for i in own[b] ] for f in range( F ) }
		heavy = PULL * max( 3.0, float( len( own[b] ) ) )
		pts = [ b ] + [ k for k in kids[b] if k in bones ] + ( [ ( b, "end" ) ] if ( b, "end" ) in land else [] )
		if joints[b]["name"] == "Hips":
			pts = [ J["Lupleg"], J["Rupleg"], J["Waist"] ]
		for q in pts:
			if q not in land:
				continue
			src.append( ar.stand_up( ends[joints[q[0]]["name"]] ) if isinstance( q, tuple ) else joints[q]["pos"] )
			wts.append( heavy )
			for f in range( F ):
				tg[f].append( land[q][f] )
		if len( src ) >= 3:
			motion[b] = { f: rigid_fit( src, tg[f], wts ) for f in range( F ) }
		elif len( src ) == 2 and parent_bone( b ) in motion:
			pm, a0, e0 = motion[parent_bone( b )], src[0], src[1]
			motion[b] = {}
			for f in range( F ):
				rp = pm[f][0]
				r = mmul( turn( mvec( rp, vsub( e0, a0 ) ), vsub( tg[f][1], tg[f][0] ) ), rp )
				motion[b][f] = ( r, vsub( tg[f][0], mvec( r, a0 ) ) )
	for b in bones:
		if b not in motion:
			pb = parent_bone( b )
			motion[b] = motion[pb] if pb in motion else { f: ( IDENT, ( 0, 0, 0 ) ) for f in range( F ) }
	motion[J["Body"]] = motion[J["Hips"]]
	motion[J["origin"]] = motion[J["Hips"]]

	# two weights a vertex: its bone, blended with the next one up or down
	# the limb where that carries it better over the poses
	def near( b ):
		n = [ k for k in kids[b] if k in bones ]
		p = parent_bone( b )
		return n + ( [ p ] if p >= 0 else [] )
	weights = []
	def err( i, b, o, w ):
		e = 0.0
		for f in range( F ):
			p = xform( motion[b][f], rest[i] )
			if w < 1.0:
				p = vadd( vscale( p, w ), vscale( xform( motion[o][f], rest[i] ), 1.0 - w ) )
			d = vsub( p, frames[f][i] )
			e += vdot( d, d )
		return e
	for i in range( N ):
		b = assign[i]
		best = ( b, b, 1.0, err( i, b, b, 1.0 ) )
		for o in near( b ):
			num = den = 0.0
			for f in range( F ):
				a = xform( motion[b][f], rest[i] )
				c = xform( motion[o][f], rest[i] )
				ac = vsub( a, c )
				num += vdot( ac, vsub( frames[f][i], c ) )
				den += vdot( ac, ac )
			w = 1.0 if den < 1e-9 else max( 0.0, min( 1.0, num / den ) )
			e = err( i, b, o, w )
			if e < best[3]:
				best = ( b, o, w, e )
		b, o, w = best[:3]
		if w < 0.5:
			b, o, w = o, b, 1.0 - w
		weights.append( ( b, o, w ) )

	# how far the skinned poses are from Daikatana's
	worst = total = 0.0
	for f in range( F ):
		for i in range( N ):
			b, o, w = weights[i]
			p = xform( motion[b][f], rest[i] )
			if w < 1.0:
				p = vadd( vscale( p, w ), vscale( xform( motion[o][f], rest[i] ), 1.0 - w ) )
			e = vlen( vsub( p, frames[f][i] ) )
			total, worst = total + e, max( worst, e )
	print( "  error: %.3f units on average, %.2f at most" % ( total / ( N * F ), worst ) )

	anims, restRot = ar.write_iqm( m, body, verts, rest, joints, motion, weights, outBase )

	# the model def: as autorig's for a lying body, its hitboxes the bones'
	# vertexes in their joints' frames
	name = "dead"
	lines = [ "// made by tools/rig/dead_rig.py from %s" % ar.gamePath( md3Path ),
			  "// (its joints placed by hand: tools/rig/joints/dead.txt)",
			  "entityDef model_%s {" % name,
			  "\t\"inherit\"\t\t\t\"character_base\"\t// def/dk_characters.def",
			  "\t\"mesh\"\t\t\t\t\"%s.iqm\"" % ar.meshPath( outBase ),
			  "\t\"mins\"\t\t\t\t\"-38 -38 -1\"\t// standing, at the origin (pmove's)",
			  "\t\"maxs\"\t\t\t\t\"38 38 8\"",
			  "\t\"crouch_height\"\t\t\"8\"\t\t// maxs z crouched",
			  "\t\"eye_height\"\t\t\"7\"",
			  "\t\"crouch_eye_height\"\t\"7\"",
			  "\t\"ik_minWaistAnkleDist\"\t\"16\"\t// the walk IK's waist drops no lower (Doom 3's)",
			  "" ]
	lines += [ "\t\"anim %s\"\t\t\"%s\"" % ( a[0], a[0] ) for a in anims ]
	lines.append( "" )
	for j in bones:
		rt = mtrans( restRot[j] )
		pts = [ mvec( rt, vsub( rest[i], joints[j]["pos"] ) ) for i in own[j] ]
		if len( pts ) < 4:
			continue
		lo = [ min( p[k] for p in pts ) for k in range( 3 ) ]
		hi = [ max( p[k] for p in pts ) for k in range( 3 ) ]
		lines.append( "\t\"hitbox %s\"\t\"%.1f %.1f %.1f %.1f %.1f %.1f %s\"" % ( joints[j]["name"], *lo, *hi, joints[j]["zone"] ) )
	lines += [ "", "\t\"damage_scale head\"\t\"2\"", "\t\"damage_scale arms\"\t\"0.75\"", "\t\"damage_scale legs\"\t\"0.75\"", "" ]
	# the ragdoll's bodies: the head's the head alone, the neck in no body's
	# box (the head's box, over the neck too, was too big); a twist joint's
	# vertexes its limb's
	afAssign = []
	for b in assign:
		if joints[b]["name"] == "Loneck":
			b = J["origin"]
		while joints[b].get( "extra" ):
			b = joints[b]["parentIndex"]
		afAssign.append( b )
	af = ar.ragdoll_af( name, joints, rest, afAssign, "char_" + name )
	# the torso's bodies by where the torso is, enveloping it, not by its
	# bones' vertexes (the chest bone carries three, the shoulders and the
	# neck the rest of the chest): the chest from the neck to the waist and
	# out to the shoulders, the pelvis from the waist to the hips' joints
	if af:
		lyingAt = { n: p for n, parent, p in placed }
		legs = set( J[s_ + n] for s_ in "LR" for n in ( "loleg", "ankle_r" ) )
		def limb( b ):
			while joints[b].get( "extra" ):
				b = joints[b]["parentIndex"]
			return b
		model = [ ar.lie_down( v ) for v in rest ]
		# (between the shoulders' joints a shoulder bone's vertexes are the
		# chest's sides; the arms lie outside them, and the shins past the hips)
		trunk = [ model[i] for i in range( N ) if limb( assign[i] ) not in legs ]
		def envelope( bname, x0, x1, y0, y1, reach ):
			nonlocal af
			ps = [ p for p in trunk if x0 <= p[0] <= x1 and y0 <= p[1] <= y1 ]
			lo = [ min( p[k] for p in ps ) for k in range( 3 ) ]
			hi = [ max( p[k] for p in ps ) for k in range( 3 ) ]
			# (out to the joints it reaches: the waist's, where the other one
			# begins, no gap between; the pelvis' the hips')
			for r in reach:
				lo[0], hi[0] = min( lo[0], r[0] ), max( hi[0], r[0] )
				if len( r ) > 1:
					lo[1], hi[1] = min( lo[1], r[1] ), max( hi[1], r[1] )
			c = [ 0.5 * ( lo[k] + hi[k] ) for k in range( 3 ) ]
			h = [ max( 1.0, 0.5 * ( hi[k] - lo[k] ) ) for k in range( 3 ) ]
			a = af.index( "\tbody \"%s\" {" % bname )
			b = af.index( "\t}", a )
			block = af[a:b]
			block = re.sub( r"model box\( \([^)]*\), \([^)]*\) \)", "model box( ( %.2f, %.2f, %.2f ), ( %.2f, %.2f, %.2f ) )"
							% ( -h[0], -h[1], -h[2], h[0], h[1], h[2] ), block )
			block = re.sub( r"origin \([^)]*\)", "origin ( %.2f, %.2f, %.2f )" % tuple( c ), block )
			af = af[:a] + block + af[b:]
		neck, waist = lyingAt["Loneck"], lyingAt["Waist"]
		shoulders = sorted( ( lyingAt["Luparm"][1], lyingAt["Ruparm"][1] ) )
		envelope( "chest", neck[0], waist[0], shoulders[0], shoulders[1], [ ( waist[0], ) ] )
		# the pelvis between the hips' joints, each thigh's body from its own
		# (out to the hips' rings it took both thighs' tops)
		hl, hr = lyingAt["Lupleg"], lyingAt["Rupleg"]
		envelope( "waist", waist[0], min( hl[0], hr[0] ), min( hl[1], hr[1] ), max( hl[1], hr[1] ),
				  [ ( waist[0], ), hl[:2], hr[:2] ] )
	if af:
		ar.write_af( os.path.join( "af", "char_%s.af" % name ), af )
		lines.append( "\t\"ragdoll\"\t\t\t\"char_%s\"\t// af/char_%s.af, Doom 3's articulated figure" % ( name, name ) )
	lines += [ "}", "" ]
	defPath = os.path.join( ar.STAGE or ".", "def", "char_%s.def" % name )
	os.makedirs( os.path.dirname( defPath ), exist_ok = True )
	with open( defPath, "w" ) as fp:
		fp.write( "\n".join( lines ) )
	print( "  wrote %s" % defPath )

if __name__ == "__main__":
	if len( sys.argv ) != 4:
		print( __doc__ )
		sys.exit( 1 )
	main( *sys.argv[1:] )
