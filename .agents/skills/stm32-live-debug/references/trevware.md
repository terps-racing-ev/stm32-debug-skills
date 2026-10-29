# TREVware extension debug path

Source reviewed: `terps-racing-ev/vs-code-extension-dual-booting-flashing`, commit `d9a4419e4ee52d21eb4eff43efb69bd878269130` (2026-10-29 checkout). Reinspect the active firmware workspace and extension version before relying on these defaults.

The extension's `src/configuration/LaunchTasksConfig.ts` generates `Debug STM32` and `Attach STM32` Cortex-Debug entries in `.vscode/launch.json`. They use `servertype: openocd`, `configFiles: ["openocd.cfg"]`, `preLaunchTask: "Build STM"`, and `./build/debug/${target}.elf`. `Debug STM32` has `request: launch`; `Attach STM32` has `request: attach` but still inherits the build task. The extension does not register an agent-facing debug-control command. Its standard Flash command is separate: Make invokes OpenOCD `program <elf> verify reset exit`.

The TREV dual-bank command (`src/dualBank/index.ts`, `dualBuild.ts`) generates linker scripts and builds bank A and B images. It stages `.bin`, `.elf`, and `.hex` under the configured `outputDir`; it does not upload them over CAN or start a hardware debug session. The STM32L432 preset places application bank A at `0x08008000`, bank B at `0x08022000`, with storage starting `0x0803c000` (`src/dualBank/presets.ts`). These are preset values, not a substitute for the target project's actual map.

For a live dual-bank target, determine which bank the bootloader selected. Use that bank's ELF and linker script, and check `SCB->VTOR` or the vector table at the bank origin. A source-level debugger can appear misleading if symbols come from the other bank or another build.
