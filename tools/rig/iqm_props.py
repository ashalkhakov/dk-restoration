#!/usr/bin/env python3
"""
A prop joint split into the rigid pieces its vertexes make, in an installed
(or staged) IQM, each piece a joint of its own moving as Daikatana's frames
move it.

autorig gives a prop (a piece of mesh hidden in some frames) one joint, its
motion the rigid fit of all its vertexes. Usagi's forging prop is two things
(his hammer, in his right hand, and the work, which moves on its own), so
one motion carried neither: 7.8 off in frga. Here the prop's vertexes are
grouped by the distances between them staying the same over the frames it
shows in; the biggest group keeps the prop's joint, each other a new joint
<prop>_<k>, each on the bone that carries it best (its pose the least off
from it). In a frame the prop shows in, a piece's joint is its vertexes'
rigid fit to Daikatana's frame; where it's hidden, it's hidden as the prop
was (its joint where the prop's was, scaled to nothing).

	python3 tools/rig/iqm_props.py model_usagi out/rig/stage/usagi/usagi.iqm Auto_1_prop1

rewrites the IQM (./dk rig runs it on a rig whose line says
propsplit=Auto_1_prop1, before the gate).
"""
import math
import os
import struct
import sys

sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
import rigcheck as rc
from autorig import mat_to_quat, rigid_fit

SAME = 0.4		# units: two vertexes a piece if their distance never changes more
SHOWN = 1.0		# a frame the prop shows in: its vertexes spread at least this far

def main( defName, path, propName ):
	info = rc.model_info( defName )
	rig = rc.Rig( path )
	# (its MD3 matched to this rig's vertexes; the root motion out of the
	# rig's own .json, beside it, or the installed one's)
	rootPath = os.path.splitext( path )[0] + ".json"
	if not os.path.exists( rootPath ) and info[2]:
		rootPath = os.path.join( rc.DKRES, info[2] )
	src = rc.Source( rig, os.path.join( rc.DKRES, info[1] ), rootPath )
	q = rig.q
	names = [ j.name for j in q.joints ]
	parent = [ j.parent for j in q.joints ]
	if propName not in names:
		sys.exit( "%s: no joint %s" % ( path, propName ) )
	pj = names.index( propName )
	top = lambda v: rig.bi[v][max( range( 4 ), key = lambda c: rig.bw[v][c] )]
	vs = [ v for v in range( len( rig.pos ) ) if top( v ) == pj ]
	F = len( q.frames )

	# each rig frame's MD3 frame and root offset
	md3Frame, offset = [ None ] * F, [ ( 0.0, 0.0, 0.0 ) ] * F
	for anim, ( first, count ) in rig.anims.items():
		if anim not in src.anims:
			continue
		mfirst, mcount = src.anims[anim]
		path_ = src.root.get( anim, {} ).get( "path" )
		for k in range( count ):
			md3Frame[first + k] = mfirst + min( k, mcount - 1 )
			if path_:
				o = path_[min( k, len( path_ ) - 1 )]
				offset[first + k] = ( o[0], o[1], o[2] if len( o ) > 2 else 0.0 )
	def target( v, f ):
		si, vi = src.match[v]
		a = src.m.surfaces[si].frames[md3Frame[f]][vi]
		return ( a[0] - offset[f][0], a[1] - offset[f][1], a[2] - offset[f][2] )
	shown = [ f for f in range( F ) if md3Frame[f] is not None
			  and max( math.dist( target( vs[0], f ), target( v, f ) ) for v in vs ) >= SHOWN ]

	# the pieces: vertexes whose distances stay
	groups = []
	for v in vs:
		for g in groups:
			u = g[0]
			if all( abs( math.dist( target( v, f ), target( u, f ) ) - math.dist( rig.pos[v], rig.pos[u] ) ) < SAME for f in shown ):
				g.append( v )
				break
		else:
			groups.append( [ v ] )
	groups.sort( key = len, reverse = True )
	if len( groups ) < 2:
		print( "%s: %s is one rigid piece" % ( path, propName ) )
		return

	B = []
	for j, jt in enumerate( q.joints ):
		local = ( rc.mat( jt.rotate, jt.scale ), jt.translate )
		B.append( local if jt.parent < 0 else rc.compose( B[jt.parent], local ) )
	W = []
	for f in range( F ):
		w = []
		for j in range( len( names ) ):
			t, r, s = q.frames[f][j]
			local = ( rc.mat( r, s ), t )
			w.append( local if parent[j] < 0 else rc.compose( w[parent[j]], local ) )
		W.append( w )
	propRest = B[pj]		# (a piece's rest: the prop's, so it hides as the prop did)

	# each piece's motion where it shows, and the bone that carries it best
	pieces = []
	for g in groups:
		motion = { f: rigid_fit( [ rig.pos[v] for v in g ], [ target( v, f ) for v in g ] ) for f in shown }
		best, bestOff = None, 1e9
		for j, n in enumerate( names ):
			if n.startswith( "Auto_" ) or n.endswith( "_skin" ):
				continue
			rel = [ rc.apply( rc.compose( rc.invert( rc.compose( W[f][j], rc.invert( B[j] ) ) ), motion[f] ), ( 0, 0, 0 ) ) for f in shown ]
			mid = [ sum( p[i] for p in rel ) / len( rel ) for i in range( 3 ) ]
			off = max( math.dist( p, mid ) for p in rel )
			if off < bestOff:
				best, bestOff = j, off
		pieces.append( ( g, motion, best, bestOff ) )

	# the joints: the prop's for the biggest piece, new ones after the others
	d = open( path, "rb" ).read()
	h = list( struct.unpack_from( "<27I", d, 16 ) )
	( version, filesize, flags, numText, ofsText, numMeshes, ofsMeshes, numVA, numVerts, ofsVA,
	  numTris, ofsTris, ofsAdj, numJoints, ofsJoints, numPoses, ofsPoses, numAnims, ofsAnims,
	  numFrames, numChannels, ofsFrames, ofsBounds, numComment, ofsComment, numExt, ofsExt ) = h
	poses = [ struct.unpack_from( "<iI10f10f", d, ofsPoses + 88 * k ) for k in range( numPoses ) ]
	if any( p[1] != 0x3ff for p in poses ) or numChannels != 10 * numPoses or numPoses != numJoints:
		sys.exit( "%s: every joint's ten channels expected (autorig's)" % path )
	text = bytearray( d[ofsText:ofsText + numText] )
	jointRecs = [ bytearray( d[ofsJoints + 48 * k:ofsJoints + 48 * k + 48] ) for k in range( numJoints ) ]
	jparent = list( parent )
	jointOf = []
	for i, ( g, motion, best, off ) in enumerate( pieces ):
		if i == 0:
			j = pj
		else:
			j = len( jointRecs )
			nameOfs = len( text )
			text += ( "%s_%d" % ( propName, i + 1 ) ).encode() + b"\0"
			jointRecs.append( bytearray( 48 ) )
			jparent.append( best )
		jparent[j] = best
		struct.pack_into( "<Ii", jointRecs[j], 0, nameOfs if i else struct.unpack_from( "<I", jointRecs[j], 0 )[0], best )
		local = rc.compose( rc.invert( B[best] ), propRest )
		struct.pack_into( "<3f4f3f", jointRecs[j], 8, *local[1], *mat_to_quat( local[0] ), 1.0, 1.0, 1.0 )
		jointOf.append( j )
	while len( text ) % 4:
		text += b"\0"
	allJoints = len( jointRecs )

	# each piece joint's local transform every frame: where it shows, its fit;
	# where it doesn't, the prop's world as it was (scaled to nothing)
	vals = { j: [] for j in jointOf }
	for f in range( F ):
		for ( g, motion, best, off ), j in zip( pieces, jointOf ):
			world = rc.compose( motion[f], propRest ) if f in motion else W[f][pj]
			local = rc.compose( rc.invert( W[f][best] ), world )
			m = local[0]		# (rc.mat's: each row its scale)
			sc = [ math.sqrt( sum( m[r][c] ** 2 for c in range( 3 ) ) ) or 1e-9 for r in range( 3 ) ]
			rot = [ [ m[r][c] / sc[r] for c in range( 3 ) ] for r in range( 3 ) ]
			vals[j].append( list( local[1] ) + list( mat_to_quat( rot ) ) + sc )
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
	for f in range( F ):
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

	# the vertex arrays: each piece's vertexes wholly on its joint
	pieceOf = {}
	for ( g, motion, best, off ), j in zip( pieces, jointOf ):
		for v in g:
			pieceOf[v] = j
	arrays = []
	for k in range( numVA ):
		vtype, vflags, fmt, size, ofs = struct.unpack_from( "<5I", d, ofsVA + 20 * k )
		step = { 0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 7: 4, 8: 8 }[fmt] * size
		data = bytearray( d[ofs:ofs + step * numVerts] )
		if vtype in ( 4, 5 ):
			for v, j in pieceOf.items():
				for c in range( size ):
					data[v * size + c] = ( j if c == 0 else 0 ) if vtype == 4 else ( 255 if c == 0 else 0 )
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

	new = rc.Rig( path )
	for ( g, motion, best, off ), j in zip( pieces, jointOf ):
		worst = max( math.dist( new.frame( f )[v], target( v, f ) ) for f in shown for v in g )
		print( "  %s: %d vertexes, on %s (it carries it %.1f off), %.2f off Daikatana's frames at most"
			   % ( ( propName if j == pj else "%s_%d" % ( propName, jointOf.index( j ) + 1 ) ), len( g ), names[best], off, worst ) )
	print( "%s: %s split into %d rigid pieces" % ( path, propName, len( pieces ) ) )

if __name__ == "__main__":
	if len( sys.argv ) != 4:
		print( __doc__ )
		sys.exit( 1 )
	main( sys.argv[1], sys.argv[2], sys.argv[3] )
