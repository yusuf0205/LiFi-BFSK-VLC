"""Framing, CRC, Hamming(7,4), PRBS - python reference vs. firmware C code."""
import random
import subprocess

import numpy as np
import pytest

import lifi_ref as L
from conftest import ROOT


def test_crc16_ccitt_false_check_value():
    assert L.crc16(b"123456789") == 0x29B1
    assert L.crc16(b"") == 0xFFFF


@pytest.mark.parametrize("nib", range(16))
def test_hamming74_corrects_every_single_error(nib):
    cw = L.ham74_encode(nib)
    assert L.ham74_decode(cw) == (nib, 0)
    for e in range(7):
        assert L.ham74_decode(cw ^ (1 << e)) == (nib, 1)


def test_hamming_min_distance_3():
    cws = [L.ham74_encode(n) for n in range(16)]
    d = min(bin(a ^ b).count("1") for i, a in enumerate(cws) for b in cws[i + 1:])
    assert d == 3


def test_sync_words_far_apart():
    assert bin(L.SYNC_PLAIN ^ L.SYNC_FEC).count("1") >= 8
    # no 16-bit window of preamble+sync (other than the sync itself) is near a sync word
    for sync in (L.SYNC_PLAIN, L.SYNC_FEC):
        stream = [1, 0] * 16 + [(sync >> (15 - i)) & 1 for i in range(16)]
        for i in range(len(stream) - 16):
            w = int("".join(map(str, stream[i:i + 16])), 2)
            for s in (L.SYNC_PLAIN, L.SYNC_FEC):
                assert bin(w ^ s).count("1") >= 5


def test_prbs9_period_511():
    seq = L.prbs9(511 * 2 // 8 + 2)
    bits = np.unpackbits(np.frombuffer(seq, np.uint8))
    assert np.array_equal(bits[:511], bits[511:1022])
    assert abs(bits[:511].sum() - 256) <= 1


@pytest.mark.parametrize("fec", [False, True])
def test_frame_roundtrip_with_noise_prefix(fec):
    rng = random.Random(4)
    for n in (0, 1, 7, 64, 255):
        payload = bytes(rng.randrange(256) for _ in range(n))
        bits = L.build_frame_bits(payload, fec)
        assert len(bits) == L.frame_bit_count(n, fec)
        junk = np.array([rng.randrange(2) for _ in range(77)], np.uint8)
        frames = L.deframe_bits(np.concatenate([junk, bits]))
        assert frames and frames[-1].ok and frames[-1].payload == payload and frames[-1].fec == fec


def test_crc_detects_flip():
    bits = L.build_frame_bits(b"hello world").copy()
    bits[60] ^= 1
    fr = L.deframe_bits(bits)
    assert fr and not fr[0].ok


def test_hamming_frame_survives_one_error_per_codeword():
    payload = b"FEC test payload"
    bits = L.build_frame_bits(payload, fec=True).copy()
    body_start = (L.PREAMBLE_LEN + 2) * 8
    n_cw = (len(bits) - body_start) // 7
    rng = random.Random(1)
    for k in range(n_cw):
        bits[body_start + 7 * k + rng.randrange(7)] ^= 1
    fr = L.deframe_bits(bits)
    assert fr[0].ok and fr[0].payload == payload and fr[0].corrected == n_cw


def test_bert_payload_and_error_count():
    p = bytearray(L.bert_payload(5))
    assert len(p) == L.BERT_LEN and p[0] == L.BERT_MARKER and p[1] == 5
    assert L.bert_errors(bytes(p)) == 0
    p[10] ^= 0x81
    assert L.bert_errors(bytes(p)) == 2


def test_c_tx_framer_matches_python(host_harness):
    rng = random.Random(9)
    for fec in (0, 1):
        for n in (0, 3, 40, 255):
            payload = bytes(rng.randrange(256) for _ in range(n))
            out = subprocess.run([str(host_harness), "txbits", payload.hex() or "-", str(fec)],
                                 capture_output=True, text=True, check=True).stdout.strip()
            assert out == "".join(map(str, L.build_frame_bits(payload, bool(fec))))


def test_sketch_header_copies_are_identical():
    for sketch, files in {"tx_esp32": ["lifi_proto.h"], "rx_esp32": ["lifi_proto.h", "lifi_demod.h"],
                          "tx_arduino_uno": ["lifi_proto.h"], "rx_arduino_uno_xr2211": ["lifi_proto.h"]}.items():
        for f in files:
            assert (ROOT / sketch / f).read_bytes() == (ROOT / "common" / f).read_bytes(), \
                f"{sketch}/{f} differs from common/ - run tools/sync_common.py"
