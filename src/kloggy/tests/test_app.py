"""
A: application-side setup.
"""

import re

import pytest

from .common import check_logs, run


def test_a1_setup() -> None:
    """
    setup() gives every logger kloggy's output, also libraries not using kloggy, at INFO by default.
    """

    def test() -> None:
        import logging

        import kloggy

        logger = kloggy.get_logger('pkg.mod')  # before setup(), like a module-level logger
        kloggy.setup()
        logger.info('mod info')  # LOGS: KLOGGY INFO pkg.mod: mod info
        logging.getLogger('other.lib').info('lib info')  # LOGS: KLOGGY INFO other.lib: lib info
        logger.debug('mod debug')

    check_logs(test)


def test_a1_level() -> None:
    """
    The level is root's, so it applies to every logger.
    """

    def test() -> None:
        import logging

        import kloggy

        logger = kloggy.get_logger('pkg.mod')
        kloggy.setup(level='warning')
        logger.info('mod info')
        logging.getLogger('other.lib').info('lib info')
        logger.warning('mod warning')  # LOGS: KLOGGY WARNING pkg.mod: mod warning

    check_logs(test)


def test_a1_default_level() -> None:
    """
    It's an ordinary configuration, so kloggy steps aside, and root's level beats kloggy's own defaults, e.g. a module's default level.
    """

    def test() -> None:
        import kloggy

        logger = kloggy.get_logger('pkg.mod', default_level='warning')
        kloggy.setup()
        logger.info('mod info')  # LOGS: KLOGGY INFO pkg.mod: mod info

    check_logs(test)


def test_a1_kloggy_level() -> None:
    """
    `KLOGGY_LEVEL` still applies, since it sets real levels.
    """

    def test() -> None:
        import logging
        import os

        os.environ['KLOGGY_LEVEL'] = 'pkg=debug'

        import kloggy

        logger = kloggy.get_logger('pkg.mod')
        kloggy.setup()
        logger.debug('mod debug')  # LOGS: KLOGGY DEBUG pkg.mod: mod debug
        logging.getLogger('other.lib').debug('lib debug')

    check_logs(test)


def test_a1_current_stderr() -> None:
    """
    Output goes to the current sys.stderr, e.g. a rich progress bar's, unlike basicConfig()'s handler.
    """

    def test() -> None:
        import contextlib
        import io
        import logging

        import kloggy

        kloggy.setup()
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            logging.getLogger('other.lib').warning('redirected')
        assert captured.getvalue() == 'KLOGGY WARNING other.lib: redirected\n', captured.getvalue()

    check_logs(test)


@pytest.mark.parametrize(
    ('datefmt', 'time'),
    [
        (None, r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}'),
        ('%H:%M:%S', r'\d\d:\d\d:\d\d'),
    ],
)
def test_a1_datefmt(datefmt: str | None, time: str) -> None:
    """
    The time format can be changed as in basicConfig(), e.g. without milliseconds.
    By default it's F1's, with milliseconds.
    """

    def test(*, datefmt: str | None) -> None:
        import logging

        import kloggy

        kloggy.setup(datefmt=datefmt)
        logging.getLogger('other.lib').warning('some warning')

    [line] = run(test, test_format=False, datefmt=datefmt)
    assert re.fullmatch(rf'\[WARNING {time} other\.lib <string>:\d+ *\] some warning', line), line


def test_a1_already_configured() -> None:
    """
    Like basicConfig(), it does nothing if the app already configured logging.
    """

    def test() -> None:
        import logging

        import kloggy

        logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        kloggy.setup(level='debug')
        logging.getLogger('other.lib').info('lib info')
        logging.getLogger('other.lib').warning('lib warning')  # LOGS: APP WARNING other.lib: lib warning

    check_logs(test)


def test_a1_twice() -> None:
    """
    Same for an earlier setup() call, so nothing is printed twice.
    """

    def test() -> None:
        import logging

        import kloggy

        kloggy.setup()
        kloggy.setup(level='debug')
        logging.getLogger('other.lib').info('lib info')  # LOGS: KLOGGY INFO other.lib: lib info
        logging.getLogger('other.lib').debug('lib debug')

    check_logs(test)


def test_a1_stray_basic_config() -> None:
    """
    Except root's default basicConfig() handler, e.g. from a stray `logging.warning()` (Z3), which it replaces.
    """

    def test() -> None:
        import logging

        import kloggy

        # LOGS: WARNING:root:stray
        logging.warning('stray')  # noqa: LOG015 - deliberately tests implicit basicConfig()
        kloggy.setup()
        logging.getLogger('other.lib').info('lib info')  # LOGS: KLOGGY INFO other.lib: lib info

    check_logs(test)


def test_a1_disabled() -> None:
    """
    With `KLOGGY_DISABLE`, it's plain `basicConfig(level=...)`.
    """

    def test() -> None:
        import logging
        import os

        os.environ['KLOGGY_DISABLE'] = '1'

        import kloggy

        kloggy.setup()
        logging.getLogger('other.lib').info('lib info')  # LOGS: INFO:other.lib:lib info

    check_logs(test)
