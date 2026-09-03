
# Copyright 2026 NXP / product
#
# SPDX-License-Identifier: BSD-3-Clause

cmake_minimum_required(VERSION 3.22.0)

include(${SdkRootDirPath}/cmake/extension/mcux.cmake)

project(mcxn947_secure_ota LANGUAGES C CXX ASM PROJECT_BOARD_PORT_PATH ${board_root}/${board}/ota_examples/ota_mcuboot_server/enet)

include(${SdkRootDirPath}/CMakeLists.txt)

mcux_add_source(
    SOURCES enet/network_cfg.h
            enet/app.h
            frdmmcxn947/FreeRTOSConfigBoard.h
            network_enet/init_enet.c
            network_enet/lwipopts.h
            ota_mcuboot_server/FreeRTOSConfig.h
            src/main.c
            src/led_task.c
            src/hello_service.c
            src/update_service.c
            src/diagnostics.c
            src/mtls_socket.c
            inc/app_config.h
            inc/diagnostics.h
            inc/led_task.h
            inc/hello_service.h
            inc/update_service.h
            inc/mtls_socket.h
)

mcux_add_include(
    INCLUDES enet
             flash_partitioning
             frdmmcxn947
             mcuboot_opensource
             network_enet
             ota_mcuboot_server
             inc
             src
)

mcux_add_source(
    SOURCES flash_partitioning/flash_partitioning.c
            flash_partitioning/flash_partitioning.h
            mcuboot_opensource/sblconfig.h
)

mcux_add_armgcc_configuration(
    TARGETS debug
    CC "-g1"
    CX "-g1"
)

mcux_add_mcux_configuration(
    TARGETS debug
    CC "-Og"
    CX "-g3"
)

# Default product macros come from tools/mcxn.py EXTRA_CFLAGS (V1/V2).
mcux_add_macro(
    CC "-DMCUBOOT_APPLICATION=1\
       -DMCUBOOT_OTA_SB3_SUPPORT=1\
       -DUSE_RTOS=1\
       -DPRINTF_ADVANCED_ENABLE=1\
       -DMBEDTLS_THREADING_C\
       -DMBEDTLS_THREADING_ALT"
)

mcux_add_source(
    BASE_PATH C:/mcxn-secrets/mtls/generated
    SOURCES mtls_creds.c
)

# NXP SB3 ROM path (same sources as ota_mcuboot_basic board reconfig).
mcux_add_source(
    BASE_PATH ${SdkRootDirPath}
    SOURCES examples/ota_examples/_common/sb3_api/sb3_api.h
            examples/ota_examples/_common/sb3_api/sb3_api_mcxn10.c
)

mcux_add_include(
    BASE_PATH ${SdkRootDirPath}
    INCLUDES examples/ota_examples/_common/sb3_api
)

mcux_add_macro(
    TOOLCHAINS armgcc
    CC "-D_POSIX_SOURCE"
)

mcux_remove_armgcc_configuration(
    TARGETS debug
    CC "-g"
    CX "-g"
)

mcux_add_iar_configuration(
    LD "--config_def=__stack_size__=0x1000 --config_def=__heap_size__=0x10000"
)

mcux_add_mdk_configuration(
    LD "--predefine=\"-D__stack_size__=0x1000\" --predefine=\"-D__heap_size__=0x10000\""
)

mcux_add_armgcc_configuration(
    LD "-Xlinker --defsym=__stack_size__=0x1000 -Xlinker --defsym=__heap_size__=0x1B000"
)

include(${SdkRootDirPath}/${board_root}/${board}/ota_examples/ota_mcuboot_server/enet/reconfig.cmake OPTIONAL)

# P3+: use NXP OTA/MCUboot slot linker (header at 0x400). For P2-only standalone
# bring-up without IFR MCUboot, temporarily include standalone_linker.cmake instead.
# include(${CMAKE_CURRENT_LIST_DIR}/standalone_linker.cmake)

mcux_convert_binary(BINARY ${APPLICATION_BINARY_DIR}/${MCUX_SDK_PROJECT_NAME}.bin)
