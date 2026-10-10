"""
Logging helper for HPI and related projects.

Only implements approved requirements, see doc/requirements.md.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TextIO


class _KloggyLogger(logging.Logger):
    """
    Class of loggers returned by get_logger().
    While logging isn't configured, their level defaults to INFO rather than root's WARNING (L2).
    Decided per call, so once the app configures logging, stdlib's levels apply straight away (L3), for good (Z2).
    """

    def isEnabledFor(self, level: int) -> bool:
        if _has_stepped_aside(self):
            return super().isEnabledFor(level)
        # not using stdlib's cache: it's only cleared on setLevel(), but until kloggy steps aside, the result depends on whether logging is configured
        if self.disabled or self.manager.disable >= level:
            return False
        return level >= self._level_while_unconfigured()

    def getEffectiveLevel(self) -> int:
        if _has_stepped_aside(self):
            return super().getEffectiveLevel()
        return self._level_while_unconfigured()

    def _level_while_unconfigured(self) -> int:
        """
        Same as stdlib's effective level, except INFO rather than root's level (L2).
        """
        logger: logging.Logger = self
        while logger.parent is not None:
            if logger.level != logging.NOTSET:
                # explicitly set, e.g. by the app
                return logger.level
            logger = logger.parent
        return logging.INFO


_kloggy_classes: dict[type[logging.Logger], type[logging.Logger]] = {logging.Logger: _KloggyLogger}


def _kloggy_class(cls: type[logging.Logger]) -> type[logging.Logger]:
    if issubclass(cls, _KloggyLogger):
        return cls
    if cls not in _kloggy_classes:
        # e.g. the app set its own class via logging.setLoggerClass()
        _kloggy_classes[cls] = type(f'Kloggy{cls.__name__}', (_KloggyLogger, cls), {})
    return _kloggy_classes[cls]


def _drop(record: logging.LogRecord) -> None:
    """
    Makes all remaining handlers skip the record.
    Logger.callHandlers() only passes a record to a handler if record.levelno >= handler.level, and handler levels are never below NOTSET.
    """
    record.levelno = logging.NOTSET - 1


class _FallbackHandler(logging.StreamHandler[TextIO]):
    """
    Used instead of stdlib's logging.lastResort which prints bare messages (Z1).
    Only prints a record if kloggy hasn't stepped aside for its logger, i.e. logging was never configured for it (Z2).
    """

    def handle(self, record: logging.LogRecord) -> bool:
        # decided here rather than in emit(), which runs under the handler's lock
        # getLogger() takes logging's module lock, and dictConfig() takes the two locks in the opposite order
        logger = logging.getLogger(record.name)
        if not _has_stepped_aside(logger):
            printed = super().handle(record)
            if printed:
                # so root's default basicConfig() handler doesn't print it again (Z3)
                _drop(record)
            return printed
        if record.levelno < logger.getEffectiveLevel():
            # created just before the app configured logging, at kloggy's INFO (L3)
            _drop(record)
        elif not _reaches_other_handlers(logger):
            # the app removed its handlers since, so same as stdlib without any handlers (Z2)
            # stdlib wouldn't fall back to lastResort itself, since this handler counts as found
            last_resort = logging.lastResort
            if last_resort is not None and record.levelno >= last_resort.level:
                last_resort.handle(record)
        return False


def _is_default_basic_config_handler(handler: logging.Handler) -> bool:
    """
    Whether this is root's only handler, exactly what a default basicConfig() creates, e.g. implicitly via a bare logging.warning() call (Z3).
    """
    root = logging.getLogger()
    if root.level != logging.WARNING:
        return False
    if root.handlers != [handler]:
        return False
    if type(handler) is not logging.StreamHandler:
        return False
    if handler.stream not in (sys.stderr, sys.__stderr__):
        return False
    if handler.level != logging.NOTSET:
        return False
    if len(handler.filters) != 0:
        return False
    fmt = handler.formatter
    if type(fmt) is not logging.Formatter:
        return False
    return fmt._fmt == logging.BASIC_FORMAT and fmt.datefmt is None


def _is_configured(logger: logging.Logger) -> bool:
    """
    Whether records from this logger would reach some handler other than kloggy's own (Z1),
      not counting root's default basicConfig() handler (Z3).
    Same walk as stdlib's Logger.callHandlers/Logger.hasHandlers.
    """
    current: logging.Logger | None = logger
    while current is not None:
        for h in current.handlers:
            if isinstance(h, _FallbackHandler):
                continue
            if current.parent is None and _is_default_basic_config_handler(h):
                continue
            return True
        if not current.propagate:
            return False
        current = current.parent
    return False


def _reaches_other_handlers(logger: logging.Logger) -> bool:
    """
    Whether records from this logger would reach any handler other than kloggy's own, including root's default basicConfig() handler.
    Same walk as stdlib's Logger.callHandlers/Logger.hasHandlers.
    """
    current: logging.Logger | None = logger
    while current is not None:
        if any(not isinstance(h, _FallbackHandler) for h in current.handlers):
            return True
        if not current.propagate:
            return False
        current = current.parent
    return False


# names of loggers kloggy has stepped aside for (Z2)
_stepped_aside: set[str] = set()


def _has_stepped_aside(logger: logging.Logger) -> bool:
    """
    Whether kloggy is out of the picture for this logger.
    It steps aside for good the first time it notices logging configured for the logger (Z2).
    """
    if logger.name in _stepped_aside:
        return True
    if _is_configured(logger):
        _stepped_aside.add(logger.name)
        return True
    return False


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if _has_stepped_aside(logger):
        # don't touch logging state if the app already configured it (L1)
        return logger

    package = logging.getLogger(name.partition('.')[0])
    already_set_up = any(isinstance(h, _FallbackHandler) for h in package.handlers)
    if not already_set_up:
        handler = _FallbackHandler()
        # Z1 only asks for level and logger name, the specific format is up to F21/F24
        # private test override distinguishes kloggy's output without adding setup code to the examples
        fmt = os.environ.get('_KLOGGY_TEST_FORMAT', logging.BASIC_FORMAT)
        handler.setFormatter(logging.Formatter(fmt))
        package.addHandler(handler)

    # same object, but with INFO by default while logging isn't configured (L2, L3)
    logger.__class__ = _kloggy_class(type(logger))
    return logger
