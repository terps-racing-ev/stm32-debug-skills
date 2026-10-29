---
name: stm32-live-debug
description: Use when diagnosing firmware running on an STM32 through ST-LINK, SWD/JTAG, Cortex-Debug, OpenOCD, or GDB, especially when an agent needs to inspect a live target, set breakpoints, step, or investigate a fault.
---

# STM32 live debugging

Use observations from the running target to explain a firmware failure. A VS Code launch configuration describes a debug session; it does not by itself give an agent control of that session.

## Establish the session

1. Identify the exact board and MCU, probe, firmware project, matching ELF with symbols, active image or bank, and the user's symptom. Read the workspace's `launch.json`, `openocd.cfg`, and build configuration. Check whether `openocd.cfg` runs reset or programming commands during initialization. For TREVware, read [references/trevware.md](references/trevware.md). For STLINK-V3SET hardware, read [references/stlink-v3set.md](references/stlink-v3set.md).
2. Check whether a connected tool exposes the **active** VS Code Debug Adapter Protocol session. Use it only if it can select the intended target, set breakpoints, continue/pause/step, and read stack frames, registers, and memory. Do not infer such control from the presence of the `Debug STM32` action.
3. Otherwise use a terminal-controlled OpenOCD and `arm-none-eabi-gdb` session. If VS Code already owns the probe or GDB server, ask the user to stop that session or use a confirmed control bridge; do not race two clients for one target. Read [references/gdb-session.md](references/gdb-session.md) for the command pattern.

## Investigate

- Record the exact ELF build identity and target state before changes. Observe where execution stops, the PC, call stack, registers, relevant variables, and fault registers when applicable. Reproduce with a bounded run and move breakpoints toward the first incorrect state. Distinguish a debugger connection failure from a firmware failure.
- For dual-bank bootloader projects, determine the active bank from target evidence such as the live vector-table register, bootloader metadata, or boot logs. Verify the ELF's linked load address and vector table against that bank before interpreting source-level stepping.
- Treat halt, reset, and stepping as actions that can alter real-time behavior. Tell the user when that matters for the connected system. Flashing, mass erase, option-byte changes, and firmware updates require explicit authorization for the target and image. Never use a destructive command merely to make a debug connection work.
- Stop on ambiguous target identity, mismatched ELF, loss of probe connection, or an unsafe physical state; report the evidence and the missing prerequisite. Do not invent live observations.

## Report

Give the reproduction steps, exact target/ELF/bank, decisive debugger observations, root-cause hypothesis with confidence, and a specific next experiment or fix. Separate observed facts from inference. Leave the target in a stated run or halt state and end any debugger process you started when finished.
