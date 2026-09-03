# M0 wrapper: NXP lwip_httpssrv_mbedTLS_freertos sources unchanged.
# Lab-only deltas: static IP 192.168.2.90 and IFR-MCUboot OTA linker (ROM secure boot).

cmake_minimum_required(VERSION 3.22.0)

include(${SdkRootDirPath}/cmake/extension/mcux.cmake)

project(m0_httpssrv_mbedtls LANGUAGES C CXX ASM PROJECT_BOARD_PORT_PATH ${board_root}/${board}/lwip_examples/lwip_httpssrv_mbedTLS/freertos)

include(${SdkRootDirPath}/CMakeLists.txt)
include(${SdkRootDirPath}/examples/lwip_examples/httpsrv_common/fs_data/CMakeLists.txt)
include(${SdkRootDirPath}/examples/lwip_examples/httpsrv_common/fs_data/webpage/CMakeLists.txt)

mcux_add_source(
    BASE_PATH ${SdkRootDirPath}
    SOURCES examples/lwip_examples/lwip_httpssrv_mbedTLS/freertos/lwip_httpssrv_mbedTLS_freertos.c
)

mcux_add_macro(
    CC "-DUSE_RTOS=1\
       -DPRINTF_ADVANCED_ENABLE=1\
       -DconfigIP_ADDR0=192\
       -DconfigIP_ADDR1=168\
       -DconfigIP_ADDR2=2\
       -DconfigIP_ADDR3=90\
       -DconfigNET_MASK0=255\
       -DconfigNET_MASK1=255\
       -DconfigNET_MASK2=255\
       -DconfigNET_MASK3=0\
       -DconfigGW_ADDR0=192\
       -DconfigGW_ADDR1=168\
       -DconfigGW_ADDR2=2\
       -DconfigGW_ADDR3=24"
)

mcux_add_macro(
    TOOLCHAINS armgcc
    CC "-D_POSIX_SOURCE"
)

mcux_add_linker_symbol(
    SYMBOLS "__stack_size__=1000\
             __heap_size__=110000"
)

include(${SdkRootDirPath}/${board_root}/${board}/lwip_examples/lwip_httpssrv_mbedTLS/freertos/reconfig.cmake OPTIONAL)

# Frozen ROM+IFR MCUboot: relink NXP example with OTA application map (vectors @ 0x400).
mcux_remove_armgcc_linker_script(
    BASE_PATH ${SdkRootDirPath}
    TARGETS debug release
    LINKER ${device_root}/${soc_portfolio}/${soc_series}/${device}/gcc/${CONFIG_MCUX_TOOLCHAIN_LINKER_DEVICE_PREFIX}_flash.ld
)
mcux_add_armgcc_linker_script(
    TARGETS debug release
    LINKER ${CMAKE_CURRENT_LIST_DIR}/linker/mcxn10_cm33_flash_m0.ld
)

mcux_convert_binary(BINARY ${APPLICATION_BINARY_DIR}/${MCUX_SDK_PROJECT_NAME}.bin)
