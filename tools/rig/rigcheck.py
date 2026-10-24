#!/usr/bin/env python3
"""
What of the rigs has been validated, and whether it still is.

The user validates a rig an animation at a time, in the rig viewer (./dk
viewer): plays it over Daikatana's frames and marks it valid or broken.
The record is tools/rig/validated.json:

	{ "<model def>": { "iqm": "models/rigged/<name>.iqm",
	                   "anims": { "<animation>": { "verdict": "valid" | "broken",
	                                               "note": "...", "date": "YYYY-MM-DD",
	                                               "fingerprint": "...",
	                                               "fit": [ average, worst ],
	                                               "by": "<who>" (when recorded for them) } } } }

An animation's fingerprint is a hash of its skinned mesh, every frame, each
vertex rounded to 0.05 units: a rig made again that moves no vertex
visibly keeps it. Its fit is how far the skinned vertexes are from
Daikatana's frames (the MD3 the rig was made from, the root motion autorig
--root-out took out taken out of them too), on average and at worst.

	rigcheck.py                 every validated animation whose rig changed
	                            since: "revalidate" (exit status 1 if any);
	                            and the AF files (af/, the authority once
	                            written) whose regenerated version differs

	rigcheck.py --gate <def file> <iqm> [--change die,cdie]
	                            whether a rig made again may replace the one
	                            installed: every validated animation of its
	                            model the same (new animations, from the
	                            cinematics' MD3s, may come); --change lets
	                            the ones named so change, as the user asked
	                            (exit status 1, and those listed, if not)
	rigcheck.py --restamp <model def> [die,cdie]
	                            after installing what the gate let through:
	                            the validated animations' fingerprints from it

A validated rig doesn't change: ./dk rig makes each rig in out/rig/stage/
and installs it only if the gate lets it, else keeps the one there.
"""
import datetime
import hashlib
import json
import math
import os
import re
import sys
import threading

sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
from iqm import IQM, IQM_POSITION, IQM_BLENDINDEXES, IQM_BLENDWEIGHTS
from md3 import MD3

ROOT = os.path.normpath( os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), "..", ".." ) )
DKRES = os.path.join( ROOT, "dkres" )
RECORD = os.path.join( ROOT, "tools", "rig", "validated.json" )
GRID = 0.05		# units: a vertex moved less than this hasn't changed

# ------------------------------------------------------------------ math
# a transform: ( 3x3 matrix, translation ); the matrices may scale (props)

def mat( q, s ):
	x, y, z, w = q
	l = math.sqrt( x * x + y * y + z * z + w * w ) or 1.0
	x, y, z, w = x / l, y / l, z / l, w / l
	r = [ [ 1 - 2 * ( y * y + z * z ), 2 * ( x * y - z * w ), 2 * ( x * z + y * w ) ],
		  [ 2 * ( x * y + z * w ), 1 - 2 * ( x * x + z * z ), 2 * ( y * z - x * w ) ],
		  [ 2 * ( x * z - y * w ), 2 * ( y * z + x * w ), 1 - 2 * ( x * x + y * y ) ] ]
	return [ [ r[i][c] * s[i] for c in range( 3 ) ] for i in range( 3 ) ]	# (rows: the engine's, bg_model.c)

def apply( t, v ):
	m, o = t
	return ( m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2] + o[0],
			 m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2] + o[1],
			 m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2] + o[2] )

def compose( a, b ):
	"""a after b"""
	m = [ [ sum( a[0][i][k] * b[0][k][c] for k in range( 3 ) ) for c in range( 3 ) ] for i in range( 3 ) ]
	return m, apply( a, b[1] )

def invert( t ):
	m, o = t
	a, b, c = m[0]
	d, e, f = m[1]
	g, h, i = m[2]
	det = a * ( e * i - f * h ) - b * ( d * i - f * g ) + c * ( d * h - e * g )
	det = 1.0 / det if det else 0.0
	n = [ [ ( e * i - f * h ) * det, ( c * h - b * i ) * det, ( b * f - c * e ) * det ],
		  [ ( f * g - d * i ) * det, ( a * i - c * g ) * det, ( c * d - a * f ) * det ],
		  [ ( d * h - e * g ) * det, ( b * g - a * h ) * det, ( a * e - b * d ) * det ] ]
	p = apply( ( n, ( 0.0, 0.0, 0.0 ) ), o )
	return n, ( -p[0], -p[1], -p[2] )

# ------------------------------------------------------------------ the rig

class Rig:
	"""an IQM skinned: its vertexes at any frame"""
	def __init__( self, iqmPath ):
		self.q = q = IQM( iqmPath )
		bind = []
		for j in q.joints:
			local = ( mat( j.rotate, j.scale ), j.translate )
			bind.append( local if j.parent < 0 else compose( bind[j.parent], local ) )
		self.invBind = [ invert( b ) for b in bind ]
		self.pos = q.arrays[IQM_POSITION]
		self.bi = q.arrays.get( IQM_BLENDINDEXES )
		self.bw = q.arrays.get( IQM_BLENDWEIGHTS )
		self.anims = { a[0]: ( a[1], a[2] ) for a in q.anims }

	def frame( self, f ):
		world = []
		for j, jt in enumerate( self.q.joints ):
			t, r, s = self.q.frames[f][j]
			local = ( mat( r, s ), t )
			world.append( local if jt.parent < 0 else compose( world[jt.parent], local ) )
		skin = [ compose( w, ib ) for w, ib in zip( world, self.invBind ) ]
		out = []
		for v, p in enumerate( self.pos ):
			if not self.bi:
				out.append( apply( skin[0], p ) )
				continue
			x = y = z = wsum = 0.0
			for c in range( 4 ):
				w = self.bw[v][c] / 255.0
				if w:
					a = apply( skin[self.bi[v][c]], p )
					x, y, z, wsum = x + a[0] * w, y + a[1] * w, z + a[2] * w, wsum + w
			out.append( ( x / wsum, y / wsum, z / wsum ) if wsum else p )
		return out

	def fingerprint( self, anim ):
		first, count = self.anims[anim]
		h = hashlib.sha1()
		for f in range( first, first + count ):
			for p in self.frame( f ):
				h.update( ( "%d %d %d;" % tuple( int( round( c / GRID ) ) for c in p ) ).encode() )
		return h.hexdigest()[:16]

# ------------------------------------------------------------------ the fit

class Source:
	"""the MD3 a rig was made from, its vertexes matched to the rig's, and
	the root motion autorig took out (the rig's .json)"""
	def __init__( self, rig, md3Path, rootPath ):
		self.m = MD3( md3Path )
		self.anims = { name: ( first, n ) for name, first, n in self.m.animations() }
		self.root = json.load( open( rootPath ) )["anims"] if rootPath and os.path.exists( rootPath ) else {}
		pts = [ ( si, vi ) for si, s in enumerate( self.m.surfaces ) for vi in range( s.numVerts ) ]
		def nearest( f, p ):
			best, bd = None, 1e18
			for si, vi in pts:
				a = self.m.surfaces[si].frames[f][vi]
				d = ( a[0] - p[0] ) ** 2 + ( a[1] - p[1] ) ** 2 + ( a[2] - p[2] ) ** 2
				if d < bd:
					best, bd = ( si, vi ), d
			return best, bd
		# the frame the bind pose is (the MD3's first, or --rest's): the one
		# where the most of its vertexes are exactly (a prop shows elsewhere;
		# standing frames alike are near, but only the bind's is exact)
		cands = sorted( set( [ 0 ] + [ a[0] for a in self.anims.values() ] ) )
		def score( f ):
			ds = [ nearest( f, p )[1] for p in rig.pos ]
			return ( -sum( 1 for d in ds if d < 1e-4 ), sum( ds ) )
		self.rest = min( cands, key = score )
		self.match = []
		for p in rig.pos:
			m, d = nearest( self.rest, p )
			if d >= 1e-4:
				# not there in the bind frame: a prop, at rest in the frame
				# it's biggest in; paired where it's exactly
				for f in range( len( self.m.frameNames ) ):
					m2, d2 = nearest( f, p )
					if d2 < 1e-4:
						m = m2
						break
			self.match.append( m )

	def fit( self, rig, anim ):
		"""( average, worst ) distance of the rig's vertexes from Daikatana's
		frames over the animation; None if the MD3 hasn't it"""
		if anim not in self.anims:
			return None
		first, count = rig.anims[anim]
		mfirst, mcount = self.anims[anim]
		path = self.root.get( anim, {} ).get( "path" )
		total = worst = 0.0
		n = 0
		for k in range( count ):
			got = rig.frame( first + k )
			off = path[min( k, len( path ) - 1 )] if path else ( 0.0, 0.0 )
			f = mfirst + min( k, mcount - 1 )
			for p, ( si, vi ) in zip( got, self.match ):
				a = self.m.surfaces[si].frames[f][vi]
				e = math.sqrt( ( p[0] - a[0] + off[0] ) ** 2 + ( p[1] - a[1] + off[1] ) ** 2
							   + ( p[2] - a[2] + ( off[2] if len( off ) > 2 else 0.0 ) ) ** 2 )
				total, worst, n = total + e, max( worst, e ), n + 1
		return [ round( total / n, 3 ), round( worst, 2 ) ]

# ------------------------------------------------------------------ the record

def load_record():
	return json.load( open( RECORD ) ) if os.path.exists( RECORD ) else {}

def save_record( rec ):
	with open( RECORD, "w" ) as fp:
		json.dump( rec, fp, indent = "\t", sort_keys = True )
		fp.write( "\n" )

def model_info( defName ):
	"""( iqm, md3, root json ) of a model def, game paths, from def/*.def"""
	for fn in os.listdir( os.path.join( ROOT, "def" ) ):
		if not fn.endswith( ".def" ):
			continue
		text = open( os.path.join( ROOT, "def", fn ), encoding = "latin-1" ).read()
		d = re.search( r"entityDef\s+(\S+)", text )
		mesh = re.search( r'"mesh"\s+"(models/rigged/[^"]+\.iqm)"', text )
		if d and mesh and d.group( 1 ) == defName:
			src = re.search( r"made by tools/rig/\w+\.py from (\S+\.md3)", text )
			return mesh.group( 1 ), src.group( 1 ) if src else None, mesh.group( 1 )[:-4] + ".json"
	return None

# the rigs and their sources as loaded, while their files stay as they were
# (the viewer's server asks again a verdict at a time: Daikatana's frames
# loaded and matched to the rig take seconds)
_loaded = {}
_loadLock = threading.Lock()
_sourceLock = threading.Lock()

def _stamp( *paths ):
	return tuple( os.path.getmtime( p ) if os.path.exists( p ) else None for p in paths )

def load_rig( info ):
	"""the Rig of model_info's iqm"""
	path = os.path.join( DKRES, info[0] )
	key, stamp = ( "rig", path ), _stamp( path )
	with _loadLock:
		hit = _loaded.get( key )
		if hit and hit[0] == stamp:
			return hit[1]
	rig = Rig( path )
	with _loadLock:
		_loaded[key] = ( stamp, rig )
	return rig

def load_source( info ):
	"""( Rig, Source ) of model_info's iqm and md3, the Source None without the md3"""
	rig = load_rig( info )
	if not info[1] or not os.path.exists( os.path.join( DKRES, info[1] ) ):
		return rig, None
	paths = [ os.path.join( DKRES, p ) for p in info ]
	key, stamp = ( "source", ) + tuple( paths ), _stamp( *paths )
	with _sourceLock:		# (one loading: a verdict waits for the one under way)
		hit = _loaded.get( key )
		if hit and hit[0] == stamp and hit[1][0] is rig:
			return hit[1]
		src = Source( rig, paths[1], paths[2] )
		_loaded[key] = ( stamp, ( rig, src ) )
	return rig, src

def status( defName, rec = None ):
	"""{ animation: { "state": "valid" | "broken" | "changed" | "new", the record's entry... } }
	for every animation of the model's rig as it is now"""
	rec = load_record() if rec is None else rec
	info = model_info( defName )
	if not info:
		return {}
	rig = load_rig( info )
	known = rec.get( defName, {} ).get( "anims", {} )
	out = {}
	for anim in rig.anims:
		e = dict( known.get( anim, {} ) )
		if not e:
			e["state"] = "new"
		else:
			e["state"] = e["verdict"] if rig.fingerprint( anim ) == e["fingerprint"] else "changed"
		out[anim] = e
	return out

def validate( defName, anim, verdict, note = "", by = None ):
	"""the user's verdict on an animation of the rig as it is now, recorded
	(by: whose, when it's recorded for them)"""
	if verdict not in ( "valid", "broken" ):
		raise ValueError( "verdict: valid or broken" )
	info = model_info( defName )
	if not info:
		raise ValueError( "no rigged model %s" % defName )
	rig, src = load_source( info )
	if anim not in rig.anims:
		raise ValueError( "%s has no animation %s" % ( defName, anim ) )
	fit = src.fit( rig, anim ) if src else None
	rec = load_record()
	m = rec.setdefault( defName, { "iqm": info[0], "anims": {} } )
	m["iqm"] = info[0]
	m["anims"][anim] = { "verdict": verdict, "note": note, "date": datetime.date.today().isoformat(),
						 "fingerprint": rig.fingerprint( anim ), "fit": fit }
	if by:
		m["anims"][anim]["by"] = by
	save_record( rec )
	return m["anims"][anim]

def check():
	"""the validated animations whose rig has changed: [ ( model, animation, entry ) ]"""
	rec = load_record()
	changed = []
	for defName in sorted( rec ):
		info = model_info( defName )
		if not info or not os.path.exists( os.path.join( DKRES, info[0] ) ):
			changed += [ ( defName, a, dict( e, why = "no rig" ) ) for a, e in sorted( rec[defName]["anims"].items() ) ]
			continue
		rig = Rig( os.path.join( DKRES, info[0] ) )
		for anim, e in sorted( rec[defName]["anims"].items() ):
			if anim not in rig.anims:
				changed.append( ( defName, anim, dict( e, why = "gone" ) ) )
			elif rig.fingerprint( anim ) != e["fingerprint"]:
				changed.append( ( defName, anim, dict( e, why = "changed" ) ) )
	return changed

def af_proposals():
	"""the AF files whose regenerated version (out/rig/af, autorig's
	write_af) differs from the one kept in af/, the authority: [ path ]"""
	out = []
	pdir = os.path.join( ROOT, "out", "rig", "af" )
	if os.path.isdir( pdir ):
		for fn in sorted( os.listdir( pdir ) ):
			kept = os.path.join( ROOT, "af", fn )
			if fn.endswith( ".af" ) and os.path.exists( kept ) and open( kept ).read() != open( os.path.join( pdir, fn ) ).read():
				out.append( fn )
	return out

SAME = 0.01		# units: a vertex of a validated animation moving no more than this, it's the same

def gate( defPath, iqmPath, change = () ):
	"""the valid animations of defPath's model the rig at iqmPath changes
	(those named with a prefix in change aside): [ ( animation, why ) ].
	Against the rig installed, which must be the validated one: no vertex
	in any frame more than SAME apart (a hash would flip on IQM's
	quantisation, which shifts every frame a little when one changes)"""
	d = re.search( r"entityDef\s+(\S+)", open( defPath, encoding = "latin-1" ).read() )
	defName = d.group( 1 ) if d else ""
	known = load_record().get( defName, {} ).get( "anims", {} )
	if not known:
		return []
	info = model_info( defName )
	old = Rig( os.path.join( DKRES, info[0] ) ) if info and os.path.exists( os.path.join( DKRES, info[0] ) ) else None
	rig = Rig( iqmPath )
	out = []
	for anim, e in sorted( known.items() ):
		if e["verdict"] != "valid" or any( anim.startswith( p ) for p in change ):
			continue		# (one marked broken is there to be changed)
		if anim not in rig.anims:
			out.append( ( anim, "gone" ) )
		elif not old or anim not in old.anims or old.fingerprint( anim ) != e["fingerprint"]:
			out.append( ( anim, "the rig installed isn't the validated one" ) )
		else:
			( f0, n ), ( g0, m ) = old.anims[anim], rig.anims[anim]
			if n != m or any( math.dist( p, q ) > SAME for k in range( n ) for p, q in zip( old.frame( f0 + k ), rig.frame( g0 + k ) ) ):
				out.append( ( anim, "changed" ) )
	return out

def restamp( defName, change = () ):
	"""the validated animations' fingerprints from the rig installed, once
	the gate has found them the same (those named in change keep theirs:
	they changed, to be validated again)"""
	rec = load_record()
	known = rec.get( defName, {} ).get( "anims", {} )
	info = model_info( defName )
	if not known or not info:
		return
	rig = Rig( os.path.join( DKRES, info[0] ) )
	for anim, e in known.items():
		if anim in rig.anims and not any( anim.startswith( p ) for p in change ):
			e["fingerprint"] = rig.fingerprint( anim )
	save_record( rec )

if __name__ == "__main__":
	if sys.argv[1:2] == [ "--gate" ]:
		args = sys.argv[2:]
		change = ()
		if "--change" in args:
			i = args.index( "--change" )
			change = tuple( a for a in args[i + 1].split( "," ) if a )
			args = args[:i] + args[i + 2:]
		bad = gate( args[0], args[1], change )
		if bad:
			print( "validated, would change: %s" % ", ".join( "%s (%s)" % b for b in bad ) )
		sys.exit( 1 if bad else 0 )
	if sys.argv[1:2] == [ "--restamp" ]:
		restamp( sys.argv[2], tuple( a for a in ( sys.argv[3] if len( sys.argv ) > 3 else "" ).split( "," ) if a ) )
		sys.exit( 0 )
	afs = af_proposals()
	if afs:
		print( "rigcheck: %d AF files kept, the rigs' regenerated ones differ (compare, validate): %s" % ( len( afs ),
			", ".join( "af/%s vs out/rig/af/%s" % ( f, f ) for f in afs ) ) )
	rec = load_record()
	n = sum( len( m["anims"] ) for m in rec.values() )
	changed = check()
	if not changed:
		print( "rigcheck: %d validated animations of %d models, none changed" % ( n, len( rec ) ) )
		sys.exit( 0 )
	print( "rigcheck: %d of %d validated animations changed: revalidate them (./dk viewer)" % ( len( changed ), n ) )
	for defName, anim, e in changed:
		print( "  %-22s %-14s %s (was %s%s)" % ( defName, anim, e["why"], e["verdict"],
			", fit %s" % "/".join( str( x ) for x in e["fit"] ) if e.get( "fit" ) else "" ) )
	sys.exit( 1 )
