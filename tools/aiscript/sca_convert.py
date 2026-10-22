#!/usr/bin/env python3
"""sca_convert.py -- Daikatana's action scripts (cin/aiscripts/<map>.sca,
its action.cpp) as Doom 3 scripts, one file a map

	python3 tools/aiscript/sca_convert.py <dkres> <out>

writes <out>/<map>.script for each <map>.sca: each of its scripts a function

	void ai_<name>( entity actor )

(the name in lower case: Daikatana looks them up so), its actions calls of
script/ai/ai_actions.script, and its Level_start ai_level_start(). The game
compiles <map>'s with the map's script (ai/maps/<map>.script) and starts a
function by name: a trigger_script's "aiscript", a monster_path_corner's
when a monster gets there, a monster's own as it spawns (g_aiscript.c).

A script's header may name who acts ("script Skeet1Exit SkeetAttack"): its
actions go to that entity (a "uniqueid", our targetname) when what started it
gave none. The actions:

	animate( anim [, times] )		the actor plays it, standing
	face_angle( pitch, yaw, roll )	turns to the yaw
	set_moving_animation( anim )	what it moves with on its paths
	set_state( who, state [, arg] )	ignore_player, aggressive, pathfollow <corner>
	send_message( who, script )		runs a script with who acting (and send_urgent_message)
	call( script )					runs a script, the same actor, to its end
	remove( name )					it's gone
	sound( file ), stream_sound( file )	the actor's sound, a voice everyone hears
	spawn( class, name, x, y, z, yaw [, ...] )
	use( name )						uses it, as a trigger
	print( text )					to the console

others are kept as comments.
"""

import os
import re
import sys

ACTION_RE = re.compile(r'(\w+)\s*\(([^)]*)\)\s*;')


def strip_comments(text):
    return re.sub(r'//[^\n]*', '', text)


def parse(text):
    """[(name, owner or None, [(action, [args])])]"""
    text = strip_comments(text)
    scripts = []
    pos = 0
    header = re.compile(r'(?:script\s+(\w+)(?:\s+(\w+))?|(Level_start))\s*\{', re.I)
    while True:
        m = header.search(text, pos)
        if not m:
            break
        end = text.index('}', m.end())
        body = text[m.end():end]
        name = m.group(1) or 'level_start'
        owner = m.group(2)
        actions = [(a.lower(), [x.strip() for x in args.split(',')] if args.strip() else [])
                   for a, args in ACTION_RE.findall(body)]
        scripts.append((name, owner, actions))
        pos = end + 1
    return scripts


def q(s):
    return '"' + s.replace('"', '') + '"'


def convert_action(action, args, functions):
    """a line of script for an action"""
    if action == 'animate' and args:
        times = args[1] if len(args) > 1 else '1'
        return 'ai_animate( actor, %s, %s );' % (q(args[0]), times)
    if action == 'face_angle' and len(args) >= 2:
        return 'ai_faceAngle( actor, %s );' % args[1]
    if action == 'set_moving_animation' and args:
        return 'ai_setMovingAnimation( actor, %s );' % q(args[0])
    if action == 'set_state' and len(args) >= 2:
        return 'ai_setState( %s, %s, %s );' % (q(args[0]), q(args[1].lower()), q(args[2] if len(args) > 2 else ''))
    if action in ('send_message', 'send_urgent_message') and len(args) >= 2:
        func = 'ai_' + args[1].lower()
        if func in functions:
            return 'thread %s( sys.getEntity( %s ) );' % (func, q(args[0]))
        return '// send_message( %s ): no script %s' % (', '.join(args), args[1])
    if action == 'spawn' and len(args) >= 6:
        return 'ai_spawn( %s, %s, \'%s %s %s\', %s );' % (q(args[0]), q(args[1]), args[2], args[3], args[4], args[5])
    if action == 'use' and args:
        return 'ai_use( %s );' % q(args[0])
    if action == 'call' and args:
        func = 'ai_' + args[0].lower()
        if func in functions:
            return '%s( actor );' % func
        return '// call( %s ): no such script' % args[0]
    if action == 'remove' and args:
        return 'ai_remove( %s );' % q(args[0])
    if action == 'sound' and args:
        return 'ai_sound( actor, %s );' % q('sounds/' + args[0])
    if action == 'stream_sound' and args:
        return 'sys.startGlobalSound( %s );' % q('sounds/' + args[0])
    if action == 'print' and args:
        return 'sys.println( %s );' % q(', '.join(args))
    return '// not done yet: %s( %s )' % (action, ', '.join(args))


def convert(path, mapname):
    scripts = parse(open(path, encoding='latin1').read())
    functions = {'ai_' + name.lower() for name, _, _ in scripts}
    out = ['// ai/maps/%s.script -- Daikatana\'s action scripts of %s (cin/aiscripts/%s.sca),' % (mapname, mapname, mapname),
           '// made by tools/aiscript/sca_convert.py: edit the converter, not this', '']
    # declared first: they call one another
    for name, _, _ in scripts:
        out.append('void ai_%s( entity actor );' % name.lower())
    out.append('')
    for name, owner, actions in scripts:
        out.append('void ai_%s( entity actor ) {' % name.lower())
        if owner:
            out.append('\tactor = ai_actor( actor, %s );' % q(owner))
        for action, args in actions:
            out.append('\t' + convert_action(action, args, functions))
        out.append('}')
        out.append('')
    return '\n'.join(out)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src = os.path.join(sys.argv[1], 'cin', 'aiscripts')
    os.makedirs(sys.argv[2], exist_ok=True)
    for f in sorted(os.listdir(src)) if os.path.isdir(src) else []:
        if not f.lower().endswith('.sca'):
            continue
        mapname = f[:-4].lower()
        with open(os.path.join(sys.argv[2], mapname + '.script'), 'w') as o:
            o.write(convert(os.path.join(src, f), mapname))


if __name__ == '__main__':
    main()
