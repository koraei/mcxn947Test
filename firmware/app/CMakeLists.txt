
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
            src/qa_stream.c
            src/runhours_journal.c
            inc/app_config.h
            inc/diagnostics.h
            inc/led_task.h
            inc/hello_service.h
            inc/update_service.h
            inc/mtls_socket.h
            inc/qa_stream.h
            inc/memory_layout.h
            inc/runhours_format.h
            inc/runhours_journal.h
            inc/flash_range_guard.h
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
             security
)

# LEAN_PROD_TEST: product USER_CONFIG overlay (allow-list prune). BASELINE omits this.
if(DEFINED LEAN_PROD AND LEAN_PROD)
    mcux_add_macro(
        CC "-DMBEDTLS_USER_CONFIG_FILE=\\\"mbedtls_product_user_config.h\\\""
    )
    message(STATUS "LEAN_PROD: MBEDTLS_USER_CONFIG_FILE=mbedtls_product_user_config.h")
    # Size build: -Os + GC (do not reduce TLS/lwIP buffers).
    mcux_add_armgcc_configuration(
        TARGETS release
        CC "-Os -ffunction-sections -fdata-sections"
        CX "-Os -ffunction-sections -fdata-sections"
        LD "-Wl,--gc-sections"
    )
endif()

# Build-only 512 KiB layout (no CMPA write). Pair with lean for size proof.
# Linker script swap happens after reconfig.cmake (below) so remove wins.
if(DEFINED APP_FLASH_LAYOUT_512K AND APP_FLASH_LAYOUT_512K)
    mcux_add_macro(CC "-DAPP_FLASH_LAYOUT_512K=1")
    message(STATUS "APP_FLASH_LAYOUT_512K=1 (build-only; CMPA remap unchanged until owner gate)")
endif()

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

# Production keeps 0x1B000. QA soak (APP_QA_STREAM) needs a larger newlib arena for
# a second mTLS session + FreeRTOS task stacks allocated via heap_3; pass -DQA_HEAP_SIZE=0x28000.
if(DEFINED QA_HEAP_SIZE)
    set(_APP_HEAP_SIZE ${QA_HEAP_SIZE})
else()
    set(_APP_HEAP_SIZE 0x1B000)
endif()
mcux_add_armgcc_configuration(
    LD "-Xlinker --defsym=__stack_size__=0x1000 -Xlinker --defsym=__heap_size__=${_APP_HEAP_SIZE}"
)

include(${SdkRootDirPath}/${board_root}/${board}/ota_examples/ota_mcuboot_server/enet/reconfig.cmake OPTIONAL)

# P3+: use NXP OTA/MCUboot slot linker (header at 0x400). For P2-only standalone
# bring-up without IFR MCUboot, temporarily include standalone_linker.cmake instead.
# include(${CMAKE_CURRENT_LIST_DIR}/standalone_linker.cmake)

# After SDK linker is registered: constrain to 512 KiB slot when requested.
if(DEFINED APP_FLASH_LAYOUT_512K AND APP_FLASH_LAYOUT_512K)
    mcux_remove_armgcc_linker_script(
        TARGETS debug release
        BASE_PATH ${SdkRootDirPath}
        LINKER ${board_root}/${board}/ota_examples/ota_linker/mcxn10_cm33_flash.ld
    )
    mcux_add_armgcc_linker_script(
        TARGETS debug release
        LINKER ${CMAKE_CURRENT_LIST_DIR}/linker/mcxn10_cm33_flash_512k.ld
    )
endif()

mcux_convert_binary(BINARY ${APPLICATION_BINARY_DIR}/${MCUX_SDK_PROJECT_NAME}.bin)
