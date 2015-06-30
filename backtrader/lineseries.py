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
'''

.. module:: lineroot

Defines LineSeries and Descriptors inside of it for classes that hold multiple
lines at once.

.. moduleauthor:: Daniel Rodriguez

'''
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import collections
try:
    from collections import OrderedDict
except ImportError:
    from .utils.ordereddict import OrderedDict
import operator
import sys

import six
from six.moves import xrange

from .linebuffer import LineBuffer, LinesOperation, LineDelay, NAN
from .lineroot import LineSingle, LineMultiple
from .metabase import AutoInfoClass
from . import metabase


class LineAlias(object):
    ''' Descriptor class that store a line reference and returns that line
    from the owner

    Keyword Args:
        line (int): reference to the line that will be returned from
        owner's *lines* buffer

    As a convenience the __set__ method of the descriptor is used not set
    the *line* reference because this is a constant along the live of the
    descriptor instance, but rather to set the value of the *line* at the
    instant '0' (the current one)
    '''

    def __init__(self, line):
        self.line = line

    def __get__(self, obj, cls=None):
        return obj.lines[self.line]

    def __set__(self, obj, value):
        '''
        A line cannot be "set" once it has been created. But the values
        inside the line can be "set". This is achieved by adding a binding
        to the line inside "value"
        '''
        if isinstance(value, LineMultiple):
            value = value.lines[0]

        value.addbinding(obj.lines[self.line])


class Lines(object):
    '''
    Defines an "array" of lines which also has most of the interface of
    a LineBuffer class (forward, rewind, advance...).

    This interface operations are passed to the lines held by self

    The class can autosubclass itself (_derive) to hold new lines keeping them
    in the defined order.
    '''
    _getlinesbase = classmethod(lambda cls: ())
    _getlines = classmethod(lambda cls: ())
    _getlinesextra = classmethod(lambda cls: 0)
    _getlinesextrabase = classmethod(lambda cls: 0)

    @classmethod
    def _derive(cls, name, lines, extralines, otherbases):

        obaseslines = ()
        obasesextralines = 0

        for otherbase in otherbases:
            if isinstance(otherbase, tuple):
                obaseslines += otherbase
            else:
                obaseslines += otherbase._getlines()
                obasesextralines += otherbase._getlinesextra()

        baselines = cls._getlines() + obaseslines
        baseextralines = cls._getlinesextra() + obasesextralines

        clslines = baselines + lines
        clsextralines = baseextralines + extralines

        lines2add = obaseslines + lines

        # str for Python 2/3 compatibility
        newcls = type(str(cls.__name__ + '_' + name), (cls,), {})

        setattr(newcls, '_getlinesbase', classmethod(lambda cls: baselines))
        setattr(newcls, '_getlines', classmethod(lambda cls: clslines))

        setattr(newcls,
                '_getlinesextrabase',
                classmethod(lambda cls: baseextralines))
        setattr(newcls,
                '_getlinesextra',
                classmethod(lambda cls: clsextralines))

        l2add = enumerate(lines2add, start=len(cls._getlines()))
        for line, linealias in l2add:
            if not isinstance(linealias, six.string_types):
                # a tuple or list was passed, 1st is name
                linealias = linealias[0]

            setattr(newcls, linealias, LineAlias(line))

        return newcls

    @classmethod
    def _getlinealias(cls, i):
        '''
        Return the alias for a line given the index
        '''
        lines = cls._getlines()
        if i >= len(lines):
            return ''
        linealias = lines[i]
        if not isinstance(linealias, six.string_types):
            linealias = linealias[0]
        return linealias

    def __init__(self, initlines=None):
        '''
        Create the lines recording during "_derive" or else use the
        provided "initlines"
        '''
        self.lines = list()
        for line, linealias in enumerate(self._getlines()):
            kwargs = dict()
            if not isinstance(linealias, six.string_types):
                # a tuple and not just a string - typecode is additional arg
                kwargs['typecode'] = linealias[1]

            self.lines.append(LineBuffer(**kwargs))

        # Add the required extralines
        for i in range(self._getlinesextra()):
            if not initlines:
                self.lines.append(LineBuffer())
            else:
                self.lines.append(initlines[i])

    def __len__(self):
        '''
        Proxy line operation
        '''
        return len(self.lines[0])

    def size(self):
        return len(self.lines) - self._getlinesextra()

    def fullsize(self):
        return len(self.lines)

    def extrasize(self):
        return self._getlinesextra()

    def __getitem__(self, line):
        '''
        Proxy line operation
        '''
        return self.lines[line]

    def get(self, ago=0, size=1, line=0):
        '''
        Proxy line operation
        '''
        return self.lines[line].get(ago, size=size)

    def __setitem__(self, line, value):
        '''
        Proxy line operation
        '''
        setattr(self, self._getlinealias(line), value)

    def forward(self, value=NAN, size=1):
        '''
        Proxy line operation
        '''
        for line in self.lines:
            line.forward(value, size=size)

    def backwards(self, size=1):
        '''
        Proxy line operation
        '''
        for line in self.lines:
            line.backwards(size)

    def rewind(self, size=1):
        '''
        Proxy line operation
        '''
        for line in self.lines:
            line.rewind(size)

    def extend(self, value=NAN, size=0):
        '''
        Proxy line operation
        '''
        for line in self.lines:
            line.extend(value, size)

    def reset(self):
        '''
        Proxy line operation
        '''
        for line in self.lines:
            line.reset()

    def home(self):
        '''
        Proxy line operation
        '''
        for line in self.lines:
            line.home()

    def advance(self):
        '''
        Proxy line operation
        '''
        for line in self.lines:
            line.advance()

    def buflen(self, line=0):
        '''
        Proxy line operation
        '''
        return self.lines[line].buflen()


class MetaLineSeries(LineMultiple.__class__):
    '''
    Dirty job manager for a LineSeries

      - During __new__ (class creation), it reads "lines", "plotinfo",
        "plotlines" class variable definitions and turns them into
        Classes of type Lines or AutoClassInfo (plotinfo/plotlines)

      - During "new" (instance creation) the lines/plotinfo/plotlines
        classes are substituted in the instance with instances of the
        aforementioned classes and aliases are added for the "lines" held
        in the "lines" instance

        Additionally and for remaining kwargs, these are matched against
        args in plotinfo and if existent are set there and removed from kwargs

        Remember that this Metaclass has a MetaParams (from metabase)
        as root class and therefore "params" defined for the class have been
        removed from kwargs at an earlier state
    '''

    def __new__(meta, name, bases, dct):
        '''
        Intercept class creation, identifiy lines/plotinfo/plotlines class
        attributes and create corresponding classes for them which take over
        the class attributes
        '''

        # Get the aliases - don't leave it there for subclasses
        aliases = dct.setdefault('alias', ())
        aliased = dct.setdefault('aliased', '')

        # Remove the line definition (if any) from the class creation
        newlines = dct.pop('lines', ())
        extralines = dct.pop('extralines', 0)

        # remove the new plotinfo/plotlines definition if any
        newplotinfo = dict(dct.pop('plotinfo', {}))
        newplotlines = dict(dct.pop('plotlines', {}))

        # Create the class - pulling in any existing "lines"
        cls = super(MetaLineSeries, meta).__new__(meta, name, bases, dct)
        lines = getattr(cls, 'lines', Lines)

        # Create a subclass of the lines class with our name and newlines
        # and put it in the class
        morebaseslines = [x.lines for x in bases[1:] if hasattr(x, 'lines')]
        cls.lines = lines._derive(name, newlines, extralines, morebaseslines)

        # Get a copy from base class plotinfo/plotlines (created with the
        # class or set a default)
        plotinfo = getattr(cls, 'plotinfo', AutoInfoClass)
        plotlines = getattr(cls, 'plotlines', AutoInfoClass)

        # Create a plotinfo/plotlines subclass and set it in the class
        morebasesplotinfo = \
            [x.plotinfo for x in bases[1:] if hasattr(x, 'plotinfo')]
        cls.plotinfo = plotinfo._derive(name, newplotinfo, morebasesplotinfo)

        # Before doing plotline newlines have been added and no plotlineinfo
        # is there add a default
        for line in newlines:
            if not isinstance(line, six.string_types):
                line = line[0]
            newplotlines.setdefault(line, dict())

        morebasesplotlines = \
            [x.plotlines for x in bases[1:] if hasattr(x, 'plotlines')]
        cls.plotlines = plotlines._derive(
            name, newplotlines, morebasesplotlines, recurse=True)

        # Update the doc
        clsdocorig = getattr(cls, '__doc__', '') or ''
        preclsdoc = name
        if aliases:
            aliasnames = list()
            for alias in aliases:
                if not isinstance(alias, six.string_types):
                    # a tuple or list was passed, 1st is name, 2nd plotname
                    alias = alias[0]
                aliasnames.append(alias)

            aliasdoc = ' (alias %s)\n' % ', '.join(aliasnames)
            preclsdoc += aliasdoc

        if aliased:
            preclsdoc += ' (alias of %s)\n' % aliased

        clsdoc = preclsdoc + clsdocorig

        if clsdoc[-1] != '\n':
            clsdoc += '\n'

        if len(cls.params._getpairs()):
            paramsdoc = '    Params:' + '\n'
            for pkey, pvalue in cls.params._getitems():
                paramsdoc += '      - %s (%s)\n' % (pkey, str(pvalue))

            clsdoc += paramsdoc + '\n'

        numlines = len(cls.lines._getlines())
        if numlines:
            linesdoc = '    Lines:' + '\n'
            for i in xrange(numlines):
                linesdoc += '      - ' + cls.lines._getlinealias(i) + '\n'

            clsdoc += linesdoc + '\n'

        if len(cls.plotinfo._getpairs()):
            pinfodoc = '    PlotInfo:' + '\n'
            for pkey, pvalue in cls.plotinfo._getitems():
                pinfodoc += '      - %s (%s)\n' % (pkey, str(pvalue))

            clsdoc += pinfodoc + '\n'

        if len(cls.plotlines._getpairs()):
            plinesdoc = '    PlotLines:' + '\n'
            for pkey, pvalue in cls.plotlines._getitems():
                if isinstance(pvalue, AutoInfoClass):
                    plinesdoc += '      - %s:' % pkey
                    for plkey, plvalue in pvalue._getitems():
                        plinesdoc += '        - %s (%s)\n' % (plkey, plvalue)
                elif isinstance(pvalue, (dict, OrderedDict)):
                    plinesdoc += '      - %s:' % pkey
                    for plkey, plvalue in pvalue.items():
                        plinesdoc += '        - %s (%s)\n' % (plkey, plvalue)
                else:
                    plinesdoc += '      - %s (%s)\n' % (pkey, str(pvalue))

            clsdoc += plinesdoc

        cls.__doc__ = clsdoc

        # create declared class aliases (a subclass with no modifications)
        for alias in aliases:
            newdct = {'__doc__': clsdocorig,
                      '__module__': cls.__module__,
                      'aliased': cls.__name__}

            if not isinstance(alias, six.string_types):
                # a tuple or list was passed, 1st is name, 2nd plotname
                alias = alias[0]
                aliasplotname = alias[1]
                newdct['plotinfo'] = dict(plotname=aliasplotname)

            newcls = type(str(alias), (cls,), newdct)
            clsmodule = sys.modules[cls.__module__]
            setattr(clsmodule, alias, newcls)

        # return the class
        return cls

    def donew(cls, *args, **kwargs):
        '''
        Intercept instance creation, take over lines/plotinfo/plotlines
        class attributes by creating corresponding instance variables and add
        aliases for "lines" and the "lines" held within it
        '''
        # _obj.plotinfo shadows the plotinfo (class) definition in the class
        plotinfo = cls.plotinfo()

        for pname, pdef in cls.plotinfo._getitems():
            setattr(plotinfo, pname, kwargs.pop(pname, pdef))

        # Create the object and set the params in place
        _obj, args, kwargs = super(MetaLineSeries, cls).donew(*args, **kwargs)

        # set the plotinfo member in the class
        _obj.plotinfo = plotinfo

        # _obj.lines shadows the lines (class) definition in the class
        _obj.lines = cls.lines()

        # _obj.plotinfo shadows the plotinfo (class) definition in the class
        _obj.plotlines = cls.plotlines()

        # add aliases for lines and for the lines class itself
        _obj.l = _obj.lines
        if _obj.lines.fullsize():
            _obj.line = _obj.lines[0]

        for l, line in enumerate(_obj.lines):
            setattr(_obj, 'line_%s' % l, _obj._getlinealias(l))
            setattr(_obj, 'line_%d' % l, line)
            setattr(_obj, 'line%d' % l, line)

        # Parameter values have now been set before __init__
        return _obj, args, kwargs


class LineSeries(six.with_metaclass(MetaLineSeries, LineMultiple)):
    @property
    def array(self):
        return self.lines[0].array

    def __getattr__(self, name):
        # to refer to line by name directly if the attribute was not found
        # in this object if we set an attribute in this object it will be
        # found before we end up here
        return getattr(self.lines, name)

    def __len__(self):
        return len(self.lines)

    def __getitem__(self, key):
        return self.lines[0][key]

    def __setitem__(self, key, value):
        setattr(self.lines, self.lines._getlinealias(key), value)

    def __init__(self, *args, **kwargs):
        # if any args, kwargs make it up to here, something is broken
        # defining a __init__ guarantees the existence of im_func to findbases
        # in lineiterator later, because object.__init__ has no im_func
        # (object has slots)
        super(LineSeries, self).__init__()
        pass

    def plotlabel(self):
        label = self.plotinfo.plotname or self.__class__.__name__
        sublabels = self._plotlabel()
        if sublabels:
            for i, sublabel in enumerate(sublabels):
                # if isinstance(sublabel, LineSeries): ## DOESN'T WORK ???
                if hasattr(sublabel, 'plotinfo'):
                    sublabels[i] = sublabel.plotinfo.plotname or \
                        sublabel.__name__
            label += ' (%s)' % ', '.join(map(str, sublabels))
        return label

    def _plotlabel(self):
        return self.params._getvalues()

    def __call__(self, ago, line=0):
        return LineDelay(self.lines[line], ago, _ownerskip=self)


class LineSeriesStub(LineSeries):
    extralines = 1

    def __init__(self, line):
        self.lines = self.__class__.lines(initlines=[line])
        # give a change to find the line owner (for plotting at least)
        self.owner = line._owner
        self._minperiod = line._minperiod


def LineSeriesMaker(arg):
    if isinstance(arg, LineSeries):
        return arg

    return LineSeriesStub(arg)
