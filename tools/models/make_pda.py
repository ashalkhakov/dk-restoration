#!/usr/bin/env python3
"""
Writes characters/props/pda.iqm, pda_lid.iqm, pda.tga and pda_glow.tga: the
skinny worker's PDA (the intro, shots 109 and 110: he takes it out, taps in
a few keys, the beeps the cutscene plays, and puts it back). Daikatana's was
a folded translucent box in his mesh; this is a handheld of our own.

A clamshell, folding to fit his pocket: two halves, each a box with its
edges bevelled, a dark plastic case. Open, they lie end to end, faces up
(+z): pda.iqm the near half (-x, in his hand), a keypad of twelve keys;
pda_lid.iqm the far (+x), a green screen. Each is one joint at the hinge,
the middle of the top edge across (y): the lid turned 180 degrees about y
there lies face down on the keypad (tools/rig/iqm_hold.py turns it). Quake
units, Daikatana's characters' scale: the skinny worker is 57 tall, his
hand about 4 long.

	python3 tools/models/make_pda.py [out dir]

The shader (scripts/dk_characters.shader, characters/props/pda) adds the
glow over the screen.
"""
import os
import struct
import sys

L, W, T = 4.6, 2.8, 0.36		# open: length (x), width (y); a half's thickness (z)
B = 0.15					# the bevel
TEX = 128					# the texture's size: the face on its left half, the case on its right

def build( x0, x1 ):
	"""a half, from x0 to x1 along the open PDA, its face at z 0 (the
	hinge's): the face, the back, and a bevelled band round the sides"""
	pos, nrm, tc, tris = [], [], [], []
	def quad( corners, normal, uvs ):
		base = len( pos )
		for p, uv in zip( corners, uvs ):
			pos.append( p )
			nrm.append( normal )
			tc.append( uv )
		# counter-clockwise from outside, as Quake 3 culls the back
		tris.append( ( base, base + 2, base + 1 ) )
		tris.append( ( base, base + 3, base + 2 ) )
	y0, y1 = -W / 2, W / 2
	ztop, zbot = 0.0, -T
	# the face, its texture the left half of the image (u 0..0.5): the whole
	# open PDA's face down it (v 1 at the near end, 0 at the far), each half
	# its own end of it
	v = lambda x: 1 - ( x + L / 2 ) / L
	quad( [ ( x0 + B, y0 + B, ztop ), ( x0 + B, y1 - B, ztop ), ( x1 - B, y1 - B, ztop ), ( x1 - B, y0 + B, ztop ) ],
		  ( 0, 0, 1 ), [ ( 0.5, v( x0 + B ) ), ( 0, v( x0 + B ) ), ( 0, v( x1 - B ) ), ( 0.5, v( x1 - B ) ) ] )
	# the back and the sides, plastic (the right half)
	plastic = [ ( 0.55, 0.05 ), ( 0.95, 0.05 ), ( 0.95, 0.95 ), ( 0.55, 0.95 ) ]
	quad( [ ( x0 + B, y0 + B, zbot ), ( x1 - B, y0 + B, zbot ), ( x1 - B, y1 - B, zbot ), ( x0 + B, y1 - B, zbot ) ],
		  ( 0, 0, -1 ), plastic )
	# the band: each side its top bevel, its wall and its bottom bevel
	sides = [
		( ( 1, 0 ), ( x1, y0, x1, y1 ) ),
		( ( -1, 0 ), ( x0, y1, x0, y0 ) ),
		( ( 0, 1 ), ( x1, y1, x0, y1 ) ),
		( ( 0, -1 ), ( x0, y0, x1, y0 ) ),
	]
	for ( nx, ny ), ( ax, ay, bx, by ) in sides:
		# the wall's two ends, pulled in by the bevel along it
		dx, dy = ( bx - ax ), ( by - ay )
		length = ( dx * dx + dy * dy ) ** 0.5
		ux, uy = dx / length, dy / length
		a = ( ax + ux * B, ay + uy * B )
		b = ( bx - ux * B, by - uy * B )
		ia = ( a[0] - nx * B, a[1] - ny * B )
		ib = ( b[0] - nx * B, b[1] - ny * B )
		quad( [ ( a[0], a[1], zbot + B ), ( b[0], b[1], zbot + B ), ( b[0], b[1], ztop - B ), ( a[0], a[1], ztop - B ) ],
			  ( nx, ny, 0 ), plastic )
		s = 0.7071
		quad( [ ( a[0], a[1], ztop - B ), ( b[0], b[1], ztop - B ), ( ib[0], ib[1], ztop ), ( ia[0], ia[1], ztop ) ],
			  ( nx * s, ny * s, s ), plastic )
		quad( [ ( ia[0], ia[1], zbot ), ( ib[0], ib[1], zbot ), ( b[0], b[1], zbot + B ), ( a[0], a[1], zbot + B ) ],
			  ( nx * s, ny * s, -s ), plastic )
	# the corners' bevels: a triangle each, top and bottom, and the corner's edge
	for cx, cy in ( ( x0, y0 ), ( x1, y0 ), ( x1, y1 ), ( x0, y1 ) ):
		sx, sy = ( 1 if cx > 0 else -1 ), ( 1 if cy > 0 else -1 )
		p = ( cx - sx * B, cy, )
		q = ( cx, cy - sy * B )
		for z, zin, nz in ( ( ztop - B, ztop, 1 ), ( zbot + B, zbot, -1 ) ):
			base = len( pos )
			corner = ( cx - sx * B, cy - sy * B, zin )
			pts = [ ( p[0], p[1], z ), ( q[0], q[1], z ), corner ]
			if ( sx * sy > 0 ) == ( nz > 0 ):
				pts = [ pts[1], pts[0], pts[2] ]
			for pt in pts:
				pos.append( pt )
				nrm.append( ( sx * 0.577, sy * 0.577, nz * 0.577 ) )
				tc.append( ( 0.75, 0.5 ) )
			tris.append( ( base, base + 1, base + 2 ) )
		quad( [ ( p[0], p[1], zbot + B ), ( q[0], q[1], zbot + B ), ( q[0], q[1], ztop - B ), ( p[0], p[1], ztop - B ) ]
			  if sx * sy < 0 else
			  [ ( q[0], q[1], zbot + B ), ( p[0], p[1], zbot + B ), ( p[0], p[1], ztop - B ), ( q[0], q[1], ztop - B ) ],
			  ( sx * 0.7071, sy * 0.7071, 0 ), plastic )
	# each triangle wound as Quake 3 culls: ( b - a ) x ( c - a ) away from
	# its normal (make_testchar.py's faces), whichever way it was listed
	fixed = []
	for t in tris:
		a, b, c = ( pos[i] for i in t )
		e1 = [ b[k] - a[k] for k in range( 3 ) ]
		e2 = [ c[k] - a[k] for k in range( 3 ) ]
		cr = ( e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0] )
		n = nrm[t[0]]
		fixed.append( ( t[0], t[2], t[1] ) if sum( cr[k] * n[k] for k in range( 3 ) ) > 0 else t )
	return pos, nrm, tc, fixed

def tangent( n ):
	return ( 0, 1, 0, 1 ) if abs( n[0] ) > 0.5 else ( 1, 0, 0, 1 )

def write_iqm( path, x0, x1 ):
	pos, nrm, tc, tris = build( x0, x1 )
	text = b"\0"
	def addtext( s ):
		nonlocal text
		ofs = len( text )
		text += s.encode() + b"\0"
		return ofs
	mesh_name = addtext( "pda" )
	material = addtext( "characters/props/pda" )
	joint_name = addtext( "pda" )
	while len( text ) % 4:
		text += b"\0"
	nv, nt = len( pos ), len( tris )
	ofs = 124
	sections = {}
	def place( name, data ):
		nonlocal ofs
		sections[name] = ( ofs, data )
		ofs += len( data )
	place( "text", text )
	place( "meshes", struct.pack( "<6I", mesh_name, material, 0, nv, 0, nt ) )
	va_data = [
		( 0, 7, 3, b"".join( struct.pack( "<3f", *p ) for p in pos ) ),
		( 1, 7, 2, b"".join( struct.pack( "<2f", *t ) for t in tc ) ),
		( 2, 7, 3, b"".join( struct.pack( "<3f", *n ) for n in nrm ) ),
		( 3, 7, 4, b"".join( struct.pack( "<4f", *tangent( n ) ) for n in nrm ) ),
		( 4, 1, 4, b"".join( struct.pack( "<4B", 0, 0, 0, 0 ) for _ in pos ) ),
		( 5, 1, 4, b"".join( struct.pack( "<4B", 255, 0, 0, 0 ) for _ in pos ) ),
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
	place( "joints", struct.pack( "<Ii3f4f3f", joint_name, -1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1 ) )
	filesize = ofs
	header = b"INTERQUAKEMODEL\0" + struct.pack( "<27I",
		2, filesize, 0,
		len( text ), sections["text"][0],
		1, sections["meshes"][0],
		len( va_data ), nv, va_headers_ofs,
		nt, sections["triangles"][0], 0,
		1, sections["joints"][0],
		0, 0, 0, 0, 0, 0, 0, 0,
		0, 0, 0, 0 )
	assert len( header ) == 124
	out = bytearray( filesize )
	out[0:124] = header
	for name, ( o, data ) in sections.items():
		out[o:o + len( data )] = data
	with open( path, "wb" ) as f:
		f.write( out )
	print( "%s: %d vertexes, %d triangles" % ( path, nv, nt ) )

def tga( path, pixel ):
	data = bytearray()
	for y in range( TEX ):
		for x in range( TEX ):
			r, g, b = pixel( x / TEX, 1 - ( y + 0.5 ) / TEX )
			data += bytes( ( max( 0, min( 255, int( b ) ) ), max( 0, min( 255, int( g ) ) ), max( 0, min( 255, int( r ) ) ) ) )
	with open( path, "wb" ) as f:
		f.write( struct.pack( "<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, TEX, TEX, 24, 0 ) + data )
	print( path )

# the face's layout, in its own u (0..1 across the left half: the device's
# width) and v (0 at the near end, 1 at the far): the screen the far half,
# the keys three across and four down the near
SCREEN = ( 0.12, 0.88, 0.52, 0.93 )		# u0 u1 v0 v1
KEYS = ( 0.14, 0.86, 0.07, 0.45 )

def screen_at( u, v ):
	u0, u1, v0, v1 = SCREEN
	if not ( u0 <= u <= u1 and v0 <= v <= v1 ):
		return None
	su, sv = ( u - u0 ) / ( u1 - u0 ), ( v - v0 ) / ( v1 - v0 )
	g = 40
	# lines of text, a little graph, the scan lines
	if 0.12 < su < 0.88 and any( abs( sv - l ) < 0.035 for l in ( 0.82, 0.7, 0.58 ) ) and ( su * 13 ) % 1 < 0.75:
		g = 200
	if 0.12 < su < 0.88 and 0.12 < sv < 0.42 and abs( sv - ( 0.27 + 0.1 * ( ( su * 6 ) % 1 - 0.5 ) ) ) < 0.03:
		g = 230
	if int( sv * 40 ) % 2:
		g *= 0.85
	return ( g * 0.35, g, g * 0.45 )

def key_at( u, v ):
	u0, u1, v0, v1 = KEYS
	if not ( u0 <= u <= u1 and v0 <= v <= v1 ):
		return None
	cu, cv = ( u - u0 ) / ( u1 - u0 ) * 3, ( v - v0 ) / ( v1 - v0 ) * 4
	fu, fv = cu % 1, cv % 1
	if 0.12 < fu < 0.88 and 0.15 < fv < 0.85:
		shade = 175 if fv > 0.5 else 150
		return ( shade, shade, shade * 1.05 )
	return ( 30, 30, 34 )

def base( x, y ):
	if x < 0.5:
		u, v = x / 0.5, y
		px = screen_at( u, v ) or key_at( u, v )
		if px:
			return px
		return ( 52, 54, 58 )		# the face's plastic, round them
	# the case: dark grey, a faint grain
	n = ( ( int( x * TEX ) * 7 + int( y * TEX ) * 13 ) % 5 ) * 2
	return ( 38 + n, 40 + n, 44 + n )

def glow( x, y ):
	if x < 0.5:
		px = screen_at( x / 0.5, y )
		if px:
			return ( px[0] * 0.6, px[1] * 0.6, px[2] * 0.6 )
	return ( 0, 0, 0 )

if __name__ == "__main__":
	out = sys.argv[1] if len( sys.argv ) > 1 else os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), "..", "..", "characters", "props" )
	os.makedirs( out, exist_ok = True )
	write_iqm( os.path.join( out, "pda.iqm" ), -L / 2, 0 )
	write_iqm( os.path.join( out, "pda_lid.iqm" ), 0, L / 2 )
	tga( os.path.join( out, "pda.tga" ), base )
	tga( os.path.join( out, "pda_glow.tga" ), glow )
