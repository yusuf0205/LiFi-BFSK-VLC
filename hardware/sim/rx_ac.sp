* ngspice runner for rx_frontend.cir (AC + noise)
.include ../rx_frontend.cir
.control
set wr_singlescale
set wr_vecnames
op
print v(tout) v(iout) v(qe) v(gout) v(bpout) v(adc) i(VCC)
ac dec 200 10 1Meg
wrdata rx_ac.dat vdb(tout) vdb(gout) vdb(bpout) vdb(xrin) vdb(adc) vp(bpout)
meas ac Ztia_12k   find vdb(tout)  at=12.25k
meas ac Zbp_12k    find vdb(bpout) at=12.25k
meas ac Zbp_10k    find vdb(bpout) at=10k
meas ac Zbp_15k    find vdb(bpout) at=15k
meas ac Zbp_100    find vdb(bpout) at=100
meas ac Zbp_1200   find vdb(bpout) at=1.2k
meas ac Zbp_max    max vdb(bpout)
meas ac fpk  when vdb(bpout)=Zbp_max
meas ac Zadc_20k   find vdb(adc) at=20k
meas ac Zadc_30k   find vdb(adc) at=30k
meas ac Zadc_100   find vdb(adc) at=100
meas ac Zadc_100k  find vdb(adc) at=100k
meas ac Zadc_200k  find vdb(adc) at=200k
meas ac Ztia_100   find vdb(tout) at=100
meas ac Ztia_1M    find vdb(tout) at=1Meg
noise v(bpout) IPH dec 50 100 100k
setplot noise1
wrdata rx_noise.dat inoise_spectrum onoise_spectrum
setplot noise2
print all
quit
.endc
.end
