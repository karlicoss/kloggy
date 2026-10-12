"""
W: warnings.
"""

import re

import pytest

from .common import check_logs, run, run_same_as_stdlib


def test_w1_format() -> None:
    """
    `kloggy.warnings.setup()` shows each warning on one line: stdlib's first line, without the source line under it.
    """

    def test() -> None:
        import warnings

        import kloggy.warnings

        kloggy.warnings.setup()
        warnings.warn('some warning, 100% sure', FutureWarning, stacklevel=1)

    [line] = run(test)
    assert re.fullmatch(r'<string>:\d+: FutureWarning: some warning, 100% sure', line), line


@pytest.mark.parametrize(
    ('stream', 'env', 'coloured'),
    [
        ('terminal', None, True),
        ('file', None, False),
        ('file', 'FORCE_COLOR', True),
        ('terminal', 'NO_COLOR', False),
    ],
)
def test_w1_colour(*, stream: str, env: str | None, coloured: bool) -> None:
    """
    Coloured by the same rules as kloggy's log output (F2), for the current sys.stderr (Z4).
    """

    def test(*, stream: str, env: str | None, coloured: bool) -> None:
        import contextlib
        import io
        import os
        import warnings

        import kloggy.warnings

        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        if env is not None:
            os.environ[env] = '1'
        kloggy.warnings.setup()
        captured = Terminal() if stream == 'terminal' else io.StringIO()
        with contextlib.redirect_stderr(captured):
            warnings.warn('some warning', stacklevel=1)
        output = captured.getvalue()
        assert 'some warning' in output, repr(output)
        assert ('\x1b[' in output) == coloured, repr(output)

    run(test, stream=stream, env=env, coloured=coloured)


def test_w1_customised() -> None:
    """
    It does nothing if something already customised how warnings are shown, e.g. the app, IPython or pytest.
    """

    def test() -> None:
        import sys
        import warnings
        from typing import TextIO

        import kloggy.warnings

        def app_showwarning(  # noqa: PLR0917 - same signature as warnings.showwarning
            message: Warning | str,
            category: type[Warning],
            filename: str,  # noqa: ARG001
            lineno: int,  # noqa: ARG001
            file: TextIO | None = None,  # noqa: ARG001
            line: str | None = None,  # noqa: ARG001
        ) -> None:
            print(f'APP {category.__name__}: {message}', file=sys.stderr)

        warnings.showwarning = app_showwarning  # ty: ignore[invalid-assignment]
        kloggy.warnings.setup()
        warnings.warn('some warning', stacklevel=1)  # LOGS: APP UserWarning: some warning

    check_logs(test)


def test_w1_capture() -> None:
    """
    Only how warnings are shown changes: `logging.captureWarnings()` and `catch_warnings(record=True)` work as usual,
      without colour codes in what they get.
    """

    def test() -> None:
        import logging
        import os
        import warnings

        import kloggy.warnings

        os.environ['FORCE_COLOR'] = '1'
        kloggy.warnings.setup()

        with warnings.catch_warnings(record=True) as caught:
            warnings.warn('recorded', stacklevel=1)
        assert [str(w.message) for w in caught] == ['recorded'], caught

        logging.basicConfig(format='APP %(name)s: %(message)s')
        logging.captureWarnings(capture=True)
        warnings.warn('captured', stacklevel=1)

    lines = run(test)
    assert re.fullmatch(r'APP py\.warnings: <string>:\d+: UserWarning: captured', lines[0]), lines
    assert not any('\x1b[' in line for line in lines), lines


def test_w1_disabled() -> None:
    """
    With `KLOGGY_DISABLE`, it does nothing (L5).
    """

    def test(*, use_kloggy: bool) -> None:
        import os
        import warnings

        os.environ['KLOGGY_DISABLE'] = '1'

        import kloggy.warnings

        if use_kloggy:
            kloggy.warnings.setup()
        assert warnings.showwarning is getattr(warnings, '_showwarning_orig')
        warnings.warn('some warning', stacklevel=1)

    lines = run_same_as_stdlib(test)
    assert re.fullmatch(r'<string>:\d+: UserWarning: some warning', lines[0]), lines


def test_w2_once() -> None:
    """
    `warn_once()` shows each distinct warning once, at the same location `warnings.warn()` would.
    """

    def test() -> None:
        import sys
        import warnings

        from kloggy.warnings import warn_once

        def check(path: str) -> None:
            warn_once(f'no paths matched {path}', stacklevel=2)  # attributed to the caller

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')  # so only warn_once() deduplicates
            foo_line = sys._getframe().f_lineno + 2
            for _ in range(3):
                check('/data/foo')
            check('/data/bar')
        assert [str(w.message) for w in caught] == ['no paths matched /data/foo', 'no paths matched /data/bar'], caught
        assert caught[0].lineno == foo_line, (caught[0].lineno, foo_line)

    run(test)


def test_w2_filters_changed() -> None:
    """
    stdlib shows a warning again once filters change, e.g. a library calling `catch_warnings()`; `warn_once()` doesn't.
    """

    def test() -> None:
        import warnings

        from kloggy.warnings import warn_once

        for _ in range(2):
            warnings.warn('stdlib: cachew not found', stacklevel=1)
            with warnings.catch_warnings():  # e.g. inside a library
                pass
        for _ in range(2):
            warn_once('warn_once: cachew not found', stacklevel=1)
            with warnings.catch_warnings():
                pass

    lines = [line for line in run(test) if 'UserWarning' in line]
    assert sum('stdlib: cachew not found' in line for line in lines) == 2, lines
    assert sum('warn_once: cachew not found' in line for line in lines) == 1, lines
