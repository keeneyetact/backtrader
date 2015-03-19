#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
################################################################################
#
# Copyright (C) 2015 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
################################################################################

from __future__ import absolute_import, division, print_function, unicode_literals

from six.moves import xrange

from .. import DataSeries, Indicator
from .ma import MATypes


class TrueRange(Indicator):
    lines = ('tr',)

    def __init__(self):
        self.data_high = self.datas[0].lines[DataSeries.High]
        self.data_low = self.datas[0].lines[DataSeries.Low]
        self.data_close = self.datas[0].lines[DataSeries.Close]

    def nextstart(self):
        th = self.data_high[0]
        tl = self.data_low[0]

        self.lines[0][0] = th - tl

    def next(self):
        th = self.data_high[0]
        tl = self.data_low[0]
        yc = self.data_close[-1]

        self.lines[0][0] = max(th - tl, abs(yc - th), abs(yc - tl))

    def once(self, start, end):
        dharray = self.data_high.array
        dlarray= self.data_low.array
        dcarray = self.data_close.array
        larray = self.lines[0].array

        th = dharray[start]
        tl = dlarray[start]
        larray[start] = th - tl

        for i in xrange(start + 1, end):
            th = dharray[i]
            tl = dlarray[i]
            yc = dcarray[i - 1]

            larray[i] = max(th - tl, abs(yc - th), abs(yc - tl))


class AverageTrueRange(Indicator):
    lines = ('atr',)
    params = (('period', 14), ('matype', MATypes.Simple))

    def _plotlabel(self):
        return str(self.params.period)

    plotinfo = dict(plotname='ATR')

    def __init__(self):
        tr = TrueRange(self.datas[0])
        self.params.matype(tr, period=self.params.period).bindlines()


ATR = AverageTrueRange
