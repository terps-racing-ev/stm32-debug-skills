"""Bounded ST-LINK/OpenOCD/GDB session. No flash or arbitrary command tool exists."""

from __future__ import annotations

import json
import queue
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .elf import flash_segments


TARGETS = {
    "stm32f0x", "stm32f1x", "stm32f2x", "stm32f3x", "stm32f4x",
    "stm32f7x", "stm32g0x", "stm32g4x", "stm32h7x", "stm32l0",
    "stm32l1", "stm32l4x", "stm32u5x",
}
LOCATION = re.compile(r"(?:\*0x[0-9a-fA-F]+|[A-Za-z_][\w./+-]*(?::\d+)?)\Z")
VARIABLE = re.compile(r"[A-Za-z_]\w*(?:(?:\.|->)[A-Za-z_]\w*|\[\d+\])*\Z")
CONTENTS = re.compile(r'contents="([0-9a-fA-F]+)"')
HALT_LIMIT_SECONDS = 45


class DebugError(RuntimeError):
    pass


class GdbMI:
    def __init__(self, executable: str, elf: Path | None):
        command = [executable, "--interpreter=mi3", "--quiet", "--nx"]
        if elf is not None:
            command.append(str(elf))
        self.proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        self.lines: queue.Queue[str] = queue.Queue()
        self.events: list[str] = []
        self.lock = threading.RLock()
        self.token = 0
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.lines.put(line.rstrip("\r\n"))

    def command(self, command: str, timeout: float = 10) -> str:
        with self.lock:
            if self.proc.poll() is not None:
                raise DebugError("GDB exited unexpectedly")
            self.token += 1
            token = str(self.token)
            assert self.proc.stdin is not None
            self.proc.stdin.write(token + command + "\n")
            self.proc.stdin.flush()
            deadline = time.monotonic() + timeout
            while True:
                try:
                    line = self.lines.get(timeout=max(0.01, deadline - time.monotonic()))
                except queue.Empty as exc:
                    raise DebugError(f"GDB timed out on {command.split()[0]}") from exc
                if line.startswith(token + "^"):
                    if line.startswith(token + "^error"):
                        raise DebugError(f"GDB rejected {command.split()[0]}: {line}")
                    return line[len(token) + 1 :]
                if line and line != "(gdb)":
                    self.events.append(line)

    def wait_stop(self, timeout: float) -> str | None:
        with self.lock:
            deadline = time.monotonic() + timeout
            while True:
                for index, event in enumerate(self.events):
                    if event.startswith("*stopped"):
                        return self.events.pop(index)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                try:
                    line = self.lines.get(timeout=remaining)
                except queue.Empty:
                    return None
                if line.startswith("*stopped"):
                    return line
                if line and line != "(gdb)":
                    self.events.append(line)

    def discard_stops(self) -> None:
        """Drop stale attach/step stops before starting a new run command."""
        with self.lock:
            self.events = [event for event in self.events if not event.startswith("*stopped")]
            retained: list[str] = []
            while True:
                try:
                    line = self.lines.get_nowait()
                except queue.Empty:
                    break
                if line and line != "(gdb)" and not line.startswith("*stopped"):
                    retained.append(line)
            self.events.extend(retained)

    def memory(self, address: int, size: int) -> bytes:
        response = self.command(f"-data-read-memory-bytes 0x{address:08x} {size}")
        chunks = CONTENTS.findall(response)
        if not chunks:
            raise DebugError(f"GDB returned no memory at 0x{address:08x}: {response}")
        data = bytes.fromhex("".join(chunks))
        if len(data) != size:
            raise DebugError(f"Short memory read at 0x{address:08x}")
        return data

    def close(self) -> None:
        if self.proc.poll() is None:
            try:
                self.command("-gdb-exit", timeout=2)
            except (DebugError, OSError):
                pass
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.proc.kill()


class DebugSession:
    def __init__(self, target: str, elf_path: str | None = None):
        if target not in TARGETS:
            raise DebugError(f"Unsupported target family: {target}")
        self.elf = Path(elf_path).expanduser().resolve(strict=True) if elf_path else None
        self.segments = flash_segments(self.elf) if self.elf else []
        self.base = self.segments[0][0] if self.segments else None
        self.openocd_path = shutil.which("openocd")
        self.gdb_path = shutil.which("arm-none-eabi-gdb")
        if not self.openocd_path or not self.gdb_path:
            raise DebugError("Install OpenOCD and arm-none-eabi-gdb on the host PATH")
        self.id = uuid.uuid4().hex
        self.target = target
        self.openocd: subprocess.Popen[str] | None = None
        self.gdb: GdbMI | None = None
        self.logs: queue.Queue[str] = queue.Queue()
        self.halted_since: float | None = None
        self.elf_match = False
        self.closed = False
        self.lock = threading.RLock()

    def _openocd_reader(self) -> None:
        assert self.openocd is not None and self.openocd.stdout is not None
        for line in self.openocd.stdout:
            self.logs.put(line.rstrip("\r\n"))

    def _start_openocd(self) -> int:
        try:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
        except OSError as exc:
            raise DebugError(f"Host cannot bind a loopback GDB socket: {exc}") from exc
        self.openocd = subprocess.Popen(
            [self.openocd_path, "-f", "interface/stlink.cfg", "-f",
             f"target/{self.target}.cfg", "-c", "bindto 127.0.0.1",
             "-c", "tcl_port disabled", "-c", "telnet_port disabled",
             "-c", f"gdb_port {port}"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        threading.Thread(target=self._openocd_reader, daemon=True).start()
        deadline = time.monotonic() + 12
        seen: list[str] = []
        while time.monotonic() < deadline:
            if self.openocd.poll() is not None:
                raise DebugError("OpenOCD exited: " + " | ".join(seen[-12:]))
            try:
                line = self.logs.get(timeout=0.2)
            except queue.Empty:
                continue
            seen.append(line)
            if "Listening on port" in line and "gdb connections" in line:
                return port
        raise DebugError("OpenOCD did not open its GDB port: " + " | ".join(seen[-12:]))

    def start(self) -> dict:
        try:
            port = self._start_openocd()
            self.gdb = GdbMI(self.gdb_path, self.elf)
            self.gdb.command("-gdb-set mi-async on")
            self.gdb.command("-gdb-set confirm off")
            self.gdb.command(f"-target-select remote 127.0.0.1:{port}", timeout=12)
            self.halted_since = time.monotonic()
            self.gdb.discard_stops()
            threading.Thread(target=self._watchdog, daemon=True).start()
            try:
                vtor = int.from_bytes(self.gdb.memory(0xE000ED08, 4), "little")
            except DebugError:
                vtor = None  # Cortex-M0 parts need not implement VTOR.
            try:
                chip_id = int.from_bytes(self.gdb.memory(0xE0042000, 4), "little")
            except DebugError:
                chip_id = None
            pc_response = self.gdb.command('-data-evaluate-expression "$pc"')
            match = re.search(r'value="(0x[0-9a-fA-F]+|\d+)"', pc_response)
            pc = int(match.group(1), 0) if match else None
            mismatch = None
            compared = 0
            deadline = time.monotonic() + 25
            if self.base is not None and (vtor is None or vtor == self.base):
                for address, blob in self.segments:
                    for offset in range(0, len(blob), 512):
                        if time.monotonic() >= deadline:
                            raise DebugError("ELF comparison exceeded 25 seconds")
                        expected = blob[offset : offset + 512]
                        actual = self.gdb.memory(address + offset, len(expected))
                        compared += len(expected)
                        if actual != expected:
                            first = next(i for i, (a, b) in enumerate(zip(actual, expected)) if a != b)
                            mismatch = address + offset + first
                            break
                    if mismatch is not None:
                        break
            pc_in_image = pc is not None and any(
                address <= (pc & ~1) < address + len(blob)
                for address, blob in self.segments
            )
            self.elf_match = bool(self.segments) and (vtor is None or vtor == self.base) and pc_in_image and mismatch is None
            if not self.segments:
                mismatch_reason = "no_elf"
            elif vtor is not None and vtor != self.base:
                mismatch_reason = "vector_table_points_elsewhere"
            elif not pc_in_image:
                mismatch_reason = "pc_outside_elf_image"
            elif mismatch is not None:
                mismatch_reason = "flash_bytes_differ"
            else:
                mismatch_reason = None
            result = {
                "session_id": self.id,
                "target": self.target,
                "pc": f"0x{pc:08x}" if pc is not None else None,
                "vtor": f"0x{vtor:08x}" if vtor is not None else None,
                "chip_id": f"0x{chip_id:08x}" if chip_id is not None else None,
                "elf": str(self.elf) if self.elf else None,
                "elf_flash_base": f"0x{self.base:08x}" if self.base is not None else None,
                "pc_in_elf_image": pc_in_image,
                "elf_match": self.elf_match,
                "mismatch_reason": mismatch_reason,
                "bytes_compared": compared,
                "first_mismatch": f"0x{mismatch:08x}" if mismatch is not None else None,
                "state": "halted",
                "auto_resume_seconds": HALT_LIMIT_SECONDS,
            }
            return result
        except Exception:
            self.close()
            raise

    def _watchdog(self) -> None:
        while not self.closed:
            time.sleep(1)
            with self.lock:
                self._sync_stop()
                if self.halted_since and time.monotonic() - self.halted_since >= HALT_LIMIT_SECONDS:
                    try:
                        self.resume()
                    except DebugError:
                        self.close()

    def _sync_stop(self) -> str | None:
        if self.gdb is None or self.halted_since is not None:
            return None
        stop = self.gdb.wait_stop(0.02)
        if stop is not None:
            self.halted_since = time.monotonic()
        return stop

    def _require_gdb(self) -> GdbMI:
        if self.closed or self.gdb is None:
            raise DebugError("No active debug session")
        return self.gdb

    def _require_symbols(self) -> GdbMI:
        gdb = self._require_gdb()
        if not self.elf_match:
            raise DebugError("ELF differs from running flash or active vector table; source actions are disabled")
        return gdb

    def state(self) -> dict:
        with self.lock:
            gdb = self._require_gdb()
            self._sync_stop()
            if self.halted_since is None:
                return {"state": "running", "elf_match": self.elf_match}
            result = {"state": "halted", "elf_match": self.elf_match,
                      "pc": gdb.command('-data-evaluate-expression "$pc"'),
                      "registers": gdb.command("-data-list-register-values x"),
                      "stack": gdb.command("-stack-list-frames 0 7") if self.elf_match else None}
            return result

    def memory(self, address: int, size: int) -> dict:
        with self.lock:
            if self.halted_since is None:
                raise DebugError("Pause the target before reading memory")
            if not 1 <= size <= 256 or not 0 <= address <= 0x100000000 - size:
                raise DebugError("Memory read must be 1-256 bytes within the 32-bit address space")
            data = self._require_gdb().memory(address, size)
            return {"address": f"0x{address:08x}", "hex": data.hex()}

    def breakpoint(self, location: str) -> dict:
        with self.lock:
            gdb = self._require_symbols()
            if self.halted_since is None:
                raise DebugError("Pause the target before setting a breakpoint")
            if not LOCATION.fullmatch(location):
                raise DebugError("Use a function, file:line, or *0xaddress breakpoint location")
            response = gdb.command("-break-insert -h " + json.dumps(location))
            return {"breakpoint": response, "hardware": True}

    def delete_breakpoint(self, number: int) -> dict:
        with self.lock:
            gdb = self._require_symbols()
            if not 1 <= number <= 100000:
                raise DebugError("Invalid breakpoint number")
            return {"result": gdb.command(f"-break-delete {number}")}

    def evaluate(self, expression: str) -> dict:
        with self.lock:
            gdb = self._require_symbols()
            if self.halted_since is None:
                raise DebugError("Pause the target before evaluating a variable")
            if not VARIABLE.fullmatch(expression):
                raise DebugError("Only simple variable/member reads are supported")
            return {"expression": expression,
                    "result": gdb.command("-data-evaluate-expression " + json.dumps(expression))}

    def resume(self) -> dict:
        with self.lock:
            gdb = self._require_gdb()
            self._sync_stop()
            if self.halted_since is not None:
                gdb.discard_stops()
                gdb.command("-exec-continue")
                self.halted_since = None
            return {"state": "running"}

    def pause(self) -> dict:
        with self.lock:
            gdb = self._require_gdb()
            self._sync_stop()
            if self.halted_since is None:
                gdb.discard_stops()
                gdb.command("-exec-interrupt")
                stop = gdb.wait_stop(6)
                if stop is None:
                    raise DebugError("Target did not report a halt")
                self.halted_since = time.monotonic()
            return {"state": "halted", "details": self.state()}

    def run_until_stop(self, seconds: int) -> dict:
        with self.lock:
            gdb = self._require_symbols()
            if self.halted_since is None:
                raise DebugError("Target is already running")
            if not 1 <= seconds <= 30:
                raise DebugError("Run timeout must be 1-30 seconds")
            gdb.discard_stops()
            gdb.command("-exec-continue")
            self.halted_since = None
            stop = gdb.wait_stop(seconds)
            if stop is None:
                try:
                    gdb.command("-exec-interrupt")
                    stop = gdb.wait_stop(6)
                except DebugError:
                    self.close()
                    raise
                if stop is None:
                    self.close()
                    raise DebugError("Timed out and could not confirm target halt; session closed")
                reason = "timeout-interrupted"
            else:
                reason = "target-stopped"
            self.halted_since = time.monotonic()
            return {"reason": reason, "stop": stop, "details": self.state()}

    def step(self, kind: str) -> dict:
        with self.lock:
            gdb = self._require_symbols()
            if self.halted_since is None:
                raise DebugError("Pause the target before stepping")
            commands = {"into": "-exec-step", "over": "-exec-next", "instruction": "-exec-step-instruction"}
            if kind not in commands:
                raise DebugError("Step kind must be into, over, or instruction")
            gdb.discard_stops()
            gdb.command(commands[kind])
            self.halted_since = None
            stop = gdb.wait_stop(8)
            if stop is None:
                try:
                    gdb.command("-exec-interrupt")
                    stop = gdb.wait_stop(6)
                except DebugError:
                    self.close()
                    raise
                if stop is None:
                    self.close()
                    raise DebugError("Step did not report a stop; session closed")
                reason = "timeout-interrupted"
            else:
                reason = "step-complete"
            self.halted_since = time.monotonic()
            return {"reason": reason, "stop": stop, "details": self.state()}

    def close(self) -> dict:
        with self.lock:
            if self.closed:
                return {"state": "closed"}
            self.closed = True
            state = "unknown"
            if self.gdb is not None:
                try:
                    if self.halted_since is not None:
                        self.gdb.command("-exec-continue", timeout=3)
                    state = "running; detach pending"
                    self.gdb.command("-target-detach", timeout=3)
                    state = "running and detached"
                except (DebugError, OSError):
                    pass
                self.gdb.close()
            if self.openocd is not None and self.openocd.poll() is None:
                self.openocd.terminate()
                try:
                    self.openocd.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.openocd.kill()
            return {"state": "closed", "target_state": state}


class Bridge:
    def __init__(self):
        self.session: DebugSession | None = None

    def environment(self) -> dict:
        return {"openocd": shutil.which("openocd"),
                "arm_none_eabi_gdb": shutil.which("arm-none-eabi-gdb"),
                "local_debug_access": "not yet tested"}

    def probe(self, target: str) -> dict:
        if target not in TARGETS:
            raise DebugError(f"Unsupported target family: {target}")
        if self.session is not None and not self.session.closed:
            raise DebugError("Close the current session before probing")
        executable = shutil.which("openocd")
        if executable is None:
            raise DebugError("Install OpenOCD on the host PATH")
        try:
            result = subprocess.run(
                [executable, "-f", "interface/stlink.cfg", "-f", f"target/{target}.cfg",
                 "-c", "tcl_port disabled", "-c", "telnet_port disabled",
                 "-c", "gdb_port disabled", "-c", "init; targets; shutdown"],
                capture_output=True, text=True, timeout=15, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DebugError("OpenOCD probe timed out") from exc
        output = (result.stdout + result.stderr)[-6000:]
        if result.returncode != 0:
            raise DebugError("OpenOCD could not attach: " + output)
        return {"target_family": target, "openocd_output": output}

    def start(self, target: str, elf_path: str | None = None) -> dict:
        if self.session is not None and not self.session.closed:
            raise DebugError("Close the current session before opening another")
        session = DebugSession(target, elf_path)
        result = session.start()
        self.session = session
        return result

    def current(self, session_id: str) -> DebugSession:
        if self.session is None or self.session.closed or self.session.id != session_id:
            raise DebugError("Unknown or closed debug session")
        return self.session

    def close(self) -> dict:
        if self.session is None:
            return {"state": "closed"}
        return self.session.close()
