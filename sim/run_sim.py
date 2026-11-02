#!/usr/bin/env python3
"""run_sim.py - end-to-end simulation of the Li-Fi BFSK link.

Produces (in sim/out/):
  waveforms.png      bits -> LED drive -> received ADC signal -> after DC removal -> Goertzel decisions
  spectrum.png       PSD of the LED drive (harmonics, LED/front-end LPF) and of the ADC signal
  ber_curve.png      BER vs Eb/N0: theory 0.5 exp(-Eb/2N0) vs Goertzel / filter-bank / full firmware chain
  ber_distance.png   BER vs distance with the link budget in channel.LinkBudget
  results.json       all numbers

Usage: python run_sim.py [--quick]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.signal import welch  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lifi_ref as L  # noqa: E402
from channel import Channel, LinkBudget, modulate_fast  # noqa: E402

OUT = HERE / "out"
FS_ADC, RB, F0, F1 = 48000.0, 1000.0, 10000.0, 15000.0
FS_SIM = 480e3
N = int(FS_ADC / RB)
MSG = b"Hello Li-Fi from NIT Puducherry! BFSK 10k/15k @ 1 kbps"


# ------------------------------------------------------------------ host build of the firmware demod
def find_cxx():
    for c in ("g++", "clang++", "c++"):
        if shutil.which(c):
            return [c]
    try:
        import ziglang  # noqa: F401
        return [sys.executable, "-m", "ziglang", "c++"]
    except ImportError:
        return None


def build_host_harness() -> Path | None:
    exe = HERE.parent / "tests" / "host" / "host_harness"
    src = HERE.parent / "tests" / "host" / "host_harness.cpp"
    if exe.exists() and exe.stat().st_mtime > max(src.stat().st_mtime,
                                                    (HERE.parent / "common" / "lifi_demod.h").stat().st_mtime,
                                                    (HERE.parent / "common" / "lifi_proto.h").stat().st_mtime):
        return exe
    cxx = find_cxx()
    if not cxx:
        return None
    r = subprocess.run(cxx + ["-O2", "-std=c++11", "-Wall", "-Wextra", "-I", str(HERE.parent / "common"),
                              str(src), "-o", str(exe)], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr)
        return None
    return exe


def c_demod(exe: Path, samples: np.ndarray):
    """Run the firmware's lifi_demod.h (compiled for the PC) on samples."""
    with tempfile.NamedTemporaryFile(suffix=".f32", delete=False) as f:
        samples.astype(np.float32).tofile(f)
        path = f.name
    try:
        r = subprocess.run([str(exe), "demod", path, str(FS_ADC), str(RB), str(F0), str(F1)],
                           capture_output=True, text=True, check=True)
    finally:
        os.unlink(path)
    frames = []
    for line in r.stdout.splitlines():
        if line.startswith("#FRAME,"):
            p = line.split(",")
            frames.append(dict(ok=p[1] == "1", fec=p[2] == "1", length=int(p[3]), rssi_db=float(p[4]),
                               snr_db=float(p[5]), quality=float(p[6]), corrected=int(p[7]),
                               payload=bytes.fromhex(p[11]) if len(p) > 11 else b""))
    return frames


# ------------------------------------------------------------------ helpers
def tx_stream(frames_payloads, fec=False, gap_bits=24, lead_bits=40, sine=False, cp=True, fs=None):
    """Concatenate frames with mark-idle gaps into one bit stream and modulate."""
    bits = [np.ones(lead_bits, np.uint8)]
    for p in frames_payloads:
        bits.append(np.ones(gap_bits, np.uint8))
        bits.append(L.build_frame_bits(p, fec))
    bits.append(np.ones(gap_bits, np.uint8))
    b = np.concatenate(bits)
    return b, modulate_fast(b, fs or FS_SIM, RB, F0, F1, "sine" if sine else "square", cp)


def calibrate_pwin(ch: Channel, sine: bool, cp: bool = True, nbits=4000, seed=7) -> float:
    """Mean Goertzel power of the winning tone per bit on a noiseless channel
    (defines Eb at the detector: Eb/N0 = mean(Pwin) / (N * sigma^2))."""
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, nbits).astype(np.uint8)
    drive = modulate_fast(bits, ch.fs_sim, RB, F0, F1, "sine" if sine else "square", cp)
    c2 = Channel(**{**ch.__dict__, "noise_v": 0.0, "ambient_dc_v": 0.0, "flicker_v": 0.0, "quantize": False,
                    "bias_v": 0.0, "clock_ppm": 0.0})
    x = c2.sample(c2.analog(drive))
    _, P0, P1 = L.demod_goertzel_ideal(x, FS_ADC, RB, F0, F1)
    k = slice(10, len(P0) - 10)
    return float(np.mean(np.where(bits[: len(P0)][k] > 0, P1[k], P0[k])))


def sigma_for(ebn0_db, pwin):
    return math.sqrt(pwin / (N * 10 ** (ebn0_db / 10)))


# ------------------------------------------------------------------ 1) message decode test
def message_tests(exe, results):
    print("\n=== 1) message decode through the full chain ===")
    cases = [
        dict(name="square CPFSK, DC+flicker, +150 ppm, Eb/N0 14 dB", sine=False, cp=True, fec=False, ppm=150, ebn0=14),
        dict(name="square CPFSK, Hamming(7,4), -200 ppm, Eb/N0 12 dB", sine=False, cp=True, fec=True, ppm=-200, ebn0=12),
        dict(name="square phase-reset (LEDC-like), Eb/N0 14 dB", sine=False, cp=False, fec=False, ppm=0, ebn0=14),
        dict(name="sine tones, no noise, strong flicker", sine=True, cp=True, fec=False, ppm=50, ebn0=None),
    ]
    out = []
    for c in cases:
        ch = Channel(swing_v=0.5, ambient_dc_v=0.6, flicker_v=0.3 if c["ebn0"] else 0.6, clock_ppm=c["ppm"], seed=3)
        pwin = calibrate_pwin(ch, c["sine"], c["cp"])
        if c["ebn0"] is not None:
            ch.noise_v = sigma_for(c["ebn0"], pwin)
        _, drive = tx_stream([MSG], fec=c["fec"], sine=c["sine"], cp=c["cp"])
        x = ch.sample(ch.analog(drive))
        t = time.time()
        d = L.GoertzelDemod(FS_ADC, RB, F0, F1)
        fr = d.process(x)
        tpy = time.time() - t
        py_ok = len(fr) == 1 and fr[0].ok and fr[0].payload == MSG
        c_ok = None
        if exe:
            cf = c_demod(exe, x)
            c_ok = len(cf) == 1 and cf[0]["ok"] and cf[0]["payload"] == MSG
        rec = dict(case=c["name"], python_decoded=py_ok, firmware_c_decoded=c_ok,
                   text=fr[0].payload.decode(errors="replace") if fr else None,
                   snr_db=round(fr[0].snr_db, 1) if fr else None, rssi_db=round(fr[0].rssi_db, 1) if fr else None,
                   phase_moves=fr[0].phase_moves if fr else None, hamming_corrected=fr[0].corrected if fr else None,
                   python_seconds=round(tpy, 2))
        print(rec)
        out.append(rec)
    results["message_tests"] = out
    return out


# ------------------------------------------------------------------ 2) waveforms
def plot_waveforms(results):
    ch = Channel(swing_v=0.5, ambient_dc_v=0.6, flicker_v=0.3, noise_v=0.02, seed=5)
    bits, drive = tx_stream([b"Li"], lead_bits=8, gap_bits=8)
    analog = ch.analog(drive)
    x = ch.sample(analog)
    d = L.GoertzelDemod(FS_ADC, RB, F0, F1)
    fr = d.process(x)
    # DC-removed signal (same trackers as firmware)
    a = 1 / 16
    m1 = m2 = 0.0
    y = np.empty_like(x)
    for i, v in enumerate(x):
        m1 += a * (v - m1)
        y1 = v - m1
        m2 += a * (y1 - m2)
        y[i] = y1 - m2
    t_adc = np.arange(len(x)) / FS_ADC * 1e3
    t_sim = np.arange(len(drive)) / FS_SIM * 1e3
    t0, t1 = 0, 30  # ms window (first 30 bits: idle + preamble + sync)
    fig, ax = plt.subplots(5, 1, figsize=(12, 12))
    bt = np.arange(len(bits)) / RB * 1e3
    ax[0].step(bt, bits, where="post", color="k")
    ax[0].set_ylabel("bit")
    ax[0].set_title("Tx bits: mark idle, preamble 0xAA..., sync 0x2DD4 (frame 'Li')")
    ax[1].plot(t_sim, drive, lw=0.5, label="LED drive (MOSFET gate)")
    ax[1].plot(t_sim, analog / ch.swing_v + 0.5, lw=0.8, label="after LED + front-end LPF (scaled)")
    ax[1].set_ylabel("drive")
    ax[1].legend(loc="upper right", fontsize=8)
    ax[2].plot(t_adc, x, lw=0.5)
    ax[2].set_ylabel("ADC counts")
    ax[2].set_title("zoom: received at ADC: bias + ambient DC + 100 Hz flicker + AWGN, 12-bit, 48 kSps")
    ax[3].plot(t_adc, y, lw=0.5, color="tab:green")
    ax[3].set_ylabel("counts")
    ax[3].set_title("zoom: after 2x mean-tracker DC/flicker removal")
    dec = np.array([(s, b, p0, p1) for s, _, b, p0, p1 in d.decisions])
    if len(dec):
        ts = dec[:, 0] / FS_ADC * 1e3
        ax[4].plot(ts, np.sqrt(dec[:, 2]), "o-", ms=3, label="|G(f0)| per bit")
        ax[4].plot(ts, np.sqrt(dec[:, 3]), "s-", ms=3, label="|G(f1)| per bit")
        ax[4].legend(loc="upper right", fontsize=8)
    ax[4].set_ylabel("Goertzel |X|")
    ax[4].set_xlabel("time (ms)")
    ax[4].set_title(f"locked-phase Goertzel outputs after sync (decoded: {fr[0].payload if fr else None}, CRC ok={fr[0].ok if fr else None})")
    for a_ in ax:
        a_.grid(alpha=0.3)
    zoom = (14.0, 21.0)  # ms: end of mark idle -> start of preamble
    ax[0].axvspan(*zoom, color="orange", alpha=0.2)
    full = (0, len(bits) / RB * 1e3)
    ax[0].set_xlim(*full)
    ax[4].set_xlim(*full)
    for a_ in ax[1:4]:
        a_.set_xlim(*zoom)
    ax[1].set_title("zoom (shaded in top plot): LED drive, f1 idle tone -> 0xAA preamble (f0/f1 alternating)")
    ax[3].set_xlabel("time (ms)")
    fig.tight_layout()
    fig.savefig(OUT / "waveforms.png", dpi=110)
    plt.close(fig)
    results["waveforms_decoded"] = fr[0].payload.decode() if fr else None


# ------------------------------------------------------------------ 3) spectrum
def plot_spectrum(results):
    rng = np.random.default_rng(11)
    bits = rng.integers(0, 2, 4000).astype(np.uint8)
    ch = Channel(swing_v=0.5, ambient_dc_v=0.6, flicker_v=0.3, noise_v=0.01, seed=6)
    drive = modulate_fast(bits, ch.fs_sim, RB, F0, F1, "square", True)
    analog = ch.analog(drive)
    x = ch.sample(analog) * ch.lsb()
    f1, p1 = welch(drive - drive.mean(), fs=ch.fs_sim, nperseg=8192)
    f2, p2 = welch(analog, fs=ch.fs_sim, nperseg=8192)
    f3, p3 = welch(x, fs=FS_ADC, nperseg=4096, detrend=False)
    a = 1 / 16
    m1 = m2 = 0.0
    y = np.empty_like(x)
    for i, v in enumerate(x):
        m1 += a * (v - m1)
        yy = v - m1
        m2 += a * (yy - m2)
        y[i] = yy - m2
    f4, p4 = welch(y, fs=FS_ADC, nperseg=4096, detrend=False)
    fig, ax = plt.subplots(2, 1, figsize=(11, 8))
    ax[0].semilogy(f1 / 1e3, p1, lw=0.6, label="LED drive (square CPFSK)")
    ax[0].semilogy(f2 / 1e3, p2, lw=0.6, label="after LED (100 kHz) + RX front-end (30 kHz) LPF")
    for f in (F0, F1, 3 * F0, 3 * F1, 5 * F0, 5 * F1):
        ax[0].axvline(f / 1e3, color="gray", ls=":", lw=0.6)
    ax[0].set_xlim(0, 200)
    ax[0].set_ylim(1e-12, 1)
    ax[0].set_xlabel("kHz")
    ax[0].set_ylabel("PSD")
    ax[0].set_title("Transmit side: tones at 10/15 kHz and odd harmonics (30, 45, 50, 75 kHz)")
    ax[0].legend(fontsize=8)
    ax[1].semilogy(f3 / 1e3, p3, lw=0.7, label="ADC input (DC + 100 Hz flicker + noise)")
    ax[1].semilogy(f4 / 1e3, p4, lw=0.7, label="after DC/flicker removal")
    for f, lab in ((F0, "f0"), (F1, "f1"), (18e3, "3f0"), (3e3, "3f1"), (2e3, "5f0"), (21e3, "5f1")):
        ax[1].axvline(f / 1e3, color="gray", ls=":", lw=0.6)
        ax[1].text(f / 1e3, 1e-2, lab, fontsize=8)
    ax[1].set_xlim(0, FS_ADC / 2e3)
    ax[1].set_xlabel("kHz")
    ax[1].set_ylabel("PSD (V^2/Hz)")
    ax[1].set_title("Receiver @ 48 kSps: tone harmonics alias to 2, 3, 18, 21 kHz, never onto the f0/f1 bins")
    ax[1].legend(fontsize=8)
    for a_ in ax:
        a_.grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(OUT / "spectrum.png", dpi=110)
    plt.close(fig)
    i100 = np.argmin(abs(f3 - 100))
    results["spectrum_100Hz_suppression_db"] = round(10 * math.log10(p3[i100] / p4[i100]), 1)


# ------------------------------------------------------------------ 4) BER curves
def ber_curves(exe, results, quick=False):
    print("\n=== 2) BER vs Eb/N0 ===")
    ebn0_db = np.arange(0, 14, 1.0)
    max_bits = 60_000 if quick else 400_000
    chunk = 20_000
    ch = Channel(swing_v=0.5)
    curves = {}
    for label, sine in (("goertzel_sine", True), ("goertzel_square", False)):
        rng = np.random.default_rng(21 if sine else 22)
        bits = rng.integers(0, 2, max_bits).astype(np.uint8)
        clean = []
        for i in range(0, max_bits, chunk):
            b = bits[i:i + chunk]
            drive = modulate_fast(b, ch.fs_sim, RB, F0, F1, "sine" if sine else "square", True)
            if sine:  # ideal tones straight into the ADC (textbook case)
                c2 = Channel(**{**ch.__dict__, "fc_led": 1e9, "fc_rx": 1e9})
            else:
                c2 = ch
            a = c2.analog(drive) if not sine else (drive - 0.5) * ch.swing_v
            clean.append(a[:: int(ch.fs_sim / FS_ADC)][: len(b) * N])
        clean = np.concatenate(clean)
        _, P0, P1 = L.demod_goertzel_ideal(clean, FS_ADC, RB, F0, F1)
        pwin = float(np.mean(np.where(bits > 0, P1, P0)))
        # filter-bank integrate-and-dump offset: maximise the mean normalised margin (noiseless)
        best = (-1.0, 0)
        for dly in range(0, N, 2):
            bh, E0, E1 = L.demod_filterbank(clean[:400 * N], FS_ADC, RB, F0, F1, delay=dly)
            k = len(bh) - 2
            sgn = np.where(bits[:k] > 0, 1.0, -1.0)
            mq = float(np.mean(sgn * (E1[:k] - E0[:k]) / (E1[:k] + E0[:k])))
            if mq > best[0]:
                best = (mq, dly)
        dly = best[1]
        g_ber, fb_ber = [], []
        rng_n = np.random.default_rng(99)
        for eb in ebn0_db:
            s = sigma_for(eb, pwin)
            x = clean + s * rng_n.standard_normal(len(clean))
            bh, _, _ = L.demod_goertzel_ideal(x, FS_ADC, RB, F0, F1)
            g_ber.append(float(np.mean(bh != bits[: len(bh)])))
            if sine:
                bf, _, _ = L.demod_filterbank(x, FS_ADC, RB, F0, F1, delay=dly)
                n_ok = len(bf) - 2
                fb_ber.append(float(np.mean(bf[:n_ok] != bits[:n_ok])))
        curves[label] = g_ber
        if sine:
            curves["filterbank_sine"] = fb_ber
            curves["filterbank_delay_samples"] = dly
        print(label, ["%.2e" % v for v in g_ber])
        if sine:
            print("filterbank_sine", ["%.2e" % v for v in fb_ber])

    # full firmware chain (multi-phase Goertzel, sync, tracking, CRC) with DC, flicker, clock offset
    full_pts = [4, 6, 8, 10, 11, 12, 13, 14] if not quick else [4, 8, 11, 14]
    n_frames = 400 if not quick else 120
    full = {"ebn0_db": full_pts, "plain": [], "fec": []}
    for fec in (False, True):
        for eb in full_pts:
            ch2 = Channel(swing_v=0.5, ambient_dc_v=0.6, flicker_v=0.3, clock_ppm=100, seed=int(eb * 10 + fec))
            pwin = calibrate_pwin(ch2, False)
            ebc = eb + (10 * math.log10(4 / 7) if fec else 0.0)  # Eb is per information bit
            ch2.noise_v = sigma_for(ebc, pwin)
            payloads = [L.bert_payload(i) for i in range(n_frames)]
            _, drive = tx_stream(payloads, fec=fec)
            x = ch2.sample(ch2.analog(drive))
            if exe:
                frs = c_demod(exe, x)
                frs = [(f["length"], f["payload"], f["ok"]) for f in frs]
                engine = "firmware C (host build)"
            else:
                d = L.GoertzelDemod(FS_ADC, RB, F0, F1)
                frs = [(f.length, f.payload, f.ok) for f in d.process(x)]
                engine = "python reference"
            bits_n = errs = got = okc = 0
            for ln, p, ok in frs:
                if ln == L.BERT_LEN and bin(p[0] ^ L.BERT_MARKER).count("1") <= 2:
                    got += 1
                    okc += ok
                    bits_n += L.BERT_PRBS_BYTES * 8
                    errs += L.bert_errors(p)
            rec = dict(ebn0_db=eb, frames_sent=n_frames, frames_received=got, crc_ok=okc,
                       bits=bits_n, errors=errs, ber=errs / bits_n if bits_n else None,
                       frame_loss=1 - got / n_frames, fer=1 - okc / n_frames)
            full["fec" if fec else "plain"].append(rec)
            print("full chain", "FEC" if fec else "plain", rec)
    full["engine"] = engine
    curves["full_chain"] = full

    theory = L.ber_theory_ncfsk(10 ** (ebn0_db / 10))
    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.semilogy(ebn0_db, theory, "k-", lw=2, label="theory non-coherent BFSK 0.5 exp(-Eb/2N0)")
    ax.semilogy(ebn0_db, np.maximum(curves["goertzel_sine"], 1e-7), "o--", label="Goertzel, sine tones, ideal timing")
    ax.semilogy(ebn0_db, np.maximum(curves["goertzel_square"], 1e-7), "s--",
                label="Goertzel, square tones via LED/RX LPF, ideal timing")
    ax.semilogy(ebn0_db, np.maximum(curves["filterbank_sine"], 1e-7), "^--",
                label="non-coherent filter bank (2x BPF + energy), sine")
    fp = [r["ber"] if r["ber"] else np.nan for r in full["plain"]]
    ff = [r["ber"] if r["ber"] else np.nan for r in full["fec"]]
    ax.semilogy(full_pts, np.maximum(fp, 1e-7), "D-", ms=7,
                label="full chain: firmware demod + sync + CRC, DC+flicker, 100 ppm")
    ax.semilogy(full_pts, np.maximum(ff, 1e-7), "v-", ms=7, label="full chain + Hamming(7,4) (Eb per info bit)")
    ax.set_ylim(1e-6, 1)
    ax.set_xlabel("Eb/N0 (dB)  [Eb from detector tone energy]")
    ax.set_ylabel("BER")
    ax.set_title(f"Li-Fi BFSK {F0/1e3:.0f}/{F1/1e3:.0f} kHz, {RB:.0f} bps, fs={FS_ADC/1e3:.0f} kSps (points at 1e-7 = no errors)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(OUT / "ber_curve.png", dpi=120)
    plt.close(fig)
    results["ber"] = dict(ebn0_db=ebn0_db.tolist(), theory=theory.tolist(), bits_per_point=max_bits, **curves)


# ------------------------------------------------------------------ 5) BER vs distance
def ber_distance(results, quick=False):
    print("\n=== 3) BER vs distance ===")
    lb = LinkBudget()
    noise_v = 0.008  # 8 mV rms at the ADC (TIA + ambient shot noise + ESP32 ADC noise)
    dists = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12])
    nb = 20000 if quick else 100000
    rng = np.random.default_rng(31)
    bits = rng.integers(0, 2, nb).astype(np.uint8)
    drive = modulate_fast(bits, FS_SIM, RB, F0, F1, "square", True)
    base = Channel(swing_v=1.0)
    clean1 = base.analog(drive)[:: int(FS_SIM / FS_ADC)][: nb * N]
    _, P0, P1 = L.demod_goertzel_ideal(clean1, FS_ADC, RB, F0, F1)
    pwin1 = float(np.mean(np.where(bits > 0, P1, P0)))
    sim, th, ebs = [], [], []
    for d in dists:
        sw = lb.swing_v(d)
        x = clean1 * sw + noise_v * rng.standard_normal(len(clean1))
        bh, _, _ = L.demod_goertzel_ideal(x, FS_ADC, RB, F0, F1)
        sim.append(float(np.mean(bh != bits)))
        ebn0 = pwin1 * sw ** 2 / (N * noise_v ** 2)
        ebs.append(10 * math.log10(ebn0))
        th.append(float(L.ber_theory_ncfsk(ebn0)))
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.semilogy(dists, np.maximum(th, 1e-9), "k-", label="theory (Eb/N0 from link budget)")
    ax.semilogy(dists, np.maximum(sim, 1e-7), "o--", label=f"simulated, {nb} bits/point")
    ax.set_xlabel("LED-photodiode distance (m), on axis")
    ax.set_ylabel("BER")
    ax.set_ylim(1e-7, 1)
    ax.grid(True, which="both", alpha=0.3)
    ax.set_title("0.5 W optical, 60 deg LED, BPW34, 100 kOhm TIA x10, 8 mV rms noise")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "ber_distance.png", dpi=110)
    plt.close(fig)
    results["distance"] = dict(d_m=dists.tolist(), swing_mv=[round(lb.swing_v(d) * 1e3, 1) for d in dists],
                               ebn0_db=[round(e, 1) for e in ebs], ber_sim=sim, ber_theory=th, noise_v=noise_v)
    for d, e, s in zip(dists, ebs, sim):
        print(f"  d={d:4.1f} m  Eb/N0={e:5.1f} dB  BER={s:.2e}")


# ------------------------------------------------------------------ 6) XR2211-style digital line
def xr2211_test(results):
    """Behavioural XR2211: band-pass energy comparator -> 0/1 data line, then the
    Uno's 8x DPLL decoder (python mirror of rx_arduino_uno_xr2211.ino)."""
    from scipy.signal import butter, sosfilt
    print("\n=== 4) XR2211 data line + Uno DPLL decoder ===")
    ch = Channel(swing_v=0.3, ambient_dc_v=0.4, flicker_v=0.2, noise_v=0.03, clock_ppm=2000, seed=8)
    _, drive = tx_stream([MSG, b"second frame via XR2211 path"])
    x = ch.sample(ch.analog(drive)) * ch.lsb()
    e = []
    for f in (F0, F1):
        sos = butter(2, [f - 1500, f + 1500], btype="bandpass", fs=FS_ADC, output="sos")
        y = sosfilt(sos, x)
        lp = butter(2, 0.6 * RB, fs=FS_ADC, output="sos")
        e.append(sosfilt(lp, y * y))
    line = (e[1] > e[0]).astype(int)
    line = 1 - line  # XR2211 open-collector output is often inverted: the decoder must cope
    os_line = line[:: N // 8]  # Timer2 samples at 8 x bit rate
    dec = L.DigitalLineDecoder()
    fr = dec.process(os_line)
    ok = [f.payload for f in fr if f.ok]
    print("decoded:", ok)
    results["xr2211_dpll"] = dict(frames=len(fr), ok=[p.decode() for p in ok], inverted_line=True, clock_ppm=2000)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    results = {}
    t = time.time()
    exe = build_host_harness()
    results["host_firmware_build"] = bool(exe)
    print("host build of firmware demod:", exe)
    message_tests(exe, results)
    plot_waveforms(results)
    plot_spectrum(results)
    xr2211_test(results)
    ber_curves(exe, results, args.quick)
    ber_distance(results, args.quick)
    results["runtime_s"] = round(time.time() - t, 1)
    (OUT / "results.json").write_text(json.dumps(results, indent=1, default=str))
    print("\nwrote", OUT, "runtime", results["runtime_s"], "s")


if __name__ == "__main__":
    main()
