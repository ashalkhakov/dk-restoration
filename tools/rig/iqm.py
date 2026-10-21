"""Reads an IQM (version 2, as tools/rig/autorig.py writes them): the meshes,
the vertex arrays, the triangles, the joints and their rest pose, the
animations and the frames' poses."""
import struct

# vertex array types
IQM_POSITION, IQM_TEXCOORD, IQM_NORMAL, IQM_TANGENT, IQM_BLENDINDEXES, IQM_BLENDWEIGHTS = 0, 1, 2, 3, 4, 5
FORMATS = { 0: "b", 1: "B", 2: "h", 3: "H", 4: "i", 5: "I", 7: "f", 8: "d" }

class Mesh:
	pass

class Joint:
	pass

class IQM:
	def __init__( self, path ):
		d = open( path, "rb" ).read()
		self.path = path
		if d[:16] != b"INTERQUAKEMODEL\0":
			raise ValueError( "%s: not an IQM" % path )
		h = struct.unpack_from( "<27I", d, 16 )
		( version, filesize, flags, numText, ofsText, numMeshes, ofsMeshes, numVA, numVerts, ofsVA,
		  numTris, ofsTris, ofsAdj, numJoints, ofsJoints, numPoses, ofsPoses, numAnims, ofsAnims,
		  numFrames, numChannels, ofsFrames, ofsBounds, numComment, ofsComment, numExt, ofsExt ) = h
		if version != 2:
			raise ValueError( "%s: IQM version %d" % ( path, version ) )
		text = d[ofsText:ofsText + numText]
		def name( o ):
			return text[o:text.index( b"\0", o )].decode()

		self.numVerts = numVerts
		self.arrays = {}		# type -> [ tuple a vertex ]
		for k in range( numVA ):
			vtype, vflags, fmt, size, ofs = struct.unpack_from( "<5I", d, ofsVA + 20 * k )
			f = "<%d%s" % ( size, FORMATS[fmt] )
			step = struct.calcsize( f )
			self.arrays[vtype] = [ struct.unpack_from( f, d, ofs + step * v ) for v in range( numVerts ) ]
		self.triangles = [ struct.unpack_from( "<3I", d, ofsTris + 12 * t ) for t in range( numTris ) ]

		self.meshes = []
		for k in range( numMeshes ):
			n, mat, fv, nv, ft, nt = struct.unpack_from( "<6I", d, ofsMeshes + 24 * k )
			m = Mesh()
			m.name, m.material = name( n ), name( mat )
			m.firstVert, m.numVerts, m.firstTri, m.numTris = fv, nv, ft, nt
			self.meshes.append( m )

		self.joints = []
		for k in range( numJoints ):
			v = struct.unpack_from( "<Ii3f4f3f", d, ofsJoints + 48 * k )
			j = Joint()
			j.name, j.parent = name( v[0] ), v[1]
			j.translate, j.rotate, j.scale = tuple( v[2:5] ), tuple( v[5:9] ), tuple( v[9:12] )
			self.joints.append( j )

		self.anims = []		# [ ( name, first frame, count, fps, flags ) ]
		for k in range( numAnims ):
			n, first, count, fps, aflags = struct.unpack_from( "<IIIfI", d, ofsAnims + 20 * k )
			self.anims.append( ( name( n ), first, count, fps, aflags ) )

		# the poses: [frame][pose] = ( translate, quaternion, scale ), local
		poses = []
		for k in range( numPoses ):
			v = struct.unpack_from( "<iI10f10f", d, ofsPoses + 88 * k )
			poses.append( ( v[0], v[1], v[2:12], v[12:22] ) )
		self.frames = []
		o = ofsFrames
		for f in range( numFrames ):
			row = []
			for parent, mask, offs, scales in poses:
				ch = []
				for c in range( 10 ):
					x = offs[c]
					if mask & ( 1 << c ):
						x += struct.unpack_from( "<H", d, o )[0] * scales[c]
						o += 2
					ch.append( x )
				row.append( ( tuple( ch[0:3] ), tuple( ch[3:7] ), tuple( ch[7:10] ) ) )
			self.frames.append( row )
