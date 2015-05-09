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

import collections

import six

from .comminfo import CommissionInfo
from .datapos import Position
from .metabase import MetaParams
from .order import Order, BuyOrder, SellOrder


class BrokerBack(six.with_metaclass(MetaParams, object)):

    params = (('cash', 10000.0), ('commission', CommissionInfo()),)

    def __init__(self):
        self.comminfo = dict()

    def getcash(self):
        return self.cash

    def setcash(self, cash):
        self.startingcash = self.p.cash = cash

    def getcommissioninfo(self, data):
        if data._name in self.comminfo:
            return self.comminfo[data._name]

        return self.comminfo[None]

    def setcommission(self, commission=0.0, margin=None, mult=1.0, name=None):
        self.comminfo[name] = CommissionInfo(commission=commission,
                                             margin=margin,
                                             mult=mult)

    def addcommissioninfo(self, comminfo, name=None):
        self.comminfo[name] = comminfo

    def start(self):
        if None not in self.comminfo.keys():
            self.comminfo = dict({None: self.p.commission})

        self.startingcash = self.cash = self.p.cash

        self.orders = list()  # will only be appending
        self.pending = collections.deque()  # popleft and append(right)

        self.positions = collections.defaultdict(Position)
        self.notifs = collections.deque()

    def stop(self):
        pass

    def cancel(self, order):
        try:
            self.pending.remove(order)
        except ValueError:
            # If the list didn't have the element we didn't cancel anything
            return False

        order.cancel()
        self.notify(order)
        return True

    def getvalue(self, datas=None):
        pos_value = 0.0
        for data in datas or self.positions.keys():
            comminfo = self.getcommissioninfo(data)
            position = self.positions[data]
            pos_value += comminfo.getvalue(position, data.close[0])

        return self.cash + pos_value

    def getposition(self, data):
        return self.positions[data]

    def submit(self, order):
        # FIXME: When an order is submitted, a margin check
        # requirement has to be done before it can be accepted. This implies
        # going over the entire list of pending orders for all datas and
        # existing positions, simulating order execution and ending up
        # with a "cash" figure that can be used to check the margin requirement
        # of the order. If not met, the order can be immediately rejected
        order.accept()
        self.orders.append(order)
        self.pending.append(order)
        return order

    def buy(self, owner, data, size, price=None, exectype=None, valid=None):
        order = BuyOrder(owner=owner, data=data, size=size,
                         price=price, exectype=exectype, valid=valid)
        return self.submit(order)

    def sell(self, owner, data, size, price=None, exectype=None, valid=None):
        order = SellOrder(owner=owner, data=data, size=size,
                          price=price, exectype=exectype, valid=valid)
        return self.submit(order)

    def _execute(self, order, dt, price):
        # Orders are fully executed, get operation size
        size = order.executed.remsize

        # Adjust position with operation size
        position = self.positions[order.data]
        psize, pprice, opened, closed = position.update(size, price)
        abopened, abclosed = abs(opened), abs(closed)

        # Get comminfo object for the data
        comminfo = self.getcommissioninfo(order.data)

        if closed:
            # Adjust to returned value for closed items & acquired opened items
            closedvalue = comminfo.getoperationcost(abclosed, price)
            self.cash += closedvalue
            # Calculate and substract commission
            closedcomm = comminfo.getcomm_pricesize(abclosed, price)
            self.cash -= closedcomm
            # Re-adjust cash according to future-like movements
            # Restore cash which was already taken at the start of the day
            self.cash -= comminfo.cashadjust(abclosed,
                                             price,
                                             order.data.close[0])
        else:
            closedvalue = closedcomm = 0.0

        if opened:
            openedvalue = comminfo.getoperationcost(abopened, price)
            self.cash -= openedvalue

            openedcomm = comminfo.getcomm_pricesize(abopened, price)
            self.cash -= openedcomm

            # Remove cash for the new opened contracts
            self.cash += comminfo.cashadjust(abopened,
                                             price,
                                             order.data.close[0])
        else:
            openedvalue = openedcomm = 0.0

        # Execute and notify the order
        order.execute(dt, size, price,
                      closed, closedvalue, closedcomm,
                      opened, openedvalue, openedcomm,
                      comminfo.margin, psize, pprice)

        self.notify(order)

    def notify(self, order):
        self.notifs.append(order)

    def next(self):
        for data, pos in self.positions.items():
            # futures change cash in the broker in every bar
            # to ensure margin requirements are met
            comminfo = self.getcommissioninfo(data)
            self.cash += comminfo.cashadjust(pos.size,
                                             data.close[-1],
                                             data.close[0])

        # Iterate once over all elements of the pending queue
        for i in range(len(self.pending)):
            order = self.pending.popleft()

            if order.expire():
                self.notify(order)
                continue

            plow = order.data.low[0]
            phigh = order.data.high[0]
            popen = order.data.open[0]
            pclose = order.data.close[0]
            pclose1 = order.data.close[-1]
            pcreated = order.created.price
            plimit = order.created.pricelimit

            if order.exectype == Order.Market:
                self._execute(order, order.data.datetime[0], price=popen)

            elif order.exectype == Order.Close:
                self._try_exec_close(order, price, pclose1)

            elif order.exectype == Order.Limit:
                self._try_exec_limit(order, popen, plimit)

            elif order.exectype == Order.StopLimit and order.triggered:
                self._try_exec_limit(order, popen, plimit)

            elif order.exectype == Order.Stop:
                self._try_exec_limit(order, popen, pcreated)

            elif order.exectype == Order.StopLimit:
                self._try_exec_stoplimit(order,
                                         popen, phigh, plow, pclose,
                                         pcreated, plimit)

            if order.alive():
                self.pending.append(order)

    def _try_exec_close(self, order, pclose):
        if order.data.datetime.time(0) != order.data.datetime.time(-1):
            # intraday: time changes in between bars
            self._execute(order, order.data.datetime[-1], price=pclose)
        elif order.data.datetime.date(0) != order.data.datetime.date(-1):
            # daily: time is equal, date changes
            self._execute(order, order.data.datetime[-1], price=p)

    def _try_exec_limit(self, order, popen, plimit):
        if isinstance(order, BuyOrder):
            if plimit >= popen:
                # open smaller/equal than requested - buy cheaper
                self._execute(order, order.data.datetime[0], price=popen)
            elif plimit >= plow:
                # day low below req price ... match limit price
                self._execute(order, order.data.datetime[0], price=plimit)

        else:  # Sell
            if plimit <= popen:
                # open greater/equal than requested - sell more expensive
                self._execute(order, order.data.datetime[0], price=popen)
            elif plimit <= phigh:
                # day high above req price ... match limit price
                self._execute(order, order.data.datetime[0], price=plimit)

    def _try_exec_stop(self, order, popen, pcreated):
        if isinstance(order, BuyOrder):
            if popen >= pcreated:
                # price penetrated with an open gap - use open
                self._execute(order, order.data.datetime[0], price=popen)
            elif phigh >= pcreated:
                # price penetrated during the session - use trigger price
                self._execute(order, order.data.datetime[0], price=pcreated)

        else:  # Sell
            if popen <= pcreated:
                # price penetrated with an open gap - use open
                self._execute(order, order.data.datetime[0], price=popen)
            elif plow <= pcreated:
                # price penetrated during the session - use trigger price
                self._execute(order, order.data.datetime[0], price=pcreated)

    def _try_exec_stoplimit(self, order,
                            popen, phigh, plow, pclose,
                            pcreated, plimit):
        if isinstance(order, BuyOrder):
            if popen >= pcreated:
                order.triggered = True
                # price penetrated with an open gap
                if plimit >= popen:
                    self._execute(order, order.data.datetime[0], price=popen)
                elif plimit >= plow:
                    # execute in same bar
                    self._execute(order, order.data.datetime[0], price=plimit)

            elif phigh >= pcreated:
                # price penetrated upwards during the session
                order.triggered = True
                # can calculate execution for a few cases - datetime is fixed
                dt = order.data.datetime[0]
                if popen > pclose:
                    if plimit >= pcreated:
                        self._execute(order, dt0, price=pcreated)
                    elif plimit >= pclose:
                        self._execute(order, dt0, price=plimit)
                else:  # popen < pclose
                    if plimit >= pcreated:
                        self._execute(order, dt0, price=pcreated)
        else:  # Sell
            if popen <= pcreated:
                # price penetrated downwards with an open gap
                order.triggered = True
                if plimit <= open:
                    self._execute(order, order.data.datetime[0], price=popen)
                elif plimit <= phigh:
                    # execute in same bar
                    self._execute(order, order.data.datetime[0], price=plimit)

            elif plow <= pcreated:
                # price penetrated downwards during the session
                order.triggered = True
                # can calculate execution for a few cases - datetime is fixed
                dt = order.data.datetime[0]
                if popen <= pclose:
                    if plimit <= pcreated:
                        self._execute(order, dt0, price=pcreated)
                    elif plimit <= pclose:
                        self._execute(order, dt0, price=plimit)
                else:
                    # popen > pclose
                    if plimit <= pcreated:
                        self._execute(order, dt0, price=pcreated)
