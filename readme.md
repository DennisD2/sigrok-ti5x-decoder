## TI5x (TI59, TI58, TI58C) pocket calculator decoder
My try to have a Sigrok based decoder for signals from the venerable
pocket calculators made by texas Instruments. 

Useful signals: 4 bit data bus, IDLE, EXT, IRG, PHI1.

Some signals are available at the library module slot:
* IDLE, EXT, IRG, PHI1
* GND (I use Vdd for that together with my KingST LA5032 Logic Analyzer)

4 bit data bus is only available at the chip pins after removing the 
back of the TI housing.

Two example view of some early version of the decoder. Several instruction 
cycles are shown. LA was used with 1 MS/sec and 5 MS/sec.

![](media/bug-last-digit.png)

![](media/bug-last-digit-verified.png)

## How to install the decoder
On startup, sigrok and pulseview look in several directories for decoders.

On Linux for example, the local user directory that can contain custom
decoders is located at ```$HOME/.local/share/libsigrokdecode/decoders```
Check Pulseview/Sigrok documentation for required location on other operating
systems.

Create a new directory ```ti5x``` in the mentioned directory and copy all files
from this repository to that directory, e.g. into ```$HOME/.local/share/libsigrokdecode/decoders/ti5x```
(Absolutely required files are: __init__.py and pd.py)

## How to use the decoder
After installation part described avove, restart Pulseview. 

It should now offer the new decoder in the decoder section "Retro computing".

If you have named the Pins 0..7 with correct names (IDLE, EXT, IRG, IO8, IO4,
IO2, IO1, PHI1), Pulseview will connect these pins directly to the decoder
inputs and decoding will start.

### Example input files
In directory ```examples``` I've put two sigrok sample data dumps. These can
be loaded by pulseview, the decoder then can be applied to them.

* [examples/ti59-session001-4secs-5mhz-switch-on.*](examples): 
This is a sample with length of 4 seconds from a well working TI-59. The
TI-59 is being switched on. What can be seen in the sample is that the calculator
does some initialization stuff, IDLE signal is in "CALCULATE" mode. After
initialization, the calculator goes to "DISPLAY" mode, waiting for key presses.

* [examples/ti58c-session000-5secs-switch-on-auswahl.*](examples): 
This is a sample of about 5 seconds from a broken TI-58C. The TI-58C is being switched
on. There is also an initialization section in CALCULATE mode and then the
section where calculator seems to wait for key presses, then in DISPLAY mode.
The calculator is broken, does not respond to key presses and displays arbitrary
random data in display. 

Note: For both samples, the GND pin of the logic analyzer used was attached to Vdd.
This was done because if being connected to calculators Vss (0 volts),
the signals could not be detected. The Signals are PMOS and run between 
0 volts(=Vss) and -15.6(=Vgg) / -10 volts (=Vdd). These values are too large for my logic analyzer
KingST LA5032,
which has maximum LO/HI threshold of +4 .. -4 volts.
So I have used Vdd as "virtual GND" to take these samples. I am not sure if that leads to issues, see
TODOs section below.

## TODOs
* IO-lines processing not yet done
* I am not sure at all that the decoding works correct. For example, the IO
  lines show activity after all BRA (branch) instructions (seems ok), but also after
  many other instructions, which does not make sense to me. Notably, IO line
  activity can be seen after/during mask operations (like .MANT etc.), which looks
  strange to me. 

## Documentation
* [Calculators TI–58/59 HW programming guide, by Hynek Sladky](docs/TI_58_59-HW-manual.pdf). This 
  document contains a large bunch of vauable information and also instruction code tables
* [TI PC-100A Interface Description](docs/TI_Calculator_Printer_Interface.pdf). Original
  document by Texas Instruments from 1978. Explains software/hardware protocol
  in detail, with focus on printer cradle.

## Patents by Texas Instruments related to TI-5x calculators
* 4153937 "Microprocessor system having high order capability", 1977

All patents that had been used are listed here: http://www.datamath.org/Patents.htm

