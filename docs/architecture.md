# Architecture

- FreeRTOS + lwIP + NXP ENET/LAN8741 (from `ota_mcuboot_server/enet` freestanding export)
- Product TCP: Hello port 5000 always; Update port 5555 for first 180 s
- Static IP policy: `192.168.2.90/24`, GW `192.168.2.24`
- Boot: P2 uses standalone linker (`MCUBOOT_HEADER_SIZE=0`) so app boots without IFR MCUboot
- P3+: restore NXP OTA linker + IFR MCUboot DIRECT_XIP (CMPA BOOT_SRC gated)
- Field updates: NXP SB3.1 + per-unit `CUST_MK_SK` (P4+)
