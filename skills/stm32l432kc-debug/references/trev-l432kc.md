# TREV STM32L432KC project map

Reviewed public source snapshots: [HVC-Firmware at `61ac400`](https://github.com/terps-racing-ev/HVC-Firmware/tree/61ac400ffd38c122b389ce8f88e4e0ca00336373) and [BMS-Firmware-RTOS at `1487d34`](https://github.com/terps-racing-ev/BMS-Firmware-RTOS/tree/1487d343b3303557c4b363a1c52e650a96c73d0b). Recheck the workspace version before using these paths or addresses.

Both projects' CubeMX `.ioc` files set `Mcu.CPN=STM32L432KCU6` and `Mcu.UserName=STM32L432KCUx`. Their build files define `STM32L432xx`, select Cortex-M4, and their `openocd.cfg` files source `interface/stlink.cfg` and `target/stm32l4x.cfg`. These establish the *project target*, not the part physically connected to a probe.

| Image | Linker origin / expected VTOR | Linker script | Typical staged ELF |
| --- | --- | --- | --- |
| HVC bank A | `0x08008000` | `STM32L432XX_APP_BANK_A.ld` | `build/debug/HVC_a.elf` |
| HVC bank B | `0x08022000` | `STM32L432XX_APP_BANK_B.ld` | `build/debug/HVC_b.elf` |
| BMS bank A | `0x08008000` | `STM32L432XX_APP_BANK_A.ld` | `build/debug/BMS-Firmware-RTOS_a.elf` |
| BMS bank B | `0x08022000` | `STM32L432XX_APP_BANK_B.ld` | `build/debug/BMS-Firmware-RTOS_b.elf` |

The two application banks are each 104 KiB. The linker scripts reserve `0x0803C000` onward for 16 KiB of storage. `dual_build.mk` passes `VECT_TAB_OFFSET=0x8000` for A and `0x22000` for B; `system_stm32l4xx.c` assigns `SCB->VTOR` from that offset. The normal `STM32L432XX_FLASH.ld` and a plain `build/debug/<target>.elf` are separate from the two bank images. Do not load those symbols into a banked application session just because the project name matches.

The HVC is the high-voltage controller; the BMS firmware is for TREV4 battery-module boards. Their `dual_build.mk` wrappers call PowerShell for staging, so check host tooling before attempting that build path on macOS or Linux. Neither project snapshot here identifies a matching ELF for any particular connected board. A bootloader ELF is likewise distinct from either application ELF. Determine the active image from live PC and VTOR, then require the bridge's exact flash-byte comparison before source-level debugging.

The bridge intentionally exposes no CAN-flash command. Do not run a repository's `mass_erase`, `flash`, or update target while investigating a live failure.
