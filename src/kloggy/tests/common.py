import inspect
import io
import os
import subprocess
import sys
import textwrap
import tokenize
from collections.abc import Callable
from typing import TextIO

from rich.console import Console


def run(test: Callable[..., None], *, test_format: bool = True, **kwargs: object) -> list[str]:
    """
    Runs a function's source in a separate process, since logging setup is global state.
    The function must import its dependencies locally and receive test parameters as explicit arguments.
    Arguments are either Python literals (e.g. strings, integers, booleans), or other functions following the same rules.
    Uses a distinct format for kloggy unless test_format=False.
    Returns stderr lines.
    """
    assert inspect.isfunction(test), test
    functions = [test]
    for v in kwargs.values():
        if inspect.isfunction(v):
            functions.append(v)
    for f in functions:
        # otherwise it would only fail in the subprocess, with a NameError
        assert f.__code__.co_freevars == (), (
            f'{f.__name__} uses names from the enclosing scope: {f.__code__.co_freevars}'
        )
    names = [f.__name__ for f in functions]
    assert len(set(names)) == len(names), names
    args = ', '.join(f'{k}={v.__name__}' if inspect.isfunction(v) else f'{k}={v!r}' for k, v in kwargs.items())
    code = '\n'.join(
        [
            # otherwise annotations would be evaluated in the subprocess, where nothing is imported at the top level
            'from __future__ import annotations',
            *(textwrap.dedent(inspect.getsource(f)) for f in functions),
            f'{test.__name__}({args})',
        ]
    )
    # make sure user's environment doesn't interfere
    assert '_KLOGGY_TEST_FORMAT' not in os.environ
    env = dict(os.environ)
    # e.g. the user's own KLOGGY_LEVEL would change what tests print
    env.pop('KLOGGY_LEVEL', None)
    env.pop('KLOGGY_DISABLE', None)
    env.pop('KLOGGY_PROGRESS', None)
    # would add or remove colour codes regardless of the stream (F2)
    # individual tests set them explicitly instead
    env.pop('FORCE_COLOR', None)
    env.pop('NO_COLOR', None)
    # the terminal size, which many shells export: otherwise rich would size its bars for the user's terminal, e.g. wider than the tests expect
    env.pop('COLUMNS', None)
    env.pop('LINES', None)
    # UTF-8 on both ends, i.e. here and when decoding below, which is the default on Linux, macOS, and since Python 3.15 on Windows (PEP 686)
    # before that, Windows would use the locale's encoding, e.g. cp1252, which has no '━' that rich draws bars with
    env['PYTHONIOENCODING'] = 'utf-8'
    if test_format:
        env['_KLOGGY_TEST_FORMAT'] = 'KLOGGY %(levelname)s %(name)s: %(message)s'
    res = subprocess.run(
        [sys.executable, '-c', code],
        env=env,
        capture_output=True,
        encoding='utf-8',
        check=False,
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout == '', res.stdout
    return res.stderr.splitlines()


def logs_from_comments(test: Callable[..., None]) -> list[str]:
    """
    Expected output of the function, from its `# LOGS: <line>` comments, in order.
    """
    source = textwrap.dedent(inspect.getsource(test))
    res = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        comment = token.string.removeprefix('#').strip()
        if comment.startswith('LOGS:'):
            res.append(comment.removeprefix('LOGS:').strip())
    return res


def check_logs(test: Callable[..., None], *, test_format: bool = True, **kwargs: object) -> None:
    """
    Runs the function (see run()) and checks its output is exactly what its `# LOGS: <line>` comments say, in order.
    So lines without such a comment are checked not to print anything.
    """
    assert run(test, test_format=test_format, **kwargs) == logs_from_comments(test)


def run_same_as_stdlib(test: Callable[..., None], *, test_format: bool = True, **kwargs: object) -> list[str]:
    """
    Runs the function (see run()) twice, with `use_kloggy=True` and `use_kloggy=False`, and checks the output is the same.
    The function should only use kloggy if `use_kloggy` is set, and plain stdlib otherwise, e.g. `logging.getLogger` rather than `get_logger`.
    Returns the output.
    """
    with_kloggy = run(test, test_format=test_format, use_kloggy=True, **kwargs)
    without_kloggy = run(test, test_format=test_format, use_kloggy=False, **kwargs)
    assert with_kloggy == without_kloggy, (with_kloggy, without_kloggy)
    return with_kloggy


def check_logs_same_as_stdlib(test: Callable[..., None], *, test_format: bool = True, **kwargs: object) -> None:
    """
    Like check_logs(), and also checks the output is the same as with plain stdlib, see run_same_as_stdlib().
    """
    assert run_same_as_stdlib(test, test_format=test_format, **kwargs) == logs_from_comments(test)


# printed by a test right after it configures logging, see run_same_as_stdlib_once_configured()
CONFIGURED = '--- configured'


def run_same_as_stdlib_once_configured(
    test: Callable[..., None], *, test_format: bool = True, **kwargs: object
) -> list[str]:
    """
    Like run_same_as_stdlib(), but only compares the output once the test configured logging,
      i.e. after the `--- configured` line it prints: before that, kloggy's output differs by design.
    Returns the output with kloggy.
    """
    with_kloggy = run(test, test_format=test_format, use_kloggy=True, **kwargs)
    without_kloggy = run(test, test_format=test_format, use_kloggy=False, **kwargs)

    def once_configured(lines: list[str]) -> list[str]:
        assert lines.count(CONFIGURED) == 1, lines
        return lines[lines.index(CONFIGURED) + 1 :]

    assert once_configured(with_kloggy) == once_configured(without_kloggy), (with_kloggy, without_kloggy)
    return with_kloggy


def check_logs_same_as_stdlib_once_configured(
    test: Callable[..., None], *, test_format: bool = True, **kwargs: object
) -> None:
    """
    Like check_logs(), and also checks the output once the test configured logging is the same as with plain stdlib,
      see run_same_as_stdlib_once_configured().
    """
    assert run_same_as_stdlib_once_configured(test, test_format=test_format, **kwargs) == logs_from_comments(test)


def terminal_screen(output: str, *, columns: int = 100, rows: int = 20) -> list[str]:
    """
    Non-empty lines a terminal would show after this output, e.g. from rich, which moves the cursor around to redraw its progress bars.
    """
    import pyte

    screen = pyte.Screen(columns, rows)
    # like a terminal, which turns each newline into a carriage return plus newline
    pyte.Stream(screen).feed(output.replace('\n', '\r\n'))
    return [line.rstrip() for line in screen.display if line.strip() != '']


def rich_console(terminal: TextIO) -> Console:
    """
    A rich console writing to a test terminal, e.g. for progress bars.
    """
    from rich.console import Console

    # legacy_windows=False: otherwise rich detects a legacy console on Windows when stdout isn't a real console (e.g. in CI),
    #   and draws bars with '-' instead of '━'
    # the test terminal is a modern one anyway, since terminal_screen() reads it with a VT emulator
    return Console(file=terminal, force_terminal=True, width=100, legacy_windows=False)
