# ADR-002 — NXP default IFR MCUboot / DIRECT_XIP flash remap

## Decision
Preserve NXP IFR MCUboot @ 0x01008000 and 1 MiB slots with DIRECT_XIP/flash-remap.

## Note (P2)
Until CMPA `BOOT_SRC` is approved (P3), the application uses a standalone linker (`MCUBOOT_HEADER_SIZE=0`) so vectors live at 0x0 and the board can boot for Ethernet/Hello bring-up.
