cmake_minimum_required(VERSION 3.27)

project(DkRestoration)

#set_property(GLOBAL PROPERTY GLOBAL_DEPENDS_DEBUG_MODE 1)

set(DAIKATANA_DIR "/home/deck/Games/gog/daikatana/")
set(DAIKATANA_DATA_DIR "${DAIKATANA_DIR}data/")
set(DAIKATANA_RES_DIR "${CMAKE_SOURCE_DIR}/dkres/")
set(DAIKATANA_OUTDATA_DIR "${CMAKE_SOURCE_DIR}/basedk/")
set(OUTPUT_DIR "/home/deck/Games/gog/quake-iii-arena/")

set(EXTRACT_PAKS OFF)
set(PAKS "pak1.pak" "pak2.pak" "pak3.pak" "pak4.pak" "pak5.pak" "pak6.pak")

add_subdirectory("tools/pakextract")
add_subdirectory("tools/wal-tools")
add_subdirectory("tools/bsp-sekai")
add_subdirectory("tools/qwalk")
add_subdirectory("mint-dk")
set(COPYDIR "${DAIKATANA_RES_DIR}")
add_subdirectory("spearmint")

#add_custom_target(install_all)
#add_dependencies(install_all spearmint_x86_64)
#add_dependencies(install_all spearmint-renderer-opengl2_x86_64)
#add_dependencies(install_all mint-cgame_x86_64)
#add_dependencies(install_all mint-game_x86_64)
#add_dependencies(install_all pakextract)
#add_dependencies(install_all wal-export)
#add_dependencies(install_all bspsekai)
#add_dependencies(install_all qwalk_converter)

#install(TARGETS mint-cgame_x86_64 DESTINATION ${DAIKATANA_RES_DIR})
#install(TARGETS mint-cgame_x86_64 DESTINATION ${DAIKATANA_RES_DIR})

# #
# # unpack everything
# #

# add_custom_target(prepare)

# add_custom_target(unpack)

# add_custom_target(make-DAIKATANA_RES_DIR ALL
#     COMMAND ${CMAKE_COMMAND} -E make_directory ${DAIKATANA_RES_DIR})

# # setup targets for each pak file.
# # set dependencies so that later pak is extracted after the earlier ones
# foreach(pak ${PAKS})
#     list(FIND PAKS "${pak}" pak_index)
#     list(SUBLIST PAKS 0 "${pak_index}" depends_on_paks)
#     list(TRANSFORM depends_on_paks PREPEND "extract_")

#     set(source_pak "${DAIKATANA_DATA_DIR}${pak}")
#     add_custom_target("extract_${pak}" ALL DEPENDS "extract_${pak}" make-DAIKATANA_RES_DIR)
#     add_custom_command(TARGET "extract_${pak}" PRE_BUILD
#         COMMAND pakextract -dk -o ${DAIKATANA_RES_DIR} ${source_pak}
#         DEPENDS pakextract ${source_pak} "${depends_on_packs}"
#         COMMENT "Unpacking ${pak}"
#         VERBATIM)
#     foreach (other_pak_target ${depends_on_paks})
#         add_dependencies("extract_${pak}" "${other_pak_target}")
#     endforeach()

#     add_dependencies(unpack "extract_${pak}")
# endforeach()

# # TODO: use a separate staging dir. dkres should be the 'output'.
# # (out-of-tree build)

# # TODO: use https://stackoverflow.com/questions/42476765/copying-assets-directory-from-source-to-build-directory-in-cmake

# add_custom_target(copy_maps
#     COMMAND ${CMAKE_COMMAND} -E copy_directory_if_different ${DAIKATANA_DATA_DIR}maps ${DAIKATANA_RES_DIR}maps)
# add_dependencies(copy_maps unpack)
# add_dependencies(prepare copy_maps)

# add_custom_target(copy_models
#     COMMAND ${CMAKE_COMMAND} -E copy_directory_if_different ${DAIKATANA_DATA_DIR}models ${DAIKATANA_RES_DIR}models)
# add_dependencies(copy_models unpack)
# add_dependencies(prepare copy_models)

# add_custom_target(copy_music
#     COMMAND ${CMAKE_COMMAND} -E copy_directory_if_different ${DAIKATANA_DATA_DIR}music ${DAIKATANA_RES_DIR}music)
# add_dependencies(copy_music unpack)
# add_dependencies(prepare copy_music)

# add_custom_target(copy_sounds
#     COMMAND ${CMAKE_COMMAND} -E copy_directory_if_different ${DAIKATANA_DATA_DIR}sounds ${DAIKATANA_RES_DIR}sounds)
# add_dependencies(copy_sounds unpack)
# add_dependencies(prepare copy_sounds)

# #mv dkres/maps dkres/maps-dk

# #
# # actual transformation steps
# #

# # envs need renaming
# add_custom_target(xform_envs)

# file(GLOB envfiles ${DAIKATANA_RES_DIR}env/32bit/*.tga)
# list(FILTER envfiles EXCLUDE REGEX "^(.*) copy.tga$")
# foreach (env ${envfiles})
#     get_filename_component(env_file "${env}" NAME)
#     if ("${env_file}" MATCHES "^([^_]*)(bk|dn|ft|lf|rt|up).tga$")
#         set(newenv "${DAIKATANA_OUTDATA_DIR}env/32bit/${CMAKE_MATCH_1}_${CMAKE_MATCH_2}.tga")
#     else()
#         set(newenv "${DAIKATANA_OUTDATA_DIR}env/32bit/${env_file}")
#     endif()
#     #configure_file("${env}" "${newenv}" COPYONLY)
#     add_custom_target("${env_file}" ALL
#         DEPENDS "${env}")
#     add_custom_command(
#         OUTPUT "${env_file}"
#         COMMAND ${CMAKE_COMMAND} -E copy "${env}" "${newenv}"
#         DEPENDS "${env}")
#     add_dependencies("${env_file}" prepare)
#     add_dependencies(xform_envs "${env_file}")
# endforeach()

# function(wal2tga dir xform_target)
#     file(GLOB_RECURSE waltextures ${DAIKATANA_RES_DIR}${dir}/*.wal)
#     list(FILTER waltextures EXCLUDE REGEX "^.*/(d4_banner|colormap|e_swrocket|int_font|int_buttons|int_font_bright|w_testweapon|winnt256|dndeathbed|dndeathbed2|dndeathbedside|dndeathbedsd2).wal") # FIXME: this doesn't work
#     list(FILTER waltextures EXCLUDE REGEX "^.*/(dnsaloondoor2|sign1|sign2|sign3|carch|stngls2).wal")
#     list(FILTER waltextures EXCLUDE REGEX "^.*/(stne&rck).wal") # FIXME: escaping? breaks cmake -E copy

#     foreach (walfile ${waltextures})
#         get_filename_component(wal_just_file "${walfile}" NAME_WLE)

#         get_filename_component(PARENT_DIR "${walfile}" DIRECTORY)

#         string(REPLACE ".wal" ".tga" output_tgafile "${walfile}")

#         string(REPLACE "${DAIKATANA_RES_DIR}" "" relwalfile "${walfile}")
#         string(REPLACE ".wal" "" reltgafile "${relwalfile}")

#         string(MAKE_C_IDENTIFIER "${reltgafile}" target_reltgafile)

#         set(tgafile "${DAIKATANA_OUTDATA_DIR}${reltgafile}.tga")

#         add_custom_command(
#             OUTPUT "${output_tgafile}"
#             COMMAND wal-export "${walfile}" -mip 0 -o "${wal_just_file}" || (exit 0)
#             DEPENDS "${walfile}"
#         )
#         add_custom_command(
#             OUTPUT "${tgafile}"
#             COMMAND ${CMAKE_COMMAND} -E copy "${output_tgafile}" "${tgafile}"
#             DEPENDS "${output_tgafile}"
#         )

#         add_custom_target("${target_reltgafile}" ALL
#             DEPENDS prepare "${tgafile}")

#         add_dependencies(${xform_target} "${target_reltgafile}")
#     endforeach()
# endfunction()

# # transform textures in-place
# add_custom_target(xform_waltextures)
# wal2tga("textures" xform_waltextures)

# # transform skins in-place
# #add_custom_target(xform_skins)
# #wal2tga("skins" xform_skins)

# # TODO: pcx/bmp files

# # models
# add_custom_target(xform_models)
# file(GLOB_RECURSE dkmfiles ${DAIKATANA_RES_DIR}models/*.dkm)
# foreach (dkmfile ${dkmfiles})
#     string(REPLACE "${DAIKATANA_RES_DIR}" "" reldkmfile "${dkmfile}")
#     string(REPLACE ".dkm" ".md3" relmd3file "${reldkmfile}")

#     string(MAKE_C_IDENTIFIER "${relmd3file}" target_relmd3file)

#     set(md3file "${DAIKATANA_OUTDATA_DIR}${relmd3file}")
#     set(dkmfile_out "${DAIKATANA_OUTDATA_DIR}${reldkmfile}")

#     add_custom_target("${target_relmd3file}" ALL
#         DEPENDS "${md3file}")

#     # FIXME: core dump: /home/deck/Documents/proj/dk-restoration/build/tools/qwalk/qwalk_converter -force -i /home/deck/Documents/proj/dk-restoration/basedk/models/cinematic/c_gusagi_e4m6.dkm /home/deck/Documents/proj/dk-restoration/basedk/models/cinematic/c_gusagi_e4m6.md3
#     add_custom_command(
#         OUTPUT "${md3file}"
#         COMMAND ${CMAKE_COMMAND} -E copy "${dkmfile}" "${dkmfile_out}"
#         COMMAND echo copied
#         COMMAND qwalk_converter -force -i "${dkmfile_out}" "${md3file}"
#         COMMAND echo converted
#         COMMAND ${CMAKE_COMMAND} -E remove "${dkmfile_out}"
#         COMMAND echo deleted
#         WORKING_DIRECTORY "${DAIKATANA_OUTDATA_DIR}"
#         DEPENDS "${dkmfile}"
#     )
#     #add_dependencies("${target_relmd3file}" xform_skins)

#     add_dependencies(xform_models "${target_relmd3file}")
# endforeach()

# #build/tools/qwalk/qwalk_converter -i models/characters/hiro.dkm models/characters/hiro.md3
# #cd dkres
# #while IFS= read -r -d '' file; do
# #    # single filename is in $file
# #    echo $file
# #    rm "${file%.dkm}.md3"
# #    ../build/tools/qwalk/qwalk_converter -force -i "${file}" "${file%.dkm}.md3"
# #done < <(find models -type f -name '*.dkm' -print0)
# #cd ..

# # sounds
# # ffprobe -i sounds/global/e_lightningl.wav -show_streams -select_streams a:0
# # bits_per_sample=4
# #
# # even better:
# # ffprobe -i sounds/global/e_lightningl.wav -show_entries stream=bits_per_sample -select_streams a -of compact=p=0:nk=1 -v 0
# # the above gives you 4
# # you need to up it!

# # ffmpeg -i sounds/global/e_lightningl.wav -codec:a pcm_u8 -f wav sound.wav

# # sounds
# #cd dkres
# #while IFS= read -r -d '' file; do
# #    # single filename is in $file
# #    if ffprobe -i $file -show_entries stream=bits_per_sample -select_streams a -of compact=p=0:nk=1 -v 0 | grep -q '4'; then
# #        echo $file
# #        mv $file "${file}.orig"
# #        ffmpeg -i "${file}.orig" -codec:a pcm_u8 -f wav -y "${file}" 2> /dev/null
# #        # TODO: remove the .orig file
# #    fi
# #done < <(find sounds -type f -name '*.wav' -print0)
# #cd ..
# add_custom_target(xform_sounds
#     COMMAND ${CMAKE_COMMAND} -E copy_directory_if_different ${DAIKATANA_RES_DIR}sounds ${DAIKATANA_OUTDATA_DIR}sounds)
# add_dependencies(xform_sounds prepare)

# # maps
# #build/tools/bsp-sekai/bspsekai none dkres/maps-dk/e1dm1.bsp quake3 dkres/maps/e1dm1.bsp

# add_custom_target(xform)
# add_dependencies(xform xform_envs)
# add_dependencies(xform xform_waltextures)
# #add_dependencies(xform xform_skins)
# add_dependencies(xform xform_models)

# add_custom_target(install_xformed
#     COMMAND ${CMAKE_COMMAND} -E copy ${DAIKATANA_OUTDATA_DIR} ${OUTPUT_DIR})
# add_dependencies(install_xformed xform)

# #install(DIRECTORY ${DAIKATANA_OUTDATA_DIR} DESTINATION ${OUTPUT_DIR})

# #add_custom_target(graphviz ALL
# #                  "${CMAKE_COMMAND}" "--graphviz=foo" .
# #                  WORKING_DIRECTORY "${CMAKE_BINARY_DIR}")   
