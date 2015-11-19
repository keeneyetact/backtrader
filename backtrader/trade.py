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

import itertools

from .import num2date
from .utils.py3 import range


class Trade(object):
    '''
    Keeps track of the life of an trade: size, price,
    commission (and value?)

    An trade starts at 0 can be increased and reduced and can
    be considered closed if it goes back to 0.

    The trade can be long (positive size) or short (negative size)

    An trade is not meant to be reversed (no support in the logic for it)

    Member Attributes:
      - ref: unique trade identifier
      - status (int): one of Created, Open, Closed
      - size (int): current size of the trade
      - price (float): current price of the trade
      - value (float): current value of the trade
      - commission (float): current accumulated commission
      - pnl (float): current profit and loss of the trade (gross pnl)
      - pnlcomm (float):
        current profit and loss of the trade minus commission (net pnl)
      - isclosed (bool):
        records if the last update closed (set size to null the trade
      - isopen (bool): records if any update has opened the trade
      - justopened (bool): if the trade was just opened
      - baropen (int): bar in which this trade was opened
      - dtopen (float): float coded datetime in which the trade was closed
        - Use method ``open_datetime`` to get a Python datetime.datetime
          or use the platform provided ``num2date`` method
      - barclose (int): bar in which this trade was closed
      - dtclose (float): float coded datetime in which the trade was closed
        - Use method ``close_datetime`` to get a Python datetime.datetime
          or use the platform provided ``num2date`` method
      - barlen (int): number of bars this trade was open
    '''
    refbasis = itertools.count(1)

    status_names = ['Created', 'Open', 'Closed']
    Created, Open, Closed = range(3)

    def __init__(self, data=None, tradeid=0,
                 size=0, price=0.0, value=0.0, commission=0.0):

        self.ref = next(self.refbasis)
        self.historyon = historyon
        self.data = data
        self.tradeid = tradeid
        self.size = size
        self.price = price
        self.value = value
        self.commission = commission

        self.pnl = 0.0
        self.pnlcomm = 0.0

        self.justopened = False
        self.isopen = False
        self.isclosed = False

        self.baropen = 0
        self.dtopen = 0.0
        self.barclose = 0
        self.dtclose = 0.0
        self.barlen = 0

        self.status = self.Created

    def __len__(self):
        '''Shows if the trade has a size/is open'''
        return self.size

    __bool__ = __len__

    __nonzero__ = __len__

    def open_datetime(self):
        '''Returns a datetime.datetime object with the datetime in which
        the trade was opened
        '''
        return num2date(self.dtopen)

    def close_datetime(self):
        '''Returns a datetime.datetime object with the datetime in which
        the trade was closed
        '''
        return num2date(self.dtclose)

    def update(self, size, price, value, commission, pnl, comminfo=None):
        '''
        Updates the current trade. The logic does not check if the
        trade is reversed, which is not conceptually supported by the
        object.

        If an update sets the size attribute to null, "closed" will be
        set to true

        Args:
            size (int): amount to update the order
                if size has the same sign as the current trade a
                position increase will happen
                if size has the opposite sign as current op size a
                reduction/close will happen

            price (float): always be positive to ensure consistency
            value (float): cost incurred in new size/price op
            commission (float): incurred commission in the new size/price op
        '''
        if not size:
            return  # empty update, skip all other calculations

        # Commission can only increase
        self.commission += commission

        # Update size and keep a reference for logic an calculations
        oldsize = self.size
        self.size += size  # size will carry the opposite sign if reducing

        # Check if it has been currently opened
        self.justopened = bool(not oldsize and size)

        if self.justopened:
            self.baropen = len(self.data)
            self.dtopen = self.data.datetime[0]
            self.long = self.size > 0

        # Any size means the trade was opened
        self.isopen = bool(self.size)

        # Update current trade length
        self.barlen = len(self.data) - self.baropen

        # record if the position was closed (set to null)
        self.isclosed = oldsize and not self.size

        # record last bar for the trade
        if self.isclosed:
            self.isopen = False
            self.barclose = len(self.data)
            self.dtclose = self.data.datetime[0]

            self.status = self.Closed
        elif self.isopen:
            self.status = self.Open

        if abs(self.size) > abs(oldsize):
            # position increased (be it positive or negative)
            # update the average price
            self.price = (oldsize * self.price + size * price) / self.size

        else:  # abs(self.size) < abs(oldsize)
            # position reduced/closed
            if comminfo:
                pnl = comminfo.profitandloss(-size, self.price, price)

            self.pnl += pnl
            self.pnlcomm = self.pnl - self.commission

        self.value = value
