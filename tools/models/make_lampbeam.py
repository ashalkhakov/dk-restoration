#!/usr/bin/env python3
"""
Writes gfx/fx/lampbeam.tga: a lamp's beam seen through dusty air (scripts/
dk_weapons.shader dkfx/lampbeam, drawn by cg_character.c along a lamp's
light): across its width (u) bright in the middle, soft to nothing at its
edges; along its length (v) faint streaks of dust. Grey: the lamp's colour
and its fading along the beam are the vertexes' (rgbGen vertex, added).

	python3 tools/models/make_lampbeam.py
"""
import math
import os
import random
import struct

ROOT = os.path.normpath( os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), "..", ".." ) )
W, H = 64, 128

def main():
	rnd = random.Random( 7 )
	streak = [ 0.8 + 0.2 * rnd.random() for _ in range( W ) ]
	data = bytearray()
	for y in range( H ):
		for x in range( W ):
			u = ( x + 0.5 ) / W * 2 - 1		# -1..1 across
			core = math.exp( -u * u * 6.0 )
			edge = max( 0.0, 1 - abs( u ) ) ** 2
			v = 255 * ( 0.65 * core + 0.35 * edge ) * streak[x]
			c = max( 0, min( 255, int( v ) ) )
			data += bytes( ( c, c, c ) )
	path = os.path.join( ROOT, "gfx", "fx", "lampbeam.tga" )
	os.makedirs( os.path.dirname( path ), exist_ok = True )
	with open( path, "wb" ) as f:
		f.write( struct.pack( "<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, W, H, 24, 0 ) + data )
	print( path )

if __name__ == "__main__":
	main()
