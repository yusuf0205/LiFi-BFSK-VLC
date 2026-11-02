.include ../tx_driver.cir
.control
set wr_singlescale
set wr_vecnames
tran 10n 200u 0 10n
wrdata tx_tran.dat v(gpio) v(g) v(d) i(VDD)
meas tran Ion   avg i(VDD) from=80u to=95u
meas tran Ioff  avg i(VDD) from=120u to=130u
meas tran Vdoff avg v(d) from=120u to=130u
meas tran Vg_on avg v(g) from=80u to=95u
meas tran Vdon  avg v(d)   from=80u to=95u
meas tran tr_g  trig v(g) val=0.33 rise=3 targ v(g) val=2.97 rise=3
meas tran tf_d  trig v(d) val=0.5 rise=3 targ v(d) val=1.5 rise=3
meas tran td_on trig v(gpio) val=1.65 rise=3 targ v(d) val=2.5 fall=3
quit
.endc
.end
