import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
d = np.genfromtxt("rx_ac.dat", names=True)
f = d['frequency']
fig, ax = plt.subplots(figsize=(9,5.2))
for k,lab in [('vdbtout','TIA out (U1A)'),('vdbgout','Gain stage out (U2A)'),
              ('vdbbpout','Branch A: MFB band-pass out -> XR2211'),('vdbadc','Branch B: SK LPF out -> ESP32 ADC')]:
    key=[n for n in d.dtype.names if n.replace('_','').lower().startswith(k)][0]
    ax.semilogx(f, d[key], label=lab, lw=1.6)
for x,l in [(100,'100 Hz flicker'),(10e3,'f1 10k'),(15e3,'f0 15k'),(20e3,'B: 20k'),(30e3,'B: 30k')]:
    ax.axvline(x, color='grey', ls=':', lw=0.8); ax.text(x*1.03, 32, l, rotation=90, fontsize=7, color='dimgrey')
ax.set_xlabel("Frequency (Hz)"); ax.set_ylabel("Transimpedance (dB re 1 V/A)")
ax.set_title("Li-Fi RX front end: BPW34 + TIA(47k) + DC servo + x101 + filters  (ngspice AC)")
ax.set_ylim(30,160); ax.grid(True, which='both', alpha=0.3); ax.legend(fontsize=8, loc='upper left')
fig.tight_layout(); fig.savefig("../rx_ac_response.png", dpi=130)

n = np.genfromtxt("rx_noise.dat", names=True)
fig, ax = plt.subplots(figsize=(8,4))
ax.loglog(n['frequency'], n[n.dtype.names[1]]*1e12, label='input-referred current noise (circuit only)')
ax.set_xlabel("Frequency (Hz)"); ax.set_ylabel("pA/rtHz"); ax.grid(True, which='both', alpha=.3)
shot = np.sqrt(2*1.602e-19*10e-6)*1e12
ax.axhline(shot, color='r', ls='--', label=f'shot noise of 10 uA ambient = {shot:.2f} pA/rtHz')
ax.legend(fontsize=8); ax.set_title("RX input-referred noise (ngspice .noise, op-amp macro noiseless)")
fig.tight_layout(); fig.savefig("../rx_noise.png", dpi=130)

t = np.genfromtxt("tx_tran.dat", names=True)
m = (t['time']>60e-6)&(t['time']<200e-6)
fig, ax1 = plt.subplots(figsize=(9,4.5))
ax1.plot(t['time'][m]*1e6, t['vgpio'][m], label='GPIO (V)')
ax1.plot(t['time'][m]*1e6, t['vg'][m], label='Gate (V)')
ax1.plot(t['time'][m]*1e6, t['vd'][m], label='Drain (V)')
ax2 = ax1.twinx(); ax2.plot(t['time'][m]*1e6, -t['iVDD'][m]*1e3, 'k', lw=1, label='LED current (mA)')
ax2.set_ylabel('LED current (mA)'); ax1.set_ylabel('V'); ax1.set_xlabel('time (us)')
ax1.legend(loc='upper left', fontsize=8); ax2.legend(loc='upper right', fontsize=8)
ax1.set_title('TX driver, 15 kHz tone: ESP32 GPIO -> 100R -> IRLZ44N -> 1 W LED + 6.8R @5 V (ngspice)')
fig.tight_layout(); fig.savefig("../tx_transient.png", dpi=130)
print("ok", d.dtype.names, n.dtype.names, t.dtype.names)
