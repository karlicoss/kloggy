"""
Progress for loops over items, e.g. files to process: log lines, or progress bars on a terminal.

Experimental, see P1-P4 in doc/requirements.md: may still change a lot, or move to a separate package.

Library code wraps its loops, without knowing how progress is shown:

    for path in progress(paths, logger=logger):
        ...

Each item is logged before it's processed, e.g. 'processing [ 3/10] /path/to/file', at INFO.
While a display shows a bar for the loop, e.g. rich or enlighten on a terminal, items are logged at DEBUG instead.

There is one display for the whole process, shared by all packages, so bars of nested or concurrent loops show together.
It's picked by the app via set_display(), or by the user via KLOGGY_PROGRESS,
  e.g. KLOGGY_PROGRESS=rich, or KLOGGY_PROGRESS=auto for whichever of rich and enlighten is installed.
By default there is none, i.e. log lines only.
"""

from __future__ import annotations

import logging
import os
import threading
import warnings
from collections.abc import Callable, Iterable, Iterator, Sized
from typing import Protocol, TypeVar

T = TypeVar('T')


class Bar(Protocol):
    def advance(self) -> None: ...

    def close(self, *, keep: bool) -> None:
        """
        Stops showing the bar.
        keep: leaves it on the screen as it is, e.g. if its loop didn't finish, so it's visible where it stopped.
        """
        ...


class Display(Protocol):
    """
    Shows progress bars, e.g. via a TUI library like rich or enlighten.
    """

    def bar(self, *, desc: str, total: int | None, unit: str) -> Bar | None:
        """
        Starts showing a bar, or returns None if it can't show one, e.g. if the output isn't a terminal.
        """
        ...

    def freeze(self) -> None:
        """
        Stops showing all the current bars, leaving them on the screen as they are, e.g. on Ctrl-C.
        Loops starting later get new bars.
        """
        ...


def _rich() -> Display:
    from .rich import RichDisplay

    return RichDisplay()


def _enlighten() -> Display:
    from .enlighten import EnlightenDisplay

    return EnlightenDisplay()


# KLOGGY_PROGRESS value -> display, along with the optional dependency it needs
# KLOGGY_PROGRESS=auto tries them in this order: rich first, see P4 in doc/requirements.md
_DISPLAYS: dict[str, tuple[Callable[[], Display], str]] = {
    'rich': (_rich, 'rich'),
    'enlighten': (_enlighten, 'enlighten'),
}

_lock = threading.Lock()
_display: Display | None = None
# whether the display is decided, i.e. set via set_display(), or KLOGGY_PROGRESS was read
_decided = False


def set_display(display: Display | None) -> None:
    """
    Sets the display for the whole process, e.g. set_display(RichDisplay()) in the app's main(), or None for log lines only.
    Takes precedence over KLOGGY_PROGRESS.
    Loops already in progress keep their bars.
    """
    global _display, _decided
    with _lock:
        _display = display
        _decided = True


def _get_display() -> Display | None:
    global _display, _decided
    with _lock:
        if not _decided:
            _display = _display_from_env()
            _decided = True
        return _display


def _display_from_env() -> Display | None:
    """
    KLOGGY_PROGRESS, read once, on the first progress() call, unless the app called set_display() before.
    """
    value = os.environ.get('KLOGGY_PROGRESS', '')
    name = value.strip().lower()
    if name in {'', 'off'}:
        return None
    if name == 'auto':
        # no warning if none is installed: just log lines, as without KLOGGY_PROGRESS
        for factory, dependency in _DISPLAYS.values():
            try:
                return factory()
            except ModuleNotFoundError as e:
                if e.name != dependency:
                    raise
        return None
    entry = _DISPLAYS.get(name)
    if entry is None:
        warnings.warn(
            f'KLOGGY_PROGRESS: ignoring unknown value {value!r}, expected one of {sorted([*_DISPLAYS, "auto"])} or off',
            stacklevel=1,
        )
        return None
    factory, dependency = entry
    try:
        return factory()
    except ModuleNotFoundError as e:
        if e.name != dependency:
            raise
        warnings.warn(
            f"KLOGGY_PROGRESS: {name} isn't installed, only logging progress (try `pip install kloggy[{name}]`)",
            stacklevel=1,
        )
        return None


def progress(
    items: Iterable[T],
    *,
    logger: logging.Logger,
    desc: str | None = None,
    total: int | None = None,
    unit: str = 'items',
    describe: Callable[[T], object] | None = None,
    log_items: bool = True,
) -> Iterator[T]:
    """
    Yields the items, logging each one before it's processed, e.g. 'processing [ 3/10] /path/to/file'.
    At INFO, or at DEBUG while the display shows a bar for the loop.
    desc labels the bar, by default with the logger's name.
    total defaults to len(items), if the items have a length.
    describe is what to log for an item instead of the item itself, e.g. the path for a (path, result) pair.
    log_items=False doesn't log the 'processing [i/n] ...' line for each item, so there's only the bar, if a display shows one.
      E.g. for thousands of events, where a log line for each would flood the output.
    """
    if total is None and isinstance(items, Sized):
        total = len(items)
    display = _get_display()
    bar = None if display is None else display.bar(desc=logger.name if desc is None else desc, total=total, unit=unit)
    # the bar already shows progress, so per-item lines are only useful for debugging then
    level = logging.INFO if bar is None else logging.DEBUG
    width = len(str(total))
    try:
        for i, item in enumerate(items, start=1):
            if log_items:
                shown = item if describe is None else describe(item)
                # stacklevel: the record's location is the loop in the caller, rather than this function
                if total is None:
                    logger.log(level, 'processing [%d] %s', i, shown, stacklevel=2)
                else:
                    logger.log(level, 'processing [%*d/%d] %s', width, i, total, shown, stacklevel=2)
            yield item
            if bar is not None:
                bar.advance()
    except KeyboardInterrupt:
        # Ctrl-C: all the bars stay on the screen as they are, rather than this one now, and the others whenever their loops are cleaned up
        if display is not None and bar is not None:
            display.freeze()
        raise
    except BaseException:
        # the loop didn't finish, e.g. an error, or it stopped early (GeneratorExit), e.g. via break, or Ctrl-C outside this function
        if bar is not None:
            bar.close(keep=True)
        raise
    else:
        if bar is not None:
            bar.close(keep=False)
