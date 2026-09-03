# P5 — NXP SB3 call graph (stock → product)

**Source:** SDK 26.06 `ota_mcuboot_basic` + `_common/sb3_api/sb3_api_mcxn10.c`  
**Product:** TCP `:5555` replaces XMODEM only.

## Stock path (`xmodem_sb3`)

```text
shellCmd_xmodem_sb3
  -> bl_get_update_partition_info(0)     # inactive slot address (informational)
  -> sb3_api_init()                      # API_Init + Sbloader_Init (4 KiB work buf)
  -> sb3_check_provisioning(false)       # CMPA sanity (warn only)
  -> xmodem_receive(... buffer_full_callback = process_received_data_sb3)
       process_received_data_sb3(offset, size)
         -> [offset==0] sb3_parse_header()   # magic "sbv3" + length (not crypto)
         -> sb3_api_pump(chunk)              # ROM Sbloader_Pump
  -> sb3_api_finalize()
  -> sb3_api_deinit()
  -> (shell) image test  -> bl_update_image_state(kSwapType_ReadyForTest)
  -> reboot
```

## Product path (P5)

```text
update_task
  LISTEN :5555 while window_remaining > 0
  ACCEPT (one client) — session may outlive window
  recv fixed header (magic/ver/uuid/len)
  sb3_api_init()
  loop: recv bounded chunk -> sb3_api_pump() until sb3_len
  sb3_api_finalize(); sb3_api_deinit()
  verify candidate header via mcuboot_app_support
  bl_update_image_state(0, kSwapType_ReadyForTest)
  send "OK\n"; short delay; NVIC_SystemReset()
```

Failure: no ReadyForTest; close socket; reopen listen only if window still open.

## Reuse (unchanged NXP)

| Symbol | File |
|--------|------|
| `sb3_api_init/pump/finalize/deinit` | `examples/ota_examples/_common/sb3_api/sb3_api_mcxn10.c` |
| `sb3_parse_header` | same (length accounting only) |
| `bl_update_image_state` | `middleware/mcuboot_opensource/.../mcuboot_app_support.c` |
| ROM | `driver.mem_interface` / `Sbloader_*` |
