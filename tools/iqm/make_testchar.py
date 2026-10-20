#!/usr/bin/env python3
"""
Writes characters/test/testchar.iqm and testchar.tga: a blocky humanoid to
test mint-arena's skeletal models with. Twelve joints, a box per bone, every
vertex on one joint, and two looping animations, "idle" and "walk".

Quake 3 units: z up, facing +x, the origin at the middle of a 56 unit tall
body standing on z = -24 (Quake 3's player box).

	python3 tools/iqm/make_testchar.py [out dir]
"""
import math
import os
import struct
import sys

# name, parent, joint position in the bind pose (model space)
JOINTS = [
	( "Hips",       -1, ( 0,  0,   6 ) ),
	( "Spine",       0, ( 0,  0,  12 ) ),
	( "Neck",        1, ( 0,  0,  32 ) ),
	( "Head",        2, ( 0,  0,  34 ) ),
	( "L_UpperArm",  1, ( 0,  9.5, 31 ) ),
	( "L_ForeArm",   4, ( 0,  9.5, 20 ) ),
	( "R_UpperArm",  1, ( 0, -9.5, 31 ) ),
	( "R_ForeArm",   6, ( 0, -9.5, 20 ) ),
	( "L_Thigh",     0, ( 0,  4,   4 ) ),
	( "L_Calf",      8, ( 0,  4,  -9 ) ),
	( "R_Thigh",     0, ( 0, -4,   4 ) ),
	( "R_Calf",     10, ( 0, -4,  -9 ) ),
]
J = { name: i for i, ( name, _, _ ) in enumerate( JOINTS ) }

# boxes: joint, mins, maxs, colour cell of the texture
CLOTH, SKIN, DARK = 0, 1, 2
BOXES = [
	( "Hips",       ( -4, -6,   4 ), ( 4,  6,  12 ), DARK ),
	( "Spine",      ( -4.5, -7.5, 12 ), ( 4.5, 7.5, 31 ), CLOTH ),
	( "Neck",       ( -1.5, -1.5, 31 ), ( 1.5, 1.5, 34 ), SKIN ),
	( "Head",       ( -4.5, -4, 34 ), ( 4.5, 4,  44 ), SKIN ),
	( "L_UpperArm", ( -2,  7.5, 20 ), ( 2,  11.5, 31 ), CLOTH ),
	( "L_ForeArm",  ( -2,  7.5,  8 ), ( 2,  11.5, 20 ), SKIN ),
	( "R_UpperArm", ( -2, -11.5, 20 ), ( 2, -7.5, 31 ), CLOTH ),
	( "R_ForeArm",  ( -2, -11.5,  8 ), ( 2, -7.5, 20 ), SKIN ),
	( "L_Thigh",    ( -3,  1,  -9 ), ( 3,  7,   4 ), DARK ),
	( "L_Calf",     ( -3,  1, -24 ), ( 4,  7,  -9 ), DARK ),
	( "R_Thigh",    ( -3, -7,  -9 ), ( 3, -1,   4 ), DARK ),
	( "R_Calf",     ( -3, -7, -24 ), ( 4, -1,  -9 ), DARK ),
]
COLOURS = [ ( 70, 90, 140 ), ( 220, 175, 140 ), ( 60, 50, 45 ) ]	# texture cells, left to right

def quat( axis, degrees ):
	h = math.radians( degrees ) * 0.5
	s = math.sin( h )
	return ( axis[0] * s, axis[1] * s, axis[2] * s, math.cos( h ) )

def qmul( a, b ):
	ax, ay, az, aw = a
	bx, by, bz, bw = b
	return ( aw * bx + ax * bw + ay * bz - az * by,
			 aw * by - ax * bz + ay * bw + az * bx,
			 aw * bz + ax * by - ay * bx + az * bw,
			 aw * bw - ax * bx - ay * by - az * bz )

IDENT = ( 0, 0, 0, 1 )
PITCH = ( 0, 1, 0 )		# a leg or arm swings forward or back about y
ROLL = ( 1, 0, 0 )
YAW = ( 0, 0, 1 )

def local_translation( i ):
	_, parent, pos = JOINTS[i]
	if parent < 0:
		return pos
	pp = JOINTS[parent][2]
	return ( pos[0] - pp[0], pos[1] - pp[1], pos[2] - pp[2] )

def idle_pose( t ):
	# breathing, and the arms hanging a little out
	b = math.sin( t * 2 * math.pi )
	rot = [ IDENT ] * len( JOINTS )
	rot[J["Spine"]] = quat( PITCH, 2 * b )
	rot[J["Head"]] = quat( YAW, 6 * math.sin( t * 2 * math.pi * 0.5 ) )
	rot[J["L_UpperArm"]] = quat( ROLL, -6 - 2 * b )
	rot[J["R_UpperArm"]] = quat( ROLL, 6 + 2 * b )
	rot[J["L_ForeArm"]] = quat( PITCH, -10 )
	rot[J["R_ForeArm"]] = quat( PITCH, -10 )
	return rot, ( 0, 0, 0.3 * b )

def walk_pose( t ):
	s = math.sin( t * 2 * math.pi )
	c = math.cos( t * 2 * math.pi )
	rot = [ IDENT ] * len( JOINTS )
	rot[J["L_Thigh"]] = quat( PITCH, -30 * s )
	rot[J["R_Thigh"]] = quat( PITCH, 30 * s )
	rot[J["L_Calf"]] = quat( PITCH, 25 * max( 0, c ) )
	rot[J["R_Calf"]] = quat( PITCH, 25 * max( 0, -c ) )
	rot[J["L_UpperArm"]] = quat( PITCH, 25 * s )
	rot[J["R_UpperArm"]] = quat( PITCH, -25 * s )
	rot[J["L_ForeArm"]] = quat( PITCH, -20 )
	rot[J["R_ForeArm"]] = quat( PITCH, -20 )
	rot[J["Spine"]] = qmul( quat( PITCH, 4 ), quat( YAW, 5 * s ) )
	return rot, ( 0, 0, 1.0 * abs( c ) )

# name, frames, fps, pose function
ANIMS = [ ( "idle", 20, 10.0, idle_pose ), ( "walk", 12, 12.0, walk_pose ) ]

def tangent( n ):
	# any direction along the (axial) face, and the bitangent's handedness
	return ( 0, 1, 0, 1 ) if n[0] else ( 1, 0, 0, 1 )

def build():
	pos, nrm, tc, bidx, bwt, tris, meshes = [], [], [], [], [], [], []
	faces = [
		( ( 1, 0, 0 ), [ ( 1, 0, 0 ), ( 1, 1, 0 ), ( 1, 1, 1 ), ( 1, 0, 1 ) ] ),
		( ( -1, 0, 0 ), [ ( 0, 1, 0 ), ( 0, 0, 0 ), ( 0, 0, 1 ), ( 0, 1, 1 ) ] ),
		( ( 0, 1, 0 ), [ ( 1, 1, 0 ), ( 0, 1, 0 ), ( 0, 1, 1 ), ( 1, 1, 1 ) ] ),
		( ( 0, -1, 0 ), [ ( 0, 0, 0 ), ( 1, 0, 0 ), ( 1, 0, 1 ), ( 0, 0, 1 ) ] ),
		( ( 0, 0, 1 ), [ ( 0, 0, 1 ), ( 1, 0, 1 ), ( 1, 1, 1 ), ( 0, 1, 1 ) ] ),
		( ( 0, 0, -1 ), [ ( 0, 1, 0 ), ( 1, 1, 0 ), ( 1, 0, 0 ), ( 0, 0, 0 ) ] ),
	]
	for joint, mins, maxs, colour in BOXES:
		u = ( colour + 0.5 ) / len( COLOURS )
		for normal, corners in faces:
			base = len( pos )
			for cx, cy, cz in corners:
				pos.append( ( maxs[0] if cx else mins[0], maxs[1] if cy else mins[1], maxs[2] if cz else mins[2] ) )
				nrm.append( normal )
				tc.append( ( u, 0.5 ) )
				bidx.append( ( J[joint], 0, 0, 0 ) )
				bwt.append( ( 255, 0, 0, 0 ) )
			# counter-clockwise from outside, as Quake 3 culls the back
			tris.append( ( base, base + 2, base + 1 ) )
			tris.append( ( base, base + 3, base + 2 ) )
	return pos, nrm, tc, bidx, bwt, tris

def write_iqm( path ):
	pos, nrm, tc, bidx, bwt, tris = build()
	text = b"\0"
	def addtext( s ):
		nonlocal text
		ofs = len( text )
		text += s.encode() + b"\0"
		return ofs
	mesh_name = addtext( "body" )
	material = addtext( "characters/test/testchar" )
	joint_names = [ addtext( n ) for n, _, _ in JOINTS ]
	anim_names = [ addtext( a[0] ) for a in ANIMS ]
	while len( text ) % 4:
		text += b"\0"

	nv, nt, nj = len( pos ), len( tris ), len( JOINTS )

	# frames: every channel of every joint, quantised per channel over all frames
	frames = []		# [frame][joint] = 10 floats
	for name, count, fps, fn in ANIMS:
		for f in range( count ):
			rot, hips = fn( f / count )
			channels = []
			for i in range( nj ):
				t = list( local_translation( i ) )
				if i == J["Hips"]:
					t = [ t[0] + hips[0], t[1] + hips[1], t[2] + hips[2] ]
				q = rot[i]
				channels.append( t + list( q ) + [ 1, 1, 1 ] )
			frames.append( channels )
	nf = len( frames )
	poses = []
	for i in range( nj ):
		offs, scales = [], []
		for c in range( 10 ):
			vals = [ frames[f][i][c] for f in range( nf ) ]
			lo, hi = min( vals ), max( vals )
			offs.append( lo )
			scales.append( ( hi - lo ) / 65535.0 if hi > lo else 0.0 )
		poses.append( ( offs, scales ) )
	framedata = b""
	for f in range( nf ):
		for i in range( nj ):
			offs, scales = poses[i]
			for c in range( 10 ):
				v = 0 if scales[c] == 0 else round( ( frames[f][i][c] - offs[c] ) / scales[c] )
				framedata += struct.pack( "<H", max( 0, min( 65535, v ) ) )
	if len( framedata ) % 4:
		framedata += b"\0" * ( 4 - len( framedata ) % 4 )

	# layout
	ofs = 124
	sections = {}
	def place( name, data ):
		nonlocal ofs
		sections[name] = ( ofs, data )
		ofs += len( data )
	place( "text", text )
	place( "meshes", struct.pack( "<6I", mesh_name, material, 0, nv, 0, nt ) )
	va_data = [
		( 0, 7, 3, b"".join( struct.pack( "<3f", *p ) for p in pos ) ),			# position
		( 1, 7, 2, b"".join( struct.pack( "<2f", *t ) for t in tc ) ),			# texcoord
		( 2, 7, 3, b"".join( struct.pack( "<3f", *n ) for n in nrm ) ),			# normal
		( 3, 7, 4, b"".join( struct.pack( "<4f", *tangent( n ) ) for n in nrm ) ),	# tangent
		( 4, 1, 4, b"".join( struct.pack( "<4B", *b ) for b in bidx ) ),			# blend indexes
		( 5, 1, 4, b"".join( struct.pack( "<4B", *w ) for w in bwt ) ),			# blend weights
	]
	va_headers_ofs = ofs
	ofs += 20 * len( va_data )
	va_headers = b""
	for vtype, fmt, size, data in va_data:
		va_headers += struct.pack( "<5I", vtype, 0, fmt, size, ofs )
		sections["va%d" % vtype] = ( ofs, data )
		ofs += len( data )
	sections["vaheaders"] = ( va_headers_ofs, va_headers )
	place( "triangles", b"".join( struct.pack( "<3I", *t ) for t in tris ) )
	place( "joints", b"".join( struct.pack( "<Ii3f4f3f", joint_names[i], JOINTS[i][1], *local_translation( i ), 0, 0, 0, 1, 1, 1, 1 ) for i in range( nj ) ) )
	place( "poses", b"".join( struct.pack( "<iI10f10f", JOINTS[i][1], 0x3ff, *poses[i][0], *poses[i][1] ) for i in range( nj ) ) )
	animdata = b""
	first = 0
	for k, ( name, count, fps, fn ) in enumerate( ANIMS ):
		animdata += struct.pack( "<IIIfI", anim_names[k], first, count, fps, 1 )	# 1: loop
		first += count
	place( "anims", animdata )
	place( "frames", framedata )
	place( "bounds", b"".join( struct.pack( "<8f", -12, -12, -24, 12, 12, 44, 12, 44 ) for _ in range( nf ) ) )
	filesize = ofs

	header = b"INTERQUAKEMODEL\0" + struct.pack( "<27I",
		2, filesize, 0,
		len( text ), sections["text"][0],
		1, sections["meshes"][0],
		len( va_data ), nv, va_headers_ofs,
		nt, sections["triangles"][0], 0,
		nj, sections["joints"][0],
		nj, sections["poses"][0],
		len( ANIMS ), sections["anims"][0],
		nf, nj * 10, sections["frames"][0], sections["bounds"][0],
		0, 0, 0, 0 )
	assert len( header ) == 124
	out = bytearray( filesize )
	out[0:124] = header
	for name, ( o, data ) in sections.items():
		out[o:o + len( data )] = data
	with open( path, "wb" ) as f:
		f.write( out )
	print( "%s: %d joints, %d vertexes, %d triangles, %d frames" % ( path, nj, nv, nt, nf ) )

def write_tga( path ):
	w, h = 64, 4
	data = b""
	for y in range( h ):
		for x in range( w ):
			r, g, b = COLOURS[x * len( COLOURS ) // w]
			data += bytes( ( b, g, r ) )
	with open( path, "wb" ) as f:
		f.write( struct.pack( "<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 24, 0 ) + data )

if __name__ == "__main__":
	out = sys.argv[1] if len( sys.argv ) > 1 else os.path.join( os.path.dirname( __file__ ), "..", "..", "characters", "test" )
	os.makedirs( out, exist_ok = True )
	write_iqm( os.path.join( out, "testchar.iqm" ) )
	write_tga( os.path.join( out, "testchar.tga" ) )
