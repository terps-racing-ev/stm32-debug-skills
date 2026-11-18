---
name: stm32l432kc-debug
description: Use when diagnosing STM32L432KC or STM32L432KCU6 firmware, build errors, bootloader handoff, or a live ST-LINK target, especially TREV HVC or BMS firmware. Do not use for other STM32L4 parts without confirming the exact device.
---

# STM32L432KC debugging

Use the STM32L432KC project details in [references/trev-l432kc.md](references/trev-l432kc.md). The TREV HVC and BMS projects declare `STM32L432KCU6`; OpenOCD calls their target family `stm32l4x`. A family-level probe response alone does not establish the exact fitted part.

## Diagnose

1. Identify the board and firmware project from the workspace, board marking, or user context. For TREV HVC/BMS, read the project reference. For other projects, derive the flash map and build artifacts from their own files. For a source-only error, trace the diagnostic through code, build flags, startup, and linker configuration; a connected board is optional.
2. For a live board, establish that a brief halt is safe for connected outputs. Check for another OpenOCD or VS Code debug session before taking the probe. Prefer the bundled `stm32_debug` MCP tools: `debug_environment`, `debug_probe` with `target: "stm32l4x"`, then `debug_start`. The bridge does not flash or reset.
3. Start without an ELF if the active image is unknown. Use PC and VTOR to distinguish bootloader execution from application bank A or B. Select the ELF linked for the image executing now. The bridge must report `elf_match: true` after comparing flash bytes before source breakpoints, variable evaluation, stepping, or bounded running. If it does not match, inspect only raw target evidence, close the session, and seek the exact flashed ELF.
4. With a matching ELF, inspect registers, stack, relevant variables, and fault state. Use hardware breakpoints and bounded runs to narrow the first incorrect state. Keep the target halted only as long as needed, then call `debug_close` and report whether it resumed and detached. The bridge automatically resumes an abandoned halt after 45 seconds.

If the MCP tools are unavailable, a host terminal with ST-LINK, OpenOCD, and Arm GDB can perform the same checks. Report access errors plainly; the skill cannot grant USB or loopback socket permission. Do not assume a rebuilt ELF matches a board. Flash, erase, reset, option-byte changes, and CAN updates require specific authorization for the target and image.

Report the exact project, observed target identity and state, active image and bank, ELF comparison result, evidence for the diagnosis, and the next experiment or fix. Separate observed facts from inference.
