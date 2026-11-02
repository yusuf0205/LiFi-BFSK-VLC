#!/usr/bin/env python3
"""Copy common/*.h into every Arduino sketch folder (Arduino only compiles
files inside the sketch folder). Run after editing anything in common/."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "tx_esp32": ["lifi_proto.h"],
    "rx_esp32": ["lifi_proto.h", "lifi_demod.h"],
    "tx_arduino_uno": ["lifi_proto.h"],
    "rx_arduino_uno_xr2211": ["lifi_proto.h"],
}

if __name__ == "__main__":
    for sketch, files in TARGETS.items():
        for f in files:
            shutil.copy2(ROOT / "common" / f, ROOT / sketch / f)
            print(f"common/{f} -> {sketch}/{f}")
