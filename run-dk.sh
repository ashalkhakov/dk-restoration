#!/bin/zsh
# Runs the converted Daikatana in Spearmint, straight from the working trees.
#
# Builds the mod folder out/home/dkres out of links to the converted data
# (dkres/, out/maps), the menus, effects and scripts of this repository and
# the mint-arena game modules, then starts the game in it.
#
#   ./run-dk.sh                     main menu
#   ./run-dk.sh +devmap e2dm1       straight into a map
#
# Paths can be changed with these variables:
#   Q3DIR      Quake III Arena install (for baseq3 fallbacks)
#   SPEARMINT  Spearmint build folder with the engine
#   MINT       mint-arena build folder built with -DUSE_SCRIPTED_UI=ON
#   RENDERER   opengl2 (default) or opengl1

set -e

ROOT=${0:A:h}
PROJECTS=${ROOT:h}
Q3DIR=${Q3DIR:-/Volumes/ExtraSSD/games/quake-iii-arena}
SPEARMINT=${SPEARMINT:-$PROJECTS/spearmint/build}
MINT=${MINT:-$PROJECTS/mint-arena/build-dk}

HOMEDIR=$ROOT/out/home
MOD=$HOMEDIR/dkres

mkdir -p $MOD/ui $MOD/scripts

# converted game data
for dir in textures env pics sounds models skins fonts music levelshots; do
	ln -sfn $ROOT/dkres/$dir $MOD/$dir
done
ln -sfn $ROOT/out/maps $MOD/maps
ln -sfn $ROOT/effects $MOD/effects
ln -sfn $ROOT/gameinfo.txt $MOD/gameinfo.txt

# menus: the scripts of this repository and the art made from Daikatana's
for f in $ROOT/ui/*; do
	ln -sfn $f $MOD/ui/${f:t}
done
ln -sfn $ROOT/dkres/ui/assets $MOD/ui/assets

# shaders made for each map, and the ones of this repository
for f in $ROOT/dkres/scripts/*_gen.shader(N) $ROOT/scripts/*.shader(N) $ROOT/scripts/arenas.txt; do
	ln -sfn $f $MOD/scripts/${f:t}
done

# game settings and default keys
cp -f $ROOT/mint/* $MOD/

# game modules; replace rather than overwrite, macOS refuses changed signed libraries
for lib in $MINT/*.dylib(N) $MINT/*.so(N) $MINT/*.dll(N); do
	rm -f $MOD/${lib:t}
	cp $lib $MOD/
done

# a crash leaves this behind and the next start asks about it
rm -f $HOMEDIR/*.pid(N) $MOD/*.pid(N)

ENGINE=$(ls $SPEARMINT/spearmint_* 2>/dev/null | grep -v "\.dylib$\|ded" | head -1)
if [[ -z $ENGINE ]]; then
	echo "no Spearmint engine in $SPEARMINT" >&2
	exit 1
fi

cd ${ENGINE:h}
exec $ENGINE \
	+set fs_basepath $Q3DIR \
	+set fs_homepath $HOMEDIR \
	+set fs_game dkres \
	+set vm_game 0 \
	+set vm_cgame 0 \
	+set sv_pure 0 \
	+set fs_pakWarningDialog 0 \
	+set com_renderer ${RENDERER:-opengl2} \
	"$@"
