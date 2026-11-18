"""Dependency-free MCP stdio entry point for the local debugger bridge."""

from __future__ import annotations

import atexit
import json
import signal
import sys

from .debugger import Bridge, DebugError


def tool(name: str, description: str, properties: dict, required: list[str] | None = None,
         read_only: bool = False) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": properties,
                        "required": required or [], "additionalProperties": False},
        "annotations": {"readOnlyHint": read_only, "destructiveHint": False,
                        "openWorldHint": False},
    }


SESSION = {"session_id": {"type": "string", "description": "ID returned by debug_start"}}
TOOLS = [
    tool("debug_environment", "Check host OpenOCD and Arm GDB availability.", {}, read_only=True),
    tool("debug_probe", "Identify the ST-LINK and target through OpenOCD without opening a persistent GDB session.",
         {"target": {"type": "string", "description": "OpenOCD target family, for example stm32f4x"}},
         ["target"]),
    tool("debug_start", "Attach ST-LINK to one STM32 and halt briefly. If an ELF is supplied, compare its flash bytes to the running image. Never flashes or resets.",
         {"target": {"type": "string", "description": "OpenOCD target family, for example stm32f4x"},
          "elf_path": {"type": "string", "description": "Optional absolute path to an application ELF with symbols"}},
         ["target"]),
    tool("debug_state", "Read PC, registers, and stack frames while halted; source frames require an exact ELF match.",
         SESSION, ["session_id"], read_only=True),
    tool("debug_read_memory", "Read at most 256 bytes while halted. Some peripheral registers have read side effects.",
         {**SESSION, "address": {"type": "integer", "minimum": 0, "maximum": 4294967295},
          "size": {"type": "integer", "minimum": 1, "maximum": 256}},
         ["session_id", "address", "size"]),
    tool("debug_breakpoint", "Set a hardware breakpoint by function, file:line, or *0xaddress. Requires exact ELF match and a halted target.",
         {**SESSION, "location": {"type": "string"}}, ["session_id", "location"]),
    tool("debug_delete_breakpoint", "Remove a debugger breakpoint by its number.",
         {**SESSION, "number": {"type": "integer", "minimum": 1}}, ["session_id", "number"]),
    tool("debug_evaluate", "Read a simple variable or member expression while halted; calls and assignments are rejected.",
         {**SESSION, "expression": {"type": "string"}}, ["session_id", "expression"]),
    tool("debug_resume", "Resume a halted target.", SESSION, ["session_id"]),
    tool("debug_pause", "Halt a running target for inspection.", SESSION, ["session_id"]),
    tool("debug_run", "Continue until a breakpoint or a bounded timeout, then halt for inspection.",
         {**SESSION, "seconds": {"type": "integer", "minimum": 1, "maximum": 30}},
         ["session_id", "seconds"]),
    tool("debug_step", "Step into, over, or by one instruction while halted. Requires exact ELF match.",
         {**SESSION, "kind": {"type": "string", "enum": ["into", "over", "instruction"]}},
         ["session_id", "kind"]),
    tool("debug_close", "Resume if halted, detach GDB, and stop this bridge's OpenOCD process.",
         SESSION, ["session_id"]),
]


def dispatch(bridge: Bridge, name: str, args: dict) -> dict:
    if name == "debug_environment":
        return bridge.environment()
    if name == "debug_probe":
        return bridge.probe(args["target"])
    if name == "debug_start":
        return bridge.start(args["target"], args.get("elf_path"))
    if name not in {item["name"] for item in TOOLS}:
        raise DebugError(f"Unknown tool: {name}")
    session = bridge.current(args["session_id"])
    if name == "debug_state":
        return session.state()
    if name == "debug_read_memory":
        return session.memory(args["address"], args["size"])
    if name == "debug_breakpoint":
        return session.breakpoint(args["location"])
    if name == "debug_delete_breakpoint":
        return session.delete_breakpoint(args["number"])
    if name == "debug_evaluate":
        return session.evaluate(args["expression"])
    if name == "debug_resume":
        return session.resume()
    if name == "debug_pause":
        return session.pause()
    if name == "debug_run":
        return session.run_until_stop(args["seconds"])
    if name == "debug_step":
        return session.step(args["kind"])
    if name == "debug_close":
        return session.close()
    raise DebugError(f"Unknown tool: {name}")


def response(message_id: object, result: dict | None = None, error: dict | None = None) -> None:
    payload = {"jsonrpc": "2.0", "id": message_id}
    payload["error" if error is not None else "result"] = error if error is not None else result
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main() -> None:
    bridge = Bridge()
    atexit.register(bridge.close)
    def stop(signum: int, _frame: object) -> None:
        bridge.close()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                continue
            message_id = request.get("id")
            method = request.get("method")
            if method == "notifications/initialized" or method is None:
                continue
            if message_id is None:
                continue  # JSON-RPC notifications must not operate hardware.
            if method == "initialize":
                response(message_id, {"protocolVersion": "2025-06-18",
                                      "capabilities": {"tools": {}},
                                      "serverInfo": {"name": "stm32-debug", "version": "0.4.0"}})
            elif method == "ping":
                response(message_id, {})
            elif method == "tools/list":
                response(message_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = request.get("params")
                if not isinstance(params, dict):
                    response(message_id, error={"code": -32602, "message": "Invalid params"})
                    continue
                name = params.get("name")
                args = params.get("arguments", {})
                if not isinstance(args, dict):
                    response(message_id, error={"code": -32602, "message": "Invalid arguments"})
                    continue
                try:
                    value = dispatch(bridge, name, args)
                    response(message_id, {"content": [{"type": "text", "text": json.dumps(value)}],
                                          "structuredContent": value})
                except (DebugError, OSError, ValueError, KeyError, TypeError) as exc:
                    response(message_id, {"content": [{"type": "text", "text": str(exc)}],
                                          "isError": True})
            elif message_id is not None:
                response(message_id, error={"code": -32601, "message": "Method not found"})
        except (json.JSONDecodeError, TypeError) as exc:
            print(f"Invalid MCP message: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
