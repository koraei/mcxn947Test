# P2 standalone boot: OTA-compatible memory map but MCUBOOT_HEADER_SIZE=0 so VTOR/vectors are at 0x0.

mcux_remove_armgcc_linker_script(
    BASE_PATH ${SdkRootDirPath}
    TARGETS debug release
    LINKER ${board_root}/${board}/ota_examples/ota_linker/mcxn10_cm33_flash.ld
)

mcux_remove_armgcc_linker_script(
    BASE_PATH ${SdkRootDirPath}
    TARGETS debug release
    LINKER ${board_root}/${board}/ota_examples/mcuboot_opensource/linker/mcxn10_cm33_flash.ld
)

mcux_remove_armgcc_linker_script(
    BASE_PATH ${SdkRootDirPath}
    TARGETS debug release
    LINKER ${device_root}/${soc_portfolio}/${soc_series}/${device}/gcc/${CONFIG_MCUX_TOOLCHAIN_LINKER_DEVICE_PREFIX}_flash.ld
)

mcux_add_armgcc_linker_script(
    TARGETS debug release
    LINKER ${CMAKE_CURRENT_LIST_DIR}/linker/mcxn10_cm33_flash_standalone.ld
)
