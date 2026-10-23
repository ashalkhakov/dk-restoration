#!/usr/bin/env python3
"""The rig viewer's server (./dk viewer): the page (tools/rig/viewer), the
game data it shows (dkres: the IQMs, the MD3s they were made from, the
skins) and the ragdolls (af/), on this machine only.

  serve.py [port]

/api/models lists the rigged models: every def whose "mesh" is an IQM
autorig made (def/*.def), with the MD3 it was made from (the def's first
line says) and its ragdoll (af/<name>.af).
"""
import http.server
import json
import os
import re
import sys

ROOT = os.path.normpath( os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), "..", "..", ".." ) )
PAGE = os.path.join( ROOT, "tools", "rig", "viewer" )
DKRES = os.path.join( ROOT, "dkres" )


def models():
	out = []
	defdir = os.path.join( ROOT, "def" )
	for fn in sorted( os.listdir( defdir ) ):
		if not fn.endswith( ".def" ):
			continue
		text = open( os.path.join( defdir, fn ), encoding = "latin-1" ).read()
		mesh = re.search( r'"mesh"\s+"(models/rigged/[^"]+\.iqm)"', text )
		if not mesh:
			continue
		src = re.search( r"made by tools/rig/\w+\.py from (\S+\.md3)", text )
		name = re.search( r"entityDef\s+(\S+)", text )
		ragdoll = re.search( r'"ragdoll"\s+"([^"]+)"', text )
		af = None
		if ragdoll:
			for cand in ( ragdoll.group( 1 ) + ".af", ):
				if os.path.exists( os.path.join( ROOT, "af", cand ) ):
					af = "af/" + cand
		out.append( {
			"def": name.group( 1 ) if name else fn[:-4],
			"file": "def/" + fn,
			"iqm": mesh.group( 1 ),
			"md3": src.group( 1 ) if src else None,
			"af": af,
		} )
	return out


class Handler( http.server.SimpleHTTPRequestHandler ):
	def log_message( self, fmt, *args ):
		pass

	def send_file( self, path ):
		path = os.path.realpath( path )
		if not ( path.startswith( ROOT + os.sep ) and os.path.isfile( path ) ):
			self.send_error( 404 )
			return
		data = open( path, "rb" ).read()
		self.send_response( 200 )
		ext = os.path.splitext( path )[1].lower()
		self.send_header( "Content-Type", { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" }.get(
			ext, "application/octet-stream" ) )
		self.send_header( "Content-Length", str( len( data ) ) )
		self.send_header( "Cache-Control", "no-store" )
		self.end_headers()
		self.wfile.write( data )

	def do_GET( self ):
		p = self.path.split( "?" )[0]
		if p == "/api/models":
			data = json.dumps( models() ).encode()
			self.send_response( 200 )
			self.send_header( "Content-Type", "application/json" )
			self.send_header( "Content-Length", str( len( data ) ) )
			self.end_headers()
			self.wfile.write( data )
		elif p in ( "/", "/index.html" ):
			self.send_file( os.path.join( PAGE, "index.html" ) )
		elif p.startswith( "/viewer/" ):
			self.send_file( os.path.join( PAGE, p[len( "/viewer/" ):] ) )
		elif p.startswith( "/dkres/" ):
			self.send_file( os.path.join( DKRES, p[len( "/dkres/" ):] ) )
		elif p.startswith( "/af/" ) or p.startswith( "/def/" ):
			self.send_file( os.path.join( ROOT, p[1:] ) )
		else:
			self.send_error( 404 )


if __name__ == "__main__":
	port = int( sys.argv[1] ) if len( sys.argv ) > 1 else 8765
	print( "rig viewer: http://localhost:%d" % port )
	http.server.ThreadingHTTPServer( ( "127.0.0.1", port ), Handler ).serve_forever()
