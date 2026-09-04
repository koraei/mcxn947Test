# FRDM-MCXN947 IFR MCUboot — 512 KiB A/B (LIM=15)
# Board port lives at firmware/mcuboot_ifr_512k/board_port and is junctioned into the
# SDK tree as mcuboot_opensource_512k for NXP CMake path rules.

cmake_minimum_required(VERSION 3.22.0)

include(${SdkRootDirPath}/cmake/extension/mcux.cmake)

project(mcuboot_opensource LANGUAGES C CXX ASM PROJECT_BOARD_PORT_PATH ${board_root}/${board}/ota_examples/mcuboot_opensource_512k)

include(${SdkRootDirPath}/CMakeLists.txt)

set(MCUBOOT_512K_PORT ${SdkRootDirPath}/${board_root}/${board}/ota_examples/mcuboot_opensource_512k)

mcux_add_include(
    BASE_PATH ${MCUBOOT_512K_PORT}
    INCLUDES
        .
        flash_partitioning
        ${multicore_foldername}
)

mcux_add_source(
    BASE_PATH ${MCUBOOT_512K_PORT}
    SOURCES
        main.c
        sblconfig.h
        flash_partitioning/flash_partitioning.h
        flash_partitioning/flash_partitioning.c
)

mcux_add_macro(
    CC "-DPRINTF_ADVANCED_ENABLE=1\
       -DSHELL_PRINT_COPYRIGHT=0\
       -DAPP_FLASH_LAYOUT_512K=1"
)

mcux_add_iar_configuration(
    CC "--diag_suppress=Pe257,Pa039"
)
mcux_add_iar_configuration(
    CC "--diag_suppress=Pe111,Pe177,Pe550"
)
mcux_add_armgcc_configuration(
    CC "-Wno-unused-variable\
        -Wno-unused-but-set-variable\
        -Wno-unused-function\
        -Wno-maybe-uninitialized"
)

mcux_remove_iar_configuration(
    CC "--use_c++_inline"
)

mcux_remove_mdk_configuration(
    TARGETS flexspi_nor_release flash_release release
    CC "-Oz"
)

mcux_add_mdk_configuration(
    TARGETS flexspi_nor_release flash_release release
    CC "-Os"
)

include(${MCUBOOT_512K_PORT}/${multicore_foldername}/reconfig.cmake OPTIONAL)

mcux_convert_binary(BINARY ${APPLICATION_BINARY_DIR}/${MCUX_SDK_PROJECT_NAME}.bin)
