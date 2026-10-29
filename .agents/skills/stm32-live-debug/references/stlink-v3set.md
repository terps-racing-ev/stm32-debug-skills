# STLINK-V3SET facts for target setup

Source: user-provided `DB_stlink-v3set.pdf`, STMicroelectronics data brief DB3692 Rev 3 (July 2024), pages 1-3. The brief is a feature overview; consult ST's UM2448 and the board schematic for exact connector pins and wiring.

- STLINK-V3SET is a standalone debugger/programmer for STM8 and STM32. The STM32 path supports JTAG, SWD, and Serial Wire Viewer (SWV).
- The probe is USB powered through Micro-B. The stated target application voltage for JTAG/SWD is 3 to 3.6 V, with 5 V tolerant inputs. Do not assume the probe supplies target power or infer wiring from connector names alone.
- STDC14 is available on the main debug connection; supplied adapters can map to MIPI10/STDC14/MIPI20. The virtual COM port UART is available on STDC14, not MIPI10. SPI/UART/I2C/CAN/GPIO bridge signals require the MB1440 adapter board.
- The optional second virtual COM port uses a reversible probe firmware change that disables the mass-storage drag-and-drop interface. Such a firmware change is separate from ordinary MCU debugging.
- CAN bridge capability does not imply that the TREV extension's dual-bank build command performs CAN flashing. Confirm the host tool, adapter wiring, and bootloader protocol before attempting any CAN upload.
