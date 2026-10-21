#!/usr/bin/env python3
"""
Puts a Daikatana cinematic model's animations (c_<name>_<map>.md3, vertex
animated, a model of its own for each cutscene) on a character rigged by
tools/rig/autorig.py, the walking Daikatana baked into them taken out.

How:
 1. The rig (dkres/models/rigged/<character>.iqm): its joints and rest pose,
    the mesh's base pose (the global model's first frame) and its skin.
 2. The cinematic mesh isn't the global one (other vertexes, other surfaces),
    but it's the same character, on the same textures: its frame nearest the
    rig's base pose is the reference, and each of its vertexes takes the skin
    of the rig's vertex at the same place on the texture (on the same side,
    for a texture mirrored left and right), or else nearest it there (a
    head's from the head). Hardpoints (a triangle) are left out.
 3. Each joint's motion a frame: the rigid motion (weighted by the skin) of
    its vertexes from the reference frame to that one, after the motion that
    takes the rig's base pose to the reference frame (so the rig takes the
    cinematic's pose, not its own a little apart). A joint with too few
    vertexes (an end, an attacher) keeps its rest pose on its parent; Body
    moves with the hips, the origin never (as autorig's).
 4. Root motion out: in each animation the root's (Body, the hips') going
    over the ground and the feet's turning about the vertical (the hips twist
    when the sword swings; the feet turn when the character does) since the
    animation's first frame are taken off every frame, so it plays in place; rising and falling,
    pitching and rolling (sitting down, getting up) stay. What's taken off is
    written down, for the game to move the character by.
 5. <out base>.iqm: the character's mesh and skeleton as they are (it draws
    as <character>.iqm), the character's own animations as they are (an actor
    walking in a cutscene plays its walk), then the cinematic's (the md3's
    names, "c_" before one the character has already; 10 frames a second,
    looping those named amb...); <out base>.json: what was taken out of each
    animation, and its name in the IQM.

	python3 tools/rig/retarget.py hiro dkres/models/cinematic/c_hiro_e1m1.md3 dkres/models/rigged/hiro_e1m1
	python3 tools/rig/retarget.py --ppm /tmp/look 0,25,50 hiro dkres/models/cinematic/c_hiro_e1m1.md3 dkres/models/rigged/hiro_e1m1
--ppm draws those frames to <prefix>_<frame>.ppm, front and side: the
cinematic's vertexes red, the rig skinned with the root motion green, played
in place blue. --no-align leaves the rig's own pose at the reference frame.

Pure Python (no numpy): a few seconds to a minute a model.
"""
import json
import math
import os
import re
import struct
import sys
import time

sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
from md3 import MD3, Surface
from iqm import IQM, IQM_POSITION, IQM_TEXCOORD, IQM_BLENDINDEXES, IQM_BLENDWEIGHTS
from autorig import ( vsub, vadd, vscale, vlen, mvec, mmul, mtrans, IDENT, quat_to_mat, mat_to_quat,
	rigid_fit, xform, write_iqm, gamePath, D3_TEMPLATE )

FPS = 10.0
LOOPING = re.compile( r"^amb" )
MIN_VERTS = 6		# a joint fitted needs this many vertexes...
MIN_WEIGHT = 3.0	# ...and this much skin on them
CELL = 2.0			# the nearest vertex search's grid
FAR = 16.0			# nearer than this, or counted as this far
UV_CELL = 256		# the texture coordinates' grid
UV_EPS = 0.002		# texture coordinates this near are the same
BAD_ANIM = 2.0		# an animation this much worse than the model's on average is named

ZONES = { name: zone for name, parent, pos, zone in D3_TEMPLATE }

def is_head( name ):
	return "head" in name.lower()

# ------------------------------------------------------------------------
# rigid transforms ( R, t ): x' = R x + t

def compose( a, b ):
	"""a after b"""
	return mmul( a[0], b[0] ), xform( a, b[1] )

def inverse( a ):
	rt = mtrans( a[0] )
	return rt, vscale( mvec( rt, a[1] ), -1.0 )

def rot_z( deg ):
	c, s = math.cos( math.radians( deg ) ), math.sin( math.radians( deg ) )
	return [ [ c, -s, 0.0 ], [ s, c, 0.0 ], [ 0.0, 0.0, 1.0 ] ]

def yaw_of( r ):
	"""A rotation's turn about the vertical (its twist about z, degrees): what
	of it isn't pitching or rolling"""
	x, y, z, w = mat_to_quat( r )
	return math.degrees( 2.0 * math.atan2( z, w ) )

def wrap( a ):
	while a > 180.0:
		a -= 360.0
	while a <= -180.0:
		a += 360.0
	return a

# ------------------------------------------------------------------------
# nearest vertexes: a grid

class Grid:
	def __init__( self, points, idx ):
		self.points = points
		self.cells = {}
		for i in idx:
			self.cells.setdefault( self.key( points[i] ), [] ).append( i )

	def key( self, p ):
		return ( int( math.floor( p[0] / CELL ) ), int( math.floor( p[1] / CELL ) ), int( math.floor( p[2] / CELL ) ) )

	def nearest( self, p, far = FAR ):
		"""( index, distance ), ( None, far ) when none is nearer than far"""
		kx, ky, kz = self.key( p )
		best, bestD = None, far
		for r in range( int( far / CELL ) + 2 ):
			for dx in range( -r, r + 1 ):
				for dy in range( -r, r + 1 ):
					for dz in range( -r, r + 1 ):
						if max( abs( dx ), abs( dy ), abs( dz ) ) != r:
							continue
						for i in self.cells.get( ( kx + dx, ky + dy, kz + dz ), () ):
							q = self.points[i]
							d = math.sqrt( ( p[0] - q[0] ) ** 2 + ( p[1] - q[1] ) ** 2 + ( p[2] - q[2] ) ** 2 )
							if d < bestD:
								best, bestD = i, d
			# what's in further shells is at least r cells away
			if best is not None and bestD <= r * CELL:
				break
		return best, bestD

# ------------------------------------------------------------------------

def load_rig( path ):
	"""The rig as autorig.write_iqm takes it: surfaces, the base pose, joints
	(world rest places, zones), the skin ( bone, blend bone, weight )"""
	q = IQM( path )
	rest = [ tuple( p ) for p in q.arrays[IQM_POSITION] ]
	weights = []
	for bi, bw in zip( q.arrays[IQM_BLENDINDEXES], q.arrays[IQM_BLENDWEIGHTS] ):
		weights.append( ( bi[0], bi[1], bw[0] / 255.0 ) )		# a blend bone kept at no weight too
	body, verts = [], []
	for k, m in enumerate( q.meshes ):
		s = Surface()
		s.name, s.shader, s.numVerts = m.name, m.material, m.numVerts
		s.triangles = [ tuple( c - m.firstVert for c in t ) for t in q.triangles[m.firstTri:m.firstTri + m.numTris] ]
		s.st = [ tuple( t ) for t in q.arrays[IQM_TEXCOORD][m.firstVert:m.firstVert + m.numVerts] ]
		body.append( s )
		verts += [ ( k, vi ) for vi in range( m.numVerts ) ]
	# the joints' world rest: autorig's restRot and places
	joints, world = [], []
	for j, jt in enumerate( q.joints ):
		if jt.parent >= j:
			raise ValueError( "%s: joint %s before its parent" % ( path, jt.name ) )
		r = quat_to_mat( jt.rotate )
		if jt.parent < 0:
			w = ( r, jt.translate )
		else:
			w = compose( world[jt.parent], ( r, jt.translate ) )
		world.append( w )
		zone = ZONES.get( jt.name, "hair" if jt.name.startswith( "Ponytail" ) else None )
		joints.append( { "name": jt.name, "parent": q.joints[jt.parent].name if jt.parent >= 0 else None,
						 "parentIndex": jt.parent, "zone": zone, "pos": w[1] } )
	return q, body, verts, rest, joints, world, weights

class Frames:
	"""What write_iqm takes of an md3: the frames and the animations"""
	def __init__( self, numFrames, anims ):
		self.numFrames = numFrames
		self._anims = anims

	def animations( self ):
		return self._anims

def skin( motion, f, wt, p ):
	b, o, w = wt
	a = xform( motion[b][f], p )
	if w >= 1.0:
		return a
	return vadd( vscale( a, w ), vscale( xform( motion[o][f], p ), 1.0 - w ) )

def render_ppm( path, layers, size = 360 ):
	"""Points front (looking along -x) and side (along y), orthographic:
	layers [ ( colour, points ) ]"""
	allPts = [ p for c, pts in layers for p in pts ]
	lo = [ min( p[k] for p in allPts ) for k in range( 3 ) ]
	hi = [ max( p[k] for p in allPts ) for k in range( 3 ) ]
	span = max( hi[k] - lo[k] for k in range( 3 ) ) + 4
	sc = ( size - 8 ) / span
	W, H = 2 * size, size
	img = bytearray( b"\xff" * ( W * H * 3 ) )
	for view in range( 2 ):
		for colour, pts in layers:
			for p in pts:
				a = ( hi[1] - p[1] ) if view == 0 else ( p[0] - lo[0] )
				x = int( view * size + 4 + a * sc )
				y = int( H - 4 - ( p[2] - lo[2] ) * sc )
				for dx in ( 0, 1 ):
					for dy in ( 0, 1 ):
						if 0 <= x + dx < W and 0 <= y + dy < H:
							o = ( ( y + dy ) * W + x + dx ) * 3
							img[o:o + 3] = bytes( colour )
	with open( path, "wb" ) as fp:
		fp.write( b"P6\n%d %d\n255\n" % ( W, H ) + bytes( img ) )

def main( character, md3Path, outBase, align = True, ppm = None ):
	t0 = time.time()
	rigPath = os.path.join( os.path.dirname( md3Path.rstrip( "/" ) ), "..", "rigged", character + ".iqm" )
	if not os.path.exists( rigPath ):
		rigPath = os.path.join( "dkres", "models", "rigged", character + ".iqm" )
	q, body, verts, rest, joints, restWorld, weights = load_rig( rigPath )
	nj, N = len( joints ), len( rest )
	J = { j["name"]: i for i, j in enumerate( joints ) }

	m = MD3( md3Path )
	surfs = [ s for s in m.surfaces if s.numVerts > 3 ]		# not the hardpoints
	cverts = [ ( si, vi ) for si, s in enumerate( surfs ) for vi in range( s.numVerts ) ]
	C, F = len( cverts ), m.numFrames
	cin = [ [ surfs[si].frames[f][vi] for si, vi in cverts ] for f in range( F ) ]
	anims = m.animations()
	print( "%s: %d vertexes (%s), %d frames, %d animations; rig %s: %d vertexes, %d joints" % ( md3Path, C,
		", ".join( "%s %d" % ( s.name, s.numVerts ) for s in surfs ), F, len( anims ), rigPath, N, nj ) )

	# 2. the reference frame: the median distance to the rig's base pose least
	# (the nearest vertex's, in its own group: the head's or the body's)
	rigHead = set( i for i, ( k, vi ) in enumerate( verts ) if is_head( body[k].name ) )
	grids = { None: Grid( rest, range( N ) ) }
	if rigHead and len( rigHead ) < N:
		grids[True] = Grid( rest, sorted( rigHead ) )
		grids[False] = Grid( rest, [ i for i in range( N ) if i not in rigHead ] )
	group = [ ( is_head( surfs[si].name ) if len( grids ) > 1 else None ) for si, vi in cverts ]
	sample = list( range( 0, C, max( 1, C // 250 ) ) )
	def median_dist( f, idx, far ):
		ds = sorted( grids[group[c]].nearest( cin[f][c], far )[1] for c in idx )
		return ds[len( ds ) // 2]
	# (only a frame near the base pose matters: a short search first)
	coarse = sorted( ( median_dist( f, sample, 4.0 ), f ) for f in range( F ) )
	if coarse[0][0] >= 4.0:
		coarse = sorted( ( median_dist( f, sample, FAR ), f ) for f in range( F ) )
	candidates = [ f for d, f in coarse[:5] ]
	near = min( ( median_dist( f, range( C ), FAR ), f ) for f in candidates )[1]

	# the skin: each cinematic vertex its rig vertex's. The models share
	# their skins' textures: the rig's vertex at the same place on the same
	# texture is the one (whatever the poses); of a mirrored texture's (an
	# arm's, both arms'), the one on the same side, then the nearest. Without
	# one (a surface the rig hasn't), the nearest vertex in its group
	uvCells = {}
	for i, ( k, vi ) in enumerate( verts ):
		u, v = body[k].st[vi]
		uvCells.setdefault( ( os.path.basename( body[k].shader ), round( u * UV_CELL ), round( v * UV_CELL ) ), [] ).append( i )
	midY = joints[0]["pos"][1]
	height = max( p[2] for p in rest ) - min( p[2] for p in rest )
	def side( p ):
		return 0 if abs( p[1] - midY ) < 1.0 else ( 1 if p[1] > midY else -1 )
	def correspond( f ):
		corr, byUV = [], 0
		for c, ( si, vi ) in enumerate( cverts ):
			u, v = surfs[si].st[vi]
			tex = os.path.basename( surfs[si].shader )
			ku, kv = round( u * UV_CELL ), round( v * UV_CELL )
			same = [ i for du in ( -1, 0, 1 ) for dv in ( -1, 0, 1 ) for i in uvCells.get( ( tex, ku + du, kv + dv ), () )
					 if abs( body[verts[i][0]].st[verts[i][1]][0] - u ) < UV_EPS and abs( body[verts[i][0]].st[verts[i][1]][1] - v ) < UV_EPS ]
			p = cin[f][c]
			if same:
				sp = side( p )
				i = min( same, key = lambda i: ( 0 if side( rest[i] ) * sp >= 0 else 1, vlen( vsub( rest[i], p ) ) ) )
				# not a place across the body (a texture's bit used twice)
				if vlen( vsub( rest[i], p ) ) < 0.4 * height:
					corr.append( i )
					byUV += 1
					continue
			corr.append( grids[group[c]].nearest( p, 4 * FAR )[0] )
		return corr, byUV
	corr, byUV = correspond( near )
	# the reference: of the frames near the base pose, the one nearest it by
	# these pairs
	def pair_dists( f ):
		return sorted( vlen( vsub( rest[corr[c]], cin[f][c] ) ) for c in range( C ) )
	ref = min( candidates, key = lambda f: pair_dists( f )[C // 2] )
	if ref != near:
		corr, byUV = correspond( ref )
	ds = pair_dists( ref )
	cweights = [ weights[i] for i in corr ]
	print( "  reference frame %d (%s): to the rig's base pose (vertex pairs) %.2f median, %.2f mean, %.2f at most; "
		"%d of %d vertexes paired by texture, the rest by place" % ( ref, m.frameNames[ref], ds[C // 2], sum( ds ) / C, ds[-1], byUV, C ) )

	# each joint's vertexes, weighted
	members = [ ( [], [] ) for j in range( nj ) ]
	for c, ( b, o, w ) in enumerate( cweights ):
		members[b][0].append( c ); members[b][1].append( w )
		if w < 1.0:
			members[o][0].append( c ); members[o][1].append( 1.0 - w )
	fitted = [ len( members[j][0] ) >= MIN_VERTS and sum( members[j][1] ) >= MIN_WEIGHT for j in range( nj ) ]
	for name in ( "origin", "Body" ):
		if name in J:
			fitted[J[name]] = False
	print( "  joints kept on their parents: %s" % ", ".join( "%s (%d)" % ( joints[j]["name"], len( members[j][0] ) )
		for j in range( nj ) if not fitted[j] and joints[j]["name"] not in ( "origin", "Body" ) ) )

	# 3. the joints' motions (from the rig's rest, world): the base pose to the
	# reference frame (align), then the reference frame to each
	ident = ( IDENT, ( 0.0, 0.0, 0.0 ) )
	alignTo = [ ident ] * nj
	if align:
		for j in range( nj ):
			if fitted[j]:
				idx, w = members[j]
				alignTo[j] = rigid_fit( [ rest[corr[c]] for c in idx ], [ cin[ref][c] for c in idx ], w )
	# raw: the reference frame to each; the joints without vertexes enough
	# take their parent's (Body the hips'), the origin none
	raw = [ None ] * nj
	for j in range( nj ):
		if fitted[j]:
			idx, w = members[j]
			src = [ cin[ref][c] for c in idx ]
			raw[j] = [ rigid_fit( src, [ cin[f][c] for c in idx ], w ) for f in range( F ) ]
	for j in range( nj ):
		name = joints[j]["name"]
		if name == "origin" or ( raw[j] is None and joints[j]["parentIndex"] < 0 ):
			raw[j] = [ ident ] * F
		elif name == "Body" and "Hips" in J and fitted[J["Hips"]]:
			raw[j], alignTo[j] = raw[J["Hips"]], alignTo[J["Hips"]]
		elif raw[j] is None:
			raw[j], alignTo[j] = raw[joints[j]["parentIndex"]], alignTo[joints[j]["parentIndex"]]
	motion = [ [ compose( raw[j][f], alignTo[j] ) for f in range( F ) ] for j in range( nj ) ]
	t1 = time.time()

	# 6. (before 4: with the root motion in) how far the rig is from the
	# cinematic: drawn, the rig's vertexes skinned against the cinematic's
	# paired with them (the meshes' own difference in it); skin, the cinematic's
	# own vertexes skinned so (how well the joints carry its motion)
	total, maxErr, totalS, maxS, count = 0.0, 0.0, 0.0, 0.0, 0
	animErr = []
	for name, first, n in anims:
		at, am, st, sm, worst = 0.0, 0.0, 0.0, 0.0, None
		for f in range( first, first + n ):
			skinned = [ skin( motion, f, weights[i], rest[i] ) for i in range( N ) ]
			for c in range( C ):
				e = vlen( vsub( skinned[corr[c]], cin[f][c] ) )
				at += e
				am = max( am, e )
				e = vlen( vsub( skin( raw, f, cweights[c], cin[ref][c] ), cin[f][c] ) )
				st += e
				if e > sm:
					sm, worst = e, ( f, c )
		total += at; totalS += st
		count += n * C
		maxErr = max( maxErr, am ); maxS = max( maxS, sm )
		animErr.append( ( name, at / ( n * C ), am, st / ( n * C ), sm, worst ) )
	mean, meanS = total / count, totalS / count
	print( "  error drawn: %.2f units on average, %.2f at most (the rig's own pose %.2f off the reference frame, median)" % (
		mean, maxErr, ds[C // 2] ) )
	print( "  error skin: %.2f units on average, %.2f at most (the cinematic's vertexes skinned)" % ( meanS, maxS ) )
	for name, ae, am, se, sm, worst in animErr:
		if ae > BAD_ANIM * mean or ae > mean + 1.0 or se > BAD_ANIM * meanS or se > meanS + 1.0:
			f, c = worst
			si, vi = cverts[c]
			print( "    %s: drawn %.2f/%.2f, skin %.2f/%.2f on average/at most (worst frame %d, %s:%d, on %s)" % ( name, ae, am, se, sm,
				f, surfs[si].name, vi, joints[cweights[c][0]]["name"] ) )

	# 4. the root motion out
	root = J["Body"] if "Body" in J else next( j for j in range( nj ) if fitted[j] )
	rootPos = joints[root]["pos"]
	inPlace = [ list( mj ) for mj in motion ]
	# the turn: the feet's (each foot's, the vertexes on its ankle, the two
	# turns averaged), not the hips': a swing of the sword twists the hips
	# with the feet planted; a character turning round turns its feet
	feet = [ [ c for c, wt in enumerate( cweights ) if joints[wt[0]]["name"] == name ] for name in ( "Lankle_r", "Rankle_r" ) ]
	feet = [ vs for vs in feet if len( vs ) >= MIN_VERTS ] if all( len( vs ) >= MIN_VERTS for vs in feet ) else None
	out = { "character": character, "source": gamePath( md3Path ), "reference_frame": ref,
			"reference_frame_name": m.frameNames[ref], "root": joints[root]["name"],
			"turn_from": "feet" if feet else joints[root]["name"], "anims": {} }
	for name, first, n in anims:
		r0 = motion[root][first][0]
		g0 = xform( motion[root][first], rootPos )
		path, yaw = [], 0.0
		yaws = [ 0.0 ] * ( len( feet ) if feet else 1 )
		for f in range( first, first + n ):
			g = xform( motion[root][f], rootPos )
			# the turn since the first frame, each unwound past half a turn
			if feet:
				turns = [ rigid_fit( [ cin[first][c] for c in vs ], [ cin[f][c] for c in vs ] )[0] for vs in feet ]
			else:
				turns = [ mmul( motion[root][f][0], mtrans( r0 ) ) ]
			yaws = [ y + wrap( yaw_of( t ) - y ) for y, t in zip( yaws, turns ) ]
			yaw = sum( yaws ) / len( yaws )
			path.append( [ round( g[0] - g0[0], 2 ), round( g[1] - g0[1], 2 ), round( yaw, 2 ) ] )
			# take = the turn about g0 and the travel: g0 -> g
			take = ( rot_z( yaw ), vsub( ( g[0], g[1], g0[2] ), mvec( rot_z( yaw ), g0 ) ) )
			back = inverse( take )
			for j in range( nj ):
				if joints[j]["name"] != "origin":
					inPlace[j][f] = compose( back, motion[j][f] )
		entry = { "frames": n, "fps": FPS, "move": path[-1][:2], "turn": path[-1][2], "path": path }
		key = name
		k = 2
		while key in out["anims"]:
			key = "%s#%d" % ( name, k )
			k += 1
		out["anims"][key] = entry
		print( "    %-14s %3d frames: moved %6.1f %6.1f, turned %6.1f, root rises %5.1f" % ( name, n, path[-1][0], path[-1][1],
			path[-1][2], xform( motion[root][first + n - 1], rootPos )[2] - g0[2] ) )

	# 5. the IQM: the character's own animations first, as they are (an actor
	# walking in a cutscene plays the walk), then the cinematic's, a name the
	# character has already taken given a "c_" before it
	F0 = len( q.frames )
	invRest = [ inverse( restWorld[j] ) for j in range( nj ) ]
	own = [ [ None ] * F0 for j in range( nj ) ]
	for f in range( F0 ):
		world = []
		for j in range( nj ):
			t, rq, s = q.frames[f][j]
			loc = ( quat_to_mat( rq ), t )
			world.append( loc if joints[j]["parentIndex"] < 0 else compose( world[joints[j]["parentIndex"]], loc ) )
			own[j][f] = compose( world[j], invRest[j] )
	taken = set( a[0] for a in q.anims )
	allAnims = [ ( a[0], a[1], a[2] ) for a in q.anims ]
	rates = [ ( a[3], a[4] & 1 ) for a in q.anims ]
	for ( name, first, n ), key in zip( anims, list( out["anims"] ) ):
		iqmName = name
		while iqmName in taken:
			iqmName = "c_" + iqmName
		taken.add( iqmName )
		out["anims"][key]["iqm_name"] = iqmName
		allAnims.append( ( iqmName, F0 + first, n ) )
		rates.append( ( FPS, 1 if LOOPING.match( name ) else 0 ) )
	renamed = [ ( k, v["iqm_name"] ) for k, v in out["anims"].items() if v["iqm_name"] != k.split( "#" )[0] ]
	if renamed:
		print( "  renamed (the character has these): %s" % ", ".join( "%s -> %s" % r for r in renamed ) )
	class Loops:
		def match( self, name ):
			return any( a[0] == name and r[1] for a, r in zip( allAnims, rates ) )
	write_iqm( Frames( F0 + F, allAnims ), body, verts, rest, joints, [ own[j] + inPlace[j] for j in range( nj ) ], weights,
			   outBase, looping = Loops(), fps = FPS )
	# each animation's own rate (write_iqm gives them one)
	data = bytearray( open( outBase + ".iqm", "rb" ).read() )
	ofsAnims = struct.unpack_from( "<I", data, 16 + 4 * 18 )[0]
	for k, ( fps, loop ) in enumerate( rates ):
		struct.pack_into( "<fI", data, ofsAnims + 20 * k + 12, fps, loop )
	open( outBase + ".iqm", "wb" ).write( bytes( data ) )
	with open( outBase + ".json", "w" ) as fp:
		json.dump( out, fp, indent = "\t" )
		fp.write( "\n" )
	print( "  wrote %s.json" % outBase )

	# the skeleton and the mesh as the character's
	w = IQM( outBase + ".iqm" )
	same = ( [ ( j.name, j.parent ) for j in w.joints ] == [ ( j.name, j.parent ) for j in q.joints ]
			 and all( max( abs( a - b ) for a, b in zip( x.translate + x.rotate, y.translate + y.rotate ) ) < 1e-4
					  for x, y in zip( w.joints, q.joints ) )
			 and w.arrays == q.arrays and w.triangles == q.triangles
			 and [ vars( x ) for x in w.meshes ] == [ vars( y ) for y in q.meshes ] )
	print( "  mesh and skeleton %s %s" % ( "the same as" if same else "DIFFER from", rigPath ) )
	# and the character's animations as its
	off = 0.0
	for f in range( F0 ):
		for a, b in zip( w.frames[f], q.frames[f] ):
			off = max( off, max( abs( x - y ) for x, y in zip( a[0] + a[1], b[0] + b[1] ) ) )
	print( "  the character's %d animations (%d frames) copied, %.4f off at most; %s" % ( len( q.anims ), F0, off,
		"names, rates and loops kept" if w.anims[:len( q.anims )] == q.anims else "THEIR NAMES OR RATES DIFFER" ) )

	if ppm:
		prefix, frameList = ppm
		for f in frameList:
			if not 0 <= f < F:
				continue
			render_ppm( "%s_%03d.ppm" % ( prefix, f ), [
				( ( 0, 0, 255 ), [ skin( inPlace, f, weights[i], rest[i] ) for i in range( N ) ] ),
				( ( 0, 170, 0 ), [ skin( motion, f, weights[i], rest[i] ) for i in range( N ) ] ),
				( ( 220, 0, 0 ), cin[f] ) ] )
			print( "  drew %s_%03d.ppm (%s)" % ( prefix, f, m.frameNames[f] ) )
	print( "  %.1f s (fitting %.1f s)" % ( time.time() - t0, t1 - t0 ) )

if __name__ == "__main__":
	args = sys.argv[1:]
	align, ppm = True, None
	while args and args[0].startswith( "--" ):
		if args[0] == "--no-align":
			align = False
			args = args[1:]
		elif args[0] == "--ppm" and len( args ) > 2:
			ppm = ( args[1], [ int( x ) for x in args[2].split( "," ) ] )
			args = args[3:]
		else:
			break
	if len( args ) != 3:
		print( __doc__ )
		sys.exit( 1 )
	main( args[0], args[1], args[2], align, ppm )
