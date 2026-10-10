"""
Z: output when logging isn't configured, i.e. kloggy's fallback handler.
"""

import logging
from collections.abc import Callable

import pytest

from .common import check_logs, run


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
