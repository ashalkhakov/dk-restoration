#!/usr/bin/env python3
"""The rig viewer's server (./dk viewer): the page (tools/rig/viewer), the
game data it shows (dkres: the IQMs, the MD3s they were made from, the
skins) and the ragdolls (af/), on this machine only.

  serve.py [port]

GET /api/status?def=<model def> says, for each of its rig's animations,
whether it's validated (tools/rig/rigcheck.py, tools/rig/validated.json):
valid, broken, changed since, or new; POST /api/validate { "def", "anim",
"verdict": "valid" | "broken", "note" } records a verdict on it as it is now
(Daikatana's frames, to score it by, loaded when its status is asked and
kept while the files stay as they were).

POST /api/save?name=<file> saves what the page sends to out/rigcheck/<file>
(its capture: a picture of each model, its fit numbers).

/api/models lists the rigged models: every def whose "mesh" is an IQM
autorig made (def/*.def), with the MD3 it was made from (the def's first
line says), its ragdoll (af/<name>.af) and what --root-out took out of its
animations (<iqm>.json).
"""
import http.server
import json
import os
import re
import sys
import threading
import urllib.parse

sys.path.insert( 0, os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), ".." ) )
import rigcheck  # noqa: E402

ROOT = os.path.normpath( os.path.join( os.path.dirname( os.path.abspath( __file__ ) ), "..", "..", ".." ) )
PAGE = os.path.join( ROOT, "tools", "rig", "viewer" )
DKRES = os.path.join( ROOT, "dkres" )
SHOTS = os.path.join( ROOT, "out", "rigcheck" )	# what the page's capture saves (POST /api/save?name=)


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
		af = afNew = None
		if ragdoll:
			for cand in ( ragdoll.group( 1 ) + ".af", ):
				if os.path.exists( os.path.join( ROOT, "af", cand ) ):
					af = "af/" + cand
				# the rig's regenerated one, where it differs from the kept
				# one (af/ is the authority: validated here before it's put there)
				new = os.path.join( ROOT, "out", "rig", "af", cand )
				if os.path.exists( new ) and ( not af or open( new ).read() != open( os.path.join( ROOT, af ) ).read() ):
					afNew = "out/rig/af/" + cand
		root = mesh.group( 1 )[:-4] + ".json"		# what autorig --root-out took out
		out.append( {
			"root": root if os.path.exists( os.path.join( DKRES, root ) ) else None,
			"def": name.group( 1 ) if name else fn[:-4],
			"file": "def/" + fn,
			"iqm": mesh.group( 1 ),
			"md3": src.group( 1 ) if src else None,
			"af": af,
			"afNew": afNew,
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

	def send_json( self, obj, code = 200 ):
		data = json.dumps( obj ).encode()
		self.send_response( code )
		self.send_header( "Content-Type", "application/json" )
		self.send_header( "Content-Length", str( len( data ) ) )
		self.end_headers()
		self.wfile.write( data )

	def do_POST( self ):
		p, _, q = self.path.partition( "?" )
		if p == "/api/validate":
			try:
				body = json.loads( self.rfile.read( int( self.headers.get( "Content-Length", 0 ) ) ) )
				entry = rigcheck.validate( body["def"], body["anim"], body["verdict"], body.get( "note", "" ) )
				self.send_json( dict( entry, state = entry["verdict"] ) )
			except ( ValueError, KeyError ) as e:
				self.send_json( { "error": str( e ) }, 400 )
			return
		name = q[len( "name=" ):] if q.startswith( "name=" ) else ""
		if p != "/api/save" or not re.match( r"^[A-Za-z0-9_.-]+$", name ) or name.startswith( "." ):
			self.send_error( 400 )
			return
		data = self.rfile.read( int( self.headers.get( "Content-Length", 0 ) ) )
		os.makedirs( SHOTS, exist_ok = True )
		open( os.path.join( SHOTS, name ), "wb" ).write( data )
		self.send_response( 204 )
		self.end_headers()

	def do_GET( self ):
		p = self.path.split( "?" )[0]
		if p == "/api/status":
			q = urllib.parse.parse_qs( self.path.partition( "?" )[2] )
			defName = q.get( "def", [ "" ] )[0]
			self.send_json( rigcheck.status( defName ) )
			# Daikatana's frames for the verdicts to come, loaded meanwhile
			info = rigcheck.model_info( defName )
			if info:
				threading.Thread( target = rigcheck.load_source, args = ( info, ), daemon = True ).start()
		elif p == "/api/models":
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
		elif p.startswith( "/af/" ) or p.startswith( "/def/" ) or p.startswith( "/out/rig/" ):
			self.send_file( os.path.join( ROOT, p[1:] ) )
		else:
			self.send_error( 404 )


if __name__ == "__main__":
	port = int( sys.argv[1] ) if len( sys.argv ) > 1 else 8765
	print( "rig viewer: http://localhost:%d" % port )
	http.server.ThreadingHTTPServer( ( "127.0.0.1", port ), Handler ).serve_forever()
