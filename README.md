# What is this?

A data pipeline that converts Daikatana's assets for Spearmint, a Quake 3
Arena source port, and the menus, effects and scripts of the port.

# Layout

The code is spread over repositories checked out next to this one:

    spearmint/        engine                  (branch d3-physics)
    mint-arena/       game, cgame and menus   (branch cmake-build)
    bsp-sekai/        map converter           (branch daikatana-support)
    wal-tools/        texture converter       (branch palette-expansion)
    qwalk/            model converter         (branch master)
    pakextract/       pak unpacker            (branch cmake-build)
    dk-restoration/   this one: the dk script, menus, effects, shaders

Everything builds into `build/` here. `dkres/` holds Daikatana's data
(unpacked and converted in place), `out/maps` the converted maps, `out/home`
the game's home folder when you play, `out/test-home` the one tests use.

# How to use

Copy `dk.local.example` to `dk.local` and set the paths of this machine
(Quake 3 and Daikatana). Then:

    ./dk setup                  clone the repositories that are missing
    ./dk build                  build all of them (or: ./dk build mint-arena)
    ./dk extract paks           unpack Daikatana's paks into dkres/
    ./dk extract all            convert textures, skins, models, sounds,
                                menu art and loading screens
    ./dk convert                convert the maps (or: ./dk convert e2dm1)
    ./dk run                    play (or: ./dk run +devmap e2dm1)

For checking a change:

    ./dk test                   load every map, fail on errors, screenshot
                                each (out/shots/test.jpg has them all)
    ./dk shots e2dm1 before     screenshots from the spawn points, into
                                out/shots/before/
    ./dk status                 branch and state of every repository
    ./dk install [dir]          copy the mod into a Quake 3 folder

`./dk help` lists it all. Changes to a repository are committed and pushed
in that repository; nothing here pins their versions.
