# Terminal-controlled debug session

Use this path when no tool controls the active VS Code debug session. Start from the firmware workspace, using its own `openocd.cfg` and exact ELF. Prefer an interactive terminal session so breakpoints and target state persist across agent calls.

## Preflight

Check `command -v openocd` and `command -v arm-none-eabi-gdb`; inspect `.vscode/launch.json`, `openocd.cfg`, the build output, and any existing OpenOCD/GDB processes. Check `openocd.cfg` for commands that reset or program the target during initialization. Confirm the MCU, ST-LINK probe, and target bank. Do not launch a second server while Cortex-Debug owns the probe. If the required tool is missing, report it rather than guessing another executable or changing host setup without authorization.

## Connect

When the probe is free, run `openocd -f openocd.cfg` in a persistent terminal. Read its output and actual GDB listening address. Open a second persistent terminal with `arm-none-eabi-gdb -q -nx <matching.elf>` and connect with `target remote <address>` (often `localhost:3333`, but use the observed endpoint). Attaching may halt execution. Do not issue `load`, `monitor reset`, or `monitor flash` as part of connection.

Useful GDB commands after connection:

```gdb
info files
info threads
bt
info registers
info breakpoints
break file.c:line
continue
interrupt
next
step
finish
print variable
x/8wx address
```

Set breakpoints at an entry point or just before the suspected failure. Use `continue` with a bounded wait; if it does not stop, interrupt and record the PC. Inspect fault registers using the device reference manual and the live register state; do not assume every STM32 has identical fault registers. If source lines do not match behavior, verify ELF build identity, optimization level, load address, and vector table before drawing a firmware conclusion.

Close GDB with `detach` only after deciding whether the target should run, then `quit`. Stop only the OpenOCD process that this session started. Report whether the target was left running or halted.
