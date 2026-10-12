"""
L: library-side behaviour.
"""

from collections.abc import Callable

import pytest

from .common import check_logs, check_logs_same_as_stdlib_once_configured, run, run_same_as_stdlib


@pytest.mark.parametrize('setup', ['root', 'root_level', 'package', 'null'])
def test_l1_configured_before_untouched(setup: str) -> None:
    """
    If the app configured logging before kloggy sets up the package logger, kloggy leaves it alone.
    The package logger keeps its handlers and level, and output is the same as with plain stdlib loggers.
    """

    # ways the app may have configured logging before kloggy sets up the 'my' package logger
    def configure(*, setup: str) -> None:
        import logging

        if setup == 'root':
            logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        elif setup == 'root_level':
            logging.basicConfig(level=logging.ERROR)
        elif setup == 'package':
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter('PKG %(name)s: %(message)s'))
            logging.getLogger('my').addHandler(h)
        else:
            assert setup == 'null', setup
            logging.getLogger('my').addHandler(logging.NullHandler())

    expected = {
        'root': [
            'APP WARNING my.foo: some warning',
            'APP ERROR my.foo: some error',
        ],
        'root_level': [
            'ERROR:my.foo:some error',
        ],
        'package': [
            'PKG my.foo: some warning',
            'PKG my.foo: some error',
        ],
        'null': [],
    }[setup]

    def test(*, configure: Callable[..., None], setup: str, use_kloggy: bool) -> None:
        import logging

        from kloggy import get_logger

        configure(setup=setup)
        handlers_before = list(logging.getLogger('my').handlers)

        getter = get_logger if use_kloggy else logging.getLogger
        logger = getter('my.foo')

        package = logging.getLogger('my')
        assert type(logger) is logging.Logger, type(logger)
        assert package.handlers == handlers_before, package.handlers
        assert package.level == logging.NOTSET, package.level
        logger.warning('some warning')
        logger.error('some error')

    assert run_same_as_stdlib(test, configure=configure, setup=setup) == expected


def test_l2_info_by_default() -> None:
    """
    Without any configuration, everything from INFO up from `get_logger()` loggers is shown (e.g. INFO for a sense of progress), DEBUG isn't.
    """

    def test() -> None:
        from kloggy import get_logger

        logger = get_logger('my.foo')
        logger.debug('some debug')
        logger.info('some info')  # LOGS: KLOGGY INFO my.foo: some info
        logger.warning('some warning')  # LOGS: KLOGGY WARNING my.foo: some warning
        logger.error('some error')  # LOGS: KLOGGY ERROR my.foo: some error
        logger.critical('some critical')  # LOGS: KLOGGY CRITICAL my.foo: some critical

    check_logs(test)


def test_l3_configured_after() -> None:
    """
    If the app configures logging after `get_logger()` (e.g. `basicConfig()` in `main()` after imports),
      the app's levels apply straight away.
    """

    def test(*, use_kloggy: bool) -> None:
        import logging
        import sys

        from kloggy import get_logger

        logger = (get_logger if use_kloggy else logging.getLogger)('my.foo')
        logger.info('before 1')  # LOGS: KLOGGY INFO my.foo: before 1
        logger.info('before 2')  # LOGS: KLOGGY INFO my.foo: before 2
        logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        print('--- configured', file=sys.stderr)  # LOGS: --- configured
        logger.info('after 1')  # INFO right after configuration isn't let through
        logger.info('after 2')  # INFO right after configuration isn't let through
        logger.warning('some warning')  # LOGS: APP WARNING my.foo: some warning
        assert logging.getLogger('my').level == logging.NOTSET

    check_logs_same_as_stdlib_once_configured(test)


def test_l3_configured_after_plain_logger() -> None:
    """
    Same as test_l3_configured_after, for a module in the package which uses plain `logging.getLogger()` instead of `get_logger()`.
    It keeps stdlib's levels (no INFO by default), so there's no stray record in the first place.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        get_logger('my.foo')
        logger = logging.getLogger('my.plain')
        logger.info('before 1')  # a plain logger keeps stdlib's levels, so no INFO
        logger.info('before 2')
        logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        logger.info('after 1')  # no stray INFO either
        logger.info('after 2')
        logger.warning('some warning')  # LOGS: APP WARNING my.plain: some warning
        assert logging.getLogger('my').level == logging.NOTSET

    check_logs(test)


def test_l3_configured_after_on_module_logger() -> None:
    """
    Same as test_l3_configured_after, but the app attaches its handler to the module's own logger instead of root.
    That handler sees records before kloggy's handler on the package logger does,
      but the stray record isn't created in the first place.
    """

    def test(*, use_kloggy: bool) -> None:
        import logging
        import sys

        from kloggy import get_logger

        logger = (get_logger if use_kloggy else logging.getLogger)('my.foo')
        logger.info('before 1')  # LOGS: KLOGGY INFO my.foo: before 1
        logger.info('before 2')  # LOGS: KLOGGY INFO my.foo: before 2
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter('APP %(levelname)s %(name)s: %(message)s'))
        logger.addHandler(h)
        print('--- configured', file=sys.stderr)  # LOGS: --- configured
        logger.info('after 1')  # INFO right after configuration isn't let through
        logger.info('after 2')  # INFO right after configuration isn't let through
        logger.warning('some warning')  # LOGS: APP WARNING my.foo: some warning
        assert logging.getLogger('my').level == logging.NOTSET

    check_logs_same_as_stdlib_once_configured(test)


def test_l3_configured_after_on_module_logger_plain_logger() -> None:
    """
    Same as test_l3_configured_after_on_module_logger, but for a plain `logging.getLogger()` logger.
    It keeps stdlib's levels (no INFO by default), so there's no stray record in the first place.
    Warnings use kloggy's fallback before configuration and the app's handler afterwards, without duplicates.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        get_logger('my.foo')  # kloggy sets up
        logger = logging.getLogger('my.plain')
        logger.info('before 1')  # a plain logger keeps stdlib's levels, so no INFO
        logger.info('before 2')
        logger.warning('before')  # LOGS: KLOGGY WARNING my.plain: before
        logger.addHandler(logging.StreamHandler())  # the app's handler, prints bare messages
        logger.info('after 1')  # no stray INFO either
        logger.info('after 2')
        logger.warning('after')  # LOGS: after

    check_logs(test)


def test_l3_configured_after_more_verbose() -> None:
    """
    If the app asks for more than INFO after `get_logger()` (e.g. `basicConfig(level=DEBUG)` in `main()` after imports),
      DEBUG records show up straight away.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        logger = get_logger('my.foo')
        logger.debug('debug before configuration')  # kloggy's default is INFO
        logging.basicConfig(level=logging.DEBUG, format='APP %(levelname)s %(name)s: %(message)s')
        logger.debug('debug 1')  # LOGS: APP DEBUG my.foo: debug 1
        # DEBUG doesn't depend on a record at INFO or above passing through first
        logger.info('some info')  # LOGS: APP INFO my.foo: some info
        logger.debug('debug 2')  # LOGS: APP DEBUG my.foo: debug 2

    check_logs(test)


def test_l3_configured_after_on_subpackage() -> None:
    """
    Whether logging is configured is decided per logger, so the app taking over one subpackage doesn't affect the others.
    Here the app attaches its handler to `my.reddit` only, which `my.reddit.rexport` records reach via that intermediate logger,
      while `my.other` is still printed by kloggy, with INFO by default.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        rexport = get_logger('my.reddit.rexport')
        other = get_logger('my.other')
        rexport.info('before takeover')  # LOGS: KLOGGY INFO my.reddit.rexport: before takeover
        # the app takes over my.reddit, prints bare messages
        logging.getLogger('my.reddit').addHandler(logging.StreamHandler())
        rexport.info('rexport info')  # my.reddit is configured, so stdlib's levels apply there
        rexport.warning('rexport warning')  # LOGS: rexport warning
        other.info('other info')  # LOGS: KLOGGY INFO my.other: other info
        other.warning('other warning')  # LOGS: KLOGGY WARNING my.other: other warning

    check_logs(test)


def test_l3_concurrent() -> None:
    """
    Several threads making their first logging calls after the app configures logging use its levels immediately.
    The barrier releases the threads before the level check, so each INFO call must be suppressed.
    """

    def test() -> None:
        import logging
        import threading

        from kloggy import get_logger

        logger = get_logger('my.foo')
        logger.info('before configuration')  # LOGS: KLOGGY INFO my.foo: before configuration
        barrier = threading.Barrier(4)

        def work() -> None:
            barrier.wait(timeout=5)
            logger.info('stray info')

        logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        threads = [threading.Thread(target=work) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        logger.warning('some warning')  # LOGS: APP WARNING my.foo: some warning

    check_logs(test)


def test_l2_level_changed_since() -> None:
    """
    If someone sets the package logger's level after `get_logger()`, it applies.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        logger = get_logger('my.foo')
        logging.getLogger('my').setLevel(logging.DEBUG)
        logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        logger.debug('some debug')  # LOGS: APP DEBUG my.foo: some debug
        assert logging.getLogger('my').level == logging.DEBUG

    check_logs(test)


def test_l2_explicit_level() -> None:
    """
    Levels set explicitly (e.g. by the app before importing the library) apply while logging isn't configured too,
      e.g. DEBUG for one module, or WARNING for the whole package.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        logging.getLogger('my.foo').setLevel(logging.DEBUG)
        logging.getLogger('my').setLevel(logging.WARNING)
        foo = get_logger('my.foo')
        bar = get_logger('my.bar')
        assert len(logging.getLogger('my').handlers) == 1
        foo.debug('foo debug')  # LOGS: KLOGGY DEBUG my.foo: foo debug
        bar.info('bar info')  # WARNING is set for the whole package
        bar.warning('bar warning')  # LOGS: KLOGGY WARNING my.bar: bar warning

    check_logs(test)


def test_l2_app_logger_class() -> None:
    """
    If the app installed its own logger class (`logging.setLoggerClass()`), loggers from `get_logger()` keep its behaviour.
    """

    def test() -> None:
        import logging

        class AppLogger(logging.Logger):
            def app_method(self) -> str:
                return 'app method'

        logging.setLoggerClass(AppLogger)
        from kloggy import get_logger

        logger = get_logger('my.foo')
        assert isinstance(logger, AppLogger)
        assert logger.app_method() == 'app method'
        logger.info('some info')  # LOGS: KLOGGY INFO my.foo: some info

    check_logs(test)


def test_l2_plain_logger() -> None:
    """
    Plain `logging.getLogger()` loggers in the package keep stdlib's levels, so no INFO by default: they never asked kloggy for anything.
    Their records still reach kloggy's handler on the package logger, so kloggy prints them while logging isn't configured (Z1).
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        get_logger('my.foo')
        logger = logging.getLogger('my.plain')
        logger.info('some info')  # a plain logger keeps stdlib's levels
        logger.warning('some warning')  # LOGS: KLOGGY WARNING my.plain: some warning
        logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        logger.info('info after configuration')  # same
        logger.warning('warning after configuration')  # LOGS: APP WARNING my.plain: warning after configuration

    check_logs(test)


def test_l3_created_before_configured() -> None:
    """
    Records created at kloggy's INFO just before the app configured logging, but reaching the handlers after, are dropped.
    Warnings created at the same time still reach the app's handlers.
    The app's filter on the module logger holds them until the app has configured logging.
    """

    def test() -> None:
        import logging
        import threading

        from kloggy import get_logger

        logger = get_logger('my.foo')
        created = threading.Barrier(9)  # 8 threads + main
        configured = threading.Event()

        def hold(_record: logging.LogRecord) -> bool:
            created.wait(timeout=5)
            return configured.wait(timeout=5)

        logger.addFilter(hold)
        threads = [
            *(threading.Thread(target=logger.info, args=('info created before configuration',)) for _ in range(4)),
            *(
                threading.Thread(target=logger.warning, args=('warning created before configuration',))
                for _ in range(4)
            ),
        ]
        for t in threads:
            t.start()
        created.wait(timeout=5)  # all records exist, and logging isn't configured yet
        logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        configured.set()
        for t in threads:
            t.join()
        logger.removeFilter(hold)
        logger.warning('some warning')

    assert run(test) == [
        # no 'info created before configuration': the app's effective level is WARNING
        'APP WARNING my.foo: warning created before configuration',
        'APP WARNING my.foo: warning created before configuration',
        'APP WARNING my.foo: warning created before configuration',
        'APP WARNING my.foo: warning created before configuration',
        'APP WARNING my.foo: some warning',
    ]


def test_l3_effective_level() -> None:
    """
    `getEffectiveLevel()` agrees with what's shown: INFO while logging isn't configured, the app's level once it is.
    It's always a plain int, e.g. HPI passes it on to logzero-based libraries.
    """

    def test() -> None:
        import logging
        import sys

        from kloggy import get_logger

        logger = get_logger('my.foo')
        level = logger.getEffectiveLevel()
        print('unconfigured:', level, type(level).__name__, file=sys.stderr)  # LOGS: unconfigured: 20 int
        logging.basicConfig(level=logging.DEBUG)
        level = logger.getEffectiveLevel()
        print('configured:', level, type(level).__name__, file=sys.stderr)  # LOGS: configured: 10 int

    check_logs(test)


def test_l6_default_level() -> None:
    """
    A module's default level replaces INFO for its logger while logging isn't configured, also for its child loggers.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        logger = get_logger('pkg.mod', default_level='warning')
        logger.info('mod info')
        logger.warning('mod warning')  # LOGS: KLOGGY WARNING pkg.mod: mod warning
        assert logger.getEffectiveLevel() == logging.WARNING, logger.getEffectiveLevel()
        get_logger('pkg.mod.sub').info('sub info')
        get_logger('pkg.other').info('other info')  # LOGS: KLOGGY INFO pkg.other: other info

    check_logs(test)


def test_l6_nearest_default() -> None:
    """
    The nearest default wins, e.g. a module can be more verbose than its package, and `logging` constants work too.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        get_logger('pkg', default_level=logging.ERROR)
        get_logger('pkg.mod', default_level=logging.DEBUG).debug('mod debug')  # LOGS: KLOGGY DEBUG pkg.mod: mod debug
        get_logger('pkg.other').warning('other warning')
        get_logger('pkg.other').error('other error')  # LOGS: KLOGGY ERROR pkg.other: other error

    check_logs(test)


def test_l6_other_code() -> None:
    """
    It applies to records other code logs through the module's logger too, e.g. cachew logs through the decorated function's module logger.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        get_logger('pkg.mod', default_level='warning')
        # same logger object as the module's
        logging.getLogger('pkg.mod').info('loading 100 objects from cachew')
        logging.getLogger('pkg.mod').warning('cachew warning')  # LOGS: KLOGGY WARNING pkg.mod: cachew warning

    check_logs(test)


def test_l6_explicit_level() -> None:
    """
    Levels set explicitly, on the logger or an ancestor below root, beat the default.
    Also when set before the module is imported, e.g. with lazy imports or pytest's `caplog`, which a plain `setLevel()` in the module would overwrite.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        # before the modules call get_logger(), e.g. imported lazily
        logging.getLogger('pkg.a').setLevel(logging.DEBUG)
        logging.getLogger('pkg.b').setLevel(logging.DEBUG)
        get_logger('pkg.a', default_level='warning').debug('a debug')  # LOGS: KLOGGY DEBUG pkg.a: a debug
        # the explicit level is further up than the default, and still wins
        get_logger('pkg.b.mod', default_level='warning').debug('b debug')  # LOGS: KLOGGY DEBUG pkg.b.mod: b debug
        # after
        c = get_logger('pkg.c', default_level='warning')
        logging.getLogger('pkg.c').setLevel(logging.DEBUG)
        c.debug('c debug')  # LOGS: KLOGGY DEBUG pkg.c: c debug

    check_logs(test)


@pytest.mark.parametrize('spec', ['debug', 'pkg.mod=debug'])
def test_l6_kloggy_level(spec: str) -> None:
    """
    `KLOGGY_LEVEL` sets explicit levels, so it beats the default, e.g. `KLOGGY_LEVEL=debug` shows everything.
    """

    def test(*, spec: str) -> None:
        import os

        os.environ['KLOGGY_LEVEL'] = spec

        from kloggy import get_logger

        get_logger('pkg.mod', default_level='warning').debug('mod debug')  # LOGS: KLOGGY DEBUG pkg.mod: mod debug

    check_logs(test, spec=spec)


def test_l6_app_configured() -> None:
    """
    Once the app configures logging, the app's levels apply, same as for INFO (L3).
    """

    def test(*, use_kloggy: bool) -> None:
        import logging
        import sys

        from kloggy import get_logger

        logger = get_logger('pkg.mod', default_level='warning') if use_kloggy else logging.getLogger('pkg.mod')
        logger.info('info before')  # below the module's default
        logging.basicConfig(level=logging.INFO, format='APP %(levelname)s %(name)s: %(message)s')
        print('--- configured', file=sys.stderr)  # LOGS: --- configured
        logger.info('info after')  # LOGS: APP INFO pkg.mod: info after

    check_logs_same_as_stdlib_once_configured(test)


def test_l6_last_wins() -> None:
    """
    If several calls pass different defaults for the same logger, the last one wins, and calls without one keep it.
    """

    def test() -> None:
        from kloggy import get_logger

        get_logger('pkg.mod', default_level='warning')
        get_logger('pkg.mod', default_level='error')
        logger = get_logger('pkg.mod')
        logger.warning('mod warning')
        logger.error('mod error')  # LOGS: KLOGGY ERROR pkg.mod: mod error

    check_logs(test)


def test_l6_invalid() -> None:
    """
    An unknown level name is an error, since it's a bug in the code rather than e.g. a typo in an env variable.
    """

    def test() -> None:
        import pytest

        from kloggy import get_logger

        with pytest.raises(AssertionError, match='loud'):
            get_logger('pkg.mod', default_level='loud')

    check_logs(test)


@pytest.mark.parametrize('name', ['', None, 'root'])
def test_l7_root_logger(name: str | None) -> None:
    """
    `get_logger()` refuses the names stdlib maps to the root logger, e.g. `__package__` is `''` under `python -m`, and `None` in a script run directly.
    """

    def test(*, name: str | None) -> None:
        import pytest

        from kloggy import get_logger

        with pytest.raises(AssertionError, match='needs a module name'):
            get_logger(name)  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]

    check_logs(test, name=name)


def test_l7_disabled() -> None:
    """
    With `KLOGGY_DISABLE`, `get_logger()` is plain `logging.getLogger()`, without the check (L5).
    """

    def test() -> None:
        import logging
        import os

        os.environ['KLOGGY_DISABLE'] = '1'

        from kloggy import get_logger

        assert get_logger('') is logging.getLogger()

    check_logs(test)
