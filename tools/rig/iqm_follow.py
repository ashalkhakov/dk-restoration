#!/usr/bin/env python3
"""
Joints that carry no vertex made to follow a bone's motion, in an installed
IQM: no rerig, no vertex moves.

The ragdoll's first body is the root's (Doom 3's AF: its "waist" on joint
"origin"), and the walk IK's waist is "Body". autorig leaves origin, Body and
Hips still when the pelvis carries the motion (Toshiro's: his Hips carries no
vertex), so in his dying and dead poses the pelvis' body stood where his
pelvis is when he stands, out of his lying body. Here each named joint is
moved, every frame, as the bone (its rigid motion from the bind pose)
moves: world = motion(bone, frame) * bind(joint). Their children's world
transforms are kept, their local ones made again; every other joint's data
stays as it was, bit for bit (each IQM channel is quantised per joint).

	python3 tools/rig/iqm_follow.py dkres/models/rigged/toshiro.iqm Waist origin Body Hips

rewrites the IQM in place (./dk rig runs it on a rig whose line in
RIG_MODELS says follow=Waist:origin,Body,Hips, before the gate).
"""
import math
import os
import struct
import sys

sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
import rigcheck as rc
from autorig import mat_to_quat

def main( path, bone, followers ):
	d = bytearray( open( path, "rb" ).read() )
	h = struct.unpack_from( "<27I", d, 16 )
	numJoints, ofsJoints, numPoses, ofsPoses, numFrames, numChannels, ofsFrames = h[13], h[14], h[15], h[16], h[19], h[20], h[21]
	rig = rc.Rig( path )
	q = rig.q
	names = [ j.name for j in q.joints ]
	parent = [ j.parent for j in q.joints ]
	poses = [ struct.unpack_from( "<iI10f10f", d, ofsPoses + 88 * k ) for k in range( numPoses ) ]
	if any( p[1] != 0x3ff for p in poses ) or numChannels != 10 * numPoses:
		sys.exit( "%s: every pose's ten channels expected (autorig's)" % path )

	B = []
	for j, jt in enumerate( q.joints ):
		local = ( rc.mat( jt.rotate, jt.scale ), jt.translate )
		B.append( local if jt.parent < 0 else rc.compose( B[jt.parent], local ) )
	b = names.index( bone )
	follow = [ names.index( n ) for n in followers ]
	touched = sorted( set( follow ) | set( k for k in range( numJoints ) if parent[k] in follow ) )
	for k in touched:
		for f in range( numFrames ):
			if max( abs( s - 1.0 ) for s in q.frames[f][k][2] ) > 1e-4:
				sys.exit( "%s: %s scales; not for this tool" % ( path, names[k] ) )

	vals = { k: [] for k in touched }	# joint: [frame] = 10 channels
	for f in range( numFrames ):
		W = []
		for j in range( numJoints ):
			t, r, s = q.frames[f][j]
			local = ( rc.mat( r, s ), t )
			W.append( local if parent[j] < 0 else rc.compose( W[parent[j]], local ) )
		motion = rc.compose( W[b], rc.invert( B[b] ) )
		newW = list( W )
		for j in follow:
			newW[j] = rc.compose( motion, B[j] )
		for k in touched:
			local = newW[k] if parent[k] < 0 else rc.compose( rc.invert( newW[parent[k]] ), newW[k] )
			vals[k].append( list( local[1] ) + list( mat_to_quat( local[0] ) ) + [ 1.0, 1.0, 1.0 ] )

	# the touched poses quantised again, their frames' channels rewritten
	for k in touched:
		offs, scales = [], []
		for c in range( 10 ):
			col = [ v[c] for v in vals[k] ]
			lo, hi = min( col ), max( col )
			offs.append( lo )
			scales.append( ( hi - lo ) / 65535.0 if hi > lo else 0.0 )
		struct.pack_into( "<iI10f10f", d, ofsPoses + 88 * k, poses[k][0], poses[k][1], *offs, *scales )
		for f in range( numFrames ):
			for c in range( 10 ):
				v = 0 if scales[c] == 0 else int( round( ( vals[k][f][c] - offs[c] ) / scales[c] ) )
				struct.pack_into( "<H", d, ofsFrames + 2 * ( f * numChannels + 10 * k + c ), max( 0, min( 65535, v ) ) )
	with open( path, "wb" ) as fp:
		fp.write( bytes( d ) )
	print( "%s: %s follow %s; rewrote %s" % ( path, ", ".join( followers ), bone, ", ".join( names[k] for k in touched ) ) )

if __name__ == "__main__":
	if len( sys.argv ) < 4:
		print( __doc__ )
		sys.exit( 1 )
	main( sys.argv[1], sys.argv[2], sys.argv[3:] )
