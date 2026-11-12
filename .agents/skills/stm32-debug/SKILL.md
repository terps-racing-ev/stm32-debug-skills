---
name: stm32-debug
description: Use when a user asks why STM32 firmware code, HAL or CubeMX code, a build or linker error, a HardFault, or behavior on the board is failing, including when they paste code or an error message with STM32 clues. Do not use for unrelated C or C++ questions.
---

# STM32 debugging

Choose the least invasive evidence that can explain the failure. Pasted code and error output can support source-level diagnosis; a claim about actual on-device behavior needs observations from the target.

## Code or error pasted without a live target

1. Identify the STM32 evidence in the request or code, such as `stm32...` headers, HAL/LL calls, CubeMX files, `arm-none-eabi` output, a HardFault, or a named MCU. Determine whether the failure is from compilation, linking, flashing, startup, or runtime. If the code gives no STM32 clue, use ordinary code debugging instead of assuming this skill applies.
2. Trace the exact diagnostic to the source, build flags, linker script, or startup code it depends on. Explain a concrete cause when the evidence supports one. If the pasted snippet is insufficient, inspect available project files and request the exact error text or missing call site while giving any findings already supported by the code.
3. Do not require a probe, ELF, active bank, or hardware connection for a source-only question. State which conclusions need a build or target observation to confirm.

## Live target investigation

1. Identify the exact board and MCU, probe, firmware project, matching ELF with symbols, active image or bank, and the user's symptom. Read the workspace's `launch.json`, `openocd.cfg`, and build configuration. Check whether `openocd.cfg` runs reset or programming commands during initialization. For TREVware, read [references/trevware.md](references/trevware.md). For STLINK-V3SET hardware, read [references/stlink-v3set.md](references/stlink-v3set.md).
2. Check whether a connected tool exposes the **active** VS Code Debug Adapter Protocol session. Use it only if it can select the intended target, set breakpoints, continue/pause/step, and read stack frames, registers, and memory. Do not infer such control from the presence of the `Debug STM32` action.
3. Otherwise use a terminal-controlled OpenOCD and `arm-none-eabi-gdb` session. If VS Code already owns the probe or GDB server, ask the user to stop that session or use a confirmed control bridge; do not race two clients for one target. Read [references/gdb-session.md](references/gdb-session.md) for the command pattern.

- Record the exact ELF build identity and target state before changes. Observe where execution stops, the PC, call stack, registers, relevant variables, and fault registers when applicable. Reproduce with a bounded run and move breakpoints toward the first incorrect state. Distinguish a debugger connection failure from a firmware failure.
- For dual-bank bootloader projects, determine the active bank from target evidence such as the live vector-table register, bootloader metadata, or boot logs. Verify the ELF's linked load address and vector table against that bank before interpreting source-level stepping.
- Treat halt, reset, and stepping as actions that can alter real-time behavior. Tell the user when that matters for the connected system. Flashing, mass erase, option-byte changes, and firmware updates require explicit authorization for the target and image. Never use a destructive command merely to make a debug connection work.
- Stop on ambiguous target identity, mismatched ELF, loss of probe connection, or an unsafe physical state; report the evidence and the missing prerequisite. Do not invent live observations.

## Report

Give the diagnostic evidence, root-cause hypothesis with confidence, and a specific next experiment or fix. Separate observed facts from inference. For a live session, include the reproduction steps, exact target/ELF/bank, decisive debugger observations, and whether the target was left running or halted. End any debugger process you started when finished.
