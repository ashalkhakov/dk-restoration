#!/usr/bin/env python3
"""vsc_frames.py -- Daikatana's monster sound tables (sounds/<episode>/m_*.vsc)
as Doom 3 frame commands

	python3 tools/vsc/vsc_frames.py <dkres> <out.def>

A .vsc is a CSV with each byte XORed with 0x96 (after its "CVSC"): a row an
animation, with two sounds and the frames they play on (from 1), whether it
loops, its attack frames ("attack seq 1", "attack seq 2"), its speed, how
often an idle one is chosen ("anim %") and how often its second sound plays
("sound2 %"). For each monster below it writes

	entityDef model_<name>_frames {
		"frame ataka 8"		"sound sounds/e1/m_croxataka.wav"
		"frame ataka 12"	"call attackFrame"
	}

which the model def of that name takes its frame commands from (bg_model.c),
the md3's or the rigged one's: the cgame plays the sounds as the animation
gets there, the game calls the monster script's attackFrame() at the attack
frames (the bite, the shot). Sounds played only by chance (an idle's) are
left to the scripts.
"""

import csv
import io
import os
import sys

# model def (model_<name>) <- its sound table
MONSTERS = {
    'froginator': 'e1/m_frog', 'slaughterskeet': 'e1/m_skeeter', 'thunderskeet': 'e1/m_thunderskeet',
    'crox': 'e1/m_crox', 'protopod': 'e1/m_protopod', 'cambot': 'e1/m_cambot', 'rockgat': 'e1/m_rockgat',
    'skinnyworker': 'e1/m_mwskny', 'fatworker': 'e1/m_mwfaty', 'mishimaguard': 'e1/m_mwguard',
    'surgeon': 'e1/m_mwsurgeon', 'cryotech': 'e1/m_cryotech', 'prisoner': 'e1/m_priza', 'prisonerb': 'e1/m_prizb',
    'battleboar': 'e1/m_bboar', 'deathsphere': 'e1/m_deathsphere', 'dopefish': 'e1/m_dopefish',
    'inmater': 'e1/m_inmater', 'lasergat': 'e1/m_lasergat', 'psyclaw': 'e1/m_psyclaw',
    'ragemaster': 'e1/m_ragemaster', 'sludgeminion': 'e1/m_sludgeminion', 'vermin': 'e1/m_vermin',
}


def read_vsc(path):
    data = open(path, 'rb').read()
    if data[:4] != b'CVSC':
        raise ValueError('%s is not a sound table' % path)
    text = bytes(b ^ 0x96 for b in data[4:]).decode('latin1')
    return list(csv.reader(io.StringIO(text)))


def frame_commands(rows, dkres):
    """[(anim, frame from 0, command)]"""
    out = []
    head = [h.strip().lower() for h in rows[0]] if rows else []

    def col(row, name):
        i = head.index(name) if name in head else -1
        return row[i].strip() if 0 <= i < len(row) else ''

    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        anim = row[0].strip()
        chance = col(row, 'anim %') != ''		# an idle's: the scripts choose it
        for snd, frm, pct in (('sound1', 'frame1', None), ('sound2', 'frame2', 'sound2 %')):
            sound, frame = col(row, snd), col(row, frm)
            if not sound or not frame.isdigit() or chance or (pct and col(row, pct)):
                continue
            path = 'sounds/' + sound.replace('\\', '/')
            if os.path.exists(os.path.join(dkres, path)):
                out.append((anim, int(frame) - 1, 'sound ' + path))
        for seq in ('attack seq 1', 'attack seq 2', 'attack seq ', 'attack seq2'):
            frame = col(row, seq)
            if frame.isdigit():
                out.append((anim, int(frame) - 1, 'call attackFrame'))
    return sorted(set(out))


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    dkres, outPath = sys.argv[1], sys.argv[2]
    lines = ['// made by tools/vsc/vsc_frames.py from Daikatana\'s monster sound tables: edit the converter, not this', '']
    for name, table in sorted(MONSTERS.items()):
        path = os.path.join(dkres, 'sounds', table + '.vsc')
        if not os.path.exists(path):
            continue
        cmds = frame_commands(read_vsc(path), dkres)
        if not cmds:
            continue
        # one key a frame, its commands joined by ";"
        frames = {}
        for anim, frame, cmd in cmds:
            frames.setdefault((anim, frame), []).append(cmd)
        lines.append('entityDef model_%s_frames {' % name)
        for (anim, frame), c in sorted(frames.items()):
            lines.append('\t"frame %s %d"\t"%s"' % (anim, frame, '; '.join(c)))
        lines.append('}')
        lines.append('')
    os.makedirs(os.path.dirname(outPath) or '.', exist_ok=True)
    open(outPath, 'w').write('\n'.join(lines))


if __name__ == '__main__':
    main()
