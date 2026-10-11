"""
Z: output when logging isn't configured, i.e. kloggy's fallback handler.
"""

import logging
from collections.abc import Callable
from typing import TextIO

import pytest
from rich.console import Console

from .common import check_logs, rich_console, run, terminal_screen


def test_z1_stdlib_baseline() -> None:
    """
    Baseline, why Z1 exists: without any configuration, stdlib prints just the message (via `logging.lastResort`).
    No level or logger name, so an error looks the same as a warning.
    """

    def test() -> None:
        import logging

        logging.getLogger('my.foo').error('some error')  # LOGS: some error

    check_logs(test)


def test_z1_not_bare() -> None:
    """
    Without any configuration, kloggy output includes the level and the logger name.
    The specific format isn't checked, that's F1.
    """

    def test() -> None:
        from kloggy import get_logger

        get_logger('my.foo').error('some error')

    [line] = run(test, test_format=False)
    assert line != 'some error'
    for part in ['ERROR', 'my.foo', 'some error']:
        assert part in line, line


@pytest.mark.parametrize('setup', ['root', 'package', 'logger', 'null'])
def test_z2_configured_after(setup: str) -> None:
    """
    Configuring logging after kloggy set up switches kloggy output off.
    Each record is printed once, by the app's handlers (or not at all for a `NullHandler`).
    """

    # ways the app may configure logging after kloggy set up the 'my' package logger
    def configure(*, setup: str) -> None:
        import logging

        if setup == 'root':
            logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        elif setup == 'package':
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter('PKG %(name)s: %(message)s'))
            logging.getLogger('my').addHandler(h)
        elif setup == 'logger':
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter('OWN %(name)s: %(message)s'))
            logging.getLogger('my.foo').addHandler(h)
        else:
            assert setup == 'null', setup
            logging.getLogger('my').addHandler(logging.NullHandler())

    expected = {
        'root': [
            'APP WARNING my.foo: after',
        ],
        'package': [
            'PKG my.foo: after',
        ],
        'logger': [
            'OWN my.foo: after',
        ],
        'null': [],
    }[setup]

    def test(*, configure: Callable[..., None], setup: str) -> None:
        from kloggy import get_logger

        logger = get_logger('my.foo')
        logger.warning('before')
        configure(setup=setup)
        logger.warning('after')

    assert run(test, configure=configure, setup=setup) == [
        'KLOGGY WARNING my.foo: before',
        *expected,
    ]


def test_z2_stays_off_when_unconfigured() -> None:
    """
    Once the app's handler is removed again, kloggy output stays off.
    Output is then what it would be without kloggy: stdlib's levels and `logging.lastResort`.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        logger = get_logger('my.foo')
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter('APP %(name)s: %(message)s'))
        logging.getLogger().addHandler(h)
        logger.warning('configured')  # LOGS: APP my.foo: configured
        logging.getLogger().removeHandler(h)
        logger.info('some info')  # stdlib's levels apply, so no INFO
        logger.warning('unconfigured again')  # LOGS: unconfigured again

    check_logs(test)


def test_z2_stays_off_when_configured_at_setup() -> None:
    """
    Same as test_z2_stays_off_when_unconfigured, but logging is already configured when get_logger() is called.
    Output doesn't depend on whether logging was configured before or after get_logger().
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter('APP %(name)s: %(message)s'))
        logging.getLogger().addHandler(h)
        logger = get_logger('my.foo')
        logger.warning('configured')  # LOGS: APP my.foo: configured
        logging.getLogger().removeHandler(h)
        logger.warning('unconfigured again')  # LOGS: unconfigured again

    check_logs(test)


def test_z2_stays_off_per_logger() -> None:
    """
    kloggy only steps aside for loggers logging was configured for.
    Other loggers in the same package keep kloggy output, also after the app's handler is removed.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        plan = get_logger('my.plan')
        other = get_logger('my.other')
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter('APP %(name)s: %(message)s'))
        logging.getLogger('my.plan').addHandler(h)
        plan.warning('configured')  # LOGS: APP my.plan: configured
        other.info('not configured')  # LOGS: KLOGGY INFO my.other: not configured
        logging.getLogger('my.plan').removeHandler(h)
        plan.warning('unconfigured again')  # LOGS: unconfigured again
        other.info('still not configured')  # LOGS: KLOGGY INFO my.other: still not configured

    check_logs(test)


CONFIGURATION_CHANGES = {
    # the app's handler on root, root at DEBUG
    'debug': (
        logging.DEBUG,
        [
            # no 'during the change': kloggy stepped aside during the level check, and stdlib's logging.lastResort only shows warnings
            'APP DEBUG my.foo: after 1',
            'APP DEBUG my.foo: after 2',
            'APP WARNING my.foo: some warning',
        ],
    ),
    # the app's handler on the module's own logger, root at WARNING
    'info': (
        logging.INFO,
        [
            # no 'after 1' or 'after 2': the app's effective level is WARNING
            'APP WARNING my.foo: some warning',
        ],
    ),
}


@pytest.mark.parametrize(('level', 'expected'), CONFIGURATION_CHANGES.values(), ids=CONFIGURATION_CHANGES.keys())
def test_z2_configuration_changes_during_level_check(level: int, expected: list[str]) -> None:
    """
    If logging stops being configured right in the middle of a level check (e.g. another thread removes the app's handler),
      kloggy has stepped aside for good: once the handler is back, the app's levels apply.
    Stdlib caches level checks and only clears the cache on setLevel(), so kloggy's loggers don't use that cache until they step aside.
    """

    def test(*, level: int) -> None:
        import logging
        import threading
        from unittest.mock import patch

        import kloggy
        from kloggy import get_logger

        logging.getLogger().setLevel(logging.DEBUG if level == logging.DEBUG else logging.WARNING)
        logger = get_logger('my.foo')
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter('APP %(levelname)s %(name)s: %(message)s'))
        target = logging.getLogger() if level == logging.DEBUG else logger
        target.addHandler(h)

        checked = threading.Event()
        resume = threading.Event()
        original = kloggy._is_configured
        calls: list[bool] = []

        def pause_after_first_check(logger: logging.Logger) -> bool:
            result = original(logger)
            if len(calls) == 0:
                calls.append(result)
                checked.set()
                assert resume.wait(timeout=5)
            return result

        with patch.object(kloggy, '_is_configured', pause_after_first_check):
            t = threading.Thread(target=logger.log, args=(level, 'during the change'))
            t.start()
            assert checked.wait(timeout=5)
            target.removeHandler(h)  # logging stops being configured in the middle of the level check
            resume.set()
            t.join(timeout=5)
            assert not t.is_alive()
        assert calls == [True]

        target.addHandler(h)
        logger.log(level, 'after 1')
        logger.log(level, 'after 2')
        logger.warning('some warning')

    assert run(test, level=level) == expected


def test_z3_stray_call_before() -> None:
    """
    A stray `logging.warning()` before kloggy sets up implicitly calls `basicConfig()`, but doesn't stop kloggy from setting up.
    kloggy's records aren't duplicated by root's default handler.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        # LOGS: WARNING:root:stray
        logging.warning('stray')  # noqa: LOG015 - deliberately tests implicit basicConfig()
        logger = get_logger('my.foo')
        logger.warning('some warning')  # LOGS: KLOGGY WARNING my.foo: some warning

    check_logs(test)


def test_z3_stray_call_after() -> None:
    """
    A stray `logging.warning()` after kloggy set up doesn't switch kloggy off.
    kloggy's records are printed once, while other loggers' records still go to root's default handler.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        logger = get_logger('my.foo')
        logger.warning('before')  # LOGS: KLOGGY WARNING my.foo: before
        # LOGS: WARNING:root:stray
        logging.warning('stray')  # noqa: LOG015 - deliberately tests implicit basicConfig()
        # printed once, not again by root's default handler
        logger.warning('after')  # LOGS: KLOGGY WARNING my.foo: after
        # root's default handler still prints everything else
        logging.getLogger('other').warning('not kloggy')  # LOGS: WARNING:other:not kloggy
        assert logging.getLogger().handlers[0].filters == []  # kloggy doesn't touch root's handler

    check_logs(test)


@pytest.mark.parametrize('setup', ['force', 'customised'])
def test_z3_configured_after_stray_call(setup: str) -> None:
    """
    Explicitly configuring logging after a stray call still switches kloggy off,
      either via `basicConfig(force=True)` or by customising the handler the stray call created.
    The filter kloggy added to that handler doesn't drop anything then.
    """

    def configure(*, setup: str) -> None:
        import logging

        if setup == 'force':
            logging.basicConfig(force=True, format='APP %(levelname)s %(name)s: %(message)s')
        else:
            assert setup == 'customised', setup
            # e.g. the app customising the handler a stray call created
            logging.getLogger().handlers[0].setFormatter(logging.Formatter('APP %(levelname)s %(name)s: %(message)s'))

    def test(*, configure: Callable[..., None], setup: str) -> None:
        import logging

        from kloggy import get_logger

        logger = get_logger('my.foo')
        # LOGS: WARNING:root:stray
        logging.warning('stray')  # noqa: LOG015 - deliberately tests implicit basicConfig()
        logger.warning('before')  # LOGS: KLOGGY WARNING my.foo: before
        configure(setup=setup)
        logger.warning('after')  # LOGS: APP WARNING my.foo: after

    check_logs(test, configure=configure, setup=setup)


def test_z3_explicit_bare_basic_config() -> None:
    """
    Accepted misfire: an explicit bare `basicConfig()` looks the same as one called implicitly by a stray call, so kloggy stays on.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        logging.basicConfig()
        logger = get_logger('my.foo')
        logger.warning('some warning')  # LOGS: KLOGGY WARNING my.foo: some warning

    check_logs(test)


def test_z3_stray_call_keeps_info() -> None:
    """
    Root's default `basicConfig()` handler doesn't count as configured for levels either,
      so INFO keeps showing after a stray `logging.warning()`, printed once.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        logger = get_logger('my.foo')
        # LOGS: WARNING:root:stray
        logging.warning('stray')  # noqa: LOG015 - deliberately tests implicit basicConfig()
        logger.info('some info')  # LOGS: KLOGGY INFO my.foo: some info

    check_logs(test)


def test_z4_replaced_stderr() -> None:
    """
    kloggy writes to whatever sys.stderr is at the moment, like stdlib's logging.lastResort, even if it was replaced after get_logger().
    E.g. contextlib.redirect_stderr, pytest's capsys, or a rich progress bar.
    """

    def test() -> None:
        import contextlib
        import io

        from kloggy import get_logger

        logger = get_logger('pkg.mod')
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            logger.warning('redirected')
        logger.warning('not redirected')  # LOGS: KLOGGY WARNING pkg.mod: not redirected
        assert captured.getvalue() == 'KLOGGY WARNING pkg.mod: redirected\n', captured.getvalue()

    check_logs(test)


@pytest.mark.parametrize('replaced_with', ['terminal', 'file'])
def test_z4_colour_follows(replaced_with: str) -> None:
    """
    Colour (F2) follows the current sys.stderr too: a terminal gets colour, a file doesn't,
      regardless of what sys.stderr was when kloggy set up.
    """

    def test(*, replaced_with: str) -> None:
        import contextlib
        import io
        import sys

        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        from kloggy import get_logger

        # for 'file', kloggy sets up on a terminal, which then gets replaced by a file
        initial = Terminal() if replaced_with == 'file' else sys.stderr
        replacement = Terminal() if replaced_with == 'terminal' else io.StringIO()
        with contextlib.redirect_stderr(initial):
            logger = get_logger('pkg.mod')
            with contextlib.redirect_stderr(replacement):
                logger.warning('some warning')
        output = replacement.getvalue()
        assert 'some warning' in output, repr(output)
        assert output.startswith('\x1b[') == (replaced_with == 'terminal'), repr(output)

    run(test, test_format=False, replaced_with=replaced_with)


def test_z4_not_kept_alive() -> None:
    """
    Once sys.stderr is switched back, kloggy doesn't hold on to the replacement, so e.g. a buffer with lots of captured output can be freed.
    """

    def test() -> None:
        import contextlib
        import gc
        import io
        import weakref

        from kloggy import get_logger

        logger = get_logger('pkg.mod')
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            logger.warning('redirected')
        ref = weakref.ref(captured)
        del captured
        gc.collect()
        assert ref() is None

    check_logs(test)


def test_z4_rich() -> None:
    """
    A rich progress bar doesn't mangle kloggy's output: it goes through rich, which prints each line above the bar.
    Otherwise each line would be glued onto a frozen copy of the bar.
    Also for records with several lines, e.g. with a traceback.
    """

    def test(*, terminal_screen: Callable[[str], list[str]], rich_console: Callable[[TextIO], Console]) -> None:
        import contextlib
        import io

        from rich.progress import Progress

        from kloggy import get_logger

        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        def fail() -> None:
            raise ValueError('boom')

        # one terminal, which both kloggy (via sys.stderr) and rich write to, like in practice
        terminal = Terminal()
        with contextlib.redirect_stderr(terminal):
            logger = get_logger('pkg.mod')  # before the progress bar starts, like a module-level logger
            # no auto refresh, so rich doesn't start a thread for it, and this is all synchronous
            with Progress(console=rich_console(terminal), auto_refresh=False) as progress:
                task = progress.add_task('processing', total=3)
                for item in range(3):
                    if item == 1:
                        try:
                            fail()
                        except ValueError:
                            logger.exception('item %d failed', item)
                    else:
                        logger.info('item %d', item)
                    progress.advance(task)

        *logged, bar = terminal_screen(terminal.getvalue())
        assert logged[:3] == [
            'KLOGGY INFO pkg.mod: item 0',
            'KLOGGY ERROR pkg.mod: item 1 failed',
            'Traceback (most recent call last):',
        ], logged
        assert logged[-2:] == ['ValueError: boom', 'KLOGGY INFO pkg.mod: item 2'], logged
        # no progress bars interleaved with the log lines, e.g. frozen copies of the bar, or log lines glued onto one
        # rich draws its bars with '━', also the unfinished part
        assert not any('━' in line for line in logged), logged
        # a single bar, at the bottom, with nothing glued onto it
        assert bar.startswith('processing ━'), bar
        assert bar.endswith('100% 0:00:00'), bar

    check_logs(test, terminal_screen=terminal_screen, rich_console=rich_console)


def test_z27_no_deadlock_with_dict_config() -> None:
    """
    kloggy's handler never waits for logging's module lock while holding its own lock.
    `dictConfig()` holds the module lock while it acquires every handler's lock, so logging from another thread could deadlock otherwise.
    """

    def test() -> None:
        import logging
        import threading

        from kloggy import get_logger

        logger = get_logger('my.foo')
        [handler] = logging.getLogger('my').handlers
        assert handler.lock is not None
        # caches the level check, which would otherwise wait for the module lock before any handler
        logger.warning('some warning')
        with getattr(logging, '_lock'):  # what dictConfig() holds while it acquires the handlers' locks
            t = threading.Thread(target=logger.warning, args=('some warning',))
            t.start()
            t.join(timeout=0.5)  # the thread blocks on the module lock
            assert handler.lock.acquire(timeout=5)
            handler.lock.release()
        t.join()

    run(test)
