"""
V: verbosity, i.e. level control.
"""

import pytest

from .common import check_logs


def test_v1_default() -> None:
    """
    A level without a logger name is the default for each package using kloggy.
    """

    def test() -> None:
        import os

        os.environ['KLOGGY_LEVEL'] = 'debug'

        from kloggy import get_logger

        get_logger('pkg.mod').debug('some debug')  # LOGS: KLOGGY DEBUG pkg.mod: some debug
        get_logger('other.mod').debug('other debug')  # LOGS: KLOGGY DEBUG other.mod: other debug

    check_logs(test)


def test_v1_entries() -> None:
    """
    Other entries set the level of a specific logger, hierarchically, and the most specific one wins regardless of order.
    """

    def test() -> None:
        import os

        os.environ['KLOGGY_LEVEL'] = 'pkg.sub=debug,pkg=warning,error'

        from kloggy import get_logger

        get_logger('pkg.sub.mod').debug('sub debug')  # LOGS: KLOGGY DEBUG pkg.sub.mod: sub debug
        get_logger('pkg.other').info('other info')  # pkg=warning beats the default
        get_logger('pkg.other').warning('other warning')  # LOGS: KLOGGY WARNING pkg.other: other warning

    check_logs(test)


def test_v1_other_packages() -> None:
    """
    Packages which don't use kloggy aren't affected, even if they're named in the spec.
    Once they call get_logger(), they are.
    """

    def test() -> None:
        import logging
        import os

        os.environ['KLOGGY_LEVEL'] = 'debug,third=info'

        from kloggy import get_logger

        get_logger('pkg.mod')
        third = logging.getLogger('third')
        assert third.level == logging.NOTSET, third.level
        third.info('third info')  # stdlib's default WARNING
        get_logger('third.mod')
        assert third.level == logging.INFO, third.level

    check_logs(test)


def test_v1_level_names() -> None:
    """
    Level names are case-insensitive, `warn` works too, and `off` silences a logger completely, like RUST_LOG.
    """

    def test() -> None:
        import logging
        import os

        os.environ['KLOGGY_LEVEL'] = 'Warn,pkg.a=DEBUG,pkg.b=info,pkg.noisy=OFF'

        from kloggy import get_logger

        get_logger('pkg.mod')
        levels = [logging.getLogger(name).level for name in ['pkg', 'pkg.a', 'pkg.b']]
        assert levels == [logging.WARNING, logging.DEBUG, logging.INFO], levels
        get_logger('pkg.noisy').critical('some critical')

    check_logs(test)


def test_v1_later_wins() -> None:
    """
    A later entry for the same logger wins, and empty entries (e.g. a trailing comma) are skipped, like RUST_LOG.
    """

    def test() -> None:
        import logging
        import os
        import warnings

        os.environ['KLOGGY_LEVEL'] = 'debug,pkg.sub=debug,,info,pkg.sub=warning,'

        from kloggy import get_logger

        with warnings.catch_warnings():
            warnings.simplefilter('error')
            get_logger('pkg.mod')
        levels = [logging.getLogger(name).level for name in ['pkg', 'pkg.sub']]
        assert levels == [logging.INFO, logging.WARNING], levels

    check_logs(test)


@pytest.mark.parametrize(
    'entry',
    [
        'debgu',  # unknown level
        'pkg=',
        '=debug',
        'pkg=debug=info',
    ],
)
def test_v1_invalid(entry: str) -> None:
    """
    Invalid entries are ignored with a warning naming KLOGGY_LEVEL, like RUST_LOG, and the rest of the spec still applies.
    """

    def test(*, entry: str) -> None:
        import logging
        import os
        import warnings

        import pytest

        os.environ['KLOGGY_LEVEL'] = f'{entry},pkg.sub=debug'

        from kloggy import get_logger

        with pytest.warns(UserWarning, match='KLOGGY_LEVEL: ignoring'):
            get_logger('pkg.mod')
        assert logging.getLogger('pkg.sub').level == logging.DEBUG
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            get_logger('other.mod')  # the spec is only read once, so it doesn't warn for every package

    check_logs(test, entry=entry)


@pytest.mark.parametrize('order', ['before', 'after'])
def test_v1_app_configured(order: str) -> None:
    """
    The levels apply even if the app configures logging, before or after the package calls get_logger().
    """

    def test(*, order: str) -> None:
        import logging
        import os

        os.environ['KLOGGY_LEVEL'] = 'debug'

        from kloggy import get_logger

        if order == 'before':
            logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        logger = get_logger('pkg.mod')
        if order == 'after':
            logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        logger.debug('some debug')  # LOGS: APP DEBUG pkg.mod: some debug

    check_logs(test, order=order)


def test_v1_app_set_level_later() -> None:
    """
    The levels are set when a package first calls get_logger(), so the app's own setLevel() after that wins.
    """

    def test() -> None:
        import logging
        import os

        os.environ['KLOGGY_LEVEL'] = 'debug'

        from kloggy import get_logger

        logger = get_logger('pkg.mod')
        logger.debug('debug before')  # LOGS: KLOGGY DEBUG pkg.mod: debug before
        logging.getLogger('pkg').setLevel(logging.WARNING)
        get_logger('pkg.other')  # another module of the package doesn't set the levels again
        logger.debug('debug after')
        logger.warning('some warning')  # LOGS: KLOGGY WARNING pkg.mod: some warning

    check_logs(test)


def test_v1_app_set_level_before() -> None:
    """
    Levels set before the package calls get_logger(), e.g. by the app, aren't overridden either.
    """

    def test() -> None:
        import logging
        import os

        os.environ['KLOGGY_LEVEL'] = 'debug,pkg.sub=debug'

        logging.getLogger('pkg').setLevel(logging.WARNING)
        logging.getLogger('pkg.sub').setLevel(logging.ERROR)

        from kloggy import get_logger

        get_logger('pkg.mod').info('mod info')
        get_logger('pkg.mod').warning('mod warning')  # LOGS: KLOGGY WARNING pkg.mod: mod warning
        get_logger('pkg.sub').warning('sub warning')
        get_logger('pkg.sub').error('sub error')  # LOGS: KLOGGY ERROR pkg.sub: sub error

    check_logs(test)
