#!/usr/bin/env python3
"""
A thing a character holds: a joint on a bone of his, the model of it attached
there ("attach <joint>"), and a lid hinged to it, folding; shown in the
frames its file names (hidden elsewhere, scaled to nothing, as props are),
as open as it says; Daikatana's model of it taken out of his mesh. In a
staged rig (./dk rig runs it on a line saying hold=<file>).

The skinny worker's PDA (tools/rig/joints/skinnyworker_pda.txt): Daikatana's
was a folded piece of his mesh at his chest (SkinnySkinboy 451-464) and a
translucent box (trans33), unfolding in front of him in faaeaa, used in
eambd, folded back in eaafaa. Ours is a clamshell (characters/props/pda.iqm
and pda_lid.iqm, tools/models/make_pda.py) in his right hand: held where
Daikatana's sat as he used it, its face turned up to his eyes; out of his
pocket folded, opening as he lifts it, folded again as he puts it back.

	python3 tools/rig/iqm_hold.py <def dir> <iqm> <file>

The file's lines are described in tools/rig/joints/skinnyworker_pda.txt.
"""
import glob
import math
import os
import re
import struct
import sys

sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
import rigcheck as rc
from autorig import mat_to_quat

HIDDEN = 0.01	# a hidden joint's scale (autorig's props')

def norm( v ):
	l = math.sqrt( sum( x * x for x in v ) ) or 1e-9
	return [ x / l for x in v ]

def cross( a, b ):
	return [ a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0] ]

def read_spec( path ):
	spec = { "drop": [], "show": [] }
	for line in open( path ):
		w = line.split( "#" )[0].split()
		if not w:
			continue
		if w[0] in ( "drop", "show" ):
			spec[w[0]].append( w[1:] )
		else:
			spec[w[0]] = w[1:]
	return spec

def main( defDir, path, specPath ):
	spec = read_spec( specPath )
	jointName, boneName, modelPath = spec["hold"]
	useAnim, outSurface = spec["grip"]
	lidName, lidModel, folded = spec["lid"][0], spec["lid"][1], float( spec["lid"][2] )
	drops = [ d[0] for d in spec["drop"] ]
	defPath = glob.glob( os.path.join( defDir, "*.def" ) )[0]
	defName = re.search( r"entityDef\s+(\S+)", open( defPath ).read() ).group( 1 )
	info = rc.model_info( defName )
	rig = rc.Rig( path )
	q = rig.q
	md3 = rc.MD3( os.path.join( rc.DKRES, info[1] ) )
	manims = { name: ( first, n ) for name, first, n in md3.animations() }
	names = [ j.name for j in q.joints ]
	parent = [ j.parent for j in q.joints ]
	bone = names.index( boneName )
	F = len( q.frames )

	# what goes: the vertexes named, by mesh
	meshes = q.meshes
	drop = set()
	for d in drops:
		mname, _, span = d.partition( ":" )
		mesh = [ m for m in meshes if m.name == mname ]
		if not mesh:
			sys.exit( "%s: no mesh %s" % ( path, mname ) )
		m = mesh[0]
		if span:
			a, _, b = span.partition( "-" )
			drop |= set( m.firstVert + i for i in range( int( a ), int( b or a ) + 1 ) )
		else:
			drop |= set( range( m.firstVert, m.firstVert + m.numVerts ) )

	# the frames it's out, and how open in each
	surf = [ s for s in md3.surfaces if s.name == outSurface ][0]
	shown, opened = [ False ] * F, [ 0.0 ] * F
	for anim, a, b, oa, ob in spec["show"]:
		first, count = rig.anims[anim]
		a, b = int( a ), count - 1 if b == "end" else int( b )
		for k in range( a, b + 1 ):
			t = ( k - a ) / ( b - a ) if b > a else 0.0
			t = t * t * ( 3 - 2 * t )		# (eased)
			shown[first + k] = True
			opened[first + k] = float( oa ) + ( float( ob ) - float( oa ) ) * t

	# the bone's world transform each frame
	def worlds( f ):
		w = []
		for j in range( len( names ) ):
			t, r, s = q.frames[f][j]
			local = ( rc.mat( r, s ), t )
			w.append( local if parent[j] < 0 else rc.compose( w[parent[j]], local ) )
		return w

	# the grip: where Daikatana's thing sat as he used it, in the bone's frame,
	# its face up to his eyes, its far end out from him
	first, count = rig.anims[useAnim]
	mfirst, _ = manims[useAnim]
	k = count // 2
	w = worlds( first + k )
	pts = surf.frames[mfirst + k]
	centre = [ sum( p[i] for p in pts ) / len( pts ) for i in range( 3 ) ]
	eyes = w[names.index( "Head" )][1]
	up = norm( [ eyes[i] - centre[i] for i in range( 3 ) ] )
	out = norm( [ centre[0] - w[names.index( "Chest" )][1][0], centre[1] - w[names.index( "Chest" )][1][1], 0 ] )
	fwd = norm( [ out[i] - sum( out[j] * up[j] for j in range( 3 ) ) * up[i] for i in range( 3 ) ] )
	left = cross( up, fwd )
	held = ( [ [ fwd[r], left[r], up[r] ] for r in range( 3 ) ], tuple( centre ) )		# (rows: rc's)
	grip = rc.compose( rc.invert( w[bone] ), held )
	gripQuat = mat_to_quat( grip[0] )

	# the file again: the vertexes kept, the joint added
	d = open( path, "rb" ).read()
	h = list( struct.unpack_from( "<27I", d, 16 ) )
	( version, filesize, flags, numText, ofsText, numMeshes, ofsMeshes, numVA, numVerts, ofsVA,
	  numTris, ofsTris, ofsAdj, numJoints, ofsJoints, numPoses, ofsPoses, numAnims, ofsAnims,
	  numFrames, numChannels, ofsFrames, ofsBounds, numComment, ofsComment, numExt, ofsExt ) = h
	keep = [ v for v in range( numVerts ) if v not in drop ]
	renum = { v: i for i, v in enumerate( keep ) }
	text = bytearray( d[ofsText:ofsText + numText] )
	nameOfs = len( text )
	text += jointName.encode() + b"\0"
	lidOfs = len( text )
	text += lidName.encode() + b"\0"
	while len( text ) % 4:
		text += b"\0"
	meshRecs, tris = [], []
	for mi in range( numMeshes ):
		mname, material, fv, nv, ft, nt = struct.unpack_from( "<6I", d, ofsMeshes + 24 * mi )
		vs = [ renum[v] for v in range( fv, fv + nv ) if v in renum ]
		mt = []
		for ti in range( ft, ft + nt ):
			t = struct.unpack_from( "<3I", d, ofsTris + 12 * ti )
			if all( v in renum for v in t ):
				mt.append( tuple( renum[v] for v in t ) )
		if not vs:
			continue
		meshRecs.append( struct.pack( "<6I", mname, material, vs[0], len( vs ), len( tris ), len( mt ) ) )
		tris += mt
	arrays = []
	for k_ in range( numVA ):
		vtype, vflags, fmt, size, ofs = struct.unpack_from( "<5I", d, ofsVA + 20 * k_ )
		step = { 0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 7: 4, 8: 8 }[fmt] * size
		arrays.append( ( vtype, vflags, fmt, size, b"".join( d[ofs + step * v:ofs + step * ( v + 1 )] for v in keep ) ) )
	# the lid: on the hinge (the hold joint's origin), turned about y so far
	# as it's folded (the way that lifts it off the keypad)
	def lidQuat( o ):
		th = -math.radians( folded * ( 1 - o ) ) / 2
		return [ 0.0, math.sin( th ), 0.0, math.cos( th ) ]
	jointRecs = ( d[ofsJoints:ofsJoints + 48 * numJoints]
				  + struct.pack( "<Ii3f4f3f", nameOfs, bone, *grip[1], *gripQuat, 1, 1, 1 )
				  + struct.pack( "<Ii3f4f3f", lidOfs, numJoints, 0, 0, 0, *lidQuat( 1 ), 1, 1, 1 ) )

	# their channels: the grip, its scale nothing where it's put away; the
	# lid's turn
	added = [
		( bone, [ list( grip[1] ) + list( gripQuat ) + ( [ 1.0 ] * 3 if shown[f] else [ HIDDEN ] * 3 ) for f in range( F ) ] ),
		( numJoints, [ [ 0.0, 0.0, 0.0 ] + lidQuat( opened[f] ) + [ 1.0 ] * 3 for f in range( F ) ] ),
	]
	poseRecs = d[ofsPoses:ofsPoses + 88 * numPoses]
	quant = []
	for par_, vals in added:
		offs, scales = [], []
		for c in range( 10 ):
			col = [ v[c] for v in vals ]
			lo, hi = min( col ), max( col )
			offs.append( lo )
			scales.append( ( hi - lo ) / 65535.0 if hi > lo else 0.0 )
		poseRecs += struct.pack( "<iI10f10f", par_, 0x3ff, *offs, *scales )
		quant.append( ( vals, offs, scales ) )
	frameData = bytearray()
	for f in range( F ):
		o = ofsFrames + 2 * f * numChannels
		frameData += d[o:o + 2 * numChannels]
		for vals, offs, scales in quant:
			for c in range( 10 ):
				v = 0 if scales[c] == 0 else int( round( ( vals[f][c] - offs[c] ) / scales[c] ) )
				frameData += struct.pack( "<H", max( 0, min( 65535, v ) ) )
	while len( frameData ) % 4:
		frameData += b"\0"

	sections, ofs = [], 124
	def place( data ):
		nonlocal ofs
		o = ofs
		sections.append( ( o, data ) )
		ofs += len( data )
		return o
	oText = place( bytes( text ) )
	oMeshes = place( b"".join( meshRecs ) )
	oVA = ofs
	ofs += 20 * numVA
	headers = b""
	for vtype, vflags, fmt, size, data in arrays:
		headers += struct.pack( "<5I", vtype, vflags, fmt, size, ofs )
		place( data )
	sections.append( ( oVA, headers ) )
	oTris = place( b"".join( struct.pack( "<3I", *t ) for t in tris ) )
	oJoints = place( jointRecs )
	oPoses = place( poseRecs )
	oAnims = place( d[ofsAnims:ofsAnims + 20 * numAnims] )
	oFrames = place( bytes( frameData ) )
	oBounds = place( d[ofsBounds:ofsBounds + 32 * numFrames] ) if ofsBounds else 0
	header = b"INTERQUAKEMODEL\0" + struct.pack( "<27I", 2, ofs, flags, len( text ), oText, len( meshRecs ), oMeshes,
		numVA, len( keep ), oVA, len( tris ), oTris, 0, numJoints + 2, oJoints, numJoints + 2, oPoses, numAnims, oAnims,
		numFrames, 10 * ( numJoints + 2 ), oFrames, oBounds, 0, 0, 0, 0 )
	out = bytearray( ofs )
	out[0:124] = header
	for o, data in sections:
		out[o:o + len( data )] = data
	with open( path, "wb" ) as fp:
		fp.write( out )

	# the model def: the thing and its lid attached at their joints
	src = open( defPath ).read()
	for j, m in ( ( jointName, modelPath ), ( lidName, lidModel ) ):
		line = '\t"attach %s"\t\t"%s"\t// held (tools/rig/iqm_hold.py): drawn at the joint, hidden where it\'s put away\n' % ( j, m )
		if '"attach %s"' % j not in src:
			cut = src.rstrip().rfind( "}" )
			src = src[:cut] + line + src[cut:]
	open( defPath, "w" ).write( src )
	print( "%s: %d vertexes out (%s), joint %s on %s holding %s, its lid %s; out in %d of %d frames"
		   % ( path, len( drop ), " ".join( drops ), jointName, boneName, modelPath, lidName, sum( shown ), F ) )

if __name__ == "__main__":
	if len( sys.argv ) != 4:
		print( __doc__ )
		sys.exit( 1 )
	main( sys.argv[1], sys.argv[2], sys.argv[3] )
