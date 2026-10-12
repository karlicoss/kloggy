"""
L5: opting out of kloggy completely via KLOGGY_DISABLE.
"""

import pytest

from .common import check_logs, check_logs_same_as_stdlib


def test_l5_disabled() -> None:
    """
    `KLOGGY_DISABLE=1` makes get_logger() return plain loggers without touching anything, and KLOGGY_LEVEL is ignored.
    So logging behaves exactly as plain stdlib.
    """

    def test(*, use_kloggy: bool) -> None:
        import logging
        import os

        os.environ['KLOGGY_DISABLE'] = '1'
        os.environ['KLOGGY_LEVEL'] = 'debug'

        from kloggy import get_logger

        logger = (get_logger if use_kloggy else logging.getLogger)('pkg.mod')
        assert type(logger) is logging.Logger, type(logger)
        package = logging.getLogger('pkg')
        assert package.handlers == [], package.handlers
        assert package.level == logging.NOTSET, package.level
        logger.debug('some debug')  # KLOGGY_LEVEL is ignored
        logger.info('some info')  # stdlib's default WARNING
        logger.warning('some warning')  # LOGS: some warning
        logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        logger.warning('configured')  # LOGS: APP WARNING pkg.mod: configured

    check_logs_same_as_stdlib(test)


@pytest.mark.parametrize(
    ('value', 'disabled'),
    [
        ('1', True),
        ('true', True),
        ('YES', True),
        ('on', True),
        ('', False),
        ('0', False),
        ('false', False),
        ('No', False),
        ('off', False),
    ],
)
def test_l5_values(value: str, *, disabled: bool) -> None:
    """
    Values follow the usual boolean words (as in systemd), case-insensitive, and empty means not set.
    """

    def test(*, value: str, disabled: bool) -> None:
        import logging
        import os

        os.environ['KLOGGY_DISABLE'] = value

        from kloggy import get_logger

        logger = get_logger('pkg.mod')
        assert (type(logger) is logging.Logger) == disabled, type(logger)

    check_logs(test, value=value, disabled=disabled)


def test_l5_invalid() -> None:
    """
    Anything else is ignored with a warning naming KLOGGY_DISABLE.
    """

    def test() -> None:
        import logging
        import os

        import pytest

        os.environ['KLOGGY_DISABLE'] = 'maybe'

        from kloggy import get_logger

        with pytest.warns(UserWarning, match='KLOGGY_DISABLE: ignoring'):
            logger = get_logger('pkg.mod')
        assert type(logger) is not logging.Logger, type(logger)

    check_logs(test)
