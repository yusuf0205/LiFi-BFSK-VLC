"""Goertzel demodulator, timing recovery, channel impairments, XR2211 path."""
import math

import numpy as np
import pytest

import lifi_ref as L
import run_sim as R
from channel import Channel

FS, RB, F0, F1 = R.FS_ADC, R.RB, R.F0, R.F1
MSG = b"Li-Fi pytest message 0123456789"


def test_goertzel_recursion_equals_dft_power():
    rng = np.random.default_rng(0)
    x = rng.standard_normal(48 * 5)
    blocks = L.goertzel_power_blocks(x, 48, F0, FS)
    c = 2 * math.cos(2 * math.pi * F0 / FS)
    for b in range(5):
        q1 = q2 = 0.0
        for v in x[48 * b:48 * (b + 1)]:
            q1, q2 = v + c * q1 - q2, q1
        assert abs((q1 * q1 + q2 * q2 - c * q1 * q2) - blocks[b]) < 1e-9 * max(1, blocks[b])


def _chain(payloads, fec=False, cp=True, sine=False, ebn0=None, ppm=0.0, dc=0.6, flick=0.3, seed=2):
    ch = Channel(swing_v=0.5, ambient_dc_v=dc, flicker_v=flick, clock_ppm=ppm, seed=seed)
    if ebn0 is not None:
        ch.noise_v = R.sigma_for(ebn0, R.calibrate_pwin(ch, sine, cp))
    _, drive = R.tx_stream(payloads, fec=fec, sine=sine, cp=cp)
    return ch.sample(ch.analog(drive))


@pytest.mark.parametrize("kw", [
    dict(),
    dict(fec=True),
    dict(cp=False),
    dict(sine=True, flick=0.8),
    dict(ppm=300),
    dict(ppm=-300, ebn0=16),
    dict(ebn0=15, fec=True, ppm=100),
])
def test_python_demod_decodes_message(kw):
    x = _chain([MSG, b"second"], **kw)
    fr = L.GoertzelDemod(FS, RB, F0, F1).process(x)
    assert [f.payload for f in fr if f.ok] == [MSG, b"second"]


def test_python_and_firmware_c_demod_agree(host_harness):
    x = _chain([MSG, L.bert_payload(1), b"third frame"], ebn0=13, ppm=150, seed=5)
    py = [(f.ok, f.payload) for f in L.GoertzelDemod(FS, RB, F0, F1).process(x)]
    c = [(f["ok"], f["payload"]) for f in R.c_demod(host_harness, x)]
    assert py == c and len(py) == 3


def test_fractional_samples_per_bit():
    # 44.1 kSps / 1 kbps = 44.1 samples per bit (non-integer) must still decode
    from scipy.signal import resample_poly
    x = _chain([MSG], dc=0.2, flick=0.1)
    y = resample_poly(x - x.mean(), 441, 480) + x.mean()
    fr = L.GoertzelDemod(44100.0, RB, F0, F1).process(y)
    assert fr and fr[0].ok and fr[0].payload == MSG


def test_rssi_tracks_signal_level():
    a = L.GoertzelDemod(FS, RB, F0, F1).process(_chain([MSG]))[0]
    ch = Channel(swing_v=0.125, ambient_dc_v=0.6, flicker_v=0.3, seed=2)
    _, drive = R.tx_stream([MSG])
    b = L.GoertzelDemod(FS, RB, F0, F1).process(ch.sample(ch.analog(drive)))[0]
    assert abs((a.rssi_db - b.rssi_db) - 12.0) < 1.0  # 4x amplitude = 12 dB


def test_ber_matches_noncoherent_theory():
    rng = np.random.default_rng(3)
    bits = rng.integers(0, 2, 60000).astype(np.uint8)
    from channel import modulate_fast
    x0 = modulate_fast(bits, FS, RB, F0, F1, "sine") - 0.5
    _, P0, P1 = L.demod_goertzel_ideal(x0, FS, RB, F0, F1)
    pw = float(np.mean(np.where(bits > 0, P1, P0)))
    for eb in (6.0, 9.0):
        x = x0 + R.sigma_for(eb, pw) * rng.standard_normal(len(x0))
        ber = np.mean(L.demod_goertzel_ideal(x, FS, RB, F0, F1)[0] != bits)
        th = L.ber_theory_ncfsk(10 ** (eb / 10))
        assert 0.8 * th < ber < 1.2 * th, (eb, ber, th)


@pytest.mark.parametrize("ppm,invert", [(0, False), (2000, True), (-2000, False)])
def test_xr2211_line_dpll_decoder(ppm, invert):
    from scipy.signal import butter, sosfilt
    ch = Channel(swing_v=0.3, ambient_dc_v=0.4, flicker_v=0.2, noise_v=0.02, clock_ppm=ppm, seed=8)
    _, drive = R.tx_stream([MSG, b"two"])
    x = ch.sample(ch.analog(drive)) * ch.lsb()
    e = []
    for f in (F0, F1):
        y = sosfilt(butter(2, [f - 1500, f + 1500], btype="bandpass", fs=FS, output="sos"), x)
        e.append(sosfilt(butter(2, 0.6 * RB, fs=FS, output="sos"), y * y))
    line = (e[1] > e[0]).astype(int)
    if invert:
        line = 1 - line
    fr = L.DigitalLineDecoder().process(line[:: int(FS / RB) // 8])
    assert [f.payload for f in fr if f.ok] == [MSG, b"two"]
