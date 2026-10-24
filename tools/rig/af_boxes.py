#!/usr/bin/env python3
"""
A ragdoll's boxes placed by hand (af/<name>.af): each body named in a file a
box about what of the mesh lies along a segment given in its bind pose,
whatever bone carries it; everything else in the AF kept. For a creature
whose bones don't lie along its limbs (the froginator's: his left shin and
foot one bone, his right thigh's taking in his hip), where af_refit.py's
humans' template doesn't go.

	python3 tools/rig/af_boxes.py <model def> <file>

writes out/rig/af/<name>.af, for the user to validate (./dk viewer) and copy
over. The file's lines (# comments; z up, the model's front +x, its left +y):

	<body> <joint> x y z x y z r <reach> [fixed <body>]

the body's box along the segment, about the mesh's points (its vertexes and
points across its triangles) within reach of it, from just before its start
to just past its end; on that joint. A body the AF hasn't is added (a copy
of the settings of the body on that joint, or the first's) and, with
"fixed", held to the body named there (Doom 3's fixed constraint: the
froginator's left foot, on his shin's bone, as his shin).
"""
import math
import os
import re
import sys

sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
import rigcheck as rc
import af_refit

ROOT = os.path.normpath( os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), "..", ".." ) )
SAMPLES = 4		# points across a triangle, each way

def seg_t( p, a, b ):
	d = [ b[k] - a[k] for k in range( 3 ) ]
	L2 = sum( x * x for x in d ) or 1e-9
	return sum( ( p[k] - a[k] ) * d[k] for k in range( 3 ) ) / L2

def seg_dist( p, a, b ):
	t = max( 0.0, min( 1.0, seg_t( p, a, b ) ) )
	return math.dist( p, [ a[k] + t * ( b[k] - a[k] ) for k in range( 3 ) ] )

def read_boxes( path ):
	out = []
	for n, line in enumerate( open( path ), 1 ):
		w = line.split( "#" )[0].split()
		if not w:
			continue
		if len( w ) < 10 or w[8] != "r":
			sys.exit( "%s:%d: <body> <joint> x y z x y z r <reach> [fixed <body>]" % ( path, n ) )
		v = [ float( x ) for x in w[2:8] ]
		out.append( { "body": w[0], "joint": w[1], "a": v[0:3], "b": v[3:6], "reach": float( w[9] ),
					  "fixed": w[11] if len( w ) >= 12 and w[10] == "fixed" else None } )
	return out

def main( defName, path ):
	info = rc.model_info( defName )
	if not info:
		sys.exit( "%s: no rigged model def" % defName )
	defDir = os.path.join( ROOT, "def" )
	defFile = [ f for f in sorted( os.listdir( defDir ) ) if f.endswith( ".def" )
				and re.search( r"entityDef\s+%s\b[^}]*\"ragdoll\"" % re.escape( defName ), open( os.path.join( defDir, f ), encoding = "latin-1" ).read() ) ][0]
	afName = re.search( r'"ragdoll"\s+"([^"]+)"', open( os.path.join( defDir, defFile ), encoding = "latin-1" ).read() ).group( 1 )
	af = open( os.path.join( ROOT, "af", afName + ".af" ) ).read()
	rig = rc.load_rig( info )

	# the mesh's points: its vertexes and points across its triangles
	pts = list( rig.pos )
	for t in rig.q.triangles:
		p0, p1, p2 = ( rig.pos[v] for v in t )
		for i in range( SAMPLES + 1 ):
			for j in range( SAMPLES + 1 - i ):
				u, w = i / SAMPLES, j / SAMPLES
				pts.append( tuple( p0[k] + ( p1[k] - p0[k] ) * u + ( p2[k] - p0[k] ) * w for k in range( 3 ) ) )

	report = []
	for box in read_boxes( path ):
		a, b = box["a"], box["b"]
		ps = [ p for p in pts if seg_dist( p, a, b ) <= box["reach"] and -0.05 <= seg_t( p, a, b ) <= 1.05 ]
		if len( ps ) < 4:
			sys.exit( "%s: %d points along it" % ( box["body"], len( ps ) ) )
		c, h, axes = af_refit.obb( ps, [ b[k] - a[k] for k in range( 3 ) ], ( a, b ) )
		ang, h = af_refit.box_angles( box["body"], axes, h )
		m = re.search( r'\tbody "%s" \{.*?\n\t\}' % re.escape( box["body"] ), af, re.S )
		if m:
			block = m.group( 0 )
		else:
			# a body of its own: the settings of the body on its joint (or the first's)
			src = re.search( r'\tbody "\w+" \{\n\t\tjoint "%s".*?\n\t\}' % re.escape( box["joint"] ), af, re.S ) \
				or re.search( r'\tbody "\w+" \{.*?\n\t\}', af, re.S )
			block = re.sub( r'\tbody "\w+"', '\tbody "%s"' % box["body"], src.group( 0 ), count = 1 )
			if "\t\tangles (" not in block:
				block = block.replace( "\t\torigin (", "\t\tangles ( 0, 0, 0 )\n\t\torigin (", 1 )
		new = re.sub( r'\t\tjoint "[^"]*"', '\t\tjoint "%s"' % box["joint"], block, count = 1 )
		new = re.sub( r"\t\tmodel [^\n]*", "\t\tmodel box( ( %.2f, %.2f, %.2f ), ( %.2f, %.2f, %.2f ) )" % ( -h[0], -h[1], -h[2], h[0], h[1], h[2] ), new, count = 1 )
		new = re.sub( r"\t\torigin \([^)]*\)", "\t\torigin ( %.2f, %.2f, %.2f )" % tuple( c ), new, count = 1 )
		if "\t\tangles (" in new:
			new = re.sub( r"\t\tangles \([^)]*\)", "\t\tangles ( %.1f, %.1f, %.1f )" % ang, new, count = 1 )
		else:
			new = new.replace( "\t\torigin (", "\t\tangles ( %.1f, %.1f, %.1f )\n\t\torigin (" % ang, 1 )
		if m:
			af = af.replace( block, new )
		else:
			# after the last body, its constraint after the last constraint
			last = list( re.finditer( r'\tbody "\w+" \{.*?\n\t\}\n', af, re.S ) )[-1]
			af = af[:last.end()] + "\n" + new + "\n" + af[last.end():]
			if box["fixed"]:
				end = af.rstrip().rfind( "\n}" )
				af = af[:end + 1] + '\tfixed "%s" {\n\t\tbody1 "%s"\n\t\tbody2 "%s"\n\t}\n\n' % ( box["body"], box["body"], box["fixed"] ) + af[end + 1:]
		report.append( "  %-10s %5d points: %.1f x %.1f x %.1f on %s%s" % ( box["body"], len( ps ), 2 * h[0], 2 * h[1], 2 * h[2],
					   box["joint"], ", fixed to %s" % box["fixed"] if box["fixed"] and not m else "" ) )
	dst = os.path.join( ROOT, "out", "rig", "af", afName + ".af" )
	os.makedirs( os.path.dirname( dst ), exist_ok = True )
	with open( dst, "w" ) as fp:
		fp.write( af )
	print( "%s (%s):" % ( afName, info[0] ) )
	print( "\n".join( report ) )
	print( "  wrote %s" % os.path.relpath( dst, ROOT ) )

if __name__ == "__main__":
	if len( sys.argv ) != 3:
		print( __doc__ )
		sys.exit( 1 )
	main( sys.argv[1], sys.argv[2] )
