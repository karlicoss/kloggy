"""
F: output format.
Other tests use a simpler format (see common.run), these check the real one.
"""

import re

import pytest

from .common import run


def test_f1_format() -> None:
    """
    Level padded to 7 characters, timestamp with milliseconds, logger name, file and line number padded to 4.
    CRITICAL isn't truncated, just one character wider.
    """

    def test() -> None:
        from kloggy import get_logger

        logger = get_logger('pkg.mod')
        logger.info('some info')
        logger.critical('some critical')

    info, critical = run(test, test_format=False)
    time = r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}'
    assert re.fullmatch(rf'\[INFO    {time} pkg\.mod <string>:\d+ *\] some info', info), info
    assert re.fullmatch(rf'\[CRITICAL {time} pkg\.mod <string>:\d+ *\] some critical', critical), critical


def test_f1_file() -> None:
    """
    The file is where the record was logged, even via another module's logger,
      e.g. cachew logging through the decorated module's logger.
    """

    def test() -> None:
        import importlib
        import sys
        import tempfile
        from pathlib import Path

        from kloggy import get_logger

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'helper.py').write_text('def log(logger):\n    logger.info("from helper")\n')
            sys.path.insert(0, tmp)
            helper = importlib.import_module('helper')
            helper.log(get_logger('pkg.mod'))

    [line] = run(test, test_format=False)
    assert line.endswith(' pkg.mod helper.py:2   ] from helper'), line


@pytest.mark.parametrize('no_color', [False, True])
def test_f2_tty(*, no_color: bool) -> None:
    """
    On a terminal, the prefix is coloured by level, unless NO_COLOR is set.
    """

    def test(*, no_color: bool) -> None:
        import contextlib
        import io
        import os

        if no_color:
            os.environ['NO_COLOR'] = '1'

        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        from kloggy import get_logger

        terminal = Terminal()
        with contextlib.redirect_stderr(terminal):
            get_logger('pkg.mod').warning('some warning')
        output = terminal.getvalue()
        if no_color:
            assert '\x1b[' not in output, repr(output)
        else:
            assert output.startswith('\x1b[33m[WARNING '), repr(output)
            assert ']\x1b[0m some warning' in output, repr(output)

    run(test, test_format=False, no_color=no_color)


def test_f2_force_color() -> None:
    """
    FORCE_COLOR colours the prefix even if the stream isn't a terminal, e.g. in CI.
    """

    def test() -> None:
        import os

        os.environ['FORCE_COLOR'] = '1'

        from kloggy import get_logger

        get_logger('pkg.mod').warning('some warning')

    [line] = run(test, test_format=False)
    assert line.startswith('\x1b[33m[WARNING '), repr(line)
