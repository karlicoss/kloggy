"""
L: library-side behaviour.
"""

from collections.abc import Callable

import pytest

from .common import check_logs, run


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

    with_kloggy = run(test, configure=configure, setup=setup, use_kloggy=True)
    without_kloggy = run(test, configure=configure, setup=setup, use_kloggy=False)
    assert with_kloggy == without_kloggy == expected


def test_l2_info_by_default() -> None:
    """
    Without any configuration, everything from INFO up from kloggy loggers is shown (e.g. INFO for a sense of progress), DEBUG isn't.
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
    If the app configures logging after kloggy set up (e.g. `basicConfig()` in `main()` after imports),
      the app's levels apply straight away.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        logger = get_logger('my.foo')
        logger.info('before 1')  # LOGS: KLOGGY INFO my.foo: before 1
        logger.info('before 2')  # LOGS: KLOGGY INFO my.foo: before 2
        logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        logger.info('after 1')  # INFO right after configuration isn't let through
        logger.info('after 2')  # INFO right after configuration isn't let through
        logger.warning('some warning')  # LOGS: APP WARNING my.foo: some warning
        assert logging.getLogger('my').level == logging.NOTSET

    check_logs(test)


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

    def test() -> None:
        import logging

        from kloggy import get_logger

        logger = get_logger('my.foo')
        logger.info('before 1')  # LOGS: KLOGGY INFO my.foo: before 1
        logger.info('before 2')  # LOGS: KLOGGY INFO my.foo: before 2
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter('APP %(levelname)s %(name)s: %(message)s'))
        logger.addHandler(h)
        logger.info('after 1')  # INFO right after configuration isn't let through
        logger.info('after 2')  # INFO right after configuration isn't let through
        logger.warning('some warning')  # LOGS: APP WARNING my.foo: some warning
        assert logging.getLogger('my').level == logging.NOTSET

    check_logs(test)


def test_l3_configured_after_on_module_logger_plain_logger() -> None:
    """
    Same as test_l3_configured_after_on_module_logger, but for a plain `logging.getLogger()` logger.
    It keeps stdlib's levels (no INFO by default), so there's no stray record in the first place.
    """

    def test() -> None:
        import logging

        from kloggy import get_logger

        get_logger('my.foo')  # kloggy sets up
        logger = logging.getLogger('my.plain')
        logger.info('before 1')  # a plain logger keeps stdlib's levels, so no INFO
        logger.info('before 2')
        logger.addHandler(logging.StreamHandler())  # the app's handler, prints bare messages
        logger.info('after 1')  # no stray INFO either
        logger.info('after 2')
        logger.warning('some warning')  # LOGS: some warning

    check_logs(test)


def test_l3_configured_after_more_verbose() -> None:
    """
    If the app asks for more than INFO after kloggy set up (e.g. `basicConfig(level=DEBUG)` in `main()` after imports),
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
    Several threads logging at once right after the app configured logging don't let INFO through either.
    The app's filter on the module logger would hold any records until all of them were created.
    """

    def test() -> None:
        import logging
        import threading

        from kloggy import get_logger

        get_logger('my.foo')
        logger = logging.getLogger('my.plain')
        barrier = threading.Barrier(4)
        logger.addFilter(lambda _record: barrier.wait(timeout=5) >= 0)
        logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        threads = [threading.Thread(target=logger.info, args=('stray info',)) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        logger.filters.clear()
        logger.warning('some warning')  # LOGS: APP WARNING my.plain: some warning

    check_logs(test)


def test_l2_level_changed_since() -> None:
    """
    If someone sets the package logger's level after kloggy set up, it applies.
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
        import sys

        class AppLogger(logging.Logger):
            def app_method(self) -> str:
                return 'app method'

        logging.setLoggerClass(AppLogger)
        from kloggy import get_logger

        logger = get_logger('my.foo')
        assert isinstance(logger, AppLogger)
        print(isinstance(logger, AppLogger), logger.app_method(), file=sys.stderr)  # LOGS: True app method
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
