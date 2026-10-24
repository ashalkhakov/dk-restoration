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
		[--surface metal]
(--bones: merge the parts that move most alike until there are no more than N;
--root-out-anims a,b: the travel in those animations out, each playing over
the origin, <out base>.json what was taken out (the froginator's leap and
hop: the game throws him); --mirror: left and right split alike, each part's image across the middle
the part on the other side (the froginator's legs came out split unlike);
--chain N: a separate piece of the mesh of at most N vertexes (the froginator's
tongue) a bone for each ring of it along its length, so it can stretch;
--seeds N: parts to start with (default 40; more for small parts that
move on their own: the thunderskeet's thin wings); --merge F: parts that move alike within F of the size are one (default
0.010; less, more bones: the thunderskeet's twisting wings and tail);
--surface metal: a robot, its hits spark; --no-hitbox a,b: no hitbox on those
joints, shots go through what they carry: the cambot's thin antenna)
	python3 tools/rig/creature_rig.py dkres/models/e1/m_frog.md3 dkres/models/rigged/frog froginator \\
		--anims "amba 10 loop;runa 15 loop;..."
writes dkres/models/rigged/frog.iqm, def/rig_froginator.def (model_froginator:
the mesh, the animations, hitboxes fitted to the bones; a later def of the
name replaces the md3's) and af/monster_froginator.af (its ragdoll, Doom 3's
articulated figure), and prints how far the skinned frames are from the
original ones. ./dk rig runs it for the creatures.
"""
import json
import math
import os
import re
import sys

sys.path.insert( 0, os.path.dirname( __file__ ) )
import autorig as A
from autorig import vsub, vadd, vscale, vdot, vlen, vnorm, mvec, rigid_fit, xform, eigen3, IDENT
from md3 import MD3
import af_refit

SEEDS = 40				# parts to start with
SAMPLE_STEP = 3			# every third frame fits the motions (all of them adds little)
SPATIAL = 0.5			# nearness to a part's middle against its motion, per frame (of the size squared)
MERGE = 0.010			# of the size: two parts whose merged motion fits this well on average are one
MIN_PART = 6			# vertexes: a smaller part goes to a neighbour
MIRROR = False			# --mirror: left and right split alike
ROOT_OUT = []			# --root-out-anims a,b: the travel out of those animations
CHAIN = 0				# --chain: a separate piece of no more vertexes a bone a ring (a tongue)
JOINT_MOVE = 0.15		# of the size: how far a joint goes from where its parts meet
DEFAULT_FPS = 10.0		# Daikatana's monsters animate at 10 frames a second

def centroid( pts ):
	n = float( len( pts ) )
	return ( sum( p[0] for p in pts ) / n, sum( p[1] for p in pts ) / n, sum( p[2] for p in pts ) / n )

def main( md3Path, outBase, name, animSpec, maxBones = 64, surface = None, noHitbox = () ):
	m = MD3( md3Path )
	# the body: every surface but the hardpoints (a triangle each: a muzzle, an eye)
	body = [ s for s in m.surfaces if not A.is_hardpoint( s ) ]
	hps = [ s for s in m.surfaces if A.is_hardpoint( s ) ]
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

	# --mirror: the creature left and right alike (a frog's legs): each vertex
	# its mirror image across the plane y = mid, the parts in pairs (mp: a
	# part's mirror, itself for one across the middle), a vertex on the left
	# and its image placed together, a pair merged together; a vertex on the
	# plane in a part across the middle, one with no image ("U") as it fits
	mir, side, mp = [ -1 ] * N, [ "C" ] * N, {}
	if MIRROR:
		tol = 0.05 * S		# (Daikatana's meshes are only near mirrored: the froginator's 0.66 apart, its images)
		# (by place: a seam's vertexes, welded, are one; each place on the
		# left with the nearest free place on the right, the nearest pairs
		# first)
		reps = sorted( set( group ) )
		def images( mid ):
			left = [ g for g in reps if rest[g][1] > mid + 0.5 * tol ]
			right = [ g for g in reps if rest[g][1] < mid - 0.5 * tol ]
			pairs = []
			for a in left:
				q = ( rest[a][0], 2 * mid - rest[a][1], rest[a][2] )
				for b in right:
					d = vlen( vsub( rest[b], q ) )
					if d < tol:
						pairs.append( ( d, a, b ) )
			pairs.sort()
			out, used = {}, set()
			for d, a, b in pairs:
				if a not in used and b not in used:
					used.update( ( a, b ) )
					out[a], out[b] = b, a
			return out
		c0 = 0.5 * ( restLo[1] + restHi[1] )
		mid = max( ( c0 + k * 0.005 * S for k in range( -10, 11 ) ), key = lambda c: len( images( c ) ) )
		pairOf = images( mid )
		for i in range( N ):
			g = pairOf.get( group[i] )
			if g is not None:
				mir[i] = g
				side[i] = "L" if rest[i][1] > mid else "R"
			elif abs( rest[i][1] - mid ) >= 0.5 * tol:
				side[i] = "U"		# (no image: its own way)
		print( "  mirrored across y %.2f: %d of %d vertexes in pairs" % ( mid, sum( 1 for s in side if s != "C" ), N ) )
	def mirror_right():
		"""the right side as the left's image"""
		for i in range( N ):
			if side[i] == "R":
				assign[i] = mp[assign[mir[i]]]

	# 1. parts: seeds far apart, the nearest one's vertexes (with --mirror,
	# the left's and the middle's, each left one's image the right's)
	seeds = [ min( ( i for i in range( N ) if side[i] in ( "L", "C" ) ), key = lambda i: vlen( vsub( rest[i], centroid( rest ) ) ) ) ]
	dist = [ vlen( vsub( rest[i], rest[seeds[0]] ) ) if side[i] in ( "L", "C" ) else 0.0 for i in range( N ) ]
	while len( seeds ) < min( SEEDS, N // MIN_PART ):
		far = max( range( N ), key = lambda i: dist[i] )
		seeds.append( far )
		dist = [ min( dist[i], vlen( vsub( rest[i], rest[far] ) ) ) for i in range( N ) ]
	for k in range( len( seeds ) ):
		mp[k] = k
		if side[seeds[k]] == "L":
			mp[k] = len( seeds )
			mp[len( seeds )] = k
			seeds.append( mir[seeds[k]] )
	assign = [ min( [ k for k in range( len( seeds ) ) if side[i] != "C" or mp[k] == k ],
					key = lambda s: vlen( vsub( rest[i], rest[seeds[s]] ) ) ) for i in range( N ) ]
	mirror_right()

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
		def cost( i, p ):
			d = vlen( vsub( rest[i], mids[p] ) ) / S
			return motion_err( i, motion, p ) + SPATIAL * len( sample ) * d * d * S * S * 0.01
		for i in range( N ):
			if side[i] == "R":
				continue
			cands = set( [ assign[i] ] + [ assign[n] for n in adj[i] ] )
			if side[i] == "C" and MIRROR:
				cands = set( p for p in cands if mp[p] == p ) or { assign[i] }
			if side[i] == "L":
				# (a part whose image has gone, its right side all gone
				# elsewhere, no place for a vertex with an image)
				cands = set( p for p in cands if mp.get( p ) in mids ) or { assign[i] }
				best = min( cands, key = lambda p: cost( i, p ) + ( cost( mir[i], mp[p] ) if mp.get( p ) in mids else 0.0 ) )
			else:
				best = min( cands, key = lambda p: cost( i, p ) )
			if best != assign[i]:
				assign[i] = best
				changed += 1
		mirror_right()
		weld_parts()
		changed += keep_whole()
		if MIRROR:
			mirror_right()
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

	# a small separate piece that stretches (--chain: the froginator's
	# tongue, shot out to seven times its length): a part, a bone, for each
	# ring of it along its length, never merged, so they slide apart
	chainParts = set()
	if CHAIN:
		size = {}
		for i in range( N ):
			size[piece[i]] = size.get( piece[i], 0 ) + 1
		nextPart = max( assign ) + 1
		for pc, n in size.items():
			if n > CHAIN:
				continue
			idx = [ i for i in range( N ) if piece[i] == pc ]
			c = centroid( [ rest[i] for i in idx ] )
			cov = [ [ sum( ( rest[i][r] - c[r] ) * ( rest[i][s] - c[s] ) for i in idx ) for s in range( 3 ) ] for r in range( 3 ) ]
			vals, vecs = eigen3( cov )
			axis = vecs[max( range( 3 ), key = lambda k: vals[k] )]
			t_ = { i: vdot( vsub( rest[i], c ), axis ) for i in idx }
			ts = sorted( set( round( x, 3 ) for x in t_.values() ) )
			gap = 0.05 * ( ts[-1] - ts[0] )
			ring, rings = 0, {}
			for a, b in zip( [ None ] + ts, ts ):
				if a is not None and b - a > gap:
					ring += 1
				rings[b] = ring
			for i in idx:
				assign[i] = nextPart + rings[round( t_[i], 3 )]
				chainParts.add( assign[i] )
				mp[assign[i]] = assign[i]
			print( "  a chain of %d rings: %d vertexes" % ( ring + 1, n ) )
			nextPart += ring + 1

	while True:
		ps = parts()
		best = None
		for p, idx in ps.items():
			for q in neighbours_of( p, ps ):
				if q <= p or p in chainParts or q in chainParts:
					continue
				small = min( len( idx ), len( ps[q] ) ) < MIN_PART
				mq = ( mp.get( p, p ), mp.get( q, q ) )
				if MIRROR and set( mq ) != { p, q } and tuple( sorted( mq ) ) < ( p, q ):
					continue		# (a pair and its image once, as the lesser pair)
				err = merged_error( idx + ps[q] )
				if MIRROR and set( mq ) != { p, q } and all( m in ps for m in mq ):
					err = max( err, merged_error( ps[mq[0]] + ps[mq[1]] ) )
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
		if MIRROR:
			mpp, mpq = mp.get( p, p ), mp.get( q, q )
			if q == mpp:
				mp[p] = p		# (a part and its image: one across the middle)
			elif mpp != p and mpq != q:
				for i in ps.get( mpq, [] ):
					assign[i] = mpp
				mp[p], mp[mpp] = mpp, p
	# a separate piece of mesh that moves alone stays a part; one with no
	# neighbour at all that's too small goes to the nearest part
	ps = parts()
	for p, idx in list( ps.items() ):
		if len( idx ) < MIN_PART and len( ps ) > 1 and p not in chainParts:
			others = [ q for q in ps if q != p ]
			c = centroid( [ rest[i] for i in idx ] )
			q = min( others, key = lambda q: min( vlen( vsub( rest[i], c ) ) for i in ps[q] ) )
			for i in idx:
				assign[i] = q
	if MIRROR:
		mirror_right()
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
	# (mirrored, a part across the middle: a side's small one, near the
	# middle of the graph, isn't the body)
	middle = [ p for p in ps if mp.get( p ) == p and p not in chainParts ] if MIRROR else []
	root = min( middle or ps, key = lambda p: ( eccentricity( p ), -len( ps[p] ) ) )
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
			# (less than half its own: the other's, blended with its own; the
			# thunderskeet's wing roots, in his body's part, move as his wings)
			w = 1.0 if den < 1e-9 else max( 0.0, min( 1.0, num / den ) )
			err = 0.0
			for f in sample:
				pt = vadd( vscale( xform( jmotion[b][f], rest[i] ), w ), vscale( xform( jmotion[o][f], rest[i] ), 1 - w ) )
				d = vsub( pt, frames[f][i] )
				err += vdot( d, d )
			if best[3] is None or err < best[3]:
				best = ( b, o, w, err ) if w >= 0.5 else ( o, b, 1 - w, err )
		weights.append( best[:3] if best[3] is not None else ( b, b, 1.0 ) )
	# welded places skin alike (the group's first's weights)
	for g, ms in members.items():
		for i in ms:
			weights[i] = weights[ms[0]]
	# each vertex its bone as skinned (a wing's root, in the body's part, the
	# wing's): its hitbox's and its ragdoll body's
	jassign = [ weights[i][0] for i in range( N ) ]

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

	# the hardpoints, rigid joints on the bones that carry them
	for joint, jm in A.hardpoint_joints( hps, joints, jmotion, [ index[p] for p in boneOrder ], F, sample ):
		joints.append( joint )
		jmotion[len( joints ) - 1] = jm
		print( "  hardpoint %s on %s" % ( joint["name"], joint["parent"] ) )

	if ROOT_OUT:
		root_out( m, joints, jmotion, index[root], outBase, md3Path )

	# the IQM, with Daikatana's frame rates and loops
	spec, looping = A.anim_spec( animSpec, DEFAULT_FPS, A.MONSTER_LOOPING )
	anims, restRot = A.write_iqm( m, body, verts, rest, joints, jmotion, weights, outBase, looping, DEFAULT_FPS )

	write_def( m, name, outBase, joints, rest, jassign, anims, spec, looping, restRot, frames, surface )
	write_af( name, joints, rest, jassign, S )

def root_out( m, joints, jmotion, body, outBase, md3Path ):
	"""--root-out-anims: Daikatana's travel out of the animations named so
	(the froginator's leap and hop: the game throws him, and the frames'
	rise on top of it doubled it): each of their frames' body put back
	where the bind pose has it, every joint with it (up and down too), so
	they play over the origin; turning stays. <outBase>.json says what was
	taken out, as autorig.py's root_out: each frame's place (path)"""
	at = joints[body]["pos"]
	outOf = set( f for name, first, count in m.animations() if any( name.startswith( p ) for p in ROOT_OUT )
				 for f in range( first, first + count ) )
	off = []
	for f in range( m.numFrames ):
		h = xform( jmotion[body][f], at )
		off.append( vsub( h, at ) if f in outOf else ( 0.0, 0.0, 0.0 ) )
	for j, mt in list( jmotion.items() ):
		if not all( r == IDENT and t == ( 0, 0, 0 ) for r, t in mt.values() ):		# (the origin stays)
			jmotion[j] = { f: ( r, vsub( t, off[f] ) ) for f, ( r, t ) in mt.items() }
	anims = {}
	for name, first, count in m.animations():
		s0, s1 = off[first], off[first + count - 1]
		anims[name] = { "frames": count, "fps": DEFAULT_FPS, "start": [ round( s0[k], 2 ) for k in range( 3 ) ],
						"move": [ round( s1[k] - s0[k], 2 ) for k in range( 3 ) ], "turn": 0,
						"path": [ [ round( off[f][k], 2 ) for k in range( 3 ) ] for f in range( first, first + count ) ] }
	most = { n: max( vlen( p ) for p in a["path"] ) for n, a in anims.items() }
	with open( outBase + ".json", "w" ) as fp:
		json.dump( { "character": os.path.basename( outBase ), "source": A.gamePath( md3Path ), "root": joints[body]["name"],
					 "anims": anims }, fp, indent = "\t" )
	print( "  travel out (%s), wrote %s.json" % ( ", ".join( "%s %.0f" % ( n, d ) for n, d in most.items() if d > 1 ), outBase ) )

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
			# two forks may come to the same name (Head3's second child, Head2b's
			# first): the later one takes the next letter free
			base, k = n, 0
			while n in used:
				k += 1
				n = base + chr( ord( "a" ) + k )
			names[p] = n
			used.add( n )
			kids = sorted( [ q for q in ps if parentOf[q] == p ], key = lambda q: -len( ps[q] ) )
			for k, q in enumerate( kids ):
				label( q, depth + 1, suffix + ( chr( ord( "a" ) + k ) if k else "" ) )
		label( top, 1, "" )
	return names

def boxes( joints, assign, anims, looping, frames ):
	"""Its boxes: the one it moves with, of all but its wings as it idles
	(its first looping animation; a frog's legs kick out far behind it as it
	swims, which a box that can't turn would make room for whichever way it
	faced), square (Quake 3's boxes don't turn); and the one shots meet, of all
	of it over all it does that loops (idling and moving), as far as it reaches
	whichever way it faces."""
	loops = [ a for a in anims if looping.match( a[0] ) ] or anims[:1]
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

MOVING = re.compile( r"^(walk|run)[a-z]?$" )

def ground_speed( a, fps, frames ):
	"""How fast a walk or a run goes over the ground, as it plays in place:
	what's on the ground (the frame's lowest vertexes) goes back as fast as
	the creature goes forward. None if nothing stays on the ground"""
	if not MOVING.match( a[0] ) or a[2] < 2:
		return None
	speeds = []
	for k in range( a[2] ):
		f0, f1 = a[1] + k, a[1] + ( k + 1 ) % a[2]
		zs = [ p[2] for p in frames[f0] ]
		lo, hi = min( zs ), max( zs )
		near = 0.04 * ( hi - lo )
		lo1 = min( v[2] for v in frames[f1] )
		for i, p in enumerate( frames[f0] ):
			q = frames[f1][i]
			# on the ground in both frames, going back
			if p[2] < lo + near and q[2] < lo1 + near and q[0] < p[0]:
				speeds.append( ( p[0] - q[0] ) * fps )
	if len( speeds ) < a[2]:
		return None
	speeds.sort()
	return speeds[len( speeds ) // 2]

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

def write_def( m, name, outBase, joints, rest, assign, anims, spec, looping, restRot, frames, surface = None ):
	N = len( rest )
	mins, maxs, hitMins, hitMaxs = boxes( joints, assign, anims, looping, frames )
	lines = [ "// made by tools/rig/creature_rig.py from %s: the rigged model, in place of the md3's" % m.path.split( "dkres/" )[-1],
			  "entityDef model_%s {" % name,
			  "\t\"mesh\"\t\t\t\"%s.iqm\"" % A.meshPath( outBase ),
			  "\t\"mins\"\t\t\t\"%.0f %.0f %.0f\"\t// the box it moves with: all but its wings, idling" % mins,
			  "\t\"maxs\"\t\t\t\"%.0f %.0f %.0f\"" % maxs,
			  "\t\"hit_mins\"\t\t\"%.0f %.0f %.0f\"\t// the box shots meet: all of it, whichever way it faces" % hitMins,
			  "\t\"hit_maxs\"\t\t\"%.0f %.0f %.0f\"" % hitMaxs ]
	if surface:
		lines.append( "\t\"surface\"\t\t\"%s\"\t// Doom 3's surface type: its hits spark, no blood" % surface )
	lines.append( "" )
	seen = set()
	for a in anims:
		if a[0] in seen:
			continue
		seen.add( a[0] )
		fps, loop = spec.get( a[0], ( DEFAULT_FPS, looping.match( a[0] ) ) )
		lines.append( "\t\"anim %s\"\t\t\"%s %g%s\"" % ( a[0], a[0], fps, " loop" if loop else "" ) )
	for a in anims:
		speed = ground_speed( a, spec.get( a[0], ( DEFAULT_FPS, ) )[0], frames )
		if speed:
			lines.append( "\t\"anim_speed %s\"\t\"%.0f\"\t// over the ground, from its feet" % ( a[0], speed ) )
	perch = perch_frame( joints, assign, anims, frames )
	if perch is not None:
		lines.append( "\t\"anim perch\"\t\t\"%d 1 1 loop\"\t// landed, its wings raised: the frame they reach out least" % perch )
	lines.append( "" )
	for j, joint in enumerate( joints ):
		if not joint["zone"] or joint["name"] in noHitbox:
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
	os.makedirs( os.path.join( A.STAGE or ".", "def" ), exist_ok = True )
	path = os.path.join( A.STAGE or ".", "def", "rig_%s.def" % name )
	with open( path, "w" ) as fp:
		fp.write( "\n".join( lines ) )
	print( "  wrote %s" % path )

def write_af( name, joints, rest, assign, S ):
	"""Doom 3's articulated figure: a body a bone (a bone shape along a limb,
	a box for the rest), each held to its parent's by a universal joint at
	its joint, bending within a cone"""
	N = len( rest )
	nj = len( joints )
	kids = { j: [ k for k in range( nj ) if joints[k]["parentIndex"] == j and joints[k]["zone"] ] for j in range( nj ) }
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
			# a limb: a box along it, joint to joint, its points' own axes
			# across it (a wing is flat: a round bone about it stood out of
			# it, the slaughterskeet's)
			origin, h, axes = af_refit.obb( pts, vsub( b, a ), ( a, b ) )
			angles, h = af_refit.box_angles( bodyName[j], axes, h )
			h = [ max( minHalf, x ) for x in h ]
			model = "box( ( %.2f, %.2f, %.2f ), ( %.2f, %.2f, %.2f ) )" % ( -h[0], -h[1], -h[2], h[0], h[1], h[2] )
		else:
			# the box about its points along their own axes (the
			# thunderskeet's wings: thin, tilted, their box square to him
			# took half of them)
			origin, h, axes = af_refit.obb( pts )
			angles, h = af_refit.box_angles( bodyName[j], axes, h )
			h = [ max( minHalf, x ) for x in h ]
			model = "box( ( %.2f, %.2f, %.2f ), ( %.2f, %.2f, %.2f ) )" % ( -h[0], -h[1], -h[2], h[0], h[1], h[2] )
		lines.extend( [ "	body \"%s\" {" % bodyName[j],
						# the body's (the root's) moves the origin, as Doom 3 wants
						"		joint \"%s\"" % ( "origin" if joint["parentIndex"] == 0 else joint["name"] ),
						"		mod orientation",
						"		model %s" % model,
						"		angles ( %.1f, %.1f, %.1f )" % tuple( angles ),
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
	path = os.path.join( "af", "monster_%s.af" % name )
	A.write_af( path, "\n".join( lines ) )
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
	surface = None
	if "--surface" in args:
		i = args.index( "--surface" )
		surface = args[i + 1]
		args = args[:i] + args[i + 2:]
	noHitbox = ()
	if "--root-out-anims" in args:
		i = args.index( "--root-out-anims" )
		ROOT_OUT = [ a for a in args[i + 1].split( "," ) if a ]
		args = args[:i] + args[i + 2:]
	if "--mirror" in args:
		MIRROR = True
		args.remove( "--mirror" )
	if "--chain" in args:
		i = args.index( "--chain" )
		CHAIN = int( args[i + 1] )
		args = args[:i] + args[i + 2:]
	if "--seeds" in args:
		i = args.index( "--seeds" )
		SEEDS = int( args[i + 1] )
		args = args[:i] + args[i + 2:]
	if "--merge" in args:
		i = args.index( "--merge" )
		MERGE = float( args[i + 1] )
		args = args[:i] + args[i + 2:]
	if "--no-hitbox" in args:
		i = args.index( "--no-hitbox" )
		noHitbox = tuple( args[i + 1].split( "," ) )
		args = args[:i] + args[i + 2:]
	if len( args ) != 3:
		print( __doc__ )
		sys.exit( 1 )
	main( args[0], args[1], args[2], animSpec, maxBones, surface, noHitbox )
