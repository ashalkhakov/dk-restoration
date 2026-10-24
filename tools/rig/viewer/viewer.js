// The rig viewer (tools/rig/viewer, ./dk viewer): an IQM autorig made, its
// animations played, and over it what it was made from: Daikatana's MD3
// frame by frame, how far each vertex is off it, the skeleton and the
// ragdoll's bodies (af/). Z is up, as in the game; the grid is the model's
// floor (z 0) and the axes its origin.
"use strict";

// ------------------------------------------------------------------ math
// 4x4 matrices column-major (as GL), points [x, y, z]

function m4() { const m = new Float32Array( 16 ); m[0] = m[5] = m[10] = m[15] = 1; return m; }
function m4mul( a, b ) {
	const o = new Float32Array( 16 );
	for ( let c = 0; c < 4; c++ ) {
		for ( let r = 0; r < 4; r++ ) {
			o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3];
		}
	}
	return o;
}
// translate * scale * rotate (quaternion x y z w): the scale along the
// parent's axes, as the engine does it (bg_model.c, tr_model_iqm.c)
function m4trs( t, q, s ) {
	let [ x, y, z, w ] = q;
	const l = Math.hypot( x, y, z, w ) || 1;
	x /= l; y /= l; z /= l; w /= l;
	const m = new Float32Array( 16 );
	m[0] = ( 1 - 2 * ( y * y + z * z ) ) * s[0]; m[1] = 2 * ( x * y + z * w ) * s[1]; m[2] = 2 * ( x * z - y * w ) * s[2];
	m[4] = 2 * ( x * y - z * w ) * s[0]; m[5] = ( 1 - 2 * ( x * x + z * z ) ) * s[1]; m[6] = 2 * ( y * z + x * w ) * s[2];
	m[8] = 2 * ( x * z + y * w ) * s[0]; m[9] = 2 * ( y * z - x * w ) * s[1]; m[10] = ( 1 - 2 * ( x * x + y * y ) ) * s[2];
	m[12] = t[0]; m[13] = t[1]; m[14] = t[2]; m[15] = 1;
	return m;
}
function m4inv( m ) {
	const inv = new Float32Array( 16 );
	inv[0] = m[5] * m[10] * m[15] - m[5] * m[11] * m[14] - m[9] * m[6] * m[15] + m[9] * m[7] * m[14] + m[13] * m[6] * m[11] - m[13] * m[7] * m[10];
	inv[4] = -m[4] * m[10] * m[15] + m[4] * m[11] * m[14] + m[8] * m[6] * m[15] - m[8] * m[7] * m[14] - m[12] * m[6] * m[11] + m[12] * m[7] * m[10];
	inv[8] = m[4] * m[9] * m[15] - m[4] * m[11] * m[13] - m[8] * m[5] * m[15] + m[8] * m[7] * m[13] + m[12] * m[5] * m[11] - m[12] * m[7] * m[9];
	inv[12] = -m[4] * m[9] * m[14] + m[4] * m[10] * m[13] + m[8] * m[5] * m[14] - m[8] * m[6] * m[13] - m[12] * m[5] * m[10] + m[12] * m[6] * m[9];
	inv[1] = -m[1] * m[10] * m[15] + m[1] * m[11] * m[14] + m[9] * m[2] * m[15] - m[9] * m[3] * m[14] - m[13] * m[2] * m[11] + m[13] * m[3] * m[10];
	inv[5] = m[0] * m[10] * m[15] - m[0] * m[11] * m[14] - m[8] * m[2] * m[15] + m[8] * m[3] * m[14] + m[12] * m[2] * m[11] - m[12] * m[3] * m[10];
	inv[9] = -m[0] * m[9] * m[15] + m[0] * m[11] * m[13] + m[8] * m[1] * m[15] - m[8] * m[3] * m[13] - m[12] * m[1] * m[11] + m[12] * m[3] * m[9];
	inv[13] = m[0] * m[9] * m[14] - m[0] * m[10] * m[13] - m[8] * m[1] * m[14] + m[8] * m[2] * m[13] + m[12] * m[1] * m[10] - m[12] * m[2] * m[9];
	inv[2] = m[1] * m[6] * m[15] - m[1] * m[7] * m[14] - m[5] * m[2] * m[15] + m[5] * m[3] * m[14] + m[13] * m[2] * m[7] - m[13] * m[3] * m[6];
	inv[6] = -m[0] * m[6] * m[15] + m[0] * m[7] * m[14] + m[4] * m[2] * m[15] - m[4] * m[3] * m[14] - m[12] * m[2] * m[7] + m[12] * m[3] * m[6];
	inv[10] = m[0] * m[5] * m[15] - m[0] * m[7] * m[13] - m[4] * m[1] * m[15] + m[4] * m[3] * m[13] + m[12] * m[1] * m[7] - m[12] * m[3] * m[5];
	inv[14] = -m[0] * m[5] * m[14] + m[0] * m[6] * m[13] + m[4] * m[1] * m[14] - m[4] * m[2] * m[13] - m[12] * m[1] * m[6] + m[12] * m[2] * m[5];
	inv[3] = -m[1] * m[6] * m[11] + m[1] * m[7] * m[10] + m[5] * m[2] * m[11] - m[5] * m[3] * m[10] - m[9] * m[2] * m[7] + m[9] * m[3] * m[6];
	inv[7] = m[0] * m[6] * m[11] - m[0] * m[7] * m[10] - m[4] * m[2] * m[11] + m[4] * m[3] * m[10] + m[8] * m[2] * m[7] - m[8] * m[3] * m[6];
	inv[11] = -m[0] * m[5] * m[11] + m[0] * m[7] * m[9] + m[4] * m[1] * m[11] - m[4] * m[3] * m[9] - m[8] * m[1] * m[7] + m[8] * m[3] * m[5];
	inv[15] = m[0] * m[5] * m[10] - m[0] * m[6] * m[9] - m[4] * m[1] * m[10] + m[4] * m[2] * m[9] + m[8] * m[1] * m[6] - m[8] * m[2] * m[5];
	let det = m[0] * inv[0] + m[1] * inv[4] + m[2] * inv[8] + m[3] * inv[12];
	det = det ? 1 / det : 0;
	for ( let i = 0; i < 16; i++ ) inv[i] *= det;
	return inv;
}
function xf( m, p ) {
	return [ m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12], m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13],
			 m[2] * p[0] + m[6] * p[1] + m[10] * p[2] + m[14] ];
}
const sub = ( a, b ) => [ a[0] - b[0], a[1] - b[1], a[2] - b[2] ];
const add = ( a, b ) => [ a[0] + b[0], a[1] + b[1], a[2] + b[2] ];
const scl = ( a, s ) => [ a[0] * s, a[1] * s, a[2] * s ];
const dot = ( a, b ) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = ( a, b ) => [ a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0] ];
const len = a => Math.hypot( a[0], a[1], a[2] );
const norm = a => { const l = len( a ) || 1; return [ a[0] / l, a[1] / l, a[2] / l ]; };

function perspective( fovy, aspect, near, far ) {
	const f = 1 / Math.tan( fovy / 2 ), m = new Float32Array( 16 );
	m[0] = f / aspect; m[5] = f; m[10] = ( far + near ) / ( near - far ); m[11] = -1; m[14] = 2 * far * near / ( near - far );
	return m;
}
function lookAt( eye, at, up ) {
	const z = norm( sub( eye, at ) ), x = norm( cross( up, z ) ), y = cross( z, x ), m = m4();
	m[0] = x[0]; m[4] = x[1]; m[8] = x[2];
	m[1] = y[0]; m[5] = y[1]; m[9] = y[2];
	m[2] = z[0]; m[6] = z[1]; m[10] = z[2];
	m[12] = -dot( x, eye ); m[13] = -dot( y, eye ); m[14] = -dot( z, eye );
	return m;
}

// ------------------------------------------------------------------ files

function cstr( u8, o, n ) {
	let s = "";
	for ( let i = 0; i < n && u8[o + i]; i++ ) s += String.fromCharCode( u8[o + i] );
	return s;
}

// IQM 2 (tools/rig/iqm.py reads the same)
function parseIQM( buf ) {
	const dv = new DataView( buf ), u8 = new Uint8Array( buf );
	if ( cstr( u8, 0, 16 ) !== "INTERQUAKEMODEL" ) throw new Error( "not an IQM" );
	const h = [];
	for ( let i = 0; i < 27; i++ ) h.push( dv.getUint32( 16 + 4 * i, true ) );
	const [ version, , , numText, ofsText, numMeshes, ofsMeshes, numVA, numVerts, ofsVA, numTris, ofsTris, ,
			numJoints, ofsJoints, numPoses, ofsPoses, numAnims, ofsAnims, numFrames, , ofsFrames ] = h;
	if ( version !== 2 ) throw new Error( "IQM version " + version );
	const name = o => cstr( u8, ofsText + o, numText - o );
	const iqm = { numVerts, arrays: {}, meshes: [], joints: [], anims: [], frames: [] };
	const FORMATS = { 0: [ 1, ( o ) => dv.getInt8( o ) ], 1: [ 1, ( o ) => dv.getUint8( o ) ], 2: [ 2, ( o ) => dv.getInt16( o, true ) ],
					  3: [ 2, ( o ) => dv.getUint16( o, true ) ], 4: [ 4, ( o ) => dv.getInt32( o, true ) ],
					  5: [ 4, ( o ) => dv.getUint32( o, true ) ], 7: [ 4, ( o ) => dv.getFloat32( o, true ) ] };
	for ( let k = 0; k < numVA; k++ ) {
		const b = ofsVA + 20 * k;
		const type = dv.getUint32( b, true ), fmt = dv.getUint32( b + 8, true ), size = dv.getUint32( b + 12, true ), ofs = dv.getUint32( b + 16, true );
		const f = FORMATS[fmt];
		if ( !f ) continue;
		const a = new Float32Array( numVerts * size );
		for ( let i = 0; i < numVerts * size; i++ ) a[i] = f[1]( ofs + f[0] * i );
		iqm.arrays[type] = { size, data: a };
	}
	iqm.tris = new Uint32Array( numTris * 3 );
	for ( let i = 0; i < numTris * 3; i++ ) iqm.tris[i] = dv.getUint32( ofsTris + 4 * i, true );
	for ( let k = 0; k < numMeshes; k++ ) {
		const b = ofsMeshes + 24 * k, g = i => dv.getUint32( b + 4 * i, true );
		iqm.meshes.push( { name: name( g( 0 ) ), material: name( g( 1 ) ), firstVert: g( 2 ), numVerts: g( 3 ), firstTri: g( 4 ), numTris: g( 5 ) } );
	}
	for ( let k = 0; k < numJoints; k++ ) {
		const b = ofsJoints + 48 * k, f = i => dv.getFloat32( b + 8 + 4 * i, true );
		iqm.joints.push( { name: name( dv.getUint32( b, true ) ), parent: dv.getInt32( b + 4, true ),
						   t: [ f( 0 ), f( 1 ), f( 2 ) ], q: [ f( 3 ), f( 4 ), f( 5 ), f( 6 ) ], s: [ f( 7 ), f( 8 ), f( 9 ) ] } );
	}
	for ( let k = 0; k < numAnims; k++ ) {
		const b = ofsAnims + 20 * k;
		iqm.anims.push( { name: name( dv.getUint32( b, true ) ), first: dv.getUint32( b + 4, true ), count: dv.getUint32( b + 8, true ),
						  fps: dv.getFloat32( b + 12, true ), flags: dv.getUint32( b + 16, true ) } );
	}
	const poses = [];
	for ( let k = 0; k < numPoses; k++ ) {
		const b = ofsPoses + 88 * k, offs = [], scales = [];
		for ( let c = 0; c < 10; c++ ) { offs.push( dv.getFloat32( b + 8 + 4 * c, true ) ); scales.push( dv.getFloat32( b + 48 + 4 * c, true ) ); }
		poses.push( { mask: dv.getUint32( b + 4, true ), offs, scales } );
	}
	let o = ofsFrames;
	for ( let f = 0; f < numFrames; f++ ) {
		const row = [];
		for ( const p of poses ) {
			const ch = [];
			for ( let c = 0; c < 10; c++ ) {
				let x = p.offs[c];
				if ( p.mask & ( 1 << c ) ) { x += dv.getUint16( o, true ) * p.scales[c]; o += 2; }
				ch.push( x );
			}
			row.push( m4trs( ch.slice( 0, 3 ), ch.slice( 3, 7 ), ch.slice( 7, 10 ) ) );
		}
		iqm.frames.push( row );
	}
	// the bind pose's joints in model space, and their inverses
	iqm.bind = [];
	for ( const j of iqm.joints ) {
		const local = m4trs( j.t, j.q, j.s );
		iqm.bind.push( j.parent >= 0 ? m4mul( iqm.bind[j.parent], local ) : local );
	}
	iqm.invBind = iqm.bind.map( m4inv );
	return iqm;
}

// MD3: every surface's vertexes, a frame at a time; the frames' names
function parseMD3( buf ) {
	const dv = new DataView( buf ), u8 = new Uint8Array( buf );
	if ( cstr( u8, 0, 4 ) !== "IDP3" ) throw new Error( "not an MD3" );
	const numFrames = dv.getInt32( 76, true ), numSurfaces = dv.getInt32( 84, true );
	const ofsFrames = dv.getInt32( 92, true );
	let ofsSurf = dv.getInt32( 100, true );
	const md3 = { frameNames: [], surfaces: [], numFrames };
	for ( let f = 0; f < numFrames; f++ ) md3.frameNames.push( cstr( u8, ofsFrames + 56 * f + 40, 16 ) );
	for ( let s = 0; s < numSurfaces; s++ ) {
		const b = ofsSurf, g = i => dv.getInt32( b + i, true );
		const sname = cstr( u8, b + 4, 64 ), nf = g( 72 ), nv = g( 80 ), nt = g( 84 ), ofsTri = g( 88 ), ofsXyz = g( 100 );
		const tris = new Uint32Array( nt * 3 );
		for ( let i = 0; i < nt * 3; i++ ) tris[i] = dv.getInt32( b + ofsTri + 4 * i, true );
		const frames = [];
		for ( let f = 0; f < nf; f++ ) {
			const a = new Float32Array( nv * 3 );
			for ( let v = 0; v < nv; v++ ) {
				for ( let c = 0; c < 3; c++ ) a[v * 3 + c] = dv.getInt16( b + ofsXyz + ( f * nv + v ) * 8 + 2 * c, true ) / 64;
			}
			frames.push( a );
		}
		md3.surfaces.push( { name: sname, numVerts: nv, tris, frames } );
		ofsSurf += g( 104 );
	}
	// the animations by the frames' names ("run01"...), as tools/rig/md3.py
	md3.anims = [];
	md3.frameNames.forEach( ( n, i ) => {
		const p = n.replace( /\d+$/, "" ), last = md3.anims[md3.anims.length - 1];
		if ( last && last.name === p ) last.count++;
		else md3.anims.push( { name: p, first: i, count: 1 } );
	} );
	return md3;
}

// TGA (uncompressed or RLE, 8/24/32 bits) to RGBA, top row first
function parseTGA( buf ) {
	const u8 = new Uint8Array( buf );
	const idLen = u8[0], cmapType = u8[1], type = u8[2], w = u8[12] | ( u8[13] << 8 ), h = u8[14] | ( u8[15] << 8 ), bpp = u8[16], desc = u8[17];
	let o = 18 + idLen + ( cmapType ? ( u8[5] | ( u8[6] << 8 ) ) * ( u8[7] >> 3 ) : 0 );
	const px = bpp >> 3, out = new Uint8Array( w * h * 4 );
	const put = ( i, s ) => {
		if ( px === 1 ) { out[i * 4] = out[i * 4 + 1] = out[i * 4 + 2] = u8[s]; out[i * 4 + 3] = 255; }
		else { out[i * 4] = u8[s + 2]; out[i * 4 + 1] = u8[s + 1]; out[i * 4 + 2] = u8[s]; out[i * 4 + 3] = px === 4 ? u8[s + 3] : 255; }
	};
	if ( type === 2 || type === 3 ) {
		for ( let i = 0; i < w * h; i++, o += px ) put( i, o );
	} else if ( type === 10 || type === 11 ) {
		let i = 0;
		while ( i < w * h ) {
			const c = u8[o++], n = ( c & 0x7f ) + 1;
			if ( c & 0x80 ) { for ( let k = 0; k < n; k++ ) put( i++, o ); o += px; }
			else { for ( let k = 0; k < n; k++, o += px ) put( i++, o ); }
		}
	} else throw new Error( "TGA type " + type );
	if ( !( desc & 0x20 ) ) {
		// stored bottom up
		const row = w * 4, tmp = new Uint8Array( row );
		for ( let y = 0; y < h >> 1; y++ ) {
			const a = y * row, b = ( h - 1 - y ) * row;
			tmp.set( out.subarray( a, a + row ) ); out.copyWithin( a, b, b + row ); out.set( tmp, b );
		}
	}
	return { w, h, data: out };
}

// the bodies of an articulated figure as autorig writes it (af/*.af)
function parseAF( text ) {
	const bodies = [];
	text = text.replace( /\/\/[^\n]*/g, "" );
	const re = /body\s+"([^"]+)"\s*\{([^}]*)\}/g;
	const vec = s => s.split( "," ).map( Number );
	let m;
	while ( ( m = re.exec( text ) ) ) {
		const b = { name: m[1] }, body = m[2];
		const j = /joint\s+"([^"]+)"/.exec( body ); b.joint = j && j[1];
		const box = /model\s+box\(\s*\(([^)]*)\)\s*,\s*\(([^)]*)\)\s*\)/.exec( body );
		const bone = /model\s+bone\(\s*\(([^)]*)\)\s*,\s*\(([^)]*)\)\s*,\s*([-\d.]+)\s*\)/.exec( body );
		const org = /origin\s+\(([^)]*)\)/.exec( body );
		b.origin = org ? vec( org[1] ) : [ 0, 0, 0 ];
		if ( box ) { b.lo = vec( box[1] ); b.hi = vec( box[2] ); }
		if ( bone ) { b.a = vec( bone[1] ); b.b = vec( bone[2] ); b.w = Number( bone[3] ); }
		bodies.push( b );
	}
	return bodies;
}

// ------------------------------------------------------------------ GL

const canvas = document.getElementById( "gl" );
const gl = canvas.getContext( "webgl2", { antialias: true } );

function program( vs, fs ) {
	const p = gl.createProgram();
	for ( const [ type, src ] of [ [ gl.VERTEX_SHADER, vs ], [ gl.FRAGMENT_SHADER, fs ] ] ) {
		const s = gl.createShader( type );
		gl.shaderSource( s, src ); gl.compileShader( s );
		if ( !gl.getShaderParameter( s, gl.COMPILE_STATUS ) ) throw new Error( gl.getShaderInfoLog( s ) );
		gl.attachShader( p, s );
	}
	gl.linkProgram( p );
	if ( !gl.getProgramParameter( p, gl.LINK_STATUS ) ) throw new Error( gl.getProgramInfoLog( p ) );
	return p;
}
const meshProg = program( `#version 300 es
in vec3 pos; in vec3 nrm; in vec2 uv; in vec3 col;
uniform mat4 mvp;
out vec3 vN; out vec2 vUV; out vec3 vC;
void main() { vN = nrm; vUV = uv; vC = col; gl_Position = mvp * vec4( pos, 1.0 ); }`,
`#version 300 es
precision mediump float;
in vec3 vN; in vec2 vUV; in vec3 vC;
uniform sampler2D tex; uniform int mode;	// 0 texture, 1 vertex colours, 2 grey
out vec4 frag;
void main() {
	vec3 n = normalize( vN );
	float l = 0.45 + 0.55 * abs( dot( n, normalize( vec3( 0.4, 0.3, 0.85 ) ) ) );
	vec3 c = mode == 0 ? texture( tex, vUV ).rgb : ( mode == 1 ? vC : vec3( 0.75 ) );
	frag = vec4( c * l, 1.0 );
}` );
const lineProg = program( `#version 300 es
in vec3 pos; in vec3 col; uniform mat4 mvp; uniform float psize; out vec3 vC;
void main() { vC = col; gl_PointSize = psize; gl_Position = mvp * vec4( pos, 1.0 ); }`,
`#version 300 es
precision mediump float; in vec3 vC; out vec4 frag; void main() { frag = vec4( vC, 1.0 ); }` );

function buffer() { return gl.createBuffer(); }
function upload( buf, data, target = gl.ARRAY_BUFFER ) { gl.bindBuffer( target, buf ); gl.bufferData( target, data, gl.DYNAMIC_DRAW ); }
function attrib( prog, name, buf, size ) {
	const loc = gl.getAttribLocation( prog, name );
	if ( loc < 0 ) return;
	gl.bindBuffer( gl.ARRAY_BUFFER, buf ); gl.enableVertexAttribArray( loc ); gl.vertexAttribPointer( loc, size, gl.FLOAT, false, 0, 0 );
}
const B = { pos: buffer(), nrm: buffer(), uv: buffer(), col: buffer(), idx: buffer(), lpos: buffer(), lcol: buffer() };
const whiteTex = gl.createTexture();
gl.bindTexture( gl.TEXTURE_2D, whiteTex );
gl.texImage2D( gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array( [ 200, 200, 200, 255 ] ) );

// ------------------------------------------------------------------ state

const $ = id => document.getElementById( id );
const S = { model: null, iqm: null, md3: null, af: null, tex: {}, anim: 0, frame: 0, playing: false, t0: 0, sel: -1,
			cam: { yaw: -0.6, pitch: 0.35, dist: 140, target: [ 0, 0, 30 ] } };

async function fetchBuf( url ) {
	const r = await fetch( url );
	if ( !r.ok ) throw new Error( url + ": " + r.status );
	return r.arrayBuffer();
}

async function loadModel( m ) {
	$( "err" ).textContent = "";
	S.model = m;
	S.iqm = parseIQM( await fetchBuf( "/dkres/" + m.iqm ) );
	S.md3 = null; S.af = null; S.match = null;
	try { if ( m.md3 ) S.md3 = parseMD3( await fetchBuf( "/dkres/" + m.md3 ) ); }
	catch ( e ) { $( "err" ).textContent = "MD3: " + e.message; }
	S.root = null;
	try { if ( m.root ) S.root = JSON.parse( new TextDecoder().decode( await fetchBuf( "/dkres/" + m.root ) ) ); }
	catch ( e ) { $( "err" ).textContent += " root: " + e.message; }
	try { if ( m.af ) S.af = parseAF( new TextDecoder().decode( await fetchBuf( "/" + m.af ) ) ); }
	catch ( e ) { $( "err" ).textContent += " AF: " + e.message; }
	for ( const mesh of S.iqm.meshes ) {
		if ( S.tex[mesh.material] !== undefined ) continue;
		S.tex[mesh.material] = whiteTex;
		try {
			const img = parseTGA( await fetchBuf( "/dkres/" + mesh.material ) );
			const t = gl.createTexture();
			gl.bindTexture( gl.TEXTURE_2D, t );
			gl.texImage2D( gl.TEXTURE_2D, 0, gl.RGBA, img.w, img.h, 0, gl.RGBA, gl.UNSIGNED_BYTE, img.data );
			gl.generateMipmap( gl.TEXTURE_2D );
			gl.texParameteri( gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR );
			S.tex[mesh.material] = t;
		} catch ( e ) { console.warn( mesh.material, e ); }
	}
	if ( S.md3 ) matchMD3();
	// the joints' list
	const list = $( "joints" );
	list.innerHTML = "";
	S.iqm.joints.forEach( ( j, i ) => {
		let depth = 0;
		for ( let p = j.parent; p >= 0; p = S.iqm.joints[p].parent ) depth++;
		const d = document.createElement( "div" );
		d.textContent = " ".repeat( depth * 2 ) + j.name;
		d.onclick = () => { S.sel = S.sel === i ? -1 : i; update(); };
		list.appendChild( d );
	} );
	S.sel = -1;
	// the animations
	const sel = $( "anim" );
	sel.innerHTML = "";
	S.iqm.anims.forEach( ( a, i ) => {
		const o = document.createElement( "option" );
		o.value = i; o.textContent = `${a.name}  (${a.count} frames, ${a.fps} fps)`;
		sel.appendChild( o );
	} );
	setAnim( 0 );
	loadValidation();
	// the camera on the bind pose
	const p = S.iqm.arrays[0].data;
	let lo = [ 1e9, 1e9, 1e9 ], hi = [ -1e9, -1e9, -1e9 ];
	for ( let i = 0; i < S.iqm.numVerts; i++ ) for ( let c = 0; c < 3; c++ ) { lo[c] = Math.min( lo[c], p[i * 3 + c] ); hi[c] = Math.max( hi[c], p[i * 3 + c] ); }
	S.span = Math.max( hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2] );
	S.cam.target = scl( add( lo, hi ), 0.5 );
	S.cam.dist = S.span * 1.8;
	location.hash = m.def;
	update();
}

// which MD3 vertex each IQM vertex is: nearest in the frame the rig was made
// from (the MD3's first, or the first of the animation --rest named: the one
// whose vertexes the bind pose's are nearest)
function matchMD3() {
	const iqm = S.iqm, md3 = S.md3, P = iqm.arrays[0].data;
	const all = [];		// [ surface, vertex ]
	md3.surfaces.forEach( ( s, si ) => { for ( let v = 0; v < s.numVerts; v++ ) all.push( [ si, v ] ); } );
	const nearest = ( f, i ) => {
		let best = -1, bd = 1e18;
		for ( let k = 0; k < all.length; k++ ) {
			const [ si, v ] = all[k], a = md3.surfaces[si].frames[f];
			const d = ( a[v * 3] - P[i * 3] ) ** 2 + ( a[v * 3 + 1] - P[i * 3 + 1] ) ** 2 + ( a[v * 3 + 2] - P[i * 3 + 2] ) ** 2;
			if ( d < bd ) { bd = d; best = k; }
		}
		return [ best, bd ];
	};
	// (where the most of its vertexes are exactly: a prop shows elsewhere,
	// and standing frames alike are near, but only the bind's is exact)
	let restFrame = 0, restScore = null;
	for ( const f of new Set( [ 0, ...md3.anims.map( a => a.first ) ] ) ) {
		let exact = 0, sum = 0;
		for ( let i = 0; i < iqm.numVerts; i++ ) { const d = nearest( f, i )[1]; if ( d < 1e-4 ) exact++; sum += d; }
		if ( !restScore || exact > restScore[0] || ( exact === restScore[0] && sum < restScore[1] ) ) { restScore = [ exact, sum ]; restFrame = f; }
	}
	S.md3Rest = restFrame;
	S.match = new Int32Array( iqm.numVerts );
	S.matchDist = new Float32Array( iqm.numVerts );
	for ( let i = 0; i < iqm.numVerts; i++ ) {
		let [ k, d ] = nearest( restFrame, i );
		// not there in the bind frame: a prop, at rest in the frame it's
		// biggest in; paired where it's exactly
		for ( let f = 0; d >= 1e-4 && f < md3.numFrames; f++ ) {
			const [ k2, d2 ] = nearest( f, i );
			if ( d2 < 1e-4 ) { k = k2; d = d2; }
		}
		S.match[i] = k; S.matchDist[i] = Math.sqrt( d );
	}
	S.md3All = all;
}

// the MD3 frame an IQM frame was made from: the animation of the same name,
// that far in; else the frame of that name (a pose, autorig --lying's: the
// dead bodies' dead000...); else the rest frame (--rest's "rest")
function md3Frame( animIndex, k ) {
	if ( !S.md3 ) return -1;
	const a = S.iqm.anims[animIndex], m = S.md3.anims.find( x => x.name === a.name );
	if ( m ) return m.first + Math.min( k, m.count - 1 );
	const f = S.md3.frameNames.indexOf( a.name );
	return f >= 0 ? f : S.md3Rest;
}

function setAnim( i ) {
	S.anim = i; S.frame = 0;
	$( "anim" ).value = i;
	$( "frame" ).max = Math.max( 0, S.iqm.anims[i].count - 1 );
	showValidation();
	update();
}

// ------------------------------------------------------------------ validation
// each animation's verdict (tools/rig/validated.json, through the server's
// tools/rig/rigcheck.py): valid, broken, changed since it was judged, or new

const MARK = { valid: "\u2713", broken: "\u2717", changed: "!", new: "\u00b7" };

async function loadValidation() {
	S.valid = null;
	showValidation();
	const def = S.model.def;
	try {
		const st = await ( await fetch( "/api/status?def=" + encodeURIComponent( def ) ) ).json();
		if ( S.model.def !== def ) return;
		S.valid = st;
	} catch ( e ) { S.valid = {}; }
	labelAnims();
	showValidation();
}

function labelAnims() {
	[ ...$( "anim" ).options ].forEach( ( o, i ) => {
		const a = S.iqm.anims[i], v = S.valid && S.valid[a.name];
		o.textContent = `${v ? MARK[v.state] : " "} ${a.name}  (${a.count} frames, ${a.fps} fps)`;
	} );
}

function showValidation() {
	const box = $( "vstate" ), a = S.iqm && S.iqm.anims[S.anim];
	if ( !a || !S.valid ) { box.className = "vstate"; box.textContent = "checking…"; return; }
	const v = S.valid[a.name] || { state: "new" };
	box.className = "vstate " + v.state;
	const fit = v.fit ? `, fit ${v.fit[0]} average, ${v.fit[1]} worst` : "";
	box.textContent = {
		new: `${a.name}: not validated yet`,
		valid: `${a.name}: valid (${v.date}${fit})`,
		broken: `${a.name}: broken (${v.date}${fit})`,
		changed: `${a.name}: CHANGED since you marked it ${v.verdict} (${v.date}${fit}): validate again`,
	}[v.state] + ( v.note ? `\n${v.note}` : "" );
	$( "vnote" ).value = v.note || "";
}

async function judge( verdict ) {
	const a = S.iqm.anims[S.anim];
	$( "vstate" ).textContent = "recording…";
	const r = await fetch( "/api/validate", { method: "POST", headers: { "Content-Type": "application/json" },
		body: JSON.stringify( { def: S.model.def, anim: a.name, verdict, note: $( "vnote" ).value } ) } );
	const e = await r.json();
	if ( !r.ok ) { $( "err" ).textContent = e.error || "not recorded"; showValidation(); return; }
	S.valid[a.name] = e;
	labelAnims();
	showValidation();
}
$( "vvalid" ).onclick = () => judge( "valid" );
$( "vbroken" ).onclick = () => judge( "broken" );

// ------------------------------------------------------------------ pose

function pose() {
	const iqm = S.iqm, a = iqm.anims[S.anim], fi = a ? a.first + S.frame : -1;
	const world = [];
	iqm.joints.forEach( ( j, i ) => {
		const local = fi >= 0 && iqm.frames[fi] ? iqm.frames[fi][i] : m4trs( j.t, j.q, j.s );
		world.push( j.parent >= 0 ? m4mul( world[j.parent], local ) : local );
	} );
	const skin = world.map( ( w, i ) => m4mul( w, iqm.invBind[i] ) );
	const P = iqm.arrays[0].data, BI = iqm.arrays[4], BW = iqm.arrays[5], n = iqm.numVerts;
	const out = new Float32Array( n * 3 );
	for ( let v = 0; v < n; v++ ) {
		const p = [ P[v * 3], P[v * 3 + 1], P[v * 3 + 2] ];
		let acc = [ 0, 0, 0 ], wsum = 0;
		for ( let c = 0; c < 4; c++ ) {
			const w = BW ? BW.data[v * 4 + c] / 255 : ( c ? 0 : 1 );
			if ( !w ) continue;
			acc = add( acc, scl( xf( skin[BI ? BI.data[v * 4 + c] : 0], p ), w ) );
			wsum += w;
		}
		if ( wsum ) acc = scl( acc, 1 / wsum );
		out.set( acc, v * 3 );
	}
	return { world, skin, verts: out };
}

function normals( verts, tris, n ) {
	const N = new Float32Array( n * 3 );
	for ( let t = 0; t < tris.length; t += 3 ) {
		const [ a, b, c ] = [ tris[t], tris[t + 1], tris[t + 2] ];
		const pa = [ verts[a * 3], verts[a * 3 + 1], verts[a * 3 + 2] ];
		const fn = cross( sub( [ verts[b * 3], verts[b * 3 + 1], verts[b * 3 + 2] ], pa ), sub( [ verts[c * 3], verts[c * 3 + 1], verts[c * 3 + 2] ], pa ) );
		for ( const v of [ a, b, c ] ) for ( let k = 0; k < 3; k++ ) N[v * 3 + k] += fn[k];
	}
	return N;
}

function errColour( e ) {
	// green under half a unit, yellow at 2, red from 6
	if ( e < 0.5 ) return [ 0.25, 0.8, 0.35 ];
	if ( e < 2 ) { const t = ( e - 0.5 ) / 1.5; return [ 0.25 + 0.75 * t, 0.8 + 0.1 * t, 0.35 - 0.2 * t ]; }
	const t = Math.min( 1, ( e - 2 ) / 4 ); return [ 1, 0.9 - 0.75 * t, 0.15 ];
}

// ------------------------------------------------------------------ draw

let lines = [], lcols = [], points = [], pcols = [];
function line( a, b, c ) { lines.push( ...a, ...b ); lcols.push( ...c, ...c ); }
function point( a, c ) { points.push( ...a ); pcols.push( ...c ); }
function boxLines( m, lo, hi, c ) {
	const corner = i => xf( m, [ i & 1 ? hi[0] : lo[0], i & 2 ? hi[1] : lo[1], i & 4 ? hi[2] : lo[2] ] );
	for ( const [ a, b ] of [ [ 0, 1 ], [ 2, 3 ], [ 4, 5 ], [ 6, 7 ], [ 0, 2 ], [ 1, 3 ], [ 4, 6 ], [ 5, 7 ], [ 0, 4 ], [ 1, 5 ], [ 2, 6 ], [ 3, 7 ] ] ) {
		line( corner( a ), corner( b ), c );
	}
}

function update() { S.dirty = true; }

function draw() {
	S.dirty = false;
	const w = canvas.clientWidth * devicePixelRatio, h = canvas.clientHeight * devicePixelRatio;
	if ( canvas.width !== w || canvas.height !== h ) { canvas.width = w; canvas.height = h; }
	gl.viewport( 0, 0, w, h );
	gl.clearColor( 0.106, 0.114, 0.133, 1 );
	gl.clear( gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT );
	gl.enable( gl.DEPTH_TEST );
	if ( !S.iqm ) return;
	const iqm = S.iqm, a = iqm.anims[S.anim];
	$( "frame" ).value = S.frame;
	$( "frameNo" ).textContent = a ? `${S.frame + 1} / ${a.count}` : "";
	const P = pose();
	const md3f = md3Frame( S.anim, S.frame );
	// what --root-out took out of this frame: Daikatana's frame without it
	const ra = S.root && a && S.root.anims[a.name], rp = ra && ra.path[Math.min( S.frame, ra.path.length - 1 )];
	const md3Off = rp ? [ -rp[0], -rp[1], -( rp[2] || 0 ) ] : [ 0, 0, 0 ];

	// camera
	const cam = S.cam;
	let target = cam.target;
	if ( $( "lockOrigin" ).checked ) {
		const hips = iqm.joints.findIndex( j => j.name === "Hips" );
		if ( hips >= 0 ) target = xf( P.world[hips], [ 0, 0, 0 ] );
	}
	const eye = add( target, scl( [ Math.cos( cam.pitch ) * Math.cos( cam.yaw ), Math.cos( cam.pitch ) * Math.sin( cam.yaw ), Math.sin( cam.pitch ) ], cam.dist ) );
	const vp = m4mul( perspective( 0.8, w / h, 0.5, 5000 ), lookAt( eye, target, [ 0, 0, 1 ] ) );

	// the vertexes' error against the MD3's frame
	const n = iqm.numVerts, err = new Float32Array( n );
	let errSum = 0, errMax = 0, md3Pts = null;
	if ( S.md3 && S.match && md3f >= 0 ) {
		md3Pts = new Float32Array( n * 3 );
		for ( let i = 0; i < n; i++ ) {
			const [ si, v ] = S.md3All[S.match[i]], fr = S.md3.surfaces[si].frames[md3f];
			if ( !fr ) continue;
			for ( let c = 0; c < 3; c++ ) md3Pts[i * 3 + c] = fr[v * 3 + c] + md3Off[c];
			err[i] = Math.hypot( P.verts[i * 3] - md3Pts[i * 3], P.verts[i * 3 + 1] - md3Pts[i * 3 + 1], P.verts[i * 3 + 2] - md3Pts[i * 3 + 2] );
			errSum += err[i]; errMax = Math.max( errMax, err[i] );
		}
	}

	// the rigged mesh
	if ( $( "showMesh" ).checked ) {
		const cols = new Float32Array( n * 3 );
		const selVerts = S.sel >= 0 && iqm.arrays[4] ? iqm.arrays[4].data : null;
		for ( let i = 0; i < n; i++ ) {
			let c = $( "showErr" ).checked ? errColour( err[i] ) : [ 0.75, 0.75, 0.75 ];
			if ( selVerts ) {
				const BW = iqm.arrays[5].data;
				let wsel = 0;
				for ( let k = 0; k < 4; k++ ) if ( selVerts[i * 4 + k] === S.sel ) wsel += BW[i * 4 + k] / 255;
				if ( wsel > 0 ) c = [ 0.3 + 0.7 * wsel, 0.35, 0.95 - 0.6 * wsel ];
			}
			cols.set( c, i * 3 );
		}
		const mode = ( $( "showErr" ).checked || S.sel >= 0 ) ? 1 : ( $( "showTex" ).checked ? 0 : 2 );
		gl.useProgram( meshProg );
		upload( B.pos, P.verts ); attrib( meshProg, "pos", B.pos, 3 );
		upload( B.nrm, normals( P.verts, iqm.tris, n ) ); attrib( meshProg, "nrm", B.nrm, 3 );
		upload( B.uv, iqm.arrays[1] ? iqm.arrays[1].data : new Float32Array( n * 2 ) ); attrib( meshProg, "uv", B.uv, 2 );
		upload( B.col, cols ); attrib( meshProg, "col", B.col, 3 );
		gl.uniformMatrix4fv( gl.getUniformLocation( meshProg, "mvp" ), false, vp );
		gl.uniform1i( gl.getUniformLocation( meshProg, "mode" ), mode );
		upload( B.idx, iqm.tris, gl.ELEMENT_ARRAY_BUFFER );
		for ( const mesh of iqm.meshes ) {
			gl.bindTexture( gl.TEXTURE_2D, S.tex[mesh.material] || whiteTex );
			gl.drawElements( gl.TRIANGLES, mesh.numTris * 3, gl.UNSIGNED_INT, mesh.firstTri * 12 );
		}
	}

	lines = []; lcols = []; points = []; pcols = [];
	// the floor and the origin
	if ( $( "showGrid" ).checked ) {
		const g = 8 * Math.ceil( S.span / 8 ), c = [ 0.24, 0.26, 0.3 ];
		for ( let x = -g; x <= g; x += 8 ) { line( [ x, -g, 0 ], [ x, g, 0 ], c ); line( [ -g, x, 0 ], [ g, x, 0 ], c ); }
		line( [ 0, 0, 0 ], [ 16, 0, 0 ], [ 1, 0.3, 0.3 ] ); line( [ 0, 0, 0 ], [ 0, 16, 0 ], [ 0.3, 1, 0.3 ] ); line( [ 0, 0, 0 ], [ 0, 0, 16 ], [ 0.4, 0.5, 1 ] );
	}
	// Daikatana's frame: its triangles' edges, over the rig or beside it
	if ( $( "showMd3" ).checked && S.md3 && md3f >= 0 ) {
		const off = add( md3Off, $( "sideBySide" ).checked ? [ 0, -S.span * 1.1, 0 ] : [ 0, 0, 0 ] );
		for ( const s of S.md3.surfaces ) {
			const fr = s.frames[md3f];
			if ( !fr ) continue;
			const p = v => add( [ fr[v * 3], fr[v * 3 + 1], fr[v * 3 + 2] ], off );
			for ( let t = 0; t < s.tris.length; t += 3 ) {
				const [ a_, b_, c_ ] = [ s.tris[t], s.tris[t + 1], s.tris[t + 2] ];
				line( p( a_ ), p( b_ ), [ 1, 0.6, 0.24 ] ); line( p( b_ ), p( c_ ), [ 1, 0.6, 0.24 ] ); line( p( c_ ), p( a_ ), [ 1, 0.6, 0.24 ] );
			}
		}
	}
	// the ragdoll's bodies, each moving with its joint
	if ( $( "showAF" ).checked && S.af ) {
		for ( const b of S.af ) {
			const ji = iqm.joints.findIndex( j => j.name === b.joint );
			const m = ji >= 0 ? P.skin[ji] : m4();
			const c = [ 0.37, 0.88, 0.54 ];
			if ( b.lo ) {
				const t = m4(); t[12] = b.origin[0]; t[13] = b.origin[1]; t[14] = b.origin[2];
				boxLines( m4mul( m, t ), b.lo, b.hi, c );
			} else if ( b.a ) {
				// a bone: a box b.w wide from a to b
				const d = norm( sub( b.b, b.a ) ), up = Math.abs( d[2] ) < 0.9 ? [ 0, 0, 1 ] : [ 1, 0, 0 ];
				const x = norm( cross( up, d ) ), y = cross( d, x ), L = len( sub( b.b, b.a ) ), t = m4();
				t[0] = x[0]; t[1] = x[1]; t[2] = x[2]; t[4] = y[0]; t[5] = y[1]; t[6] = y[2]; t[8] = d[0]; t[9] = d[1]; t[10] = d[2];
				t[12] = b.a[0]; t[13] = b.a[1]; t[14] = b.a[2];
				boxLines( m4mul( m, t ), [ -b.w / 2, -b.w / 2, 0 ], [ b.w / 2, b.w / 2, L ], c );
			}
			point( xf( m, b.origin ), c );
		}
	}
	// the skeleton
	const labels = $( "labels" );
	labels.innerHTML = "";
	if ( $( "showSkel" ).checked ) {
		iqm.joints.forEach( ( j, i ) => {
			const p = xf( P.world[i], [ 0, 0, 0 ] ), c = i === S.sel ? [ 0.4, 0.8, 1 ] : [ 1, 0.88, 0.54 ];
			if ( j.parent >= 0 ) line( xf( P.world[j.parent], [ 0, 0, 0 ] ), p, c );
			point( p, c );
			if ( $( "showNames" ).checked || i === S.sel ) {
				const q = [ ...p, 1 ], cl = [ 0, 1, 2, 3 ].map( r => vp[r] * q[0] + vp[4 + r] * q[1] + vp[8 + r] * q[2] + vp[12 + r] );
				if ( cl[3] > 0 ) {
					const s = document.createElement( "span" );
					s.textContent = j.name;
					s.style.left = ( ( cl[0] / cl[3] + 1 ) / 2 * canvas.clientWidth ) + "px";
					s.style.top = ( ( 1 - cl[1] / cl[3] ) / 2 * canvas.clientHeight ) + "px";
					labels.appendChild( s );
				}
			}
		} );
	}
	gl.useProgram( lineProg );
	gl.uniformMatrix4fv( gl.getUniformLocation( lineProg, "mvp" ), false, vp );
	if ( lines.length ) {
		upload( B.lpos, new Float32Array( lines ) ); attrib( lineProg, "pos", B.lpos, 3 );
		upload( B.lcol, new Float32Array( lcols ) ); attrib( lineProg, "col", B.lcol, 3 );
		gl.drawArrays( gl.LINES, 0, lines.length / 3 );
	}
	if ( points.length ) {
		gl.disable( gl.DEPTH_TEST );
		gl.uniform1f( gl.getUniformLocation( lineProg, "psize" ), 6 * devicePixelRatio );
		upload( B.lpos, new Float32Array( points ) ); attrib( lineProg, "pos", B.lpos, 3 );
		upload( B.lcol, new Float32Array( pcols ) ); attrib( lineProg, "col", B.lcol, 3 );
		gl.drawArrays( gl.POINTS, 0, points.length / 3 );
	}

	// the numbers
	let hud = `${S.model.def}  ${S.model.iqm}\n${a ? a.name : "-"} frame ${S.frame}` +
		( S.md3 ? `   MD3 frame ${md3f} (${S.md3.frameNames[md3f] || "?"})` : "   no MD3" );
	if ( md3Pts ) hud += `\nerror vs MD3: ${( errSum / n ).toFixed( 2 )} average, ${errMax.toFixed( 2 )} at most`;
	if ( ra ) hud += `\nroot motion out: starts ${ra.start.join( " " )}, moves ${ra.move.join( " " )} (MD3 drawn without it)`;
	if ( S.match ) {
		let mm = 0; for ( const d of S.matchDist ) mm = Math.max( mm, d );
		hud += `\nbind pose = MD3 frame ${S.md3Rest} (${S.md3.frameNames[S.md3Rest]}), vertexes matched to ${mm.toFixed( 2 )}`;
	}
	$( "hud" ).textContent = hud;

	// the selected joint
	let info = "";
	if ( S.sel >= 0 ) {
		const j = iqm.joints[S.sel], p = xf( P.world[S.sel], [ 0, 0, 0 ] );
		info += `${j.name}  parent ${j.parent >= 0 ? iqm.joints[j.parent].name : "-"}\n`;
		info += `at   ${p.map( x => x.toFixed( 1 ) ).join( " " )}\n`;
		const bp = xf( iqm.bind[S.sel], [ 0, 0, 0 ] );
		info += `bind ${bp.map( x => x.toFixed( 1 ) ).join( " " )}\n`;
		if ( j.parent >= 0 ) {
			const L = len( sub( p, xf( P.world[j.parent], [ 0, 0, 0 ] ) ) ), L0 = len( sub( bp, xf( iqm.bind[j.parent], [ 0, 0, 0 ] ) ) );
			info += `bone ${L.toFixed( 2 )} long (bind ${L0.toFixed( 2 )})${Math.abs( L - L0 ) > 0.05 ? "  STRETCHED" : ""}\n`;
		}
		if ( iqm.arrays[4] ) {
			let cnt = 0, e = 0, em = 0;
			for ( let i = 0; i < n; i++ ) {
				if ( iqm.arrays[4].data[i * 4] === S.sel ) { cnt++; e += err[i]; em = Math.max( em, err[i] ); }
			}
			info += `${cnt} vertexes mostly its` + ( md3Pts && cnt ? `, off ${( e / cnt ).toFixed( 2 )} average, ${em.toFixed( 2 )} at most` : "" );
		}
	}
	$( "info" ).textContent = info;
	[ ...$( "joints" ).children ].forEach( ( d, i ) => d.classList.toggle( "sel", i === S.sel ) );
}

// ------------------------------------------------------------------ input

function loop( t ) {
	if ( S.playing && S.iqm ) {
		const a = S.iqm.anims[S.anim];
		const f = Math.floor( ( t - S.t0 ) / 1000 * a.fps * Number( $( "speed" ).value ) ) % Math.max( 1, a.count );
		if ( f !== S.frame ) { S.frame = f; S.dirty = true; }
	}
	if ( S.dirty ) draw();
	requestAnimationFrame( loop );
}

let drag = null;
canvas.addEventListener( "mousedown", e => { drag = { x: e.clientX, y: e.clientY, pan: e.shiftKey || e.button === 2 }; } );
canvas.addEventListener( "contextmenu", e => e.preventDefault() );
window.addEventListener( "mouseup", () => { drag = null; } );
window.addEventListener( "mousemove", e => {
	if ( !drag ) return;
	const dx = e.clientX - drag.x, dy = e.clientY - drag.y, c = S.cam;
	drag.x = e.clientX; drag.y = e.clientY;
	if ( drag.pan ) {
		const k = c.dist / canvas.clientHeight;
		const right = [ -Math.sin( c.yaw ), Math.cos( c.yaw ), 0 ];
		const up = [ -Math.sin( c.pitch ) * Math.cos( c.yaw ), -Math.sin( c.pitch ) * Math.sin( c.yaw ), Math.cos( c.pitch ) ];
		c.target = add( c.target, add( scl( right, -dx * k ), scl( up, dy * k ) ) );
	} else {
		c.yaw -= dx * 0.01;
		c.pitch = Math.max( -1.55, Math.min( 1.55, c.pitch + dy * 0.01 ) );
	}
	update();
} );
canvas.addEventListener( "wheel", e => { e.preventDefault(); S.cam.dist *= Math.exp( e.deltaY * 0.001 ); update(); }, { passive: false } );
window.addEventListener( "resize", update );
window.addEventListener( "keydown", e => {
	if ( e.target.tagName === "SELECT" || e.target.tagName === "INPUT" ) return;
	if ( e.key === " " ) { e.preventDefault(); $( "play" ).click(); }
	if ( e.key === "ArrowRight" ) $( "next" ).click();
	if ( e.key === "ArrowLeft" ) $( "prev" ).click();
} );
$( "play" ).onclick = () => {
	S.playing = !S.playing;
	$( "play" ).textContent = S.playing ? "Pause" : "Play";
	if ( S.playing && S.iqm ) S.t0 = performance.now() - S.frame / S.iqm.anims[S.anim].fps / Number( $( "speed" ).value ) * 1000;
};
const step = d => { if ( !S.iqm ) return; const a = S.iqm.anims[S.anim]; S.frame = ( S.frame + d + a.count ) % a.count; update(); };
$( "next" ).onclick = () => step( 1 );
$( "prev" ).onclick = () => step( -1 );
$( "frame" ).oninput = e => { S.frame = Number( e.target.value ); update(); };
$( "anim" ).onchange = e => setAnim( Number( e.target.value ) );
for ( const id of [ "showMesh", "showTex", "showErr", "showMd3", "sideBySide", "showSkel", "showNames", "showAF", "showGrid", "lockOrigin" ] ) {
	$( id ).onchange = update;
}

// ------------------------------------------------------------------ start

( async () => {
	const models = await ( await fetch( "/api/models" ) ).json();
	const sel = $( "model" );
	models.forEach( ( m, i ) => {
		const o = document.createElement( "option" );
		o.value = i; o.textContent = m.def + ( m.md3 ? "" : "  (no MD3)" );
		sel.appendChild( o );
	} );
	sel.onchange = () => loadModel( models[sel.value] ).catch( e => { $( "err" ).textContent = e.message; } );
	const want = decodeURIComponent( location.hash.slice( 1 ) );
	const start = Math.max( 0, models.findIndex( m => m.def === want ) );
	sel.value = start;
	await loadModel( models[start] ).catch( e => { $( "err" ).textContent = e.message; } );
	requestAnimationFrame( loop );
} )();
