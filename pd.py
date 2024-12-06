##
## This file is part of the libsigrokdecode project.
##
## Copyright (C) 20xxx
##
## This program is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation; either version 3 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program; if not, see <http://www.gnu.org/licenses/>.
##

import sigrokdecode as srd
from functools import reduce
import string

class SamplerateError(Exception):
    pass

class State:
    INIT, IDLEwait, SXwait, SXstarts, SX, SXends = range(6)

class Pin:
    IDLE = 0
    EXT = 1
    IRG = 2
    IO8 = 3
    IO4 = 4
    IO2 = 5
    IO1 = 6
    PHI1 = 7

class Mode:
    CALCULATE, DISPLAY = range(2)

class AnnoRowPos:
    STATE, EXTBITS, IRGBITS, CALC, DISP, TIMING, INSTRUCTION, WARN, ERROR = range(9)

# Provide custom format type 'H' for hexadecimal output
# with leading decimal digit (assembler syntax).
class AsmFormatter(string.Formatter):
    def format_field(self, value, format_spec):
        if format_spec.endswith('H'):
            result = format(value, format_spec[:-1] + 'X')
            return result if result[0] in string.digits else '0' + result
        else:
            return format(value, format_spec)

formatter = AsmFormatter()


def normalize_time(t):
    if abs(t) >= 1.0:
        return '%.3f s  (%.3f Hz)' % (t, (1/t))
    elif abs(t) >= 0.001:
        if 1/t/1000 < 1:
            return '%.3f ms (%.3f Hz)' % (t * 1000.0, (1/t))
        else:
            return '%.3f ms (%.3f kHz)' % (t * 1000.0, (1/t)/1000)
    elif abs(t) >= 0.000001:
        if 1/t/1000/1000 < 1:
            return '%.3f μs (%.3f kHz)' % (t * 1000.0 * 1000.0, (1/t)/1000)
        else:
            return '%.3f μs (%.3f MHz)' % (t * 1000.0 * 1000.0, (1/t)/1000/1000)
    elif abs(t) >= 0.000000001:
        if 1/t/1000/1000/1000:
            return '%.3f ns (%.3f MHz)' % (t * 1000.0 * 1000.0 * 1000.0, (1/t)/1000/1000)
        else:
            return '%.3f ns (%.3f GHz)' % (t * 1000.0 * 1000.0 * 1000.0, (1/t)/1000/1000/1000)
    else:
        return '%f' % t

class Decoder(srd.Decoder):
    api_version = 3
    id       = 'ti5x'
    name     = 'TI5x'
    longname = 'TI-5x decoder'
    desc     = 'Texas Instruments TI-5x pocket calculator system bus decoding.'
    license  = 'gplv3+'
    inputs   = ['logic']
    outputs  = []
    tags     = ['Retro computing']
    channels = (
        {'id': 'idle', 'name': 'IDLE', 'desc': 'IDLE'},
        {'id': 'ext', 'name': 'EXT', 'desc': 'serial data line'},
        {'id': 'irg', 'name': 'IRG', 'desc': 'serial command line'},
        {'id': 'io8', 'name': 'IO8', 'desc': 'data line 8'},
        {'id': 'io4', 'name': 'IO4', 'desc': 'data line 4'},
        {'id': 'io2', 'name': 'IO2', 'desc': 'data line 2'},
        {'id': 'io1', 'name': 'IO1', 'desc': 'data line 1'},
        {'id': 't1', 'name': 'PHI1', 'desc': 'clock PHI 1'},
    )
    optional_channels = ()
    annotations = (
        ('s0', 'Start of instruction cycle'),
        ('extbit', 'EXT line data bits'),
        ('irgbit', 'IRG line data bits'),
        ('bitdata', 'data bits'),
        ('calculate', 'calculate mode'),
        ('display', 'display mode'),
        ('timing', 'Timing'),
        ('instruction', 'Instruction'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    )

    annotation_rows = (
        ('state', 'State', (0,)),
        ('extbits', 'EXT', (1,)),
        ('irgbits', 'IRG', (2,)),
        ('calc', 'Timing Calculate', (3,)),
        ('disp', 'Timing Display', (4,)),
        ('timings', 'Timings', (5,)),
        ('instructions', 'Instructions', (6,)),
        ('warnings', 'Warnings', (7,)),
        ('errors', 'Errors', (8,)),
    )

    def __init__(self):
        self.state = State.INIT
        self.last_idle = 0
        self.last_phi1 = 0
        self.idle_samplenum = 0
        self.mode = Mode.CALCULATE

    def metadata(self, key, value):
        if key == srd.SRD_CONF_SAMPLERATE:
            self.samplerate = value

    def reset(self):
        # reset inner states
        self.state = State.INIT
        self.samplerate = None

    def start(self):
        self.out_ann    = self.register(srd.OUTPUT_ANN)

    def put_text(self, ss, ann_idx, ann_text):
        self.put(ss, self.samplenum, self.out_ann, [ann_idx, [ann_text]])

    def decode(self):
        if not self.samplerate:
            raise SamplerateError('Cannot decode without samplerate.')

        statenum = 0
        extBits = ""
        irgBits = ""
        self.state = State.INIT

        while True:
            pins = self.wait()
            idle = pins[Pin.IDLE]
            phi1 = pins[Pin.PHI1]

            valExt = 0

            if self.state == State.INIT:
                self.state = State.IDLEwait
                statenum = 0
                # initialize last_* values
                self.last_idle = idle
                self.last_phi1 = phi1
                self.put_text(self.samplenum, AnnoRowPos.STATE,
                              'INIT')

            if self.state == State.IDLEwait:
                # falling edge of IDLE ?
                if (idle == 0) and (self.last_idle == 1):
                    self.state = State.SXstarts
                    #self.put_text(self.samplenum, AnnoRowPos.STATE,
                    #              's0')
                    #self.put(self.samplenum, self.samplenum+2, self.out_ann,
                    #         [AnnoRowPos.STATE, ['s0']])
                    # keep starting sample for later use
                    self.idle_samplenum = self.samplenum
                    statenum = 0

            if self.state == State.SXstarts:
                self.state = State.SX
                valExt = 0
                self.put_text(self.samplenum, AnnoRowPos.STATE,
                              's' + str(statenum))

            if self.state == State.SX:
                if phi1 == 0:
                    valExt += pins[Pin.EXT]
                else:
                    self.state = State.SXends

            if self.state == State.SXends:
                if phi1 == 0 and self.last_phi1 == 1:
                    if statenum < 15:
                        self.state = State.SXstarts
                        statenum += 1
                        self.put_text(self.samplenum, AnnoRowPos.EXTBITS,
                                  str(valExt))
                    else:
                        self.state = State.IDLEwait

            self.last_idle = idle
            self.last_phi1 = phi1