#!/usr/bin/env python3
"""lifi_gui.py - small Tk GUI for the Li-Fi link: send text/files to the TX,
watch the RX log, live BER and RSSI plot, received files saved automatically.

  python lifi_gui.py            (pick ports in the window)
Requires: pyserial, matplotlib (TkAgg), Tk.
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lifi_link import (BertEvent, FileReceiver, FrameEvent, StatEvent, file_to_chunks,  # noqa: E402
                       open_port, parse_line, send_bytes, send_text)

import matplotlib  # noqa: E402

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402


def list_ports():
    try:
        from serial.tools import list_ports as lp
        return [p.device for p in lp.comports()]
    except Exception:
        return []


class App:
    def __init__(self, root):
        self.root = root
        root.title("Li-Fi BFSK link")
        self.tx = None
        self.rx = None
        self.q: queue.Queue = queue.Queue()
        self.files = FileReceiver()
        self.saved = set()
        self.out_dir = Path("received")
        self.t0 = time.time()
        self.ber_hist, self.rssi_hist = [], []

        top = ttk.Frame(root, padding=6)
        top.pack(fill="x")
        ports = list_ports()
        self.tx_var = tk.StringVar(value=ports[0] if ports else "")
        self.rx_var = tk.StringVar(value=ports[1] if len(ports) > 1 else "")
        self.rx_baud = tk.StringVar(value="921600")
        ttk.Label(top, text="TX port").pack(side="left")
        ttk.Combobox(top, textvariable=self.tx_var, values=ports, width=14).pack(side="left")
        ttk.Label(top, text="RX port").pack(side="left", padx=(8, 0))
        ttk.Combobox(top, textvariable=self.rx_var, values=ports, width=14).pack(side="left")
        ttk.Combobox(top, textvariable=self.rx_baud, values=["921600", "115200"], width=8).pack(side="left")
        ttk.Button(top, text="Connect", command=self.connect).pack(side="left", padx=6)

        mid = ttk.Frame(root, padding=6)
        mid.pack(fill="x")
        self.entry = ttk.Entry(mid, width=60)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send_text())
        ttk.Button(mid, text="Send text", command=self.send_text).pack(side="left", padx=3)
        ttk.Button(mid, text="Send file...", command=self.send_file).pack(side="left", padx=3)
        ttk.Button(mid, text="BER test (200)", command=lambda: self.tx_cmd("!bert 200 20")).pack(side="left", padx=3)
        ttk.Button(mid, text="FEC on", command=lambda: self.tx_cmd("!fec on")).pack(side="left")
        ttk.Button(mid, text="FEC off", command=lambda: self.tx_cmd("!fec off")).pack(side="left")

        body = ttk.Frame(root, padding=6)
        body.pack(fill="both", expand=True)
        self.log = tk.Text(body, width=70, height=28, font=("Consolas", 9))
        self.log.pack(side="left", fill="both", expand=True)
        fig = Figure(figsize=(5, 5))
        self.ax1 = fig.add_subplot(211)
        self.ax2 = fig.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(fig, master=body)
        self.canvas.get_tk_widget().pack(side="right", fill="both", expand=True)
        self.status = tk.StringVar(value="not connected")
        ttk.Label(root, textvariable=self.status, padding=4).pack(fill="x")
        root.after(200, self.poll)

    # ------------------------------------------------------------ actions
    def println(self, s):
        self.log.insert("end", s + "\n")
        self.log.see("end")

    def connect(self):
        try:
            if self.tx_var.get():
                self.tx = open_port(self.tx_var.get(), 115200)
            if self.rx_var.get():
                self.rx = open_port(self.rx_var.get(), int(self.rx_baud.get()))
                threading.Thread(target=self.reader, daemon=True).start()
            self.status.set(f"TX={self.tx_var.get() or '-'}  RX={self.rx_var.get() or '-'}")
        except Exception as e:  # noqa: BLE001
            self.status.set(f"error: {e}")

    def tx_cmd(self, c):
        if self.tx:
            self.tx.write((c + "\n").encode())

    def send_text(self):
        t = self.entry.get()
        if self.tx and t:
            threading.Thread(target=send_text, args=(self.tx, t), daemon=True).start()
            self.println(f">> {t}")
            self.entry.delete(0, "end")

    def send_file(self):
        p = filedialog.askopenfilename()
        if not p or not self.tx:
            return
        data = Path(p).read_bytes()

        def run():
            chunks = file_to_chunks(Path(p).name, data, int(time.time()) & 0xFF)
            for i, c in enumerate(chunks):
                send_bytes(self.tx, c, timeout=10)
                self.q.put(("status", f"sending {Path(p).name}: {i + 1}/{len(chunks)}"))
            self.q.put(("status", f"sent {Path(p).name} ({len(data)} bytes)"))

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------ RX thread + UI loop
    def reader(self):
        while True:
            try:
                line = self.rx.readline().decode(errors="replace").rstrip()
            except Exception:  # noqa: BLE001
                break
            if line:
                self.q.put(("line", line))

    def poll(self):
        redraw = False
        while not self.q.empty():
            kind, val = self.q.get()
            if kind == "status":
                self.status.set(val)
                continue
            ev = parse_line(val)
            now = time.time() - self.t0
            if isinstance(ev, FrameEvent):
                if ev.rssi_db is not None:
                    self.rssi_hist.append((now, ev.rssi_db))
                    redraw = True
                if ev.ok:
                    fa = self.files.feed(ev.payload)
                    if fa is not None:
                        self.status.set(f"file '{fa.name}': {fa.total - 1 - len(fa.missing())}/{fa.total - 1} chunks")
                        if fa.verified() and fa.file_id not in self.saved:
                            self.out_dir.mkdir(exist_ok=True)
                            out = self.out_dir / (os.path.basename(fa.name) or "file.bin")
                            out.write_bytes(fa.data())
                            self.saved.add(fa.file_id)
                            self.println(f"[file saved] {out}")
                        continue
            elif isinstance(ev, BertEvent) or (isinstance(ev, StatEvent) and ev.bert_bits):
                self.ber_hist.append((now, max(ev.ber, 1e-7)))
                redraw = True
            if not val.startswith("#FRAME"):
                self.println(val)
        if redraw:
            self.ax1.clear()
            self.ax2.clear()
            if self.ber_hist:
                self.ax1.semilogy(*zip(*self.ber_hist), "o-", ms=3)
            self.ax1.set_ylabel("BER")
            self.ax1.grid(True, which="both", alpha=0.3)
            if self.rssi_hist:
                self.ax2.plot(*zip(*self.rssi_hist), ".-")
            self.ax2.set_ylabel("RSSI dB")
            self.ax2.set_xlabel("s")
            self.canvas.draw_idle()
        self.root.after(200, self.poll)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
