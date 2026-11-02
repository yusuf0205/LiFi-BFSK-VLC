# Project Plan: Li-Fi Link Using BFSK

## 1. The idea, formulated
**Working title:** Design and Implementation of a Low-Cost, Ambient-Light-Robust Visible Light Communication Link Using BFSK Modulation

**Problem.** Radio spectrum is crowded and RF is unwanted in some places (hospitals, aircraft cabins, mines, underwater, RF-sensitive labs). Visible light is unlicensed, does not pass through walls (a natural security boundary) and every LED is already a potential transmitter. The usual student Li-Fi demo uses on-off keying (OOK), which breaks easily under sunlight, tube lights and 100 Hz mains flicker.

**Our approach.** Encode bits as two tones (f0 for 0, f1 for 1) on the LED current. Since the information lives in *frequency*, not brightness, the receiver can high-pass and band-pass away ambient DC light and 100 Hz flicker, and the LED's average brightness stays constant (no visible flicker). Demodulate two ways and compare: (a) the classic XR2211 PLL FSK demodulator IC, (b) a Goertzel-filter demodulator running on an ESP32.

**Objectives**
1. Build a working one-way VLC link: text, then files, over 0.5 to 3 m at 1 to 10 kbps.
2. Achieve BER below 1e-3 at 1 m under normal room lighting.
3. Compare PLL (XR2211) vs software Goertzel demodulation on BER, range, cost and complexity.
4. Characterise BER vs distance, angle, ambient light (dark, tube light, sunlight) and bit rate.
5. Add framing + CRC-16 (and Hamming(7,4) FEC) and measure its effect.

**Expected contribution (the "research gap" angle).** A reproducible, sub Rs 3,000 BFSK VLC prototype with a side-by-side, measured comparison of hardware PLL and MCU Goertzel demodulation under real Indian indoor lighting (CFL/LED tube flicker at 100 Hz), plus an adaptive tone-selection scheme. That is enough for a conference paper.

## 2. Novelty ideas (pick 1-2 on top of the core)
| # | Idea | Novelty | Feasibility | Demo impact |
|---|---|---|---|---|
| 1 | **Adaptive tone selection**: RX measures ambient spectrum, tells TX (via IR or BLE back-channel) which f0/f1 pair is cleanest | High | Medium | High |
| 2 | **PLL vs Goertzel head-to-head** with BER curves | Medium | High | Medium (paper-friendly) |
| 3 | **Bidirectional link**: visible downlink + IR uplink (true Li-Fi, not just VLC) | Medium | Medium | High |
| 4 | **Audio streaming** over light (play music via torch beam) | Low | High | Very high (crowd demo) |
| 5 | **Hamming(7,4)/CRC + ARQ** reliable file transfer | Medium | High | Medium |
| 6 | **Multi-FSK (4-FSK)** to double rate | Medium | Medium | Medium |
| 7 | **Li-Fi indoor positioning**: each ceiling LED sends its ID as an FSK tone pair, phone/receiver locates itself | High | Medium | High |
| 8 | **Smartphone receiver**: decode FSK from the phone's ambient light sensor or camera rolling shutter | High | Low-Medium | Very high |
| 9 | **Secure short-range data exchange** (light-confined key exchange for pairing IoT devices) | High | Medium | Medium |
| 10 | **Underwater or vehicle-to-vehicle** demo (tail-light to car) in a water tank / toy cars | Medium | Medium | Very high |
| 11 | **Solar-panel receiver**: use a small solar cell as both energy harvester and photodetector | High | Medium | High |

**Recommendation:** Core BFSK link + Idea 2 (comparison, makes the paper) + Idea 1 or 11 (the novelty) + Idea 4 for the demo day wow factor.

## 3. What you need to learn (in order)
1. **Digital comm basics**: ASK/FSK/PSK, coherent vs non-coherent detection, BER, Eb/N0. (NPTEL "Principles of Digital Communication", Lathi/Haykin chapters on FSK.)
2. **Optics for VLC**: LED electro-optical response and bandwidth, photodiode responsivity, Lambertian channel model, line-of-sight path loss. (Haas "What is LiFi"; Komine & Nakagawa 2004.)
3. **Analog front end**: transimpedance amplifier design (gain, Cf for stability, noise), active filters (Sallen-Key, MFB bandpass), comparators. (TI "Transimpedance Considerations" app notes; TI Filter Designer; Analog Filter Wizard.)
4. **PLL & FSK ICs**: XR2211 datasheet formulas, LM567 tone decoder.
5. **DSP**: sampling, Goertzel algorithm, windowing, bit-timing recovery.
6. **ESP32 firmware**: LEDC PWM, ADC continuous / I2S mode, timers and ISRs, FreeRTOS tasks (also builds your RTOS skill for job applications).
7. **Tools**: LTspice (simulate RX), KiCad (PCB), Python (numpy, matplotlib, pyserial) for simulation and logging.
8. **Writing**: IEEE paper format (Overleaf IEEE template), how to plot BER curves properly.

This also ticks Pratham's skill path: RTOS on ESP32 and a real fabricated KiCad PCB.

## 4. Schedule (fits your semester)
Conference target: IEEE CONECCT 2027 (Bengaluru, 29 to 31 Jul 2027) is the best timing fit; check its paper deadline (usually spring).

Calendar anchors: FA-Theory Nov 23 to Dec 3 2026; vacation from Dec 7; even sem from Jan 4 2027; GATE in Feb 2027; internship from mid-May 2027.

| Phase | Dates | Work | Deliverable |
|---|---|---|---|
| 0. Learn + read | Nov 1 to Nov 20 2026 (light, around exams) | Read 6 key papers, digital comm FSK refresh, run the Python simulation | Notes, sim plots |
| Exams | Nov 21 to Dec 6 2026 | Pause | |
| 0b. Order XR2211 (import) | This week, Nov 2026 | XR2211 is obsolete and not stocked in India: order from an overseas seller now, or plan two LM567s as fallback | Part on the way |
| 1. Order + breadboard TX | Dec 7 to Dec 20 2026 | Order BOM, LED driver, ESP32 LEDC tone TX, check tones on scope | TX working |
| 2. RX front end | Dec 21 2026 to Jan 3 2027 | Photodiode + TIA + filters on breadboard, LTspice matched to scope | Clean tone at RX |
| 3. Demodulation | Jan 4 to Jan 31 2027 | XR2211 path + ESP32 Goertzel path, first text over light | First end-to-end text |
| GATE prep | Feb 2027 | Minimal project work | |
| 4. Framing + reliability | Mar 1 to Mar 21 2027 | Preamble/sync, CRC-16, Hamming(7,4), PC tool | File transfer |
| 5. Experiments | Mar 22 to Apr 18 2027 | BER vs distance/angle/ambient/bit-rate, PLL vs Goertzel | Data + plots |
| 6. Novelty | Apr 19 to May 10 2027 | Adaptive tones or solar-cell RX, audio demo | Feature demo |
| Internship | mid-May to Jul 2027 | Paper draft in spare time | Draft paper |
| 7. PCB | Aug 2027 | KiCad TX and RX boards, fabricate (JLCPCB/PCBPower), assemble | Working PCBs |
| 8. Paper + review 1 | Sep to Oct 2027 | Submit to a conference, project review 1 | Paper submitted |
| 9. Polish + report | Nov 2027 to Mar 2028 | Enclosure, final report, demo video, GitHub | Final report, viva |

If your college's final project timeline is different, shift phases 7 to 9; phases 0 to 6 are the real build and should be done early so the final year is just polish and paper.

## 5. Further work / extensions after the core
- Raise the rate: faster photodiode (BPW34 -> SFH 213 / PIN with lower capacitance), dedicated LED driver, move to 4-FSK or OFDM.
- Full-duplex networking: multiple users (FDMA by tone pairs), a tiny Li-Fi access point.
- Integration with an IoT gateway (MQTT over light).
- Camera/smartphone receiver app.
- Underwater VLC with blue LEDs.
- Compare against IEEE 802.15.7 PHY I modes.

## 6. Report outline (final year report)
1. Introduction and motivation
2. Literature survey
3. Theory: VLC channel, BFSK, PLL and Goertzel demodulation
4. System design: TX, RX, calculations
5. Firmware and software
6. Simulation results
7. Hardware results and experiments
8. Comparison and discussion
9. Conclusion and future work
References, appendices (schematics, BOM, code)

## 7. Viva questions to prepare
- Why BFSK and not OOK? What is the trade-off in bandwidth?
- How does your RX reject 100 Hz flicker and sunlight?
- What limits your data rate (LED bandwidth, photodiode capacitance, TIA GBW, MCU sampling)?
- Explain Goertzel vs FFT. Why Goertzel here?
- XR2211 timing: how did you choose R0, C0, R1?
- Theoretical BER of non-coherent BFSK? How does your measured curve compare?
- Eye safety and flicker: is your LED within safe limits?
