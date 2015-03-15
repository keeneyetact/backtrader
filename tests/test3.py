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

import testbase

import datetime
import os.path
import time
import sys

import backtrader as bt
import backtrader.feeds as btfeeds
import backtrader.indicators as btind


class TestStrategy(bt.Strategy):
    params = (
        ('maperiod', 15),
        ('stake', 10),
        ('exectype', bt.Order.Market),
        ('atlimitperc', 1.0),
        ('expiredays', 10),
        ('printdata', True),
    )

    def log(self, txt, dt=None):
        dt = dt or self.data.datetime[0]
        print('%s, %s' % (dt.isoformat(), txt))

    def __init__(self):
        self.data = self.datas[0]
        self.dataclose = self.data.close
        self.sma = btind.MovingAverageSimple(self.data, period=self.params.maperiod)
        self.orderid = None
        self.expiry = datetime.timedelta(days=self.params.expiredays)
        btind.ATR(self.data)
        btind.MACDHistogram(self.data)
        btind.Stochastic(self.data)
        btind.RSI(self.data)
        btind.MovingAverageExponential(self.data, period=int(0.8 * self.params.maperiod))
        btind.MovingAverageSmoothed(self.data, period=int(1.2 * self.params.maperiod))
        btind.MovingAverageWeighted(self.data, period=int(1.5 * self.params.maperiod))

        self.sizer = bt.SizerFix(stake=self.params.stake)

    def start(self):
        self.tstart = time.clock()

    def notify(self, order):
        if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
            return # Await further notifications

        if order.status == bt.Order.Completed:
            if isinstance(order, bt.BuyOrder):
                self.log('BUY , %.2f' % order.executed.price, order.executed.dt)
            else: # elif isinstance(order, SellOrder):
                self.log('SELL , %.2f' % order.executed.price, order.executed.dt)
        elif order.status in [order.Expired, order.Canceled, order.Margin]:
            self.log('%s ,' % order.Status[order.status])
            pass # Do nothing for expired orders

        # Allow new orders
        self.orderid = None

    def next(self):
        if self.params.printdata:
            self.log(
                'Open, High, Low, Close, %.2f, %.2f, %.2f, %.2f, Sma, %f' %
                (self.data.open[0], self.data.high[0], self.data.low[0], self.dataclose[0], self.sma[0][0])
            )

        if self.orderid:
            return # if an order is active, no new orders are allowed

        if not self.position.size:
            if self.dataclose[0] > self.sma[0][0]:
                valid = self.data.datetime[0] + self.expiry
                price = self.dataclose[0]
                if self.params.exectype == bt.Order.Limit:
                    price *= self.params.atlimitperc
                self.log('BUY CREATE , %.2f' % price)
                self.orderid = self.buy(exectype=self.params.exectype, price=price, valid=valid)

        elif self.dataclose[0] < self.sma[0][0]:
            self.log('SELL CREATE , %.2f' % self.dataclose[0])
            self.orderid = self.sell(exectype=bt.Order.Market)

    def stop(self):
        tused = time.clock() - self.tstart
        print('Time used:', str(tused))
        print('Final portfolio value: %.2f' % self.broker.getvalue())


cerebro = bt.Cerebro()

# The datas are in a subdirectory of the samples. Need to find where the script is
# because it could have been called from anywhere
modpath = os.path.dirname(os.path.abspath(sys.argv[0]))
datapath = os.path.join(modpath, '../samples/datas/yahoo/oracle-1995-2014.csv')
data = bt.feeds.YahooFinanceCSVData(
    dataname=datapath,
    reversed=True,
    fromdate=datetime.datetime(2000, 1, 1),
    todate=datetime.datetime(2000, 12, 31)
)

cerebro.adddata(data)

cerebro.broker.setcash(1000.0)
cerebro.addstrategy(TestStrategy,
                    printdata=False,
                    maperiod=15,
                    exectype=bt.Order.Market,
                    atlimitperc=0.80,
                    expiredays=7)
cerebro.run()
cerebro.plot()
