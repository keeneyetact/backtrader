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
import itertools
import operator

import six

from .broker import BrokerBack
from .lineiterator import LineIterator, StrategyBase
from .sizer import SizerFix
from .trade import Trade


class _Template(object):

    def __init__(self):
        self.members = list()
        self.names = list()

    def __len__(self):
        return len(self.members)

    def addmember(self, name, member):
        setattr(self, name, member)
        self.members.append(member)
        self.names.append(name)

    def __getitem__(self, key):
        return self.members[key]

    def getitems(self):
        return zip(self.names, self.members)


class MetaStrategy(StrategyBase.__class__):
    def __new__(meta, name, bases, dct):
        # Hack to support original method name for notify_order
        if 'notify' in dct:
            # rename 'notify' to 'notify_order'
            dct['notify_order'] = dct.pop('notify')
        if 'notify_operation' in dct:
            # rename 'notify' to 'notify_order'
            dct['notify_trade'] = dct.pop('notify_operation')

        return super(MetaStrategy, meta).__new__(meta, name, bases, dct)

    def dopreinit(cls, _obj, env, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaStrategy, cls).dopreinit(_obj, *args, **kwargs)
        _obj.env = env
        _obj.broker = env.broker
        _obj._sizer = SizerFix()
        _obj._orders = list()
        _obj._orderspending = list()
        _obj._trades = collections.defaultdict(list)
        _obj._tradespending = list()

        _obj.stats = _Template()
        _obj.analyzers = _Template()

        return _obj, args, kwargs

    def dopostinit(cls, _obj, *args, **kwargs):
        _obj, args, kwargs = \
            super(MetaStrategy, cls).dopostinit(_obj, *args, **kwargs)

        dataids = [id(data) for data in _obj.datas]

        _dminperiods = collections.defaultdict(list)
        for lineiter in _obj._lineiterators[LineIterator.IndType]:
            # if multiple datas are used and multiple timeframes the larger
            # timeframe may place larger time constraints in calling next.
            clk = getattr(lineiter, '_clock', None)
            if clk is None:
                clk = getattr(lineiter._owner, '_clock', None)
                if clk is None:
                    continue

            while True:
                if id(clk) in dataids:
                    break

                clk2 = getattr(clk, '._clock', None)
                if clk2 is None:
                    clk2 = getattr(clk._owner, '._clock', None)

                clk = clk2
                if clk is None:
                    break

            if clk is None:
                continue

            _dminperiods[clk].append(lineiter._minperiod)

        _obj._minperiods = list()
        for data in _obj.datas:
            dminperiod = max(_dminperiods[data] or [_obj._minperiod])
            _obj._minperiods.append(dminperiod)

        # Set the minperiod
        minperiods = \
            [x._minperiod for x in _obj._lineiterators[LineIterator.IndType]]
        _obj._minperiod = max(minperiods or [_obj._minperiod])

        if not _obj._sizer.getbroker():
            _obj._sizer.setbroker(_obj.broker)

        # change operators to stage 2
        _obj._stage2()

        return _obj, args, kwargs


class Strategy(six.with_metaclass(MetaStrategy, StrategyBase)):
    '''Based class to be subclassed for user defined strategies.

    Strategies are ``Lines`` objects but only an unnamed line is defined to
    ensure the strategy can be synchronized to the main data.

    Logic does usually involve Indicators. Indicators are defined in:

      - ``__init__``


    The class will:

      - Be notified through ``notify_order(order)`` of any status change in an
        order

      - Be notified through ``notify_trade(trade)`` of any
        opening/updating/closing trade

      - Have its methods ``prenext``, ``nextstart`` and ``next`` invoked to
        execute the logic

    Bits:

      - A Strategy has a "length" which is always equal to that of the main
        data (datas[0])

        ``next`` can be called without changes in length if data is being
        replayed or a live feed is being passed and new ticks for the same
        point in time (length) are arriving

    Member Attributes:

      - ``env``: the cerebro entity in which this Strategy lives
      - ``datas``: array of datas which have been passed to cerebro

        - ``data/data0`` is an alias for datas[0]
        - ``dataX`` is an alias for datas[X]

      - ``broker``: reference to the broker associated to this strategy
        (received from cerebro)

      - stats: list/named tuple-like sequence holding the Observers created by
        cerebro for this strategy

      - analyzers: list/named tuple-like sequence holding the Analyzers created
        by cerebro for this strategy

    Member Attributes (meant for statistics/observers/analyzers):

      - ``_orderspending``: list of orders which will be notified to the
        strategy before ``next`` is called

      - ``_tradespending``: list of trades which will be notified to the
        strategy before ``next`` is called

      - ``_orders``: list of order which have been already notified. An order
        can be several times in the list with different statuses and different
        execution bits. The list is menat to keep the history.

      - ``_trades``: list of order which have been already notified. A trade
        can be several times in the list just like an order.

    User Methods (will be called):

      - ``prenext``: will be called before the minimum period of all
        datas/indicators have been meet for the strategy to start executing

      - ``nextstart``: will be called once, exactly when the minimum period for
        all datas/indicators have been meet. The default behavior is to call
        next

      - ``next``: will be called for all remaining data points when the minimum
        period for all datas/indicators have been meet.

      .. note::

        The 3 methods above can be called several times for the same point in
        time (ticks updating prices for the daily bar, when a daily timeframe
        is in use)

      - ``notify_order(order)``: receives an order whenever there has been a
        change in one

      - ``notify_trade(trade)``: receives a trade whenever there has been a
        change in once

      - ``start``: called right before the backtesting is about to be started

      - ``stop``: called right before the backtesting is about to be stopped

    User Methods (to be called):

      - buy(self, data=None, size=None,
            price=None, plimit=None,
            exectype=None, valid=None)

        To create a buy (long) order and send it to the broker

        Returns: the submitted order

      - sell(self, data=None, size=None,
            price=None, plimit=None,
            exectype=None, valid=None)

        To create a selll (short) order and send it to the broker

        Returns: the submitted order

      - close(data=None, size=None, price=None, exectype=None, valid=None)

        Counters a long/short position closing it

        Returns: the submitted order

      - broker.cancel(order)

        (indirect call through broker)

        Tries to cnacel an order (it may have been executed before the call
        succeeds)

        Returns: bool with status of request

      - sizer/getsizer()

        Returns the sizer which is in used if automatic statke calculation is
        used

      - setsizer(sizer)

        Replace the default (fixed statke) sizer

      - getsizing(data=None))

        Return the stake calculated by the sizer instance for the current
        situation

      - position/getposition(data=None, broker=None)

        Return the current position for a given data in a given broker. If both
        are None, the main data and the default broker will be used
    '''

    _ltype = LineIterator.StratType

    # This unnamed line is meant to allow having "len" and "forwarding"
    extralines = 1

    def _addanalyzer(self, ancls, *anargs, **ankwargs):
        anname = ankwargs.pop('_name', '') or ancls.__name__.lower()
        analyzer = ancls(*anargs, **ankwargs)
        self.analyzers.addmember(anname, analyzer)

    def _addobserver(self, multi, obscls, *obsargs, **obskwargs):
        obsname = obskwargs.pop('obsname', '')
        if not obsname:
            obsname = obscls.__name__.lower()

        if not multi:
            newargs = list(itertools.chain(self.datas, obsargs))
            obs = obscls(*newargs, **obskwargs)
            self.stats.addmember(obsname, obs)
            return

        setattr(self.stats, obsname, list())
        l = getattr(self.stats, obsname)

        for data in self.datas:
            obs = obscls(data, *obsargs, **obskwargs)
            l.append(obs)

    def _oncepost(self):
        for indicator in self._lineiterators[LineIterator.IndType]:
            indicator.advance()

        self.advance()
        self._notify()

        # check the min period status connected to datas
        dlens = map(operator.sub, self._minperiods, map(len, self.datas))
        minperstatus = max(dlens)

        if minperstatus < 0:
            self.next()
        elif minperstatus == 0:
            self.nextstart()  # only called for the 1st value
        else:
            self.prenext()

        for observer in self._lineiterators[LineIterator.ObsType]:
            observer.advance()
            if minperstatus < 0:
                observer.next()
            elif minperstatus == 0:
                observer.nextstart()  # only called for the 1st value
            else:
                observer.prenext()

        for analyzer in self.analyzers:
            if minperstatus < 0:
                analyzer._next()
            elif minperstatus == 0:
                analyzer._nextstart()  # only called for the 1st value
            else:
                analyzer._prenext()

        self.clear()

    def _next(self):
        super(Strategy, self)._next()

        for analyzer in self.analyzers:
            analyzer._next()

        self.clear()

    def _start(self):
        for analyzer in self.analyzers:
            analyzer._start()

        self.start()

    def start(self):
        pass

    def _stop(self):
        for analyzer in self.analyzers:
            analyzer._stop()

        self.stop()

    def stop(self):
        pass

    def clear(self):
        self._orders.extend(self._orderspending)
        self._orderspending = list()

        self._tradespending = list()

    def _addnotification(self, order):
        self._orderspending.append(order)

        if not order.executed.size:
            return

        tradedata = order.data
        datatrades = self._trades[tradedata]
        if not datatrades:
            datatrades.append(Trade(data=tradedata))

        trade = datatrades[-1]

        for exbit in order.executed.exbits:
            trade.update(exbit.closed,
                         exbit.price,
                         exbit.closedvalue,
                         exbit.closedcomm,
                         exbit.pnl)

            if trade.isclosed:
                self._tradespending.append(trade)

                # Open the next trade
                trade = Trade(data=tradedata)
                datatrades.append(trade)

            # Update it if needed
            trade.update(exbit.opened,
                         exbit.price,
                         exbit.openedvalue,
                         exbit.openedcomm,
                         exbit.pnl)

            if trade.justopened:
                self._tradespending.append(trade)

    def _notify(self):
        for order in self._orderspending:
            self.notify_order(order)

        for trade in self._tradespending:
            self.notify_trade(trade)

    def notify_order(self, order):
        pass

    def notify_trade(self, trade):
        pass

    def buy(self, data=None,
            size=None, price=None, plimit=None,
            exectype=None, valid=None):

        data = data or self.datas[0]
        size = size or self.getsizing(data)

        return self.broker.buy(
            self, data,
            size=size, price=price, plimit=plimit,
            exectype=exectype, valid=valid)

    def sell(self, data=None,
             size=None, price=None, plimit=None,
             exectype=None, valid=None):

        data = data or self.datas[0]
        size = size or self.getsizing(data)

        return self.broker.sell(
            self, data,
            size=size, price=price, plimit=plimit,
            exectype=exectype, valid=valid)

    def close(self,
              data=None, size=None, price=None, exectype=None, valid=None):
        possize = self.getposition(data, self.broker).size
        size = abs(size or possize)

        if possize > 0:
            return self.sell(data, size, price, exectype, valid)
        elif possize < 0:
            return self.buy(data, size, price, exectype, valid)

        return None

    def getposition(self, data=None, broker=None):
        data = data or self.datas[0]
        return self.broker.getposition(data)

    position = property(getposition)

    def setsizer(self, sizer):
        self._sizer = sizer
        if not sizer.getbroker():
            sizer.setbroker(self.broker)
        return sizer

    def getsizer(self):
        return self._sizer

    sizer = property(getsizer, setsizer)

    def getsizing(self, data=None):
        data = data or self.datas[0]
        return self._sizer.getsizing(data)
