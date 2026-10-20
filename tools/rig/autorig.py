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
 5. Daikatana's hardpoints (hp_gun, ctf_flag: a triangle each) become rigid
    attachment joints, as Doom 3's *_ATTACHER joints.
The joints' rest frames are the mesh's first frame; every frame of the MD3
becomes a pose, its animations (named by the frame names) the IQM's.

	python3 tools/rig/autorig.py dkres/models/global/m_hiro.md3 dkres/models/rigged/hiro
writes dkres/models/rigged/hiro.iqm and def/char_hiro.def (the model def,
with hitboxes fitted to the bones) and prints how far the skinned frames
are from the original ones. ./dk rig runs it for the characters.

Pure Python (no numpy): a few minutes for a character.
"""
import math
import os
import re
import struct
import sys

sys.path.insert( 0, os.path.dirname( __file__ ) )
from md3 import MD3

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

def place_template( rest, tris, headVerts, gunHand = None ):
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
	def leg( side, z ):
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

# Daikatana plays its characters' animations at 20 frames a second
# (FRAMETIME_FPS20: client_init.cpp, bot.cpp, Sidekick.cpp)
ANIM_FPS = 20.0
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
	# the body: every surface but the hardpoints
	body = [ s for s in m.surfaces if s.name not in HARDPOINTS ]
	hps = [ s for s in m.surfaces if s.name in HARDPOINTS ]
	verts = []		# [ ( surface index, vertex index ) ]
	for si, s in enumerate( body ):
		verts += [ ( si, vi ) for vi in range( s.numVerts ) ]
	N, F = len( verts ), m.numFrames
	frames = [ [ body[si].frames[f][vi] for si, vi in verts ] for f in range( F ) ]
	rest = frames[0]
	print( "%s: %d vertexes, %d frames" % ( md3Path, N, F ) )

	gunHand = None
	for hp in hps:
		if HARDPOINTS[hp.name][1] == "Rhand":
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
	joints, hairIdx = place_template( rest, tris, headVerts, gunHand )
	J = { j["name"]: i for i, j in enumerate( joints ) }
	pins = load_pins( os.path.basename( outBase ), body, verts, J )
	for j in joints:
		j["parentIndex"] = J[j["parent"]] if j["parent"] else -1
	children = { i: [ k for k, j in enumerate( joints ) if j["parentIndex"] == i ] for i in range( len( joints ) ) }
	bones = [ i for i, j in enumerate( joints ) if j["zone"] ]

	# 1. first split: the nearest bone (from its joint toward its first child)
	def bone_segment( i ):
		a = joints[i]["pos"]
		kids = children[i]
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
	# and what's pinned by hand
	for i, pin in pins.items():
		assign[i] = pin[0]
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
		move = vsub( x, p0 )
		if vlen( move ) > JOINT_MOVE * H:
			x = vadd( p0, vscale( move, JOINT_MOVE * H / vlen( move ) ) )
		joints[b]["pos"] = x
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
	for s in hps:
		name, parent = HARDPOINTS[s.name]
		c = vscale( vadd( vadd( s.frames[0][0], s.frames[0][1] ), s.frames[0][2] ), 1.0 / 3 )
		joints.append( { "name": name, "parent": parent, "parentIndex": J[parent], "zone": None, "pos": c } )
		motion[len( joints ) - 1] = { f: rigid_fit( s.frames[0], s.frames[f] ) for f in range( F ) }
	motion[J["origin"]] = { f: ( IDENT, ( 0, 0, 0 ) ) for f in range( F ) }

	write_outputs( m, body, verts, rest, joints, motion, weights, assign, outBase )

def gamePath( path ):
	"""The path the game sees: from the data folder (dkres) on."""
	path = os.path.normpath( path ).replace( os.sep, "/" )
	for top in ( "dkres/", "characters/" ):
		i = path.find( top )
		if i >= 0:
			return path[i + ( len( top ) if top == "dkres/" else 0 ):]
	return path

def write_outputs( m, body, verts, rest, joints, motion, weights, assign, outBase ):
	N, F = len( verts ), m.numFrames
	nj = len( joints )

	# rest orientations along the bones, as Half-Life's and Doom 3's rest:
	# x down the bone (to the child, or on from the parent at an end), z as
	# near up as it can be; so hitboxes fitted in the joint's space hug the limb
	kids = { j: [ k for k in range( nj ) if joints[k]["parentIndex"] == j and joints[k]["zone"]
				 and ( joints[k]["zone"] != "hair" or joints[j]["zone"] == "hair" ) ] for j in range( nj ) }
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
				row.append( ( o, mat_to_quat( r ) ) )
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
			restLocal.append( ( p, mat_to_quat( restRot[j] ) ) )
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
			positions.append( rest[g] )
			n = vnorm( vnormals[vi] )
			normals.append( n if vlen( n ) > 0 else ( 0, 0, 1 ) )
			texcoords.append( s.st[vi] )
			t = vnorm( vcross( n, ( 0, 0, 1 ) ) ) if abs( n[2] ) < 0.9 else ( 1.0, 0.0, 0.0 )
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
		vals = [ list( locals_[f][j][0] ) + list( locals_[f][j][1] ) + [ 1.0, 1.0, 1.0 ] for f in range( F ) ]
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
	ofs_anims = place( b"".join( struct.pack( "<IIIfI", animText[k], a[1], a[2], ANIM_FPS, 1 if LOOPING.match( a[0] ) else 0 ) for k, a in enumerate( anims ) ) )
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

	# the model def: animations and hitboxes fitted to each bone's vertexes
	name = os.path.basename( outBase )

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
	half, bottom, top = pose_extent( [ "amb", "aamb" ] )
	_, _, crouchTop = pose_extent( [ "camb", "acamb" ] )
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
			  "\t\"ik_minWaistAnkleDist\"\t\"%.0f\"\t// the walk IK's waist drops no lower (Doom 3's)" % minWaistAnkle,
			  "" ]
	seen = set()
	for a in anims:
		if a[0] in seen:
			continue
		seen.add( a[0] )
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
	soundKeys, soundShaders = character_sounds( name )
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
	# as a player model: Quake 3's animations (pmove's) to Daikatana's, the
	# first of each list the character has
	lines.append( "" )
	for q3, candidates in PLAYER_ANIMS:
		for c in candidates:
			anim, hold = ( c.split() + [ "" ] )[:2]
			if anim in seen:
				lines.append( "\t\"player_anim %s\"\t\"%s\"" % ( q3, c ) )
				break
	lines += [ "}", "" ]
	defPath = os.path.join( "def", "char_%s.def" % name )
	with open( defPath, "w" ) as fp:
		fp.write( "\n".join( lines ) )
	print( "  wrote %s" % defPath )

if __name__ == "__main__":
	if len( sys.argv ) != 3:
		print( __doc__ )
		sys.exit( 1 )
	main( sys.argv[1], sys.argv[2] )
