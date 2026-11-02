#!/usr/bin/env python3
"""lifi_tool.py - PC command line tool for the Li-Fi BFSK link (pyserial).

  python lifi_tool.py --tx COM5 send "hello over light"
  python lifi_tool.py --tx COM5 sendfile photo.jpg [--repeat 2]
  python lifi_tool.py --tx COM5 bert --count 500
  python lifi_tool.py --rx COM6 monitor [--plot] [--save-files out/] [--log rx.csv]
  python lifi_tool.py --tx COM5 cmd "!f0 12000"

The receiver port defaults to 921600 baud (rx_esp32); use --rx-baud 115200 for the Uno.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lifi_link import (BertEvent, FileReceiver, FrameEvent, StatEvent, file_to_chunks,  # noqa: E402
                       open_port, parse_line, read_lines, send_bytes, send_text, wait_for)


def cmd_send(a):
    s = open_port(a.tx, a.tx_baud)
    send_text(s, " ".join(a.text))
    print("sent")


def cmd_cmd(a):
    s = open_port(a.tx, a.tx_baud)
    s.write((a.command + "\n").encode())
    print(wait_for(s, "#INFO", 3.0) or "(no #INFO reply)")


def cmd_sendfile(a):
    s = open_port(a.tx, a.tx_baud)
    data = Path(a.file).read_bytes()
    chunks = file_to_chunks(Path(a.file).name, data, a.file_id)
    t0 = time.time()
    for r in range(a.repeat):
        for i, c in enumerate(chunks):
            send_bytes(s, c, timeout=10)
            print(f"\rpass {r + 1}/{a.repeat} chunk {i + 1}/{len(chunks)}", end="", flush=True)
    dt = time.time() - t0
    print(f"\nsent {len(data)} bytes in {dt:.1f} s ({8 * len(data) * a.repeat / dt:.0f} bit/s goodput)")


def cmd_bert(a):
    s = open_port(a.tx, a.tx_baud)
    s.write(f"!bert {a.count} {a.gap}\n".encode())
    print(wait_for(s, "#BERTTX", a.count * 1.0 + 10) or "timeout")


def cmd_monitor(a):
    s = open_port(a.rx, a.rx_baud)
    if a.reset:
        s.write(b"!reset\n")
    files = FileReceiver()
    saved = set()
    out_dir = Path(a.save_files) if a.save_files else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    log = csv.writer(open(a.log, "w", newline="")) if a.log else None
    if log:
        log.writerow(["t", "type", "ok", "len", "rssi_db", "snr_db", "ber", "text_or_hex"])

    hist_t, hist_ber, hist_rssi = deque(maxlen=600), deque(maxlen=600), deque(maxlen=600)
    plt = None
    if a.plot:
        import matplotlib.pyplot as plt  # noqa: F811
        plt.ion()
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
        (l1,) = ax1.semilogy([], [], "o-", ms=3)
        ax1.set_ylabel("BER (cumulative)")
        ax1.grid(True, which="both", alpha=0.3)
        (l2,) = ax2.plot([], [], ".-")
        ax2.set_ylabel("frame RSSI (dB counts)")
        ax2.set_xlabel("time (s)")
        ax2.grid(alpha=0.3)
    t0 = time.time()
    last_draw = 0.0
    for line in read_lines(s):
        ev = parse_line(line)
        now = time.time() - t0
        if not line.startswith("#FRAME"):
            print(line)
        if isinstance(ev, FrameEvent):
            if ev.rssi_db is not None:
                hist_rssi.append((now, ev.rssi_db))
            if ev.ok:
                fa = files.feed(ev.payload)
                if fa is not None:
                    miss = fa.missing()
                    print(f"[file {fa.file_id} '{fa.name}'] {fa.total - 1 - len(miss)}/{fa.total - 1} chunks")
                    if out_dir and fa.verified() and fa.file_id not in saved:
                        p = out_dir / (os.path.basename(fa.name) or f"file{fa.file_id}.bin")
                        p.write_bytes(fa.data())
                        saved.add(fa.file_id)
                        print(f"[file saved] {p} ({len(fa.data())} bytes, CRC ok)")
            if log:
                log.writerow([f"{now:.3f}", "frame", int(ev.ok), ev.length, ev.rssi_db, ev.snr_db, "",
                              ev.payload.decode(errors="replace") if ev.payload.isascii() else ev.payload.hex()])
        elif isinstance(ev, (BertEvent, StatEvent)):
            ber = ev.ber
            if (isinstance(ev, BertEvent) or ev.bert_bits) and ber is not None:
                hist_ber.append((now, max(ber, 1e-7)))
            if log:
                log.writerow([f"{now:.3f}", type(ev).__name__, "", "", "", "", ber, ""])
        if plt and now - last_draw > 1.0 and (hist_ber or hist_rssi):
            if hist_ber:
                l1.set_data(*zip(*hist_ber))
            if hist_rssi:
                l2.set_data(*zip(*hist_rssi))
            for ax in (ax1, ax2):
                ax.relim()
                ax.autoscale_view()
            plt.pause(0.01)
            last_draw = now


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tx", help="TX serial port")
    ap.add_argument("--rx", help="RX serial port")
    ap.add_argument("--tx-baud", type=int, default=115200)
    ap.add_argument("--rx-baud", type=int, default=921600)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("send"); p.add_argument("text", nargs="+"); p.set_defaults(fn=cmd_send)
    p = sub.add_parser("cmd"); p.add_argument("command"); p.set_defaults(fn=cmd_cmd)
    p = sub.add_parser("sendfile"); p.add_argument("file"); p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--file-id", type=int, default=1); p.set_defaults(fn=cmd_sendfile)
    p = sub.add_parser("bert"); p.add_argument("--count", type=int, default=200)
    p.add_argument("--gap", type=int, default=20, help="ms between frames"); p.set_defaults(fn=cmd_bert)
    p = sub.add_parser("monitor"); p.add_argument("--plot", action="store_true")
    p.add_argument("--save-files"); p.add_argument("--log"); p.add_argument("--reset", action="store_true")
    p.set_defaults(fn=cmd_monitor)
    a = ap.parse_args(argv)
    if a.cmd in ("send", "cmd", "sendfile", "bert") and not a.tx:
        ap.error("--tx PORT is required")
    if a.cmd == "monitor" and not a.rx:
        ap.error("--rx PORT is required")
    a.fn(a)


if __name__ == "__main__":
    main()
