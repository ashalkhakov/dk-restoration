#!/usr/bin/env python3
"""
Puts another outfit of a character, rigged on its own (Hiro's gi, from the
intro's cinematic model), on the character's rig (Hiro's), animations and all:
one IQM, one skeleton, both meshes, the character's animations and the
outfit's. A .skin of the outfit's surfaces shows it (the others "nodraw"),
one of the character's shows the character as it was.

How:
 1. Both rigs have Doom 3's joint names (tools/rig/autorig.py). An outfit
    joint the character lacks (an extra bone) goes with its nearest
    ancestor the character has.
 2. The outfit's vertexes are bound again, joint by joint: from the outfit
    joint's rest to the character's (so the outfit takes the character's
    proportions where they differ).
 3. The outfit's animations as the character's joints': each joint as the
    outfit's lies (its rest frame turned to the outfit's, then moved as the
    outfit's moves from its rest, in the world); the
    bones the character's lengths; the body's going about (its place over
    the origin) scaled by the two's heights. A joint the outfit lacks turns
    with its parent.
 4. <out base>.iqm: the character's mesh, then the outfit's surfaces (named
    <prefix>_<surface>), the character's animations as they are, then the
    outfit's ("c_" before a name the character has); <out base>.skin and
    <out base>_<prefix>.skin.

	python3 tools/rig/outfit.py dkres/models/rigged/hiro.iqm dkres/models/rigged/hirogi.iqm gi dkres/models/rigged/hiro_outfits
	python3 tools/rig/outfit.py --defs def/char_hiro.def def/rig_hirogi.def <the same>
--defs: the character's model def and the outfit's (as autorig wrote them) on
the IQM with both, each in its skin, the outfit's animations by their names
in it.

Pure Python (no numpy): a few seconds.
"""
import os
import re
import struct
import sys

sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
from autorig import vsub, vadd, vscale, mvec, mmul, mtrans, quat_to_mat, xform, write_iqm, gamePath
from retarget import load_rig, compose, inverse, Frames

def main( basePath, outfitPath, prefix, outBase ):
	q, body, verts, rest, joints, restWorld, weights = load_rig( basePath )
	oq, obody, overts, orest, ojoints, orestWorld, oweights = load_rig( outfitPath )
	nj, onj = len( joints ), len( ojoints )
	J = { j["name"]: i for i, j in enumerate( joints ) }
	OJ = { j["name"]: i for i, j in enumerate( ojoints ) }

	# 1. an outfit joint -> the character's: itself, else its nearest ancestor's
	anc = []
	for j in range( onj ):
		k = j
		while k >= 0 and ojoints[k]["name"] not in J:
			k = ojoints[k]["parentIndex"]
		anc.append( k if k >= 0 else 0 )
	tojoint = [ J[ojoints[anc[j]]["name"]] if ojoints[anc[j]]["name"] in J else 0 for j in range( onj ) ]
	missing = sorted( set( ojoints[j]["name"] for j in range( onj ) if anc[j] != j ) )
	if missing:
		print( "  the character hasn't %s: on their ancestors" % ", ".join( missing ) )

	# 2. the outfit's vertexes bound again
	rebind = [ compose( restWorld[tojoint[j]], inverse( orestWorld[anc[j]] ) ) for j in range( onj ) ]
	base = len( body )
	for k, s in enumerate( obody ):
		s.name = "%s_%s" % ( prefix, s.name )
		body.append( s )
	for ( k, vi ), p, ( b, o, w ) in zip( overts, orest, oweights ):
		a = xform( rebind[b], p )
		c = xform( rebind[o], p )
		verts.append( ( base + k, vi ) )
		rest.append( vadd( vscale( a, w ), vscale( c, 1.0 - w ) ) )
		weights.append( ( tojoint[b], tojoint[o], w ) )

	# 3. the outfit's animations as the character's joints': each turned
	# from its rest as the outfit's is, each at the end of its parent's bone
	# (the character's), the body where the outfit's is (scaled)
	height = restWorld[J["Body"]][1][2] - restWorld[J["origin"]][1][2]
	oheight = orestWorld[OJ["Body"]][1][2] - orestWorld[OJ["origin"]][1][2]
	scale = height / oheight if oheight > 1e-6 else 1.0
	carried = ( "origin", "Body" )		# their places move (the going about); the others' are the bones
	invRest = [ inverse( restWorld[j] ) for j in range( nj ) ]
	oinvRest = [ inverse( orestWorld[j] ) for j in range( onj ) ]
	def world_frames( q, n ):
		out = []
		for f in range( len( q.frames ) ):
			w = []
			for j in range( n ):
				t, rq, sc = q.frames[f][j]
				loc = ( quat_to_mat( rq ), t )
				p = q.joints[j].parent
				w.append( loc if p < 0 else compose( w[p], loc ) )
			out.append( w )
		return out
	own = [ [ compose( w[j], invRest[j] ) for j in range( nj ) ] for w in world_frames( q, nj ) ]
	# the character's rest turned to the outfit's (each joint's frame lies
	# along its bone in both): the outfit's motion goes on from there
	align = [ mmul( orestWorld[OJ[j["name"]]][0], mtrans( restWorld[k][0] ) ) if j["name"] in OJ else None
			  for k, j in enumerate( joints ) ]
	worn = []
	for ow in world_frames( oq, onj ):
		omot = [ compose( ow[j], oinvRest[j] ) for j in range( onj ) ]
		rot, place = [], []
		for j in range( nj ):
			name, p = joints[j]["name"], joints[j]["parentIndex"]
			oj = OJ.get( name )
			pos = joints[j]["pos"]
			if oj is not None and ( p < 0 or name in carried ):
				opos = ojoints[oj]["pos"]
				at = vadd( pos, vscale( vsub( xform( omot[oj], opos ), opos ), scale ) )
			else:
				at = vadd( place[p], mvec( rot[p], vsub( pos, joints[p]["pos"] ) ) )
			r = mmul( omot[oj][0], align[j] ) if oj is not None else rot[p]
			rot.append( r )
			place.append( at )
		worn.append( [ ( rot[j], vsub( place[j], mvec( rot[j], joints[j]["pos"] ) ) ) for j in range( nj ) ] )
	frames = own + worn
	motion = [ { f: frames[f][j] for f in range( len( frames ) ) } for j in range( nj ) ]

	# 4. the IQM, then each animation's own rate
	taken = set( a[0] for a in q.anims )
	anims = [ ( a[0], a[1], a[2] ) for a in q.anims ]
	rates = [ ( a[3], a[4] & 1 ) for a in q.anims ]
	F0 = len( q.frames )
	names = {}
	for a in oq.anims:
		name = a[0]
		while name in taken:
			name = "c_" + name
		taken.add( name )
		names[a[0]] = name
		anims.append( ( name, F0 + a[1], a[2] ) )
		rates.append( ( a[3], a[4] & 1 ) )
	class Loops:
		def match( self, name ):
			return any( a[0] == name and r[1] for a, r in zip( anims, rates ) )
	write_iqm( Frames( len( frames ), anims ), body, verts, rest, joints, motion, weights, outBase, looping = Loops() )
	data = bytearray( open( outBase + ".iqm", "rb" ).read() )
	ofsAnims = struct.unpack_from( "<I", data, 16 + 4 * 18 )[0]
	for k, ( fps, loop ) in enumerate( rates ):
		struct.pack_into( "<fI", data, ofsAnims + 20 * k + 12, fps, loop )
	open( outBase + ".iqm", "wb" ).write( bytes( data ) )

	# the skins: the character as it was, and in the outfit
	for path, shown in ( ( outBase + ".skin", body[:base] ), ( "%s_%s.skin" % ( outBase, prefix ), body[base:] ) ):
		with open( path, "w" ) as fp:
			for s in body:
				fp.write( "%s,%s\n" % ( s.name, ( s.shader or "skins/default" ) if s in shown else "nodraw" ) )
		print( "  wrote %s" % path )
	renamed = sorted( ( k, v ) for k, v in names.items() if k != v )
	print( "  %s: %d joints; its %d animations, then %s's %d%s" % ( outBase + ".iqm", nj, len( q.anims ), prefix, len( oq.anims ),
		( " (renamed: %s)" % ", ".join( "%s -> %s" % r for r in renamed ) ) if renamed else "" ) )
	return names

def wear( defPath, mesh, skin, names = None, skeleton = None ):
	"""A model def ("made by tools/rig/autorig.py") on the IQM with both, in
	that skin; its animations by their names there (names: the outfit's);
	skeleton: the character's def, whose hitboxes and ragdoll it takes (its
	skeleton's now)"""
	text = open( defPath ).read()
	if skeleton:
		theirs = open( skeleton ).read()
		keys = r'\n\t"(hitbox \S+|ragdoll)"[^\n]*'
		mine = [ m.start() for m in re.finditer( keys, text ) ]
		if mine:
			at = mine[0]
			text = re.sub( keys, "", text )
			text = text[:at] + "".join( m.group( 0 ) for m in re.finditer( keys, theirs ) ) + text[at:]
	text, n = re.subn( r'("mesh"\s+)"[^"]*"', lambda m: '%s"%s"' % ( m.group( 1 ), mesh ), text, count = 1 )
	if not n:
		sys.exit( "%s: no mesh" % defPath )
	text = re.sub( r'\n\t"skin"[^\n]*', "", text )
	text = re.sub( r'(\n\t"mesh"[^\n]*)', lambda m: '%s\n\t"skin"\t\t\t\t"%s"\t// tools/rig/outfit.py' % ( m.group( 1 ), skin ), text, count = 1 )
	if names:
		def anim( m ):
			first, rest = m.group( 2 ).split( " ", 1 ) if " " in m.group( 2 ) else ( m.group( 2 ), None )
			first = names.get( first, first )
			return '%s"%s"' % ( m.group( 1 ), first + ( " " + rest if rest else "" ) )
		text = re.sub( r'("anim \S+"\s+)"([^"]*)"', anim, text )
	open( defPath, "w" ).write( text )
	print( "  %s: %s, %s" % ( defPath, mesh, skin ) )

if __name__ == "__main__":
	args = sys.argv[1:]
	defs = None
	if args and args[0] == "--defs":
		defs, args = args[1:3], args[3:]
	if len( args ) != 4:
		sys.exit( __doc__ )
	names = main( *args )
	if defs:
		outBase, prefix = args[3], args[2]
		wear( defs[0], gamePath( outBase + ".iqm" ), gamePath( outBase + ".skin" ) )
		wear( defs[1], gamePath( outBase + ".iqm" ), gamePath( "%s_%s.skin" % ( outBase, prefix ) ), names, defs[0] )
