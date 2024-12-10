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


def get_nibble(d):
    #print(d)
    result = 0
    if d[0]=="1":
        result += 8
    if d[1]=="1":
        result += 4
    if d[2]=="1":
        result += 2
    if d[3]=="1":
        result += 1
    #print("Nibble: " + d + " -> " + str(result))
    return result


def get_address(d):
    #print(d)
    result = 0
    if d[0]=="1":
        result += 512
    if d[1]=="1":
        result += 256
    if d[2]=="1":
        result += 128
    if d[3]=="1":
        result += 64
    if d[4]=="1":
        result += 32
    if d[5]=="1":
        result += 16
    if d[6]=="1":
        result += 8
    if d[7]=="1":
        result += 4
    if d[8]=="1":
        result += 2
    if d[9]=="1":
        result += 1
    #print("Address: " + d + " -> " + str(result))
    return result


def get_register(d):
    print(d)
    result = 0
    if d[0]=="1":
        result += 4
    if d[1]=="1":
        result += 2
    if d[2]=="1":
        result += 1
    print("Register: " + d + " -> " + str(result))
    return result


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

        debug = 1 # 0 or 1
        decoded = 0
        total = 0
        total_instructions = 0

        s_ext_values = 16 * [0]
        s_irg_values = 16 * [0]

        # initialize state machine
        next_state = State.INIT

        while True:
            pins = self.wait()
            idle = pins[Pin.IDLE]
            phi1 = pins[Pin.PHI1]
            ext = pins[Pin.EXT]
            irg = pins[Pin.IRG]

            total += 1

            if next_state != self.state:
                # A new state was reached
                self.state_start_sample = self.samplenum
                # forward state machine
                self.state = next_state
                if debug>0:
                    #name = next(name for name, value in vars(State).items() if value == self.state)
                    name = str(self.state)
                    self.put(self.samplenum, self.samplenum, self.out_ann,
                             [AnnoRowPos.WARN, [name]])

            if self.state == State.INIT:
                # next state will wait for IDLE become LO
                next_state = State.WAIT_FOR_IDLE_LO
                # initialize last_* values
                self.last_idle = idle
                self.last_phi1 = phi1
                self.put_text(self.samplenum, AnnoRowPos.STATE,
                              'INIT')

            if self.state == State.WAIT_FOR_IDLE_LO:
                # wait for IDLE become LO
                # falling edge of IDLE ?
                # Test change: if idle became LO during last phi1=1, we would miss this by checking for edge.
                # So I check for IDLE==LO only, without edge check.
                # OLD: if idle == 0: and self.last_idle == 1:
                if idle == 0:
                    next_state = State.WAIT_FOR_PHI_HI

                    # calculate cycle time
                    cycle_duration = (self.samplenum - self.instruction_start_sample) / self.samplerate
                    self.put(self.instruction_start_sample, self.samplenum, self.out_ann,
                             [AnnoRowPos.TIMING, [normalize_time(cycle_duration)]])

                    # keep starting sample for later use
                    self.instruction_start_sample = self.samplenum
                    self.state_start_sample = self.samplenum
                    statenum = 0
                    total_instructions += 1

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

                if debug>0 or statenum==0:
                    self.put_text(self.sx_samplenum, AnnoRowPos.STATE,
                                  's' + str(statenum))
                next_state = State.SX

            if self.state == State.SX:
                if phi1 == 1:
                    valExt += ext
                    valIRG += irg
                else:
                    next_state = State.SX_END

                if statenum == 1:
                    if idle == 1:
                        self.mode = Mode.CALCULATE
                        #self.put(self.samplenum, self.samplenum+4, self.out_ann,
                        #         [AnnoRowPos.CALC, ['CALCULATE']])
                    else:
                        self.mode = Mode.DISPLAY
                        #self.put(self.samplenum, self.samplenum+4, self.out_ann,
                        #         [AnnoRowPos.DISP, ['DISPLAY']])

            if self.state == State.SX_END:
                self.put(self.sx_samplenum, self.samplenum, self.out_ann,
                         [AnnoRowPos.EXTBITS, [str(valExt)]])
                self.put(self.sx_samplenum, self.samplenum, self.out_ann,
                         [AnnoRowPos.IRGBITS, [str(valIRG)]])
                s_ext_values[statenum] = valExt
                s_irg_values[statenum] = valIRG

                if statenum < 15:
                    # wait for next sx state
                    next_state = State.WAIT_FOR_PHI_HI
                    statenum += 1
                else:
                    # all states of this instruction cycle have been read, start over
                    statenum = 0
                    next_state = State.WAIT_FOR_IDLE_LO

                if statenum == 15:
                    # Add last bit value
                    extBits = ""
                    i = 0
                    for x in s_ext_values:
                        if x>1:
                            x=1
                        extBits += str(x)
                        i+=1
                        if i>0 and i<16 and i % 4 == 0:
                            extBits += "."

                    irgBits = ""
                    i = 0
                    for x in s_irg_values:
                        if x>1:
                            x=1
                        irgBits += str(x)
                        i+=1
                        if i>0 and i<16 and i % 4 == 0:
                            irgBits += "."

                    # EXT line value annotation
                    self.put(self.instruction_start_sample, self.samplenum, self.out_ann,
                             [AnnoRowPos.EXTWORDS, [extBits]])
                    # IRG line value annotation
                    self.put(self.instruction_start_sample, self.samplenum, self.out_ann,
                             [AnnoRowPos.IRGWORDS, [irgBits]])

                    instructionPart = irgBits[3:]
                    reversed = instructionPart[::-1]

                    annoText = self.get_instruction(reversed)
                    if annoText != "":
                        decoded += 1
                        if (decoded % 100 == 0):
                            print("Decoded: " + str(decoded) + " from total: " + str(total_instructions))
                        self.put(self.instruction_start_sample, self.samplenum, self.out_ann,
                                 [AnnoRowPos.INSTRUCTION, [annoText]])
                    else:
                        print("Undecoded instruction: " + reversed )
                    #annoText = self.get_instruction(irgBits[::-1])
                    #if annoText != "":
                    #    self.put(self.instruction_start_sample, self.samplenum, self.out_ann,
                    #             [AnnoRowPos.INSTRUCTION, [annoText + "(R)"]])

            # update last_* values
            self.last_idle = idle
            self.last_phi1 = phi1


    def get_instruction(self, irgBits):
        irgBits2 = irgBits.replace('.', '')
        #print (irgBits2)
        annoText = ""

        firstbit=irgBits2[0]
        op1 = irgBits2[1:5]
        op2 = irgBits2[5:9]
        op3 = irgBits2[9:13]
        #print( firstbit + "." + op1 + "." + op2 + "." + op3 )

        if firstbit=="1":
            lastbit = irgBits2[12]
            address = get_address(irgBits2[1:12])
            if lastbit == "0":
                return "BRA0 offs OR const +" + str(address)
            else:
                return "BRA1 offs OR const -"+ str(address)

        #return ""

        if op1 == "0000" and op3 == "0000":
            bit = get_nibble(op2)
            annoText = "TST FA(" + str(bit) + ")"
        if op1 == "0000" and op3 == "0001":
            bit = get_nibble(op2)
            annoText = "SET FA(" + str(bit) + ")"
        if op1 == "0000" and op3 == "0010":
            bit = get_nibble(op2)
            annoText = "CLR FA(" + str(bit) + ")"
        if op1 == "0000" and op3 == "0011":
            bit = get_nibble(op2)
            annoText = "INV FA(" + str(bit) + ")"
        if op1 == "0000" and op3 == "0100":
            bit = str(get_nibble(op2))
            annoText = "XCH FA(" + bit +  "),FB(" + bit + ")"

        if op1 == "0000" and op3 == "0101" and not (op2 == "0001"):
            if op2 == "0001":
                annoText = "SET PREG"
            else:
                bit = get_nibble(op2)
                annoText = "SET KR(" + str(bit) + ")"

        if op1 == "0000" and op3 == "0110":
            bit = str(get_nibble(op2))
            annoText = "MOV FA(" + bit +  "),FB(" + bit + ")"
        if op1 == "0000" and op3 == "0111":
            annoText = "MOV FA,R5"
        if op1 == "0000" and op3 == "1000":
            bit = get_nibble(op2)
            annoText = "TST FB(" + str(bit) + ")"
        if op1 == "0000" and op3 == "1001":
            bit = get_nibble(op2)
            annoText = "SET FB(" + str(bit) + ")"
        if op1 == "0000" and op3 == "1010":
            bit = get_nibble(op2)
            annoText = "CLR FB(" + str(bit) + ")"
        if op1 == "0000" and op3 == "1011":
            bit = get_nibble(op2)
            annoText = "INV FB(" + str(bit) + ")"
        if op1 == "0000" and op3 == "1100":
            bit = str(get_nibble(op2))
            annoText = "CMP FA(" + bit +  "),FB(" + bit + ")"
        if op1 == "0000" and op3 == "1101":
            bit = get_nibble(op2)
            annoText = "CLR KR(" + str(bit) + ")"
        if op1 == "0000" and op3 == "1110":
            bit = str(get_nibble(op2))
            annoText = "MOV FB(" + bit +  "),FA(" + bit + ")"
        if op1 == "0000" and op3 == "1111":
            annoText = "MOV R5,FB"

        if op1 == "0001":
            annoText = ".ALL"
        if op1 == "0010":
            annoText = ".DPT"
        if op1 == "0011":
            annoText = ".DPT1"
        if op1 == "0100":
            annoText = ".DPTC"
        if op1 == "0101":
            annoText = ".LLSD1"
        if op1 == "0110":
            annoText = ".EXP"
        if op1 == "0111":
            annoText = ".EXP1"
        if op1 == "1000":
            annoText = "KEY mask"
        if op1 == "1001":
                annoText = ".MANT"
        if op1 == "1010" and op3 == "0000":
            annoText = "WAIT DIGIT " + str(get_nibble(op2))
        if op1 == "1010" and op3 == "0001":
            annoText = "CLR IDLE"
        if op1 == "1010" and op3 == "0010":
            annoText = "CLR FA"
        if op1 == "1010" and op3 == "0011":
            annoText = "WAIT BUSY"
        if op1 == "1010" and op3 == "0100":
            annoText = "INK KR"
        if op1 == "1010" and op3 == "0101":
            bit = get_nibble(op2)
            annoText = "TST KR(" + str(bit) + ")"



        if op1 == "1010" and op2 == "0000" and op3 == "1100":
            annoText = "MOV KR,EXT"
        if op1 == "1010" and op2[3] == "0" and op3 == "0110":
            annoText = "MOV R5,FA"
        if op1 == "1010" and op2[3] == "1" and op3 == "0110":
            annoText = "MOV R5,FB"
        if op1 == "1010" and op3 == "0111":
            const = get_nibble(op2)
            annoText = "MOV R5,#" + str(const)
        if op1 == "1010" and op3 == "1000" and op2 == "0000":
            annoText = "MOV R5,KR"
        if op1 == "1010" and op3 == "1000" and op2 == "0001":
            annoText = "MOV KR,R5"

        # card reader
        if op1 == "1010" and op3 == "0010" and op2 == "1000":
            annoText = "IN CRD"
        if op1 == "1010" and op3 == "0011" and op2 == "1000":
            annoText = "OUT CRD"
        if op1 == "1010" and op2 == "0100" and op3 == "1000":
            annoText = "CRD_OFF"
        if op1 == "1010" and op2 == "0101" and op3 == "1000":
            annoText = "CRD_READ"

        # printer
        if op1 == "1010" and op3 == "1000" and op2 == "0110":
            annoText = "OUT PRT"
        if op1 == "1010" and op3 == "1000" and op2 == "0111":
            annoText = "OUT PRT_FUNC"
        if op1 == "1010" and op2 == "1000" and op3 == "1000":
            annoText = "PRT_CLEAR"
        if op1 == "1010" and op3 == "1000" and op2 == "1001":
            annoText = "PRT_STEP"
        if op1 == "1010" and op3 == "1000" and op2 == "1010":
            annoText = "PRT_PRINT"
        if op1 == "1010" and op3 == "1000" and op2 == "1011":
            annoText = "PRT_FEED"
        if op1 == "1010" and op3 == "1000" and op2 == "1100":
            annoText = "PRT_WRITE"

        if op1 == "1010" and op2 == "1111" and op3 == "1000":
            annoText = "RAM_OP"
        if op1 == "1010" and op3 == "1001":
            annoText = "SET IDLE"
        if op1 == "1010" and op3 == "1010":
            annoText = "CLR FB"
        if op1 == "1010" and op3 == "1011":
            annoText = "TST BUSY"
        if op1 == "1010" and op3 == "1100":
            annoText = "MOV KR,EXT"
        if op1 == "1010" and op3 == "1101":
            annoText = "XCH KR,SR"
        if op1 == "1010" and op3 == "1110":
            annoText = "NO-OP"
        if op1 == "1010" and op2 == "0000" and op3 == "1110": # FETCH
            annoText = "IN LIB"
        if op1 == "1010" and op2 == "0001" and op3 == "1110": # "LOAD PC"
            annoText = "OUT LIB_PC"
        if op1 == "1010" and op2 == "0010" and op3 == "1110": # "UNLOAD PC"
            annoText = "IN LIB_PC"
        if op1 == "1010" and op2 == "0011" and op3 == "1110": # "FETCH HIGH"
            annoText = "IN LIB_HIGH"

        # register access
        if op1 == "1010" and op3 == "1111":
            register = get_register(op2[0:3])
            if op2[3] == "0":
                annoText = "REG WRITE(" + str(register) + ")"
            else:
                annoText = "REG READ " + str(register) + ")"

        if op1 == "1011" :
            annoText = ".MLSD5"
        if op1 == "1100" :
            annoText = ".MAEX"
        if op1 == "1101" :
            annoText = ".MLSD1"
        if op1 == "1110" :
            annoText = ".MMSD1"

        # ALU operations
        if op1 == "1111" :
            annoText = ".MAEX1"
            if op2 == "0000":
                if op3[0] == "0": annoText += " ADD _,A,#const"
            else:
                annoText += " SUB _,A,#const"
            op3part = op3[1:]
            if op3part == "000": annoText += " sum -> A"

        #if irgBits2 == "1 1001 1111 100 0":  # C1F8 TRIGGER WORD 58/59 "BRANCH 0N C -1F"
        #    annoText = "BRANCH 0N C -1F"

        return annoText