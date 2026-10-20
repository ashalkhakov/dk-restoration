"""Reads the frames of an MD3 (the converted Daikatana models)."""
import re
import struct

MD3_XYZ_SCALE = 1.0 / 64

class Surface:
	pass

class MD3:
	def __init__( self, path ):
		d = open( path, "rb" ).read()
		self.path = path
		nf, nt, ns, nsk, of, ot, osurf, oend = struct.unpack_from( "<8i", d, 76 )
		self.numFrames = nf
		self.frameNames = [ d[of + i * 56 + 40:of + i * 56 + 56].split( b"\0" )[0].decode() for i in range( nf ) ]
		self.surfaces = []
		o = osurf
		for s in range( ns ):
			surf = Surface()
			surf.name = d[o + 4:o + 68].split( b"\0" )[0].decode()
			sflags, snf, nsh, nv, ntri, otri, osh, ost, oxyz, oend2 = struct.unpack_from( "<10i", d, o + 68 )
			surf.shader = d[o + osh:o + osh + 64].split( b"\0" )[0].decode() if nsh else ""
			surf.triangles = [ struct.unpack_from( "<3i", d, o + otri + 12 * t ) for t in range( ntri ) ]
			surf.st = [ struct.unpack_from( "<2f", d, o + ost + 8 * v ) for v in range( nv ) ]
			surf.frames = []
			for f in range( nf ):
				base = o + oxyz + f * nv * 8
				verts = []
				for v in range( nv ):
					x, y, z, n = struct.unpack_from( "<3hH", d, base + v * 8 )
					verts.append( ( x * MD3_XYZ_SCALE, y * MD3_XYZ_SCALE, z * MD3_XYZ_SCALE ) )
				surf.frames.append( verts )
			surf.numVerts = nv
			self.surfaces.append( surf )
			o += oend2

	def animations( self ):
		"""[ ( name, first frame, count ) ] from the frame names ("run01"...)."""
		groups = []
		for i, n in enumerate( self.frameNames ):
			p = re.sub( r"\d+$", "", n )
			if groups and groups[-1][0] == p:
				groups[-1][2] += 1
			else:
				groups.append( [ p, i, 1 ] )
		return [ tuple( g ) for g in groups ]
