# Li-Fi BFSK link: firmware, simulation and PC tools

A visible-light link for a student project. An LED sends binary FSK tones
(bit 0 = f0, bit 1 = f1, 50 % duty square waves). A photodiode front-end
feeds an ESP32 ADC, and the ESP32 recovers the bits with Goertzel filters.
An Arduino Uno version (timer-generated tones, XR2211 PLL demodulator) is
included too.

Defaults: **f0 = 10 kHz, f1 = 15 kHz, 1000 bit/s, receiver fs = 48 kSps**.

```
 PC ──USB── TX (ESP32 or Uno) ── MOSFET ── LED  ~~~ light ~~~  photodiode ── TIA ── HPF/gain ── RX ADC (ESP32)
   tools/                     tx_esp32/ tx_arduino_uno/                                          rx_esp32/
                                                                      └── XR2211 ── data line ── Uno rx_arduino_uno_xr2211/
```

## Repository layout

| Path | What it is |
|---|---|
| `common/lifi_proto.h` | Framing, CRC-16-CCITT, Hamming(7,4), PRBS9, streaming TX framer and RX deframer (plain C, header-only) |
| `common/lifi_demod.h` | Streaming demodulator: DC/flicker removal, 8-phase Goertzel bank, preamble timing lock, tracking, RSSI/SNR |
| `tx_esp32/` | ESP32 transmitter (Arduino-ESP32 core 3.x). Uses the DDS timer ISR for continuous-phase FSK, or LEDC |
| `rx_esp32/` | ESP32 receiver. Continuous (DMA) ADC, Goertzel demod, CRC, BER statistics |
| `tx_arduino_uno/` | Uno transmitter. Timer1 continuous-phase toggling, or `tone()`. Packet or plain-UART coding |
| `rx_arduino_uno_xr2211/` | Uno receiver behind an XR2211. 8x oversampled DPLL on the data line, or SoftwareSerial in UART mode |
| `sim/lifi_ref.py` | Python reference: same framing and demod as the C code, plus a filter-bank receiver and the XR2211-line DPLL |
| `sim/channel.py` | LED/front-end low-pass, Lambertian distance loss, ambient DC, 100 Hz flicker, AWGN, 12-bit ADC, clock offset |
| `sim/run_sim.py` | Full simulation. Writes `sim/out/*.png` and `results.json` |
| `tests/` | pytest suite (47 tests). `tests/host/host_harness.cpp` builds the **firmware headers on the PC** |
| `tools/lifi_tool.py`, `tools/lifi_gui.py`, `tools/lifi_link.py` | PC CLI and Tk GUI (pyserial): send text and files, run BER tests, live BER/RSSI plot |
| `tools/sync_common.py` | Copies `common/*.h` into each sketch folder. Arduino can't include files from outside the sketch, so each sketch carries a copy. A test checks the copies match |

## Frame format

```
| 0xAA 0xAA 0xAA 0xAA | SYNC (16 b) | LEN (8 b) | PAYLOAD (0..255 B) | CRC16 (16 b) |      bits MSB first
```
* `SYNC = 0x2DD4`: plain body. `SYNC = 0xD263`: LEN, PAYLOAD and CRC are Hamming(7,4) coded
  (each byte becomes two 7-bit codewords, ordered p1 p2 d1 p3 d2 d3 d4). The receiver picks the mode from the sync word, so
  coded and plain frames can be mixed on the same link.
* CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over LEN and PAYLOAD. Check value: "123456789" gives 0x29B1.
* The two sync words differ in 14 bits. Every 16-bit window of preamble+sync is at least 5 bits away from either sync word.
* Between frames the TX idles on the f1 tone ("mark"). This keeps the LED's average brightness constant, so there's no visible flicker.
* BER-test frame: `0xB5, seq, 32 bytes PRBS9`. The RX counts bit errors in the PRBS part.

## Receiver algorithm (`common/lifi_demod.h`)
1. **Ambient light**: two cascaded running-mean trackers (alpha = 1/16, about 500 Hz corner at 48 kSps) remove the DC level and
   most of the 100 Hz mains flicker. The Goertzel window rejects what's left (in simulation the 100 Hz line drops by about 29 dB).
2. **8 timing phases**: each phase has its own Goertzel pair (f0, f1) over one bit window, offset by 1/8 bit. Fractional
   samples-per-bit are handled, so the measured ADC rate (for example 47 993 Sps) can be used directly.
3. **Decision**: bit = P(f1) > P(f0). Margin m = (P1-P0)/(P1+P0).
4. **Acquisition**: every phase looks for `[0xAA][SYNC]`. On a match, the phase with the best average |m| over the
   0xAA preamble is locked. A phase that is later than the matching one skips one window, so bit alignment is kept.
5. **Tracking**: after each bit, the lock can step to a neighbouring phase whose slow-average |m| is clearly better.
   This absorbs crystal offset between TX and RX (tested to ±300 ppm, and fractional fs).
6. **Per-frame statistics**: RSSI = 20·log10(mean winning-tone amplitude in ADC counts). SNR = winner/loser tone energy.
   Quality = mean |m|.

CPU estimate on the ESP32 (not measured): 16 Goertzel updates per sample × 48 kSps ≈ 0.8 M multiply-adds/s,
a few % of one 240 MHz core.

### Design note: why fs = 48 kSps and not 40 kSps
At fs = 40 kSps = 4·f0, the 3rd harmonic of the square-wave f0 tone (30 kHz) folds back exactly onto 10 kHz.
The f0 tone energy then swings by about 3 dB depending on the ADC sampling phase. The simulation measured
Goertzel power from 24.7 to 47.3 across sampling phases, which cost about 1 dB in BER.
At 48 kSps the harmonics fold to 2, 3, 18 and 21 kHz. Those are other Goertzel bins, which are orthogonal over a 48-sample window
(`sim/out/spectrum.png`). If you change f0, f1 or fs, check that k·f0 and k·f1 (k = 3, 5, 7) don't fold onto either tone.
Also keep the tone spacing a multiple of the bit rate (here 5·Rb), so the two tones are orthogonal.

## Simulation results (`python sim/run_sim.py`, about 2 min; `--quick` takes about 20 s)

Eb/N0 is defined from the tone energy the detector actually sees.
The **full chain** row runs the firmware's own `lifi_demod.h`, compiled for the PC,
on 400 BER-test frames per point. The channel includes ambient DC (0.6 V), 100 Hz flicker (0.3 V peak), +100 ppm clock
offset, LED (100 kHz) and front-end (30 kHz) low-pass, and a 12-bit ADC.

| Eb/N0 (dB) | 8 | 10 | 11 | 12 | 13 | 14 |
|---|---|---|---|---|---|---|
| theory 0.5·exp(-Eb/2N0) | 2.1e-2 | 3.4e-3 | 9.2e-4 | 1.8e-4 | 2.3e-5 | 1.8e-6 |
| Goertzel, square tones, ideal timing (4e5 bits) | 2.2e-2 | 3.6e-3 | 9.9e-4 | 2.2e-4 | 2.3e-5 | – |
| filter bank (2×BPF + energy), sine | 3.1e-2 | 6.0e-3 | 2.0e-3 | 5.2e-4 | 1.3e-4 | – |
| **full chain, plain** (BER / frames lost / FER) | 2.7e-2 / 40 % / 100 % | 4.5e-3 / 9 % / 74 % | 1.3e-3 / 2.5 % / 34 % | 3.4e-4 / 1.5 % / 9 % | 6.8e-5 / 0 / 1.8 % | **0 / 0 / 0** |
| full chain + Hamming(7,4) (Eb per info bit) | 6.6e-2 | 8.5e-3 | 3.3e-3 | 4.4e-4 | 5.9e-5 | 9.8e-6 / FER 0.25 % |

* The Goertzel receiver matches non-coherent BFSK theory. The full firmware chain, with real impairments, comes within about 0.3–0.5 dB of it.
  The filter bank is about 1 dB worse. Full-chain BER counts only frames whose sync was found; frame loss is listed separately.
* Hard-decision Hamming(7,4) costs 2.4 dB of energy per coded bit. It only breaks even at about 13 dB (BER ≤ 1e-4), and
  it also weakens the uncoded preamble and sync. Use it on a link with occasional single-bit hits, not as a range extender.
* Range: 0.5 W optical LED (60° half-angle), BPW34, 100 kΩ TIA ×10, 8 mV rms noise. Error-free (1e5 bits) to 5 m,
  BER 1.1e-4 at 6 m, 4.6e-3 at 7 m (`ber_distance.png`).
* Message tests (Python and firmware-C demod both decode the 55-byte message). Cases: square continuous-phase at 14 dB
  +150 ppm; Hamming at 12 dB −200 ppm (2 bits corrected); phase-reset tones like LEDC; sine with 0.6 V flicker.
* XR2211 path: a behavioural XR2211 (band-pass energy comparator, inverted output) feeds the Uno DPLL at
  2000 ppm clock offset. Both frames decode, and the polarity is detected automatically.

Plots: `sim/out/ber_curve.png`, `spectrum.png`, `waveforms.png`, `ber_distance.png`.

## Building

Install arduino-cli. Then install the `esp32:esp32` core (3.x) from
`https://espressif.github.io/arduino-esp32/package_esp32_index.json`, and `arduino:avr`.

```
python tools/sync_common.py            # after editing common/
arduino-cli compile --fqbn esp32:esp32:esp32 tx_esp32
arduino-cli compile --fqbn esp32:esp32:esp32 rx_esp32
arduino-cli compile --fqbn arduino:avr:uno tx_arduino_uno
arduino-cli compile --fqbn arduino:avr:uno rx_arduino_uno_xr2211
arduino-cli upload -p COM5 --fqbn esp32:esp32:esp32 tx_esp32
```
Compile-checked here (not flashed) with arduino-cli 1.5.1, esp32 core 3.3.12 and arduino:avr 1.8.8, using `--warnings all`
(no warnings from the sketch code). See `BUILD_LOG.md` for sizes.

## Hardware notes
**TX driver**: GPIO25 (ESP32) or D9 (Uno) → 100 Ω → gate of a logic-level N-MOSFET (AO3400, IRLML6344, or IRLZ44N on 5 V
only), with 10 kΩ gate-to-source pull-down. Use low-side switching: LED string and current-limit resistor (or a constant-current
driver) from the supply to the drain, source to ground. At 3.3 V gate drive, pick a MOSFET with R_DS(on) specified at
V_GS = 2.5 V. Keep the LED driver free of large output capacitors: the light has to follow 15 kHz edges.

**RX front-end** (suggested): photodiode (BPW34) reverse-biased into a transimpedance amp, e.g. MCP6022 or OPA350.
Use Rf = 100 kΩ and Cf ≈ 47 pF (≈ 34 kHz bandwidth, which is also the anti-alias filter). Then AC coupling (≈ 100 Hz HPF) and a ×10 stage biased at
1.65 V, into GPIO34 (ADC1). With 12 dB attenuation, the ESP32 ADC is most linear between about 0.15 and 2.45 V, so keep the swing inside that.
Bright ambient light can saturate a DC-coupled TIA. Then lower Rf or shade the photodiode; the digital mean removal
can't undo clipping.

**XR2211 for 10/15 kHz, 1000 baud.** These come from the XR-2211A datasheet design instructions
(https://www.maxlinear.com/ds/xr2211av104.pdf):
f_o = √(f1·f2) = 12.25 kHz. R0 = 20 kΩ (15 k plus a 10 k trimmer). C0 = 1/(R0·f_o) ≈ 3.9 nF.
R1 = 2·R0·f_o/(f2−f1) ≈ 100 kΩ. C1 = 1250·C0/(R1·ζ²) with ζ = 0.5 ≈ 200–220 pF. RF ≥ 5·R1 → 510 kΩ.
RB ≥ 5·RF → 2.7 MΩ. CF = 0.25/(R_sum·baud) ≈ 470 pF.
Input is AC-coupled (0.1 µF), 10 mV–3 V rms. DO (pin 7) is open-collector: use 5.1 kΩ to 5 V, then Uno D2.
DO is high for the lower tone, so it is inverted relative to bit = 1 → f1. The sketch detects polarity from the sync word.
Tune the trimmer for 50 % duty on DO while the TX sends the 0xAA preamble (`!bert`).

## Using it
**TX (115200 baud)**: type a line to send it. Commands:
`!f0 <Hz>`, `!f1 <Hz>`, `!rate <bps>`, `!mode dds|ledc`, `!fec on|off`, `!idle mark|off|on`,
`!bert <n> [gap_ms]`, `!hex <bytes>`, `!info`.
* `dds` (default): a hardware timer at 160 kHz steps a 32-bit phase accumulator. Tone switches are phase-continuous, and
  bit timing comes from a second accumulator. Edge jitter is at most one tick (6.25 µs). Lower `TICK_HZ` if ISR load
  matters; keep TICK_HZ ≥ 8·f1.
* `ledc`: `ledcChangeFrequency()` at each bit boundary, paced with `esp_timer`. Simpler, but the switch happens at the next PWM
  period and has some timing jitter. Neither mode needs Manchester coding: the sync and preamble give timing, and the receiver
  tracks it.

**RX (921600 baud)** prints `RX ok "text"` and machine-readable lines:
`#FRAME,ok,fec,len,rssi_db,snr_db,quality,corrected,phase,moves,hex`,
`#BERT,frames,bits,errors,ber,lost`, and every 2 s
`#STAT,ms,fs_meas,syncs,frames,crc_fail,bert_frames,bert_bits,bert_errs,ber,idle_rssi_db`.
At boot it measures the real ADC rate for 1 s and uses it (`AUTO_CAL_FS`). Commands: `!reset`, `!info`.

**PC tools** (`pip install pyserial matplotlib`):
```
python tools/lifi_tool.py --tx COM5 send "hello over light"
python tools/lifi_tool.py --tx COM5 sendfile notes.txt --repeat 2
python tools/lifi_tool.py --tx COM5 bert --count 500
python tools/lifi_tool.py --rx COM6 monitor --plot --save-files received/ --log rx.csv
python tools/lifi_gui.py
```

## Tests
```
pip install numpy scipy matplotlib pytest pyserial
python -m pytest -q tests        # 47 passed
```
The tests cover:
* CRC check value, Hamming correcting every single-bit error, sync-word distances, and PRBS period
* Framing round trips (0–255 bytes, plain and FEC)
* **C TX framer output equals the Python framer, bit for bit** (host-compiled firmware header)
* **Python demod and firmware C demod decode identical frames**
* Demod under DC, flicker, ±300 ppm, phase-reset tones, FEC, and 44.1 kSps (fractional samples per bit)
* RSSI scaling, BER within ±20 % of theory at 6 and 9 dB, the XR2211 DPLL decoder (±2000 ppm, inverted line),
  log parsing, file chunking and reassembly, and that the sketch header copies are identical
The host harness is built with g++/clang++ if present, otherwise with `pip install ziglang`.

## Options and stretch goals
* **Hamming(7,4)**: implemented end to end (`!fec on`; RX auto-detects it). See the trade-off above.
* **File transfer**: implemented in `tools/`. Files are split into 200-byte chunks with a header (id, seq, total, CRC16 of the chunk);
  chunk 0 carries the name and a whole-file CRC. The link is one-way with no ACK, so use `--repeat` and the receiver keeps the good
  copies. At 1 kbps the goodput is about 0.75 kbit/s.
* **Audio streaming** (not implemented): 8 kHz PCM needs 64 kbit/s. Codec2 at 1200–3200 bit/s fits after
  raising the link to about 4 kbit/s. For example, use f0/f1 = 40/60 kHz at 4 kbps with fs = 192 kSps on the ESP32 ADC (spb = 48, same demod),
  a faster TIA, a stream of fixed-length frames, and a small jitter buffer. Frame loss gets masked by repeating the last codec frame.
* Further ideas: soft-decision decoding (keep m instead of the hard bit) with a convolutional code, an ACK channel
  (IR LED back) for ARQ, carrier-sense on the idle tone, and Wi-Fi/BLE bridging.

## Limitations (honest list)
* Nothing has been flashed or tried on hardware. The sketches compile, and the protocol and demod logic run on the PC from the same headers,
  but ISR timing, ADC behaviour and analog values still need checking on the bench.
* The ESP32 continuous-ADC rate is not exact. The firmware measures it at boot. The ESP32 ADC is also noisy (several LSB), which the
  range estimate covers only through the 8 mV noise figure.
* The DDS ISR at 160 kHz is the heaviest part of the TX. If the core misses ticks, lower `TICK_HZ` or switch to `ledc`.
