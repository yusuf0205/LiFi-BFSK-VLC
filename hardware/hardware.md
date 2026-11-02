# Li-Fi BFSK link: hardware design pack

Student visible-light link using binary FSK. Solo build, India, under Rs 3,000. Target: 1 to 10 kbps over 0.5 to 3 m indoors, with rejection of ambient light.
Lab gear assumed: oscilloscope, function generator, bench or USB 5 V supply, multimeter.

Files in `/workspace/work/lifi/hardware/`:

| File | What it is |
|---|---|
| `hardware.md` | This document |
| `rx_frontend.cir` | RX analog front end netlist for LTspice and ngspice: BPW34, TIA, DC servo, gain stage, MFB band-pass (branch A), Sallen-Key anti-alias filter (branch B) |
| `tx_driver.cir` | TX LED driver netlist: ESP32 GPIO, IRLZ44N, 1 W LED. Also contains an AO3400 model for tiers B and C |
| `rx_ac_response.png` | ngspice AC response of every RX stage |
| `rx_noise.png` | ngspice input-referred noise of the RX circuit |
| `tx_transient.png` | ngspice transient of the TX driver at 15 kHz |
| `sim/rx_ac.sp`, `sim/tx_tran.sp` | ngspice batch runners (use `.include ../*.cir`) |
| `sim/make_plots.py`, `sim/link_budget.py`, `sim/link_budget.md` | Plot and link-budget scripts and their output |
| `ngspice.sh` | Sandbox-only wrapper for a user-space ngspice 44.2. You don't need it on your PC |

---

## 0. Design decisions at a glance

| Item | Choice | Why |
|---|---|---|
| Tone plan, main | **f1 (logic 1, mark, idle) = 10 kHz; f0 (logic 0, space) = 15 kHz** | Far above the 100 Hz mains flicker and its strong low harmonics. Above 3 kHz, so no visible or stroboscopic flicker. Inside the MCP6022 bandwidth at ×101 gain. Both demodulators can use it, which gives a fair PLL vs Goertzel comparison. |
| Bit rates on the main plan | 2.5 kbps (safe) and **5 kbps (comparison point)** | Δf = 5 kHz = Rb at 5 kbps, so the tones are orthogonal for non-coherent FSK. That is ≥2 cycles of the low tone per bit, so the XR2211 PLL can follow. |
| Tone plan, 10 kbps (tier B) | 20 / 30 kHz, Goertzel on ESP32 | Δf = Rb = 10 kHz. With fs = 200 kS/s, N = 20 samples per bit, bins k = 2 and 3 are integers. |
| Bring-up plan | 1200 / 2200 Hz at 1200 bps (Bell-202) | This is the XR2211 datasheet's own worked example, so it verifies the chip straight from the function generator. |
| LED | 1 W white star LED, switched on/off (square tone), about 0.27 A peak | Cheap, bright, no driver IC needed. The average stays constant, so illumination looks steady. |
| Switch | IRLZ44N (TO-220, logic level) for tier A; AO3400 (SOT-23) for B and C | IRLZ44N fits a breadboard. The AO3400 has 1/3 the gate charge, so its edges are faster. |
| Photodiode | BPW34 PIN, 7.5 mm², reverse-biased 2.5 V | Rs 59 to 92 in India. 25 pF at 3 V, 100 ns rise time. |
| Op-amp | **MCP6022** (dual, 10 MHz, 1 pA bias, rail-to-rail, 2.5 to 5.5 V, DIP-8) | It works on 5 V and 3.3 V, so its output can't damage the ESP32 ADC. Trade-offs are in section 2.3.6. |
| Ambient rejection | (1) DC servo sinks ambient photocurrent at the TIA input (headroom up to about 400 µA). (2) Two AC-coupled high-pass corners. (3) Band-pass or Goertzel bins. | Simulated: 100 Hz flicker sits 105 dB below the in-band gain at the XR2211 input (section 3) |

---

## 1. System block diagrams

### 1A. Tier A: analog/IC baseline (XR2211 PLL demodulator)

```
 TRANSMITTER (5 V USB or 5 V 2 A adapter)
 ┌──────────────┐  UART TX 5 kbps   ┌───────────────────────────┐  square tone   ┌──────────┐
 │ ESP32 #1     │──────────────────►│ Tone generator:           │──── 100 Ω ────►│ IRLZ44N  │ gate
 │ (data source,│  (or PRBS for BER)│  (a) ESP32 LEDC/RMT  ★     │                │ low-side │
 │  PRBS gen)   │                   │  (b) XR2206 FSK, pin 9 key│                └────┬─────┘
 └──────────────┘                   └───────────────────────────┘                     │ drain
                                                           +5 V ── 6.8 Ω 2 W ── LED 1 W ─┘
                                                                              │ (optional 15° TIR lens)
                                                                              ▼  light, 0.5 to 3 m
 RECEIVER (5 V for analog + XR2211; ESP32 3.3 V)
   (optional 15° TIR lens used backwards as a concentrator)
            ▼
   BPW34 ──► TIA (U1A, 47 k ∥ 33 p) ──► AC couple + x101 gain (U2A) ──► MFB band-pass (U2B)
   (-2.5 V      ▲                        HPF 3.4 k + 1.6 kHz              f0 12.25 kHz, Q 1.5
   reverse)     │ ambient DC servo                                         │
                └─ U1B integrator ─► Q1 current sink                        ▼ 100 nF
                   (removes sunlight/room DC, corner ~190 Hz)         XR2211 PLL FSK demod
                                                                      (f0 12.25 k, ±2.5 k track)
                                                                        │ pin 7 DO (open coll.)
                                                                        ▼ 5.1 k pull-up to 3.3 V
                                                                  ESP32 #2 UART2 RX (GPIO16)
                                                                  LDOQ pin 6 ─► GPIO4 (carrier detect)
 Fallback demod if XR2211 can't be sourced: 2 × LM567 tone decoders (10 k and 15 k), ≤ ~500 bps.
```

### 1B. Tier B: MCU-centric (ESP32 LEDC tone generation + ADC/I2S sampling + Goertzel)

```
 TX:  ESP32 #1 ── LEDC or RMT (phase-continuous tone switching) ── 33 Ω ── AO3400 (or IRLZ44N) ── LED
                  (f1/f0 = 10/15 kHz @ 2.5 to 5 kbps, or 20/30 kHz @ 10 kbps)

 RX:  BPW34 ─► TIA + servo (same board as tier A) ─► x101 gain ─┬─► branch A: band-pass ─► XR2211 ─► GPIO16
                                                                 │
                                                                 └─► branch B: 1 µF ─► /3 attenuator
                                                                       ─► Sallen-Key LPF fc ≈ 50 kHz
                                                                          (U3A, 3.3 V rail, bias 1.25 V)
                                                                       ─► 100 Ω/1 nF ─► ESP32 #2 GPIO36
                                                                          (ADC1_CH0, 11 dB atten)
                                                                       ─► adc_continuous @ 200 kS/s
                                                                       ─► Goertzel bins f1, f0 per bit
                                                                       ─► compare |X1|²>|X0|² ─► bit
 One RX board feeds both demodulators from the same received light, so the PLL vs Goertzel
 comparison is head-to-head.
```

### 1C. Tier C: stretch, higher rate (40 to 500 kbps)

```
 TX: ESP32 RMT/SPI bitstream ─ 22 Ω ─ AO3400 ─ LED (5 mm high-brightness RED or BLUE, 30 to 50 mA,
                                               or 1 W red; no phosphor) with an RC "speed-up"
                                               network: R_series ∥ 1 nF
     Modulation: BFSK 100/150 kHz @ 50 kbps (edge-period demod) or Manchester OOK @ 250 to 500 kbps

 RX: BPW34 (5 V reverse bias, Cd ≈ 20 pF) ─► TIA Rf 10 k ∥ 4.7 pF (MCP6022, BW ≈ 2 MHz)
     ─► AC couple (1 nF/10 k, 16 kHz HPF) ─► ×5 gain ─► LM311 comparator with 20 mV hysteresis
     ─► ESP32: RMT-RX or PCNT measures each period (FSK) / UART at 250 to 500 kbaud (Manchester OOK)
     (optional: blue gel filter on the PD to block the slow yellow phosphor light of a white LED)
```

---

## 2. Schematics, component by component, with calculations

### 2.1 Power and references

| Ref | Part | Connection | Notes |
|---|---|---|---|
| PS1 | 5 V 2 A adapter or USB charger | TX: +5 V rail for the LED and the ESP32 VIN | LED peak 0.27 A plus ESP32 about 0.1 A |
| RX 5 V | from the RX ESP32 5 V/VIN pin (USB) | MCP6022 U1/U2, XR2211 VCC | Add 100 nF at every IC VDD pin and 10 µF bulk per board |
| RX 3.3 V | ESP32 3V3 pin | U3 (branch B) only | Keeps the ADC input at or below 3.3 V |
| VREF 2.5 V | 10 k / 10 k divider from 5 V + 10 µF + 100 nF | non-inverting inputs of U1A, U1B, U2B; RHP, CG, R2BP returns | Its AC impedance must be low. If you see hum on VREF, buffer it with a spare op-amp half. |
| VB2 1.25 V | 22 k (to 3V3) / 13 k (to GND) + 10 µF | branch B bias | 3.3·13/35 = 1.23 V |
| GND | single star point at the RX board | | Keep the TX LED current loop away from RX ground. Use separate boards. |

### 2.2 Transmitter

#### 2.2.1 LED driver (tier A and B), simulated in `tx_driver.cir`

| Ref | Value / part | Pins / nodes |
|---|---|---|
| U_TX | ESP32 DevKit (38-pin) | **GPIO25** = tone output. Avoid the strapping pins 0, 2, 12, 15. |
| RG | 100 Ω, ¼ W | GPIO25 → MOSFET gate |
| RGS | 100 kΩ | gate → GND. Keeps the LED off while the ESP32 boots or floats. |
| Q_TX | IRLZ44N (TO-220: pin 1 G, pin 2 D, pin 3 S, tab = D) | S → GND; D → LED cathode |
| D_LED | 1 W white LED on a 20 mm star | anode → R_LED; cathode → drain |
| R_LED | 6.8 Ω, 2 W metal-oxide | +5 V → LED anode |
| C_bulk | 470 µF/10 V + 100 nF across +5 V/GND, right at the LED | supplies the 0.27 A current pulses |

**Calculations**

* LED current: I = (5 − V_F − V_DS) / R = (5 − 3.2 − 0.01) / 6.8 ≈ **0.26 A peak** (simulation: 0.267 A). At 50 % duty the average is about 0.13 A, so the LED is far below its 350 mA rating and runs cool on the star.
  Because V_F of cheap LEDs spreads from 2.9 to 3.5 V, **measure the drop across R_LED** and adjust R (5.6 to 8.2 Ω) for 0.25 to 0.3 A.
* R_LED dissipation: I²R = 0.26²·6.8 = 0.46 W peak, 0.23 W average, so a 2 W part has margin.
* MOSFET: R_DS(on) ≤ 35 mΩ at V_GS 4.5 V (Infineon). At 3.3 V it is somewhat higher, about 50 mΩ typical. Conduction loss = 0.26²·0.05·0.5 ≈ 2 mW. No heatsink needed.
* Gate resistor: the ESP32 pin's default drive is 20 mA, with an absolute maximum of 40 mA.
  RG ≥ 3.3 V / 25 mA − R_pin(≈30 Ω) ≈ 100 Ω.
  IRLZ44N gate charge is about 32 nC at 4.5 V (about 20 nC at 3.3 V), so the gate rise ≈ Q / I_avg ≈ 20 nC / 13 mA ≈ 1.5 µs.
  **Simulated:** gate 10 to 90 % in 0.92 µs, drain fall 82 ns, turn-on delay 0.21 µs. At 15 kHz (33 µs half-period) that is under 3 % of the period, which is fine.
  At 20/30 kHz or in tier C, use the **AO3400** (Q_g ≈ 6 nC, C_iss 630 pF, V_th 0.65 to 1.45 V) with RG = 22 to 33 Ω. The edges then become sub-200 ns.
* LED bandwidth: phosphor-converted white LEDs have about 1 to 3 MHz total modulation bandwidth. The yellow phosphor (~0.5 to 1 MHz) is the slow part; the blue die reaches 10 to 20 MHz. At 10 to 30 kHz the LED is effectively instantaneous. It only matters in tier C, which uses a blue filter at the RX or a red/blue LED.
* Optional 15° TIR lens: on axis, the intensity gain ≈ η(m′+1)/(m+1). With m′ = −ln2 / ln cos 7.5° ≈ 81 and η ≈ 0.8, that is about **30× (+15 dB optical, +30 dB electrical)**. The beam at 3 m is only about 0.8 m wide, so the lens is for range tests, not for coverage.

#### 2.2.2 Tone generation, option (a), recommended: ESP32 LEDC/RMT

* LEDC at 50 % duty: `ledcAttach(25, 10000, 8)`. Switching frequency with `ledcChangeFrequency` causes phase glitches and takes tens of µs. So for 5 to 10 kbps, generate the waveform with **RMT** (each half-period is one RMT item: 50 µs / 33.3 µs) or with a 1 MHz timer ISR. Both give phase-continuous CPFSK and exact frequencies. The details belong to the firmware folder.
* Mapping: idle = mark = logic 1 = **10 kHz**; logic 0 = **15 kHz**. With this, the XR2211 data output (high for the lower frequency) directly reproduces UART polarity.

#### 2.2.3 Tone generation, option (b): XR2206 analog FSK

The datasheet pinout is listed here; check it against your copy before you power up.

| XR2206 pin | Connect |
|---|---|
| 4 V_CC | +12 V. The XR2206 needs 10 to 26 V single supply, so it needs the 12 V adapter. |
| 12 GND | GND |
| 5, 6 TC1/TC2 | C_T = 10 nF film between them |
| 7 TR1 (selected when pin 9 is high or open) | R = 8.2 k + 5 k trimpot to GND → f = 1/(R·C) = 10 kHz needs R = 10.0 k |
| 8 TR2 (selected when pin 9 < 1 V) | R = 5.6 k + 2 k trimpot to GND → 15 kHz needs R = 6.67 k |
| 9 FSK input | MCU UART TX (3.3 V logic is OK: > 2 V selects pin 7) |
| 10 BIAS | 1 µF to GND |
| 11 SYNC (square out, open collector) | 1 kΩ pull-up to +5 V → 47 Ω → IRLZ44N gate. Don't use a 10 k pull-up: with the 1.7 nF gate the edges become 17 µs. |

### 2.3 Receiver analog front end (simulated in `rx_frontend.cir`)

MCP6022 DIP-8 pinout: 1 OUTA, 2 −INA, 3 +INA, 4 VSS (GND), 5 +INB, 6 −INB, 7 OUTB, 8 VDD.

#### 2.3.1 Photodiode and TIA (U1A)

| Ref | Value | Connection |
|---|---|---|
| PD1 | BPW34 | **Cathode → +5 V**, anode → U1 pin 2 (TIN). Find the cathode with a multimeter diode test: the PD reads about 0.4 to 0.6 V when the red probe is on the anode. |
| U1A | MCP6022 half A | pin 3 = VREF 2.5 V, pin 2 = TIN, pin 1 = TOUT |
| RF | 47 kΩ, 1 % metal film | pin 1 ↔ pin 2 |
| CF | 33 pF C0G | pin 1 ↔ pin 2 |

The photodiode sits at 5 − 2.5 = 2.5 V reverse bias, so C_d ≈ 25 to 30 pF. Light → current into TIN → V_TOUT = 2.5 V − I·RF (the output falls with light).

* **Gain choice.** RF sets both transimpedance and headroom. Without the servo, the output saturates at I_amb ≈ 2.4 V / 47 k ≈ 50 µA. That is roughly a brightly lit desk near a window: indoor 500 lux gives about 3 to 4 µA, indirect daylight 1 to 5 klux gives 10 to 50 µA.
  At 3 m the signal (≈ 20 nA peak) gives only about 1 mV at TOUT, so the real gain is placed after the AC coupling.
  A larger RF gains almost no SNR, because the shot noise of the ambient light already dominates. At 10 µA ambient: √(2qI) = 1.8 pA/√Hz, versus 4kT/RF at 47 k = 0.59 pA/√Hz.
* **Stability (minimum CF).** C_in = C_d (30 p) + op-amp C_CM + C_DM (≈ 9 p) + Q1 C_cb (≈ 4 p) + stray (3 p) ≈ 45 pF.
  CF_min ≈ √(C_in / (2π·RF·GBW)) = √(45 p / (2π·47 k·10 MHz)) ≈ **3.9 pF** for about 45° phase margin.
  The chosen 33 pF gives far more margin and deliberately limits bandwidth: f_−3dB = 1/(2π·47 k·33 p) = **103 kHz** (simulated 103.5 kHz). That passes 30 kHz tones and cuts noise.
* **Responsivity.** The BPW34 peaks at about 0.6 A/W near 900 nm. Over a white-LED spectrum (450 nm blue spike plus 550 to 650 nm phosphor) the effective value is about **0.3 A/W**, which is the number used in the link budget. The OPT101 is specified at 0.45 A/W at 650 nm.

#### 2.3.2 Ambient-light DC servo (U1B + Q1)

| Ref | Value | Connection |
|---|---|---|
| RI | 100 kΩ | TOUT → U1 pin 6 |
| CI | 39 nF film | U1 pin 7 ↔ pin 6 |
| U1B | MCP6022 half B | pin 5 = VREF, pin 7 = IOUT |
| RB | 1 kΩ | IOUT → Q1 base |
| Q1 | BC547B (TO-92: C-B-E, flat side facing you) | collector → TIN, emitter → RE |
| RE | 10 kΩ | Q1 emitter → GND |

How it works: when ambient light pulls TOUT below VREF, the integrator output rises and Q1 sinks I_C = (V_B − 0.65)/RE from the TIA input. That cancels the DC photocurrent, so TOUT returns to 2.5 V.

* Loop gain L(s) = RF / (RE·s·RI·CI), giving a first-order high-pass at the TIA output with f_c = RF / (2π·RE·RI·CI) = 47 k / (2π·10 k·100 k·39 n) ≈ **190 Hz**. Simulated: −3 dB at 153 Hz, −5 dB at 100 Hz.
* Capacity: I_max ≈ (4.9 − 0.65) / 10 k ≈ **0.4 mA**, which covers bright indirect daylight. Direct sunlight on a bare BPW34 (about 1 to 2 mA) still saturates it: shade the PD with a 2 to 3 cm black tube.
* Built-in ambient meter: **V(RE) / 10 kΩ = ambient photocurrent** (10 µA → 100 mV). Log it on the scope or with a spare ESP32 ADC pin for every experiment.
* Noise cost: Q1 adds shot noise equal to the ambient's, a √2 penalty (about 1.5 dB SNR). That buys a 10× wider ambient range. For dim-room tests you can pull Q1 out.

#### 2.3.3 AC-coupled gain stage (U2A), ×101

| Ref | Value | Connection |
|---|---|---|
| CC1 | 4.7 nF film | TOUT → U2 pin 3 (HIN) |
| RHP | 10 kΩ | HIN → VREF. First HPF corner: 1/(2π·10 k·4.7 n) = **3.39 kHz** |
| RG2 | 100 kΩ | U2 pin 1 (GOUT) ↔ pin 2 |
| RG1 + CG | 1 kΩ in series with 100 nF | pin 2 → VREF. Gain = 1 + 100 k/1 k = 101 (40 dB) above 1/(2π·1 k·100 n) = **1.59 kHz**; unity gain at DC, so no offset amplification |

Closed-loop bandwidth ≈ GBW/101 ≈ 99 kHz (simulated stage −3 dB band 3.7 to 70 kHz). The output can clip at the rails at short range, which is harmless for FSK because the information is in the zero-crossings.

#### 2.3.4 Branch A: MFB band-pass (U2B), f0 = 12.25 kHz, Q = 1.5, H0 = −2

Design with C1 = C2 = C = 2.2 nF and ω0 = 2π·12 247:

* R3 = 2Q/(ω0C) = 3 / 1.693e-4 = 17.7 k → **18 k**
* R1 = Q/(ω0C·H0) = 4.43 k → **4.3 k** (E12: 4.7 k)
* R2 = Q/(ω0C(2Q² − H0)) = 1.5/(1.693e-4·2.5) = 3.54 k → **3.6 k** (E12: 3.9 k)

| Ref | Value | Connection |
|---|---|---|
| R1BP | 4.3 k | GOUT → node MID |
| R2BP | 3.6 k | MID → VREF |
| C1BP | 2.2 nF C0G/film | MID → U2 pin 6 |
| C2BP | 2.2 nF C0G/film | MID → U2 pin 7 (BPOUT) |
| R3BP | 18 k | pin 7 ↔ pin 6 |
| U2B | MCP6022 half B | pin 5 = VREF |
| CXR | 100 nF | BPOUT → XR2211 pin 2 |

−3 dB band = f0[√(1 + 1/4Q²) ± 1/(2Q)] = **8.8 to 17.0 kHz**. Simulated: 9.0 to 16.8 kHz, peak 12.30 kHz. 10 kHz and 15 kHz are both down only 1.4 dB and are equal, so the PLL sees no amplitude bias.
With the E12 substitutes (4.7 k / 3.9 k) f0 moves to about 11.7 kHz, which is still fine.

#### 2.3.5 Branch B: anti-alias filter to the ESP32 ADC (U3A on 3.3 V)

| Ref | Value | Connection |
|---|---|---|
| CC2 | 1 µF | GOUT → AIN |
| RA1 / RA2 | 2 k / 1 k | AIN → AX → VB2 (1.25 V). This /3 attenuator keeps a 5 V-pp clipped signal inside the 0.15 to 2.45 V ADC window. |
| RSK1, RSK2 | 2.0 k, 2.7 k | AX → S1 → S2 (unity-gain Sallen-Key; the 667 Ω source adds to RSK1) |
| CSK1 | 1.5 nF | S1 → U3A output (feedback cap) |
| CSK2 | 680 pF | S2 → VB2 |
| U3A | MCP6022 (VDD = 3.3 V), follower | +IN = S2, OUT = −IN = ADCBUF |
| RADC / CADC | 100 Ω / 1 nF | ADCBUF → **GPIO36 (VP, ADC1_CH0)** with 1 nF to GND. Supplies the SAR sampling-cap charge. |

f_c ≈ 1/(2π√(R1R2C1C2)) ≈ 50 kHz (simulated −3 dB at 49.5 kHz). At 30 kHz it is −0.4 dB; at 100 kHz −15 dB, at 200 kHz −35 dB (fs = 200 kS/s, Nyquist 100 kHz).
Use **ADC1**, not ADC2: ADC2 is unusable while Wi-Fi is on.
Sampling uses the ESP-IDF `adc_continuous` (DMA) driver. The classic ESP32 accepts up to about 2 MS/s nominal; 200 kS/s is used for margin and better ENOB.

Goertzel parameters (for the firmware folder):

| Mode | Tones | Rb | fs | N = fs/Rb | bins k = f·N/fs | coeff = 2cos(2πk/N) |
|---|---|---|---|---|---|---|
| B1 (comparison) | 10 / 15 kHz | 5 kbps | 200 kS/s | 40 | 2, 3 | 1.8478, 1.6180 |
| B2 (safe) | 10 / 15 kHz | 2.5 kbps | 200 kS/s | 80 | 4, 6 | 1.9754, 1.9021 |
| B3 (10 kbps) | 20 / 30 kHz | 10 kbps | 200 kS/s | 20 | 2, 3 | 1.6180, 1.1756 |

#### 2.3.6 Op-amp trade-off (what fits this board)

| Op-amp | GBW | Input bias | Noise | Rails / supply | Package | India availability (seen) | Verdict |
|---|---|---|---|---|---|---|---|
| **MCP6022** | 10 MHz | 1 pA | 8.7 nV/√Hz | RRIO, 2.5 to 5.5 V | DIP-8 dual | Robu DIP Rs 211 (older listing showed in stock); SOIC Rs 171 (out of stock when checked) | **Recommended**: one part for every stage, works on 3.3 V and 5 V |
| AD8605 | 10 MHz | 0.2 pA | 8 nV/√Hz | RRIO, 2.7 to 5.5 V | SOT-23-5 single | Robu Rs 88 (out of stock when checked) | Equally good electrically; needs SOT adapters (×5) |
| OPA380 | 90 MHz | 3 pA | 5.8 nV/√Hz | RRIO, 2.7 to 5.5 V | MSOP/SOIC | not found at the four target stores | Overkill below 100 kHz; consider only for tier C |
| LM358 | ~0.7 to 1 MHz | 20 to 45 nA | ~40 nV/√Hz | output only reaches V+ − 1.5 V; 0.3 V/µs | DIP-8 | Rs 10 to 20 everywhere | OK only for the 1.2/2.2 kHz bring-up; the ×101 stage would have about 10 kHz bandwidth, so **not for 10 to 30 kHz** |

Alternative detectors:
* **OPT101**: internal 1 MΩ, 14 kHz bandwidth. It saturates at about 4.5 µA, i.e. an ordinary lit room, and costs Rs 1,150 to 1,550 in India. Not recommended.
* **BPW21**: has a built-in eye-response filter that rejects sunlight IR, but its ~580 pF capacitance limits RF·C bandwidth. Worth trying only if sunlight IR dominates.

### 2.4 XR2211 FSK demodulator (branch A output)

Datasheet design equations (MaxLinear/Exar XR-2211A rev 1.04):
* f0 = √(f1·f2)
* C0 = 1/(R0·f0)
* R1 = 2·R0·f0 / (f1 − f2)
* C1 = 1250·C0 / (R1·ζ²), with ζ = 0.5
* RF ≥ 5·R1, RB ≥ 5·RF
* Rsum = (RF + R1)·RB / (R1 + RF + RB)
* CF = 0.25 / (Rsum·Baud)
* V_REF = V_CC/2 − 0.65 V (1.85 V at 5 V supply)

**Main plan: 10 / 15 kHz**
* f0 = √(150e6) = **12 247 Hz**
* R0 = 15 k + 10 k multiturn trimpot (nominal 20.9 k)
* C0 = **3.9 nF** film/C0G
* R1 = 2·20.9 k·12 247 / 5000 = 102 k → **100 k**
* C1 = 1250·3.9 n / (100 k·0.25) = 195 pF → **220 pF** (ζ = 0.47)
* RF = **470 k** (4.7·R1)
* RB = **2.2 M** (4.7·RF; 2 × 1 M + 220 k if the kit stops at 1 M)
* Rsum = 570 k·2.2 M / 2.77 M = **453 k**
* CF = 0.25/(453 k·5000) = **110 pF → 100 pF** at 5 kbps; **220 pF** at 2.5 kbps
* CD (lock-detect filter) ≥ 16/Δf µF with Δf = 5 kHz → 3.2 nF minimum; use **47 to 100 nF** with RD = 470 k so the carrier-detect output doesn't chatter.

**Bring-up plan: Bell-202, 1200 / 2200 Hz, 1200 bps** (datasheet example):
R0 = 10 k + 10 k pot, C0 = 39 nF, R1 = 51 k, C1 = 3.9 nF, RF = 270 k, RB = 1.2 M, CF = 1 nF.
Drive pin 2 directly from the function generator (FSK mode, 100 mV rms). The 12.25 kHz band-pass would block these tones.

| XR2211 pin | Connect (main plan) |
|---|---|
| 1 VCC | +5 V, 100 nF + 10 µF to GND (4.5 to 20 V allowed) |
| 2 INP | from CXR 100 nF (internal 20 k). 10 mV to 3 V rms; limits above about 2 mV rms |
| 3 LDF | RD 470 k ∥ CD 47 to 100 nF to GND |
| 4 GND | GND |
| 5 LDOQN | 5.1 k pull-up to 3.3 V (optional "no carrier" LED) |
| 6 LDOQ | 5.1 k pull-up to 3.3 V → ESP32 **GPIO4** (carrier detect). Datasheet Fig. 11 alternative: tie pin 6 to pin 7 so data is forced low without a carrier. |
| 7 DO | 5.1 k pull-up **to 3.3 V** (open collector, so it is 3.3 V-safe) → ESP32 **GPIO16 (UART2 RX)**; RB 2.2 M from pin 7 to pin 8 (hysteresis) |
| 8 COMP I | RF 470 k from pin 11; CF 100 pF to GND (datasheet Fig. 10 shows CF on pin 8; check your copy for GND vs V_REF return) |
| 9 NC | ,  |
| 10 VREF | 100 nF to GND (mandatory); C1 220 pF from pin 11 to pin 10 |
| 11 LDO (loop phase detector out) | R1 100 k to pin 12; RF to pin 8; **scope this pin**: it is the analog demodulated data |
| 12 TIM R | R0 = 15 k + 10 k trimpot to GND |
| 13, 14 TIM C | C0 3.9 nF between them |

Tuning: send alternating 0/1 (0x55 at 5 kbps) and trim R0 until pin 7 shows a 50 % duty cycle (datasheet procedure).
Output polarity: pin 7 is high for the low tone (10 kHz = mark = 1), which matches UART idle.

**Availability warning.** No XR2211 listing was found at robu.in, robocraze.com, electronicscomp.com or evelta.com; the electronicscomp search returned nothing. Tayda lists it at $1.75 but was out of stock, and other listings are overseas brokers. Plan on importing one (LCSC, Tayda, eBay; about Rs 150 to 250 plus shipping) or using the fallback below. The part is marked obsolete by MaxLinear.

### 2.5 Fallback demodulator: 2 × LM567 (Rs 24 to 29 each in India)

Each LM567 detects one tone.
* f0 = 1/(1.1·R1·C1), with C1 = 10 nF:
  * 10 kHz: R1 = 9.1 k (8.2 k + 2 k trimpot)
  * 15 kHz: R1 = 6.1 k (5.6 k + 1 k trimpot)
* Bandwidth ≈ 1070·√(V_in / (f0·C2)) %, with V_in ≤ 200 mV rms and C2 in µF. For 10 % at 10 kHz: C2 ≈ 0.22 µF. Output filter C3 ≈ 2·C2 = 0.47 µF.
* Pins: 1 C3, 2 C2, 3 input (≤ 200 mV rms, so add a 10:1 divider from BPOUT), 4 +5 V, 5 R1, 6 C1, 7 GND, 8 open-collector output (10 k pull-up to 3.3 V).
* The ESP32 reads both outputs; a bit = (15 k detector active) ? 0 : 1.
* Detection needs about 10 to 20 cycles, so expect only **300 to 500 bps**. It works as a demo, but not for the comparison.

### 2.6 Tier C component values

| Block | Values |
|---|---|
| TX | AO3400 on a SOT-23 adapter, RG 22 Ω, RGS 100 k. LED: 5 mm high-brightness red or blue, 40 mA: R = (5 − 2.0 − 0.05)/0.04 ≈ 75 Ω for red (blue: (5 − 3.1)/0.04 ≈ 47 Ω). Pre-emphasis: 1 nF across R (τ = 75 ns) overdrives the edges. |
| RX TIA | BPW34 at 2.5 V (or a separate 12 V for Cd ≈ 12 pF), RF 10 k, CF 4.7 pF. f_−3dB = √(GBW/(2π·RF·C_in)) ≈ √(10 M/(2π·10 k·35 p)) ≈ 2.1 MHz; 1/(2π·10 k·4.7 p) = 3.4 MHz, so about 2 MHz overall. |
| Gain + comparator | 1 nF/10 k AC coupling (16 kHz HPF) → MCP6022 ×5 (BW ≈ 2 MHz) → **LM311** (open collector, 1 k pull-up to 3.3 V, about 200 ns response). Hysteresis: 1 k input divider + 100 k positive feedback ≈ 30 mV. |
| Decoding | FSK 100/150 kHz @ 50 kbps: ESP32 RMT-RX or PCNT measures the period of each cycle (6.7 µs vs 10 µs). OOK Manchester @ 250 to 500 kbps: ESP32 UART + software Manchester. |
| Expected | 2× to 10× faster than tier B. The limits are the white LED's phosphor and the LM311 edge rate; a TLV3501 (4.5 ns) is a drop-in upgrade if you can source it. |

### 2.7 Link budget (Lambertian LOS), computed in `sim/link_budget.py`

The LOS DC channel gain gives received optical power:

P_rx = P_t·(m+1)/(2πd²)·cos^m(φ)·A·cos(ψ)   (with ψ within the PD field of view)

Assumptions:
* P_t(on) = 0.25 W optical (1 W white LED at 0.27 A, about 30 % efficient)
* m = 1 (60° half-power angle)
* A = 7.5 mm²
* R = 0.30 A/W
* The square-wave fundamental is (√2/π)·I_on rms
* Noise: PD shot + servo-transistor shot of the ambient current, RF thermal, and signal shot, in the simulated branch-A noise bandwidth **B_eq = 11.3 kHz**
* Non-coherent FSK: BER = ½·exp(−Eb/2N0)

| d (m) | angle | P_rx peak (µW) | I_on (nA) | I_sig rms (nA) | XR2211 input (mV rms) | ambient (µA) | noise (pA rms) | SNR (dB) | Eb/N0 @4.8 to 5 kbps (dB) |
|---|---|---|---|---|---|---|---|---|---|
| 0.5 | 0° | 2.39 | 716 | 322 | clips at ~1.7 V (fine for FSK) | 10 | 279 | 61 | 65 |
| 1 | 0° | 0.60 | 179 | 81 | 647 | 2 / 10 / 50 | 137 / 277 / 605 | 55 / 49 / 43 | 59 / 53 / 46 |
| 2 | 0° | 0.15 | 45 | 20 | 162 | 10 | 277 | 37 | 41 |
| 3 | 0° | 0.066 | 20 | 9.0 | 72 | 2 / 10 / 50 | 136 / 276 / 605 | 36 / 30 / 23 | 40 / 34 / 27 |
| 3 | 30° tx & rx | 0.050 | 15 | 6.7 | 54 | 10 | 276 | 28 | 31 |
| 3 + 15° TX lens | 0° | 2.0 | 597 | 269 | clips | 10 | 278 | 60 | 63 |

What the table means:
* Thermal and shot noise alone predict BER < 10⁻¹² everywhere in the 0.5 to 3 m target, because ideal non-coherent FSK needs only 14.2 dB Eb/N0 for 10⁻⁶.
* Estimated maximum range at 10 kbps, keeping 10 dB implementation margin: about **6 m (dim, 2 µA), 4.4 m (10 µA), 3.0 m (50 µA near a window)** with the bare LED.
* **In practice the link will be limited by interference, not noise:**
  * harmonics of lamp flicker
  * CFL and electronic-ballast tubes switching at 20 to 60 kHz, right next to the 20/30 kHz tones
  * PWM-dimmed LED panels at 1 to 20 kHz
  * misalignment, PLL lock range, and bit-timing slips
* This is why section 5 measures the ambient spectrum first.
* The XR2211 input level stays above its 10 mV rms threshold out to about 7 m, so no AGC is needed.

---

## 3. Netlists and simulation results

* **Simulator:** ngspice 44.2 ran in the sandbox: Debian `.deb`s extracted to user space, since there was no root access. Results below are from it.
* **LTspice:** both `.cir` files are plain SPICE (`.subckt`, `.model ... VDMOS`, `.ac` / `.tran`) and open directly. Plot `V(bpout)`, `V(adc)`, `V(tout)`; with AC 1 A in `IPH`, volts = ohms of transimpedance.
* **ngspice on your PC:** `cd sim && ngspice -b rx_ac.sp && ngspice -b tx_tran.sp && python3 make_plots.py && python3 link_budget.py`.
* **Models:** the op-amp is a single-pole macro (A0 = 100 dB, GBW = 10 MHz, 6 pF inputs). It has no slew limit, clipping or voltage noise, so swap in Microchip's MCP6022 SPICE model for large-signal checks. The IRLZ44N and AO3400 VDMOS models are approximate fits to datasheet headline numbers, and the LED is a diode fitted to V_F = 3.2 V at 0.3 A.

RX AC results (ngspice, `rx_ac_response.png`):

| Node | Midband | −3 dB band | Key points |
|---|---|---|---|
| TOUT (TIA + servo) | 93.4 dBΩ = 46.8 kΩ | 153 Hz to 103.5 kHz | 100 Hz: −5 dB (servo) |
| GOUT (×101) | 133.2 dBΩ = 4.6 MΩ | 3.7 to 70 kHz | |
| **BPOUT (to XR2211)** | **139.6 dBΩ = 9.5 MΩ peak at 12.30 kHz** | **9.0 to 16.8 kHz** | 10 kHz: 138.1 dBΩ, 15 kHz: 138.1 dBΩ (equal, −1.5 dB); **100 Hz: 34.9 dBΩ → 105 dB rejection**; 1.2 kHz: −37 dB |
| **ADC (to ESP32)** | 123.7 dBΩ = 1.53 MΩ | 3.7 to 49.5 kHz | 20 k: 123.7, 30 k: 123.2 dBΩ; 100 Hz: −61 dB; 100 kHz: −15 dB; 200 kHz: −35 dB |

* DC operating point with 10 µA ambient: TOUT 2.500 V (the servo removed the DC exactly), U1B output 0.62 V, V(RE) = 0.100 V (= 10 µA), all stages centred on their bias.
* Noise (`rx_noise.png`): circuit noise at BPOUT is 1.30 mV rms (100 Hz to 100 kHz), equivalent to 136 pA rms at the input in band, which includes Q1's shot noise. Add the photodiode's own ambient shot noise for the totals in section 2.7.

TX transient (`tx_transient.png`, 15 kHz tone):

| Quantity | Value |
|---|---|
| LED on-current | 267 mA |
| V_DS(on) | 9 mV |
| Off leakage | 2.7 µA |
| Gate rise (10 to 90 %) | 0.92 µs (Miller plateau) |
| Drain fall | 82 ns |
| Turn-on delay | 0.21 µs |
| Off-state drain | ~2.8 V (LED sub-threshold) |

---

## 4. Bill of materials (INR, incl. GST where shown)

Prices are what the linked page or search listing showed in Oct 2026; stock changes daily. Every URL below was seen via search or fetch. **"No URL"** means none was verified, so buy it from a local shop or any kit.

### 4.1 Core: tiers A + B on one RX board

| # | Part | Qty | Unit Rs | Line Rs | Store URL (seen) | Note |
|---|---|---|---|---|---|---|
| 1 | ESP32 38-pin DevKit (WROOM-32) | 2 | 422 | 844 | https://robocraze.com/products/esp32-development-board | TX + RX. Cheaper option: Rs 340 at https://robukits.in/product/301/esp32-development-board-esp32-devkit-v1 |
| 2 | MCP6022-I/P dual op-amp DIP-8 | 3 | 211 | 633 | https://oldwp.robu.in/product/mcp6022-i-p-microchip-operational-amplifier-dual/ | U1, U2, U3. SOIC alternative Rs 171 (OOS): https://robu.in/product/mcp6022-e-sn-microchip-operational-amplifier-dual-2-channels-10-mhz-7-v-%c2%b5s-2-5v-to-5-5v-soic-8-pins/ |
| 3 | XR2211 FSK demodulator | 1 | ~200 (import) | 200 | **not stocked at the four Indian stores**; Tayda (OOS): https://www.taydaelectronics.com/xr2211-fsk-demodulation-tone-decoder-pdip-14.html | Order early, or use row 4 |
| 4 | LM567 tone decoder (fallback) | 2 | 29 | 58 | https://electronicspices.com/product/lm567-tone-decoder-ic | Optional if the XR2211 arrives |
| 5 | BPW34 PIN photodiode | 2 | 59 | 118 | https://rajivelectronics.com/product/bpw34-silicon-pin-photodiode-sensor-dip2-bpw34-photodiode | Also Rs 64: https://robodium.com/products/bpw34-silicon-pin-photodiode ; Rs 92: https://www.sunrom.com/p/bpw34 |
| 6 | IRLZ44N logic-level MOSFET | 2 | 44 | 88 | https://robu.in/product/irlz44n/ | |
| 7 | BC547 NPN (servo Q1) | 2 | ~9 | 9 | https://ebhoot.com/products/bc547-npn-dip-transistor | Listing price Rs 8.5 (pack option) |
| 8 | 1 W white LED with star heatsink | 2 | 13 | 26 | https://componentstree.com/product/1w-white-led-with-heat-sink-high-brightness-power-led-module/ | |
| 9 | 6.8 Ω 2 W metal-oxide resistor | 2 | 14 | 28 | https://sumangenergy.com/product-category/electronics/resistors/wirewound-resistors/ | Showed out of stock; any 5.6 to 8.2 Ω 2 W from a local shop |
| 10 | Metal-film resistor kit, 600 pcs, 30 values, 1 % | 1 | 174 | 174 | https://robu.in/product/30-different-valued-metal-film-resistor-assorted-kit-for-diy-electronic-projects-and-experiments/ | E24 values (4.3 k, 3.6 k) may need series combos |
| 11 | Ceramic capacitor kit, 30 values, 2 pF to 0.1 µF | 1 | 188 | 188 | https://oldwp.robu.in/product/ceramic-capacitor-assorted-kit-30-kinds-from-2pf-0-1uf/ | Use C0G/film for C0, CF, BPF caps where possible |
| 12 | 3296W 10 k multiturn trimpot | 3 | 18 | 54 | https://oldwp.robu.in/product/3296w-10k-ohm-trimpot-trimmer-potentiometer-pack-of-5/ | XR2211 R0, LM567, spare |
| 13 | MB102 830-point breadboard | 2 | 64 | 128 | https://robocraze.com/products/mb102-830-points-solderless-breadboard | TX and RX separate |
| 14 | Perfboard 10 × 15 cm | 2 | 49 | 98 | https://anuelectronics.com/products/10-x-15-cm-universal-pcb-prototype-board-single-sided-perfboard-4-x-6-inch | Final RX build (robu Rs 99, OOS: https://robu.in/product/10-x-15-cm-universal-pcb-prototype-board-single-sided-2-54mm-hole-pitch/ ) |
| 15 | 20 mm 15° TIR LED lens | 2 | 15 | 30 | https://electronifyindia.com/products/20mm-led-lens-15-degree-for-high-power-led-light | One on TX, one reversed over the PD as a ±7.5° concentrator |
| 16 | 5 V 2 A adapter (TX LED rail) | 1 | 183 | 183 | https://robocraze.com/collections/ac-dc-converters | Listed as "5V 2A Power Adapter Rs 183". Skip it if a 2 A phone charger plus USB cable powers the TX ESP32 VIN. |
| 17 | Electrolytics (10 µF ×6, 470 µF ×1), jumper wires, 2 × 8-pin + 1 × 14-pin DIP sockets | 1 lot | ~80 | 80 | no URL | Local shop |
| | **Core total (tiers A + B)** | | | **≈ Rs 2,939** | | Rs 2,698 without the optional adapter and LM567s. Add Rs 0 to 150 shipping; free above Rs 999 per store at Robu and Robocraze, so consolidate orders. |

### 4.2 Optional and tier C add-ons

| Part | Qty | Rs | URL (seen) | Use |
|---|---|---|---|---|
| AO3400 SOT-23 MOSFET | 5 | 8 ea | https://robu.in/product/ao3400-xblw-30v-5-8a-34m%25cf%25894-5v5a-1-4w-700mv250ua-1-n-channel-sot-23-3l-mosfets-rohs/ | Fast switch for tiers B and C |
| SOT-23 to DIP adapter (7Semi) | 2 | 29 | https://robocraze.com/products/sot23-3-sot23-5-sot23-6-sot23-8-smd-to-dip-pcb-adapter-board-7semi (also https://evelta.com/7semi-sot23-3-sot23-5-sot23-6-sot23-8-smd-to-dip-pcb-adapter-board/) | For the AO3400 |
| LM311 comparator DIP-8 | 1 | 19 | https://www.electronicscomp.com/lm311-ic (robu Rs 17: https://oldwp.robu.in/product/lm311-voltage-comparator-ic-dip-8-package/) | Tier C slicer |
| XR2206 signal-generator kit (soldered) | 1 | 330 | https://techtonics.in/product/xr2206-high-precision-signal-generator-soldered | Analog TX option; needs 9 to 12 V. The bare IC is Rs 595 to 729 in India, so the kit is cheaper. |
| 12 V 2 A adapter | 1 | 185 | https://robocraze.com/products/12-volt-2-amp-power-adapter-ac-to-dc | Only for the XR2206 |
| Convex glass lens set (50 mm, f 15 to 30 cm) | 1 | 79 | https://sciencestore.in/products/convex-lens-1 | High-gain RX optics for long-range tests (FOV only about ±0.5°) |
| OPT101 module | ,  | 1,150 to 1,769 | https://www.dnatechindia.com/opt101-light-intensity-sensor-module-fr-01-133-buy-in-india.html | Not recommended (section 2.3.6) |
| AD8605 SOT-23 op-amp | ,  | 88 | https://robu.in/product/ad8605artz-reel-analog-devices-operational-amplifier-1-amplifier-10-mhz-5-v-%c2%b5s-2-7v-to-5-5v-sot-23-5-pins/ | Alternative to the MCP6022 |

---

## 5. Test and measurement plan

### 5.1 Stage-by-stage bring-up (scope at each point)

| Step | Stimulus | Probe | Expect | Pass criterion |
|---|---|---|---|---|
| 1. XR2211 alone | Function generator in FSK mode: 1200/2200 Hz, 1200 bps, 100 mV rms into pin 2 (Bell-202 values) | pin 11 (analog), pin 7 (data) vs FG trigger | Clean square at pin 7 that copies the FG's keying | Duty within 50 ± 5 % on 0x55 after trimming R0 |
| 2. Main XR2211 values | FG FSK 10/15 kHz, 5 kbps, 100 mV rms | pin 11, 8, 7 | Pin 11 eye open, pin 7 = data | Correct bits at 10 mV to 1 V rms input |
| 3. TX driver | ESP32 tone 10 kHz | CH1 gate, CH2 drain; LED current = V across R_LED / 6.8 | Gate rise ≈ 1 µs, drain fall < 0.2 µs, I_on 0.25 to 0.3 A | Matches `tx_transient.png`; MOSFET cold to touch |
| 4. TIA DC | no TX, room light | TOUT, V(RE) | TOUT = 2.50 V ± 20 mV (servo on); V(RE)/10 k = ambient current | Log V(RE) for every later experiment |
| 5. TIA AC | TX at 1 m, 10 kHz | TOUT (AC-coupled, 1 mV/div) | ~8 mV p-p square (179 nA × 47 k), plus 100 Hz ripple | No oscillation: scope at 1 MHz span shows nothing near 1 to 5 MHz |
| 6. Gain stage | same | GOUT | ~0.8 V p-p, rounded square | Not clipping at 1 m; clipping at 0.5 m is OK |
| 7. Band-pass | same | BPOUT, scope FFT | Sine at 10 or 15 kHz; 100 Hz component below the noise | FFT: 100 Hz at least 60 dB under the tone |
| 8. Front-end Bode | FG sine sweep 100 Hz to 200 kHz into the gate (square drive; read the fundamental) or, better, FG → 100 kΩ → TIN for electrical injection (10 µA/V) | BPOUT, ADC node | Compare with `rx_ac_response.png` | Peak within ±10 % of 12.3 kHz; within ±2 dB of simulation |
| 9. ADC branch | TX at 1 m | ADCBUF (≤ 3.3 V!), ESP32 raw dump | 1.25 V centred, ≤ 2.4 V p-p | Goertzel bins separate by > 20 dB |

### 5.2 BER test method

1. The TX ESP32 sends framed **PRBS-15** (x¹⁵ + x¹⁴ + 1) as 8N1 UART bytes. Frame: preamble 0x55 ×8, sync word 0xD3 0x91, 64-byte payload, CRC-16.
2. The RX ESP32 runs the same PRBS generator. After sync it XOR-compares received bits, counting bit errors, frame errors and lost syncs. It prints `d, angle, lux/V(RE), Rb, demod, bits, errors` over USB serial to a laptop CSV logger.
3. Do both demodulators in the same run: the XR2211 path on UART2 and the Goertzel path on the ADC see identical light.
4. Bits per point: run until 100 errors or 10⁷ bits (about 33 min at 5 kbps, 17 min at 10 kbps). With zero errors in N bits, report **BER < 3/N** (95 % confidence).
5. Eye diagrams: XR2211 pin 11 and the Goertzel decision metric (|X1|² − |X0|²) with scope persistence, triggered on the TX bit clock (spare GPIO).

### 5.3 Experiments and expected plots

| Experiment | Sweep | Fixed | Expected plot / result |
|---|---|---|---|
| Range | d = 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5 m (tape on the floor) | 0°, 5 kbps, room LED tubes | BER vs d (log y): floor below 10⁻⁶ to about 3 to 4 m, then a cliff. Overlay the received tone amplitude at BPOUT (should fall as 1/d²) and the link-budget curve. |
| Angle | TX tilt and RX tilt, 0 to 60° in 10° steps | 1 m and 2 m | Amplitude follows cos^m(φ)·cos(ψ) with m ≈ 1; BER cliff near 50 to 60°. With lenses: a sharp cliff at ±7.5°. |
| Ambient | dark / room LED / CFL / tube / window daylight / phone flashlight as interferer | 2 m | V(RE)-measured ambient on x, BER and tone SNR on y. Expect graceful loss with DC (servo) but **sharp loss with CFL/ballast interference near 20 to 60 kHz**, which hits tier B3 more than 10/15 kHz. |
| Ambient spectrum | none (TX off) | | Scope FFT of GOUT, 0 to 100 kHz, for each light source. This is the data for adaptive tone selection. |
| Bit rate | 1.2 (Bell), 2.5, 5, 7.5, 10 kbps | 2 m | BER vs Rb for PLL vs Goertzel. Expect the XR2211 to degrade above about 5 kbps on 10/15 kHz (loop settling), and the Goertzel path to hold to 5 kbps on 10/15 kHz and to 10 kbps on 20/30 kHz. |
| PLL vs Goertzel | same light, same frames | all above | Paired BER table and a cost/complexity comparison: the paper figure. |
| Throughput demo | text and small file transfer | 1 m | Goodput vs raw rate (framing/CRC overhead) |

### 5.4 Measurements to record per point

Distance, angles, V(RE) (ambient), tone amplitude at BPOUT (mV rms), noise floor at BPOUT with TX off, BER per demod, XR2211 lock flag (pin 6) duty, LED current, room light type, time.

---

## 6. Common pitfalls and debugging checklist

**Optics and light**
- [ ] PD reversed: with the cathode not at +5 V, TOUT rises with light and the servo runs away. Check the multimeter diode test.
- [ ] Direct sun or a desk lamp shining on the PD saturates even the servo (V(RE) > 4 V). Add a 2 to 3 cm black-tube shade (a pen barrel works) or move it.
- [ ] CFL, tube-light ballasts or PWM-dimmed panels inject 20 to 60 kHz lines: look at the GOUT FFT with TX off. If a line lands near a tone, move the tones (keep Δf = Rb) or switch off that lamp. Note it in the paper.
- [ ] Phone cameras show the LED flickering at 10 kHz (rolling shutter). That's normal and not visible to the eye.
- [ ] A lens on the TX makes the link alignment-critical: align it with the TX running a 10 kHz tone while watching BPOUT amplitude.

**Analog**
- [ ] TIA oscillates (MHz ringing at TOUT, scope at 1 µs/div): CF is missing or too small (< 4 pF), or there is a long wire at TIN. Keep the PD leads under 1 cm and put RF/CF right on the op-amp pins.
- [ ] Huge 100 Hz at GOUT: the servo isn't working (check Q1 pinout C-B-E and integrator polarity: U1B (+) = VREF, (−) via RI from TOUT). Another cause is VREF ripple: decouple VREF with 10 µF at each op-amp.
- [ ] Gain stage drifts or latches: CG must be in series with RG1 to VREF (not to GND), or the ×101 gain amplifies the offset and DC.
- [ ] Band-pass peak at the wrong frequency: X7R ceramics lose capacitance with temperature and voltage. Use C0G or film for 2.2 nF, 3.9 nF and 220 pF.
- [ ] MCP6022 on 5 V feeding the ESP32 ADC directly will kill the pin. Only U3 (on 3.3 V) may touch GPIO36.
- [ ] Ground loops: the TX and RX ESP32s are both on laptop USB, so the shared ground carries LED current and noise. Power the TX from a separate charger.

**XR2211 / PLL**
- [ ] No output: pin 10 needs 100 nF (mandatory per the datasheet); input must be AC-coupled; V_CC ≥ 4.5 V.
- [ ] Output stuck high or low: f0 is mistuned. Send 0x55 and trim R0 for 50 % duty, and check pin 11 swings around V_REF.
- [ ] Bit errors at 5 kbps but fine at 2.5 kbps: CF too large (data filter too slow) or C1 too large (loop too slow). Try CF 68 to 100 pF; check ζ ≈ 0.5.
- [ ] Polarity inverted: pin 7 is high for the low tone. Either swap the tone map at TX or invert in the ESP32 UART (`uart_set_line_inverse`).
- [ ] Pull-up to 5 V on pin 7 feeding the ESP32 exceeds 3.6 V abs max: pull up to 3.3 V only.

**TX / firmware**
- [ ] LED flashes at ESP32 boot: RGS 100 k is missing, or a strapping pin is used for the gate.
- [ ] Frequency glitches at bit boundaries (spectral splatter, PLL slips): use RMT/timer phase-continuous switching, not repeated `ledcChangeFrequency`.
- [ ] The UART start bit is lost because the TX emits no carrier between frames: keep the carrier on (idle mark at 10 kHz) and send a 0x55 preamble.
- [ ] Goertzel bins mismatched: fs drifts from the nominal 200 kS/s. Measure the real rate by timing 10⁶ samples; use non-integer-k Goertzel if needed.
- [ ] Wi-Fi on and ADC2 used: ADC2 is blocked by Wi-Fi. Always use ADC1 (GPIO32 to 39).

**Measurement hygiene**
- [ ] Scope ground lead pickup at 10 kHz: use the short ground spring on BPOUT/TOUT.
- [ ] Record V(RE) (ambient) with every BER point; without it the ambient experiments can't be compared.
- [ ] Repeat each point three times, at different times of day, because daylight varies.

---

## Notes, assumptions, open items

* The link budget assumes 0.25 W optical from the 1 W LED and 0.30 A/W effective BPW34 responsivity for white light. Both are estimates (±3 dB). Measure TOUT at 1 m to calibrate: expect about 8 mV p-p.
* The simulation op-amp is an ideal-ish macro. Large-signal clipping, slew rate and op-amp voltage noise aren't modelled; at these frequencies they are negligible, apart from intentional clipping at short range.
* The XR2206 pin assignments and the XR2211 CF/C1 return pins come from the datasheet figures as described. Check them against your printed datasheet before soldering.
* Prices and stock are as seen during the search in Oct 2026. Several low-cost listings (MCP6022 SOIC, AO3400 alternatives, 6.8 Ω 2 W) were out of stock at that moment.
