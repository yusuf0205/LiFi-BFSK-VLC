import numpy as np
q=1.602e-19; kT=1.38e-23*300
# ---- assumptions (see hardware.md section 2.6) ----
P_on   = 0.25     # W optical, 1 W white LED driven at ~0.27 A (approx 30 % wall-plug)
m      = 1.0      # Lambertian order, half-power semi-angle 60 deg (bare LED star)
A      = 7.5e-6   # BPW34 active area, m^2
R      = 0.30     # A/W, BPW34 responsivity averaged over white-LED spectrum (peak 0.6 A/W @ 900 nm)
Rf     = 47e3
# noise bandwidth of branch A from simulated response
d = np.genfromtxt("rx_ac.dat", names=True); f=d['frequency']; H=10**(d['vdbbpout']/20)
Beq = np.trapezoid((H/H.max())**2, f); Hpk=H.max()
H10 = np.interp(10e3,f,H); H15=np.interp(15e3,f,H)
def lam(dist, phi=0, psi=0, m=m, gain=1.0):
    return P_on*(m+1)/(2*np.pi*dist**2)*np.cos(np.radians(phi))**m*A*np.cos(np.radians(psi))*gain
rows=[]
fmt=lambda b: '<1e-12' if b<1e-12 else f'{b:.1e}'
print(f"Branch-A noise bandwidth B_eq = {Beq/1e3:.1f} kHz, peak transimpedance = {Hpk/1e6:.2f} MOhm, at 10k/15k = {H10/1e6:.2f}/{H15/1e6:.2f} MOhm")
print("| d (m) | angle | P_rx peak (uW) | I_on (nA) | I_sig fund. rms (nA) | XR2211 in (mV rms) | ambient (uA) | noise in B_eq (pA rms) | SNR (dB) | Eb/N0 @4.8k (dB) | BER ncFSK @4.8k | BER @10k |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
for dist,ang,gain,tag in [(0.5,0,1,''),(1,0,1,''),(2,0,1,''),(3,0,1,''),(3,30,1,''),(3,0,30,' +15deg TX lens')]:
    for Iamb in ([2e-6,10e-6,50e-6] if (dist in (1,3) and ang==0 and gain==1) else [10e-6]):
        P=lam(dist,ang,ang,gain=gain); Ion=P*R; Isig=np.sqrt(2)/np.pi*Ion
        S = 2*q*Iamb*2 + 4*kT/Rf + 2*q*Ion/2   # A^2/Hz: PD shot + servo-transistor shot + Rf thermal + signal shot
        n_rms=np.sqrt(S*Beq); snr=20*np.log10(Isig/n_rms)
        out=[]
        for Rb in (4.8e3,10e3):
            ebn0 = Isig**2/Rb/S
            out.append((10*np.log10(ebn0), 0.5*np.exp(-ebn0/2)))
        vxr = Isig*H10*1e3
        rows.append((dist,ang,tag,P*1e6,Ion*1e9,Isig*1e9,vxr,Iamb*1e6,n_rms*1e12,snr,out[0][0],out[0][1],out[1][1]))
        print(f"| {dist}{tag} | {ang} deg | {P*1e6:.3g} | {Ion*1e9:.3g} | {Isig*1e9:.3g} | {min(vxr,1700):.3g}{' (clips, OK for FSK)' if vxr>1700 else ''} | {Iamb*1e6:g} | {n_rms*1e12:.0f} | {snr:.1f} | {out[0][0]:.1f} | {fmt(out[0][1])} | {fmt(out[1][1])} |")

# max range where Eb/N0 at 10 kbps = 14.2 dB (BER 1e-6 ideal ncFSK) + 10 dB implementation margin, 10 uA ambient
for Iamb in (2e-6,10e-6,50e-6):
    for gain,tag in ((1,'bare LED'),(30,'15deg TX lens')):
        ds=np.linspace(0.3,40,4000); ok=[]
        for dd in ds:
            P=lam(dd,gain=gain); Ion=P*R; Isig=np.sqrt(2)/np.pi*Ion
            S=2*q*Iamb*2+4*kT/Rf+2*q*Ion/2
            ok.append(10*np.log10(Isig**2/10e3/S))
        ok=np.array(ok); dmax=ds[np.where(ok>=24.2)[0].max()]
        print(f"max range @10 kbps, ambient {Iamb*1e6:g} uA, {tag}: {dmax:.1f} m")
