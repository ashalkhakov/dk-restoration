#!/usr/bin/env python3
"""
A rig's bones moved as the parts of the body they should carry, in an
installed IQM: no rerig, no vertex moves.

A ragdoll's bodies hang on the body's bones (Doom 3's AF: a body a joint). A
rig can fit Daikatana's frames with its bones carrying the wrong parts: the
ninja's left hand on his thigh's bone, his right upper arm on his chest's,
his legs on point bones of their own (each a vertex's, fitting it exactly),
so his thigh's bone moved like his hand and his ragdoll's bodies lay off
him. tools/rig/joints/<name>_parts.txt places each part by hand, a bone and
the segment it runs along in the rest pose; a vertex is the part it's
nearest (a prop's none), of those it's within reach of ("r <reach>" on a
part's line: an arm hanging beside the trunk and thigh not taking their
vertexes). A bone that carries its part badly (on average
more than BAD off over the frames, its own motion taking the part's
vertexes from the rest pose), where the part's own rigid motion carries it
clearly better (GAIN) and no scaled joint (a prop) hangs on it:
	- gets a twin, <bone>_skin, with its rest place and parent and its
	  motion as it was, and every vertex's weight on it: the mesh doesn't
	  move;
	- moves as its part does: its motion each frame the rigid fit of the
	  part's vertexes, as the rig puts them.
A part whose line ends with "aim" (a thigh whose few vertexes are its coat's
hem at the knee, flaring as he moves: their fit turns it) hangs from its
segment's start as the bone's parent carries it (the hip, the pelvis') and
points at its vertexes' middle as they move ("aim <part>": at that part's,
a forearm at its hand), turned about its length as their fit is.
Every other joint stays where it was in each frame (its local transform
made again under a moved parent; the others' data as they were, bit for
bit).

	python3 tools/rig/iqm_parts.py dkres/models/rigged/ninja.iqm tools/rig/joints/ninja_parts.txt

rewrites the IQM, and says how far any vertex moved (it shouldn't).
"""
import math
import os
import struct
import sys

sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
import rigcheck as rc
from autorig import mat_to_quat, rigid_fit

BAD = 0.75		# units: a bone carrying its part worse than this moves as the part,
GAIN = 0.8		# if that carries it at least this much better (a part sculpted anew
				# in each frame, the ninja's legs, no rigid motion carries better)

def seg_dist( p, a, b ):
	d = [ b[k] - a[k] for k in range( 3 ) ]
	L2 = sum( x * x for x in d ) or 1e-9
	t = max( 0.0, min( 1.0, sum( ( p[k] - a[k] ) * d[k] for k in range( 3 ) ) / L2 ) )
	return math.dist( p, [ a[k] + t * d[k] for k in range( 3 ) ] )

def read_parts( path ):
	"""a parts file: each line a bone, its segment (x y z x y z) and its
	words: "aim [part]", "r <reach>" """
	parts, aims, reach = {}, {}, {}
	for line in open( path ):
		w = line.split( "#" )[0].split()
		if w:
			v = [ float( x ) for x in w[1:7] ]
			parts[w[0]] = ( v[0:3], v[3:6] )
			i = 7
			while i < len( w ):
				if w[i] == "r":
					reach[w[0]] = float( w[i + 1] )
					i += 2
				elif w[i] == "aim":
					named = i + 1 < len( w ) and w[i + 1] not in ( "aim", "r" )
					aims[w[0]] = w[i + 1] if named else w[0]
					i += 2 if named else 1
				else:
					sys.exit( "%s: what is %s?" % ( path, w[i] ) )
	return parts, aims, reach

def nearest( p, parts, reach ):
	"""the part a point is: the nearest whose reach it's in"""
	return min( ( b for b in parts if seg_dist( p, *parts[b] ) <= reach.get( b, 1e9 ) ), key = lambda b: seg_dist( p, *parts[b] ) )

def swing( a, b ):
	"""the least rotation taking the direction a to b"""
	la, lb = math.sqrt( sum( x * x for x in a ) ), math.sqrt( sum( x * x for x in b ) )
	a, b = [ x / la for x in a ], [ x / lb for x in b ]
	k = [ a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0] ]
	c = sum( a[i] * b[i] for i in range( 3 ) )
	K = [ [ 0, -k[2], k[1] ], [ k[2], 0, -k[0] ], [ -k[1], k[0], 0 ] ]
	K2 = [ [ sum( K[i][m] * K[m][n] for m in range( 3 ) ) for n in range( 3 ) ] for i in range( 3 ) ]
	f = 1.0 / ( 1.0 + c ) if c > -0.9999 else 0.0
	return [ [ ( i == n ) + K[i][n] + K2[i][n] * f for n in range( 3 ) ] for i in range( 3 ) ]

def aimed( fit, aimFit, start, src, carried ):
	"""a part's fit made to hang from start (as carried takes it) and point at
	the middle of the vertexes src (as aimFit takes them)"""
	mid = [ sum( p[k] for p in src ) / len( src ) for k in range( 3 ) ]
	hip, end = rc.apply( carried, start ), rc.apply( aimFit, mid )
	m = fit[0]
	rest = [ mid[k] - start[k] for k in range( 3 ) ]
	turned = [ sum( m[i][k] * rest[k] for k in range( 3 ) ) for i in range( 3 ) ]
	r = rc.compose( ( swing( turned, [ end[k] - hip[k] for k in range( 3 ) ] ), ( 0, 0, 0 ) ), ( m, ( 0, 0, 0 ) ) )[0]
	return r, tuple( hip[i] - sum( r[i][k] * start[k] for k in range( 3 ) ) for i in range( 3 ) )

def main( path, partsPath ):
	parts, aims, reach = read_parts( partsPath )
	d = open( path, "rb" ).read()
	h = list( struct.unpack_from( "<27I", d, 16 ) )
	( version, filesize, flags, numText, ofsText, numMeshes, ofsMeshes, numVA, numVerts, ofsVA,
	  numTris, ofsTris, ofsAdj, numJoints, ofsJoints, numPoses, ofsPoses, numAnims, ofsAnims,
	  numFrames, numChannels, ofsFrames, ofsBounds, numComment, ofsComment, numExt, ofsExt ) = h
	poses = [ struct.unpack_from( "<iI10f10f", d, ofsPoses + 88 * k ) for k in range( numPoses ) ]
	if any( p[1] != 0x3ff for p in poses ) or numChannels != 10 * numPoses or numPoses != numJoints:
		sys.exit( "%s: every joint's ten channels expected (autorig's)" % path )
	rig = rc.Rig( path )
	q = rig.q
	names = [ j.name for j in q.joints ]
	parent = [ j.parent for j in q.joints ]
	N = len( rig.pos )
	if any( n.endswith( "_skin" ) for n in names ):
		sys.exit( "%s: done already (its twins are there)" % path )

	# each vertex its part (a prop's none)
	def prop( j ):
		while j >= 0:
			if names[j].startswith( "Auto_" ):
				return True
			j = parent[j]
		return False
	part = [ None if prop( rig.bi[v][max( range( 4 ), key = lambda c: rig.bw[v][c] )] )
			 else nearest( rig.pos[v], parts, reach ) for v in range( N ) ]

	B = []
	for j, jt in enumerate( q.joints ):
		local = ( rc.mat( jt.rotate, jt.scale ), jt.translate )
		B.append( local if jt.parent < 0 else rc.compose( B[jt.parent], local ) )
	W, frames = [], []
	for f in range( numFrames ):
		w = []
		for j in range( numJoints ):
			t, r, s = q.frames[f][j]
			local = ( rc.mat( r, s ), t )
			w.append( local if parent[j] < 0 else rc.compose( w[parent[j]], local ) )
		W.append( w )
		frames.append( rig.frame( f ) )
	def scaled( k ):
		return any( max( abs( s - 1.0 ) for s in q.frames[f][k][2] ) > 1e-4 for f in range( numFrames ) )

	# the bones that move as their parts
	refit = {}
	for b in parts:
		if b not in names:
			continue
		j = names.index( b )
		vs = [ v for v in range( N ) if part[v] == b ]
		if len( vs ) < 3:
			continue
		err = sum( math.dist( rc.apply( rc.compose( W[f][j], rc.invert( B[j] ) ), rig.pos[v] ), frames[f][v] )
				   for f in range( numFrames ) for v in vs ) / ( numFrames * len( vs ) )
		if err <= BAD and b not in aims:
			continue
		src = [ rig.pos[v] for v in vs ]
		motion = [ rigid_fit( src, [ frames[f][v] for v in vs ] ) for f in range( numFrames ) ]
		if b in aims:
			# (its parent's motion as moved here, if it was)
			p = parent[j]
			carried = [ refit[p][f] if p in refit else rc.compose( W[f][p], rc.invert( B[p] ) ) for f in range( numFrames ) ]
			ts = [ v for v in range( N ) if part[v] == aims[b] ]
			tsrc = [ rig.pos[v] for v in ts ]
			target = motion if aims[b] == b else [ rigid_fit( tsrc, [ frames[f][v] for v in ts ] ) for f in range( numFrames ) ]
			motion = [ aimed( motion[f], target[f], parts[b][0], tsrc, carried[f] ) for f in range( numFrames ) ]
		after = sum( math.dist( rc.apply( motion[f], rig.pos[v] ), frames[f][v] )
					 for f in range( numFrames ) for v in vs ) / ( numFrames * len( vs ) )
		blocked = scaled( j ) or any( scaled( k ) for k in range( numJoints ) if parent[k] == j )
		if ( after < GAIN * err or b in aims ) and not blocked:	# (an aim placed by hand)
			refit[j] = motion
		print( "  %-9s carried its part (%d vertexes) %.2f off on average; as the part moves, %.2f%s" % ( b, len( vs ), err, after,
			   "" if j in refit else ( ": kept (scaled)" if blocked else ": kept (no better)" ) ) )
	if not refit:
		print( "%s: every bone carries its part" % path )
		return

	# the twins: joints after the others, each with its bone's rest and parent
	twin = {}
	for j in sorted( refit ):
		twin[j] = numJoints + len( twin )
	allJoints = numJoints + len( twin )
	text = bytearray( d[ofsText:ofsText + numText] )
	nameOfs = {}
	for j, t in twin.items():
		nameOfs[t] = len( text )
		text += ( names[j] + "_skin" ).encode() + b"\0"
	while len( text ) % 4:
		text += b"\0"
	jointRecs = [ bytearray( d[ofsJoints + 48 * k:ofsJoints + 48 * k + 48] ) for k in range( numJoints ) ]
	for j, t in twin.items():
		rec = bytearray( jointRecs[j] )
		struct.pack_into( "<I", rec, 0, nameOfs[t] )
		jointRecs.append( rec )
	jparent = parent + [ parent[j] for j in sorted( twin ) ]

	# each frame: the moved bones' world transforms, the twins' the old ones;
	# the local transforms of what changed (a moved bone, a joint on one, a
	# twin) made again, the rest kept as they were
	newWorld = []
	for f in range( numFrames ):
		nw = list( W[f] )
		for j, motion in refit.items():
			nw[j] = rc.compose( motion[f], B[j] )
		nw += [ W[f][j] for j in sorted( twin ) ]
		newWorld.append( nw )
	touched = sorted( set( refit ) | set( k for k in range( numJoints ) if parent[k] in refit ) | set( twin.values() ) )
	vals = { k: [] for k in touched }
	for f in range( numFrames ):
		nw = newWorld[f]
		for k in touched:
			local = nw[k] if jparent[k] < 0 else rc.compose( rc.invert( nw[jparent[k]] ), nw[k] )
			vals[k].append( list( local[1] ) + list( mat_to_quat( local[0] ) ) + [ 1.0, 1.0, 1.0 ] )
	poseRecs, quant = [], {}
	for k in range( allJoints ):
		if k in vals:
			offs, scales = [], []
			for c in range( 10 ):
				col = [ v[c] for v in vals[k] ]
				lo, hi = min( col ), max( col )
				offs.append( lo )
				scales.append( ( hi - lo ) / 65535.0 if hi > lo else 0.0 )
			quant[k] = ( offs, scales )
			poseRecs.append( struct.pack( "<iI10f10f", jparent[k], 0x3ff, *offs, *scales ) )
		else:
			poseRecs.append( d[ofsPoses + 88 * k:ofsPoses + 88 * k + 88] )
	frameData = bytearray()
	for f in range( numFrames ):
		for k in range( allJoints ):
			if k in quant:
				offs, scales = quant[k]
				for c in range( 10 ):
					v = 0 if scales[c] == 0 else int( round( ( vals[k][f][c] - offs[c] ) / scales[c] ) )
					frameData += struct.pack( "<H", max( 0, min( 65535, v ) ) )
			else:
				o = ofsFrames + 2 * ( f * numChannels + 10 * k )
				frameData += d[o:o + 20]
	while len( frameData ) % 4:
		frameData += b"\0"

	# the vertex arrays, every weight on a moved bone on its twin
	arrays = []
	for k in range( numVA ):
		vtype, vflags, fmt, size, ofs = struct.unpack_from( "<5I", d, ofsVA + 20 * k )
		step = { 0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 7: 4, 8: 8 }[fmt] * size
		data = bytearray( d[ofs:ofs + step * numVerts] )
		if vtype == 4:
			for v in range( numVerts ):
				for c in range( size ):
					if data[v * size + c] in twin:
						data[v * size + c] = twin[data[v * size + c]]
		arrays.append( ( vtype, vflags, fmt, size, bytes( data ) ) )

	# the file again, its sections in autorig's order
	sections, ofs = [], 124
	def place( data ):
		nonlocal ofs
		o = ofs
		sections.append( ( o, data ) )
		ofs += len( data )
		return o
	oText = place( bytes( text ) )
	oMeshes = place( d[ofsMeshes:ofsMeshes + 24 * numMeshes] )
	oVA = ofs
	ofs += 20 * numVA
	headers = b""
	for vtype, vflags, fmt, size, data in arrays:
		headers += struct.pack( "<5I", vtype, vflags, fmt, size, ofs )
		place( data )
	sections.append( ( oVA, headers ) )
	oTris = place( d[ofsTris:ofsTris + 12 * numTris] )
	oJoints = place( b"".join( bytes( r ) for r in jointRecs ) )
	oPoses = place( b"".join( poseRecs ) )
	oAnims = place( d[ofsAnims:ofsAnims + 20 * numAnims] )
	oFrames = place( bytes( frameData ) )
	oBounds = place( d[ofsBounds:ofsBounds + 32 * numFrames] ) if ofsBounds else 0
	header = b"INTERQUAKEMODEL\0" + struct.pack( "<27I", 2, ofs, flags, len( text ), oText, numMeshes, oMeshes,
		numVA, numVerts, oVA, numTris, oTris, 0, allJoints, oJoints, allJoints, oPoses, numAnims, oAnims,
		numFrames, 10 * allJoints, oFrames, oBounds, 0, 0, 0, 0 )
	out = bytearray( ofs )
	out[0:124] = header
	for o, data in sections:
		out[o:o + len( data )] = data
	with open( path, "wb" ) as fp:
		fp.write( out )

	# how far any vertex moved
	new = rc.Rig( path )
	worst = max( math.dist( p, o ) for f in range( numFrames ) for p, o in zip( new.frame( f ), frames[f] ) )
	print( "%s: %s move as their parts (their twins carry the mesh); vertexes moved %.3f at most"
		   % ( path, ", ".join( names[j] for j in sorted( refit ) ), worst ) )

if __name__ == "__main__":
	if len( sys.argv ) != 3:
		print( __doc__ )
		sys.exit( 1 )
	main( sys.argv[1], sys.argv[2] )
