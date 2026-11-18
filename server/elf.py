"""Read loadable flash bytes from an ARM ELF without external dependencies."""

from __future__ import annotations

import struct
from pathlib import Path


class ElfError(ValueError):
    pass


def flash_segments(path: str | Path) -> list[tuple[int, bytes]]:
    data = Path(path).read_bytes()
    if len(data) < 52 or data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 1:
        raise ElfError("Expected a little-endian 32-bit ARM ELF")
    machine = struct.unpack_from("<H", data, 18)[0]
    if machine != 40:
        raise ElfError("ELF machine is not ARM")
    phoff = struct.unpack_from("<I", data, 28)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 42)
    if phentsize < 32 or phnum > 128 or phoff + phnum * phentsize > len(data):
        raise ElfError("Invalid ELF program headers")
    segments: list[tuple[int, bytes]] = []
    for index in range(phnum):
        kind, offset, _, physical, size, _, _, _ = struct.unpack_from(
            "<IIIIIIII", data, phoff + index * phentsize
        )
        if kind != 1 or size == 0 or not 0x08000000 <= physical < 0x10000000:
            continue
        if offset + size > len(data) or physical + size > 0x10000000:
            raise ElfError("Invalid flash segment")
        segments.append((physical, data[offset : offset + size]))
    if not segments or sum(len(blob) for _, blob in segments) > 4 * 1024 * 1024:
        raise ElfError("ELF has no bounded flash image")
    segments.sort()
    for left, right in zip(segments, segments[1:]):
        if left[0] + len(left[1]) > right[0]:
            raise ElfError("Overlapping flash segments")
    return segments
