# Build and test log

Environment: Linux aarch64 sandbox, arduino-cli 1.5.1, esp32:esp32 3.3.12 (ESP-IDF 5.x based), arduino:avr 1.8.8,
Python 3 with numpy/scipy/matplotlib/pytest, host C++ via `python -m ziglang c++` (clang).
All compiles used `--warnings all`. No warnings or errors came from the sketch or `common/` code; only warnings from the Arduino core itself.
**Nothing was flashed to real boards.**

| Sketch | Board (FQBN) | Result | Flash | RAM (globals) |
|---|---|---|---|---|
| tx_esp32 | esp32:esp32:esp32 | OK | 289 531 B (22 %) | 24 272 B (7 %) |
| rx_esp32 | esp32:esp32:esp32 | OK | 287 284 B (21 %) | 23 988 B (7 %) |
| rx_esp32 | esp32:esp32:esp32s3 (TYPE2 ADC format path) | OK | 298 073 B (22 %) | 23 656 B (7 %) |
| tx_esp32 | esp32:esp32:esp32c3 (RISC-V, gpio_ll path) | OK* | 320 138 B (24 %) | 16 388 B (5 %) |
| tx_arduino_uno (Timer1 CPFSK) | arduino:avr:uno | OK | 4 156 B (12 %) | 418 B (20 %) |
| tx_arduino_uno (USE_TONE 1) | arduino:avr:uno | OK | 4 810 B (14 %) | 365 B (17 %) |
| rx_arduino_uno_xr2211 (packet/DPLL) | arduino:avr:uno | OK | 5 582 B (17 %) | 554 B (27 %) |
| rx_arduino_uno_xr2211 (RX_MODE_UART) | arduino:avr:uno | OK | 3 172 B (9 %) | 305 B (14 %) |

\* On ESP32-C3, change `LED_PIN` (GPIO25 does not exist there; e.g. use GPIO4).

Host build of the firmware headers (`tests/host/host_harness.cpp`, `-Wall -Wextra`): clean.

`python -m pytest -q tests` → **47 passed**.
`python sim/run_sim.py` → plots and `results.json` in `sim/out/` (about 2 min).
