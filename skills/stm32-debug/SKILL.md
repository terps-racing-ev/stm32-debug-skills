---
name: stm32-debug
description: Use when diagnosing STM32 firmware code, build errors, bootloader handoff, ST-LINK connection, or behavior on a running board, including pasted STM32 code or errors. Do not use for unrelated C or C++ questions.
---

# STM32 debugging

Choose the least invasive evidence that can explain the failure. Pasted code and error output can support source-level diagnosis; a claim about actual on-device behavior needs observations from the target.

## Code or error pasted without a live target

1. Identify the STM32 evidence in the request or code, such as `stm32...` headers, HAL/LL calls, CubeMX files, `arm-none-eabi` output, a HardFault, or a named MCU. Determine whether the failure is from compilation, linking, flashing, startup, or runtime. If the code gives no STM32 clue, use ordinary code debugging instead of assuming this skill applies.
2. Trace the exact diagnostic to the source, build flags, linker script, or startup code it depends on. Explain a concrete cause when the evidence supports one. If the pasted snippet is insufficient, inspect available project files and request the exact error text or missing call site while giving any findings already supported by the code.
3. Do not require a probe, ELF, active bank, or hardware connection for a source-only question. State which conclusions need a build or target observation to confirm.

## Live target investigation

1. Identify the exact board and MCU, probe, firmware project, matching ELF with symbols, active image or bank, and the user's symptom or setup goal. Read the workspace's `launch.json`, `openocd.cfg`, and build configuration. Check whether `openocd.cfg` runs reset or programming commands during initialization. For TREVware, read [references/trevware.md](references/trevware.md). For STLINK-V3SET hardware, read [references/stlink-v3set.md](references/stlink-v3set.md).
2. Prefer the bundled `stm32_debug` MCP tools when available. Follow [references/bridge.md](references/bridge.md): check the host environment, probe, then start a session with the target family and candidate ELF. The bridge reads the live vector table and flash and reports whether the ELF is an exact match. If it differs, do not use that ELF for source breakpoints or stepping. Raw PC, registers, and memory can still help identify the target. Always close the session when finished.
3. If a connected tool exposes the **active** VS Code Debug Adapter Protocol session, use it only if it can select the intended target, set breakpoints, continue/pause/step, and read stack frames, registers, and memory. Do not infer such control from the presence of the `Debug STM32` action. Otherwise use a terminal-controlled OpenOCD and `arm-none-eabi-gdb` session if the agent's runtime has host USB and socket access. Read [references/gdb-session.md](references/gdb-session.md). If the runtime blocks those capabilities, report the precise blocker; a skill cannot grant them. If VS Code already owns the probe or GDB server, ask the user to stop that session or use a confirmed control bridge; do not race two clients for one target.

- Record the exact ELF build identity and target state before changes. Observe where execution stops, the PC, call stack, registers, relevant variables, and fault registers when applicable. Reproduce with a bounded run and move breakpoints toward the first incorrect state. Distinguish a debugger connection failure from a firmware failure.
- For bootloader projects, distinguish execution still in the bootloader from execution in the application it started. Determine the active image and application bank from target evidence such as PC, the live vector-table register, bootloader metadata, or boot logs. Verify that image's ELF load address and flash bytes against the live target before interpreting source-level stepping. A source revision that looks close is still not an exact ELF match.
- Treat halt, reset, and stepping as actions that can alter real-time behavior. Tell the user when that matters for the connected system. Flashing, mass erase, option-byte changes, and firmware updates require explicit authorization for the target and image. Never use a destructive command merely to make a debug connection work.
- Before attaching to a live controller that may drive physical outputs, establish that a brief halt is safe; do not infer bench safety from a USB connection alone.
- Stop source-level actions on ambiguous target identity, mismatched ELF, loss of probe connection, or an unsafe physical state; report the evidence and the missing prerequisite. Do not invent live observations.

## Report

Give the diagnostic evidence, root-cause hypothesis with confidence, and a specific next experiment or fix. Separate observed facts from inference. For a live session, include the reproduction steps, exact target/ELF/bank, decisive debugger observations, and whether the target was left running or halted. End any debugger process you started when finished.
