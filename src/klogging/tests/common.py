import inspect
import io
import os
import subprocess
import sys
import textwrap
import tokenize
from collections.abc import Callable


def run(test: Callable[..., None], *, test_format: bool = True, **kwargs: object) -> list[str]:
    """
    Runs a function's source in a separate process, since logging setup is global state.
    The function must import its dependencies locally and receive test parameters as explicit arguments.
    Arguments are either Python literals (e.g. strings, integers, booleans), or other functions following the same rules.
    Uses a distinct format for klogging unless test_format=False.
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
    assert '_KLOGGING_TEST_FORMAT' not in os.environ
    env = {k: v for k, v in os.environ.items() if not k.startswith('LOGGING_')}
    if test_format:
        env['_KLOGGING_TEST_FORMAT'] = 'KLOGGING %(levelname)s %(name)s: %(message)s'
    res = subprocess.run(
        [sys.executable, '-c', code],
        env=env,
        capture_output=True,
        text=True,
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
