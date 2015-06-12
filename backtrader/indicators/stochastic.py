#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
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
###############################################################################
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

from .. import Indicator
from .ma import MovAv
from .miscops import Highest, Lowest


class _StochasticBase(Indicator):
    lines = ('percK', 'percD',)
    params = (('period', 14), ('period_dfast', 3), ('movav', MovAv.Simple),
              ('upperband', 80.0), ('lowerband', 20.0),)

    plotlines = dict(d=dict(ls='--'))

    def _plotlabel(self):
        plabels = [self.p.period, self.p.period_dfast]
        plabels += [self.p.movav] * self.p.notdefault('movav')
        return plabels

    def __init__(self):
        self.plotinfo.plotyhlines = [self.p.upperband, self.p.lowerband]

        highesthigh = Highest(self.data.high, period=self.p.period)
        lowestlow = Lowest(self.data.low, period=self.p.period)
        knum = self.data.close - lowestlow
        kden = highesthigh - lowestlow
        self.k = 100.0 * (knum / kden)
        self.d = self.p.movav(self.k, period=self.p.period_dfast)


class StochasticFast(_StochasticBase):
    '''StochasticFast

    By Dr. George Lane in the 50s. It compares a closing price to the price
    range and tries to show convergence if the closing prices are close to the
    extremes

      - It will go up if closing prices are close to the highs
      - It will roughly go down if closing prices are close to the lows

    It shows divergence if the extremes keep on growign but closing prices
    do not in the same manner (distance to the extremes grow)

    Formula:
      - hh = highest(data.high, period)
      - ll = lowest(data.low, period)
      - knum = data.close - ll
      - kden = hh - ll
      - k = 100 - (knum / kden)
      - d = MovingAverage(k, period_dfast)

    See:
      - http://en.wikipedia.org/wiki/Stochastic_oscillator

    Lines:
      - percK
      - percD

    Params:
      - period (14): period for the indicator
      - period_dfast (3): smoothing period for the percD average
      - movav (Simple): moving average to apply
      - upperband (80): indication line of overbought territory
      - lowerband (20): indication line of oversold territory
    '''
    def __init__(self):
        super(StochasticFast, self).__init__()
        self.lines.percK = self.k
        self.lines.percD = self.d


class Stochastic(_StochasticBase):
    '''Stochastic (alias StochasticSlow)

    The regular (or slow version) adds an additional moving average layer and
    thus:

      - The percD line of the StochasticFast becomes the percK line
      - percD becomes a  moving average of period_dslow of the original percD

    Formula:
      - k = k
      - d = d
      - d = MovingAverage(d, period_dslow)

    See:
      - http://en.wikipedia.org/wiki/Stochastic_oscillator

    Lines:
      - percK
      - percD

    Params:
      - period (14): period for the indicator
      - period_dfast (3): smoothing period for the percD average
      - period_dslow (3): additional smoothing period for the percD average
      - movav (Simple): moving average to apply
      - upperband (80): indication line of overbought territory
      - lowerband (20): indication line of oversold territory
    '''
    params = (('period_dslow', 3),)

    def _plotlabel(self):
        plabels = [self.p.period, self.p.period_dfast, self.p.period_dslow]
        plabels += [self.p.movav] * self.p.notdefault('movav')
        return plabels

    def __init__(self):
        super(Stochastic, self).__init__()
        self.lines.percK = self.d
        self.l.percD = self.p.movav(self.l.percK, period=self.p.period_dslow)


class StochasticSlow(Stochastic):
    pass


class StochasticFull(_StochasticBase):
    '''StochasticFull

    This version displays the 3 possible lines:

      - percK
      - percD
      - percSlow

    Formula:
      - k = d
      - d = MovingAverage(k, period_dslow)
      - dslow =

    See:
      - http://en.wikipedia.org/wiki/Stochastic_oscillator

    Lines:
      - percK
      - percD
      - percDSlow

    Params:
      - period (14): period for the indicator
      - period_dfast (3): smoothing period for the percD average
      - period_dslow (3): additional smoothing period for the percD average
      - movav (Simple): moving average to apply
      - upperband (80): indication line of overbought territory
      - lowerband (20): indication line of oversold territory
    '''
    lines = ('percDSlow',)
    params = (('period_dslow', 3),)

    def _plotlabel(self):
        plabels = [self.p.period, self.p.period_dfast, self.p.period_dslow]
        plabels += [self.p.movav] * self.p.notdefault('movav')
        return plabels

    def __init__(self):
        super(StochasticFull, self).__init__()
        self.lines.percK = self.k
        self.lines.percD = self.d
        self.l.percDSlow = self.p.movav(
            self.l.percD, period=self.p.period_dslow)
