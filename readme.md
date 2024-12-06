## TI5x (TI59, TI58, TI58C) pocket calculator decoder
4 bit data bus, IDLE, EXT, IRG, PHI1.

## Patents
4153937	TI-59	 	1977	Microprocessor system having high order capability

## TODOs
* timing ausgeben
* cycle time (phi, instruction) berechnen und bei timing ausgeben

* Fix bug:
![](bug-last-digit.png)

Check second instruction cycle: 
While the IRG bit line decodes correct to 1111.0100.1001.1110,
the IRG Word line IRGW decodes wrong to:  1111.0100.1001.1111, so last bit is wrong.

It looks like the last bit repeats value or the bit before. This is somehow verified
by next example. 
4 cycles can be seen:
* cycle 1: bits end with ...10, word then becomes ...11
* cycle 2: bits end with ...01, word then becomes ...00
* cycle 3: bits end with ...00, word then becomes ...00
* cycle 4: bits end with ...10, word then becomes ...11
![](bug-last-digit-verified.png)

This means that the value of the bit at s14 is used for s15 when creating the word value.
For the creation of the bit value, it works already correct.
