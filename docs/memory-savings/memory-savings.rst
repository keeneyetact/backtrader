
.. post:: May 09, 2016
   :author: mementum
   :image: 1

Saving Memory
#############

`Release 1.3.1.92
<https://github.com/mementum/backtrader/releases/tag/1.3.1.92>`_ has reworked
and fully implemented the memory saving schemes that were previously in place,
although not much touted and less used.

``backtrader`` was (and will be further) developed in machines with nice
amounts of RAM and that put together with the fact that visual feedback through
plotting is a nice to have and almost a must have, mde it easy for a design
decision: keep everything in memory.

This decision has some drawbacks:

  - ``array.array`` which is used for data storage has to allocate and move
    data when some bounds are exceeded

  - Machines with low amounts of RAM may suffer

  - Connection to a live data feed which can be online for weeks/months feeded
    thousands of seconds/minutes resolution ticks into the system

The latter being even more important than the 1st due to another design
decision which was made for ``backtrader``:

  - Be pure Python to allow to run in embedded systems if needed be

    A scenario in the future could have ``backtrader`` connected to a 2nd
    machine which provides the live feed, whilst ``backtrader`` itself runs
    inside a *Raspberry Pi* or something even more limited like an ADSL Router
    (AVM Frit!Box 7490 with a *Freetz* image)

Hence the need to have ``backtrader`` support dynamid memory schemes. Now
``Cerebro`` can be instantiated or ``run`` with the following semantics:

      - exactbars (default: False)

        With the default ``False`` value each and every value stored in a line
        is kept in memory

        Possible values:
          - ``True`` or ``1``: all "lines" objects reduce memory usage to the
            automatically calculated minimum period.

            If a Simple Moving Average has a period of 30, the underlying data
            will have always a running buffer of 30 bars to allow the
            calculation of the Simple Moving Average

            - This setting will deactivate ``preload`` and ``runonce``
            - Using this setting also deactivates **plotting**

          - ``-1``: datas and indicators/operations at strategy level will keep
            all data in memory.

            For example: a ``RSI`` internally uses the indicator ``UpDay`` to
            make calculations. This subindicator will not keep all data in
            memory

            - This allows to keep ``plotting`` and ``preloading`` active.

            - ``runonce`` will be deactivated

          - ``-2``: datas and indicators kept as attributes of the strategy
            will keep all data in memory.

            For example: a ``RSI`` internally uses the indicator ``UpDay`` to
            make calculations. This subindicator will not keep all data in
            memory

            If in the ``__init__`` something like
            ``a = self.data.close - self.data.high`` is defined, then ``a``
            will not keep all data in memory

            - This allows to keep ``plotting`` and ``preloading`` active.

            - ``runonce`` will be deactivated


As always, an example is worth a thousand words. A sample script shows the
differences. It runs against the *Yahoo* daily data for the years 1996 to 2015,
for a total of ``4965`` days.

.. note:: This is a small sample. The EuroStoxx50 future which trades 14 hours
	  a day, would produce approximately 18000 1-minute bars in just 1
	  month of trading.

The script 1st executed to see how many memory positions are used when no
memory savings are requested::

  $ ./memory-savings.py --save 0
  Total memory cells used: 506430

For level 1 (total savings)::

  $ ./memory-savings.py --save 1
  Total memory cells used: 2041

OMG!!! Down from *half-a-million* to ``2041``. Indeed. Each an every *lines*
object in the system uses a ``collections.deque`` as buffer (instead of
``array.array``) and is length-bounding to the absolute needed minimum for the
requested operations. Example:

  - A Strategy using a ``SimpleMovingAverage`` of period ``30`` on the data
    feed.

In this case the following adjustments would be made:

  - The *data feed* will have a buffer of ``30`` positions, the amount needed
    by the ``SimpleMovingAverage`` to produce the next value

  - The ``SimpleMovingAverage`` will have a buffer of ``1`` position, because
    unless needed by other *indicator* (which would rely on the moving average)
    there is no need to keep a larger buffer in place.

.. note::
   The most attractive and probably important feature of this mode is that the
   amount of memory used remains constant throughout the entire life of a
   script.

   Regardless of the size of the data feed.

   This would be of great use if for example connected to a live feed for a
   long period of time.

   But take into account:

     1. *Plotting* is not available

     2. There are other sources of memory consumption which would accumulate
	over time like ``orders`` generated by the strategy.

     3. This mode can only be used with ``runonce=False`` in ``cerebro``. This
	would also be compulsory for a live data feed, but in case of simple
	backtesting this is slower than ``runonce=True``.

	There is for sure a trade off point from which memory management is
	more expensive than the step-by-step execution of the backtesting, but
	this can only be judged by the end-user of the platform on a case by
	case basis.

Now the negative levels. These are meant to keep *plotting* available whilst
still saving a decent amount of memory. First level ``-1``::

  $ ./memory-savings.py --save -1
  Total memory cells used: 184623

In this case the 1st level of *indicators* (those declared in the strategy)
keep its full length buffers. But if this indicators rely on others (which is
the case) to do its work, the subobjects will be length-bounded. In this case
we have gone from:

  - ``506430`` memory positions to -> ``184623``

Over 50% savings.

.. note:: Of course ``array.array`` objects have been traded for
	  ``collections.deque`` which are more expensive in memory terms
	  although faster in operation terms. But the ``collection.deque``
	  objects are rather small and the savings approach the roughly
	  counted memory positions used.

Level ``-2`` now, which is meant to also save on the indicators declared at the
strategy level which have been marked as no to be plotted::

  $ ./memory-savings.py --save -2
  Total memory cells used: 174695

Not much has been saved now. This being because a single indicator has been
tagged as not be plotted: ``TestInd().plotinfo.plot = False``

Let's see the plotting from this last example::

  $ ./memory-savings.py --save -2 --plot
  Total memory cells used: 174695

.. thumbnail:: memory-savings.png

For the interested reader, the sample script can produce a detailed analysis of
each *lines* object traversed in the hierarchy of *indicators*. Running with
*plotting* enabled (saving at ``-1``)::

  $ ./memory-savings.py --save -1 --lendetails
  -- Evaluating Datas
  ---- Data 0 Total Cells 34755 - Cells per Line 4965
  -- Evaluating Indicators
  ---- Indicator 1.0 Average Total Cells 30 - Cells per line 30
  ---- SubIndicators Total Cells 1
  ---- Indicator 1.1 _LineDelay Total Cells 1 - Cells per line 1
  ---- SubIndicators Total Cells 1
  ...
  ---- Indicator 0.5 TestInd Total Cells 9930 - Cells per line 4965
  ---- SubIndicators Total Cells 0
  -- Evaluating Observers
  ---- Observer 0 Total Cells 9930 - Cells per Line 4965
  ---- Observer 1 Total Cells 9930 - Cells per Line 4965
  ---- Observer 2 Total Cells 9930 - Cells per Line 4965
  Total memory cells used: 184623

The same but with maximum savings (``1``) enabled::

  $ ./memory-savings.py --save 1 --lendetails
  -- Evaluating Datas
  ---- Data 0 Total Cells 266 - Cells per Line 38
  -- Evaluating Indicators
  ---- Indicator 1.0 Average Total Cells 30 - Cells per line 30
  ---- SubIndicators Total Cells 1
  ...
  ---- Indicator 0.5 TestInd Total Cells 2 - Cells per line 1
  ---- SubIndicators Total Cells 0
  -- Evaluating Observers
  ---- Observer 0 Total Cells 2 - Cells per Line 1
  ---- Observer 1 Total Cells 2 - Cells per Line 1
  ---- Observer 2 Total Cells 2 - Cells per Line 1

The 2nd output immediately shows how the lines in the *data feed* have been
capped to ``38`` memory positions instead of the ``4965`` which comprises the
full data source length.

And *indicators* and *observers** have been when possible capped to ``1`` as
seen in the last lines of the output.

Script Code and Usage
^^^^^^^^^^^^^^^^^^^^^

Available as sample in the sources of ``backtrader``. Usage::

  $ ./memory-savings.py --help
  usage: memory-savings.py [-h] [--data DATA] [--save SAVE] [--datalines]
                           [--lendetails] [--plot]

  Check Memory Savings

  optional arguments:
    -h, --help    show this help message and exit
    --data DATA   Data to be read in (default: ../../datas/yhoo-1996-2015.txt)
    --save SAVE   Memory saving level [1, 0, -1, -2] (default: 0)
    --datalines   Print data lines (default: False)
    --lendetails  Print individual items memory usage (default: False)
    --plot        Plot the result (default: False)

The code:

.. literalinclude:: ./memory-savings.py
   :language: python
   :lines: 21-
