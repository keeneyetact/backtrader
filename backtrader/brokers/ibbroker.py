#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015,2016 Daniel Rodriguez
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
from copy import copy
from datetime import date, datetime, timedelta
import threading

import ib.ext.Order
import ib.opt as ibopt

from backtrader.feed import DataBase
from backtrader import (TimeFrame, num2date, date2num, BrokerBase,
                        Order, OrderBase, OrderData)
from backtrader.utils.py3 import bytes, with_metaclass, queue, MAXFLOAT
from backtrader.metabase import MetaParams
from backtrader.comminfo import CommInfoBase
from backtrader.position import Position
from backtrader.stores import ibstore
from backtrader.utils import AutoDict, AutoOrderedDict
from backtrader.comminfo import CommInfoBase


class IBOrder(OrderBase, ib.ext.Order.Order):
    '''Subclasses the IBPy order to provide the minimum extra functionality
    needed to be compatible with the internally defined orders

    Once ``OrderBase`` has processed the parameters, the __init__ method takes
    over to use the parameter values and set the appropriate values in the
    ib.ext.Order.Order object

    Any extra parameters supplied with kwargs are applied directly to the
    ib.ext.Order.Order object, which could be used as follows::

      Example: if the 4 order execution types directly supported by
      ``backtrader`` are not enough, in the case of for example
      *Interactive Brokers* the following could be passed as *kwargs*::

        orderType='LIT', lmtPrice=10.0, auxPrice=9.8

      This would override the settings created by ``backtrader`` and
      generate a ``LIMIT IF TOUCHED`` order with a *touched* price of 9.8
      and a *limit* price of 10.0.

    This would be done almost always from the ``Buy`` and ``Sell`` methods of
    the ``Strategy`` subclass being used in ``Cerebro``
    '''

    def __str__(self):
        '''Get the printout from the base class and add some ib.Order specific
        fields'''
        basetxt = super(IBOrder, self).__str__()
        tojoin = [basetxt]
        tojoin.append('Ref: {}'.format(self.ref))
        tojoin.append('orderId: {}'.format(self.m_orderId))
        tojoin.append('Action: {}'.format(self.m_action))
        tojoin.append('Size (ib): {}'.format(self.m_totalQuantity))
        tojoin.append('Lmt Price: {}'.format(self.m_lmtPrice))
        tojoin.append('Aux Price: {}'.format(self.m_auxPrice))
        tojoin.append('OrderType: {}'.format(self.m_orderType))
        tojoin.append('Tif (Time in Force): {}'.format(self.m_tif))
        tojoin.append('GoodTillDate: {}'.format(self.m_goodTillDate))
        return '\n'.join(tojoin)

    # Map backtrader order types to the ib specifics
    _OrdTypes = {
        None: bytes('MKT'),  # default
        Order.Market: bytes('MKT'),
        Order.Limit: bytes('LMT'),
        Order.Close: bytes('MOC'),
        Order.Stop: bytes('STP'),
        Order.StopLimit: bytes('STPLMT'),
    }

    def __init__(self, action, **kwargs):

        self.ordtype = self.Buy if action == 'BUY' else self.Sell
        super(IBOrder, self).__init__()

        # Simulate the "params" from the internal Order class and set them
        # before calling the OrderBase initialization
        if False:
            self.owner = owner
            self.data = data
            self.size = size
            self.tradeid = tradeid
            self.exectype = exectype
            self.price = price
            self.pricelimit = pricelimit
            self.tradeid = tradeid
            self.valid = valid

            OrderBase.__init__(self)  # call 2nd baseclass

        ib.ext.Order.Order.__init__(self)  # Invoke 2nd base class

        # Now fill in the specific IB parameters
        self.m_orderType = self._OrdTypes[self.exectype]
        self.m_permid = 0

        # 'B' or 'S' should be enough
        self.m_action = bytes(action)

        # Set the prices
        self.m_lmtPrice = 0.0
        self.m_auxPrice = 0.0

        if self.exectype == self.Market:  # is it really needed for Market?
            pass
        elif self.exectype == self.Close:  # is it ireally needed for Close?
            pass
        elif self.exectype == self.Limit:
            self.m_lmtPrice = self.price
        elif self.exectype == self.Stop:
            self.m_auxPrice = self.price  # stop price / exec is market
        elif self.exectype == self.StopLimit:
            self.m_lmtPrice = self.pricelimit  # req limit execution
            self.m_auxPrice = self.price  # trigger price

        self.m_totalQuantity = abs(self.size)  # ib takes only positives

        self.m_transmit = True

        # Time In Force: DAY, GTC, IOC, GTD
        if self.valid is None:
            tif = 'GTC'  # Good til cancelled
        elif isinstance(self.valid, (datetime, date)):
            tif = 'GTD'  # Good til date
            self.m_goodTillDate = bytes(self.valid.strftime('%Y%m%d %H:%M:%S'))
        elif isinstance(self.valid, (timedelta,)):
            if self.valid == self.DAY:
                tif = 'DAY'
            else:
                tif = 'GTD'  # Good til date
                valid = datetime.now() + self.valid
                self.m_goodTillDate = bytes(valid.strftime('%Y%m%d %H:%M:%S'))

        elif self.valid == 0:
            tif = 'DAY'
        else:  # assume it is a float
            tif = 'GTD'  # Good til date
            valid = num2date(self.valid)
            self.m_goodTillDate = bytes(valid.strftime('%Y%m%d %H:%M:%S'))

        self.m_tif = bytes(tif)

        # pass any custom arguments to the order
        for k in kwargs:
            setattr(self, (not hasattr(self, k)) * 'm_' + k, kwargs[k])


class IBCommInfo(CommInfoBase):
    '''
    Commissions are calculated by ib, but the trades calculations in the
    ```Strategy`` rely on the order carrying a CommInfo object attached for the
    calculation of the operation cost and value.

    These are non-critical informations, but removing them from the trade could
    break existing usage and it is better to provide a CommInfo objet which
    enables those calculations even if with approvimate values.

    The margin calculation is not a known in advance information with IB
    (margin impact can be gotten from OrderState objects) and therefore it is
    left as future exercise to get it'''

    def getvaluesize(self, size, price):
        # In real life the margin approaches the price
        return abs(size) * price

    def getoperationcost(self, size, price):
        '''Returns the needed amount of cash an operation would cost'''
        # Same reasoning as above
        return abs(size) * price


class MetaIBBroker(MetaParams):
    def __init__(cls, name, bases, dct):
        '''Class has already been created ... register'''
        # Initialize the class
        super(MetaIBBroker, cls).__init__(name, bases, dct)
        ibstore.IBStore.BrokerCls = cls


class IBBroker(with_metaclass(MetaIBBroker, BrokerBase)):
    '''Broker implementation for Interactive Brokers.

    This class maps the orders/positions from Interactive Brokers to the
    internal API of ``backtrader``.

    Notes:

      - ``tradeid`` is not really supported, because the profit and loss are
        taken directly from IB. Because (as expected) calculates it in FIFO
        manner, the pnl is not accurate for the tradeid.

      - Position

        If there is an open position for an asset at the beginning of
        operaitons or orders given by other means change a position, the trades
        calculated in the ``Strategy`` in cerebro will not reflect the reality.

        To avoid this, this broker would have to do its own position
        management which would also allow tradeid with multiple ids (profit and
        loss would also be calculated locally), but could be considered to be
        defeating the purpose of working with a live broker
    '''
    params = ()

    def __init__(self, **kwargs):
        super(IBBroker, self).__init__()

        self.ib = ibstore.IBStore(**kwargs)

        self.startingcash = self.cash = 0.0
        self.startingvalue = self.value = 0.0

        self._lock_orders = threading.Lock()  # control access
        self.orderbyid = dict()  # orders by order id
        self.executions = dict()  # notified executions
        self.ordstatus = collections.defaultdict(dict)
        self.notifs = queue.Queue()  # holds orders which are notified
        self.tonotify = collections.deque()  # hold oids to be notified

    def start(self):
        super(IBBroker, self).start()
        self.ib.start(broker=self)

        if self.ib.connected():
            self.ib.reqAccountUpdates()
            self.startingcash = self.cash = self.ib.get_acc_cash()
            self.startingvalue = self.value = self.ib.get_acc_value()
        else:
            self.startingcash = self.cash = 0.0
            self.startingvalue = self.value = 0.0

    def stop(self):
        super(IBBroker, self).stop()
        self.ib.stop()

    def getcash(self):
        # This call cannot block if no answer is available from ib
        self.cash = self.ib.get_acc_cash()
        return self.cash

    def getvalue(self, datas=None):
        self.value = self.ib.get_acc_value()
        return self.value

    def getposition(self, data, clone=True):
        return self.ib.getposition(data.contract, clone=clone)

    def cancel(self, order):
        try:
            o = self.orderbyid[order.m_orderId]
        except (ValueError, KeyError):
            return  # not found ... not cancellable

        if order.status == Order.Cancelled:  # already cancelled
            return

        self.ib.cancelOrder(order.m_orderId)

    def orderstatus(self, order):
        try:
            o = self.orderbyid[order.m_orderId]
        except (ValueError, KeyError):
            o = order

        return o.status

    def submit(self, order):
        order.submit(self)

        self.orderbyid[order.m_orderId] = order
        self.ib.placeOrder(order.m_orderId, order.data.contract, order)
        self.notify(order)

        return order

    def getcommissioninfo(self, data):
        contract = data.contract
        try:
            mult = float(contract.m_multiplier)
        except (ValueError, TypeError):
            mult = 1.0

        stocklike = contract.m_secType in ['FUT', 'OPT', 'FOP']

        return IBCommInfo(mult=mult, stocklike=stocklike)

    def _makeorder(self, action, owner, data,
                   size, price=None, plimit=None,
                   exectype=None, valid=None,
                   tradeid=0, **kwargs):

        order = IBOrder(action, owner=owner, data=data,
                        size=size, price=price, plimit=plimit,
                        exectype=exectype, valid=valid,
                        tradeid=tradeid,
                        m_clientId=self.ib.clientId,
                        m_orderId=self.ib.nextOrderId(),
                        **kwargs)

        order.addcomminfo(self.getcommissioninfo(data))
        return order

    def buy(self, owner, data,
            size, price=None, plimit=None,
            exectype=None, valid=None, tradeid=0,
            **kwargs):

        order = self._makeorder(
            'BUY',
            owner, data, size, price, plimit, exectype, valid, tradeid,
            **kwargs)

        return self.submit(order)

    def sell(self, owner, data,
             size, price=None, plimit=None,
             exectype=None, valid=None, tradeid=0,
             **kwargs):

        order = self._makeorder(
            'SELL',
            owner, data, size, price, plimit, exectype, valid, tradeid,
            **kwargs)

        return self.submit(order)

    def notify(self, order):
        self.notifs.put(order.clone())

    def get_notification(self):
        try:
            return self.notifs.get(False)
        except queue.Empty:
            pass

        return None

    def next(self):
        self.notifs.put(None)  # mark notificatino boundary

    # Order statuses in msg
    SUBMITTED, FILLED, CANCELLED, INACTIVE = (
        'Submitted', 'Filled', 'Cancelled', 'Inactive')

    def push_orderstatus(self, msg):
        # Cancelled and Submitted with Filled = 0 can be pushed immediately
        try:
            order = self.orderbyid[msg.orderId]
        except KeyError:
            return  # not found, it was not an order

        if msg.status == self.SUBMITTED and msg.filled == 0:
            if order.status == order.Accepted:  # duplicate detection
                return

            order.accept(self)
            self.notify(order)

        elif msg.status == self.CANCELLED:
            if order.status == order.Cancelled:  # duplicate detection
                return

            order.cancel()
            self.notify(order)

        elif msg.status == self.INACTIVE:
            if order.status == order.Rejected:  # duplicate detection
                return

            order.reject(self)
            self.notify(order)

        elif msg.status in [self.SUBMITTED, self.FILLED]:
            # These two are kept inside the order until execdetails and
            # commission are all in place - commission is the last to come
            self.ordstatus[msg.orderId][msg.filled] = msg
        else:  # Unknown status ...
            pass

    def push_execution(self, ex):
        self.executions[ex.m_execId] = ex

    def push_commissionreport(self, cr):
        with self._lock_orders:
            ex = self.executions.pop(cr.m_execId)
            oid = ex.m_orderId
            order = self.orderbyid[oid]
            ostatus = self.ordstatus[oid][ex.m_cumQty]

            position = self.getposition(order.data, clone=False)
            pprice_orig = position.price
            size = ex.m_shares if ex.m_side[0] == 'B' else -ex.m_shares
            price = ex.m_price
            # use pseudoupdate and let the updateportfolio do the real update?
            psize, pprice, opened, closed = position.update(size, price)

            # split commission between closed and opened
            comm = cr.m_commission
            closedcomm = comm * closed / size
            openedcomm = comm - closedcomm

            comminfo = order.comminfo
            closedvalue = comminfo.getoperationcost(closed, pprice_orig)
            openedvalue = comminfo.getoperationcost(opened, price)

            # default in m_pnl is MAXFLOAT
            pnl = cr.m_realizedPNL if closed else 0.0

            # The internal broker calc should yield the same result
            # pnl = comminfo.profitandloss(-closed, pprice_orig, price)

            # FIXME ... from data or from execution From data it can be way off
            # the real execution time depending on the timeframe dt =
            # order.data.datetime[0] With execution time, the problem is the
            # time difference from UTC (data) if no timezone has been provided,
            # because the actual time is reported in computer's local
            # time. Sample: m_time: 20160518 20:19:46
            dt = date2num(datetime.strptime(ex.m_time, '%Y%m%d  %H:%M:%S'))

            # Need to simulate a margin, but it plays no role, because it is
            # controlled by a real broker. Let's set the price of the item
            margin = order.data.close[0]

            order.execute(dt, size, price,
                          closed, closedvalue, closedcomm,
                          opened, openedvalue, openedcomm,
                          margin, pnl,
                          psize, pprice)

            if ostatus.status == self.FILLED:
                order.completed()
            else:
                order.partial()

            if oid not in self.tonotify:  # Lock needed
                self.tonotify.append(oid)

    def push_portupdate(self):
        # If the IBStore receives a Portfolio update, then this method will be
        # indicated. If the execution of an order is split in serveral lots,
        # updatePortfolio messages will be intermixed, which is used as a
        # signal to indicate that the strategy can be notified
        with self._lock_orders:
            while self.tonotify:
                oid = self.tonotify.popleft()
                order = self.orderbyid[oid]
                self.notify(order)

    def push_ordererror(self, msg):
        with self._lock_orders:
            try:
                order = self.orderbyid[msg.id]
            except (KeyError, AttributeError):
                return  # no order or no id in error

            if msg.errorCode == 202:  # cancelled (by user?)
                if order.status == order.Cancelled:
                    return
            elif msg.errorCode == 201:  # rejected
                if order.status == order.Rejected:
                    return

            # Default case for the other codes
            order.reject()
            self.notify(order)
