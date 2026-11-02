import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sim"))
sys.path.insert(0, str(ROOT / "tools"))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def host_harness():
    """Firmware lifi_proto.h/lifi_demod.h compiled for the PC (skips if no C++ compiler)."""
    import run_sim
    exe = run_sim.build_host_harness()
    if exe is None:
        pytest.skip("no C++ compiler (g++/clang++/ziglang) available")
    return exe
