"""
Warnings: on one line, coloured on a terminal (W1), and once per message (W2).
"""

from __future__ import annotations

import contextlib
import functools
import logging
import sys
import warnings
from typing import TextIO

import colorlog

from . import _disabled


def setup() -> None:
    """
    Shows warnings on one line, coloured on a terminal, unless something already customised how warnings are shown (W1).
    """
    if _disabled():
        # plain stdlib instead (L5)
        return
    # stdlib uses _showwarning_orig itself to tell whether showwarning was customised; getattr, since typeshed doesn't declare it
    if warnings.showwarning is not getattr(warnings, '_showwarning_orig'):
        # e.g. IPython, pytest or the app installed their own, or setup() was already called
        return
    # ty treats module functions as non-assignable, even with the same signature
    warnings.showwarning = _showwarning  # ty: ignore[invalid-assignment]


# like warnings.warn(), but once per distinct arguments, also if warning filters change in between (W2)
# functools.cache is implemented in C, so it adds no frame, and stacklevel works as with warnings.warn()
warn_once = functools.cache(warnings.warn)


def _showwarning(  # noqa: PLR0917 - same signature as warnings.showwarning
    message: Warning | str,
    category: type[Warning],
    filename: str,
    lineno: int,
    file: TextIO | None = None,
    line: str | None = None,  # noqa: ARG001 - the source line, deliberately not shown
) -> None:
    # same as stdlib: the current sys.stderr, if there is one
    stream = sys.stderr if file is None else file
    if stream is None:
        return
    text = _format(message, category, filename, lineno, stream=stream)
    # same as stdlib: if the stream is invalid, the warning is lost
    with contextlib.suppress(OSError):
        stream.write(text)


# like the first line of stdlib's format, so terminals and editors can still jump to file:line
# stdlib's second line, the source line, is dropped: it's often just the `warnings.warn(...)` call repeating the message
# colorlog fills in the escape codes, or blanks them if it decides against colour
_FORMAT = '%(thin)s%(pathname)s:%(lineno)d:%(reset)s %(bold_red)s%(category)s:%(reset)s %(red)s%(message)s'


def _format(message: Warning | str, category: type[Warning], filename: str, lineno: int, *, stream: TextIO) -> str:
    record = logging.makeLogRecord(
        {'msg': str(message), 'pathname': filename, 'lineno': lineno, 'category': category.__name__}
    )
    # colorlog decides on colour for the stream, same as for kloggy's log output (F2)
    # except it would raise for a stream without isatty(), e.g. a replaced sys.stderr, and the exception would reach the warn() call
    has_isatty = hasattr(stream, 'isatty')
    formatter = colorlog.ColoredFormatter(_FORMAT, stream=stream if has_isatty else None, no_color=not has_isatty)
    return formatter.format(record) + '\n'
