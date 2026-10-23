#!/usr/bin/env python3
"""
Turns a Daikatana character (a vertex animated .dkm, converted to .md3 frame
by frame) into a skeletal IQM with Doom 3's joint names, its own animations
kept, with no rigging by hand.

How (a small form of skinning decomposition, Le & Deng's SSDR):
 1. A humanoid template skeleton with Doom 3's joint names and hierarchy is
    placed in the mesh by its proportions (Doom 3's human rig, scaled).
 2. The mesh is split into rigid segments, one a bone, first by where the
    vertices are, then again and again by which bone's rigid motion (fitted
    to every frame) carries each vertex best.
 3. Each joint is put where the parent's and the child's motions agree
    best: the point that moves least between the two segments over the
    frames (least squares).
 4. Each vertex blends its bone with a neighbouring one where that fits the
    frames better (two weights a vertex).
 5. Daikatana's hardpoints (hp_gun, ctf_flag, the monsters' hr_muzzle...: a
    triangle each) become rigid attachment joints, as Doom 3's *_ATTACHER
    joints.
With --name, a monster or another character, not a player: def/rig_<name>.def
(model_<name>) and af/monster_<name>.af, its animations at 10 frames a second
(--fps) or as --anims "<anim> <fps> [loop];..." says, and with --extra N up to
N more bones for what the template has no bone for (a cape, wings, a sword);
--surface metal makes it a robot, its hits spark.
With --lying, the model lies on its back, its head toward -x (as Daikatana's
dead bodies: their frames are poses, not animations): it's rigged stood up,
head up and facing +x, and everything written is turned back to lying.
The joints' rest frames are the mesh's first frame; every frame of the MD3
becomes a pose, its animations (named by the frame names) the IQM's.

	python3 tools/rig/autorig.py dkres/models/global/m_hiro.md3 dkres/models/rigged/hiro
	python3 tools/rig/autorig.py --lying dkres/models/e1/m_dead.md3 dkres/models/rigged/dead
	python3 tools/rig/autorig.py --name fatworker --extra 8 dkres/models/e1/m_mwfaty.md3 dkres/models/rigged/mwfaty
writes dkres/models/rigged/hiro.iqm and def/char_hiro.def (the model def,
with hitboxes fitted to the bones) and prints how far the skinned frames
are from the original ones. ./dk rig runs it for the characters (RIG_MODELS).

Pure Python (no numpy): a few minutes for a character.
"""
import math
import os
import re
import struct
import sys

sys.path.insert( 0, os.path.dirname( __file__ ) )
from md3 import MD3, Surface

# ------------------------------------------------------------------------
# small linear algebra

def vsub( a, b ): return ( a[0] - b[0], a[1] - b[1], a[2] - b[2] )
def vadd( a, b ): return ( a[0] + b[0], a[1] + b[1], a[2] + b[2] )
def vscale( a, s ): return ( a[0] * s, a[1] * s, a[2] * s )
def vdot( a, b ): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def vlen( a ): return math.sqrt( vdot( a, a ) )
def vcross( a, b ): return ( a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0] )
def vnorm( a ):
	l = vlen( a )
	return vscale( a, 1.0 / l ) if l > 1e-9 else ( 0.0, 0.0, 0.0 )

def mvec( m, v ):
	"""3x3 (rows) times a vector."""
	return ( m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
			 m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
			 m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2] )

def mmul( a, b ):
	return [ [ sum( a[i][k] * b[k][j] for k in range( 3 ) ) for j in range( 3 ) ] for i in range( 3 ) ]

def mtrans( m ):
	return [ [ m[j][i] for j in range( 3 ) ] for i in range( 3 ) ]

IDENT = [ [ 1.0, 0.0, 0.0 ], [ 0.0, 1.0, 0.0 ], [ 0.0, 0.0, 1.0 ] ]

def quat_to_mat( q ):
	x, y, z, w = q
	return [ [ 1 - 2 * ( y * y + z * z ), 2 * ( x * y - z * w ), 2 * ( x * z + y * w ) ],
			 [ 2 * ( x * y + z * w ), 1 - 2 * ( x * x + z * z ), 2 * ( y * z - x * w ) ],
			 [ 2 * ( x * z - y * w ), 2 * ( y * z + x * w ), 1 - 2 * ( x * x + y * y ) ] ]

def mat_to_quat( m ):
	tr = m[0][0] + m[1][1] + m[2][2]
	if tr > 0:
		s = math.sqrt( tr + 1.0 ) * 2
		q = ( ( m[2][1] - m[1][2] ) / s, ( m[0][2] - m[2][0] ) / s, ( m[1][0] - m[0][1] ) / s, 0.25 * s )
	elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
		s = math.sqrt( 1.0 + m[0][0] - m[1][1] - m[2][2] ) * 2
		q = ( 0.25 * s, ( m[0][1] + m[1][0] ) / s, ( m[0][2] + m[2][0] ) / s, ( m[2][1] - m[1][2] ) / s )
	elif m[1][1] > m[2][2]:
		s = math.sqrt( 1.0 + m[1][1] - m[0][0] - m[2][2] ) * 2
		q = ( ( m[0][1] + m[1][0] ) / s, 0.25 * s, ( m[1][2] + m[2][1] ) / s, ( m[0][2] - m[2][0] ) / s )
	else:
		s = math.sqrt( 1.0 + m[2][2] - m[0][0] - m[1][1] ) * 2
		q = ( ( m[0][2] + m[2][0] ) / s, ( m[1][2] + m[2][1] ) / s, 0.25 * s, ( m[1][0] - m[0][1] ) / s )
	n = math.sqrt( sum( c * c for c in q ) )
	q = tuple( c / n for c in q )
	return q if q[3] >= 0 else tuple( -c for c in q )

def solve3( a, b ):
	"""a x = b for a 3x3 a (Cramer)."""
	def det( m ):
		return ( m[0][0] * ( m[1][1] * m[2][2] - m[1][2] * m[2][1] )
				 - m[0][1] * ( m[1][0] * m[2][2] - m[1][2] * m[2][0] )
				 + m[0][2] * ( m[1][0] * m[2][1] - m[1][1] * m[2][0] ) )
	d = det( a )
	if abs( d ) < 1e-12:
		return None
	x = []
	for c in range( 3 ):
		m = [ row[:] for row in a ]
		for r in range( 3 ):
			m[r][c] = b[r]
		x.append( det( m ) / d )
	return tuple( x )

def eigen3( a ):
	"""A symmetric 3x3's eigenvalues and unit eigenvectors (Jacobi)."""
	m = [ row[:] for row in a ]
	v = [ [ 1.0 if r == c else 0.0 for c in range( 3 ) ] for r in range( 3 ) ]
	for sweep in range( 50 ):
		off = sum( m[r][c] ** 2 for r in range( 3 ) for c in range( 3 ) if r != c )
		if off < 1e-18:
			break
		for p in range( 3 ):
			for q in range( p + 1, 3 ):
				if abs( m[p][q] ) < 1e-12:
					continue
				th = 0.5 * math.atan2( 2 * m[p][q], m[q][q] - m[p][p] )
				c, s = math.cos( th ), math.sin( th )
				for k in range( 3 ):
					mkp, mkq = m[k][p], m[k][q]
					m[k][p], m[k][q] = c * mkp - s * mkq, s * mkp + c * mkq
				for k in range( 3 ):
					mpk, mqk = m[p][k], m[q][k]
					m[p][k], m[q][k] = c * mpk - s * mqk, s * mpk + c * mqk
				for k in range( 3 ):
					vkp, vkq = v[k][p], v[k][q]
					v[k][p], v[k][q] = c * vkp - s * vkq, s * vkp + c * vkq
	return [ m[i][i] for i in range( 3 ) ], [ ( v[0][i], v[1][i], v[2][i] ) for i in range( 3 ) ]

def rigid_fit( src, dst, weights = None ):
	"""The rotation and translation that best take the points src to dst
	(Horn's quaternion method): x' = R x + t."""
	n = len( src )
	if weights is None:
		weights = [ 1.0 ] * n
	wsum = sum( weights )
	cs = [ sum( weights[i] * src[i][k] for i in range( n ) ) / wsum for k in range( 3 ) ]
	cd = [ sum( weights[i] * dst[i][k] for i in range( n ) ) / wsum for k in range( 3 ) ]
	s = [ [ 0.0 ] * 3 for _ in range( 3 ) ]
	for i in range( n ):
		w = weights[i]
		a0, a1, a2 = src[i][0] - cs[0], src[i][1] - cs[1], src[i][2] - cs[2]
		b0, b1, b2 = dst[i][0] - cd[0], dst[i][1] - cd[1], dst[i][2] - cd[2]
		s[0][0] += w * a0 * b0; s[0][1] += w * a0 * b1; s[0][2] += w * a0 * b2
		s[1][0] += w * a1 * b0; s[1][1] += w * a1 * b1; s[1][2] += w * a1 * b2
		s[2][0] += w * a2 * b0; s[2][1] += w * a2 * b1; s[2][2] += w * a2 * b2
	sxx, sxy, sxz = s[0]
	syx, syy, syz = s[1]
	szx, szy, szz = s[2]
	nm = [ [ sxx + syy + szz, syz - szy, szx - sxz, sxy - syx ],
		   [ syz - szy, sxx - syy - szz, sxy + syx, szx + sxz ],
		   [ szx - sxz, sxy + syx, -sxx + syy - szz, syz + szy ],
		   [ sxy - syx, szx + sxz, syz + szy, -sxx - syy + szz ] ]
	# the eigenvector of the largest eigenvalue, by power iteration (shifted)
	shift = sum( abs( c ) for row in nm for c in row ) + 1e-9
	for i in range( 4 ):
		nm[i][i] += shift
	q = [ 1.0, 0.0, 0.0, 0.0 ]
	for _ in range( 60 ):
		q2 = [ sum( nm[i][j] * q[j] for j in range( 4 ) ) for i in range( 4 ) ]
		l = math.sqrt( sum( c * c for c in q2 ) )
		q = [ c / l for c in q2 ]
	w, x, y, z = q
	r = quat_to_mat( ( x, y, z, w ) )
	t = vsub( cd, mvec( r, cs ) )
	return r, t

def xform( rt, v ):
	r, t = rt
	return vadd( mvec( r, v ), t )

# ------------------------------------------------------------------------
# the template: Doom 3's human rig (models/md5/characters/npcs/playermoves,
# joints that deform the body), positions in its space (x left, -y
# forward, z up, about 72 tall, the head's top about 77)

D3_TEMPLATE = [
	# name, parent, position, zone
	( "origin",    None,       ( 0, 0, 0 ), None ),
	( "Body",      "origin",   ( 0, 0, 45.0 ), None ),
	( "Hips",      "Body",     ( 0.07, 0.16, 45.0 ), "torso" ),
	( "Lupleg",    "Hips",     ( 5.0, -0.55, 43.2 ), "legs" ),
	( "Lloleg",    "Lupleg",   ( 7.48, 1.9, 22.9 ), "legs" ),
	( "Lankle_r",  "Lloleg",   ( 9.69, 4.09, 4.78 ), "legs" ),
	( "Rupleg",    "Hips",     ( -4.87, -0.55, 43.2 ), "legs" ),
	( "Rloleg",    "Rupleg",   ( -7.35, 1.91, 22.87 ), "legs" ),
	( "Rankle_r",  "Rloleg",   ( -9.56, 4.09, 4.78 ), "legs" ),
	( "Waist",     "Body",     ( -0.05, 0.0, 49.5 ), "torso" ),
	( "Chest",     "Waist",    ( 0.07, 2.1, 56.0 ), "torso" ),
	( "Loneck",    "Chest",    ( 0.07, -0.03, 66.5 ), "head" ),
	( "Head",      "Loneck",   ( 0.07, -0.46, 70.5 ), "head" ),
	( "Luparm",    "Chest",    ( 7.69, 1.08, 64.1 ), "arms" ),
	( "Lloarm",    "Luparm",   ( 9.0, 1.2, 52.0 ), "arms" ),
	( "Lhand",     "Lloarm",   ( 9.5, -1.0, 41.0 ), "arms" ),
	( "Ruparm",    "Chest",    ( -7.55, 1.08, 64.1 ), "arms" ),
	( "Rloarm",    "Ruparm",   ( -9.0, 1.2, 52.0 ), "arms" ),
	( "Rhand",     "Rloarm",   ( -9.5, -1.0, 41.0 ), "arms" ),
]
# (the arms are put hanging down, as Daikatana's characters stand, not
# Doom 3's bind pose)
D3_HEIGHT = 77.0

# Quake 3's player animations (animNumber_t) to Daikatana's, for a character
# as a player model: the first of each list it has. The torso's attack plays
# over the legs' (from the waist up); the others leave the torso to the legs.
PLAYER_ANIMS = [
	( "BOTH_DEATH1", [ "die" ] ), ( "BOTH_DEAD1", [ "die hold" ] ),
	( "BOTH_DEATH2", [ "diea", "die" ] ), ( "BOTH_DEAD2", [ "diea hold", "die hold" ] ),
	( "BOTH_DEATH3", [ "dieb", "die" ] ), ( "BOTH_DEAD3", [ "dieb hold", "die hold" ] ),
	( "TORSO_ATTACK", [ "atak" ] ), ( "TORSO_ATTACK2", [ "atak" ] ),
	( "LEGS_IDLE", [ "aamb", "amb" ] ), ( "LEGS_TURN", [ "aamb", "amb" ] ),
	( "LEGS_WALK", [ "walk" ] ), ( "LEGS_BACKWALK", [ "bwalk", "walk" ] ),
	( "LEGS_RUN", [ "run" ] ), ( "LEGS_BACK", [ "run" ] ),
	( "LEGS_IDLECR", [ "camb" ] ), ( "LEGS_WALKCR", [ "cwalk" ] ), ( "LEGS_BACKCR", [ "cwalk" ] ),
	( "LEGS_JUMP", [ "jump", "ajump" ] ), ( "LEGS_JUMPB", [ "jump", "ajump" ] ),
	# landing has none: the legs go on with what they play (bg_model.c)
	( "LEGS_SWIM", [ "swim" ] ),
	( "LEGS_CLIMB", [ "ladderup" ] ), ( "LEGS_CLIMBDOWN", [ "ladderdn" ] ),
]

# hardpoint surfaces -> attachment joints (Doom 3 names its weapon ones so)
HARDPOINTS = { "hp_gun": ( "WEAPON_ATTACHER", "Rhand" ), "ctf_flag": ( "FLAG_ATTACHER", "Chest" ) }

def is_hardpoint( s ):
	"""Daikatana's hardpoints are surfaces of one triangle (hp_gun, the
	monsters' hr_muzzle, hp_head, eye1, sword1...): points, not mesh"""
	return s.name in HARDPOINTS or ( s.numVerts == 3 and len( s.triangles ) == 1 )

def hardpoint_joints( hps, joints, motion, bones, F, sample ):
	"""The hardpoints as rigid joints: hp_gun and ctf_flag Doom 3's
	attachers on their bones, the others by their surface's name on the bone
	whose motion carries the triangle best"""
	out = []
	J = { j["name"]: i for i, j in enumerate( joints ) }
	for s in hps:
		c = vscale( vadd( vadd( s.frames[0][0], s.frames[0][1] ), s.frames[0][2] ), 1.0 / 3 )
		if s.name in HARDPOINTS and HARDPOINTS[s.name][1] in J:
			name, parent = HARDPOINTS[s.name][0], J[HARDPOINTS[s.name][1]]
		else:
			def err( b ):
				return sum( vlen( vsub( xform( motion[b][f], s.frames[0][k] ), s.frames[f][k] ) ) for f in sample for k in range( 3 ) )
			name, parent = s.name, min( bones, key = err )
		out.append( ( { "name": name, "parent": joints[parent]["name"], "parentIndex": parent, "zone": None, "pos": c },
					  { f: rigid_fit( s.frames[0], s.frames[f] ) for f in range( F ) } ) )
	return out

def extent( pts ):
	return vlen( vsub( tuple( max( p[k] for p in pts ) for k in range( 3 ) ), tuple( min( p[k] for p in pts ) for k in range( 3 ) ) ) )

def is_prop( s ):
	"""A prop: a surface Daikatana hides in some frames by squashing it to a
	point (Usagi's Daikatana, carried in some shots, not in others), not a
	part of the body"""
	sizes = [ extent( f ) for f in s.frames ]
	return s.numVerts > 3 and max( sizes ) > 1 and min( sizes ) < 0.1 * max( sizes )

def split_props( surfaces ):
	"""A surface's pieces Daikatana hides by squashing them (Hiro's sword in
	his gi: blade, guard and hilt, in his body's surface) as surfaces of
	their own, props; the pieces hidden in the same frames one prop (they're
	one thing). A piece: its triangles joined, and its vertexes where they're
	in the same place in every frame (the md3 splits them where the texture
	does)."""
	out = []
	for s in surfaces:
		if is_hardpoint( s ) or s.numVerts < 8:
			out.append( s )
			continue
		F = len( s.frames )
		par = list( range( s.numVerts ) )
		def find( a ):
			while par[a] != a:
				par[a] = par[par[a]]
				a = par[a]
			return a
		for t in s.triangles:
			par[find( t[0] )] = find( t[1] )
			par[find( t[1] )] = find( t[2] )
		probe = sorted( set( [ 0, F // 4, F // 2, 3 * F // 4, F - 1 ] ) )
		place = {}
		for v in range( s.numVerts ):
			k = tuple( round( c * 4 ) for f in probe for c in s.frames[f][v] )
			if k in place:
				par[find( v )] = find( place[k] )
			else:
				place[k] = v
		pieces = {}
		for v in range( s.numVerts ):
			pieces.setdefault( find( v ), [] ).append( v )
		props = {}		# the frames it's hidden in -> its vertexes
		for vs in pieces.values():
			if len( vs ) == s.numVerts:
				break
			sizes = [ extent( [ s.frames[f][v] for v in vs ] ) for f in range( F ) ]
			if max( sizes ) > 1 and min( sizes ) < 0.1 * max( sizes ):
				hidden = tuple( f for f in range( F ) if sizes[f] < 0.1 * max( sizes ) )
				props.setdefault( hidden, [] ).extend( vs )
		if not props:
			out.append( s )
			continue
		def part( name, vs ):
			idx = { v: i for i, v in enumerate( sorted( vs ) ) }
			p = Surface()
			p.name, p.shader, p.numVerts = name, s.shader, len( idx )
			p.triangles = [ tuple( idx[c] for c in t ) for t in s.triangles if t[0] in idx ]
			p.st = [ s.st[v] for v in sorted( vs ) ]
			p.frames = [ [ fr[v] for v in sorted( vs ) ] for fr in s.frames ]
			return p
		taken = set( v for vs in props.values() for v in vs )
		out.append( part( s.name, [ v for v in range( s.numVerts ) if v not in taken ] ) )
		for k, vs in enumerate( props.values() ):
			out.append( part( "%s_prop%d" % ( s.name, k + 1 ), vs ) )
			print( "  %s: a piece of %d vertexes hidden in some frames, a prop" % ( s.name, len( vs ) ) )
	return out

# a prop's joint's scale a frame (0.01 where it's hidden): joint -> { frame: scale }
PROP_SCALE = {}

def prop_joints( props, joints, motion, bones, F ):
	"""The props as joints of their own: rest the frame each is biggest in,
	moved and scaled to each frame as a whole (a rigid fit and a uniform
	scale, Umeyama's), on the bone that keeps nearest it. Returns ( joint,
	its motion, its scale a frame, its vertexes' rest places )"""
	out = []
	for s in props:
		sizes = [ extent( f ) for f in s.frames ]
		rf = max( range( F ), key = lambda f: sizes[f] )
		rest = s.frames[rf]
		c = vscale( tuple( sum( p[k] for p in rest ) for k in range( 3 ) ), 1.0 / len( rest ) )
		seen = [ f for f in range( F ) if sizes[f] > 0.5 * sizes[rf] ]
		def dist( b ):
			p = joints[b]["pos"]
			return sum( vlen( vsub( xform( motion[b][f], p ), vscale( tuple( sum( q[k] for q in s.frames[f] ) for k in range( 3 ) ),
																		 1.0 / len( rest ) ) ) ) for f in seen )
		parent = min( bones, key = dist )
		jm, js = {}, {}
		for f in range( F ):
			r, t = rigid_fit( rest, s.frames[f] )
			cd = vscale( tuple( sum( q[k] for q in s.frames[f] ) for k in range( 3 ) ), 1.0 / len( rest ) )
			num = sum( vdot( mvec( r, vsub( a, c ) ), vsub( b, cd ) ) for a, b in zip( rest, s.frames[f] ) )
			den = sum( vdot( vsub( a, c ), vsub( a, c ) ) for a in rest )
			js[f] = max( 0.01, num / den if den > 0 else 1.0 )
			jm[f] = ( r, vsub( cd, mvec( r, c ) ) )		# the centre to the frame's
		out.append( ( { "name": s.name, "parent": joints[parent]["name"], "parentIndex": parent, "zone": None, "pos": c },
					  jm, js, rest ) )
	return out

# a monster's or another character's animations: Daikatana plays them at 10
# frames a second (a server frame each); those that loop, its idle and its
# ways of getting about. A spec ("<anim> <fps> [loop];...") overrides.
MONSTER_FPS = 10.0
MONSTER_LOOPING = r"^(amba|(walk|run|swim|fly|hover|row)[a-z]?)$"

class Looping:
	"""Which animations loop: the spec's say, the others by the default's names"""
	def __init__( self, spec, default ):
		self.spec, self.default = spec, re.compile( default, re.I )
	def match( self, anim ):
		return self.spec[anim][1] if anim in self.spec else bool( self.default.match( anim ) )

def anim_spec( text, fps, looping ):
	"""{ anim: ( fps, loops ) } from a spec ("<anim> <fps> [loop];..."), and
	which animations loop"""
	spec = {}
	for part in text.split( ";" ):
		w = part.split()
		if w:
			spec[w[0]] = ( float( w[1] ) if len( w ) > 1 else fps, "loop" in w[2:] )
	return spec, Looping( spec, looping )

# the animations that loop: Daikatana's names, a weapon prefix (a, b, c, o)
# and a variant suffix (a, b) on idling, walking, running...
# footsteps: on these animations' frames where a foot comes down (the
# cgame traces under it for the surface's sound), at a volume. Daikatana
# and Quake 3 step only when running; here walking steps too, quieter, and
# crouching is quiet (as Doom 3's)
FOOTSTEP_ANIMS = [ ( re.compile( r"^run[ab]?$", re.I ), 1.0 ), ( re.compile( r"^b?walk[ab]?$", re.I ), 0.4 ) ]
FOOTSTEP_JOINTS = ( "Lankle_r", "Rankle_r" )

# the characters' voices (Daikatana's client.cpp): name -> ( folder, pains,
# heavy pains (its "death" sounds for big hits), drowning sounds )
CHARACTER_SOUNDS = {
	"hiro": ( "hiro", 10, 10, [ "waterdeath1", "waterdeath2", "waterdeath3" ] ),
	"mikiko": ( "Mikiko", 8, 8, [ "waterchoke1", "waterchoke2", "waterchoke3" ] ),
	"superfly": ( "Superfly", 7, 7, [ "waterchoke2", "waterchoke3", "waterchoke4" ] ),
}

def character_sounds( name ):
	"""The model def's sound keys, each naming a sound shader, and the shaders
	(Doom 3's .sndshd): ( key lines, sound shader file text )."""
	if name not in CHARACTER_SOUNDS:
		return [], ""
	folder, pains, heavy, drown = CHARACTER_SOUNDS[name]
	sounds = [
		( "snd_pain", [ "pain%d" % i for i in range( 1, pains + 1 ) ] ),
		( "snd_pain_heavy", [ "death%d" % i for i in range( 1, heavy + 1 ) ] ),
		( "snd_death", [ "death%d" % i for i in range( 1, 5 ) ] ),
		( "snd_gib", [ "udeath" ] ),
		( "snd_jump", [ "jump1", "jump2", "jump3" ] ),
		( "snd_land", [ "land1", "land2", "land3" ] ),
		( "snd_land_hurt", [ "landhurt1", "landhurt2" ] ),
		( "snd_gasp", [ "breathe2", "choke1" ] ),
		( "snd_drown", drown ),
		( "snd_exitwater", [ "exitwater" ] ),
	]
	keys, shaders = [], [ "// %s's voice, made by tools/rig/autorig.py: Daikatana's (client.cpp PlayClientSound,"
		" volume 0.85, normal attenuation); Doom 3 sound shaders, distances in metres\n" % name ]
	for key, files in sounds:
		shader = "%s_%s" % ( name, key[4:] )
		keys.append( "\t\"%s\"\t\"%s\"" % ( key, shader ) )
		shaders.append( "%s\n{\n\tminDistance\t6.5\n\tmaxDistance\t16.5\n\tvolume\t\t0.85\n\tno_dups\n%s}\n" % (
			shader, "".join( "\tsounds/%s/%s.wav\n" % ( folder, f ) for f in files ) ) )
	return keys, "\n".join( shaders )

LOOPING = re.compile( r"^(a|b|c|o)?(amb|walk|run|ws|swim|ladderup|ladderdn|lookaround|talk|samb)[ab]?$", re.I )

# ------------------------------------------------------------------------

def place_template( rest, tris, headVerts, gunHand = None, headPoint = None ):
	"""The template's joints in the mesh, measured from it: Daikatana's
	characters aren't built like Doom 3's (bigger heads, shorter legs), so only
	the names and the hierarchy are Doom 3's. Where the neck narrows to the
	head, where the legs meet, how wide the shoulders are and where the hands
	hang (the right one at the gun hardpoint) place the joints."""
	zs = [ v[2] for v in rest ]
	zmin, zmax = min( zs ), max( zs )
	H = zmax - zmin
	band = [ v for v in rest if zmin + 0.45 * H < v[2] < zmin + 0.75 * H ]
	x0 = sorted( v[0] for v in band )[len( band ) // 2]
	y0 = sorted( v[1] for v in band )[len( band ) // 2]

	def slab( lo, hi ):
		return [ v for v in rest if zmin + lo * H <= v[2] < zmin + hi * H ]
	def width( vs ):
		return max( abs( v[1] - y0 ) for v in vs ) if vs else 0.0
	steps = 40
	widths = [ width( slab( k / steps, ( k + 1 ) / steps ) ) for k in range( steps ) ]
	wmax = max( widths )

	# the neck: going down from the top, where the body widens out of the head
	k = steps - 1
	while k > steps // 2 and widths[k] < 0.45 * wmax:
		k -= 1
	zNeck = zmin + ( k + 1 ) / steps * H
	if NAME:
		# a monster's or another character's head may be as wide as its
		# shoulders (a helmet, a mane, arms up): its head hardpoint (hp_head,
		# under the face) if it has one, else a head too small to be one
		# goes by Doom 3's proportions, the motion fitting the joint after
		# (the top near the middle, where there's a head's worth of mesh: an
		# arm or a bow may be raised over it)
		central = sorted( ( v[2] for v in rest if abs( v[1] - y0 ) < 0.12 * H ), reverse = True )
		ztop = next( ( z for z in central if sum( 1 for c in central if z - 0.05 * H <= c <= z ) >= max( 5, 0.03 * len( central ) ) ),
					 zmax )
		if headPoint:
			zNeck = headPoint[2] - 0.02 * H
		elif not 0.08 * H < ztop - zNeck < 0.3 * H:
			zNeck = ztop - 0.13 * ( ztop - zmin )
	zShoulder = zNeck - 0.05 * H
	# the crotch: going down, where a gap first opens between the legs, no
	# triangle cut there crossing the middle (going up from the feet stops
	# early where knees or thighs touch; vertexes alone miss the big
	# triangles a low-poly trunk spans the middle with)
	def crosses_middle( z ):
		for t in tris:
			pts = []
			for a, b in ( ( t[0], t[1] ), ( t[1], t[2] ), ( t[2], t[0] ) ):
				pa, pb = rest[a], rest[b]
				if ( pa[2] - z ) * ( pb[2] - z ) < 0:
					u = ( z - pa[2] ) / ( pb[2] - pa[2] )
					pts.append( pa[1] + u * ( pb[1] - pa[1] ) )
			if len( pts ) == 2 and ( pts[0] - y0 ) * ( pts[1] - y0 ) <= 0:
				return True
		return False
	zCrotch = zmin + 0.45 * H
	fine = 100
	for k in range( int( 0.6 * fine ), int( 0.25 * fine ), -1 ):
		if not crosses_middle( zmin + k / fine * H ):
			zCrotch = zmin + ( k + 1 ) / fine * H
			break
	shoulderY = 0.7 * width( slab( ( zShoulder - zmin ) / H - 0.05, ( zShoulder - zmin ) / H + 0.02 ) )

	def mean( vs ):
		return vscale( ( sum( v[0] for v in vs ), sum( v[1] for v in vs ), sum( v[2] for v in vs ) ), 1.0 / len( vs ) )
	def section_middle( side, z, near = None ):
		"""the middle of the side's outline where the mesh is cut at the
		height (each piece of it by its length), near a place if given; None
		if nothing's there"""
		sx = sy = sl = 0.0
		for t in tris:
			pts = []
			for a_, b_ in ( ( t[0], t[1] ), ( t[1], t[2] ), ( t[2], t[0] ) ):
				pa, pb = rest[a_], rest[b_]
				if ( pa[2] - z ) * ( pb[2] - z ) < 0:
					u = ( z - pa[2] ) / ( pb[2] - pa[2] )
					pts.append( ( pa[0] + u * ( pb[0] - pa[0] ), pa[1] + u * ( pb[1] - pa[1] ) ) )
			if len( pts ) != 2:
				continue
			mx, my = 0.5 * ( pts[0][0] + pts[1][0] ), 0.5 * ( pts[0][1] + pts[1][1] )
			if ( my - y0 ) * side <= 0 or ( near and math.hypot( mx - near[0], my - near[1] ) > 0.1 * H ):
				continue
			l = math.hypot( pts[0][0] - pts[1][0], pts[0][1] - pts[1][1] )
			sx, sy, sl = sx + mx * l, sy + my * l, sl + l
		return ( sx / sl, sy / sl, z ) if sl > 0 else None

	def leg( side, z ):
		if not TO_MODEL and LEGS == "placed":
			# the ankle is the shin's middle just over the foot (the foot's
			# reaches forward to the toes); higher, the leg goes from the
			# ankle in toward the pelvis, as Doom 3's legs splay (the hip half
			# as far out as the ankle, and over the pelvis front to back). At
			# the crotch's height the hanging hands are as far out as the
			# thighs (the fat worker's), and an average of the side would put
			# the hip in the hand
			if z <= zmin + 0.15 * H:
				# along the shin down to the ankle's height (a leg in a
				# stance slants: the shin's middle over the foot is behind
				# the ankle): the line through the middles of its outline
				# higher up, clear of the foot (a low-poly shin has hardly a
				# vertex between the ankle and the knee, its outline does)
				a, b = section_middle( side, zmin + 0.12 * H ), section_middle( side, zmin + 0.2 * H )
				if a and b:
					u = ( z - a[2] ) / ( b[2] - a[2] )
					return ( a[0] + u * ( b[0] - a[0] ), a[1] + u * ( b[1] - a[1] ), z )
			shin = [ v for v in rest if ( v[1] - y0 ) * side > 0 and zmin + 0.09 * H < v[2] < zmin + 0.15 * H ]
			# a low-poly shin may have no vertex there (the fat worker's):
			# then from the ankle on the shin's line
			a = mean( shin ) if shin else ( leg( side, zmin + 0.08 * H ) if z > zmin + 0.15 * H else None )
			if a:
				if z <= zmin + 0.15 * H:
					return ( a[0], a[1], z )
				u = max( 0.0, min( 1.0, ( z - zmin ) / max( 1e-3, zCrotch - zmin ) ) )
				return ( a[0] + u * ( x0 - a[0] ), y0 + ( 1.0 - 0.48 * u ) * ( a[1] - y0 ), z )
		vs = [ v for v in rest if ( v[1] - y0 ) * side > 0 and abs( v[2] - z ) < 0.05 * H ]
		if not vs:
			return ( x0, y0 + side * 0.1 * H, z )
		c = mean( vs )
		return ( c[0], c[1], z )
	def hand( side ):
		# the arm's outermost end, hanging at the side or held out
		vs = [ v for v in rest if ( v[1] - y0 ) * side > 0.55 * shoulderY and v[2] > zCrotch + 0.08 * H ]
		if not vs:
			return ( x0, y0 + side * shoulderY, zCrotch )
		far = sorted( vs, key = lambda v: -( v[1] - y0 ) * side )[:max( 3, len( vs ) // 15 )]
		return mean( far )

	def knee( side, hip, ankle ):
		"""where the leg bends: a character's first frame is often a stance,
		not an A- or T-pose (legs apart, one forward and bent), so the knee
		isn't at a height. Along the leg from the hip to the ankle, the side's
		vertexes under the crotch go in thin slabs (a low-poly leg is rings);
		the knee is the middle of the slabs in the leg's middle (30 to 60% of
		the way down: lower, a coat's hem or a boot's top stands out) that
		stand farthest forward of the straight line between them (the
		kneecap: knees point forward), else 45% of the way down (Daikatana's
		shins are long)"""
		d = vsub( ankle, hip )
		L2 = vdot( d, d )
		if L2 < 1e-6:
			return None
		slabs = {}
		for v in rest:
			if ( v[1] - y0 ) * side > 0 and zmin + 0.08 * H < v[2] < zCrotch:
				t = vdot( vsub( v, hip ), d ) / L2
				if 0.3 < t < 0.6:
					slabs.setdefault( int( t * 20 ), [] ).append( v )
		ahead = []
		for sv in slabs.values():
			if len( sv ) < 4:
				continue
			c = mean( sv )
			t = vdot( vsub( c, hip ), d ) / L2
			ahead.append( ( c[0] - ( hip[0] + t * d[0] ), sv ) )
		top = max( [ a for a, sv in ahead ] + [ 0.0 ] )
		if top < 0.02 * H:
			return vadd( hip, vscale( d, 0.45 ) )
		# the knee's height (its rings above and below the cap), and there the
		# middle of the leg, not the cap: the mesh cut at that height, the
		# middle of the outline about it (each piece of it by its length)
		cap = mean( [ v for a, sv in ahead if a >= 0.8 * top for v in sv ] )
		return section_middle( side, cap[2], cap ) or cap

	pos = {}
	pos["origin"] = ( x0, y0, zmin )
	pos["Hips"] = ( x0, y0, zCrotch + 0.06 * H )
	pos["Body"] = pos["Hips"]
	pos["Waist"] = ( x0, y0, zCrotch + 0.14 * H )
	pos["Chest"] = ( x0, y0, zCrotch + 0.55 * ( zShoulder - zCrotch ) )
	pos["Loneck"] = ( x0, y0, zNeck - 0.02 * H )
	pos["Head"] = ( x0, y0, zNeck + 0.03 * H )
	for side, s_ in ( ( 1, "L" ), ( -1, "R" ) ):
		pos[s_ + "upleg"] = leg( side, zCrotch + 0.02 * H )
		pos[s_ + "loleg"] = leg( side, zmin + 0.5 * ( zCrotch - zmin ) )
		pos[s_ + "ankle_r"] = leg( side, zmin + 0.08 * H )
		if not TO_MODEL and LEGS == "placed":
			# the hip level with the pelvis, the knee where the leg bends
			h = pos[s_ + "upleg"]
			pos[s_ + "upleg"] = ( h[0], h[1], pos["Hips"][2] )
			k = knee( side, pos[s_ + "upleg"], pos[s_ + "ankle_r"] )
			if k:
				pos[s_ + "loleg"] = k
		sh = ( x0, y0 + side * shoulderY, zShoulder )
		hd = gunHand if ( side < 0 and gunHand ) else hand( side )
		pos[s_ + "uparm"] = sh
		pos[s_ + "hand"] = hd
		pos[s_ + "loarm"] = vscale( vadd( sh, hd ), 0.5 )
	joints = []
	for name, parent, p, zone in D3_TEMPLATE:
		joints.append( { "name": name, "parent": parent, "zone": zone, "pos": pos[name] } )
	chain, hairIdx = hair_chain( rest, headVerts, pos["Head"] )
	joints += chain
	print( "  neck %.1f, shoulders %.1f (%.1f wide), crotch %.1f, feet %.1f" % ( zNeck, zShoulder, 2 * shoulderY, zCrotch, zmin ) )
	return joints, hairIdx

# --lying: model space from the space rigged in (stood up: x' = z, y' = y,
# z' = -x, the head up and the face forward); None standing
TO_MODEL = None

def stand_up( v ):
	return ( v[2], v[1], -v[0] )

def lie_down( v ):
	return ( -v[2], v[1], v[0] )

LIE_DOWN = [ [ 0.0, 0.0, -1.0 ], [ 0.0, 1.0, 0.0 ], [ 1.0, 0.0, 0.0 ] ]	# lie_down as a matrix

def to_model( v ):
	return TO_MODEL( v ) if TO_MODEL else v

# --name: a monster or another character, not a player: def/rig_<name>.def
# (model_<name>) and af/monster_<name>.af, its animations at --fps (else
# MONSTER_FPS) or as --anims says; None for a player character
# (def/char_<file>.def, af/char_<file>.af, player animations, a voice)
NAME = None
FPS = None
ANIMS = ""

# Daikatana plays its characters' animations at 20 frames a second
# (FRAMETIME_FPS20: client_init.cpp, bot.cpp, Sidekick.cpp)
ANIM_FPS = 20.0
# the animations that move the character over the ground (their speed measured)
MOVING_ANIMS = re.compile( r"^(run|walk|bwalk|cwalk)[ab]?$" )
SEAM = 0.3			# vertexes this near are one place
HAIR_BONES = 3		# at most

def hair_chain( rest, headVerts, head ):
	"""A ponytail's own little spine: the head surface's vertexes that hang
	behind the back of the skull are hair; bones run
	down its middle from where it leaves the head (Ponytail1, parented to the
	head) to its tip. Nothing when there's no such hair."""
	skull = sorted( rest[i][0] for i in headVerts if rest[i][2] > head[2] )
	if not skull:
		return [], set()
	# the back of the skull (the model faces x), from most of the head: hair
	# may hang from the crown (Mikiko's) or below the head (Hiro's)
	back = skull[len( skull ) // 6]
	hairIdx = set( i for i in headVerts if rest[i][0] < back - 1.5 )
	hair = [ rest[i] for i in hairIdx ]
	numBones = min( HAIR_BONES, len( hair ) // 6 )		# a bone needs vertexes to fit
	if numBones < 1:
		return [], set()
	top = max( v[2] for v in hair )
	rootVs = [ v for v in hair if v[2] > top - 1.0 ]
	root = vscale( ( sum( v[0] for v in rootVs ), sum( v[1] for v in rootVs ), sum( v[2] for v in rootVs ) ), 1.0 / len( rootVs ) )
	reach = max( vlen( vsub( v, root ) ) for v in hair )
	height = max( v[2] for v in rest ) - min( v[2] for v in rest )
	if reach < height / 8:
		return [], set()		# a bun or a bump, not a tail
	chain, parent = [], "Head"
	for k in range( numBones ):
		lo, hi = reach * k / numBones, reach * ( k + 0.5 ) / numBones
		band = [ v for v in hair if lo <= vlen( vsub( v, root ) ) <= hi ] if k else [ root ]
		p = vscale( ( sum( v[0] for v in band ), sum( v[1] for v in band ), sum( v[2] for v in band ) ), 1.0 / len( band ) ) \
			if band else vadd( root, vscale( vsub( chain[-1]["pos"], root ), 1.5 ) )
		name = "Ponytail%d" % ( k + 1 )
		chain.append( { "name": name, "parent": parent, "zone": "hair", "pos": p } )
		parent = name
	print( "  hair: %d vertexes, %.1f long, %d bones" % ( len( hair ), reach, numBones ) )
	return chain, hairIdx

EXTRA_BONES = 0		# --extra: at most this many bones for what the template doesn't carry
SURFACE = None		# --surface: "metal" for a robot, its hits spark
REST = None			# --rest: the animation whose first frame it's rigged from
LEGS = "placed"		# the legs' joints placed in the mesh, or "fitted": as the motion puts them (see main)
WRITE = True		# False: only how well it fits
EXTRA_ERROR = 0.02	# of the height: a vertex its bone carries worse than this, on average, is extra
EXTRA_MIN = 8		# vertexes: a smaller part stays on its bone

def extra_bones( rest, frames, tris, assign, joints, bones, motion, sample, pins, hairIdx, budget ):
	"""Bones for the mesh no template bone carries well: its pieces (joined by
	the mesh) are split by their motion until each moves rigidly, the biggest
	first; each becomes a bone on the one it meets most, the vertexes it
	carries better than their bones moving to it. Returns the new bones'
	joint indexes (joints, bones and assign are updated)"""
	N = len( rest )
	H = max( v[2] for v in rest ) - min( v[2] for v in rest )
	def err( i, mt ):
		return sum( vlen( vsub( xform( mt[f], rest[i] ), frames[f][i] ) ) for f in sample ) / len( sample )
	def fit( idx ):
		src = [ rest[i] for i in idx ]
		return { f: rigid_fit( src, [ frames[f][i] for i in idx ] ) for f in sample }
	adj = [ set() for i in range( N ) ]
	for t in tris:
		for p, q in ( ( t[0], t[1] ), ( t[1], t[2] ), ( t[2], t[0] ) ):
			adj[p].add( q )
			adj[q].add( p )
	# one place, one vertex (seams)
	place = {}
	for i, v in enumerate( rest ):
		place.setdefault( tuple( int( round( c / SEAM ) ) for c in v ), [] ).append( i )
	for ms in place.values():
		for i in ms:
			adj[i].update( k for k in ms if k != i )
	cur = [ err( i, motion[assign[i]] ) for i in range( N ) ]
	bad = set( i for i in range( N ) if cur[i] > EXTRA_ERROR * H and i not in pins and i not in hairIdx )
	def pieces( vs ):
		vs, out, seen = set( vs ), [], set()
		for s0 in vs:
			if s0 in seen:
				continue
			stack, piece = [ s0 ], []
			seen.add( s0 )
			while stack:
				v = stack.pop()
				piece.append( v )
				for n in adj[v]:
					if n in vs and n not in seen:
						seen.add( n )
						stack.append( n )
			out.append( piece )
		return out
	def split( idx ):
		"""two parts by motion: the two farthest apart seed them, each vertex to
		the part whose motion carries it best, a few rounds"""
		a = max( idx, key = lambda i: vlen( vsub( rest[i], rest[idx[0]] ) ) )
		b = max( idx, key = lambda i: vlen( vsub( rest[i], rest[a] ) ) )
		side = { i: vlen( vsub( rest[i], rest[a] ) ) < vlen( vsub( rest[i], rest[b] ) ) for i in idx }
		for it in range( 4 ):
			pa = [ i for i in idx if side[i] ]
			pb = [ i for i in idx if not side[i] ]
			if len( pa ) < 3 or len( pb ) < 3:
				return None
			ma, mb = fit( pa ), fit( pb )
			side = { i: err( i, ma ) <= err( i, mb ) for i in idx }
		parts = []
		for flag in ( True, False ):
			parts += pieces( [ i for i in idx if side[i] == flag ] )
		return parts
	# a separate piece of mesh (an arrow, a prop) is big enough from a triangle
	whole = {}
	for p in pieces( range( N ) ):
		for i in p:
			whole[i] = len( p )
	def big( p ):
		return len( p ) >= EXTRA_MIN or ( len( p ) >= 3 and whole[p[0]] == len( p ) )
	# the pieces, split until rigid (or too small to split)
	todo = [ p for p in pieces( bad ) if big( p ) ]
	parts = []
	while todo and len( parts ) + len( todo ) <= budget * 2:
		p = max( todo, key = len )
		todo.remove( p )
		mt = fit( p )
		mean = sum( err( i, mt ) for i in p ) / len( p )
		if mean < 0.5 * EXTRA_ERROR * H or len( p ) < 2 * EXTRA_MIN:
			parts.append( ( p, mt ) )
			continue
		halves = split( p )
		if not halves or len( halves ) < 2:
			parts.append( ( p, mt ) )
			continue
		for h in halves:
			if big( h ):
				todo.append( h )
	parts.sort( key = lambda pm: -len( pm[0] ) )
	added = []
	for idx, mt in parts:
		if len( added ) >= budget:
			break
		# the vertexes it carries better than their bones do (by a good margin)
		gain = [ i for i in idx if err( i, mt ) < 0.5 * cur[i] ]
		if not big( gain ):
			continue
		# on the bone it meets most (its old one, else a new one)
		meet = {}
		gs = set( gain )
		for i in gain:
			for n in adj[i]:
				if n not in gs:
					meet[assign[n]] = meet.get( assign[n], 0 ) + 1
		parent = max( meet, key = meet.get ) if meet else max( set( assign[i] for i in gain ), key = [ assign[i] for i in gain ].count )
		edge = [ rest[n] for i in gain for n in adj[i] if n not in gs and assign[n] == parent ]
		pos = vscale( ( sum( v[0] for v in edge ), sum( v[1] for v in edge ), sum( v[2] for v in edge ) ), 1.0 / len( edge ) ) if edge \
			else min( ( rest[i] for i in gain ), key = lambda v: vlen( vsub( v, joints[parent]["pos"] ) ) )
		pname = joints[parent]["name"]
		k = 1
		while any( j["name"] == "%s_%d" % ( pname, k ) for j in joints ):
			k += 1
		joints.append( { "name": "%s_%d" % ( pname, k ), "parent": pname, "parentIndex": parent,
						 "zone": joints[parent]["zone"], "pos": pos, "extra": True } )
		b = len( joints ) - 1
		bones.append( b )
		added.append( b )
		motion[b] = mt
		for i in gain:
			assign[i] = b
			cur[i] = err( i, mt )
	return added

# the hinges blended by place: ( upper bone, the hinge's bone, the one after
# it ), and how far the blend reaches either side of the joint (of the shorter
# bone's length)
HINGES = [ ( "Lupleg", "Lloleg", "Lankle_r" ), ( "Rupleg", "Rloleg", "Rankle_r" ),
		   ( "Luparm", "Lloarm", "Lhand" ), ( "Ruparm", "Rloarm", "Rhand" ) ]
HINGE_BAND = 0.3

def seg_dist( p, a, b ):
	ab = vsub( b, a )
	l2 = vdot( ab, ab )
	t = 0.0 if l2 < 1e-9 else max( 0.0, min( 1.0, vdot( vsub( p, a ), ab ) / l2 ) )
	return vlen( vsub( p, vadd( a, vscale( ab, t ) ) ) )

def plot_segments( rest, assign, joints, path ):
	"""An SVG of the rest frame from the front and the side, a colour a bone,
	and the joints (RIG_DEBUG=<file>)."""
	colours = [ "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6",
				"#bcf60c", "#fabebe", "#008080", "#e6beff", "#9a6324", "#800000", "#aaffc3", "#808000",
				"#ffd8b1", "#000075", "#808080", "#000000", "#ff00ff" ]
	zs = [ v[2] for v in rest ]
	sc = 380.0 / ( max( zs ) - min( zs ) + 10 )
	out = [ '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="420"><rect width="100%" height="100%" fill="white"/>' ]
	for view, ox in ( ( 0, 220 ), ( 1, 660 ) ):
		def proj( v ):
			a = -v[1] if view == 0 else v[0]
			return ox + a * sc, 400 - ( v[2] - min( zs ) ) * sc
		for i, v in enumerate( rest ):
			x, y = proj( v )
			out.append( '<circle cx="%.1f" cy="%.1f" r="2.5" fill="%s"/>' % ( x, y, colours[assign[i] % len( colours )] ) )
		for j, joint in enumerate( joints ):
			x, y = proj( joint["pos"] )
			out.append( '<rect x="%.1f" y="%.1f" width="7" height="7" fill="%s" stroke="black"/>' % ( x - 3.5, y - 3.5, colours[j % len( colours )] ) )
			out.append( '<text x="%.1f" y="%.1f" font-size="9">%s</text>' % ( x + 5, y, joint["name"] ) )
	out.append( "</svg>" )
	open( path, "w" ).write( "\n".join( out ) )

def cap_holes( sf ):
	"""Fills the triangle-sized holes in a surface (Hiro's back of the neck
	misses one): a loop of three open edges, its vertexes by place (the md3
	splits a vertex where its texture does), gets a triangle wound against
	its neighbours'."""
	rest = sf.frames[0]
	place = {}
	canon = [ place.setdefault( tuple( round( c * 4 ) for c in p ), i ) for i, p in enumerate( rest ) ]
	uses = {}
	for t in sf.triangles:
		for a, b in ( ( t[0], t[1] ), ( t[1], t[2] ), ( t[2], t[0] ) ):
			uses.setdefault( tuple( sorted( ( canon[a], canon[b] ) ) ), [] ).append( ( a, b ) )
	# an open edge's way round, reversed: the filler's
	back = {}
	for e, used in uses.items():
		if len( used ) == 1:
			a, b = used[0]
			back[canon[b]] = ( canon[a], b )		# from b's place to a's, b's own vertex
	added = 0
	for start in list( back ):
		loop, at = [], start
		while at in back and len( loop ) < 4:
			nxt, vert = back[at]
			loop.append( vert )
			at = nxt
			if at == start:
				break
		if len( loop ) == 3 and at == start:
			sf.triangles.append( tuple( loop ) )
			for k in loop:
				back.pop( canon[k], None )
			added += 1
	if added:
		print( "  %s: %d holes capped" % ( sf.name, added ) )

def load_pins( name, body, verts, J ):
	"""Vertexes pinned to bones by hand, tools/rig/skin/<name>.txt: lines of
	"<surface>:<index> <bone> [<blend bone> <weight>]" (the skin table's
	columns), # comments. Daikatana's data stays out: only numbers and names."""
	path = os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), "skin", name + ".txt" )
	pins = {}
	if not os.path.exists( path ):
		return pins
	index = { ( body[si].name, vi ): i for i, ( si, vi ) in enumerate( verts ) }
	for n, line in enumerate( open( path ), 1 ):
		w = line.split( "#" )[0].split()
		if not w:
			continue
		surf, _, vi = w[0].rpartition( ":" )
		i = index.get( ( surf, int( vi ) ) ) if surf else None
		if i is None or w[1] not in J or ( len( w ) >= 4 and w[2] not in J ):
			print( "  %s:%d: no vertex %s or bone %s" % ( path, n, w[0], " ".join( w[1:3] ) ) )
			continue
		pins[i] = ( J[w[1]], J[w[2]], float( w[3] ) ) if len( w ) >= 4 else ( J[w[1]], )
	print( "  %d vertexes pinned (%s)" % ( len( pins ), os.path.relpath( path ) ) )
	return pins

def main( md3Path, outBase ):
	m = MD3( md3Path )
	if REST:
		# rigged from that animation's first frame, as if it were the first
		# (a model whose first frame isn't standing: Toshiro's starts dead):
		# a copy of it goes first, its own one-frame animation "rest"
		rest = next( ( first for name, first, n in m.animations() if name == REST ), None )
		if rest is None:
			sys.exit( "%s: no animation %s" % ( md3Path, REST ) )
		m.frameNames.insert( 0, "rest" )
		m.numFrames += 1
		for sf in m.surfaces:
			sf.frames.insert( 0, list( sf.frames[rest + 1 - 1] ) )
	if TO_MODEL:
		for sf in m.surfaces:
			sf.frames = [ [ stand_up( v ) for v in frame ] for frame in sf.frames ]
	# the body: every surface but the hardpoints and the props
	m.surfaces = split_props( m.surfaces )
	body = [ s for s in m.surfaces if not is_hardpoint( s ) and not is_prop( s ) ]
	hps = [ s for s in m.surfaces if is_hardpoint( s ) ]
	props = [ s for s in m.surfaces if not is_hardpoint( s ) and is_prop( s ) ]
	verts = []		# [ ( surface index, vertex index ) ]
	for si, s in enumerate( body ):
		verts += [ ( si, vi ) for vi in range( s.numVerts ) ]
	N, F = len( verts ), m.numFrames
	frames = [ [ body[si].frames[f][vi] for si, vi in verts ] for f in range( F ) ]
	rest = frames[0]
	print( "%s: %d vertexes, %d frames" % ( md3Path, N, F ) )

	gunHand = None
	for hp in hps:
		if HARDPOINTS.get( hp.name, ( None, None ) )[1] == "Rhand":
			gunHand = vscale( vadd( vadd( hp.frames[0][0], hp.frames[0][1] ), hp.frames[0][2] ), 1.0 / 3 )
	for sf in body:
		cap_holes( sf )
	base, tris = {}, []
	for k, ( si, vi ) in enumerate( verts ):
		base.setdefault( si, k )
	for si, sf in enumerate( body ):
		tris += [ ( base[si] + a, base[si] + b, base[si] + c ) for a, b, c in sf.triangles ]
	headVerts = [ i for i, ( si, vi ) in enumerate( verts ) if "head" in body[si].name.lower() ]
	def tri_name( t ):
		a, b, c = tris[t]
		return "%s:%d-%d-%d" % ( body[verts[a][0]].name, verts[a][1], verts[b][1], verts[c][1] )
	headPoint = next( ( vscale( vadd( vadd( hp.frames[0][0], hp.frames[0][1] ), hp.frames[0][2] ), 1.0 / 3 )
					   for hp in hps if hp.name == "hp_head" ), None )
	joints, hairIdx = place_template( rest, tris, headVerts, gunHand, headPoint )
	placed = [ j["pos"] for j in joints ]
	J = { j["name"]: i for i, j in enumerate( joints ) }
	pins = load_pins( os.path.basename( outBase ), body, verts, J )
	for j in joints:
		j["parentIndex"] = J[j["parent"]] if j["parent"] else -1
	children = { i: [ k for k, j in enumerate( joints ) if j["parentIndex"] == i ] for i in range( len( joints ) ) }
	bones = [ i for i, j in enumerate( joints ) if j["zone"] ]

	# 1. first split: the nearest bone (from its joint toward its first child)
	def bone_segment( i ):
		a = joints[i]["pos"]
		kids = [ k for k in children[i] if not joints[k].get( "extra" ) ]	# an extra bone leaves its parent's be
		if kids:
			# toward the middle of its children
			b = vscale( ( sum( joints[k]["pos"][0] for k in kids ), sum( joints[k]["pos"][1] for k in kids ),
						  sum( joints[k]["pos"][2] for k in kids ) ), 1.0 / len( kids ) )
		else:
			# an end: on past the joint, half as long as the parent's bone
			p = joints[joints[i]["parentIndex"]]["pos"]
			b = vadd( a, vscale( vsub( a, p ), 0.6 ) )
		return a, b
	segs = { i: bone_segment( i ) for i in bones }

	# the hair's bones carry only the hair, and the hair only them, the head
	# or the neck
	hairBones = set( b for b in bones if joints[b]["zone"] == "hair" )
	def allowed( i, b ):
		if not hairBones:
			return True
		if i in hairIdx:
			return b in hairBones or joints[b]["name"] in ( "Head", "Loneck" )
		return b not in hairBones
	def allowed_bones( i, among ):
		return [ b for b in among if allowed( i, b ) ] or [ assign[i] ]

	assign = []
	for i, v in enumerate( rest ):
		assign.append( min( [ b for b in bones if allowed( i, b ) ], key = lambda b: seg_dist( v, *segs[b] ) ) )

	# frames to fit with (all of them takes long and adds little)
	sample = list( range( 0, F, 3 ) )

	def fit_bones( frameList ):
		"""Each bone's rigid motion from the rest frame to the frames."""
		motion = {}
		for b in bones:
			idx = [ i for i in range( N ) if assign[i] == b ]
			motion[b] = idx
		out = {}
		for b in bones:
			idx = motion[b]
			if len( idx ) < 4:
				out[b] = None
				continue
			src = [ rest[i] for i in idx ]
			out[b] = { f: rigid_fit( src, [ frames[f][i] for i in idx ] ) for f in frameList }
		# a bone with too few vertexes moves with its parent
		for b in bones:
			if out[b] is None:
				p = joints[b]["parentIndex"]
				while p >= 0 and ( p not in out or out[p] is None ):
					p = joints[p]["parentIndex"]
				out[b] = out[p] if p >= 0 else { f: ( IDENT, ( 0, 0, 0 ) ) for f in frameList }
		return out

	def neighbours( b ):
		n = set( [ b ] + children[b] )
		p = joints[b]["parentIndex"]
		if p >= 0 and joints[p]["zone"]:
			n.add( p )
			n.update( children[p] )
		return [ x for x in n if x in bones ]

	# 2. split again by which bone carries each vertex best; parts that move
	# together (chest and neck) are near ties, so nearness to the bone counts too
	SPATIAL = 0.15
	JOINT_MOVE = 0.1	# of the height: how far a joint goes from the template's place
	BAD_FIT = 4.0		# units off, on average, for a vertex to look further
	for it in range( 4 ):
		motion = fit_bones( sample )
		changed = 0
		def fit( i, b ):
			err = SPATIAL * len( sample ) * seg_dist( rest[i], *segs[b] ) ** 2
			for f in sample:
				d = vsub( xform( motion[b][f], rest[i] ), frames[f][i] )
				err += vdot( d, d )
			return err
		for i in range( N ):
			best, bestErr = assign[i], None
			candidates = neighbours( assign[i] )
			# one its bone carries badly (a hip vertex the hanging hand took)
			# may belong to any: every bone is tried
			if fit( i, assign[i] ) > len( sample ) * BAD_FIT ** 2:
				candidates = bones
			candidates = allowed_bones( i, candidates )
			for b in candidates:
				err = fit( i, b )
				if bestErr is None or err < bestErr:
					best, bestErr = b, err
			if best != assign[i]:
				assign[i] = best
				changed += 1
		print( "  split %d: %d vertexes moved" % ( it + 1, changed ) )
		if changed < N * 0.002:
			break

	# a leg's vertexes by where they are along it: the animations hardly bend
	# the knees, so the motion can't tell a thigh from its shin, but the walk
	# IK bends them, and a thigh skinned to the shin stretches
	legChains = [ [ J[s_ + n] for n in ( "upleg", "loleg", "ankle_r" ) ] for s_ in ( "L", "R" ) ]
	for chain in legChains:
		for i in range( N ):
			if assign[i] in chain:
				assign[i] = min( chain, key = lambda c: seg_dist( rest[i], *segs[c] ) )
	# and what no leg bone carries (a hand hanging against the thigh) goes
	# to the bone that does
	motion = fit_bones( sample )
	for i in range( N ):
		if any( assign[i] in chain for chain in legChains ) and fit( i, assign[i] ) > len( sample ) * BAD_FIT ** 2:
			assign[i] = min( allowed_bones( i, bones ), key = lambda b: fit( i, b ) )
	# a head that never turns on its body (a helmet, a mane) the motion can't
	# tell from the chest: it's the mesh over the neck, but what the arms carry
	if NAME and assign.count( J["Head"] ) < EXTRA_MIN:
		H0 = max( v[2] for v in rest ) - min( v[2] for v in rest )
		hp = joints[J["Head"]]["pos"]
		for i, v in enumerate( rest ):
			if v[2] > joints[J["Loneck"]]["pos"][2] and math.hypot( v[0] - hp[0], v[1] - hp[1] ) < 0.15 * H0 \
					and joints[assign[i]]["zone"] in ( "torso", "head" ):
				assign[i] = J["Head"]
		print( "  head: %d vertexes over the neck" % assign.count( J["Head"] ) )

	# and what's pinned by hand
	for i, pin in pins.items():
		assign[i] = pin[0]

	# what the template has no bone for (a cape, wings, a held sword, more
	# arms): the mesh no bone carries gets bones of its own, as the creature
	# rigger finds them (EXTRA_BONES at most)
	if EXTRA_BONES:
		motion = fit_bones( sample )
		added = extra_bones( rest, frames, tris, assign, joints, bones, motion, sample, pins, hairIdx, EXTRA_BONES )
		if added:
			children = { i: [ k for k, j in enumerate( joints ) if j["parentIndex"] == i ] for i in range( len( joints ) ) }
			J = { j["name"]: i for i, j in enumerate( joints ) }
			for b in added:
				segs[b] = bone_segment( b )
			print( "  extra bones: %s" % ", ".join( "%s(%d, on %s)" % ( joints[b]["name"], assign.count( b ), joints[b]["parent"] ) for b in added ) )
	motion = fit_bones( range( F ) )
	if os.environ.get( "RIG_DEBUG" ):
		plot_segments( rest, assign, joints, os.environ["RIG_DEBUG"] )

	# 3. joints where parent and child agree
	H = max( v[2] for v in rest ) - min( v[2] for v in rest )
	for b in bones:
		p = joints[b]["parentIndex"]
		if p < 0 or p not in motion:
			continue
		p0 = joints[b]["pos"]
		a = [ [ 0.0 ] * 3 for r in range( 3 ) ]
		rhs = [ 0.0 ] * 3
		for f in sample:
			rp, tp = motion[p][f]
			rc, tc = motion[b][f]
			d = [ [ rp[r][c] - rc[r][c] for c in range( 3 ) ] for r in range( 3 ) ]
			e = vsub( tc, tp )
			for r in range( 3 ):
				for c in range( 3 ):
					a[r][c] += sum( d[k][r] * d[k][c] for k in range( 3 ) )
				rhs[r] += sum( d[k][r] * e[k] for k in range( 3 ) )
		# a hinge (the knee, the elbow) agrees all along its axis: along a
		# direction the motion hardly pins down the template's place stays,
		# else the joint slides off sideways; and it never goes far from it
		vals, vecs = eigen3( a )
		top = max( vals )
		r0 = vsub( rhs, mvec( a, p0 ) )
		x = p0
		for val, vec in zip( vals, vecs ):
			if val > 0.05 * top:
				x = vadd( x, vscale( vec, vdot( vec, r0 ) / val ) )
		# the hips (balls) the motion pins well, and the IK turns the thighs
		# about them: a wrong pivot stretches the skin at the pelvis. A knee
		# it may slide down the shin: kept in the leg's middle, else the
		# template's height (halfway); an ankle at the template's height
		name = joints[b]["name"]
		if name.endswith( "loleg" ):
			hipZ = joints[joints[b]["parentIndex"]]["pos"][2]
			ankleZ = joints[children[b][0]]["pos"][2] if children[b] else p0[2]
			if not ( ankleZ + 0.3 * ( hipZ - ankleZ ) <= x[2] <= ankleZ + 0.7 * ( hipZ - ankleZ ) ):
				x = ( x[0], x[1], p0[2] )
		elif name.endswith( "ankle_r" ):
			x = ( x[0], x[1], p0[2] )
		elif name.endswith( "upleg" ) and not TO_MODEL and LEGS == "placed":
			# a hip stays on its side (the motion pinned Hiro's right one
			# across his middle): how far out is the legs' placing's
			x = ( x[0], p0[1], x[2] )
		move = vsub( x, p0 )
		if vlen( move ) > JOINT_MOVE * H:
			x = vadd( p0, vscale( move, JOINT_MOVE * H / vlen( move ) ) )
		joints[b]["pos"] = x
	# the legs where the placing put them: the motion pins a hip's height
	# badly (Hiro's came out 7 apart, one under his crotch) and hardly a
	# knee's (Daikatana's animations hardly bend them). The hips level with
	# the pelvis, the knees where the legs bend, the ankles on the shins' line.
	# Where the animations do bend the knees (the skinny worker's), the
	# motion knows better: LEGS "fitted" leaves the legs to it (main() is run
	# both ways, the better kept)
	if not TO_MODEL and LEGS == "placed":
		for s_ in ( "L", "R" ):
			hip, knee_ = J[s_ + "upleg"], J[s_ + "loleg"]
			x = joints[hip]["pos"]
			joints[hip]["pos"] = ( x[0], x[1], joints[J["Hips"]]["pos"][2] )
			joints[knee_]["pos"] = placed[knee_]
			joints[J[s_ + "ankle_r"]]["pos"] = placed[J[s_ + "ankle_r"]]
	# Body sits on the hips, the root at the floor under it
	joints[J["Body"]]["pos"] = joints[J["Hips"]]["pos"]
	zmin = min( v[2] for v in rest )
	joints[J["origin"]]["pos"] = ( joints[J["Hips"]]["pos"][0], joints[J["Hips"]]["pos"][1], zmin )
	motion[J["Body"]] = motion[J["Hips"]]

	# 4. two weights a vertex: its bone, and a neighbour where blending fits
	weights = []
	for i in range( N ):
		b = assign[i]
		best = ( b, b, 1.0, None )
		for o in allowed_bones( i, neighbours( b ) ):
			# one leg's vertex never follows the other: the walk IK moves
			# them apart, which the animations never do
			if o == b or joints[o]["name"][1:] == joints[b]["name"][1:] and joints[b]["zone"] == "legs":
				continue
			# along a leg, blending only near the joint between the two
			# bones: a thigh half on its shin stretches when the IK bends
			chain = next( ( c for c in legChains if b in c and o in c ), None )
			if chain:
				shared = joints[o]["pos"] if joints[o]["parentIndex"] == b else joints[b]["pos"]
				length = vlen( vsub( *segs[b] ) )
				if vlen( vsub( rest[i], shared ) ) > 0.25 * length:
					continue
			num = den = 0.0
			err1 = 0.0
			for f in sample:
				a = xform( motion[b][f], rest[i] )
				c = xform( motion[o][f], rest[i] )
				tgt = frames[f][i]
				ac = vsub( a, c )
				num += vdot( ac, vsub( tgt, c ) )
				den += vdot( ac, ac )
			w = 1.0 if den < 1e-9 else max( 0.5, min( 1.0, num / den ) )
			err = 0.0
			for f in sample:
				a = xform( motion[b][f], rest[i] )
				c = xform( motion[o][f], rest[i] )
				p = vadd( vscale( a, w ), vscale( c, 1 - w ) )
				d = vsub( p, frames[f][i] )
				err += vdot( d, d )
			if best[3] is None or err < best[3]:
				best = ( b, o, w, err )
		if i in pins:
			best = pins[i] if len( pins[i] ) == 3 else ( pins[i][0], pins[i][0], 1.0 )
		weights.append( best[:3] )

	# the knees and the elbows by where the vertexes are: blended across the
	# joint over a band about it, smoothly, so the limb keeps its volume as it
	# bends (fitted to Daikatana's frames, which hardly bend them, the blend
	# lands off the joint and the limb thins where it bends)
	for upper, hinge, lower in HINGES:
		if not all( n in J for n in ( upper, hinge ) ):
			continue
		P, C = J[upper], J[hinge]
		c, a = joints[C]["pos"], joints[P]["pos"]
		d = joints[J[lower]]["pos"] if lower in J else vadd( c, vsub( c, a ) )
		up, down = vnorm( vsub( c, a ) ), vnorm( vsub( d, c ) )
		axis = vnorm( vadd( up, down ) )
		h = HINGE_BAND * min( vlen( vsub( c, a ) ), vlen( vsub( d, c ) ) )
		for i in range( N ):
			b, o, w = weights[i]
			if b not in ( P, C ) or o not in ( P, C ) or i in pins:
				continue
			t = min( 1.0, max( 0.0, ( vdot( vsub( rest[i], c ), axis ) + h ) / ( 2 * h ) ) )
			wc = t * t * ( 3 - 2 * t )
			weights[i] = ( C, P, wc ) if wc >= 0.5 else ( P, C, 1 - wc )
			assign[i] = weights[i][0]

	# an arm's vertexes are what's joined to its shoulder: a hand resting on a
	# thigh (Usagi's) is near the thigh, and moves with it in most frames,
	# but the thigh's vertexes are the leg's (joined to it by the mesh). A
	# piece that isn't, but is joined to another bone's, goes to the bone
	# nearest it that isn't the arm's
	adjv = [ set() for i in range( N ) ]
	for a, b, c in tris:
		for p, q in ( ( a, b ), ( b, c ), ( c, a ) ):
			adjv[p].add( q )
			adjv[q].add( p )
	at = {}
	for i, v in enumerate( rest ):
		at.setdefault( tuple( int( round( c / SEAM ) ) for c in v ), [] ).append( i )
	for same in at.values():
		for i in same:
			adjv[i].update( k for k in same if k != i )
	moved = 0
	for side in "LR":
		arm = set( j for j, jt in enumerate( joints ) if jt["zone"] == "arms" and jt["name"].startswith( side ) )
		if side + "uparm" not in J:
			continue
		mine = set( i for i in range( N ) if weights[i][0] in arm )
		if not mine:
			continue
		# from the vertexes nearest the shoulder, through the arm's
		shoulder = joints[J[side + "uparm"]]["pos"]
		start = min( mine, key = lambda i: vlen( vsub( rest[i], shoulder ) ) )
		seen, todo = { start }, [ start ]
		while todo:
			v = todo.pop()
			for n in adjv[v]:
				if n in mine and n not in seen:
					seen.add( n )
					todo.append( n )
		# the rest, a piece at a time: off the arm if the mesh joins it to
		# what isn't the arm's (a separate piece, a glove, stays)
		rest_ = mine - seen
		while rest_:
			piece, todo = set(), [ rest_.pop() ]
			while todo:
				v = todo.pop()
				piece.add( v )
				for n in adjv[v]:
					if n in rest_:
						rest_.discard( n )
						todo.append( n )
			if not any( n not in mine for v in piece for n in adjv[v] ):
				continue
			for i in piece:
				if i in pins:
					continue
				b = min( ( b for b in bones if b not in arm and allowed( i, b ) ), key = lambda b: seg_dist( rest[i], *segs[b] ) )
				weights[i] = ( b, b, 1.0 )
				assign[i] = b
				moved += 1
	if moved:
		print( "  %d vertexes not joined to their arm off it" % moved )

	# the seams: vertexes of different surfaces in one place (Hiro's head on
	# his neck) skin alike, or a pose the animations never had (the head
	# pitched to aim) opens a hole between them. A group takes whichever of
	# its members' weights carries all of them best
	def skin_err( i, wt ):
		b, o, w = wt
		err = 0.0
		for f in sample:
			p = xform( motion[b][f], rest[i] )
			if w < 1.0:
				p = vadd( vscale( p, w ), vscale( xform( motion[o][f], rest[i] ), 1 - w ) )
			d = vsub( p, frames[f][i] )
			err += vdot( d, d )
		return err
	welded = 0
	seen = set()
	for i in range( N ):
		if i in seen:
			continue
		group = [ k for k in range( N ) if vlen( vsub( rest[k], rest[i] ) ) < SEAM ]
		seen.update( group )
		if len( set( verts[k][0] for k in group ) ) < 2 or len( set( weights[k] for k in group ) ) < 2:
			continue
		best = min( set( weights[k] for k in group ), key = lambda wt: sum( skin_err( k, wt ) for k in group ) )
		for k in group:
			weights[k] = best
		welded += 1
	if welded:
		print( "  %d seams welded" % welded )

	# the error of the skinned frames
	total = maxErr = 0.0
	count = 0
	worst = []
	vertErr = [ [ 0.0, 0.0 ] for i in range( N ) ]
	flips = {}		# triangle -> frames it faces the other way from Daikatana's
	for f in range( F ):
		skinned = [ None ] * N
		for i in range( N ):
			b, o, w = weights[i]
			p = xform( motion[b][f], rest[i] )
			if w < 1.0:
				p = vadd( vscale( p, w ), vscale( xform( motion[o][f], rest[i] ), 1 - w ) )
			skinned[i] = p
			e = vlen( vsub( p, frames[f][i] ) )
			if e > 6 and os.environ.get( "RIG_WORST" ):
				worst.append( ( e, f, i ) )
			total += e
			maxErr = max( maxErr, e )
			vertErr[i][0] += e / F
			vertErr[i][1] = max( vertErr[i][1], e )
			count += 1
		# a triangle turned over shows its back, and is culled: a hole
		for t, ( a, b, c ) in enumerate( tris ):
			n0 = vcross( vsub( frames[f][b], frames[f][a] ), vsub( frames[f][c], frames[f][a] ) )
			n1 = vcross( vsub( skinned[b], skinned[a] ), vsub( skinned[c], skinned[a] ) )
			if vdot( n0, n1 ) < 0 and vlen( n0 ) > 0.01:
				flips[t] = flips.get( t, 0 ) + 1
	if flips:
		print( "  %d triangles turn over in some frames, the most: %s" % ( len( flips ), ", ".join(
			"%s %d/%d" % ( tri_name( t ), n, F ) for t, n in sorted( flips.items(), key = lambda x: -x[1] )[:int( os.environ.get( "RIG_FLIPS", 6 ) )] ) ) )
	if worst:
		names = [ ( a[0], a[1], a[1] + a[2] ) for a in m.animations() ]
		byVert = {}
		for e, f, i in worst:
			byVert.setdefault( i, [] ).append( ( e, f ) )
		for i in sorted( byVert, key = lambda i: -max( byVert[i] )[0] )[:12]:
			e, f = max( byVert[i] )
			anim = next( ( n for n, a, b in names if a <= f < b ), "?" )
			b, o, w = weights[i]
			print( "  vertex %d: %.1f off in %s (frame %d, %d frames over 6), %s/%s %.2f, rest %s" % ( i, e, anim, f, len( byVert[i] ),
				joints[b]["name"], joints[o]["name"], w, tuple( round( c ) for c in rest[i] ) ) )
	print( "  error: %.3f units on average, %.2f at most (the character is %.0f tall)" % ( total / count, maxErr,
		max( v[2] for v in rest ) - zmin ) )
	if not WRITE:
		return total / count

	# the skin table: every vertex's bones, and how well they carry it
	with open( outBase + "_skin.txt", "w" ) as fp:
		fp.write( "# %s's skin (tools/rig/autorig.py): a vertex a line; pin one in tools/rig/skin/%s.txt\n"
				  % ( os.path.basename( outBase ), os.path.basename( outBase ) ) )
		fp.write( "# vertex  surface:index  bone  blend  weight  mean_error  max_error  rest_x rest_y rest_z  pinned\n" )
		for i, ( si, vi ) in enumerate( verts ):
			b, o, w = weights[i]
			fp.write( "%4d  %s:%d  %s  %s  %.2f  %.2f  %.2f  %.1f %.1f %.1f%s\n" % ( i, body[si].name, vi, joints[b]["name"],
				joints[o]["name"] if w < 1.0 else "-", w, vertErr[i][0], vertErr[i][1], *rest[i], "  pinned" if i in pins else "" ) )
	print( "  wrote %s_skin.txt" % outBase )

	# 5. hardpoints as attachment joints
	for joint, jm in hardpoint_joints( hps, joints, motion, bones, F, sample ):
		joints.append( joint )
		motion[len( joints ) - 1] = jm
		print( "  hardpoint %s on %s" % ( joint["name"], joint["parent"] ) )
	motion[J["origin"]] = { f: ( IDENT, ( 0, 0, 0 ) ) for f in range( F ) }

	# 6. props as joints of their own, their vertexes all theirs
	for joint, jm, js, prest in prop_joints( props, joints, motion, bones, F ):
		joints.append( joint )
		j = len( joints ) - 1
		motion[j], PROP_SCALE[j] = jm, js
		si = len( body )
		body.append( next( sf for sf in props if sf.name == joint["name"] ) )
		for vi in range( body[-1].numVerts ):
			verts.append( ( si, vi ) )
			rest.append( prest[vi] )
			weights.append( ( j, j, 1.0 ) )
			assign.append( j )
		print( "  prop %s on %s, hidden in %d frames" % ( joint["name"], joint["parent"], sum( 1 for v in js.values() if v < 0.1 ) ) )

	write_outputs( m, body, verts, rest, joints, motion, weights, assign, outBase )
	return total / count

def gamePath( path ):
	"""The path the game sees: from the data folder (dkres) on."""
	path = os.path.normpath( path ).replace( os.sep, "/" )
	for top in ( "dkres/", "characters/" ):
		i = path.find( top )
		if i >= 0:
			return path[i + ( len( top ) if top == "dkres/" else 0 ):]
	return path

# ------------------------------------------------------------------------
# the ragdoll: a Doom 3 articulated figure (af/char_<name>.af, the game's
# bg_afdecl.c), made in the bind pose (the rest above): boxes for the waist,
# the chest and the head, bones for the limbs, as Doom 3's human figures;
# universal joints with cone limits for the waist, the neck, the shoulders and
# the hips, hinges for the elbows and the knees

def rodrigues( v, axis, angle ):
	"""v turned by angle (radians) about axis, right handed"""
	c, s = math.cos( angle ), math.sin( angle )
	return vadd( vadd( vscale( v, c ), vscale( vcross( axis, v ), s ) ), vscale( axis, vdot( axis, v ) * ( 1 - c ) ) )

def d3_orthogonal_basis( v ):
	"""idVec3::OrthogonalBasis: left, up"""
	x, y, z = v
	if abs( z ) > 0.7:
		l = y * y + z * z
		s = 1.0 / math.sqrt( l )
		up = ( 0.0, z * s, -y * s )
		left = ( l * s, -x * up[2], x * up[1] )
	else:
		l = x * x + y * y
		s = 1.0 / math.sqrt( l )
		left = ( -y * s, x * s, 0.0 )
		up = ( -z * left[1], z * left[0], l * s )
	return left, up

def d3_rotation_angle( axis, frm, to ):
	"""the angle a for which Doom 3's frm * idRotation( axis, a ) points as to
	(its rotations turn vectors the other way round: by -a, right handed)"""
	a = math.atan2( vdot( axis, vcross( frm, to ) ), vdot( frm, to ) )
	return -math.degrees( a )

def ragdoll_af( name, joints, rest, assign, afName = None ):
	J = { joint["name"]: j for j, joint in enumerate( joints ) }
	if any( n not in J for n in ( "Hips", "Waist", "Chest", "Loneck", "Head", "Luparm", "Lloarm", "Lhand",
								  "Ruparm", "Rloarm", "Rhand", "Lupleg", "Lloleg", "Lankle_r", "Rupleg", "Rloleg", "Rankle_r" ) ):
		return None
	P = lambda n: joints[J[n]]["pos"]
	def pts( names ):
		return [ rest[i] for i in range( len( rest ) ) if joints[assign[i]]["name"] in names ]
	H = max( v[2] for v in rest ) - min( v[2] for v in rest )
	def box( names, shrink = 0.85 ):
		ps = pts( names )
		if len( ps ) < 8:
			# a bone with few vertexes of its own (a pelvis skinned to the
			# thighs): the body about its joint
			c = P( names[0] )
			ps = [ v for v in rest if vlen( vsub( v, c ) ) < 0.1 * H ]
			if not ps:
				# nothing near it (a joint the fit left in a gap): its nearest
				ps = sorted( rest, key = lambda v: vlen( vsub( v, c ) ) )[:8]
		lo = [ min( p[k] for p in ps ) for k in range( 3 ) ]
		hi = [ max( p[k] for p in ps ) for k in range( 3 ) ]
		c = [ 0.5 * ( lo[k] + hi[k] ) for k in range( 3 ) ]
		h = [ max( 1.0, 0.5 * ( hi[k] - lo[k] ) * shrink ) for k in range( 3 ) ]
		if len( pts( names ) ) < 8:
			# a pelvis at least (thick, wide, tall, of the height)
			h = [ max( h[0], 0.06 * H ), max( h[1], 0.08 * H ), max( h[2], 0.05 * H ) ]
		return c, h
	def width( names, a, b ):
		d = vsub( b, a )
		L = vlen( d )
		ds = []
		for p in pts( names ):
			t = max( 0.0, min( 1.0, vdot( vsub( p, a ), d ) / ( L * L ) ) )
			ds.append( vlen( vsub( p, vadd( a, vscale( d, t ) ) ) ) )
		ds.sort()
		return max( 2.0, 2 * 0.9 * ds[int( 0.7 * ( len( ds ) - 1 ) )] ) if ds else 3.0
	def vec( v ):
		return "( %.2f, %.2f, %.2f )" % tuple( to_model( v ) )
	def raw( v ):
		return "( %.2f, %.2f, %.2f )" % tuple( v )
	def end_of( names, a, b ):
		"""where the limb's vertexes reach past b along a->b"""
		d = vnorm( vsub( b, a ) )
		ps = pts( names )
		reach = max( [ vdot( vsub( p, b ), d ) for p in ps ] + [ 1.0 ] )
		return vadd( b, vscale( d, 0.8 * reach ) )

	lines = [ "// made by tools/rig/autorig.py: %s's ragdoll, Doom 3's articulated figure" % name,
			  "// (made in the model's bind pose; joint() and bone*() name the IQM's joints)",
			  "articulatedFigure %s {" % ( afName or "char_" + name ),
			  "	settings {",
			  "		model \"model_%s\"" % name,
			  "		friction 0.01, 0.01, 0.8, 0.5",
			  "		suspendSpeed 20, 30, 40, 60",
			  "		noMoveTime 1",
			  "		noMoveTranslation 10",
			  "		noMoveRotation 10",
			  "		minMoveTime -1",
			  "		maxMoveTime -1",
			  "		totalMass -1",
			  "		contents corpse",
			  "		clipMask solid, corpse",
			  "		selfCollision 1",
			  "	}", "" ]
	def body_box( bname, joint, names, mod = "orientation" ):
		c, h = box( names )
		if TO_MODEL:
			h = [ abs( x ) for x in to_model( h ) ]		# the box's extents turned with it
		lines.extend( [ "	body \"%s\" {" % bname,
						"		joint \"%s\"" % joint,
						"		mod %s" % mod,
						"		model box( ( %.2f, %.2f, %.2f ), ( %.2f, %.2f, %.2f ) )" % ( -h[0], -h[1], -h[2], h[0], h[1], h[2] ),
						"		origin %s" % vec( c ),
						"		density 0.2",
						"		friction 0.01, 0.01, 0.8",
						"		contents corpse",
						"		clipMask solid, corpse",
						"		selfCollision 1",
						"	}", "" ] )
	J_ = { j["name"]: j for j in joints }
	hips = vlen( vsub( J_["Lupleg"]["pos"], J_["Rupleg"]["pos"] ) ) if "Lupleg" in J_ and "Rupleg" in J_ else None
	def body_bone( bname, joint, names, a, b ):
		w = width( names[:1], a, b )		# the limb's own vertexes, not a hand's or a foot's
		# not much fatter than it's long, nor a leg wider than the hips are
		# apart: a robe round Toshiro's thighs made them 12 wide, each deep in
		# the other, and the figure stood stuck
		w = min( w, max( 2.0, 0.7 * vlen( vsub( b, a ) ) ) )
		if hips and names[0].endswith( ( "upleg", "loleg" ) ):
			w = min( w, max( 2.0, 0.9 * hips ) )
		# the body clear of the floor it stands on: one in it at the start is
		# stuck there (Doom 3's AF rests a body it can't get out), and the
		# figure with it, standing (Toshiro's thick legs)
		floor = min( v[2] for v in rest ) + 0.5 * w + 0.5
		if b[2] < floor:
			b = ( b[0], b[1], floor )
		lines.extend( [ "	body \"%s\" {" % bname,
						"		joint \"%s\"" % joint,
						"		mod orientation",
						"		model bone( %s, %s, %.2f )" % ( vec( a ), vec( b ), w ),
						"		origin %s" % vec( vscale( vadd( a, b ), 0.5 ) ),
						"		density 0.2",
						"		friction 0.01, 0.01, 0.8",
						"		contents corpse",
						"		clipMask solid, corpse",
						"		selfCollision 1",
						"	}", "" ] )

	body_box( "waist", "origin", ( "Hips", "Body" ) )
	body_box( "chest", "Waist", ( "Waist", "Chest" ) )
	body_box( "head", "Loneck", ( "Loneck", "Head" ) )
	for s in "LR":
		hand = end_of( ( s + "hand", ), P( s + "loarm" ), P( s + "hand" ) )
		ps = pts( ( s + "ankle_r", ) )
		foot = ( P( s + "ankle_r" )[0], P( s + "ankle_r" )[1], min( p[2] for p in ps ) + 2 ) if ps else P( s + "ankle_r" )
		body_bone( s + "uparm", s + "uparm", ( s + "uparm", ), P( s + "uparm" ), P( s + "loarm" ) )
		body_bone( s + "loarm", s + "loarm", ( s + "loarm", s + "hand" ), P( s + "loarm" ), hand )
		body_bone( s + "upleg", s + "upleg", ( s + "upleg", ), P( s + "upleg" ), P( s + "loleg" ) )
		body_bone( s + "loleg", s + "loleg", ( s + "loleg", s + "ankle_r" ), P( s + "loleg" ), foot )

	def universal( cname, body1, body2, anchor, shaft, cone, angle, friction = 0.2 ):
		lines.extend( [ "	universalJoint \"%s\" {" % cname,
						"		body1 \"%s\"" % body1,
						"		body2 \"%s\"" % body2,
						"		anchor joint( \"%s\" )" % anchor,
						"		shafts %s, %s" % ( vec( shaft ), vec( vscale( shaft, -1 ) ) ),
						"		friction %.2f" % friction,
						"		coneLimit %s, %.0f" % ( vec( vnorm( cone ) ), angle ),
						"	}", "" ] )
	def hinge( cname, body1, body2, anchor, axis, straight, forward, bend, friction = 0.2 ):
		"""body1 turns about axis from straight to bend degrees towards forward"""
		# in model space: the game takes the limit's reference from the axis
		axis, straight, forward = to_model( vnorm( axis ) ), to_model( straight ), to_model( forward )
		flat = lambda v: vnorm( vsub( v, vscale( axis, vdot( v, axis ) ) ) )
		straight = flat( straight )
		sign = 1.0 if vdot( rodrigues( straight, axis, 0.1 ), forward ) > vdot( straight, forward ) else -1.0
		bisector = rodrigues( straight, axis, sign * math.radians( bend * 0.5 ) )
		left, up = d3_orthogonal_basis( axis )
		a0 = d3_rotation_angle( axis, left, bisector )
		a2 = d3_rotation_angle( axis, left, straight )
		lines.extend( [ "	hinge \"%s\" {" % cname,
						"		body1 \"%s\"" % body1,
						"		body2 \"%s\"" % body2,
						"		anchor joint( \"%s\" )" % anchor,
						"		axis %s" % raw( axis ),
						"		friction %.2f" % friction,
						"		limit %.1f, %.1f, %.1f" % ( a0, bend + 10, a2 ),
						"	}", "" ] )

	universal( "waistChest", "chest", "waist", "Waist", ( 0, 0, 1 ), ( 0, 0, 1 ), 60 )
	universal( "chestHead", "head", "chest", "Loneck", ( 0, 0, 1 ), ( 0, 0, 1 ), 80 )
	for s, side in ( ( "L", 1.0 ), ( "R", -1.0 ) ):
		arm = vnorm( vsub( P( s + "loarm" ), P( s + "uparm" ) ) )
		universal( s + "shoulder", s + "uparm", "chest", s + "uparm", arm, ( 0.0, 0.4 * side, -1.0 ), 170 )
		hinge( s + "elbow", s + "loarm", s + "uparm", s + "loarm", ( 0, 1, 0 ), arm, ( 1, 0, 0 ), 140 )
		leg = vnorm( vsub( P( s + "loleg" ), P( s + "upleg" ) ) )
		universal( s + "hip", s + "upleg", "waist", s + "upleg", leg, ( 0.5, 0.15 * side, -0.85 ), 120 )
		hinge( s + "knee", s + "loleg", s + "upleg", s + "loleg", ( 0, 1, 0 ), leg, ( -1, 0, 0 ), 130 )
	lines += [ "}", "" ]
	return "\n".join( lines )

def write_iqm( m, body, verts, rest, joints, motion, weights, outBase, looping = None, fps = None ):
	"""The skeletal IQM: joints, the skin, every frame a pose, the animations
	named by the frames' names (looping: those that loop, fps their rate).
	Returns the animations and the joints' rest rotations."""
	looping = looping or LOOPING
	fps = fps or ANIM_FPS
	N, F = len( verts ), m.numFrames
	nj = len( joints )

	# rest orientations along the bones, as Half-Life's and Doom 3's rest:
	# x down the bone (to the child, or on from the parent at an end), z as
	# near up as it can be; so hitboxes fitted in the joint's space hug the limb
	kids = { j: [ k for k in range( nj ) if joints[k]["parentIndex"] == j and joints[k]["zone"]
				 and ( joints[k]["zone"] != "hair" or joints[j]["zone"] == "hair" )
				 and ( not joints[k].get( "extra" ) or joints[j].get( "extra" ) ) ] for j in range( nj ) }
	restRot = []
	for j in range( nj ):
		p = joints[j]["pos"]
		if not joints[j]["zone"]:
			restRot.append( IDENT )
			continue
		if kids[j]:
			c = vscale( ( sum( joints[k]["pos"][0] for k in kids[j] ), sum( joints[k]["pos"][1] for k in kids[j] ),
						  sum( joints[k]["pos"][2] for k in kids[j] ) ), 1.0 / len( kids[j] ) )
			d = vsub( c, p )
		else:
			d = vsub( p, joints[joints[j]["parentIndex"]]["pos"] )
		x = vnorm( d )
		if vlen( x ) < 0.5:
			restRot.append( IDENT )
			continue
		up = ( 0.0, 0.0, 1.0 ) if abs( x[2] ) < 0.9 else ( 1.0, 0.0, 0.0 )
		z = vnorm( vsub( up, vscale( x, vdot( up, x ) ) ) )
		y = vcross( z, x )
		restRot.append( [ [ x[0], y[0], z[0] ], [ x[1], y[1], z[1] ], [ x[2], y[2], z[2] ] ] )

	# joint world transforms a frame: the bone's motion, about the joint
	def world( j, f ):
		r, t = motion[j][f]
		p = joints[j]["pos"]
		return mmul( r, restRot[j] ), xform( ( r, t ), p )		# rotation, the joint's place
	locals_ = []	# [frame][joint] = ( translate, quat )
	for f in range( F ):
		row = []
		for j in range( nj ):
			r, o = world( j, f )
			pi = joints[j]["parentIndex"]
			if pi < 0:
				row.append( ( to_model( o ), mat_to_quat( mmul( LIE_DOWN, r ) if TO_MODEL else r ) ) )
				continue
			pr, po = world( pi, f )
			prt = mtrans( pr )
			lr = mmul( prt, r )
			lt = mvec( prt, vsub( o, po ) )
			row.append( ( lt, mat_to_quat( lr ) ) )
		locals_.append( row )

	# rest: joints at their places, on their bones, relative to their parents
	restLocal = []
	for j in range( nj ):
		pi = joints[j]["parentIndex"]
		p = joints[j]["pos"]
		if pi < 0:
			restLocal.append( ( to_model( p ), mat_to_quat( mmul( LIE_DOWN, restRot[j] ) if TO_MODEL else restRot[j] ) ) )
			continue
		prt = mtrans( restRot[pi] )
		restLocal.append( ( mvec( prt, vsub( p, joints[pi]["pos"] ) ), mat_to_quat( mmul( prt, restRot[j] ) ) ) )

	# mesh: one IQM mesh a surface, vertexes in the order above
	positions, normals, texcoords, blendIdx, blendWt, tangents, tris, meshes = [], [], [], [], [], [], [], []
	vbase = 0
	vi_global = 0
	for si, s in enumerate( body ):
		first_tri = len( tris )
		vnormals = [ ( 0.0, 0.0, 0.0 ) ] * s.numVerts
		for a, b, c in s.triangles:
			# md3 triangles wind clockwise seen from outside
			n = vcross( vsub( rest[vbase + c], rest[vbase + a] ), vsub( rest[vbase + b], rest[vbase + a] ) )
			for k in ( a, b, c ):
				vnormals[k] = vadd( vnormals[k], n )
		for vi in range( s.numVerts ):
			g = vbase + vi
			positions.append( to_model( rest[g] ) )
			n = vnorm( vnormals[vi] )
			normals.append( to_model( n ) if vlen( n ) > 0 else ( 0, 0, 1 ) )
			texcoords.append( s.st[vi] )
			t = to_model( vnorm( vcross( n, ( 0, 0, 1 ) ) ) if abs( n[2] ) < 0.9 else ( 1.0, 0.0, 0.0 ) )
			tangents.append( ( t[0], t[1], t[2], 1.0 ) )
			b, o, w = weights[g]
			wb = int( round( w * 255 ) )
			blendIdx.append( ( b, o, 0, 0 ) )
			blendWt.append( ( wb, 255 - wb, 0, 0 ) )
		for a, b, c in s.triangles:
			# the same winding as the md3's (the engine draws both alike)
			tris.append( ( vbase + a, vbase + b, vbase + c ) )
		meshes.append( ( s.name, s.shader or "skins/default", vbase, s.numVerts, first_tri, len( s.triangles ) ) )
		vbase += s.numVerts

	anims = m.animations()
	text = b"\0"
	def addtext( s ):
		nonlocal text
		o = len( text )
		text += s.encode() + b"\0"
		return o
	meshText = [ ( addtext( n ), addtext( mat ) ) for n, mat, *_ in meshes ]
	jointText = [ addtext( j["name"] ) for j in joints ]
	animText = [ addtext( a[0] ) for a in anims ]
	while len( text ) % 4:
		text += b"\0"

	# poses, quantised per channel
	chans = []
	for j in range( nj ):
		vals = [ list( locals_[f][j][0] ) + list( locals_[f][j][1] ) + [ PROP_SCALE.get( j, {} ).get( f, 1.0 ) ] * 3 for f in range( F ) ]
		offs, scales = [], []
		for c in range( 10 ):
			col = [ v[c] for v in vals ]
			lo, hi = min( col ), max( col )
			offs.append( lo )
			scales.append( ( hi - lo ) / 65535.0 if hi > lo else 0.0 )
		chans.append( ( vals, offs, scales ) )
	framedata = bytearray()
	for f in range( F ):
		for j in range( nj ):
			vals, offs, scales = chans[j]
			for c in range( 10 ):
				v = 0 if scales[c] == 0 else int( round( ( vals[f][c] - offs[c] ) / scales[c] ) )
				framedata += struct.pack( "<H", max( 0, min( 65535, v ) ) )
	while len( framedata ) % 4:
		framedata += b"\0"

	sections = []
	ofs = 124
	def place( data ):
		nonlocal ofs
		o = ofs
		sections.append( ( o, data ) )
		ofs += len( data )
		return o
	ofs_text = place( text )
	ofs_meshes = place( b"".join( struct.pack( "<6I", meshText[k][0], meshText[k][1], meshes[k][2], meshes[k][3], meshes[k][4], meshes[k][5] ) for k in range( len( meshes ) ) ) )
	arrays = [
		( 0, 7, 3, b"".join( struct.pack( "<3f", *p ) for p in positions ) ),
		( 1, 7, 2, b"".join( struct.pack( "<2f", *t ) for t in texcoords ) ),
		( 2, 7, 3, b"".join( struct.pack( "<3f", *n ) for n in normals ) ),
		( 3, 7, 4, b"".join( struct.pack( "<4f", *t ) for t in tangents ) ),
		( 4, 1, 4, b"".join( struct.pack( "<4B", *b ) for b in blendIdx ) ),
		( 5, 1, 4, b"".join( struct.pack( "<4B", *w ) for w in blendWt ) ),
	]
	ofs_va = ofs
	ofs += 20 * len( arrays )
	vaheaders = b""
	for vtype, fmt, size, data in arrays:
		vaheaders += struct.pack( "<5I", vtype, 0, fmt, size, ofs )
		place( data )
	sections.append( ( ofs_va, vaheaders ) )
	ofs_tris = place( b"".join( struct.pack( "<3I", *t ) for t in tris ) )
	ofs_joints = place( b"".join( struct.pack( "<Ii3f4f3f", jointText[j], joints[j]["parentIndex"], *restLocal[j][0], *restLocal[j][1], 1, 1, 1 ) for j in range( nj ) ) )
	ofs_poses = place( b"".join( struct.pack( "<iI10f10f", joints[j]["parentIndex"], 0x3ff, *chans[j][1], *chans[j][2] ) for j in range( nj ) ) )
	ofs_anims = place( b"".join( struct.pack( "<IIIfI", animText[k], a[1], a[2], fps, 1 if looping.match( a[0] ) else 0 ) for k, a in enumerate( anims ) ) )
	ofs_frames = place( bytes( framedata ) )
	xs = [ p[0] for p in positions ]; ys = [ p[1] for p in positions ]; zs = [ p[2] for p in positions ]
	bounds = ( min( xs ) - 8, min( ys ) - 8, min( zs ) - 4, max( xs ) + 8, max( ys ) + 8, max( zs ) + 4 )
	r = max( abs( c ) for c in bounds )
	ofs_bounds = place( b"".join( struct.pack( "<8f", *bounds, r, r ) for _ in range( F ) ) )

	header = b"INTERQUAKEMODEL\0" + struct.pack( "<27I", 2, ofs, 0,
		len( text ), ofs_text, len( meshes ), ofs_meshes,
		len( arrays ), len( positions ), ofs_va,
		len( tris ), ofs_tris, 0,
		nj, ofs_joints, nj, ofs_poses,
		len( anims ), ofs_anims,
		F, nj * 10, ofs_frames, ofs_bounds,
		0, 0, 0, 0 )
	out = bytearray( ofs )
	out[0:124] = header
	for o, data in sections:
		out[o:o + len( data )] = data
	os.makedirs( os.path.dirname( outBase ) or ".", exist_ok = True )
	with open( outBase + ".iqm", "wb" ) as fp:
		fp.write( out )
	print( "  wrote %s.iqm: %d joints, %d animations" % ( outBase, nj, len( anims ) ) )
	return anims, restRot

def write_outputs( m, body, verts, rest, joints, motion, weights, assign, outBase ):
	N = len( verts )
	spec, looping = anim_spec( ANIMS, FPS or MONSTER_FPS, MONSTER_LOOPING ) if NAME else ( {}, None )
	fps = ( FPS or MONSTER_FPS ) if NAME else ANIM_FPS
	anims, restRot = write_iqm( m, body, verts, rest, joints, motion, weights, outBase, looping, fps )

	# the model def: animations and hitboxes fitted to each bone's vertexes
	name = NAME or os.path.basename( outBase )
	prefix = "rig_" if NAME else "char_"
	afName = ( "monster_" if NAME else "char_" ) + name

	# the collision box, Doom 3's "mins"/"maxs": the body standing (its idle),
	# legs, torso and head, not the arms (the hitboxes have those); square
	# about the origin, as the box doesn't turn with the character. Crouched,
	# its top in the crouched idle; the eyes a little under the top
	animAt = { a[0]: a for a in anims }
	def pose_extent( animNames ):
		a = next( ( animAt[n] for n in animNames if n in animAt ), None )
		frames = range( a[1], a[1] + a[2] ) if a else range( 1 )
		pts = [ body[si].frames[f][vi] for f in frames for i, ( si, vi ) in enumerate( verts )
				if joints[assign[i]]["zone"] in ( "legs", "torso", "head" ) ]
		half = max( max( abs( p[0] ), abs( p[1] ) ) for p in pts )
		return half, min( p[2] for p in pts ), max( p[2] for p in pts )
	half, bottom, top = pose_extent( [ "amb", "aamb", "amba" ] )
	_, _, crouchTop = pose_extent( [ "camb", "acamb" ] )
	if not any( n in animAt for n in ( "camb", "acamb" ) ):
		crouchTop = top		# it doesn't crouch
	if TO_MODEL:
		# lying: the box about the body as it lies
		lying = [ to_model( v ) for v in rest ]
		half = max( max( abs( v[0] ), abs( v[1] ) ) for v in lying )
		bottom, top = min( v[2] for v in lying ), max( v[2] for v in lying )
		crouchTop = top
	tall = top - bottom
	eye = top - 0.09 * tall			# Doom 3's player: eyes 68 of 74
	crouchEye = crouchTop - 0.09 * tall
	# the walk IK's waist never closer to the higher ankle than this: on a
	# slope the box stands on its uphill edge, and the waist dropping to the
	# feet below folds the other leg into a squat
	Jn = { joint["name"]: j for j, joint in enumerate( joints ) }
	minWaistAnkle = 0.85 * ( joints[Jn["Body"]]["pos"][2]
							 - 0.5 * ( joints[Jn["Lankle_r"]]["pos"][2] + joints[Jn["Rankle_r"]]["pos"][2] ) )
	lines = [ "// made by tools/rig/autorig.py from %s" % m.path.split( "dkres/" )[-1],
			  "entityDef model_%s {" % name,
			  "\t\"inherit\"\t\t\t\"character_base\"\t// def/dk_characters.def",
			  "\t\"mesh\"\t\t\t\t\"%s.iqm\"" % gamePath( outBase ),
			  "\t\"mins\"\t\t\t\t\"%.0f %.0f %.0f\"\t// standing, at the origin (pmove's)" % ( -half, -half, bottom ),
			  "\t\"maxs\"\t\t\t\t\"%.0f %.0f %.0f\"" % ( half, half, top ),
			  "\t\"crouch_height\"\t\t\"%.0f\"\t\t// maxs z crouched" % crouchTop,
			  "\t\"eye_height\"\t\t\"%.0f\"" % eye,
			  "\t\"crouch_eye_height\"\t\"%.0f\"" % crouchEye,
			  "\t\"ik_minWaistAnkleDist\"\t\"%.0f\"\t// the walk IK's waist drops no lower (Doom 3's)" % minWaistAnkle ]
	if SURFACE:
		lines.append( "\t\"surface\"\t\t\t\"%s\"\t// Doom 3's surface type: its hits spark, no blood" % SURFACE )
	lines.append( "" )
	seen = set()
	for a in anims:
		if a[0] in seen:
			continue
		seen.add( a[0] )
		if NAME:
			afps, loop = spec.get( a[0], ( fps, looping.match( a[0] ) ) )
			lines.append( "\t\"anim %s\"\t\t\"%s %g%s\"" % ( a[0], a[0], afps, " loop" if loop else "" ) )
		else:
			lines.append( "\t\"anim %s\"\t\t\"%s\"" % ( a[0], a[0] ) )
	lines.append( "" )

	# footsteps: where each foot comes down, once a cycle: its sole (the
	# lowest vertex of its bone) the first frame after its highest that it's
	# in the bottom quarter of its swing
	J = { joint["name"]: j for j, joint in enumerate( joints ) }
	steps = {}
	stepVolume = {}
	for a in anims:
		volumes = [ v for r, v in FOOTSTEP_ANIMS if r.match( a[0] ) ]
		if not volumes or a[0] in steps:
			continue
		stepVolume[a[0]] = volumes[0]
		steps[a[0]] = {}
		for foot in FOOTSTEP_JOINTS:
			if foot not in J:
				continue
			sole = [ verts[i] for i in range( N ) if assign[i] == J[foot] ]
			if not sole:
				continue
			z = [ min( body[si].frames[a[1] + k][vi][2] for si, vi in sole ) for k in range( a[2] ) ]
			lo, hi = min( z ), max( z )
			if hi - lo < 1:
				continue
			low = lo + ( hi - lo ) / 4
			top = z.index( hi )
			for k in range( 1, a[2] + 1 ):
				i = ( top + k ) % a[2]		# the anim loops
				if z[i] <= low:
					steps[a[0]].setdefault( i, [] ).append( foot )
					break
	for anim in steps:
		for i in sorted( steps[anim] ):
			# one command a frame: both feet down at once step once
			volume = "" if stepVolume[anim] == 1.0 else " %g" % stepVolume[anim]
			lines.append( "\t\"frame %s %d\"\t\"footstep %s%s\"" % ( anim, i, steps[anim][i][0], volume ) )
	lines.append( "" )
	# how fast each moving animation goes over the ground at its rate: each
	# foot's sole (its lowest third) reaches forward and back by a step a
	# cycle, two steps a cycle; the game plays the legs faster or slower to
	# match the player's speed ("anim_speed")
	for a in anims:
		if not MOVING_ANIMS.match( a[0] ) or a[2] < 2:
			continue
		reach = []
		for foot in FOOTSTEP_JOINTS:
			vs = [ i for i in range( N ) if assign[i] == J[foot] ]
			if not vs:
				continue
			xs = []
			for k in range( a[2] ):
				pts = sorted( ( body[verts[i][0]].frames[a[1] + k][verts[i][1]] for i in vs ), key = lambda p: p[2] )
				pts = pts[:max( 3, len( pts ) // 3 )]
				xs.append( sum( p[0] for p in pts ) / len( pts ) )
			reach.append( max( xs ) - min( xs ) )
		if reach:
			speed = 2 * sum( reach ) / len( reach ) / ( a[2] / spec.get( a[0], ( fps, ) )[0] )
			lines.append( "\t\"anim_speed %s\"\t\"%.0f\"" % ( a[0], speed ) )
	lines.append( "" )

	# swimming: the body lies along the stroke; the game puts its middle (the
	# swim animation's vertexes' on average) at the player's
	if "swim" in animAt:
		a = animAt["swim"]
		pts = [ body[verts[i][0]].frames[a[1] + k][verts[i][1]] for i in range( N ) for k in range( 0, a[2], 2 ) ]
		lines.append( "\t\"swim_center\"\t\t\"%.1f %.1f %.1f\"\t// the swimming body's middle" % tuple(
			sum( p[c] for p in pts ) / len( pts ) for c in range( 3 ) ) )
		lines.append( "" )

	# the ladder: how far a cycle of climbing climbs (the body rises as fast
	# as the holding hands and feet go down it, which they do in place), and
	# how far ahead the hands hold it
	if "ladderup" in animAt:
		a = animAt["ladderup"]
		limbs = [ [ i for i in range( N ) if assign[i] == J[l] ] for l in ( "Lhand", "Rhand", "Lankle_r", "Rankle_r" ) ]
		def limb_z( vs, f ):
			return sum( body[verts[i][0]].frames[f][verts[i][1]][2] for i in vs ) / len( vs )
		rise = 0.0
		for k in range( a[2] ):
			f0, f1 = a[1] + k, a[1] + ( k + 1 ) % a[2]
			down = [ limb_z( vs, f0 ) - limb_z( vs, f1 ) for vs in limbs if vs ]
			holding = [ d for d in down if d > 0 ]
			rise += sum( holding ) / len( holding ) if holding else 0.0
		hands = [ i for vs in limbs[:2] for i in vs ]
		reach = sum( body[verts[i][0]].frames[a[1] + k][verts[i][1]][0] for i in hands for k in range( a[2] ) ) / ( len( hands ) * a[2] )
		lines.append( "\t\"ladder_climb\"\t\t\"%.1f\"\t// a cycle of ladderup climbs this (rungs half as far apart)" % rise )
		lines.append( "\t\"ladder_reach\"\t\t\"%.1f\"\t// the hands this far ahead" % reach )
		lines.append( "" )
	soundKeys, soundShaders = character_sounds( name ) if not NAME else ( [], "" )
	lines += soundKeys
	lines.append( "" )
	if soundShaders:
		os.makedirs( "sound", exist_ok = True )
		with open( os.path.join( "sound", "char_%s.sndshd" % name ), "w" ) as fp:
			fp.write( soundShaders )
	for j, joint in enumerate( joints ):
		if not joint["zone"] or joint["zone"] == "hair":
			continue		# the hair has none: shots go through it
		# the bone's vertexes in its joint's (rotated) space
		rt = mtrans( restRot[j] )
		pts = [ mvec( rt, vsub( rest[i], joint["pos"] ) ) for i in range( N ) if assign[i] == j ]
		if len( pts ) < 4:
			continue
		lo = [ min( p[k] for p in pts ) for k in range( 3 ) ]
		hi = [ max( p[k] for p in pts ) for k in range( 3 ) ]
		lines.append( "\t\"hitbox %s\"\t\"%.1f %.1f %.1f %.1f %.1f %.1f %s\"" % ( joint["name"], *lo, *hi, joint["zone"] ) )
	lines += [ "", "\t\"damage_scale head\"\t\"2\"", "\t\"damage_scale arms\"\t\"0.75\"", "\t\"damage_scale legs\"\t\"0.75\"" ]
	af = ragdoll_af( name, joints, rest, assign, afName )
	if af:
		os.makedirs( "af", exist_ok = True )
		with open( os.path.join( "af", "%s.af" % afName ), "w" ) as fp:
			fp.write( af )
		lines += [ "", "\t\"ragdoll\"\t\t\t\"%s\"\t// af/%s.af, Doom 3's articulated figure" % ( afName, afName ) ]
	# as a player model: Quake 3's animations (pmove's) to Daikatana's, the
	# first of each list the character has
	lines.append( "" )
	for q3, candidates in PLAYER_ANIMS if not NAME else []:
		for c in candidates:
			anim, hold = ( c.split() + [ "" ] )[:2]
			if anim in seen:
				lines.append( "\t\"player_anim %s\"\t\"%s\"" % ( q3, c ) )
				break
	lines += [ "}", "" ]
	os.makedirs( "def", exist_ok = True )
	defPath = os.path.join( "def", "%s%s.def" % ( prefix, name ) )
	with open( defPath, "w" ) as fp:
		fp.write( "\n".join( lines ) )
	print( "  wrote %s" % defPath )

if __name__ == "__main__":
	args = sys.argv[1:]
	if args and args[0] == "--lying":
		TO_MODEL = lie_down
		args = args[1:]
	for opt, var, kind in ( ( "--name", "NAME", str ), ( "--fps", "FPS", float ), ( "--anims", "ANIMS", str ),
							( "--extra", "EXTRA_BONES", int ), ( "--surface", "SURFACE", str ), ( "--rest", "REST", str ) ):
		if opt in args:
			i = args.index( opt )
			globals()[var] = kind( args[i + 1] )
			args = args[:i] + args[i + 2:]
	if len( args ) != 2:
		print( __doc__ )
		sys.exit( 1 )
	if TO_MODEL:
		main( args[0], args[1] )
	else:
		# the legs both ways, placed in the mesh and fitted to the motion:
		# whichever carries the frames better
		WRITE = False
		errs = {}
		for LEGS in ( "fitted", "placed" ):
			print( "legs %s:" % LEGS )
			errs[LEGS] = main( args[0], args[1] )
		LEGS = min( errs, key = errs.get )
		WRITE = True
		print( "legs %s (%s), rigging:" % ( LEGS, ", ".join( "%s %.3f" % kv for kv in sorted( errs.items() ) ) ) )
		main( args[0], args[1] )
