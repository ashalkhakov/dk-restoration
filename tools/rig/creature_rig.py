#!/usr/bin/env python3
"""
Rigs a Daikatana creature (a vertex animated model, converted to .md3 frame by
frame) into a skeletal IQM from its animations alone: no template, so a frog,
an insect or anything else. autorig.py fits Doom 3's human rig; this finds the
creature's own (a skinning decomposition, Le & Deng's SSDR, with the bones
found rather than given):

 1. The mesh is split into many small parts by where its vertexes are, then
    again and again by which part's rigid motion (fitted to the frames) carries
    each vertex best, each part kept in one piece.
 2. Neighbouring parts that move as one are merged, until every part moves
    its own way: the creature's rigid pieces (a thigh, a wing).
 3. The parts become bones: the biggest the body, the others linked to it by
    where they meet (most mesh edges between two parts first).
 4. Each joint is put where the parent's and the child's motions agree best
    (least squares), from where the two parts meet.
 5. Each vertex blends its bone with a neighbouring one where that fits the
    frames better (two weights a vertex).
 6. The bones are named by where they are: Body, Head (in front), Tail
    (behind), L/R limbs (wings if they're wide and up), numbered out from the
    body.
The joints' rest frames are the mesh's first frame; every frame of the MD3
becomes a pose, its animations (named by the frame names) the IQM's.

	python3 tools/rig/creature_rig.py <md3> <out base> <name> [--bones N] [--anims "<anim> <fps> [loop];..."]
(--bones: merge the parts that move most alike until there are no more than N)
	python3 tools/rig/creature_rig.py dkres/models/e1/m_frog.md3 dkres/models/rigged/frog froginator \\
		--anims "amba 10 loop;runa 15 loop;..."
writes dkres/models/rigged/frog.iqm, def/rig_froginator.def (model_froginator:
the mesh, the animations, hitboxes fitted to the bones; a later def of the
name replaces the md3's) and af/monster_froginator.af (its ragdoll, Doom 3's
articulated figure), and prints how far the skinned frames are from the
original ones. ./dk rig runs it for the creatures.
"""
import math
import os
import re
import sys

sys.path.insert( 0, os.path.dirname( __file__ ) )
import autorig as A
from autorig import vsub, vadd, vscale, vdot, vlen, vnorm, mvec, rigid_fit, xform, eigen3, IDENT
from md3 import MD3

SEEDS = 40				# parts to start with
SAMPLE_STEP = 3			# every third frame fits the motions (all of them adds little)
SPATIAL = 0.5			# nearness to a part's middle against its motion, per frame (of the size squared)
MERGE = 0.010			# of the size: two parts whose merged motion fits this well on average are one
MIN_PART = 6			# vertexes: a smaller part goes to a neighbour
JOINT_MOVE = 0.15		# of the size: how far a joint goes from where its parts meet
DEFAULT_FPS = 10.0		# Daikatana's monsters animate at 10 frames a second

def centroid( pts ):
	n = float( len( pts ) )
	return ( sum( p[0] for p in pts ) / n, sum( p[1] for p in pts ) / n, sum( p[2] for p in pts ) / n )

def main( md3Path, outBase, name, animSpec, maxBones = 64 ):
	m = MD3( md3Path )
	body = m.surfaces
	verts = []
	for si, s in enumerate( body ):
		verts += [ ( si, vi ) for vi in range( s.numVerts ) ]
	N, F = len( verts ), m.numFrames
	frames = [ [ body[si].frames[f][vi] for si, vi in verts ] for f in range( F ) ]
	rest = frames[0]
	print( "%s: %d vertexes, %d frames" % ( md3Path, N, F ) )
	for sf in body:
		A.cap_holes( sf )
	base, tris = {}, []
	for k, ( si, vi ) in enumerate( verts ):
		base.setdefault( si, k )
	for si, sf in enumerate( body ):
		tris += [ ( base[si] + a, base[si] + b, base[si] + c ) for a, b, c in sf.triangles ]

	# its size: the biggest extent over all frames
	lo = [ min( p[k] for f in frames for p in f ) for k in range( 3 ) ]
	hi = [ max( p[k] for f in frames for p in f ) for k in range( 3 ) ]
	restLo = [ min( p[k] for p in rest ) for k in range( 3 ) ]
	restHi = [ max( p[k] for p in rest ) for k in range( 3 ) ]
	S = max( restHi[k] - restLo[k] for k in range( 3 ) )

	# one place, one vertex: what's welded (a seam) moves as one
	weld = {}
	group = []
	for i, v in enumerate( rest ):
		key = tuple( int( round( c / A.SEAM ) ) for c in v )
		group.append( weld.setdefault( key, i ) )
	members = {}
	for i in range( N ):
		members.setdefault( group[i], [] ).append( i )

	# mesh neighbours (welded places too)
	adj = [ set() for i in range( N ) ]
	for a, b, c in tris:
		for p, q in ( ( a, b ), ( b, c ), ( c, a ) ):
			adj[p].add( q )
			adj[q].add( p )
	for g, ms in members.items():
		for i in ms:
			for k in ms:
				if k != i:
					adj[i].add( k )

	sample = list( range( 0, F, SAMPLE_STEP ) )

	# 1. parts: seeds far apart, the nearest one's vertexes
	seeds = [ min( range( N ), key = lambda i: vlen( vsub( rest[i], centroid( rest ) ) ) ) ]
	dist = [ vlen( vsub( rest[i], rest[seeds[0]] ) ) for i in range( N ) ]
	while len( seeds ) < min( SEEDS, N // MIN_PART ):
		far = max( range( N ), key = lambda i: dist[i] )
		seeds.append( far )
		dist = [ min( dist[i], vlen( vsub( rest[i], rest[far] ) ) ) for i in range( N ) ]
	assign = [ min( range( len( seeds ) ), key = lambda s: vlen( vsub( rest[i], rest[seeds[s]] ) ) ) for i in range( N ) ]

	def parts():
		out = {}
		for i in range( N ):
			out.setdefault( assign[i], [] ).append( i )
		return out

	def fit_parts( frameList ):
		motion = {}
		for p, idx in parts().items():
			src = [ rest[i] for i in idx ]
			motion[p] = { f: rigid_fit( src, [ frames[f][i] for i in idx ] ) if len( idx ) >= 3 else ( IDENT, vsub( frames[f][idx[0]], rest[idx[0]] ) ) for f in frameList }
		return motion

	def motion_err( i, motion, p ):
		err = 0.0
		for f in sample:
			d = vsub( xform( motion[p][f], rest[i] ), frames[f][i] )
			err += vdot( d, d )
		return err

	def keep_whole():
		"""each part in one piece: its smaller pieces go to a neighbour's part"""
		moved = 0
		for p, idx in parts().items():
			idxSet = set( idx )
			seen, pieces = set(), []
			for i in idx:
				if i in seen:
					continue
				stack, piece = [ i ], []
				seen.add( i )
				while stack:
					v = stack.pop()
					piece.append( v )
					for n in adj[v]:
						if n in idxSet and n not in seen:
							seen.add( n )
							stack.append( n )
				pieces.append( piece )
			pieces.sort( key = len, reverse = True )
			for piece in pieces[1:]:
				nbr = [ assign[n] for v in piece for n in adj[v] if assign[n] != p ]
				if nbr:
					target = max( set( nbr ), key = nbr.count )
					for v in piece:
						assign[v] = target
					moved += len( piece )
		return moved

	def weld_parts():
		for g, ms in members.items():
			votes = [ assign[i] for i in ms ]
			best = max( set( votes ), key = votes.count )
			for i in ms:
				assign[i] = best

	for it in range( 10 ):
		motion = fit_parts( sample )
		mids = { p: centroid( [ rest[i] for i in idx ] ) for p, idx in parts().items() }
		changed = 0
		for i in range( N ):
			cands = set( [ assign[i] ] + [ assign[n] for n in adj[i] ] )
			def cost( p ):
				d = vlen( vsub( rest[i], mids[p] ) ) / S
				return motion_err( i, motion, p ) + SPATIAL * len( sample ) * d * d * S * S * 0.01
			best = min( cands, key = cost )
			if best != assign[i]:
				assign[i] = best
				changed += 1
		weld_parts()
		changed += keep_whole()
		print( "  split %d: %d vertexes moved, %d parts" % ( it + 1, changed, len( parts() ) ) )
		if changed < N * 0.002:
			break

	# 2. merge what moves as one, the best fitting pair first
	def neighbours_of( p, ps ):
		out = set()
		for i in ps[p]:
			for n in adj[i]:
				if assign[n] != p:
					out.add( assign[n] )
		return out

	def merged_error( idx ):
		src = [ rest[i] for i in idx ]
		total = 0.0
		for f in sample:
			mt = rigid_fit( src, [ frames[f][i] for i in idx ] )
			for i in idx:
				total += vlen( vsub( xform( mt, rest[i] ), frames[f][i] ) )
		return total / ( len( idx ) * len( sample ) )

	# the mesh's separate pieces (a tongue in a mouth): the budget doesn't
	# merge across them, only moving alike does
	piece = [ -1 ] * N
	for s in range( N ):
		if piece[s] >= 0:
			continue
		stack = [ s ]
		piece[s] = s
		while stack:
			v = stack.pop()
			for n in adj[v]:
				if piece[n] < 0:
					piece[n] = s
					stack.append( n )
	def piece_of( idx ):
		votes = [ piece[i] for i in idx ]
		return max( set( votes ), key = votes.count )

	while True:
		ps = parts()
		best = None
		for p, idx in ps.items():
			for q in neighbours_of( p, ps ):
				if q <= p:
					continue
				small = min( len( idx ), len( ps[q] ) ) < MIN_PART
				err = merged_error( idx + ps[q] )
				if small:
					err = -1.0 / max( len( idx ), len( ps[q] ) )	# a tiny part goes anyway, to its biggest neighbour
				budget = len( ps ) > maxBones and piece_of( idx ) == piece_of( ps[q] )
				if ( err < MERGE * S or budget ) and ( best is None or err < best[0] ):
					best = ( err, p, q )
		if not best:
			break
		_, p, q = best
		for i in ps[q]:
			assign[i] = p
	# a separate piece of mesh that moves alone stays a part; one with no
	# neighbour at all that's too small goes to the nearest part
	ps = parts()
	for p, idx in list( ps.items() ):
		if len( idx ) < MIN_PART and len( ps ) > 1:
			others = [ q for q in ps if q != p ]
			c = centroid( [ rest[i] for i in idx ] )
			q = min( others, key = lambda q: min( vlen( vsub( rest[i], c ) ) for i in ps[q] ) )
			for i in idx:
				assign[i] = q
	ps = parts()
	print( "  %d parts after merging: %s" % ( len( ps ), ", ".join( str( len( v ) ) for v in sorted( ps.values(), key = len, reverse = True ) ) ) )
	if os.environ.get( "RIG_MERGES" ):
		pairs = sorted( ( merged_error( ps[p] + ps[q] ) / S, len( ps[p] ), len( ps[q] ) ) for p in ps for q in neighbours_of( p, ps ) if q > p )
		print( "  the nearest merges (of the size):", ", ".join( "%.3f (%d+%d)" % pq for pq in pairs[:15] ) )

	# 3. bones: the biggest part the body, the others linked by where they meet
	edges = {}
	for a, b, c in tris:
		for u, v in ( ( a, b ), ( b, c ), ( c, a ) ):
			pu, pv = assign[u], assign[v]
			if pu != pv:
				edges[( pu, pv )] = edges.get( ( pu, pv ), 0 ) + 1
				edges[( pv, pu )] = edges.get( ( pv, pu ), 0 ) + 1
	mids = { p: centroid( [ rest[i] for i in ps[p] ] ) for p in ps }
	nbrs = { p: set( q for ( a, q ) in edges if a == p ) for p in ps }
	# the body: the middle of the parts (fewest steps to the farthest), the
	# bigger of those (the biggest part may be a head)
	def eccentricity( r ):
		seen, layer, d = { r }, [ r ], 0
		while layer:
			nxt = [ q for p in layer for q in nbrs[p] if q not in seen ]
			seen.update( nxt )
			layer = list( set( nxt ) )
			if layer:
				d += 1
		return d + ( len( ps ) - len( seen ) )
	root = min( ps, key = lambda p: ( eccentricity( p ), -len( ps[p] ) ) )
	# breadth first from the body: each part's parent the neighbour nearer the
	# body it meets most; a separate piece of mesh to the nearest part
	depth = { root: 0 }
	layer = [ root ]
	while layer:
		nxt = []
		for p in layer:
			for q in nbrs[p]:
				if q not in depth:
					depth[q] = depth[p] + 1
					nxt.append( q )
		layer = nxt
	for q in ps:
		if q not in depth:
			depth[q] = 1 + max( depth.values() )
	parentOf = { root: None }
	for q in sorted( ps, key = lambda q: depth[q] ):
		if q == root:
			continue
		ups = [ p for p in nbrs[q] if depth.get( p, 1e9 ) < depth[q] ]
		if ups:
			parentOf[q] = max( ups, key = lambda p: edges[( p, q )] )
		else:
			done = [ p for p in parentOf ]
			parentOf[q] = min( done, key = lambda p: min( vlen( vsub( rest[i], mids[p] ) ) for i in ps[q] ) )

	motion = fit_parts( range( F ) )

	# 4. joints where parent and child agree, from where they meet
	jointPos = {}
	jointPos[root] = mids[root]
	order = sorted( ps, key = lambda q: depth[q] )
	for q in order[1:]:
		p = parentOf[q]
		meet = [ i for i in ps[q] if any( assign[n] == p for n in adj[i] ) ] + \
			   [ i for i in ps[p] if any( assign[n] == q for n in adj[i] ) ]
		if meet:
			p0 = centroid( [ rest[i] for i in meet ] )
		else:
			p0 = min( ( rest[i] for i in ps[q] ), key = lambda v: vlen( vsub( v, mids[p] ) ) )
		a = [ [ 0.0 ] * 3 for r in range( 3 ) ]
		rhs = [ 0.0 ] * 3
		for f in sample:
			rp, tp = motion[p][f]
			rc, tc = motion[q][f]
			d = [ [ rp[r][c] - rc[r][c] for c in range( 3 ) ] for r in range( 3 ) ]
			e = vsub( tc, tp )
			for r in range( 3 ):
				for c in range( 3 ):
					a[r][c] += sum( d[k][r] * d[k][c] for k in range( 3 ) )
				rhs[r] += sum( d[k][r] * e[k] for k in range( 3 ) )
		vals, vecs = eigen3( a )
		top = max( vals ) if max( vals ) > 1e-9 else 1.0
		r0 = vsub( rhs, mvec( a, p0 ) )
		x = p0
		for val, vec in zip( vals, vecs ):
			if val > 0.05 * top:
				x = vadd( x, vscale( vec, vdot( vec, r0 ) / val ) )
		move = vsub( x, p0 )
		if vlen( move ) > JOINT_MOVE * S:
			x = vadd( p0, vscale( move, JOINT_MOVE * S / vlen( move ) ) )
		jointPos[q] = x

	# 6. names by where they are
	names = name_bones( ps, parentOf, root, mids, rest, restLo, restHi )
	if os.environ.get( "RIG_DEBUG" ):
		with open( os.environ["RIG_DEBUG"], "w" ) as fp:
			for i in range( N ):
				fp.write( "%s\n" % names[assign[i]] )
			for p in ps:
				fp.write( "# %s %.1f %.1f %.1f %s\n" % ( names[p], *jointPos[p], names[parentOf[p]] if parentOf[p] is not None else "-" ) )

	# the joints: the origin on the floor under the body, then the bones from the body out
	boneOrder = []
	def visit( p ):
		boneOrder.append( p )
		for q in sorted( [ q for q in ps if parentOf[q] == p ], key = lambda q: names[q] ):
			visit( q )
	visit( root )
	joints = [ { "name": "origin", "parent": None, "parentIndex": -1, "zone": None,
				 "pos": ( jointPos[root][0], jointPos[root][1], restLo[2] ) } ]
	index = {}
	for p in boneOrder:
		index[p] = len( joints )
		parent = parentOf[p]
		joints.append( { "name": names[p], "parent": "origin" if parent is None else names[parent],
						 "parentIndex": 0 if parent is None else index[parent], "zone": zone_of( names[p] ),
						 "pos": jointPos[p] } )
	jmotion = { 0: { f: ( IDENT, ( 0.0, 0.0, 0.0 ) ) for f in range( F ) } }
	for p in boneOrder:
		jmotion[index[p]] = motion[p]
	jassign = [ index[assign[i]] for i in range( N ) ]

	# 5. two weights a vertex: its bone, and a neighbour where blending fits
	children = { j: [ k for k in range( len( joints ) ) if joints[k]["parentIndex"] == j ] for j in range( len( joints ) ) }
	def near_bones( b ):
		n = set( [ b ] + children[b] )
		pi = joints[b]["parentIndex"]
		if pi > 0:
			n.add( pi )
			n.update( children[pi] )
		return n
	weights = []
	for i in range( N ):
		b = jassign[i]
		best = ( b, b, 1.0, None )
		for o in near_bones( b ):
			if o == b:
				continue
			num = den = 0.0
			for f in sample:
				pa = xform( jmotion[b][f], rest[i] )
				pc = xform( jmotion[o][f], rest[i] )
				ac = vsub( pa, pc )
				num += vdot( ac, vsub( frames[f][i], pc ) )
				den += vdot( ac, ac )
			w = 1.0 if den < 1e-9 else max( 0.5, min( 1.0, num / den ) )
			err = 0.0
			for f in sample:
				pt = vadd( vscale( xform( jmotion[b][f], rest[i] ), w ), vscale( xform( jmotion[o][f], rest[i] ), 1 - w ) )
				d = vsub( pt, frames[f][i] )
				err += vdot( d, d )
			if best[3] is None or err < best[3]:
				best = ( b, o, w, err )
		weights.append( best[:3] if best[3] is not None else ( b, b, 1.0 ) )
	# welded places skin alike (the group's first's weights)
	for g, ms in members.items():
		for i in ms:
			weights[i] = weights[ms[0]]

	# the error of the skinned frames
	total = maxErr = 0.0
	for f in range( F ):
		for i in range( N ):
			b, o, w = weights[i]
			pt = xform( jmotion[b][f], rest[i] )
			if w < 1.0:
				pt = vadd( vscale( pt, w ), vscale( xform( jmotion[o][f], rest[i] ), 1 - w ) )
			e = vlen( vsub( pt, frames[f][i] ) )
			total += e
			maxErr = max( maxErr, e )
	print( "  error: %.3f units on average, %.2f at most (the creature is %.0f across)" % ( total / ( N * F ), maxErr, S ) )
	if os.environ.get( "RIG_WORST" ):
		animOf = lambda f: next( ( a for a, s, n in m.animations() if s <= f < s + n ), "?" )
		worst = []
		for f in range( F ):
			for i in range( N ):
				b, o, w = weights[i]
				pt = xform( jmotion[b][f], rest[i] )
				if w < 1.0:
					pt = vadd( vscale( pt, w ), vscale( xform( jmotion[o][f], rest[i] ), 1 - w ) )
				worst.append( ( vlen( vsub( pt, frames[f][i] ) ), f, i ) )
		worst.sort( reverse = True )
		bad = {}
		for e, f, i in worst:
			if e < 3:
				break
			bad.setdefault( animOf( f ), [] ).append( ( e, f, i ) )
		for a, l in sorted( bad.items(), key = lambda kv: -len( kv[1] ) ):
			print( "   %s: %d vertex-frames over 3 units, worst %.1f (frame %d, vertex %d)" % ( a, len( l ), l[0][0], l[0][1], l[0][2] ) )
	print( "  bones: %s" % ", ".join( "%s(%d)" % ( names[p], len( ps[p] ) ) for p in boneOrder ) )

	# the IQM, with Daikatana's frame rates and loops
	spec = {}
	for part in animSpec.split( ";" ):
		w = part.split()
		if w:
			spec[w[0]] = ( float( w[1] ) if len( w ) > 1 else DEFAULT_FPS, "loop" in w[2:] )
	looping = re.compile( "^(%s)$" % "|".join( re.escape( a ) for a, ( fps, loop ) in spec.items() if loop ) if any( l for f, l in spec.values() ) else "^$" )
	anims, restRot = A.write_iqm( m, body, verts, rest, joints, jmotion, weights, outBase, looping, DEFAULT_FPS )

	write_def( m, name, outBase, joints, rest, jassign, anims, spec, restRot, frames )
	write_af( name, joints, rest, jassign, S )

def zone_of( name ):
	if name.startswith( "Head" ):
		return "head"
	if name.startswith( ( "Body", "Tail" ) ):
		return "torso"
	return "legs"

def name_bones( ps, parentOf, root, mids, rest, restLo, restHi ):
	"""Body, then each branch off it by where it is: Head ahead (+x), Tail
	behind, L/R limbs (+y left), wings if wide and up; numbered out along the
	branch, a letter for a fork"""
	names = { root: "Body" }
	sizeY = restHi[1] - restLo[1]
	rc = mids[root]
	def subtree( p ):
		out = [ p ]
		for q in ps:
			if parentOf[q] == p:
				out += subtree( q )
		return out
	used = set( [ "Body" ] )
	for top in sorted( [ q for q in ps if parentOf[q] == root ], key = lambda q: mids[q] ):
		sub = subtree( top )
		pts = [ rest[i] for p in sub for i in ps[p] ]
		c = centroid( pts )
		d = vsub( c, rc )
		spanY = max( p[1] for p in pts ) - min( p[1] for p in pts )
		if abs( d[1] ) < 0.12 * sizeY:
			kind, side = ( "Head" if d[0] > 0 else "Tail" ), ""
		else:
			side = "L" if d[1] > 0 else "R"
			if spanY > 0.3 * sizeY and d[2] > -0.05 * sizeY:
				kind = "wing"
			else:
				kind = "fore" if d[0] > 0 else "hind"
		stem = side + kind
		k = 0
		while any( re.match( re.escape( stem + ( chr( ord( "a" ) + k ) if k else "" ) ) + r"\d*$", n ) for n in used ):
			k += 1
		stem += chr( ord( "a" ) + k ) if k else ""
		# out along the branch
		def label( p, depth, suffix ):
			n = "%s%d%s" % ( stem, depth, suffix ) if not ( kind == "Head" and depth == 1 and stem == "Head" ) else "Head" + suffix
			names[p] = n
			used.add( n )
			kids = sorted( [ q for q in ps if parentOf[q] == p ], key = lambda q: -len( ps[q] ) )
			for k, q in enumerate( kids ):
				label( q, depth + 1, suffix + ( chr( ord( "a" ) + k ) if k else "" ) )
		label( top, 1, "" )
	return names

def boxes( joints, assign, anims, spec, frames ):
	"""Its boxes: the one it moves with, of all but its wings as it idles
	(its first looping animation; a frog's legs kick out far behind it as it
	swims, which a box that can't turn would make room for whichever way it
	faced), square (Quake 3's boxes don't turn); and the one shots meet, of all
	of it over all it does that loops (idling and moving), as far as it reaches
	whichever way it faces."""
	loops = [ a for a in anims if spec.get( a[0], ( 0, False ) )[1] ] or anims[:1]
	idle = range( loops[0][1], loops[0][1] + loops[0][2] )
	fs = sorted( set( f for a in loops for f in range( a[1], a[1] + a[2] ) ) )
	N = len( assign )
	body = [ i for i in range( N ) if "wing" not in joints[assign[i]]["name"].lower() ]
	half = max( max( abs( frames[f][i][0] ), abs( frames[f][i][1] ) ) for f in idle for i in body )
	zlo = min( frames[f][i][2] for f in idle for i in body )
	zhi = max( frames[f][i][2] for f in idle for i in body )
	reach = max( math.sqrt( frames[f][i][0] ** 2 + frames[f][i][1] ** 2 ) for f in fs for i in range( N ) )
	hlo = min( frames[f][i][2] for f in fs for i in range( N ) )
	hhi = max( frames[f][i][2] for f in fs for i in range( N ) )
	return ( -half, -half, zlo ), ( half, half, zhi ), ( -reach, -reach, hlo ), ( reach, reach, hhi )

def perch_frame( joints, assign, anims, frames ):
	"""A winged creature's frame with its wings raised over its back, as an
	insect holds them landed: the one in its idling and flying (not its dying,
	nor a special one, a skeet's hatching curled up) whose wings reach out
	least to its sides. Daikatana's always flap, it never landed. None if it
	has no wings"""
	N = len( assign )
	wing = [ i for i in range( N ) if "wing" in joints[assign[i]]["name"].lower() ]
	body = [ i for i in range( N ) if i not in set( wing ) ]
	if not wing or not body:
		return None
	best = None
	for a in anims:
		if a[0].lower().startswith( ( "die", "special" ) ):
			continue
		for f in range( a[1], a[1] + a[2] ):
			c = centroid( [ frames[f][i] for i in body ] )
			spread = sum( math.hypot( frames[f][i][0] - c[0], frames[f][i][1] - c[1] ) for i in wing ) / len( wing )
			if best is None or spread < best[0]:
				best = ( spread, f, a[0] )
	print( "  perch: frame %d (%s), its wings %.1f out to its sides" % ( best[1], best[2], best[0] ) )
	return best[1]

def write_def( m, name, outBase, joints, rest, assign, anims, spec, restRot, frames ):
	N = len( rest )
	mins, maxs, hitMins, hitMaxs = boxes( joints, assign, anims, spec, frames )
	lines = [ "// made by tools/rig/creature_rig.py from %s: the rigged model, in place of the md3's" % m.path.split( "dkres/" )[-1],
			  "entityDef model_%s {" % name,
			  "\t\"mesh\"\t\t\t\"%s.iqm\"" % A.gamePath( outBase ),
			  "\t\"mins\"\t\t\t\"%.0f %.0f %.0f\"\t// the box it moves with: all but its wings, idling" % mins,
			  "\t\"maxs\"\t\t\t\"%.0f %.0f %.0f\"" % maxs,
			  "\t\"hit_mins\"\t\t\"%.0f %.0f %.0f\"\t// the box shots meet: all of it, whichever way it faces" % hitMins,
			  "\t\"hit_maxs\"\t\t\"%.0f %.0f %.0f\"" % hitMaxs,
			  "" ]
	seen = set()
	for a in anims:
		if a[0] in seen:
			continue
		seen.add( a[0] )
		fps, loop = spec.get( a[0], ( DEFAULT_FPS, False ) )
		lines.append( "\t\"anim %s\"\t\t\"%s %g%s\"" % ( a[0], a[0], fps, " loop" if loop else "" ) )
	perch = perch_frame( joints, assign, anims, frames )
	if perch is not None:
		lines.append( "\t\"anim perch\"\t\t\"%d 1 1 loop\"\t// landed, its wings raised: the frame they reach out least" % perch )
	lines.append( "" )
	for j, joint in enumerate( joints ):
		if not joint["zone"]:
			continue
		rt = A.mtrans( restRot[j] )
		pts = [ mvec( rt, vsub( rest[i], joint["pos"] ) ) for i in range( N ) if assign[i] == j ]
		if len( pts ) < 4:
			continue
		lo = [ min( p[k] for p in pts ) for k in range( 3 ) ]
		hi = [ max( p[k] for p in pts ) for k in range( 3 ) ]
		lines.append( "\t\"hitbox %s\"\t\"%.1f %.1f %.1f %.1f %.1f %.1f %s\"" % ( joint["name"], *lo, *hi, joint["zone"] ) )
	lines += [ "", "\t\"damage_scale head\"\t\"2\"", "\t\"damage_scale legs\"\t\"0.75\"",
			   "", "\t\"ragdoll\"\t\t\"monster_%s\"\t// af/monster_%s.af, Doom 3's articulated figure" % ( name, name ),
			   "}", "" ]
	path = os.path.join( "def", "rig_%s.def" % name )
	with open( path, "w" ) as fp:
		fp.write( "\n".join( lines ) )
	print( "  wrote %s" % path )

def write_af( name, joints, rest, assign, S ):
	"""Doom 3's articulated figure: a body a bone (a bone shape along a limb,
	a box for the rest), each held to its parent's by a universal joint at
	its joint, bending within a cone"""
	N = len( rest )
	nj = len( joints )
	kids = { j: [ k for k in range( nj ) if joints[k]["parentIndex"] == j ] for j in range( nj ) }
	vec = lambda v: "( %.2f, %.2f, %.2f )" % tuple( v )
	minHalf = max( 0.75, 0.03 * S )
	lines = [ "// made by tools/rig/creature_rig.py: the %s's ragdoll, Doom 3's articulated figure" % name,
			  "// (made in the model's bind pose; joint() names the IQM's joints)",
			  "articulatedFigure monster_%s {" % name,
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
	bodyName = {}
	for j in range( 1, nj ):
		joint = joints[j]
		pts = [ rest[i] for i in range( N ) if assign[i] == j ]
		if len( pts ) < 4:
			continue
		bodyName[j] = joint["name"].lower()
		a = joint["pos"]
		if kids[j] and joint["parentIndex"] > 0:
			# a limb: along it to its child (the middle of its children)
			b = vscale( ( sum( joints[k]["pos"][0] for k in kids[j] ), sum( joints[k]["pos"][1] for k in kids[j] ),
						  sum( joints[k]["pos"][2] for k in kids[j] ) ), 1.0 / len( kids[j] ) )
		else:
			b = None
		if b is not None and vlen( vsub( b, a ) ) > 2 * minHalf:
			d = vsub( b, a )
			L = vlen( d )
			ds = sorted( vlen( vsub( p, vadd( a, vscale( d, max( 0.0, min( 1.0, vdot( vsub( p, a ), d ) / ( L * L ) ) ) ) ) ) ) for p in pts )
			width = max( 2 * minHalf, 2 * 0.9 * ds[int( 0.7 * ( len( ds ) - 1 ) )] )
			model = "bone( %s, %s, %.2f )" % ( vec( a ), vec( b ), width )
			origin = vscale( vadd( a, b ), 0.5 )
		else:
			lo = [ min( p[k] for p in pts ) for k in range( 3 ) ]
			hi = [ max( p[k] for p in pts ) for k in range( 3 ) ]
			origin = [ 0.5 * ( lo[k] + hi[k] ) for k in range( 3 ) ]
			h = [ max( minHalf, 0.5 * ( hi[k] - lo[k] ) * 0.85 ) for k in range( 3 ) ]
			model = "box( ( %.2f, %.2f, %.2f ), ( %.2f, %.2f, %.2f ) )" % ( -h[0], -h[1], -h[2], h[0], h[1], h[2] )
		lines.extend( [ "	body \"%s\" {" % bodyName[j],
						# the body's (the root's) moves the origin, as Doom 3 wants
						"		joint \"%s\"" % ( "origin" if joint["parentIndex"] == 0 else joint["name"] ),
						"		mod orientation",
						"		model %s" % model,
						"		origin %s" % vec( origin ),
						"		density 0.2",
						"		friction 0.01, 0.01, 0.8",
						"		contents corpse",
						"		clipMask solid, corpse",
						"		selfCollision 1",
						"	}", "" ] )
	for j in range( 1, nj ):
		pi = joints[j]["parentIndex"]
		if j not in bodyName or pi <= 0:
			continue
		# up the tree to a parent with a body
		while pi > 0 and pi not in bodyName:
			pi = joints[pi]["parentIndex"]
		if pi <= 0:
			continue
		a = joints[j]["pos"]
		if kids[j]:
			c = vscale( ( sum( joints[k]["pos"][0] for k in kids[j] ), sum( joints[k]["pos"][1] for k in kids[j] ),
						  sum( joints[k]["pos"][2] for k in kids[j] ) ), 1.0 / len( kids[j] ) )
			shaft = vnorm( vsub( c, a ) )
		else:
			shaft = vnorm( vsub( a, joints[pi]["pos"] ) )
		if vlen( shaft ) < 0.5:
			shaft = ( 1.0, 0.0, 0.0 )
		cone = 45 if joints[j]["zone"] == "head" else 30 if "wing" in joints[j]["name"] else 80
		lines.extend( [ "	universalJoint \"%s\" {" % joints[j]["name"],
						"		body1 \"%s\"" % bodyName[j],
						"		body2 \"%s\"" % bodyName[pi],
						"		anchor joint( \"%s\" )" % joints[j]["name"],
						"		shafts %s, %s" % ( vec( shaft ), vec( vscale( shaft, -1 ) ) ),
						"		friction 0.20",
						"		coneLimit %s, %.0f" % ( vec( shaft ), cone ),
						"	}", "" ] )
	lines += [ "}", "" ]
	os.makedirs( "af", exist_ok = True )
	path = os.path.join( "af", "monster_%s.af" % name )
	with open( path, "w" ) as fp:
		fp.write( "\n".join( lines ) )
	print( "  wrote %s" % path )

if __name__ == "__main__":
	args = sys.argv[1:]
	animSpec = ""
	if "--anims" in args:
		i = args.index( "--anims" )
		animSpec = args[i + 1]
		args = args[:i] + args[i + 2:]
	maxBones = 64
	if "--bones" in args:
		i = args.index( "--bones" )
		maxBones = int( args[i + 1] )
		args = args[:i] + args[i + 2:]
	if len( args ) != 3:
		print( __doc__ )
		sys.exit( 1 )
	main( args[0], args[1], args[2], animSpec, maxBones )
