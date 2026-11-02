"""lifi_link.py - PC-side helpers shared by lifi_tool.py (CLI) and lifi_gui.py.

* parse RX log lines (#FRAME / #BERT / #STAT / RX ...) from rx_esp32 or the Uno receiver
* file transfer layer on top of frames (one-way, no ACK; repeat to beat losses)
* serial wrappers for the TX (text, !hex, !bert) and RX ports
"""
from __future__ import annotations

import struct
import time
import zlib
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

MAX_PAYLOAD = 255
FILE_MAGIC = 0x46  # 'F'
CHUNK_DATA = 200   # data bytes per file chunk (header 8 bytes -> 208 byte payload)


# ------------------------------------------------------------------ log parsing
@dataclass
class FrameEvent:
    ok: bool
    fec: bool
    length: int
    payload: bytes
    rssi_db: Optional[float] = None
    snr_db: Optional[float] = None
    quality: Optional[float] = None
    corrected: int = 0


@dataclass
class BertEvent:
    frames: int
    bits: int
    errors: int
    ber: float
    lost: int = 0


@dataclass
class StatEvent:
    ms: int
    fs_meas: float
    syncs: int
    frames: int
    crc_fail: int
    bert_frames: int
    bert_bits: int
    bert_errs: int
    ber: float
    idle_rssi_db: float


def parse_line(line: str):
    """Parse one receiver log line. Returns FrameEvent/BertEvent/StatEvent or None.

    rx_esp32 : #FRAME,ok,fec,len,rssi,snr,quality,corrected,phase,moves,hex
    Uno      : #FRAME,ok,fec,len,corrected,hex
    """
    line = line.strip()
    try:
        if line.startswith("#FRAME,"):
            p = line.split(",")
            if len(p) >= 11:
                return FrameEvent(p[1] == "1", p[2] == "1", int(p[3]), bytes.fromhex(p[10]),
                                  float(p[4]), float(p[5]), float(p[6]), int(p[7]))
            return FrameEvent(p[1] == "1", p[2] == "1", int(p[3]), bytes.fromhex(p[5]) if len(p) > 5 else b"",
                              corrected=int(p[4]))
        if line.startswith("#BERT,"):
            p = line.split(",")
            return BertEvent(int(p[1]), int(p[2]), int(p[3]), float(p[4]), int(p[5]) if len(p) > 5 else 0)
        if line.startswith("#STAT,"):
            p = line.split(",")
            return StatEvent(int(p[1]), float(p[2]), int(p[3]), int(p[4]), int(p[5]), int(p[6]), int(p[7]),
                             int(p[8]), float(p[9]), float(p[10]))
    except (ValueError, IndexError):
        return None
    return None


# ------------------------------------------------------------------ file transfer
# chunk payload: 'F' | file_id u8 | seq u16 | total u16 | crc32-low16 u16 | data
# seq 0 carries the file name (utf-8); the crc field of seq 0 holds crc32(file) & 0xFFFF
def file_to_chunks(name: str, data: bytes, file_id: int = 1) -> List[bytes]:
    parts = [data[i:i + CHUNK_DATA] for i in range(0, len(data), CHUNK_DATA)] or [b""]
    total = len(parts) + 1
    crc = zlib.crc32(data) & 0xFFFF
    out = [struct.pack(">BBHHH", FILE_MAGIC, file_id & 0xFF, 0, total, crc) + name.encode()[:CHUNK_DATA]]
    for i, p in enumerate(parts, start=1):
        out.append(struct.pack(">BBHHH", FILE_MAGIC, file_id & 0xFF, i, total, zlib.crc32(p) & 0xFFFF) + p)
    return out


@dataclass
class FileAssembly:
    file_id: int
    total: int = 0
    name: str = ""
    crc: int = 0
    parts: Dict[int, bytes] = field(default_factory=dict)

    def missing(self) -> List[int]:
        return [i for i in range(1, self.total) if i not in self.parts]

    def complete(self) -> bool:
        return self.total > 0 and 0 in self.parts and not self.missing()

    def data(self) -> bytes:
        return b"".join(self.parts[i] for i in range(1, self.total))

    def verified(self) -> bool:
        return self.complete() and (zlib.crc32(self.data()) & 0xFFFF) == self.crc


class FileReceiver:
    """Feed CRC-good frame payloads; collects files."""

    def __init__(self):
        self.files: Dict[int, FileAssembly] = {}

    def feed(self, payload: bytes) -> Optional[FileAssembly]:
        if len(payload) < 8 or payload[0] != FILE_MAGIC:
            return None
        _, fid, seq, total, crc = struct.unpack(">BBHHH", payload[:8])
        body = payload[8:]
        fa = self.files.setdefault(fid, FileAssembly(fid))
        fa.total = total
        if seq == 0:
            fa.name = body.decode(errors="replace")
            fa.crc = crc
            fa.parts.setdefault(0, b"")
        elif (zlib.crc32(body) & 0xFFFF) == crc:
            fa.parts[seq] = body
        return fa


# ------------------------------------------------------------------ serial wrappers
def open_port(port: str, baud: int):
    import serial  # pyserial
    s = serial.Serial(port, baud, timeout=0.2)
    time.sleep(2.0)  # boards reset when the port opens
    s.reset_input_buffer()
    return s


def wait_for(ser, prefix: str, timeout: float) -> Optional[str]:
    t0 = time.time()
    while time.time() - t0 < timeout:
        line = ser.readline().decode(errors="replace").strip()
        if line.startswith(prefix):
            return line
    return None


def send_text(ser, text: str, timeout: float = 5.0) -> None:
    for i in range(0, len(text), MAX_PAYLOAD):
        ser.write((text[i:i + MAX_PAYLOAD].replace("\n", " ") + "\n").encode())
        wait_for(ser, "#SENT", timeout)


def send_bytes(ser, payload: bytes, timeout: float = 5.0) -> None:
    ser.write(b"!hex " + payload.hex().encode() + b"\n")
    wait_for(ser, "#SENT", timeout)


def read_lines(ser) -> Iterator[str]:
    while True:
        raw = ser.readline()
        if raw:
            yield raw.decode(errors="replace").rstrip()
