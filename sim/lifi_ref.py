"""lifi_ref.py - Python reference of the Li-Fi BFSK link.

Mirrors common/lifi_proto.h and common/lifi_demod.h line for line (framing,
CRC-16/CCITT-FALSE, Hamming(7,4), multi-phase Goertzel demod with preamble
timing recovery and tracking) plus the extra receivers used for comparison in
the simulation (ideal-timing Goertzel, non-coherent filter bank, and the
digital-line DPLL used behind an XR2211 on the Arduino Uno).

Float32 is used where the C code uses float so the window boundaries and the
decisions match the firmware bit for bit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

PREAMBLE_BYTE = 0xAA
PREAMBLE_LEN = 4
SYNC_PLAIN = 0x2DD4
SYNC_FEC = 0xD263
MAX_PAYLOAD = 255
SYNC_MAX_ERRS = 0
PRE_MAX_ERRS = 1
BERT_MARKER = 0xB5
BERT_PRBS_BYTES = 32
BERT_LEN = 2 + BERT_PRBS_BYTES

F32 = np.float32


# ------------------------------------------------------------------ CRC / FEC / PRBS
def crc16_update(crc: int, b: int) -> int:
    crc ^= (b & 0xFF) << 8
    for _ in range(8):
        crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc = crc16_update(crc, b)
    return crc


def ham74_encode(nib: int) -> int:
    d1, d2, d3, d4 = (nib >> 3) & 1, (nib >> 2) & 1, (nib >> 1) & 1, nib & 1
    p1, p2, p3 = d1 ^ d2 ^ d4, d1 ^ d3 ^ d4, d2 ^ d3 ^ d4
    return (p1 << 6) | (p2 << 5) | (d1 << 4) | (p3 << 3) | (d2 << 2) | (d3 << 1) | d4


def ham74_decode(cw: int):
    c = [0] + [(cw >> (7 - i)) & 1 for i in range(1, 8)]
    s = (c[1] ^ c[3] ^ c[5] ^ c[7]) | ((c[2] ^ c[3] ^ c[6] ^ c[7]) << 1) | ((c[4] ^ c[5] ^ c[6] ^ c[7]) << 2)
    if s:
        c[s] ^= 1
    return (c[3] << 3) | (c[5] << 2) | (c[6] << 1) | c[7], 1 if s else 0


def prbs9(n: int, seed: int = 0x1FF) -> bytes:
    s = (seed & 0x1FF) or 0x1FF
    out = bytearray()
    for _ in range(n):
        b = 0
        for _ in range(8):
            nb = ((s >> 8) ^ (s >> 4)) & 1
            s = ((s << 1) | nb) & 0x1FF
            b = (b << 1) | nb
        out.append(b)
    return bytes(out)


def bert_payload(seq: int) -> bytes:
    return bytes([BERT_MARKER, seq & 0xFF]) + prbs9(BERT_PRBS_BYTES)


def bert_errors(payload: bytes) -> int:
    ref = prbs9(BERT_PRBS_BYTES)
    return sum(bin(a ^ b).count("1") for a, b in zip(payload[2:2 + BERT_PRBS_BYTES], ref))


# ------------------------------------------------------------------ framing
def _byte_bits(b: int, n: int = 8) -> List[int]:
    return [(b >> (n - 1 - i)) & 1 for i in range(n)]


def build_frame_bits(payload: bytes, fec: bool = False) -> np.ndarray:
    """Bits on air for one frame, identical to lifi_txf_next() output."""
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too long")
    sync = SYNC_FEC if fec else SYNC_PLAIN
    bits: List[int] = []
    for _ in range(PREAMBLE_LEN):
        bits += _byte_bits(PREAMBLE_BYTE)
    bits += _byte_bits(sync, 16)
    body = bytes([len(payload)]) + payload
    c = crc16(body)
    body += bytes([c >> 8, c & 0xFF])
    for b in body:
        if fec:
            bits += _byte_bits((ham74_encode(b >> 4) << 7) | ham74_encode(b & 0xF), 14)
        else:
            bits += _byte_bits(b)
    return np.array(bits, dtype=np.uint8)


def frame_bit_count(n: int, fec: bool) -> int:
    return (PREAMBLE_LEN + 2) * 8 + (n + 3) * (14 if fec else 8)


def sync_match(sr: int) -> int:
    s = sr & 0xFFFF
    pre = (sr >> 16) & 0xFF
    if bin(pre ^ PREAMBLE_BYTE).count("1") > PRE_MAX_ERRS:
        return 0
    if bin(s ^ SYNC_PLAIN).count("1") <= SYNC_MAX_ERRS:
        return 1
    if bin(s ^ SYNC_FEC).count("1") <= SYNC_MAX_ERRS:
        return 2
    return 0


@dataclass
class Frame:
    ok: bool
    fec: bool
    length: int
    payload: bytes
    crc_rx: int
    crc_calc: int
    corrected: int = 0
    rssi_db: float = 0.0
    snr_db: float = 0.0
    quality: float = 0.0
    phase: int = 0
    phase_moves: int = 0
    sample_index: int = 0


class Deframer:
    """Mirror of lifi_deframer_t."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.sr = 0
        self.hunting = True

    def start_body(self, fec: bool):
        self.hunting = False
        self.fec = fec
        self.word = 0
        self.nbits = 0
        self.idx = 0
        self.crc = 0xFFFF
        self.corrected = 0
        self.length = 0
        self.buf = bytearray()
        self.crc_rx = 0

    def push(self, bit: int):
        """Returns ('sync', None), ('frame', Frame) or None."""
        if self.hunting:
            self.sr = ((self.sr << 1) | bit) & 0xFFFFFFFF
            m = sync_match(self.sr)
            if m:
                self.start_body(m == 2)
                return ("sync", None)
            return None
        self.word = ((self.word << 1) | bit) & 0xFFFF
        self.nbits += 1
        need = 14 if self.fec else 8
        if self.nbits < need:
            return None
        if self.fec:
            hi, f1 = ham74_decode((self.word >> 7) & 0x7F)
            lo, f2 = ham74_decode(self.word & 0x7F)
            self.corrected += f1 + f2
            b = (hi << 4) | lo
        else:
            b = self.word & 0xFF
        self.word = 0
        self.nbits = 0
        j = self.idx
        self.idx += 1
        if j == 0:
            self.length = b
            self.crc = crc16_update(self.crc, b)
            return None
        if j <= self.length:
            self.buf.append(b)
            self.crc = crc16_update(self.crc, b)
            return None
        if j == self.length + 1:
            self.crc_rx = b << 8
            return None
        self.crc_rx |= b
        fr = Frame(ok=self.crc_rx == self.crc, fec=self.fec, length=self.length, payload=bytes(self.buf),
                   crc_rx=self.crc_rx, crc_calc=self.crc, corrected=self.corrected)
        self.reset()
        return ("frame", fr)


def deframe_bits(bits) -> List[Frame]:
    d = Deframer()
    out = []
    for b in bits:
        r = d.push(int(b))
        if r and r[0] == "frame":
            out.append(r[1])
    return out


# ------------------------------------------------------------------ modulator
def modulate(bits, fs: float, rb: float, f0: float, f1: float, wave: str = "square",
             continuous_phase: bool = True, idle_pre: int = 16, idle_post: int = 8,
             idle: str = "mark") -> np.ndarray:
    """LED drive waveform in 0..1 (0 = LED off, 1 = LED fully on).

    continuous_phase=True  : DDS phase accumulator (tx_esp32 MODE_DDS / Uno Timer1)
    continuous_phase=False : phase restarts at each bit (models a timer reload per bit)
    idle = 'mark' (f1 tone), 'off' (LED off), 'on' (LED steady on)
    """
    seq = [("idle", None)] * idle_pre + [("bit", int(b)) for b in bits] + [("idle", None)] * idle_post
    spb = fs / rb
    n_total = int(round(len(seq) * spb))
    out = np.empty(n_total)
    phase = 0.0
    t0 = 0
    for k, (kind, b) in enumerate(seq):
        t1 = int(round((k + 1) * spb))
        n = t1 - t0
        if kind == "idle" and idle != "mark":
            out[t0:t1] = 0.0 if idle == "off" else 1.0
            t0 = t1
            continue
        f = f1 if (kind == "idle" or b == 1) else f0
        if not continuous_phase:
            phase = 0.0
        ph = phase + 2 * np.pi * f / fs * np.arange(n)
        if wave == "square":
            out[t0:t1] = (np.mod(ph, 2 * np.pi) < np.pi).astype(float)
        else:
            out[t0:t1] = 0.5 + 0.5 * np.sin(ph)
        phase = (phase + 2 * np.pi * f / fs * n) % (2 * np.pi)
        t0 = t1
    return out


# ------------------------------------------------------------------ Goertzel demod (mirror of lifi_demod.h)
class GoertzelDemod:
    PHASES = 8
    TRACK_HYST = F32(0.10)
    AVG_K = F32(0.125)
    TRACK_K = F32(0.03125)

    def __init__(self, fs: float, rb: float, f0: float, f1: float, phases: int = 8):
        self.PHASES = phases
        self.fs, self.rb, self.f0, self.f1 = F32(fs), F32(rb), F32(f0), F32(f1)
        self.spb = F32(self.fs / self.rb)
        w0 = F32(2.0) * F32(math.pi) * self.f0 / self.fs
        w1 = F32(2.0) * F32(math.pi) * self.f1 / self.fs
        self.c0 = F32(2.0) * F32(math.cos(w0))
        self.c1 = F32(2.0) * F32(math.cos(w1))
        self.hp_alpha = F32(1.0 / 16.0)
        self.m1 = F32(0)
        self.m2 = F32(0)
        P = self.PHASES
        self.q = np.zeros((P, 4), dtype=F32)  # q0a q0b q1a q1b
        self.n = [0] * P
        self.win = [0] * P
        self.frac = [F32(0)] * P
        self.avg_q = [F32(0)] * P
        self.avg_t = [F32(0)] * P
        self.sr = [0] * P
        self.primed = [False] * P
        for p in range(P):
            x = F32(F32(p) * self.spb / F32(P) + self.spb)
            self.win[p] = int(x)
            self.frac[p] = F32(x - F32(self.win[p]))
        self.lock = -1
        self.skip_next = False
        self.df = Deframer()
        self.t = 0
        self.frames: List[Frame] = []
        self.syncs = 0
        self.decisions = []  # (sample, phase, bit, P0, P1) of locked phase (for plots)
        self._reset_acc()

    def _reset_acc(self):
        self.acc_pmax = 0.0
        self.acc_pmin = 0.0
        self.acc_mag = 0.0
        self.acc_q = 0.0
        self.nsym = 0
        self.moves = 0

    def _unlock(self):
        self.lock = -1
        self.skip_next = False
        self.sr = [0] * self.PHASES
        self.df.reset()

    def _emit(self, p: int):
        q0a, q0b, q1a, q1b = self.q[p]
        P0 = F32(q0a * q0a + q0b * q0b - self.c0 * q0a * q0b)
        P1 = F32(q1a * q1a + q1b * q1b - self.c1 * q1a * q1b)
        P0 = max(P0, F32(0))
        P1 = max(P1, F32(0))
        n = F32(self.win[p])
        self.q[p] = 0
        self.n[p] = 0
        x = F32(self.spb + self.frac[p])
        self.win[p] = int(x)
        self.frac[p] = F32(x - F32(self.win[p]))
        if not self.primed[p]:
            self.primed[p] = True
            return 0
        m = F32((P1 - P0) / (P1 + P0 + F32(1e-20)))
        bit = 1 if m > 0 else 0
        qq = F32(abs(m))
        self.avg_q[p] = F32(self.avg_q[p] + (qq - self.avg_q[p]) * self.AVG_K)
        self.avg_t[p] = F32(self.avg_t[p] + (qq - self.avg_t[p]) * self.TRACK_K)
        a0 = F32(2.0) * F32(math.sqrt(P0)) / n
        a1 = F32(2.0) * F32(math.sqrt(P1)) / n
        if self.lock < 0:
            self.sr[p] = ((self.sr[p] << 1) | bit) & 0xFFFFFFFF
            mt = sync_match(self.sr[p])
            if mt:
                P = self.PHASES
                best = p
                for k in range(P):
                    if self.avg_q[k] > self.avg_q[best]:
                        best = k
                off = (best - p + P) % P
                self.lock = best
                self.skip_next = 1 <= off <= P // 2
                self.df.start_body(mt == 2)
                self._reset_acc()
                self.syncs += 1
                return 1
            return 0
        if p != self.lock:
            return 0
        if self.skip_next:
            self.skip_next = False
            return 0
        self.decisions.append((self.t, p, bit, float(P0), float(P1)))
        self.acc_pmax += float(P1 if bit else P0)
        self.acc_pmin += float(P0 if bit else P1)
        self.acc_mag += float(a1 if bit else a0)
        self.acc_q += float(qq)
        self.nsym += 1
        r = self.df.push(bit)
        if r and r[0] == "frame":
            fr = r[1]
            ns = self.nsym or 1
            fr.rssi_db = 20 * math.log10(self.acc_mag / ns + 1e-9)
            fr.snr_db = 10 * math.log10((self.acc_pmax + 1e-20) / (self.acc_pmin + 1e-20))
            fr.quality = self.acc_q / ns
            fr.phase = self.lock
            fr.phase_moves = self.moves
            fr.sample_index = self.t
            self.frames.append(fr)
            self._unlock()
            return 2
        P = self.PHASES
        pm, pp = (p + P - 1) % P, (p + 1) % P
        cur = F32(self.avg_t[p] * (F32(1.0) + self.TRACK_HYST) + F32(0.01))
        qm, qp = self.avg_t[pm], self.avg_t[pp]
        if qp > cur and qp >= qm:
            self.lock = pp
            self.skip_next = True
            self.moves += 1
        elif qm > cur:
            self.lock = pm
            self.moves += 1
        return 0

    def push(self, x: float) -> int:
        x = F32(x)
        self.m1 = F32(self.m1 + self.hp_alpha * (x - self.m1))
        y1 = F32(x - self.m1)
        self.m2 = F32(self.m2 + self.hp_alpha * (y1 - self.m2))
        y = F32(y1 - self.m2)
        ret = 0
        for p in range(self.PHASES):
            q = self.q[p]
            s0 = F32(y + self.c0 * q[0] - q[1])
            q[1] = q[0]
            q[0] = s0
            s1 = F32(y + self.c1 * q[2] - q[3])
            q[3] = q[2]
            q[2] = s1
            self.n[p] += 1
            if self.n[p] >= self.win[p]:
                ret = max(ret, self._emit(p))
        self.t += 1
        return ret

    def process(self, samples) -> List[Frame]:
        start = len(self.frames)
        for x in samples:
            self.push(x)
        return self.frames[start:]


# ------------------------------------------------------------------ comparison receivers (ideal bit timing)
def goertzel_power_blocks(x: np.ndarray, n: int, f: float, fs: float) -> np.ndarray:
    """Goertzel power for consecutive blocks of n samples (vectorised; identical
    to running the Goertzel recursion over each block)."""
    nb = len(x) // n
    blk = x[: nb * n].reshape(nb, n)
    k = np.arange(n)
    e = np.exp(-2j * np.pi * f / fs * k)
    return np.abs(blk @ e) ** 2


def demod_goertzel_ideal(x, fs, rb, f0, f1, offset=0):
    n = int(round(fs / rb))
    y = x[offset:]
    P0 = goertzel_power_blocks(y, n, f0, fs)
    P1 = goertzel_power_blocks(y, n, f1, fs)
    return (P1 > P0).astype(np.uint8), P0, P1


def demod_filterbank(x, fs, rb, f0, f1, offset=0, order=2, bw=None, delay=None):
    """Classic non-coherent receiver: two band-pass filters, square-law
    envelope, integrate-and-dump over the bit, compare."""
    from scipy.signal import butter, sosfilt
    bw = bw or 1.5 * rb   # best of 1-3 x Rb in the simulation sweep
    n = int(round(fs / rb))
    out = []
    for f in (f0, f1):
        sos = butter(order, [f - bw / 2, f + bw / 2], btype="bandpass", fs=fs, output="sos")
        y = sosfilt(sos, x)
        out.append(y * y)
    if delay is None:
        delay = 0
    e0 = out[0][offset + delay:]
    e1 = out[1][offset + delay:]
    nb = min(len(e0), len(e1)) // n
    E0 = e0[: nb * n].reshape(nb, n).sum(1)
    E1 = e1[: nb * n].reshape(nb, n).sum(1)
    return (E1 > E0).astype(np.uint8), E0, E1


def ber_theory_ncfsk(ebn0_lin):
    return 0.5 * np.exp(-np.asarray(ebn0_lin) / 2.0)


# ------------------------------------------------------------------ XR2211 data-line decoder (mirror of rx_arduino_uno_xr2211)
class DigitalLineDecoder:
    """8x oversampled DPLL on a 0/1 data line (XR2211 DATA OUT -> GPIO).

    Mirror of rx_arduino_uno_xr2211.ino: counter c runs 0..OS-1; the bit is the
    majority of the samples at c = OS/2-1, OS/2, OS/2+1. On an edge the counter
    is reset to 0 while hunting, and nudged one step towards the edge once a
    sync word was found. Sync is searched in both polarities.
    """

    OS = 8

    def __init__(self):
        self.c = 0
        self.prev = 1
        self.votes = 0
        self.sr = 0
        self.invert = 0
        self.df = Deframer()
        self.frames: List[Frame] = []

    def _bit(self, bit: int):
        if self.df.hunting:
            self.sr = ((self.sr << 1) | bit) & 0xFFFFFFFF
            m, inv = sync_match(self.sr), 0
            if not m:
                m, inv = sync_match(~self.sr & 0xFFFFFFFF), 1
            if m:
                self.invert = inv
                self.df.start_body(m == 2)
            return
        r = self.df.push(bit ^ self.invert)
        if r and r[0] == "frame":
            self.frames.append(r[1])
            self.sr = 0

    def push(self, s: int):
        OS = self.OS
        if s != self.prev:
            if self.df.hunting:
                # hard re-align: an edge in the second half of the bit means the
                # boundary is here already, so finish the current bit first
                if self.c >= OS // 2:
                    self._bit(1 if self.votes >= 2 else 0)
                self.votes = 0
                self.c = 0
            elif self.c != 0:
                self.c += -1 if self.c < OS // 2 else 1  # edge late: slow down / early: speed up
            self.prev = s
        if OS // 2 - 1 <= self.c <= OS // 2 + 1:
            self.votes += s
        self.c += 1
        if self.c >= OS:
            self.c -= OS
            bit = 1 if self.votes >= 2 else 0
            self.votes = 0
            self._bit(bit)

    def process(self, line):
        for s in line:
            self.push(int(s))
        return self.frames
