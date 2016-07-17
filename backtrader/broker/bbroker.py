#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015, 2016 Daniel Rodriguez
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

from backtrader.comminfo import CommInfoBase
from backtrader.metabase import MetaParams
from backtrader.order import Order, BuyOrder, SellOrder
from backtrader.position import Position
from backtrader.utils.py3 import with_metaclass

__all__ = ['BrokerBase', 'BrokerBack']


class BrokerBase(with_metaclass(MetaParams, object)):
    params = (
        ('commission', CommInfoBase(percabs=True)),
    )

    def __init__(self):
        self.comminfo = dict()
        self.init()

    def init(self):
        # called from init and from start
        if None not in self.comminfo:
            self.comminfo = dict({None: self.p.commission})

    def start(self):
        self.init()

    def stop(self):
        pass

    def getcommissioninfo(self, data):
        if data._name in self.comminfo:
            return self.comminfo[data._name]

        return self.comminfo[None]

    def setcommission(self,
                      commission=0.0, margin=None, mult=1.0,
                      commtype=None, percabs=True, stocklike=False,
                      name=None):

        comm = CommInfoBase(commission=commission, margin=margin, mult=mult,
                            commtype=commtype, stocklike=stocklike,
                            percabs=percabs)
        self.comminfo[name] = comm

    def addcommissioninfo(self, comminfo, name=None):
        self.comminfo[name] = comminfo

    def getcash(self):
        raise NotImplementedError

    def getvalue(self, datas=None):
        raise NotImplementedError

    def getposition(self, data):
        raise NotImplementedError

    def submit(self, order):
        raise NotImplementedError

    def cancel(self, order):
        raise NotImplementedError

    def buy(self, owner, data, size, price=None, plimit=None, exectype=None,
            valid=None, tradeid=0, **kwargs):

        raise NotImplementedError

    def sell(self, owner, data, size, price=None, plimit=None, exectype=None,
             valid=None, tradeid=0, **kwargs):

        raise NotImplementedError

    def next(self):
        pass


class BrokerBack(BrokerBase):
    '''Broker Simulator

      The simulation supports different order types, checking a submitted order
      cash requirements against current cash, keeping track of cash and value
      for each iteration of ``cerebro`` and keeping the current position on
      different datas.

      *cash* is adjusted on each iteration for instruments like ``futures`` for
       which a price change implies in real brokers the addition/substracion of
       cash.

      Supported order types:

        - ``Market``: to be executed with the 1st tick of the next bar (namely
          the ``open`` price)

        - ``Close``: meant for intraday in which the order is executed with the
          closing price of the last bar of the session

        - ``Limit``: executes if the given limit price is seen during the
          session

        - ``Stop``: executes a ``Market`` order if the given stop price is seen

        - ``StopLimit``: sets a ``Limit`` order in motion if the given stop
          price is seen

      Because the broker is instantiated by ``Cerebro`` and there should be
      (mostly) no reason to replace the broker, the params are not controlled
      by the user for the instance.  To change this there are two options:

        1. Manually create an instance of this class with the desired params
           and use ``cerebro.broker = instance`` to set the instance as the
           broker for the ``run`` execution

        2. Use the ``set_xxx`` to set the value using
           ``cerebro.broker.set_xxx`` where ```xxx`` stands for the name of the
           parameter to set

        .. note:: ``cerebro.broker`` is a *property* supported by the
        ``getbroker`` and ``setbroker`` methods of ``Cerebro``

      Params:

        - ``cash`` (default: 10000): starting cash

        - ``commission`` (default: CommInfoBase(percabs=True))
          base commission scheme which applies to all assets

        - ``checksubmit`` (default: ``True``)
          check margin/cash before accepting an order into the system

        - ``eosbar`` (default: ``False``):
          With intraday bars consider a bar with the same ``time`` as the end
          of session to be the end of the session. This is not usually the
          case, because some bars (final auction) are produced by many
          exchanges for many products for a couple of minutes after the end of
          the session

        - ``eosbar`` (default: ``False``):
          With intraday bars consider a bar with the same ``time`` as the end
          of session to be the end of the session. This is not usually the
          case, because some bars (final auction) are produced by many
          exchanges for many products for a couple of minutes after the end of
          the session

        - ``filler`` (default: ``None``)

          A callable with signature: ``callable(order, price, ago)``

            - ``order``: obviously the order in execution. This provides access
              to the *data* (and with it the *ohlc* and *volume* values), the
              *execution type*, remaining size (``order.executed.remsize``) and
              others.

              Please check the ``Order`` documentation and reference for things
              available inside an ``Order`` instance

            - ``price`` the price at which the order is going to be executed in
              the ``ago`` bar

            - ``ago``: index meant to be used with ``order.data`` for the
              extraction of the *ohlc* and *volume* prices. In most cases this
              will be ``0`` but on a corner case for ``Close`` orders, this
              will be ``-1``.

              In order to get the bar volume (for example) do: ``volume =
              order.data.voluume[ago]``

          The callable must return the *executed size* (a value >= 0)

          The callable may of course be an object with ``__call__`` matching
          the aforementioned signature

          With the default ``None`` orders will be completely executed in a
          single shot
    '''
    params = (
        ('cash', 10000.0),
        ('checksubmit', True),
        ('eosbar', False),
        ('filler', None),
    )

    def init(self):
        super(BrokerBack, self).init()
        self.startingcash = self.cash = self.p.cash

        self.orders = list()  # will only be appending
        self.pending = collections.deque()  # popleft and append(right)

        self.positions = collections.defaultdict(Position)
        self.notifs = collections.deque()

        self.submitted = collections.deque()

    def get_notification(self):
        try:
            return self.notifs.popleft()
        except IndexError:
            pass

        return None

    def set_filler(self, filler):
        '''Sets a volume filler for volume filling execution'''
        self.p.filler = filler

    def set_checksubmit(self, checksubmit):
        '''Sets the checksubmit parameter'''
        self.p.checksubmit = checksubmit

    def set_eosbar(self, eosbar):
        '''Sets the eosbar parameter'''
        self.p.eosbar = eosbar

    seteosbar = set_eosbar

    def get_cash(self):
        '''Returns the current cash'''
        return self.cash

    getcash = get_cash

    def set_cash(self, cash):
        '''Sets the cash parameter'''
        self.startingcash = self.cash = self.p.cash = cash

    setcash = set_cash

    def cancel(self, order):
        try:
            self.pending.remove(order)
        except ValueError:
            # If the list didn't have the element we didn't cancel anything
            return False

        order.cancel()
        self.notify(order)
        return True

    def get_value(self, datas=None):
        '''Returns the portfolio value of the given datas (if datas is
        ``None``, then the total portfolio value will be returned'''
        pos_value = 0.0

        for data in datas or self.positions:
            comminfo = self.getcommissioninfo(data)
            position = self.positions[data]
            dvalue = comminfo.getvalue(position, data.close[0])
            if datas and len(datas) == 1:
                return dvalue  # raw data value requested, short selling is neg
            pos_value += abs(dvalue)  # short selling adds value

        return self.cash + pos_value

    getvalue = get_value

    def getposition(self, data):
        return self.positions[data]

    def orderstatus(self, order):
        try:
            o = self.orders.index(order)
        except ValueError:
            o = order

        return o.status

    def submit(self, order):
        if self.p.checksubmit:
            order.submit()
            self.submitted.append(order)
            self.orders.append(order)
            self.notify(order)
        else:
            self.submit_accept(order)

        return order

    def check_submitted(self):
        cash = self.cash
        positions = dict()

        while self.submitted:
            order = self.submitted.popleft()
            comminfo = self.getcommissioninfo(order.data)

            position = positions.setdefault(
                order.data, self.positions[order.data].clone())

            # pseudo-execute the order to get the remaining cash after exec
            cash = self._execute(order, cash=cash, position=position)

            if cash >= 0.0:
                self.submit_accept(order)
                continue

            order.margin()
            self.notify(order)

    def submit_accept(self, order):
        order.pannotated = None
        order.accept()
        self.pending.append(order)
        self.notify(order)

    def buy(self, owner, data,
            size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0,
            **kwargs):

        order = BuyOrder(owner=owner, data=data,
                         size=size, price=price, pricelimit=plimit,
                         exectype=exectype, valid=valid, tradeid=tradeid)

        order.addinfo(**kwargs)

        return self.submit(order)

    def sell(self, owner, data,
             size, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0,
             **kwargs):

        order = SellOrder(owner=owner, data=data,
                          size=size, price=price, pricelimit=plimit,
                          exectype=exectype, valid=valid, tradeid=tradeid)

        order.addinfo(**kwargs)

        return self.submit(order)

    def _execute(self, order, ago=None, price=None, cash=None, position=None):
        if self.p.filler is None or ago is None:
            # Order gets full size or pseudo-execution
            size = order.executed.remsize
        else:
            # Execution depends on volume filler
            size = self.p.filler(order, price, ago)
            if not order.isbuy():
                size = -size

        # Get comminfo object for the data
        comminfo = self.getcommissioninfo(order.data)

        # Adjust position with operation size
        if ago is not None:
            # Real execution with date
            position = self.positions[order.data]
            pprice_orig = position.price

            psize, pprice, opened, closed = position.pseudoupdate(size, price)

            # if part/all of a position has been closed, then there has been
            # a profitandloss ... record it
            pnl = comminfo.profitandloss(-closed, pprice_orig, price)
            cash = self.cash
        else:
            pnl = 0
            price = pprice_orig = order.created.price
            psize, pprice, opened, closed = position.update(size, price)

        # "Closing" totally or partially is possible. Cash may be re-injected
        if closed:
            # Adjust to returned value for closed items & acquired opened items
            closedvalue = comminfo.getoperationcost(closed, pprice_orig)
            cash += closedvalue + pnl * comminfo.stocklike
            # Calculate and substract commission
            closedcomm = comminfo.getcommission(closed, price)
            cash -= closedcomm

            if ago is not None:
                # Cashadjust closed contracts: prev close vs exec price
                # The operation can inject or take cash out
                cash += comminfo.cashadjust(-closed,
                                            position.adjbase,
                                            price)

                # Update system cash
                self.cash = cash
        else:
            closedvalue = closedcomm = 0.0

        popened = opened
        if opened:
            openedvalue = comminfo.getoperationcost(opened, price)
            cash -= openedvalue

            openedcomm = comminfo.getcommission(opened, price)
            cash -= openedcomm

            if cash < 0.0:
                # execution is not possible - nullify
                opened = 0
                openedvalue = openedcomm = 0.0

            elif ago is not None:  # real execution
                if abs(psize) > abs(opened):
                    # some futures were opened - adjust the cash of the
                    # previously existing futures to the operation price and
                    # use that as new adjustment base, because it already is
                    # for the new futures At the end of the cycle the
                    # adjustment to the close price will be done for all open
                    # futures from a common base price with regards to the
                    # close price
                    adjsize = psize - opened
                    cash += comminfo.cashadjust(adjsize,
                                                position.adjbase, price)

                # record adjust price base for end of bar cash adjustment
                position.adjbase = price

                # update system cash - checking if opened is still != 0
                self.cash = cash
        else:
            openedvalue = openedcomm = 0.0

        if ago is None:
            # return cash from pseudo-execution
            return cash

        execsize = closed + opened

        if execsize:
            # Confimrm the operation to the comminfo object
            comminfo.confirmexec(execsize, price)

            # do a real position update if something was executed
            position.update(execsize, price)

            # Execute and notify the order
            order.execute(order.data.datetime[ago],
                          execsize, price,
                          closed, closedvalue, closedcomm,
                          opened, openedvalue, openedcomm,
                          comminfo.margin, pnl,
                          psize, pprice)

            order.addcomminfo(comminfo)

            self.notify(order)

        if popened and not opened:
            # opened was not executed - not enough cash
            order.margin()
            self.notify(order)

    def notify(self, order):
        self.notifs.append(order.clone())

    def _try_exec_close(self, order, pclose):
        if len(order.data) > order.plen:
            dt0 = order.data.datetime[0]

            if dt0 > order.dteos or (self.p.eosbar and dt0 == order.dteos):
                # past the end of session or right at it and eosbar is True
                if order.pannotated and dt0 != order.dteos:
                    ago = -1
                    execprice = order.pannotated
                else:
                    ago = 0
                    execprice = pclose

                self._execute(order, ago=0, price=execprice)

                return

        # If no exexcution has taken place ... annotate the closing price
        order.pannotated = pclose

    def _try_exec_limit(self, order, popen, phigh, plow, plimit):
        if order.isbuy():
            if plimit >= popen:
                # open smaller/equal than requested - buy cheaper
                self._execute(order, ago=0, price=popen)
            elif plimit >= plow:
                # day low below req price ... match limit price
                self._execute(order, ago=0, price=plimit)

        else:  # Sell
            if plimit <= popen:
                # open greater/equal than requested - sell more expensive
                self._execute(order, ago=0, price=popen)
            elif plimit <= phigh:
                # day high above req price ... match limit price
                self._execute(order, ago=0, price=plimit)

    def _try_exec_stop(self, order, popen, phigh, plow, pcreated):
        if order.isbuy():
            if popen >= pcreated:
                # price penetrated with an open gap - use open
                self._execute(order, ago=0, price=popen)
            elif phigh >= pcreated:
                # price penetrated during the session - use trigger price
                self._execute(order, ago=0, price=pcreated)

        else:  # Sell
            if popen <= pcreated:
                # price penetrated with an open gap - use open
                self._execute(order, ago=0, price=popen)
            elif plow <= pcreated:
                # price penetrated during the session - use trigger price
                self._execute(order, ago=0, price=pcreated)

    def _try_exec_stoplimit(self, order,
                            popen, phigh, plow, pclose,
                            pcreated, plimit):
        if order.isbuy():
            if popen >= pcreated:
                order.triggered = True
                # price penetrated with an open gap
                if plimit >= popen:
                    self._execute(order, ago=0, price=popen)
                elif plimit >= plow:
                    # execute in same bar
                    self._execute(order, ago=0, price=plimit)

            elif phigh >= pcreated:
                # price penetrated upwards during the session
                order.triggered = True
                # can calculate execution for a few cases - datetime is fixed
                if popen > pclose:
                    if plimit >= pcreated:
                        self._execute(order, ago=0, price=pcreated)
                    elif plimit >= pclose:
                        self._execute(order, ago=0, price=plimit)
                else:  # popen < pclose
                    if plimit >= pcreated:
                        self._execute(order, ago=0, price=pcreated)
        else:  # Sell
            if popen <= pcreated:
                # price penetrated downwards with an open gap
                order.triggered = True
                if plimit <= popen:
                    self._execute(order, ago=0, price=popen)
                elif plimit <= phigh:
                    # execute in same bar
                    self._execute(order, ago=0, price=plimit)

            elif plow <= pcreated:
                # price penetrated downwards during the session
                order.triggered = True
                # can calculate execution for a few cases - datetime is fixed
                if popen <= pclose:
                    if plimit <= pcreated:
                        self._execute(order, ago=0, price=pcreated)
                    elif plimit <= pclose:
                        self._execute(order, ago=0, price=plimit)
                else:
                    # popen > pclose
                    if plimit <= pcreated:
                        self._execute(order, ago=0, price=pcreated)

    def _try_exec(self, order):
        data = order.data

        popen = data.tick_open or data.open[0]
        phigh = data.tick_high or data.high[0]
        plow = data.tick_low or data.low[0]
        pclose = data.tick_close or data.close[0]

        pcreated = order.created.price
        plimit = order.created.pricelimit

        if order.exectype == Order.Market:
            self._execute(order, ago=0, price=popen)

        elif order.exectype == Order.Close:
            self._try_exec_close(order, pclose)

        elif order.exectype == Order.Limit:
            self._try_exec_limit(order, popen, phigh, plow, pcreated)

        elif order.exectype == Order.StopLimit and order.triggered:
            self._try_exec_limit(order, popen, phigh, plow, plimit)

        elif order.exectype == Order.Stop:
            self._try_exec_stop(order, popen, phigh, plow, pcreated)

        elif order.exectype == Order.StopLimit:
            self._try_exec_stoplimit(order,
                                     popen, phigh, plow, pclose,
                                     pcreated, plimit)

    def next(self):
        if self.p.checksubmit:
            self.check_submitted()

        # Iterate once over all elements of the pending queue
        for i in range(len(self.pending)):

            order = self.pending.popleft()

            if order.expire():
                self.notify(order)
                continue

            self._try_exec(order)

            if order.alive():
                self.pending.append(order)

        # Operations have been executed ... adjust cash end of bar
        for data, pos in self.positions.items():
            # futures change cash every bar
            if pos:
                comminfo = self.getcommissioninfo(data)
                self.cash += comminfo.cashadjust(pos.size,
                                                 pos.adjbase,
                                                 data.close[0])
                # record the last adjustment price
                pos.adjbase = data.close[0]
