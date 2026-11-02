"""channel.py - optical channel / front-end models for the Li-Fi BFSK simulation.

Signal path modelled (all voltages are at the ADC pin):

  LED drive 0..1 (square or sine tone)  @ fs_sim (default 480 kHz "analog" rate)
    -> LED + MOSFET driver low-pass (1st order, fc_led)
    -> optical path gain (Lambertian LOS, 1/d^2)  -> photodiode -> TIA -> post-amp
    -> receiver front-end low-pass / anti-alias (1st order, fc_rx)
    -> + ambient light DC + 100 Hz mains flicker (rectified-sine shape) + AWGN
    -> ADC sampling at fs_adc (optionally with a clock offset in ppm), 12-bit, clipped
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.signal import bilinear, lfilter


@dataclass
class LinkBudget:
    p_opt_w: float = 0.5        # optical power swing of the LED (W) (on/off keyed tone)
    half_angle_deg: float = 60  # LED semi-angle at half power -> Lambertian order m
    area_m2: float = 7.5e-6     # photodiode area (BPW34: 7.5 mm^2)
    resp_a_w: float = 0.5       # responsivity (A/W) around 550-650 nm
    tia_ohm: float = 100e3      # transimpedance
    post_gain: float = 10.0     # AC gain stage after the TIA

    def gain(self, d_m: float, phi_deg: float = 0.0, psi_deg: float = 0.0) -> float:
        m = -math.log(2) / math.log(math.cos(math.radians(self.half_angle_deg)))
        return ((m + 1) * self.area_m2 / (2 * math.pi * d_m ** 2)
                * math.cos(math.radians(phi_deg)) ** m * math.cos(math.radians(psi_deg)))

    def swing_v(self, d_m: float) -> float:
        """Peak-to-peak voltage swing at the ADC for an on/off LED at distance d."""
        return self.p_opt_w * self.gain(d_m) * self.resp_a_w * self.tia_ohm * self.post_gain


def lowpass1(x: np.ndarray, fc: float, fs: float) -> np.ndarray:
    """First-order RC low-pass (bilinear transform with pre-warping)."""
    wc = 2 * fs * math.tan(math.pi * fc / fs)
    b, a = bilinear([wc], [1, wc], fs)
    return lfilter(b, a, x)


def modulate_fast(bits: np.ndarray, fs: float, rb: float, f0: float, f1: float,
                  wave: str = "square", continuous_phase: bool = True) -> np.ndarray:
    """Vectorised modulator for long random bit streams (integer samples per bit)."""
    spb = int(round(fs / rb))
    assert abs(spb - fs / rb) < 1e-9, "fs/rb must be an integer here"
    f = np.where(np.repeat(bits, spb) > 0, f1, f0).astype(np.float64)
    if continuous_phase:
        ph = 2 * np.pi * np.cumsum(f) / fs
        ph = np.concatenate([[0.0], ph[:-1]])
    else:
        n = np.tile(np.arange(spb), len(bits))
        ph = 2 * np.pi * f * n / fs
    if wave == "square":
        return (np.mod(ph, 2 * np.pi) < np.pi).astype(np.float64)
    return 0.5 + 0.5 * np.sin(ph)


@dataclass
class Channel:
    fs_sim: float = 480e3
    fs_adc: float = 48e3
    fc_led: float = 100e3        # LED + driver bandwidth
    fc_rx: float = 30e3          # TIA / front-end bandwidth (also the anti-alias filter)
    swing_v: float = 0.5         # p-p swing at the ADC
    bias_v: float = 1.65         # front-end bias (mid supply)
    ambient_dc_v: float = 0.0    # extra DC from room light
    flicker_v: float = 0.0       # 100 Hz flicker amplitude (peak)
    noise_v: float = 0.0         # AWGN rms at the ADC (per sample)
    clock_ppm: float = 0.0       # RX ADC clock error vs TX
    adc_bits: int = 12
    vref: float = 3.3
    quantize: bool = True
    seed: int = 1

    def analog(self, drive: np.ndarray) -> np.ndarray:
        """Noise-free voltage after LED + front-end low-pass, AC part only."""
        y = lowpass1(drive - 0.5, self.fc_led, self.fs_sim)
        y = lowpass1(y, self.fc_rx, self.fs_sim)
        return y * self.swing_v

    def sample(self, analog: np.ndarray, rng: np.random.Generator | None = None) -> np.ndarray:
        rng = rng or np.random.default_rng(self.seed)
        ratio = self.fs_sim / self.fs_adc
        n_out = int((len(analog) - 1) / ratio / (1 + self.clock_ppm * 1e-6))
        t_idx = np.arange(n_out) * ratio * (1 + self.clock_ppm * 1e-6)
        if self.clock_ppm == 0 and abs(ratio - round(ratio)) < 1e-12:
            v = analog[:: int(round(ratio))][:n_out]
        else:
            v = np.interp(t_idx, np.arange(len(analog)), analog)
        t = np.arange(n_out) / self.fs_adc
        # rectified-sine (100 Hz + harmonics) lamp ripple, peak-to-peak = 2 * flicker_v
        flick = 2 * self.flicker_v * (np.abs(np.sin(2 * np.pi * 50 * t)) - 2 / np.pi)
        v = v + self.bias_v + self.ambient_dc_v + flick + self.noise_v * rng.standard_normal(n_out)
        if self.quantize:
            lsb = self.vref / (2 ** self.adc_bits)
            v = np.clip(np.round(v / lsb), 0, 2 ** self.adc_bits - 1)
            return v  # ADC counts
        return v

    def lsb(self) -> float:
        return self.vref / (2 ** self.adc_bits)
