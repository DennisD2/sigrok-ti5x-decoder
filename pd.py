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
    INIT, INIT1, S0starts, S0, S0ends, S1, S2, X, WARN = range(9)

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
    STATE, BITS, CALC, DISP, WARN, ERROR = range(6)

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
        ('bitdata', 'data bits'),
        ('calculate', 'calculate mode'),
        ('display', 'display mode'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    )

    annotation_rows = (
        ('state', 'State', (0,)),
        ('bits', 'Bits', (1,)),
        ('calc', 'Calculate', (2,)),
        ('disp', 'Display', (3,)),
        ('warnings', 'Warnings', (4,)),
        ('errors', 'Errors', (5,)),
    )

    def __init__(self):
        self.state = 'INIT'
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

        bitposition = 0

        while True:
            pins = self.wait()
            idle = pins[Pin.IDLE]

            if (self.state == State.INIT):
                self.state = State.INIT1
                # initialize last_* values
                self.last_idle = idle
                self.last_phi1 = phi1
                self.idle_samplenum = self.samplenum

            # falling edge of IDLE ?
            if (idle == 0) and (self.last_idle == 1):
                if self.state == State.S0ends:
                    self.state = State.S0starts
                    # S0end state: now calculate length of idle period
                    idle_duration = (self.samplenum - self.idle_samplenum) / self.samplerate
                    end_anno_sample = self.samplenum
                    if (end_anno_sample-self.idle_samplenum) < 10:
                        end_anno_sample = self.idle_samplenum+10
                    anno_loc = 0
                    if idle_duration < 10e-6:
                        self.mode = Mode.CALCULATE
                        anno_loc = AnnoRowPos.CALC
                    else:
                        anno_loc = AnnoRowPos.DISP
                        self.mode = Mode.DISPLAY

                    # put annotation to starting sample
                    self.put(self.idle_samplenum, end_anno_sample, self.out_ann,
                             [anno_loc, [normalize_time(idle_duration)]])

                if (self.state != State.S0ends and self.state != State.S1
                        and self.state != State.S0):
                    self.state = State.S0starts
                    self.put_text(self.samplenum, AnnoRowPos.STATE,
                                  's0')
                    self.state = State.S0
                    # keep starting sample for later use
                    self.idle_samplenum = self.samplenum
                    bitposition = 1

            # raising edge of IDLE?
            if (idle == 1) and (self.last_idle == 0):
                if self.state == State.S0:
                    # if we are in S0, then we move to S0end
                    self.state = State.S0ends
                if self.state == State.S1:
                    # if we are in S0, then we move to S0end
                    self.state = State.S0starts

            # falling edge of PHI1 ?
            phi1 = pins[Pin.PHI1]
            if (phi1 == 0) and (self.last_phi1 == 1):
                if (self.state == State.S1 or self.state == State.S0
                        or self.state == State.S0ends or self.state == State.S0starts) :
                    ext = pins[Pin.EXT]
                    self.put_text(self.samplenum, AnnoRowPos.BITS, str(bitposition)+":"+str(ext))
                    if bitposition>16:
                        self.put_text(self.samplenum, AnnoRowPos.ERROR, "Illegal bit position: " + str(bitposition))
                    bitposition += 1
            self.last_idle = idle
            self.last_phi1 = phi1

