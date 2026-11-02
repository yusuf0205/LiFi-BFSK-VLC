# Research Pack: Li-Fi / VLC Link Using BFSK Modulation

**Project:** LED transmitter switching between two tones (f0 for bit 0, f1 for bit 1) → photodiode + TIA → filtering → BFSK demodulation (XR2211 / LM567 PLL, or Goertzel on ESP32).
**Prepared for:** B.Tech ECE final-year project, NIT Puducherry. Compiled 31 Oct 2026 (IST).
**Rule used:** every URL below was either opened (fetched) or returned directly in a search result during this research. Items marked *(abstract/metadata only)* were checked at the publisher/DOI page but the full text was not read. Items marked *(cited, not opened)* were seen only as a DOI inside another paper's reference list.

---

## 1. Literature (27 sources)

★ = one of the **6 closest to a BFSK student design** (summary list at the end of this section).

### A. Standards

**1. IEEE Std 802.15.7-2018**, *IEEE Standard for Local and Metropolitan Area Networks, Part 15.7: Short-Range Optical Wireless Communications*, IEEE, 2019 (approved Dec 2018). DOI 10.1109/IEEESTD.2019.8697198
URL: https://standards.ieee.org/ieee/802.15.7/6820 · https://ieeexplore.ieee.org/document/8697198 (listed as Free Access on Xplore)
Summary: Defines PHY and MAC for short-range optical wireless (190 nm to 10,000 nm), including ambient-light noise, dimming and flicker requirements and optical camera communication. Original 2011 version: https://standards.ieee.org/ieee/802.15.7/5154/
Borrow: Frame structure ideas (preamble/sync header, length field, CRC), flicker and dimming vocabulary, and the PHY I (low-rate, outdoor-robust) mindset to justify a low-rate, noise-robust BFSK link. PHY I spans roughly 11.67 to 266.6 kb/s and PHY II 1.25 to 96 Mb/s (figures as quoted in the Photonics 2023 survey, https://doi.org/10.3390/photonics10090993).

**2. S. Rajagopal, R. D. Roberts, S.-K. Lim**, "IEEE 802.15.7 visible light communication: modulation schemes and dimming support," *IEEE Communications Magazine*, vol. 50, no. 3, pp. 72–82, Mar. 2012. DOI 10.1109/MCOM.2012.6163585
URL: https://ieeexplore.ieee.org/document/6163585/ · ETRI copy page: https://ksp.etri.re.kr/ksp/article/read?id=91 *(abstract/metadata only)*
Summary: The standard authors' own explanation of OOK, VPPM and CSK in 802.15.7, and how dimming and flicker-free operation are achieved.
Borrow: The "why not plain OOK" argument (flicker/dimming), and a ready-made table to compare against in your report.

**3. IEEE Std 802.11bb-2023**, *Wireless LAN MAC and PHY, Amendment 6: Light Communications*, IEEE, Nov 2023. DOI 10.1109/IEEESTD.2024.10315104
URL: https://standards.ieee.org/ieee/802.11bb/10823 · https://ieeexplore.ieee.org/document/10315104
Summary: Brings Li-Fi into the Wi-Fi family, operating in the 800–1000 nm band with 10 Mb/s to 9.6 Gb/s at the MAC SAP. IEEE SA now lists it as "Superseded" (folded into the 802.11 base).
Borrow: One paragraph in your intro showing where commercial Li-Fi is heading (infrared, Wi-Fi-compatible), which contrasts nicely with a low-rate visible-light BFSK link.

### B. Key surveys and overviews

**4. H. Haas, L. Yin, Y. Wang, C. Chen**, "What is LiFi?," *Journal of Lightwave Technology*, vol. 34, no. 6, pp. 1533–1544, Mar. 2016. DOI 10.1109/JLT.2015.2510021
URL: https://ieeexplore.ieee.org/document/7360112 · open repository page: https://www.research.ed.ac.uk/en/publications/what-is-lifi-2/
Summary: Separates VLC (point-to-point link) from LiFi (fully networked, bidirectional, multiuser "attocells"), and covers components through to hybrid LiFi/WiFi networks.
Borrow: Correct terminology. Your project is technically a **VLC link**, so call it "VLC/Li-Fi link" in the title and explain the difference in one paragraph.

**5. P. H. Pathak, X. Feng, P. Hu, P. Mohapatra**, "Visible Light Communication, Networking, and Sensing: A Survey, Potential and Challenges," *IEEE Communications Surveys & Tutorials*, vol. 17, no. 4, pp. 2047–2077, 2015. DOI 10.1109/COMST.2015.2476474
URL: https://ieeexplore.ieee.org/document/7239528 · free author PDF: http://phpathak.com/files/vlc-comsoccst.pdf
Summary: Covers transmitter/receiver components, channel, modulation, MAC, programmable platforms and VLC sensing (localisation, gesture recognition).
Borrow: The section on system design and programmable platforms, which is a good template for your "hardware architecture" chapter.

**6. D. Karunatilaka, F. Zafar, V. Kalavally, R. Parthiban**, "LED Based Indoor Visible Light Communications: State of the Art," *IEEE Communications Surveys & Tutorials*, vol. 17, no. 3, pp. 1649–1678, 2015. DOI 10.1109/COMST.2015.2417576
URL: https://ieeexplore.ieee.org/document/7072557 · https://research.monash.edu/en/publications/led-based-indoor-visible-light-communications-state-of-the-art
Summary: Indoor VLC from 1979 to 2014: VLC compared with IR and RF, modulation and dimming, filtering, and indoor challenges.
Borrow: LED bandwidth limits (phosphor white LEDs are slow) and the dimming/modulation discussion for your literature-review chapter.

**7. L. E. M. Matheus, A. B. Vieira, L. F. M. Vieira, M. A. M. Vieira, O. Gnawali**, "Visible Light Communication: Concepts, Applications and Challenges," *IEEE Communications Surveys & Tutorials*, vol. 21, no. 4, pp. 3204–3237, 2019. DOI 10.1109/COMST.2019.2913348
URL: https://ieeexplore.ieee.org/document/8698841 · free author PDF: https://www2.cs.uh.edu/~gnawali/papers/vlcsurvey-ieee19.pdf
Summary: A more recent survey covering hardware, PHY/MAC, NOMA, applications and open challenges. It explicitly flags ambient light (sunlight, fluorescent, other LEDs) as a major deployment challenge.
Borrow: The "open challenges" section supplies a citation for your problem statement on ambient-light interference.

**8. J. M. Kahn, J. R. Barry**, "Wireless infrared communications," *Proceedings of the IEEE*, vol. 85, no. 2, pp. 265–298, 1997. DOI 10.1109/5.554222 *(cited, not opened; DOI taken from the reference list of source 12)*
URL: https://doi.org/10.1109/5.554222
Summary: The classic IM/DD optical-wireless channel paper (LOS/diffuse channel, shot noise from ambient light, modulation power efficiency). Most VLC channel models still build on it.
Borrow: The Lambertian LOS channel gain equation for predicting received power against distance in your link-budget section.

### C. FSK / BFSK in VLC (core of your project)

**9. ★ C. Beguni, A. Done, A.-M. Căilean, S.-A. Avătămăniței, E. Zadobrischi**, "Experimental Demonstration of a Visible Light Communications System Based on Binary Frequency-Shift Keying Modulation: A New Step toward Improved Noise Resilience," *Sensors*, vol. 23, no. 11, 5001, 2023. DOI 10.3390/s23115001 (open access, **full text read**)
URL: https://www.mdpi.com/1424-8220/23/11/5001
Summary: A hardware BFSK VLC prototype (0.96/1.04 MHz tones, 10 kb/s NRZ, red XP-E2 LED, PIN-photodiode TIA, KA3361 FSK demodulator, Schmitt trigger, ARM M7). It was compared directly against OOK-Manchester on the same platform. BFSK tolerated about 25% more direct optical noise (3500 vs 2800 µW/cm²) and about 20% more indirect noise, with BER < 10⁻⁶. The range reached 26 m in lab conditions.
Borrow: **This is your reference design.** Borrow the experimental method (calibrate OOK and BFSK to the same irradiance and range, then ramp a halogen noise source until BER > 10⁻⁶), the block diagram, the Carson's-rule bandwidth reasoning, and the honest limitations (data rate, jitter, calibration difficulty). The paper also notes that AC incandescent lamps produce 100 Hz interference with harmonics up to about 2 kHz, and fluorescent lamps produce interference up to about 40 kHz (low amplitude to 1 MHz). That spectrum is what you choose your tones to avoid.

**10. ★ A. W. Azim, A. Rullier, Y. Le Guennec, L. Ros, G. Maury**, "Energy Efficient M-ary Frequency-Shift Keying-Based Modulation Techniques for Visible Light Communication," *IEEE Transactions on Cognitive Communications and Networking*, vol. 5, no. 4, pp. 1244–1256, Dec. 2019. DOI 10.1109/TCCN.2019.2940260 *(abstract/metadata only)*
URL: https://ieeexplore.ieee.org/document/8830382
Summary: Proposes DC-FSK (DC offset) and U-FSK (unipolar, sign-flipped halves) to make FSK compatible with intensity modulation, with ML and suboptimal receivers. In simulation these schemes are more energy-efficient than M-PAM for low-rate IoT.
Borrow: The theory section. Your square-wave or DC-biased-sine LED drive is "DC-FSK" in their terms, and their BER expressions give you a theoretical curve to plot next to measured BER.

**11. ★ G. M. Mougoue Yamga, A. R. Ndjiongue, K. Ouahada**, "Low complexity clipped Frequency Shift Keying (FSK) for Visible Light Communications," *2018 IEEE 7th Int. Conf. on Adaptive Science & Technology (ICAST)*, Accra, Aug. 2018. DOI 10.1109/ICASTECH.2018.8506727 *(abstract/metadata only)*
URL: https://ieeexplore.ieee.org/document/8506727
Summary: Asymmetric FSK (AFSK) for non-negative VLC signals. It targets low cost and low complexity, mitigates flicker and dimming for square and rectified-sine carriers, and in simulation outperforms OOK for selected sizes.
Borrow: Justification that driving the LED with **square-wave tones** (what an ESP32 LEDC pin naturally produces) is a legitimate FSK variant, plus flicker arguments.

**12. ★ M. Kang, J. Wu, J. Li, Y. Zhou, Z. Zhao, Y. Zhou**, "Prolonging The Range of Low-power Visible Light Communication Systems with M-FSK," *2024 IEEE 30th Int. Conf. on Parallel and Distributed Systems (ICPADS)*, pp. 536–543, 2024. DOI 10.1109/ICPADS63350.2024.00076 *(abstract/metadata only)*
URL: https://www.computer.org/csdl/proceedings-article/icpads/2024/159600a536/22f0z3Q2Vva
Summary: Sine-intensity M-FSK on 1 W/3 W LEDs with a gradient-threshold demodulator. Reaches 5.8 m (1 W) and 10 m (3 W), which the authors describe as about 2.5× the range of prior low-power work, and argues FSK resists ambient light better than intensity (OOK) modulation.
Borrow: A recent (2024) citation proving FSK-VLC is still active research, plus a low-power-LED range benchmark to compare against.

**13. ★ N. Rajagopal, P. Lazik, A. Rowe**, "Visual Light Landmarks for Mobile Devices," *Proc. ACM/IEEE IPSN 2014*, Carnegie Mellon University.
URL (author PDF): https://users.ece.cmu.edu/~agr/resources/publications/ipsn2014-vlc.pdf *(abstract read)*
Summary: LED lights broadcast FSK tones that phone cameras or light sensors detect. Operates above 2 kHz to avoid visible flicker, detects frequencies up to 8 kHz with 0.2 kHz channel separation, and uses this for indoor landmarks/positioning.
Borrow: Tone-planning numbers (flicker floor about 2 kHz, channel spacing) and a ready **positioning extension**: each lamp sends a unique f0/f1 pair or ID.

**14. C.-W. Chow, R.-J. Shiu, Y.-C. Liu, X.-L. Liao, K.-H. Lin, Y.-C. Wang, Y.-Y. Chen**, "Using advertisement light-panel and CMOS image sensor with frequency-shift-keying for visible light communication," *Optics Express*, vol. 26, no. 10, pp. 12530–12535, 2018. DOI 10.1364/OE.26.012530 *(abstract only)*
URL: https://pubmed.ncbi.nlm.nih.gov/29801291
Summary: An FSK VLC link from an advertising light panel to a smartphone camera using the rolling-shutter effect, with a success rate above 96% up to 200 cm.
Borrow: An optional demo idea (phone camera as a second receiver) and evidence that FSK suits low-contrast optical channels.

**15. "A Dimmable Offline LED Driver With OOK-M-FSK Modulation for VLC Applications,"** *IEEE Transactions on Industrial Electronics*, 2018. DOI 10.1109/TIE.2018.2868022 *(abstract only; authors not captured)*
URL: https://doi.org/10.1109/TIE.2018.2868022
Summary: Embeds ON-OFF M-FSK into a single-stage PFC LED driver so more than one bit is sent per switching period without disturbing dimming.
Borrow: The argument that FSK can coexist with real mains-powered LED drivers, useful for a "future work: integrate into a room luminaire" section.

**16. "Comparative Study of Frequency-based Modulations for Visible Light Communication,"** *IEEE WCNC 2024*. DOI 10.1109/WCNC57260.2024.10571121 *(abstract only; authors not captured)*
URL: https://doi.org/10.1109/wcnc57260.2024.10571121
Summary: Compares FSK with frequency-shift chirp modulation (FSCM, LoRa-like) in free-space and underwater VLC. FSCM beats FSK in band-limited, frequency-selective channels.
Borrow: A good "beyond BFSK" future-work item (chirps), and an honest limitation to acknowledge for FSK.

### D. Other modulations (for the comparison table)

**17. "Designing A Dimmable OPPM-Based VLC System Under Channel Constraints,"** arXiv:1602.08765, 2016. *(abstract/intro read; authors not captured)*
URL: https://arxiv.org/pdf/1602.08765
Summary: Overlapping PPM designed for dimming control and data rate under LED/channel bandwidth constraints. Cites the IEEE 802.15.7 flicker/dimming requirements.
Borrow: PPM pros and cons for the comparison table (power efficiency, dimming).

**18. S. D. Dissanayake, J. Armstrong**, "Comparison of ACO-OFDM, DCO-OFDM and ADO-OFDM in IM/DD Systems," *Journal of Lightwave Technology*, vol. 31, no. 7, pp. 1063–1072, 2013. DOI 10.1109/JLT.2013.2241731
URL: https://opg.optica.org/jlt/abstract.cfm?uri=jlt-31-7-1063 · PDF mirror: https://optiwave.com/wp-content/uploads/2024/02/Comparison-of-ACO-OFDM-DCO-OFDM-and-ADO-OFDM-in-IM-DD-Systems.pdf
Summary: The standard reference on making OFDM real and non-negative for LEDs. DCO-OFDM wastes optical power on DC bias, while ACO-OFDM wastes half the subcarriers.
Borrow: One paragraph explaining why OFDM is the high-rate choice but out of scope for an MCU-based student link.

**19. E. Monteiro, S. Hranilovic**, "Design and Implementation of Color-Shift Keying for Visible Light Communications," *Journal of Lightwave Technology*, vol. 32, no. 10, pp. 2053–2060, 2014. DOI 10.1109/JLT.2014.2314358
URL: https://opg.optica.org/jlt/abstract.cfm?uri=jlt-32-10-2053 · thesis (open): https://macsphere.mcmaster.ca/handle/11375/13484
Summary: A CSK constellation design and hardware implementation with RGB LEDs. Total intensity stays constant, so CSK is inherently flicker-free.
Borrow: The CSK row of your table, and the idea that "the colour equivalent of FSK" exists.

### E. Low-cost Arduino/MCU VLC prototypes

**20. ★ A. L. Rodrigues Gonçalves, D. Alves de Lima, Á. Maia**, "Visible Light Communication Applied to Low Cost Embedded Systems," *IEEE Latin America Transactions*, vol. 22, no. 1, pp. 15–21, 2024 (published online 21 Dec 2023). **(full page read)**
URL: https://latamt.ieeer9.org/index.php/transactions/article/view/8232 · code: https://github.com/analuisarg/SistemaVLC
Summary: A didactic two-Arduino-UNO VLC link with off-the-shelf parts, OOK + Manchester and a checksum, reaching 500 b/s at 40 cm. Hardware and code are published.
Borrow: **Your OOK baseline.** Rebuild something like it on the same LED/photodiode so the BFSK-vs-OOK comparison is fair. Their low numbers (500 b/s, 40 cm) are an easy benchmark to beat and cite.

**21. G. Dmitriev, K. Chumak, A. Bobrovsky, R. Andreev, O. Vorobyov**, "Research of characteristics of Visible Light Communications system implemented on Arduino Uno platform," *2019 IEEE BlackSeaCom*, Sochi, June 2019. DOI 10.1109/BlackSeaCom.2019.8812781 *(abstract only)*
URL: https://ieeexplore.ieee.org/document/8812781
Summary: Measures the boundary frequencies and link quality of Arduino-Uno optical TX/RX modules, and proposes circuit fixes to raise the optical clock and reduce ambient-light effects.
Borrow: The test methodology (sweep the frequency until the link fails) and the ambient-light circuit ideas.

**22. S. Schmid, G. Corbellini, S. Mangold, T. R. Gross**, "An LED-to-LED Visible Light Communication System with Software-Based Synchronization," ETH Zurich / Disney Research Zurich (presentation slides, 2012).
URL: https://www.bu.edu/smartlighting/files/2012/10/Schmid_.pdf
Summary: Low-cost MCU LED-to-LED links (an LED used as both transmitter and receiver) for networked toys, with OOK and software synchronization, built around no-flicker and constant-brightness requirements.
Borrow: Software clock-recovery ideas, and the "LED as receiver" trick as a stretch goal.

**23. Q. Wang, D. Giustiniano, D. Puccinelli**, "An open source research platform for embedded visible light networking," *IEEE Wireless Communications*, vol. 22, no. 2, pp. 94–100, Apr. 2015. DOI 10.1109/MWC.2015.7096291
URL: https://arxiv.org/abs/1410.0328 · project: http://www.openvlc.org/ (code: https://github.com/openvlc/OpenVLC/)
Summary: OpenVLC is an open-source, software-defined VLC platform on a BeagleBone Black. Recent versions report about 400 kb/s at the transport layer and almost 20 m range (per openvlc.org).
Borrow: Software-defined PHY/MAC structure and an open hardware front-end to compare your schematic with. Also a "related platforms" citation.

### F. Ambient-light rejection and receiver front-ends

**24. ★ F.-L. Chang, W.-W. Hu, D.-H. Lee, C.-T. Yu**, "Design and implementation of anti low-frequency noise in visible light communications," *2017 IEEE Int. Conf. on Applied System Innovation (ICASI)*, Sapporo, May 2017. DOI 10.1109/ICASI.2017.7988219 *(abstract only)*
URL: https://ieeexplore.ieee.org/document/7988219
Summary: Receiver chain of TIA → 4th-order Sallen-Key high-pass filter → Schmitt trigger. It removes DC from sun/ambient light and suppresses low-frequency flicker from fluorescent lamps.
Borrow: **Your analog front-end almost exactly.** Replace their HPF with a band-pass centred between f0 and f1 and you have a BFSK front-end.

**25. "Analog filters design in VLC analog front-end receiver for reducing indoor ambient light noise,"** *2016 IEEE Asia Pacific Conf. on Circuits and Systems (APCCAS)*. DOI 10.1109/APCCAS.2016.7804058 *(abstract only; authors not captured because the publisher page failed to load)*
URL: https://doi.org/10.1109/apccas.2016.7804058
Summary: DC-offset removal (a 10 Hz HPF in automatic mode, or a pot plus differential amplifier in manual mode) plus a 100 Hz band-stop filter against lamp flicker, tested in simulation and in real time.
Borrow: A 100 Hz notch (India mains is 50 Hz, so lamp flicker sits at 100 Hz) and a DC-removal stage before your tone filters.

**26. "Ambient Light Rejection Using a Novel Average Voltage Tracking in Visible Light Communication System,"** *Applied Sciences*, vol. 7, no. 7, 670, 2017. DOI 10.3390/app7070670 *(abstract only; authors not captured)*
URL: https://doi.org/10.3390/app7070670
Summary: An average-voltage-tracking threshold circuit that is insensitive to sunlight and indoor fluorescent light, aimed at low-SNR VLC receivers.
Borrow: An adaptive threshold for your post-demodulator slicer (or the software equivalent on ESP32).

Additional front-end references seen (optional): S.-A. Avătămăniței et al., logarithmic transimpedance VLC receiver, 50 m link in direct sun, *Sensors* 2020, 20, 909 (https://doi.org/10.3390/s20030909, *cited, not opened*); M. S. Islim et al., "The Impact of Solar Irradiance on Visible Light Communications," *JLT* 36, 2018 (https://doi.org/10.1109/JLT.2018.2813396, *cited, not opened*); W. Uemura, T. Hamano, "Noise Mitigation Methods for Digital Visible Light Communication," arXiv:2602.18187, 2026 (https://arxiv.org/abs/2602.18187v1: subtracts periodic AC-lamp noise and adds a second "noise-reference" photodiode, an ANC-style idea that is cheap to try).

### G. VLC positioning

**27. Y. Zhuang, L. Hua, L. Qi, J. Yang, P. Cao, Y. Cao, Y. Wu, J. Thompson, H. Haas**, "A Survey of Positioning Systems Using Visible LED Lights," *IEEE Communications Surveys & Tutorials*, vol. 20, no. 3, pp. 1963–1988, 2018. DOI 10.1109/COMST.2018.2806558
URL: https://doi.org/10.1109/COMST.2018.2806558 · accepted manuscript (open): https://uhra.herts.ac.uk/id/eprint/6968/1/Accepted_Manuscript.pdf
Summary: A comprehensive VLP survey covering proximity, RSS, TDOA, AOA, image-sensor approaches and hybrids with inertial/RF sensors.
Borrow: If you add positioning, FSK-ID proximity or RSS trilateration with 3–4 LEDs on different tone pairs (FDM) is the natural extension.

Also: **T.-H. Do, M. Yoo**, "An in-Depth Survey of Visible Light Communication Based Positioning Systems," *Sensors*, vol. 16, no. 5, 678, 2016. DOI 10.3390/s16050678 (open access). URL: https://www.mdpi.com/1424-8220/16/5/678. It is more tutorial-style and covers >100 papers, including FDM-based LED identification (good for a multi-tone design).

### ★ The 6 closest to a BFSK student design

| # | Source | Why it's close |
|---|---|---|
| 9 | Beguni et al., *Sensors* 2023 | Actual BFSK VLC hardware, compared against OOK. Your template. |
| 24 | Chang et al., ICASI 2017 | TIA → active filter → Schmitt receiver, exactly your analog chain. |
| 20 | Rodrigues Gonçalves et al., IEEE LatAm Trans 2024 | Low-cost Arduino OOK-Manchester baseline with open code. |
| 13 | Rajagopal, Lazik, Rowe, IPSN 2014 | Low-kHz FSK tones from LEDs, tone-spacing and flicker numbers, positioning extension. |
| 11 | Mougoue Yamga et al., ICAST 2018 | Low-complexity (square-wave) FSK theory for non-negative LED signals. |
| 10 | Azim et al., IEEE TCCN 2019 | Rigorous DC-FSK/U-FSK theory and BER expressions to compare against. |

(Runner-up: #12 Kang et al. ICPADS 2024, for a recent low-power-LED M-FSK range benchmark.)

---

## 2. Modulation comparison for VLC (IM/DD with LEDs)

Ratings are qualitative and relative, synthesised from sources 2, 6, 9, 10, 17, 18, 19 and the Photonics 2023 survey (https://doi.org/10.3390/photonics10090993). "Student MCU build" means an Arduino/ESP32-class system without an FPGA or SDR.

| Scheme | Data rate (spectral efficiency) | Noise / ambient-light immunity | Flicker / dimming | Complexity | Cost | Typical student-build reality |
|---|---|---|---|---|---|---|
| **OOK (NRZ)** | Medium (1 bit/symbol). Rate limited by LED bandwidth. | **Poor.** Energy sits near DC to low kHz, overlapping sunlight DC and 100 Hz to kHz lamp flicker. Needs an adaptive threshold. | Long runs of 0s/1s cause visible flicker. Dimming only via compensation symbols. | Lowest | Lowest | kb/s on Arduino (e.g. 500 b/s at 40 cm in #20) |
| **Manchester OOK** | ½ of NRZ (2 chips/bit) | Better than NRZ: no DC, so a high-pass can remove ambient DC. Still overlaps low-frequency lamp noise at low rates. | Good: 50% duty, flicker-free above ~200 Hz chip rate. Used in 802.15.7 PHY I. | Low (clock recovery needed) | Lowest | The fair baseline to compare BFSK against (#9 did exactly this). |
| **BFSK (DC-FSK / square-tone FSK)** | **Low** (1 bit/symbol, but each bit needs several carrier cycles, so the bit rate is well below the tone frequency) | **Good.** Energy sits at two chosen tones, so you can place them above lamp interference and use narrow band-pass filters. ~20–25% better noise tolerance than OOK-Manchester measured in #9. | **Excellent.** Constant 50% average intensity whatever the data, so no data-dependent flicker if tones are > a few kHz. | Medium: two filters + PLL/tone decoder, or DSP (Goertzel) | Low (XR2211 or ESP32 only) | Realistic: 1–10 kb/s over a few metres with ESP32 or XR2211 |
| **PPM / VPPM** | Low–medium (log₂L bits per L slots). Bandwidth-hungry. | Good power efficiency (high peak, low average), but needs tight slot timing and is sensitive to multipath at high rates. | VPPM in 802.15.7 gives dimming via pulse width. | Medium (slot sync) | Low | Feasible on MCU timers, but synchronization is the hard part. |
| **OFDM (DCO / ACO-OFDM)** | **Highest** (QAM on many subcarriers; Gb/s demos) | Good against frequency-selective channels, and can notch interfered subcarriers. DCO wastes power on bias. | Fine (high-frequency, DC-biased). | **High**: IFFT/FFT, DAC/ADC at MHz, linear LED driver, PAPR issues | High (FPGA/SDR, fast DAC/ADC) | Out of scope for MCU. Simulation-only for most students. |
| **CSK** | Medium–high (log₂M bits/symbol with RGB LEDs) | Moderate. Colour crosstalk and ambient colour shifts need calibration. | **Excellent.** Total intensity constant, so inherently flicker-free. | High (RGB driver, 3-channel colour receiver, calibration) | Medium | Possible with RGB LED + colour sensor at low rates, but calibration-heavy. |

### Honest pros and limits of BFSK for this project

**Pros**
- **Ambient-light robustness by design.** Sunlight is DC, and incandescent lamps (on India's 50 Hz mains) produce 100 Hz with harmonics to ~2 kHz. Fluorescent/CFL interference extends to ~40 kHz with low-level components to ~1 MHz (per #9). Two tones placed in a clean band, behind a band-pass filter, reject most of this. A high-pass alone does not do that for OOK at low bit rates.
- **Flicker-free regardless of data.** The LED is always toggling at f0 or f1 with 50% duty, so average brightness never changes with the bit pattern.
- **Non-coherent, asynchronous detection** (PLL/tone decoder or Goertzel energy comparison). No carrier phase recovery is needed, which suits free-running MCUs (#9 makes this argument against PSK).
- **Cheap, well-documented demodulators** (XR2211 up to 300 kHz, LM567 up to 500 kHz centre frequency), plus an all-digital path (Goertzel) that needs no extra ICs.
- **Natural multi-user/positioning extension:** give each LED its own tone pair (FDM), as in #13.

**Limits**
- **Low data rate / poor spectral efficiency.** You need several carrier cycles per bit, and the LED (especially a phosphor white LED) and photodiode/TIA bandwidth caps the tone frequency. #9 reached 10 kb/s with ~1 MHz tones and a dedicated demod IC. Expect 1–10 kb/s on ESP32.
- **More hardware/tuning than OOK.** Two filters or a PLL, careful component tolerances (XR2211/LM567 centre frequency drifts with R/C), and calibration. #9 explicitly reports adjustment difficulty and jitter.
- **Wasted optical power:** the DC bias / 50% duty carries no information (the same DC-FSK issue analysed in #10).
- **PLL lock time and capture range** limit how fast you can switch tones (bit rate vs loop filter). With Goertzel, the block length N sets both frequency resolution (fs/N) and minimum bit duration.
- **Band-limited channels favour other schemes** (#16 shows chirp modulation beating FSK there). BFSK is the "robust and simple" choice, not the "fast" one.

---

## 3. Research gap a student project can address

What the literature already has:
- High-rate VLC (OFDM, CSK) is mostly simulation or lab-grade hardware (FPGA/SDR) (#18, #19; noted in #9).
- The one solid BFSK *hardware* comparison (#9) uses ~1 MHz tones, a dedicated analog FSK demod IC (KA3361), a 600 MHz ARM board, a high-power red LED with an optical filter, and halogen noise in a European lab.
- Low-cost Arduino VLC papers (#20, #21) are almost all OOK/Manchester with no systematic ambient-light study.
- FSK theory papers (#10, #11) are simulation-only.

**Gap (pick one as the headline, the rest as sub-objectives):**

1. **Analog PLL vs digital Goertzel BFSK demodulation, same link, same noise.** No source found compares an XR2211/LM567 hardware demod head-to-head with a Goertzel detector on a low-cost MCU (ESP32) for VLC, measuring BER vs distance and vs ambient illuminance (lux). This is cheap, novel enough for a conference paper, and fits your skills.
2. **BFSK vs Manchester-OOK on identical low-cost hardware under *real Indian indoor lighting*:** 50 Hz mains (100 Hz flicker), CFL/LED-tube drivers, and tropical daylight through windows. Record the interference spectrum with the ESP32 ADC (or a sound card / oscilloscope FFT) and report BER vs lux for both schemes. #9 did this with halogen only.
3. **Interference-aware (adaptive) tone selection:** the receiver measures the noise spectrum (a Goertzel bank at candidate frequencies) during idle time and the link hops to the cleanest f0/f1 pair. This is a simple "cognitive VLC" idea that #10's journal (cognitive comms) hints at, with no low-cost hardware demo found.
4. **White phosphor LED + DC-FSK dimming:** show that BFSK keeps illumination constant while dimming (vary the DC bias or duty) and measure the BER cost. This is relevant to real room lighting, whereas #9 used a red LED.
5. **Stretch goal: FSK-ID beacons for indoor positioning** (#13, #27): 3 LEDs on 3 tone pairs, with RSS-based position estimation on the ESP32.

**Suggested title:** "Low-Cost ESP32-Based BFSK Visible Light Communication Link with Goertzel Demodulation: Experimental Comparison with PLL Demodulation and OOK Under Indoor Ambient Light."

**Suggested measurable outcomes:** BER (target < 10⁻⁴ at the chosen rate) vs distance (0.5–5 m), BER vs ambient lux (dark, room light, window daylight), max bit rate for each demodulator, power consumption, and BOM cost (in ₹).

**Design starting points (to verify on the bench):**
- Keep tones well above the ~2 kHz flicker/harmonic zone. Either stay below the main CFL band (e.g. ~5–20 kHz, easy for ESP32 ADC sampling) or go above it (≥ 50 kHz, needs a faster TIA and the ESP32 ADC continuous/I2S mode near its limit, or the XR2211, max 300 kHz).
- Space f0 and f1 at ≥ the bit rate for non-coherent orthogonality (#9 uses Rb = 1/Ts spacing).
- With Goertzel, choose fs and block length N so that f0 and f1 land on bin centres (k = N·f/fs) and N/fs ≤ bit time.
- The exact ESP32 ADC maximum sample rate depends on the chip variant and mode, so confirm it in the Espressif ADC continuous-mode docs (link in §4) before fixing tone frequencies.

---

## 4. Tutorials and learning resources (15 verified links)

**Receiver analog front-end (photodiode + TIA)**
1. TI, *Transimpedance Amplifier Circuit* (Analog Engineer's Circuit SBOA268B, P. Semig): step-by-step Rf/Cf selection and a bandwidth formula. https://www.ti.com/lit/an/sboa268b/sboa268b.pdf
2. TI, *1 MHz, Single-Supply, Photodiode Amplifier Reference Design* (TIDU535): a single 5 V supply TIA with bias to avoid rail saturation, matching your hardware. https://www.ti.com/lit/ug/tidu535/tidu535.pdf
3. TI, *Transimpedance Amplifiers (TIA): Choosing the Best Amplifier for the Job* (SNOA942A): noise vs bandwidth trade-offs and op-amp selection. https://www.ti.com/jp/lit/an/snoa942a/snoa942a.pdf
4. Analog Devices, *Stabilize Your Transimpedance Amplifier*: how to pick the feedback capacitor for phase margin (prevents a ringing/oscillating TIA). https://www.analog.com/en/resources/technical-articles/stabilize-transimpedance-amplifier-circuit-design.html
5. Analog Devices, *Optimizing Precision Photodiode Sensor Circuit Design* (L. Orozco): photovoltaic vs photoconductive mode and noise analysis. https://www.analog.com/en/resources/technical-articles/optimizing-precision-photodiode-sensor-circuit-design.html

**Analog BFSK demodulators**
6. MaxLinear/Exar **XR-2211A FSK Demodulator/Tone Decoder datasheet**: PLL FSK demod, 0.01 Hz–300 kHz, 4.5–20 V, with design equations for R0/C0 (centre frequency), R1 (tracking range), C1 (loop filter) and a carrier-detect connection. https://www.maxlinear.com/ds/xr2211av104.pdf
7. TI **LM567x Tone Decoder datasheet** (Rev. F): f0 ≈ 1/(1.1·R1·C1), up to 500 kHz, bandwidth 0–14%. Use two LM567s (one per tone) as a simple BFSK detector. https://www.ti.com/lit/ds/symlink/lm567c.pdf

**Digital demodulation: Goertzel**
8. K. Banks, "The Goertzel Algorithm," *Embedded.com*: the classic embedded-programmer explanation (block size N, sampling-rate choice, the optimized Goertzel). https://www.embedded.com/the-goertzel-algorithm/
9. DSP Workshop, "Goertzel on Hardware": C struct and per-sample update code, real-only power, no buffer needed. Drops straight into ESP32 firmware. https://dsp-workshop.nl/topics/goertzel/embedded.html
10. TI Application Report SPRA066, *Modified Goertzel Algorithm in DTMF Detection*: a formal derivation plus a detection-logic example (tone presence thresholds). https://www.ti.com/lit/an/spra066/spra066.pdf

**ESP32 peripherals**
11. Espressif ESP-IDF, **LED Control (LEDC)**: generate the f0/f1 square-wave tones on a GPIO and change frequency per bit. https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/ledc.html (Arduino-core version: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html)
12. Espressif ESP-IDF, **ADC Continuous Mode Driver**: DMA-based high-rate sampling of the TIA output for Goertzel. https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/adc/adc_continuous.html (Related: I2S driver page, which notes the original ESP32 can route I2S0 to the internal ADC/DAC: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/i2s.html)

**Courses**
13. NPTEL, **Optical Wireless Communications for Beyond 5G Networks and IoT** (Prof. Anand Srivastava, IIIT Delhi, 12 weeks): LEDs, photodetectors, SNR, indoor channel models and modulation. Prerequisite: Digital Communication. https://onlinecourses.nptel.ac.in/noc23_ee61/preview · lecture list: http://www.digimat.in/nptel/courses/video/108106190/108106190.html
14. NPTEL, **Principles of Digital Communication** (Prof. Abhishek Dixit, IIT Delhi): FSK/non-coherent detection and BER theory for your analysis chapter. https://nptel.ac.in/courses/108102120

**Videos and builds**
15. Harald Haas, **"Wireless data from every light bulb"** (TEDGlobal 2011), the talk that coined "Li-Fi" (good intro for your viva). https://www.ted.com/talks/harald_haas_wireless_data_from_every_light_bulb · follow-up "Forget Wi-Fi. Meet the new Li-Fi Internet" (2015): https://www.ted.com/talks/harald_haas_forget_wi_fi_meet_the_new_li_fi_internet · YouTube "LiFi: What is it?": https://www.youtube.com/watch?v=FbDohcbuhu0

Build write-ups (OOK-style, useful for mechanics and baselines):
- Instructables, *Visible Light Communication System* (Teensy 4.1 + Arduino, Fresnel lens for range): https://www.instructables.com/Visible-Light-Communication-System
- Instructables, *Li-Fi Audio Transmission Through Light* (analog intensity modulation; an easy first demo): https://www.instructables.com/LiFi-Experiment-Audio-Transmission-Through-Light
- Hackaday, *Hackaday Explains: Li-Fi & Visible Light Communications* (2015): https://hackaday.com/2015/12/11/hackaday-explains-li-fi-visible-light-communications/
- Hackaday.io, *Power LED LiFi Communication for IoT Smarthomes* (custom TI LM3409 fast-switching power-LED driver, clean switching to ~120 kHz, which shows how to drive a bright LED fast): https://hackaday.io/project/26181-power-led-lifi-communication-for-iot-smarthomes

---

## 5. Commercial Li-Fi products and companies

| Company | Product / link | One line |
|---|---|---|
| **pureLiFi** (UK; co-founded by Prof. Harald Haas) | https://www.purelifi.com/our-solutions/ · Kitefin XE: https://www.purelifi.com/product_category/lifi-wireless-internet/ | Kitefin XE is a room-filling LiFi access point (>80 m²) with USB clients for Android/Windows/Linux, aligned to IEEE 802.11bb. |
| **Signify (Philips) – Trulifi** (Netherlands) | https://www.signify.com/global/innovation/trulifi · India page: https://www.signify.com/en-in/innovation/trulifi · datasheets: https://www.signify.com/global/innovation/trulifi/downloads | Trulifi 6002 (meeting rooms, ~220/160 Mb/s down/up, roaming), 6013/6014 point-to-point (industrial), 6004 (first LiFi system with a FIPS 140-3 validated crypto engine, June 2025: https://www.signify.com/global/our-company/news/press-releases/2025/20250611-signifys-trulifi-light-based-network-meets-highest-encryption-standards). Note: the Trulifi systems listed are infrared LiFi. |
| **Oledcomm** (France; started as a university lab in 2005) | LiFiMAX: https://www.oledcomm.net/lifi-max · product range: https://www.oledcomm.org/products/ | LiFiMAX access points/antennas (~150 Mb/s), USB receivers, a LiFi tablet, a point-to-point unit (up to 5 Gb/s at 5 m per their page), and the SOLERIS defence range. |
| **Velmenni** (India-founded, New Delhi, 2012/2014; now also Estonia/US) | https://www.velmenni.com/ · About: https://www.velmenni.com/about-lifi · Dongle/APs: https://www.velmenni.com/lifi-dongle-access-points | Describes itself as the first Indian light-communication company. Early "Jugnu" Li-Fi smart bulb; today mostly FSO/Li-Fi wireless backhaul (raised ₹30 crore pre-Series A in Mar 2026, per BusinessLine: https://www.thehindubusinessline.com/markets/velmenni-raises-30-crore-to-expand-light-based-wireless-connectivity/article70751093.ece). Good Indian industry contact for internships. |
| **Fraunhofer IPMS** (Germany, research institute with products) | https://www.ipms.fraunhofer.de/en/Components-and-Systems/Components-and-Systems-Data-Communication/Li-Fi-Data-Communication.html | Li-Fi HotSpot and GigaDock modules for industrial low-latency links, plus Power-over-Light (data + power up to 10 Mb/s, 1 m). |
| **LiFi Group** (Netherlands, reseller/integrator) | https://lifi.co/lifi-companies/ | Signify partner that maintains a useful directory of Li-Fi companies (handy for your "industry landscape" slide). |

---

## 6. Where to publish a student paper

Dates checked 31 Oct 2026. Verify deadlines on the official sites before planning.

| Venue | Type / publisher | Link | Status / notes |
|---|---|---|---|
| **NCC (National Conference on Communications)** | India's flagship comms conference (IITs + IISc JTG), IEEE-format, 6 pages, double-blind | NCC 2027 CFP: https://ece.iisc.ac.in/~ncc2027/cfp.html · archive: https://www.ncc.org.in/ | NCC 2027: IISc Bengaluru, 17–20 Feb 2027. Paper deadline was 16 Oct 2026 (passed, per an organiser's LinkedIn post). **Target NCC 2028** (deadline usually around Sept–Oct). It has an "RF and Optical" track. Most prestigious India option. |
| **IEEE INDICON** | IEEE India Council flagship, proceedings on IEEE Xplore | https://www.indicon2026.com/ · https://ieeeindiacouncil.org/indicon-2-2/ | INDICON 2026: Sri Sairam Engineering College, **Chennai**, 18–20 Dec 2026. Submissions closed (deadline was 31 Aug 2026). Target **INDICON 2027** (deadline typically mid-year). Student fee ~₹9,000 (2026 rates). |
| **IEEE CONECCT** | IEEE Bangalore Section flagship, 6–8 pages, includes a Communication Systems focus area and poster/demo tracks | https://ieee-conecct.org/ | **CONECCT 2027: 29–31 July 2027, Bengaluru** (per the site home page). 2026's paper deadline was in Feb, so expect ~Feb 2027. **Best timing fit** for a project finishing in spring 2027. Poster/demo tracks suit hardware prototypes. |
| **ICCCNT** | IEEE-sponsored, large multi-track (computing/communication/networking) | https://17icccnt.com/ · EasyChair CFP: https://easychair.org/cfp/17icccnt2026 | 17th ICCCNT 2026 was listed for IIT Delhi (28 Jun–3 Jul 2026), but the EasyChair CFP lists UNT, Texas, 19–21 Dec 2026. **The sources conflict**, so confirm on the official site. High acceptance, student-friendly. ⚠ Do **not** confuse it with the WASET "ICCCNT" listings at waset.org (widely regarded as predatory) or with "icICCNT" (Paris). |
| **Springer LNEE** (Lecture Notes in Electrical Engineering) | Book series publishing many Indian conference proceedings | https://link.springer.com/series/7818 | Not a conference itself: you submit to a conference whose proceedings go to LNEE. Scopus-indexed (SJR Q4 per https://www.scimagojr.com/journalsearch.php?q=19700186822&tip=sid). Check that the conference is genuine before paying fees. |
| **MDPI Sensors / Photonics** (journals, open access) | Peer-reviewed, Scopus/WoS indexed, with APCs (article processing charges) | Sensors: https://www.mdpi.com/journal/sensors · the BFSK paper #9 appeared in its *Automotive VLC* special issue | The natural home for an extended version with a strong hardware/experimental component. APCs are significant, so check for waivers or institutional support. |
| **IEEE Latin America Transactions** | IEEE journal, accepts didactic/low-cost embedded work (#20 was published there) | https://latamt.ieeer9.org/index.php/transactions/about | Shows that "low-cost educational VLC" papers are publishable in IEEE journals. |

**Recommended path:** build and measure through Feb 2027, then submit to **IEEE CONECCT 2027** (Bengaluru, July 2027) or the next ICCCNT. Aim for **NCC 2028 / INDICON 2027** if results are strong. Consider an MDPI Sensors extension later.

---

## Gaps and caveats in this pack
- Some IEEE papers were read only at abstract/metadata level (paywalled). Full citations for #15, #16, #17, #25 and #26 lack author names because the publisher pages did not show them during this session. Look them up via the DOI before citing.
- Kahn & Barry (#8), Avătămăniței 2020 and Islim 2018 were seen only as DOIs in reference lists.
- The IEEE 802.15.7 flicker threshold (commonly quoted as a 5 ms maximum flicker period, ≈200 Hz) was **not** verified from the standard text in this session, so check it in source #1/#2 before quoting a number.
- The ESP32 ADC maximum sampling rate was not extracted, so check the ADC continuous-mode docs for your exact chip (ESP32 vs ESP32-S3).
- Conference dates and fees change. Re-check the official sites before planning around them.
