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
    INIT, WAIT_FOR_IDLE_LO, WAIT_FOR_PHI_HI, SX_START, SX, SX_END = range(6)

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
    STATE, EXTBITS, EXTWORDS, IRGBITS, IRGWORDS, CALC, DISP, TIMING, INSTRUCTION, WARN, ERROR = range(11)

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
        ('extword', 'EXT line data word'),
        ('irgbit', 'IRG line data bits'),
        ('irgword', 'IRG line data word'),
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
        ('extwords', 'EXTW', (2,)),
        ('irgbits', 'IRG', (3,)),
        ('irgwords', 'IRGW', (4,)),
        ('calc', 'Timing Calculate', (5,)),
        ('disp', 'Timing Display', (6,)),
        ('timings', 'Timings', (7,)),
        ('instructions', 'Instructions', (8,)),
        ('warnings', 'Warnings', (9,)),
        ('errors', 'Errors', (10,)),
    )

    def __init__(self):
        self.state = State.INIT
        self.last_idle = 0
        self.last_phi1 = 0
        self.last_state = 0
        self.instruction_start_sample = 0
        self.state_start_sample = 0
        self.sx_samplenum = 0
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
        self.state = State.INIT
        valExt = 0
        valIRG = 0

        s_ext_values = 16 * [0]
        s_ext_done = 16 * [0]
        s_irg_values = 16 * [0]
        s_irg_done = 16 * [0]

        # initialize state machine
        next_state = State.INIT

        while True:
            pins = self.wait()
            idle = pins[Pin.IDLE]
            phi1 = pins[Pin.PHI1]
            ext = pins[Pin.EXT]
            irg = pins[Pin.IRG]

            if next_state != self.state:
                #name = next(name for name, value in vars(State).items() if value == self.state)
                name = str(self.state)
                self.put(self.samplenum, self.samplenum, self.out_ann,
                         [AnnoRowPos.WARN, [name]])
                self.state_start_sample = self.samplenum

            # forward state machine
            self.state = next_state

            if self.state == State.INIT:
                # next state will wait for IDLE become LO
                next_state = State.WAIT_FOR_IDLE_LO
                # initialize last_* values
                self.last_idle = idle
                self.last_phi1 = phi1
                self.put_text(self.samplenum, AnnoRowPos.STATE,
                              'INIT')

            # wait for IDLE become LO
            if self.state == State.WAIT_FOR_IDLE_LO:
                # falling edge of IDLE ?
                if idle == 0 and self.last_idle == 1:
                    next_state = State.WAIT_FOR_PHI_HI
                    # keep starting sample for later use
                    self.instruction_start_sample = self.samplenum
                    self.state_start_sample = self.samplenum
                    self.sx_samplenum = self.samplenum
                    statenum = 0

            if self.state == State.WAIT_FOR_PHI_HI:
                # read s0 until phi1 is true
                if phi1 == 1:
                    next_state = State.SX_START
                    # initialize bit value for sx state
                    valExt = ext
                    valIRG = irg

            if self.state == State.SX_START:
                # start location of sx state
                self.sx_samplenum = self.state_start_sample

                self.put_text(self.sx_samplenum, AnnoRowPos.STATE,
                              's' + str(statenum))
                next_state = State.SX

            if self.state == State.SX:
                if phi1 == 1:
                    valExt += ext
                    valIRG += irg
                else:
                    next_state = State.SX_END

            if self.state == State.SX_END:
                self.put(self.sx_samplenum, self.samplenum, self.out_ann,
                         [AnnoRowPos.EXTBITS, [str(valExt)]])
                self.put(self.sx_samplenum, self.samplenum, self.out_ann,
                         [AnnoRowPos.IRGBITS, [str(valIRG)]])

                if statenum < 15:
                    # wait for next sx state
                    next_state = State.WAIT_FOR_PHI_HI
                    statenum += 1
                else:
                    # all states of this instruction cycle have been read, start over
                    statenum = 0
                    next_state = State.WAIT_FOR_IDLE_LO

            # update last_* values
            self.last_idle = idle
            self.last_phi1 = phi1