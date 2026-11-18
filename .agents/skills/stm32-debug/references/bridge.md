# Bundled local debugger bridge

The `stm32-debug` plugin bundles one `stm32-debug` skill and a local `stm32_debug` MCP server. A single skill invocation can select and call these tools when the plugin is installed in a local desktop runtime with USB and loopback socket access. The skill alone cannot grant those permissions.

## Session workflow

1. Call `debug_environment`, then `debug_probe` with the OpenOCD target family inferred from the firmware project (for example `stm32f4x`). The bridge uses its bundled ST-LINK interface and target-family script, not arbitrary project Tcl.
2. Call `debug_start` with the target family. An ELF is optional for initial inspection. When available, choose the ELF for the **currently executing image** and pass its absolute path: the bootloader ELF while execution is in the bootloader, or the selected application-bank ELF after handoff. The bridge halts the target and reads PC, VTOR, and chip ID when available. If the vector table points at the ELF image, it compares every loadable flash byte with target flash. The PC must also lie in that image.
3. Check `elf_match` and `mismatch_reason`. If false, use `debug_state` or `debug_read_memory` only for raw target evidence, then `debug_close`. Find the matching ELF before `debug_breakpoint`, `debug_step`, `debug_run`, or `debug_evaluate`.
4. With a matching ELF, inspect state, set a hardware breakpoint, and use a bounded `debug_run`. Use `debug_step`, `debug_pause`, `debug_resume`, and `debug_evaluate` as needed. `debug_read_memory` is limited to 256 bytes per call. Reading some peripheral status registers may clear them; check the MCU reference manual before reading such registers.
5. Call `debug_close` to resume the target if halted, detach GDB, and stop only the OpenOCD process started by the bridge. The bridge also auto-resumes a target left halted for 45 seconds.

The bridge exposes no flash, erase, reset, option-byte, memory-write, arbitrary shell, or arbitrary GDB command tool. It allows one active session per server process. If a host blocks USB or local sockets, the bridge returns that error; use a runtime that can access the host probe rather than claiming a live diagnosis.
