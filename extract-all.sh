#!/bin/bash

EXTRACT_PAKS=0
BUILD_ENVS=0
BUILD_TEXTURES=0
BUILD_SKINS=0
BUILD_MODELS=0
BUILD_SOUNDS=0
BUILD_MAPS=1
INSTALL_FILES=1
INSTALL_OUTDIR=/home/deck/Games/gog/quake-iii-arena

mkdir -p ./dkres/

if [ "$EXTRACT_PAKS" -gt 0 ]; then
    build/tools/pakextract/pakextract -dk -o ./dkres ~/Games/gog/daikatana/data/pak1.pak
    build/tools/pakextract/pakextract -dk -o ./dkres ~/Games/gog/daikatana/data/pak2.pak
    build/tools/pakextract/pakextract -dk -o ./dkres ~/Games/gog/daikatana/data/pak3.pak
    build/tools/pakextract/pakextract -dk -o ./dkres ~/Games/gog/daikatana/data/pak4.pak
    build/tools/pakextract/pakextract -dk -o ./dkres ~/Games/gog/daikatana/data/pak5.pak
    build/tools/pakextract/pakextract -dk -o ./dkres ~/Games/gog/daikatana/data/pak6.pak

    cp -R ~/Games/gog/daikatana/data/maps ./dkres/
    cp -R ~/Games/gog/daikatana/data/models ./dkres/
    cp -R ~/Games/gog/daikatana/data/music ./dkres/
    cp -R ~/Games/gog/daikatana/data/sounds ./dkres/
fi

# rename envs
if [ "$BUILD_ENVS" -gt 0 ]; then
    while IFS= read -r -d '' file; do
        if [[ "${file}" =~ ^(.*)(bk|dn|ft|lf|rt|up).tga$ ]]; 
        then
            mv $file "${BASH_REMATCH[1]}_${BASH_REMATCH[2]}.tga"
        fi
    done < <(find dkres/env/32bit -type f -name '*.tga' -print0)
fi

# transform textures in-place
if [ "$BUILD_TEXTURES" -gt 0 ]; then
    while IFS= read -r -d '' file; do
        # single filename is in $file
        build/tools/wal-tools/wal-export "${file}" -mip 0 -o "${file%.wal}"
        #rm "${file}"
    done < <(find dkres/textures -type f -name '*.wal' -print0)
fi

# transform skins in-place
if [ "$BUILD_SKINS" -gt 0 ]; then
    while IFS= read -r -d '' file; do
        # single filename is in $file
        build/tools/wal-tools/wal-export "${file}" -mip 0 -o "${file%.wal}"
        #rm "${file}"
    done < <(find dkres/skins -type f -name '*.wal' -print0)
fi

# TODO: pcx/bmp files

# models
#build/tools/qwalk/qwalk_converter -i models/characters/hiro.dkm models/characters/hiro.md3
if [ "$BUILD_MODELS" -gt 0 ]; then
    cd dkres
    while IFS= read -r -d '' file; do
        # single filename is in $file
        echo $file
        rm "${file%.dkm}.md3"
        ../build/tools/qwalk/qwalk_converter -force -i "${file}" "${file%.dkm}.md3"
    done < <(find models -type f -name '*.dkm' -print0)
    cd ..
fi

# sounds
# ffprobe -i sounds/global/e_lightningl.wav -show_streams -select_streams a:0
# bits_per_sample=4
#
# even better:
# ffprobe -i sounds/global/e_lightningl.wav -show_entries stream=bits_per_sample -select_streams a -of compact=p=0:nk=1 -v 0
# the above gives you 4
# you need to up it!

# ffmpeg -i sounds/global/e_lightningl.wav -codec:a pcm_u8 -f wav sound.wav

# sounds
if [ "$BUILD_SOUNDS" -gt 0 ]; then
    cd dkres
    while IFS= read -r -d '' file; do
        # single filename is in $file
        if ffprobe -i $file -show_entries stream=bits_per_sample -select_streams a -of compact=p=0:nk=1 -v 0 | grep -q '4'; then
            echo $file
            mv $file "${file}.orig"
            ffmpeg -i "${file}.orig" -codec:a pcm_u8 -f wav -y "${file}" 2> /dev/null
            # TODO: remove the .orig file
        fi
    done < <(find sounds -type f -name '*.wav' -print0)
    cd ..
fi

# maps
if [ "$BUILD_MAPS" -gt 0 ]; then
    cd dkres
    mv maps maps-dk
    mkdir -p scripts
    mkdir -p maps
    ../build/tools/bsp-sekai/bspsekai none maps-dk/e1m1a.bsp quake3 maps/e1m1a.bsp
    cd ..
fi

if [ "$INSTALL_FILES" -gt 0 ]; then
    cp -f mint/* dkres/
    #cp -fR ./dkres "INSTALL_OUTDIR"
    rsync -a --delete ./dkres "$INSTALL_OUTDIR"
fi
