"""
Progress bars via [enlighten](https://github.com/Rockhopper-Technologies/enlighten).
"""

from __future__ import annotations

import sys
import threading
from typing import Any, TextIO

import enlighten  # type: ignore[import-untyped]

# like enlighten's default, except the parts are padded to the same width in all bars, see _widths(),
#   so e.g. the '/' and '[' line up
_BAR_FORMAT = (
    '{desc:<{desc_w}} {percentage:3.0f}%|{bar}| {count:>{count_w}d}/{total:<{total_w}d} '
    '[{elapsed}<{eta:>5}, {rate:>{rate_w}.2f} {unit:>{unit_w}}/s]'
)
# for counters without a total: like _BAR_FORMAT, but blank instead of the percentage and the bar
_COUNTER_FORMAT = (
    '{desc:<{desc_w}} {fill}  {count:>{count_w}d}/{unknown_total:<{total_w}} '
    '[{elapsed}<{unknown_eta}, {rate:>{rate_w}.2f} {unit:>{unit_w}}/s]'
)


def _widths(bars: list[tuple[str, int, int | None, str]]) -> dict[str, object]:
    """
    Fields for _BAR_FORMAT and _COUNTER_FORMAT, from each bar's description, count, total and unit.
    """
    return {
        'desc_w': max(len(desc) for desc, _, _, _ in bars),
        # as wide as the total if there is one, so the count doesn't shift as it grows
        'count_w': max(len(str(count if total is None else total)) for _, count, total, _ in bars),
        'total_w': max(len('?' if total is None else str(total)) for _, _, total, _ in bars),
        'unit_w': max(len(unit) for _, _, _, unit in bars),
        # fixed, since enlighten computes each bar's rate when drawing it: lines up up to 9999.99/s
        'rate_w': 7,
        'unknown_total': '?',
        'unknown_eta': '--:--',
    }


class EnlightenDisplay:
    """
    Shows bars at the bottom of the terminal while any loop is in progress, and removes them once it's done.
    Bars of loops that didn't finish stay on the screen.
    enlighten limits scrolling to the rest of the terminal, so any output stays above the bars, whichever stream it's written to.
    The space for the bars stays reserved until the process exits:
      the manager is kept for the whole process, since starting one queries the terminal, which may take a while.
    """

    def __init__(self, *, stream: TextIO | None = None) -> None:
        # None: sys.stderr at the time, like logs, so bars don't mix with data printed to stdout
        self._stream = stream
        # enlighten isn't thread-safe
        self._lock = threading.Lock()
        self._manager: Any = None

    def bar(self, *, desc: str, total: int | None, unit: str) -> _EnlightenBar | None:
        with self._lock:
            if self._manager is None:
                stream = sys.stderr if self._stream is None else self._stream
                if not stream.isatty():
                    return None
                self._manager = enlighten.Manager(
                    stream=stream,
                    # resizing relies on a signal handler, which can only be set from the main thread
                    no_resize=threading.current_thread() is not threading.main_thread(),
                )
            bars = [(c.desc, c.count, c.total, c.unit) for c in self._manager.counters]
            counter = self._manager.counter(
                total=total,
                desc=desc,
                unit=unit,
                leave=False,
                bar_format=_BAR_FORMAT,
                counter_format=_COUNTER_FORMAT,
                fields=_widths([*bars, (desc, 0, total, unit)]),
            )
            self._align()
            return _EnlightenBar(display=self, counter=counter)

    def _align(self) -> None:
        """
        Pads the parts of all the bars to the same width, e.g. after one was added or removed, or a count without a total got wider.
        """
        counters = list(self._manager.counters)
        if len(counters) == 0:
            return
        fields = _widths([(c.desc, c.count, c.total, c.unit) for c in counters])
        for counter in counters:
            if counter.fields != fields:
                counter.fields = fields
                # otherwise it would only be redrawn on its next update
                counter.refresh()

    def _advance(self, counter: Any) -> None:
        with self._lock:
            counter.update()
            self._align()

    def freeze(self) -> None:
        with self._lock:
            if self._manager is not None:
                # otherwise they'd show whatever they were last drawn with, which happens at most every 0.1s
                for counter in self._manager.counters:
                    counter.refresh()
                # leaves the bars that are still open on the screen, and lets the whole terminal scroll again
                self._manager.stop()
                self._manager = None

    def _close(self, counter: Any, *, keep: bool) -> None:
        with self._lock:
            if counter.manager is not self._manager:
                # frozen since, so it's already on the screen as it was
                return
            if keep:
                # stays on the screen as it is, until the process exits
                counter.leave = True
                counter.close()
            else:
                # otherwise the bar's last state would stay on the screen, even with leave=False
                counter.close(clear=True)
            self._align()


class _EnlightenBar:
    def __init__(self, *, display: EnlightenDisplay, counter: Any) -> None:
        self._display = display
        self._counter = counter

    def advance(self) -> None:
        self._display._advance(self._counter)

    def close(self, *, keep: bool) -> None:
        self._display._close(self._counter, keep=keep)
