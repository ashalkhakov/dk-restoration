#!/usr/bin/env python3
"""
A character's ragdoll (af/<name>.af) refitted to its installed rig: each
body an oriented box about its bone's vertexes, everything else in the file
kept as it is (its joints, "mod", the constraints and their limits: the AF is
the authority, edited by hand: Toshiro's "mod both").

autorig's ragdoll_af boxes the torso and the head along the model's axes by
the vertexes their bones carry, and makes a limb a bone shape between its
joints; on Toshiro (his right elbow's joint out at his shoulder, his neck's
bone carrying his upper chest) the bodies came out small, off and stuck out.
Here each body is the box about its vertexes along their own axes (their
principal ones, the longest first), turned by the body's "angles":
	- the waist (the pelvis, no vertex of its own): the torso between the
	  hips' joint and the waist's, no arm's or leg's vertexes;
	- the chest: the waist's, the chest's and the neck's bones;
	- the head: its own bone's;
	- an upper arm or a thigh its bone's; a forearm with its hand's, a shin
	  with its ankle's.
A vertex counts for the bone it's on; an extra bone's (a robe's, a point's)
and a prop's for none: the body, not its clothes. With --extras an extra
bone's counts for the body bone it hangs from (the ninja's legs are point
bones, Hiro's fingers bones of their own), but those named with --except
(a tunic, a ponytail: names they start with) and a prop's. --along-bones
lays a limb's box along its bone, joint to joint, its vertexes' axes only
across it (a shoulder pad or a hand tilted Hiro's arms' principal axes);
--neck-to-head counts the neck's bone for the head, not the chest (Hiro's
carries half his head); --shoulders-to-arms gives the chest's bone out past
an upper arm's inner side to that upper arm, the chest only between them
(Hiro's pads made his chest's box cover his arms); --feet gives each foot a
body of its own and an ankle joint to its shin, the shin's box its own
bone's (his shins' took his feet); --hands each hand a body of its own and a
wrist joint to its forearm, its box its part's ("box" on its line: the fat
worker's hands turn far from his forearms). --parts <file> counts each vertex for
the part it's nearest, placed by hand (tools/rig/iqm_parts.py's), not its
weights (the ninja's bones carried the wrong parts); --iqm <path> fits to
that rig, not the one installed; --square-waist squares the waist's box to
the body, over the hips', waist's and thighs' own bones' vertexes from 3
below the hips' joint to the sash (the waist's bone's lowest), the chest's
from the sash up (Hirogi's hips' and waist's joints 4 apart made a thin
slab under his sash, his chest's box reaching down into his hips). "mod both" keeps each joint
where it is on its body, so a body needn't lie between its joints.

	python3 tools/rig/af_refit.py model_toshiro
	python3 tools/rig/af_refit.py --extras --except Ponytail --along-bones --neck-to-head --shoulders-to-arms --feet model_hiro

writes out/rig/af/<name>.af, for the user to validate (./dk viewer shows it
beside the kept one) and copy over.
"""
import math
import os
import re
import sys

sys.path.insert( 0, os.path.dirname( os.path.abspath( __file__ ) ) )
import rigcheck as rc
import autorig as ar

ROOT = os.path.normpath( os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), "..", ".." ) )
TEMPLATE = ( "origin", "Body", "Hips", "Lupleg", "Lloleg", "Lankle_r", "Rupleg", "Rloleg", "Rankle_r", "Waist", "Chest",
			 "Loneck", "Head", "Luparm", "Lloarm", "Lhand", "Ruparm", "Rloarm", "Rhand" )
# each body's bones, by the body's name (autorig's ragdoll_af names them so)
BONES = { "chest": ( "Waist", "Chest", "Loneck" ), "head": ( "Head", ) }
for s_ in "LR":
	BONES[s_ + "uparm"] = ( s_ + "uparm", )
	BONES[s_ + "loarm"] = ( s_ + "loarm", s_ + "hand" )
	BONES[s_ + "upleg"] = ( s_ + "upleg", )
	BONES[s_ + "loleg"] = ( s_ + "loleg", s_ + "ankle_r" )

def cross( a, b ):
	return ( a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0] )

def obb( ps, along = None, ends = None ):
	"""the box about the points along their principal axes: its centre, its
	half sizes and its axes (forward, left, up: right-handed, the longest
	first); along a direction given, forward that one (a limb's bone) and
	the others the points' principal ones across it"""
	c = [ sum( p[k] for p in ps ) / len( ps ) for k in range( 3 ) ]
	if along:
		n = math.sqrt( sum( x * x for x in along ) )
		f = [ x / n for x in along ]
		flat = [ [ p[k] - c[k] - sum( ( p[i] - c[i] ) * f[i] for i in range( 3 ) ) * f[k] for k in range( 3 ) ] for p in ps ]
		cov = [ [ sum( q[r] * q[s] for q in flat ) for s in range( 3 ) ] for r in range( 3 ) ]
		vals, vecs = ar.eigen3( cov )
		l = max( ( vecs[k] for k in range( 3 ) if abs( sum( vecs[k][i] * f[i] for i in range( 3 ) ) ) < 0.5 ),
				 key = lambda v: sum( sum( q[i] * v[i] for i in range( 3 ) ) ** 2 for q in flat ) )
		d = sum( l[i] * f[i] for i in range( 3 ) )
		l = [ l[i] - d * f[i] for i in range( 3 ) ]
		n = math.sqrt( sum( x * x for x in l ) )
		l = [ x / n for x in l ]
	else:
		cov = [ [ sum( ( p[r] - c[r] ) * ( p[s] - c[s] ) for p in ps ) for s in range( 3 ) ] for r in range( 3 ) ]
		vals, vecs = ar.eigen3( cov )
		order = sorted( range( 3 ), key = lambda k: -vals[k] )
		f, l = vecs[order[0]], vecs[order[1]]
	u = cross( f, l )
	axes = ( f, l, u )
	lo, hi = [], []
	for i, a in enumerate( axes ):
		# (along a bone at least from its joint to the next: a thigh with
		# few vertexes, the ninja's, all by the knee)
		ts = [ sum( ( p[k] - c[k] ) * a[k] for k in range( 3 ) ) for p in ps + ( list( ends ) if ends and i == 0 else [] ) ]
		lo.append( min( ts ) )
		hi.append( max( ts ) )
	centre = [ c[k] + sum( 0.5 * ( lo[i] + hi[i] ) * axes[i][k] for i in range( 3 ) ) for k in range( 3 ) ]
	half = [ max( 1.0, 0.5 * ( hi[i] - lo[i] ) ) for i in range( 3 ) ]
	return centre, half, axes

def angles_of( axes ):
	"""pitch, yaw, roll whose AnglesToAxis (Quake's: forward, left, up) are
	the axes"""
	f, l, u = axes
	pitch = math.degrees( math.asin( max( -1.0, min( 1.0, -f[2] ) ) ) )
	yaw = math.degrees( math.atan2( f[1], f[0] ) )
	roll = math.degrees( math.atan2( l[2], u[2] ) )
	return pitch, yaw, roll

def axes_of( angles ):
	"""Quake's AnglesToAxis: forward, left, up"""
	p, y, r = [ math.radians( a ) for a in angles ]
	sp, cp, sy, cy, sr, cr = math.sin( p ), math.cos( p ), math.sin( y ), math.cos( y ), math.sin( r ), math.cos( r )
	f = ( cp * cy, cp * sy, -sp )
	right = ( -sr * sp * cy + cr * sy, -sr * sp * sy - cr * cy, -sr * cp )
	u = ( cr * sp * cy + sr * sy, cr * sp * sy - sr * cy, cr * cp )
	return f, tuple( -x for x in right ), u

def box_angles( bname, axes, h ):
	"""a box's angles, and its half sizes in their order: a box the same with
	its axes cycled if need be (one whose first is straight up, its pitch
	90, has no angles that give it back)"""
	for turn in range( 3 ):
		ang = angles_of( axes )
		back = axes_of( ang )
		if max( abs( back[i][k] - axes[i][k] ) for i in range( 3 ) for k in range( 3 ) ) < 1e-6:
			return ang, h
		axes, h = [ axes[1], axes[2], axes[0] ], [ h[1], h[2], h[0] ]
	sys.exit( "%s: no angles for its box" % bname )

def add_hands( af, box, P, report ):
	"""a body for each hand (box( "Lhand" ): its points, the box along them),
	on joint Xhand, and a wrist joint to its forearm: a universal joint at
	the wrist, its cone about the forearm (the fat worker's hands turn far
	from his forearms)"""
	for s_ in "LR":
		hand, fore = s_ + "hand", s_ + "loarm"
		got = box( hand )
		if not got or ( 'body "%s"' % hand ) in af:
			continue
		ps, ( c, h, axes ) = got
		ang, h = box_angles( hand, axes, h )
		mod = re.search( r'body "%s" \{.*?mod (\w+)' % fore, af, re.S ).group( 1 )
		a, b = P[fore], P[hand]
		d = [ b[k] - a[k] for k in range( 3 ) ]
		n = math.sqrt( sum( x * x for x in d ) )
		d = [ x / n for x in d ]
		body = ( '\tbody "%s" {\n\t\tjoint "%s"\n\t\tmod %s\n'
				 '\t\tmodel box( ( %.2f, %.2f, %.2f ), ( %.2f, %.2f, %.2f ) )\n\t\tangles ( %.1f, %.1f, %.1f )\n'
				 '\t\torigin ( %.2f, %.2f, %.2f )\n\t\tdensity 0.2\n\t\tfriction 0.01, 0.01, 0.8\n\t\tcontents corpse\n'
				 '\t\tclipMask solid, corpse\n\t\tselfCollision 1\n\t}\n\n'
				 % ( hand, hand, mod, -h[0], -h[1], -h[2], h[0], h[1], h[2], *ang, *c ) )
		joint = ( '\tuniversalJoint "%swrist" {\n\t\tbody1 "%s"\n\t\tbody2 "%s"\n\t\tanchor joint( "%s" )\n'
				  '\t\tshafts ( %.2f, %.2f, %.2f ), ( %.2f, %.2f, %.2f )\n\t\tfriction 0.20\n'
				  '\t\tconeLimit ( %.2f, %.2f, %.2f ), 45\n\t}\n'
				  % ( s_, hand, fore, hand, *d, *[ -x for x in d ], *d ) )
		m = re.search( r'\tbody "%s" \{.*?\n\t\}\n\n?' % fore, af, re.S )
		af = af[:m.end()] + body + af[m.end():]
		last = af.rstrip().rfind( "\n}" )
		af = af[:last + 1] + joint + af[last + 1:]
		report.append( "  %-7s %3d vertexes: %.1f x %.1f x %.1f, a body of its own, a wrist joint to %s"
					   % ( hand, len( ps ), 2 * h[0], 2 * h[1], 2 * h[2], fore ) )
	return af

def add_feet( af, pts, P, report ):
	"""a body for each foot (its ankle's bone's vertexes), on joint
	X ankle_r, and an ankle joint to its shin: a universal joint at the
	ankle, its cone about the shin (Hiro's shins' boxes took his feet)"""
	for s_ in "LR":
		foot, shin = s_ + "foot", s_ + "loleg"
		ps = pts( ( s_ + "ankle_r", ) )
		if len( ps ) < 4 or ( 'body "%s"' % foot ) in af:
			continue
		c, h, axes = obb( ps )
		ang = angles_of( axes )
		mod = re.search( r'body "%s" \{.*?mod (\w+)' % shin, af, re.S ).group( 1 )
		a, b = P[shin], P[s_ + "ankle_r"]
		d = [ b[k] - a[k] for k in range( 3 ) ]
		n = math.sqrt( sum( x * x for x in d ) )
		d = [ x / n for x in d ]
		body = ( '\tbody "%s" {\n\t\tjoint "%s"\n\t\tmod %s\n'
				 '\t\tmodel box( ( %.2f, %.2f, %.2f ), ( %.2f, %.2f, %.2f ) )\n\t\tangles ( %.1f, %.1f, %.1f )\n'
				 '\t\torigin ( %.2f, %.2f, %.2f )\n\t\tdensity 0.2\n\t\tfriction 0.01, 0.01, 0.8\n\t\tcontents corpse\n'
				 '\t\tclipMask solid, corpse\n\t\tselfCollision 1\n\t}\n\n'
				 % ( foot, s_ + "ankle_r", mod, -h[0], -h[1], -h[2], h[0], h[1], h[2], *ang, *c ) )
		joint = ( '\tuniversalJoint "%sankle" {\n\t\tbody1 "%s"\n\t\tbody2 "%s"\n\t\tanchor joint( "%s" )\n'
				  '\t\tshafts ( %.2f, %.2f, %.2f ), ( %.2f, %.2f, %.2f )\n\t\tfriction 0.20\n'
				  '\t\tconeLimit ( %.2f, %.2f, %.2f ), 45\n\t}\n'
				  % ( s_, foot, shin, s_ + "ankle_r", *d, *[ -x for x in d ], *d ) )
		# the body after its shin's, the joint after the last constraint
		m = re.search( r'\tbody "%s" \{.*?\n\t\}\n\n?' % shin, af, re.S )
		af = af[:m.end()] + body + af[m.end():]
		last = af.rstrip().rfind( "\n}" )
		af = af[:last + 1] + joint + af[last + 1:]
		report.append( "  %-7s %3d vertexes: %.1f x %.1f x %.1f, a body of its own, an ankle joint to %s"
					   % ( foot, len( ps ), 2 * h[0], 2 * h[1], 2 * h[2], shin ) )
	return af

def main( defName, extras = False, excepted = (), alongBones = False, neckToHead = False, shouldersToArms = False, feet = False,
		  partsPath = None, iqmPath = None, squareWaist = False, hands = False ):
	info = rc.model_info( defName )
	if not info:
		sys.exit( "%s: no rigged model def" % defName )
	defDir = os.path.join( ROOT, "def" )
	# (the rigged model's def, the one naming its ragdoll: the skinny
	# worker's md3 def has his name too)
	defFile = [ f for f in sorted( os.listdir( defDir ) ) if f.endswith( ".def" )
				and re.search( r"entityDef\s+%s\b[^}]*\"ragdoll\"" % re.escape( defName ), open( os.path.join( defDir, f ), encoding = "latin-1" ).read() ) ][0]
	afName = re.search( r'"ragdoll"\s+"([^"]+)"', open( os.path.join( defDir, defFile ), encoding = "latin-1" ).read() ).group( 1 )
	af = open( os.path.join( ROOT, "af", afName + ".af" ) ).read()

	rig = rc.Rig( iqmPath ) if iqmPath else rc.load_rig( info )
	q = rig.q
	names = [ j.name for j in q.joints ]
	bind = []
	for j, jt in enumerate( q.joints ):
		local = ( rc.mat( jt.rotate, jt.scale ), jt.translate )
		bind.append( local if jt.parent < 0 else rc.compose( bind[jt.parent], local ) )
	P = { n: bind[i][1] for i, n in enumerate( names ) }
	def counts( j ):
		while j >= 0:
			n = names[j]
			if n.endswith( "_skin" ) and n[:-5] in TEMPLATE:
				return n[:-5]		# (tools/rig/iqm_parts.py's twin: the mesh its bone carried)
			if n in TEMPLATE:
				return n
			if not extras or n.startswith( "Auto_" ) or any( n.startswith( e ) for e in excepted ):
				return None
			j = q.joints[j].parent
		return None
	owner = [ counts( rig.bi[v][max( range( 4 ), key = lambda c: rig.bw[v][c] )] ) for v in range( len( rig.pos ) ) ]
	parts, partsOpts = {}, { "box": {} }
	if partsPath:
		# each vertex the part it's nearest, placed by hand (tools/rig/iqm_parts.py's:
		# the ninja's bones carried the wrong parts of him), a prop's none
		import iqm_parts
		parts, _, reach, opts = iqm_parts.read_parts( partsPath )
		partsOpts = opts
		def prop( j ):
			while j >= 0:
				if names[j].startswith( "Auto_" ):
					return True
				j = q.joints[j].parent
			return False
		# (parts for only some of him, Usagi's limbs: the rest as their skin is;
		# a vertex a part of its own limb's only)
		jparent = [ j.parent for j in q.joints ]
		top = lambda v: rig.bi[v][max( range( 4 ), key = lambda c: rig.bw[v][c] )]
		root = lambda j: iqm_parts.from_root( j, names, jparent, opts["from"] )
		limb = { b: root( names.index( b ) ) for b in parts if b in names }
		def part_of( v ):
			if not opts["from"]:
				return iqm_parts.nearest( rig.pos[v], parts, reach )
			r = root( top( v ) )
			return iqm_parts.nearest( rig.pos[v], parts, reach, [ b for b in parts if r and limb.get( b ) == r ] ) if r else None
		# (out of every part's reach: its skin's bone, unless that bone has a
		# part, out of whose reach it is: Inshiro's lower tunic, skinned to his
		# shins, not theirs)
		owner = [ None if prop( top( v ) ) else ( part_of( v ) or ( owner[v] if owner[v] not in parts else None ) )
				  for v in range( len( rig.pos ) ) ]
	pts = lambda ns: [ rig.pos[v] for v in range( len( rig.pos ) ) if owner[v] in ns ]
	limbs = [ s_ + n for s_ in "LR" for n in ( "uparm", "loarm", "hand", "upleg", "loleg", "ankle_r" ) ]
	trunk = [ rig.pos[v] for v in range( len( rig.pos ) ) if owner[v] and owner[v] not in limbs ]

	# across the shoulders: a point's place from the right shoulder's joint
	# to the left's, 0 at the right and 1 at the left
	sr, sl = P["Ruparm"], P["Luparm"]
	across = [ sl[k] - sr[k] for k in range( 3 ) ]
	A2 = sum( x * x for x in across ) or 1e-9
	def side( p ):
		return sum( ( p[k] - sr[k] ) * across[k] for k in range( 3 ) ) / A2
	# --square-waist: the waist from the crotch to the sash's bottom (its own
	# bone's lowest vertex), the chest from there up
	own = lambda v: names[rig.bi[v][max( range( 4 ), key = lambda c: rig.bw[v][c] )]].replace( "_skin", "" )
	sash = min( ( rig.pos[v][2] for v in range( len( rig.pos ) ) if own( v ) == "Waist" ), default = 0.0 )
	def body_points( bname ):
		if squareWaist and bname == "chest":
			return [ p for p in body_points_( bname ) if p[2] >= sash ]
		return body_points_( bname )
	def body_points_( bname ):
		if bname in partsOpts["box"]:
			# (a box from a point of its own, Usagi's thighs from his belt: what
			# lies along it, belt to knee, whatever bone carries it; no other
			# limb's, his hands resting on them)
			# ("from" bones no part of the file is under, Osaka's arms, are
			# never a box's: his hands hang by his robe; a body that isn't a
			# joint, his head, is of any other)
			a_, b_ = partsOpts["box"][bname], parts[bname][1]
			mine = root( names.index( bname ) ) if bname in names else None		# (the head's: not a joint's name)
			partRoots = set( root( names.index( b ) ) for b in parts if b in names )
			kept = lambda r: r not in set( partsOpts.get( "from", [] ) ) - partRoots and ( mine is None or r in ( None, mine ) )
			# its vertexes and points across its triangles (Osaka's robe: a few
			# big flat ones, their vertexes at its hips and hem)
			ok = [ not prop( top( v ) ) and kept( root( top( v ) ) ) for v in range( len( rig.pos ) ) ]
			cand = [ rig.pos[v] for v in range( len( rig.pos ) ) if ok[v] ]
			S = 6
			for t in q.triangles:
				if all( ok[v] for v in t ):
					p0, p1, p2 = ( rig.pos[v] for v in t )
					for i in range( S + 1 ):
						for j in range( S + 1 - i ):
							u, w = i / S, j / S
							cand.append( tuple( p0[k] + ( p1[k] - p0[k] ) * u + ( p2[k] - p0[k] ) * w for k in range( 3 ) ) )
			L2 = sum( ( b_[k] - a_[k] ) ** 2 for k in range( 3 ) )
			return [ p for p in cand if iqm_parts.seg_dist( p, a_, b_ ) <= reach.get( bname, 5.0 )
					 and -0.1 <= sum( ( p[k] - a_[k] ) * ( b_[k] - a_[k] ) for k in range( 3 ) ) / L2 <= 1.05 ]
		if bname == "waist":
			if partsPath and "Hips" in parts:
				# (the parts placed by hand: the trunk from the crotch to the
				# belt, the tops of the thighs with it; the arms hanging
				# beside it not)
				z0 = parts["Hips"][0][2]
				z1 = max( p[2] for p in pts( ( "Waist", ) ) )
				arms = [ s_ + n for s_ in "LR" for n in ( "uparm", "loarm", "hand" ) ]
				return [ rig.pos[v] for v in range( len( rig.pos ) ) if owner[v] and owner[v] not in arms and z0 <= rig.pos[v][2] <= z1 ]
			if squareWaist:
				# (the pelvis' and thighs' own bones', no extra's: his
				# trousers' flare)
				return [ rig.pos[v] for v in range( len( rig.pos ) ) if ( owner[v] if partsPath else own( v ) ) in ( "Hips", "Waist", "Lupleg", "Rupleg" )
						 and P["Hips"][2] - 3.0 <= rig.pos[v][2] <= sash ]
			z0, z1 = sorted( ( P["Hips"][2], P["Waist"][2] ) )
			return [ p for p in trunk if z0 <= p[2] <= z1 ]
		if partsPath and bname == "chest" and "Chest" in parts:
			return pts( ( "Chest", ) )		# (the waist's part the pelvis': the chest its own, along the spine)
		if neckToHead and bname in ( "chest", "head" ):
			# (the neck's bone carrying half the head: Hiro's)
			ps = pts( ( "Waist", "Chest" ) if bname == "chest" else ( "Loneck", "Head" ) )
		else:
			ps = pts( BONES.get( bname, ( bname, ) ) if not ( feet and bname[1:] == "loleg" ) else ( bname, ) )
		if shouldersToArms:
			# the chest's bone out past an upper arm's inner side is that
			# shoulder (Hiro's pads): the upper arm's, the chest only between
			# the two (his shoulders' joints are in the middle of his arms)
			chest = pts( ( "Chest", ) )
			inR = max( side( p ) for p in pts( ( "Ruparm", ) ) )
			inL = min( side( p ) for p in pts( ( "Luparm", ) ) )
			if bname == "chest":
				ps = [ p for p in ps if inR <= side( p ) <= inL ]
			elif bname == "Luparm":
				ps = ps + [ p for p in chest if side( p ) > inL ]
			elif bname == "Ruparm":
				ps = ps + [ p for p in chest if side( p ) < inR ]
		return ps
	# a limb's bone: from its joint to the next one down the limb
	NEXT = { "uparm": "loarm", "loarm": "hand", "upleg": "loleg", "loleg": "ankle_r" }
	def bone_ends( bname ):
		if bname in partsOpts["box"]:
			return ( partsOpts["box"][bname], parts[bname][1] )		# (a box of its own: Usagi's thighs, the skinny worker's head)
		if partsPath and alongBones and bname == "chest" and "Chest" in parts:
			# (the torso along the spine, from the waist's top to the neck:
			# no gap over the belly between the two)
			a, b = parts["Chest"]
			d = [ b[k] - a[k] for k in range( 3 ) ]
			L2 = sum( x * x for x in d ) or 1e-9
			t = min( 0.0, max( sum( ( p[k] - a[k] ) * d[k] for k in range( 3 ) ) / L2 for p in pts( ( "Hips", "Waist" ) ) ) )
			return ( [ a[k] + t * d[k] for k in range( 3 ) ], b )
		if not alongBones or bname[1:] not in NEXT:
			return None
		if partsPath and bname in parts:
			if bname in partsOpts["box"]:
				return ( partsOpts["box"][bname], parts[bname][1] )		# (Usagi's thighs: from his belt, his hips' joints below it)
			return parts[bname]		# (placed by hand: the ninja's elbows' joints are at his shoulders)
		return ( P[bname], P[bname[0] + NEXT[bname[1:]]] )
	def bone_dir( bname ):
		e = bone_ends( bname )
		return [ e[1][k] - e[0][k] for k in range( 3 ) ] if e else None

	report = []
	out, pos = [], 0
	for m in re.finditer( r'\tbody "(\w+)" \{.*?\n\t\}', af, re.S ):
		block, bname = m.group( 0 ), m.group( 1 )
		out.append( af[pos:m.start()] )
		ps = body_points( bname )
		if len( ps ) >= 4:
			if ( partsPath or squareWaist ) and bname == "waist":
				# square to the body (its few points turned their own axes
				# sideways: the ninja's)
				axes = ( ( 1.0, 0.0, 0.0 ), ( 0.0, 1.0, 0.0 ), ( 0.0, 0.0, 1.0 ) )
				lo = [ min( p[k] for p in ps ) for k in range( 3 ) ]
				hi = [ max( p[k] for p in ps ) for k in range( 3 ) ]
				c, h = [ ( lo[k] + hi[k] ) / 2 for k in range( 3 ) ], [ ( hi[k] - lo[k] ) / 2 for k in range( 3 ) ]
			else:
				c, h, axes = obb( ps, bone_dir( bname ), bone_ends( bname ) )
			ang, h = box_angles( bname, axes, h )
			old = re.search( r"\t\tmodel [^\n]*", block ).group( 0 )
			block = block.replace( old, "\t\tmodel box( ( %.2f, %.2f, %.2f ), ( %.2f, %.2f, %.2f ) )" % ( -h[0], -h[1], -h[2], h[0], h[1], h[2] ) )
			block = re.sub( r"\t\torigin \([^)]*\)", "\t\torigin ( %.2f, %.2f, %.2f )" % tuple( c ), block, count = 1 )
			block = re.sub( r"\t\tangles \([^)]*\)\n", "", block )
			block = block.replace( "\t\torigin (", "\t\tangles ( %.1f, %.1f, %.1f )\n\t\torigin (" % ang, 1 )
			report.append( "  %-7s %3d vertexes: %.1f x %.1f x %.1f, angles ( %.0f %.0f %.0f )   (was %s)"
						   % ( bname, len( ps ), 2 * h[0], 2 * h[1], 2 * h[2], *ang, old.strip() ) )
		else:
			report.append( "  %-7s %d vertexes: kept" % ( bname, len( ps ) ) )
		out.append( block )
		pos = m.end()
	out.append( af[pos:] )
	if feet:
		out = [ add_feet( "".join( out ), pts, P, report ) ]
	if hands:
		def hand_box( hname ):
			if hname not in partsOpts["box"]:
				return None
			ps = body_points( hname )
			return ( ps, obb( ps, bone_dir( hname ), bone_ends( hname ) ) ) if len( ps ) >= 4 else None
		out = [ add_hands( "".join( out ), hand_box, P, report ) ]
	dst = os.path.join( ROOT, "out", "rig", "af", afName + ".af" )
	os.makedirs( os.path.dirname( dst ), exist_ok = True )
	with open( dst, "w" ) as fp:
		fp.write( "".join( out ) )
	print( "%s (%s):" % ( afName, info[0] ) )
	print( "\n".join( report ) )
	print( "  wrote %s" % os.path.relpath( dst, ROOT ) )

if __name__ == "__main__":
	args = sys.argv[1:]
	extras = "--extras" in args
	if extras:
		args.remove( "--extras" )
	excepted = []
	while "--except" in args:
		i = args.index( "--except" )
		excepted.append( args[i + 1] )
		args = args[:i] + args[i + 2:]
	alongBones = "--along-bones" in args
	if alongBones:
		args.remove( "--along-bones" )
	neckToHead = "--neck-to-head" in args
	if neckToHead:
		args.remove( "--neck-to-head" )
	shouldersToArms = "--shoulders-to-arms" in args
	if shouldersToArms:
		args.remove( "--shoulders-to-arms" )
	feet = "--feet" in args
	if feet:
		args.remove( "--feet" )
	squareWaist = "--square-waist" in args
	if squareWaist:
		args.remove( "--square-waist" )
	hands = "--hands" in args
	if hands:
		args.remove( "--hands" )
	opt = {}
	for o in ( "--parts", "--iqm" ):
		if o in args:
			i = args.index( o )
			opt[o] = args[i + 1]
			args = args[:i] + args[i + 2:]
	if len( args ) != 1:
		print( __doc__ )
		sys.exit( 1 )
	main( args[0], extras, tuple( excepted ), alongBones, neckToHead, shouldersToArms, feet, opt.get( "--parts" ), opt.get( "--iqm" ), squareWaist, hands )
