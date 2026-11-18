# Terps Racing EV STM32 Debug Skills

This repository contains two skills and one local debugger bridge:

| Skill | Use it for |
| --- | --- |
| `stm32-debug` | General STM32 firmware errors and live ST-LINK debugging |
| `stm32l432kc-debug` | STM32L432KCU6 firmware, including TREV HVC and BMS projects |

The bridge runs OpenOCD and Arm GDB on **your computer**. A cloud-only conversation cannot reach a USB-connected board. It requires Python 3.10+, `openocd`, and `arm-none-eabi-gdb` on the host `PATH`.

## Connect the board

- For a custom HVC or BMS board, connect a ST-LINK probe to the computer by USB and to the board's SWD connector. The target needs power and a shared ground. Check the board schematic for the connector pinout; do not guess it from the connector shape. The probe's target-voltage pin senses the board voltage and should not be assumed to power the board.
- For a Nucleo board with a built-in ST-LINK, connect its ST-LINK USB port to the computer and power it as the board instructions specify.
- Put the board in a state where a brief debugger halt is safe for all connected outputs. Close any other OpenOCD, GDB, or VS Code debug session that owns the probe. CAN/PCAN hardware is not needed for this debug bridge.

## ChatGPT desktop and Codex

After this repository is published, register and install its GitHub marketplace once:

```sh
codex plugin marketplace add terps-racing-ev/stm32-debug-skills
codex plugin add stm32-debug@trev-stm32-debug
```

Restart the desktop app, open the **firmware** project folder in Codex, and start a new **local** conversation. Use one of these prompts:

```text
$stm32-debug Inspect the STM32 board connected through ST-LINK. Identify the active image, check its state, and diagnose the observed problem.

$stm32l432kc-debug Inspect the connected STM32L432KC HVC or BMS board. Identify the bootloader or active application bank and check its state.
```

You can also install the plugin from the ChatGPT desktop Plugins view after adding the marketplace. The installed plugin includes both the skills and the bridge; installing a standalone `SKILL.md` does not add debugger tools. If an older personal `~/.codex/skills/stm32-debug` copy takes precedence, disable that copy.

## Claude Code CLI and Claude desktop Code tab

After publication, install the same repository as a Claude Code plugin:

```sh
claude plugin marketplace add terps-racing-ev/stm32-debug-skills
claude plugin install stm32-debug@trev-stm32-debug
```

Start a **local** Claude Code session in the firmware folder, or use the **Code** tab of the Claude desktop app with that folder selected. Invoke the plugin skills with Claude's slash-command names:

```text
/stm32-debug:stm32-debug Inspect the STM32 board connected through ST-LINK. Identify the active image and diagnose the observed problem.

/stm32-debug:stm32l432kc-debug Inspect the connected STM32L432KC HVC or BMS board. Identify the bootloader or active application bank and check its state.
```

Use the Code tab or Claude Code CLI for live hardware access. Ordinary Claude chat and cloud sessions do not run this local USB bridge.

## Firmware workspace and exact ELF

Open the firmware project that matches the board, such as [HVC-Firmware](https://github.com/terps-racing-ev/HVC-Firmware) or [BMS-Firmware-RTOS](https://github.com/terps-racing-ev/BMS-Firmware-RTOS). The L432KC skill knows their bank A (`0x08008000`) and bank B (`0x08022000`) layouts, but it checks the *live* PC and VTOR before choosing a bank. The bootloader and each application bank need their own matching ELF.

The bridge can inspect PC, registers, and memory without an ELF. It enables source breakpoints, variable evaluation, and stepping only after comparing the ELF's flash bytes with the connected target. A fresh rebuild might differ from what was flashed. If it does, locate the exact flashed ELF before source-level debugging.

The bridge never flashes, erases, resets, changes option bytes, or sends CAN updates. A target left halted is automatically resumed after 45 seconds; closing the session resumes and detaches it. If the app's sandbox denies USB or loopback socket access, the bridge reports that error.

## Local checks

```sh
python3 -m unittest discover -s tests -q
claude plugin validate .
python3 run_server.py
```

The last command starts the MCP stdio server and waits for JSON-RPC input. The tests use a fake target and do not touch connected hardware. The canonical skill files are under `skills/`; the `.agents/skills/` copies support direct skill discovery and should stay in sync.
