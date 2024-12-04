##
## This file is part of the libsigrokdecode project.
##
## Copyright (C) 2014 Daniel Elstner <daniel.kitta@gmail.com>
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

'''
TI5x (TI59, TI58, TI58C) pocket calculator decoder

4 bit data bus, IDLE, EXT, IRG, PHI1.

'''

from .pd import Decoder
