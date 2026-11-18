from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from server.debugger import DebugError, DebugSession, GdbMI
from server.elf import ElfError, flash_segments


def make_elf(path: Path, image: bytes, address: int = 0x08020000) -> None:
    data = bytearray(84 + len(image))
    data[:16] = b"\x7fELF\x01\x01\x01" + bytes(9)
    struct.pack_into("<H", data, 18, 40)  # EM_ARM
    struct.pack_into("<I", data, 28, 52)  # program header offset
    struct.pack_into("<HH", data, 42, 32, 1)
    struct.pack_into("<IIIIIIII", data, 52, 1, 84, address, address,
                     len(image), len(image), 5, 4)
    data[84:] = image
    path.write_bytes(data)


class FakeGdb:
    flash = b""
    vtor = 0x08020000
    pc = 0x08020004

    def __init__(self, executable: str, elf: Path):
        self.events: list[str] = []
        self.commands: list[str] = []

    def command(self, command: str, timeout: float = 10) -> str:
        self.commands.append(command)
        if command.startswith("-data-evaluate-expression"):
            return f'done,value="0x{self.pc:08x}"'
        return "done"

    def memory(self, address: int, size: int) -> bytes:
        if address == 0xE000ED08:
            return self.vtor.to_bytes(4, "little")
        if address == 0xE0042000:
            return (0x413).to_bytes(4, "little")
        if address < 0x08020000 or address + size > 0x08020000 + len(self.flash):
            raise DebugError("outside fake flash")
        offset = address - 0x08020000
        return self.flash[offset : offset + size]

    def wait_stop(self, timeout: float) -> str | None:
        return None

    def discard_stops(self) -> None:
        self.events.clear()

    def close(self) -> None:
        pass


class BridgeTests(unittest.TestCase):
    def test_flash_segments_rejects_non_arm_elf(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.elf"
            path.write_bytes(b"not an elf")
            with self.assertRaises(ElfError):
                flash_segments(path)

    def test_matching_image_enables_hardware_breakpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.elf"
            image = bytes(range(256)) * 3
            make_elf(path, image)
            FakeGdb.flash = image
            FakeGdb.pc = 0x08020004
            with patch("server.debugger.GdbMI", FakeGdb), patch.object(DebugSession, "_start_openocd", return_value=3333):
                session = DebugSession("stm32f4x", str(path))
                try:
                    result = session.start()
                    self.assertTrue(result["elf_match"])
                    self.assertEqual(result["bytes_compared"], len(image))
                    self.assertEqual(result["vtor"], "0x08020000")
                    self.assertTrue(session.breakpoint("main")["hardware"])
                    self.assertIn('-break-insert -h "main"', session.gdb.commands)
                finally:
                    session.close()

    def test_mismatched_image_disables_source_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.elf"
            image = bytes(range(256)) * 3
            make_elf(path, image)
            FakeGdb.flash = image[:300] + b"\xff" + image[301:]
            FakeGdb.pc = 0x08020004
            with patch("server.debugger.GdbMI", FakeGdb), patch.object(DebugSession, "_start_openocd", return_value=3333):
                session = DebugSession("stm32f4x", str(path))
                try:
                    result = session.start()
                    self.assertFalse(result["elf_match"])
                    self.assertEqual(result["first_mismatch"], "0x0802012c")
                    with self.assertRaisesRegex(DebugError, "ELF differs"):
                        session.breakpoint("main")
                finally:
                    session.close()

    def test_bootloader_elf_is_rejected_when_pc_is_in_application(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bootloader.elf"
            image = bytes(range(64))
            make_elf(path, image)
            FakeGdb.flash = image
            FakeGdb.pc = 0x08030004
            FakeGdb.vtor = 0x08020000
            with patch("server.debugger.GdbMI", FakeGdb), patch.object(DebugSession, "_start_openocd", return_value=3333):
                session = DebugSession("stm32f4x", str(path))
                try:
                    result = session.start()
                    self.assertFalse(result["pc_in_elf_image"])
                    self.assertFalse(result["elf_match"])
                finally:
                    session.close()

    def test_session_can_inspect_without_elf(self):
        FakeGdb.pc = 0x080248AC
        FakeGdb.vtor = 0x08020000
        with patch("server.debugger.GdbMI", FakeGdb), patch.object(DebugSession, "_start_openocd", return_value=3333):
            session = DebugSession("stm32f4x")
            try:
                result = session.start()
                self.assertEqual(result["pc"], "0x080248ac")
                self.assertIsNone(result["elf"])
                self.assertFalse(result["elf_match"])
            finally:
                session.close()

    def test_step_timeout_interrupts_and_closes_if_stop_is_unconfirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.elf"
            image = bytes(range(64))
            make_elf(path, image)
            FakeGdb.flash = image
            FakeGdb.pc = 0x08020004
            FakeGdb.vtor = 0x08020000
            with patch("server.debugger.GdbMI", FakeGdb), patch.object(DebugSession, "_start_openocd", return_value=3333):
                session = DebugSession("stm32f4x", str(path))
                session.start()
                try:
                    with self.assertRaisesRegex(DebugError, "session closed"):
                        session.step("over")
                    self.assertIn("-exec-interrupt", session.gdb.commands)
                    self.assertTrue(session.closed)
                finally:
                    session.close()

    def test_halt_watchdog_resumes_abandoned_session(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.elf"
            image = bytes(range(64))
            make_elf(path, image)
            FakeGdb.flash = image
            FakeGdb.pc = 0x08020004
            FakeGdb.vtor = 0x08020000
            with patch("server.debugger.GdbMI", FakeGdb), patch.object(DebugSession, "_start_openocd", return_value=3333), patch("server.debugger.HALT_LIMIT_SECONDS", 0.01):
                session = DebugSession("stm32f4x", str(path))
                try:
                    session.start()
                    deadline = time.monotonic() + 2
                    while session.halted_since is not None and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertIsNone(session.halted_since)
                    self.assertIn("-exec-continue", session.gdb.commands)
                finally:
                    session.close()

    def test_mcp_stdio_handshake_and_tool_discovery(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "debug_environment", "arguments": {}}},
        ]
        result = subprocess.run(
            [sys.executable, "-B", "-m", "server"],
            input="\n".join(json.dumps(x) for x in requests) + "\n",
            text=True, capture_output=True, timeout=5,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        messages = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([message["id"] for message in messages], [1, 2, 3])
        self.assertIn("debug_start", {tool["name"] for tool in messages[1]["result"]["tools"]})
        self.assertIn("openocd", messages[2]["result"]["structuredContent"])

    def test_malformed_tool_call_does_not_crash_or_execute_notification(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": []},
            {"jsonrpc": "2.0", "method": "tools/call",
             "params": {"name": "debug_start", "arguments": {"target": "stm32f4x"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        ]
        result = subprocess.run(
            [sys.executable, "-B", "-m", "server"],
            input="\n".join(json.dumps(x) for x in requests) + "\n",
            text=True, capture_output=True, timeout=5,
            cwd=Path(__file__).resolve().parents[1],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        messages = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([message["id"] for message in messages], [1, 2])
        self.assertEqual(messages[0]["error"]["code"], -32602)
        self.assertEqual(messages[1]["result"], {})

    def test_mi_memory_parser_rejects_short_read(self):
        gdb = GdbMI.__new__(GdbMI)
        gdb.command = lambda command: 'done,memory=[{begin="0x08020000",contents="aabb"}]'
        self.assertEqual(gdb.memory(0x08020000, 2), b"\xaa\xbb")
        with self.assertRaisesRegex(DebugError, "Short memory read"):
            gdb.memory(0x08020000, 3)


if __name__ == "__main__":
    unittest.main()
