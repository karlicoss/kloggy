"""
Logging helper for HPI and related projects.

Only implements approved requirements, see doc/requirements.md.
"""

from __future__ import annotations

import functools
import logging
import os
import sys
import warnings
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


# like RUST_LOG's 'off'
_OFF = logging.CRITICAL + 1


def _parse_level_spec(spec: str) -> dict[str, int]:
    """
    Logger name -> level from a KLOGGY_LEVEL spec, e.g. 'warning,pkg.sub=debug', with '' for the default (V1).
    Like RUST_LOG, invalid entries are ignored with a warning, and a later entry for the same logger wins.
    """
    level_names = {**logging.getLevelNamesMapping(), 'OFF': _OFF}
    levels: dict[str, int] = {}
    for entry in spec.split(','):
        entry = entry.strip()
        if entry == '':
            # e.g. a trailing comma
            continue
        name, eq, level_name = (part.strip() for part in entry.rpartition('='))
        if '=' in name or (eq != '' and name == ''):
            warnings.warn(f'KLOGGY_LEVEL: ignoring malformed entry {entry!r}', stacklevel=1)
            continue
        level = level_names.get(level_name.upper())
        if level is None:
            warnings.warn(f'KLOGGY_LEVEL: ignoring {entry!r}: unknown level {level_name!r}', stacklevel=1)
            continue
        levels[name] = level
    return levels


@functools.cache
def _level_spec() -> dict[str, int]:
    """
    KLOGGY_LEVEL, read once, on the first get_logger() call (V1).
    """
    return _parse_level_spec(os.environ.get('KLOGGY_LEVEL', ''))


# boolean values as in systemd (L5)
_TRUE = {'1', 'true', 'yes', 'on'}
_FALSE = {'', '0', 'false', 'no', 'off'}


@functools.cache
def _disabled() -> bool:
    """
    KLOGGY_DISABLE, read once, on the first get_logger() call (L5).
    """
    value = os.environ.get('KLOGGY_DISABLE', '')
    if value.strip().lower() in _TRUE:
        return True
    if value.strip().lower() not in _FALSE:
        warnings.warn(f'KLOGGY_DISABLE: ignoring unknown value {value!r}, expected e.g. 1 or 0', stacklevel=1)
    return False


# top-level packages KLOGGY_LEVEL was applied to (V1)
_levels_applied: set[str] = set()


def _apply_levels(package: str) -> None:
    """
    Sets the levels the user asked for via KLOGGY_LEVEL for a package using kloggy, once (V1).
    """
    if package in _levels_applied:
        return
    levels = _level_spec()
    _levels_applied.add(package)
    default = levels.get('')
    to_set = {name: level for name, level in levels.items() if name == package or name.startswith(f'{package}.')}
    if default is not None:
        # an entry for the package itself beats the default
        to_set.setdefault(package, default)
    for name, level in to_set.items():
        logger = logging.getLogger(name)
        if logger.level == logging.NOTSET:
            # otherwise someone, e.g. the app, set it explicitly, and the app always wins
            logger.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    if _disabled():
        # the user opted out of kloggy completely (L5)
        return logging.getLogger(name)

    logger = logging.getLogger(name)
    package_name = name.partition('.')[0]
    # the user asked for these explicitly, so even if the app configured logging
    _apply_levels(package_name)
    if _has_stepped_aside(logger):
        # don't touch logging state if the app already configured it (L1)
        return logger

    package = logging.getLogger(package_name)
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
