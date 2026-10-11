"""
P: progress, i.e. kloggy.progress (experimental).
"""

import re
import sys
from collections.abc import Callable
from typing import TextIO

import pytest
from rich.console import Console

from ...tests.common import check_logs, rich_console, run, terminal_screen


def not_installed(names: list[str]) -> None:
    """
    Makes imports of these packages fail like for packages that aren't installed, also of their submodules, e.g. rich.console.
    For the tests' functions run() runs, so it imports what it needs itself.
    """
    import importlib.abc
    import sys
    from collections.abc import Sequence
    from importlib.machinery import ModuleSpec
    from types import ModuleType

    class NotInstalled(importlib.abc.MetaPathFinder):
        # path and target are unused, but part of the finder interface
        def find_spec(
            self,
            fullname: str,
            path: Sequence[str] | None,  # noqa: ARG002
            target: ModuleType | None = None,  # noqa: ARG002
        ) -> ModuleSpec | None:
            if fullname in names:
                raise ModuleNotFoundError(f'No module named {fullname!r}', name=fullname)
            return None

    sys.meta_path.insert(0, NotInstalled())


def test_p1_log_lines() -> None:
    """
    Without a display, each item is logged at INFO before it's processed, numbered from 1, padded to the width of the total.
    Stopping early, e.g. via break, is fine.
    """

    def test() -> None:
        from kloggy import get_logger
        from kloggy.progress import progress

        logger = get_logger('pkg.mod')
        items = [f'item{i}' for i in range(10)]
        for item in progress(items, logger=logger):
            # LOGS: KLOGGY INFO pkg.mod: processing [ 1/10] item0
            # LOGS: KLOGGY INFO pkg.mod: processing [ 2/10] item1
            # LOGS: KLOGGY INFO pkg.mod: processing [ 3/10] item2
            if item == 'item2':
                break
        logger.info('done')  # LOGS: KLOGGY INFO pkg.mod: done

    check_logs(test)


def test_p1_no_length() -> None:
    """
    Items without a length, e.g. a generator, are numbered without a total, unless it's passed explicitly.
    """

    def test() -> None:
        from kloggy import get_logger
        from kloggy.progress import progress

        logger = get_logger('pkg.mod')
        for _ in progress((c for c in 'ab'), logger=logger):
            pass
        # LOGS: KLOGGY INFO pkg.mod: processing [1] a
        # LOGS: KLOGGY INFO pkg.mod: processing [2] b
        for _ in progress((c for c in 'ab'), logger=logger, total=2):
            pass
        # LOGS: KLOGGY INFO pkg.mod: processing [1/2] a
        # LOGS: KLOGGY INFO pkg.mod: processing [2/2] b

    check_logs(test)


def test_p1_describe() -> None:
    """
    What's logged for each item can be changed, e.g. to just the path when the items are (path, result) pairs.
    """

    def test() -> None:
        from kloggy import get_logger
        from kloggy.progress import progress

        logger = get_logger('pkg.mod')
        results = [('a.json', [1, 2]), ('b.json', [3])]
        for _path, _result in progress(results, logger=logger, describe=lambda r: r[0]):
            pass
        # LOGS: KLOGGY INFO pkg.mod: processing [1/2] a.json
        # LOGS: KLOGGY INFO pkg.mod: processing [2/2] b.json

    check_logs(test)


def test_p1_log_items() -> None:
    """
    The 'processing [i/n] ...' lines can be turned off, e.g. for thousands of events, where a log line for each would flood the output.
    """

    def test() -> None:
        from kloggy import get_logger
        from kloggy.progress import progress

        logger = get_logger('pkg.mod')
        for _ in progress(range(1000), logger=logger, log_items=False):
            pass
        logger.info('done')  # LOGS: KLOGGY INFO pkg.mod: done

    check_logs(test)


def test_p1_location() -> None:
    """
    Records point at the loop in the caller, rather than into kloggy, e.g. in the source location kloggy's output shows (F1).
    """

    def test() -> None:
        from kloggy import get_logger
        from kloggy.progress import progress

        logger = get_logger('pkg.mod')
        for _ in progress(['a'], logger=logger):
            pass

    [line] = run(test, test_format=False)
    # the test runs via `python -c`, and the for loop is on line 7, after the `from __future__` line run() adds
    assert re.search(r' pkg\.mod <string>:7 +\] processing \[1/1\] a$', line), line


def test_p2_rich() -> None:
    """
    While rich shows a bar for the loop, items are logged at DEBUG, i.e. not shown by default.
    Other output is printed above the bar, and the bar is removed once the loop is done.
    The bar's label is shown as is, e.g. not as rich markup.
    The bar takes the full width of the terminal (almost), with stats like enlighten's.
    stdout stays where it is if it's not a terminal, e.g. if it's piped into another program.
    """

    def test(*, terminal_screen: Callable[[str], list[str]], rich_console: Callable[[TextIO], Console]) -> None:
        import contextlib
        import io
        import re

        from kloggy import get_logger
        from kloggy.progress import progress, set_display
        from kloggy.progress.rich import RichDisplay

        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        terminal = Terminal()
        stdout = io.StringIO()
        screens = []
        with contextlib.redirect_stderr(terminal), contextlib.redirect_stdout(stdout):
            logger = get_logger('pkg.mod')
            set_display(RichDisplay(console=rich_console(terminal)))
            for item in progress(['a', 'b', 'c'], logger=logger, desc='pkg.mod[saved]', unit='files'):
                if item == 'b':
                    logger.warning('b looks odd')
                    print('data')
                screens.append(terminal_screen(terminal.getvalue()))
            logger.info('done')

        [bar] = screens[0]
        assert re.fullmatch(r'pkg\.mod\[saved\] +0% ━+ 0/3 \[00:00<--:--, \? files/s\]', bar), bar
        # the test terminal is 100 characters wide, and the bars leave room for '^C' the terminal shows on Ctrl-C
        assert len(bar) == 98, bar
        warning, bar = screens[1]
        assert warning == 'KLOGGY WARNING pkg.mod: b looks odd', screens[1]
        # the count depends on whether rich refreshed the bar since, which it does in a separate thread
        assert re.fullmatch(r'pkg\.mod\[saved\] +\d+% ━+ \d/3 \[.*files/s\]', bar), bar
        assert terminal_screen(terminal.getvalue()) == [
            'KLOGGY WARNING pkg.mod: b looks odd',
            'KLOGGY INFO pkg.mod: done',
        ]
        assert stdout.getvalue() == 'data\n'

    check_logs(test, terminal_screen=terminal_screen, rich_console=rich_console)


def test_p2_rich_unfinished() -> None:
    """
    The bar of a loop that didn't finish stays on the screen as it was, e.g. if it stopped early via break.
    On Ctrl-C, all the bars stay, also those of loops cleaned up only later, and output after that goes below them.
    """

    def test(*, terminal_screen: Callable[[str], list[str]], rich_console: Callable[[TextIO], Console]) -> None:
        import contextlib
        import io
        import re
        from collections.abc import Iterator

        from kloggy import get_logger
        from kloggy.progress import progress, set_display
        from kloggy.progress.rich import RichDisplay

        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        def interrupted() -> Iterator[str]:
            yield 'x.json'
            raise KeyboardInterrupt

        terminal = Terminal()
        with contextlib.redirect_stderr(terminal):
            logger = get_logger('pkg.mod')
            set_display(RichDisplay(console=rich_console(terminal)))
            for item in progress(['a', 'b', 'c'], logger=logger, desc='stopped', unit='files'):
                if item == 'b':
                    break
            logger.info('after break')
            try:
                for _ in progress(['export'], logger=logger, desc='outer', unit='exports'):
                    for _ in progress(interrupted(), logger=logger, desc='inner', unit='files'):
                        pass
            except KeyboardInterrupt:
                logger.warning('Aborted!')

        stopped, after_break, outer, inner, aborted = terminal_screen(terminal.getvalue())
        # rich draws partly filled cells with '╸' or '╺'
        assert re.fullmatch(r'stopped +33% [━╸╺]+ +1/3 +\[.*files/s\]', stopped), stopped
        assert after_break == 'KLOGGY INFO pkg.mod: after break'
        assert re.fullmatch(r'outer +0% [━╸╺]+ +0/1 +\[.*exports/s\]', outer), outer
        assert re.fullmatch(r'inner +[━╸╺]+ +1/\? +\[.*files/s\]', inner), inner
        # each part lines up in all rows
        for part in '/[<,]':
            assert outer.index(part) == inner.index(part), (part, outer, inner)
        assert aborted == 'KLOGGY WARNING pkg.mod: Aborted!'

    check_logs(test, terminal_screen=terminal_screen, rich_console=rich_console)


@pytest.mark.skipif(sys.platform == 'win32', reason='needs a pseudo-terminal')
def test_p2_enlighten() -> None:
    """
    Same as with rich: while enlighten shows a bar for the loop, items are logged at DEBUG,
      other output is printed above the bar, and the bar is removed once the loop is done.
    Without a total, the stats are on the right as well, like for a bar.
    On Ctrl-C, all the bars stay on the screen as they were.
    Unlike rich, enlighten needs a real terminal, so this runs in a pseudo-terminal.
    """

    def test(*, terminal_screen: Callable[[str], list[str]]) -> None:
        import contextlib
        import errno
        import fcntl
        import os
        import pty
        import re
        import struct
        import sys
        import termios
        import threading
        import time
        from collections.abc import Iterator

        from kloggy import get_logger
        from kloggy.progress import progress, set_display
        from kloggy.progress.enlighten import EnlightenDisplay

        # pytest's skip marker doesn't prevent type checkers from checking the Unix-only APIs below
        if sys.platform == 'win32':
            raise AssertionError('needs a pseudo-terminal')

        # blessed, which enlighten uses, looks up the terminal's capabilities by its name
        os.environ['TERM'] = 'xterm-256color'
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 20, 100, 0, 0))
        terminal = os.fdopen(slave, 'w', encoding='utf-8')

        output = bytearray()

        def read() -> None:
            # otherwise the writes would block once the pseudo-terminal's buffer is full
            while True:
                try:
                    data = os.read(master, 65536)
                except OSError as e:
                    # Linux reports EOF on a pseudo-terminal as EIO
                    if e.errno != errno.EIO:
                        raise
                    return
                # macOS reports EOF as an empty read
                if data == b'':
                    return
                output.extend(data)

        reader = threading.Thread(target=read)
        reader.start()
        with contextlib.redirect_stderr(terminal):
            logger = get_logger('pkg.mod')
            set_display(EnlightenDisplay())
            for item in progress(['a', 'b', 'c'], logger=logger, unit='files'):
                if item == 'b':
                    logger.warning('b looks odd')
            for _ in progress((c for c in 'xy'), logger=logger, unit='files'):
                # so enlighten draws the counter: at most every 0.1s
                time.sleep(0.15)

            def interrupted() -> Iterator[str]:
                yield 'x.json'
                raise KeyboardInterrupt

            try:
                for _ in progress(['export'], logger=logger, desc='outer', unit='exports'):
                    for _ in progress(interrupted(), logger=logger, desc='inner', unit='files'):
                        pass
            except KeyboardInterrupt:
                logger.warning('Aborted!')
        terminal.close()
        reader.join()
        os.close(master)

        shown = output.decode('utf-8')
        # enlighten draws the bar once it's updated, and at most every 0.1s unless it's complete, i.e. here only at the end
        assert 'pkg.mod 100%|' in shown, shown
        counter = re.search(r'pkg\.mod +1/\? \[00:00<--:--, +[\d.]+ files/s\]', shown)
        assert counter is not None, shown
        # the pseudo-terminal is 100 characters wide
        assert len(counter.group(0)) == 100, counter
        assert 'processing' not in shown, shown
        warning, outer, inner, aborted = terminal_screen(shown)
        assert warning == 'KLOGGY WARNING pkg.mod: b looks odd'
        assert re.fullmatch(r'outer +0%\|.*\| 0/1 \[.*exports/s\]', outer), outer
        assert re.fullmatch(r'inner +1/\? +\[.*files/s\]', inner), inner
        # each part lines up in all bars, also with a counter without a total
        for part in '/[<,]':
            assert outer.index(part) == inner.index(part), (part, outer, inner)
        assert aborted == 'KLOGGY WARNING pkg.mod: Aborted!'

    check_logs(test, terminal_screen=terminal_screen)


@pytest.mark.parametrize('display', ['rich', 'enlighten'])
def test_p2_not_terminal(display: str) -> None:
    """
    No bar if stderr isn't a terminal, e.g. redirected to a file, and items are logged at INFO.
    """

    def test(*, display: str) -> None:
        import os

        from kloggy import get_logger
        from kloggy.progress import progress

        os.environ['KLOGGY_PROGRESS'] = display
        logger = get_logger('pkg.mod')
        for _ in progress(['a'], logger=logger):
            pass
        # LOGS: KLOGGY INFO pkg.mod: processing [1/1] a

    check_logs(test, display=display)


def test_p3_shared() -> None:
    """
    One display for the whole process, e.g. picked by the user via KLOGGY_PROGRESS,
      so bars of nested loops in different packages show together, lined up.
    """

    def test(*, terminal_screen: Callable[[str], list[str]]) -> None:
        import contextlib
        import io
        import os
        import re

        from kloggy import get_logger
        from kloggy.progress import progress

        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        os.environ['KLOGGY_PROGRESS'] = 'rich'
        terminal = Terminal()
        screens = []
        with contextlib.redirect_stderr(terminal):
            export_logger = get_logger('pkg_a.export')
            dal_logger = get_logger('pkg_b.dal')
            for path in progress(['x.json', 'y.json'], logger=export_logger, unit='files'):
                for _ in progress([1, 2], logger=dal_logger, desc=f'parsing {path}', unit='entries'):
                    screens.append(terminal_screen(terminal.getvalue()))

        outer, inner = screens[0]
        assert outer.startswith('pkg_a.export '), outer
        assert re.search(r' 0/2 \[00:00<--:--, \? +files/s\]$', outer), outer
        assert inner.startswith('parsing x.json '), inner
        assert inner.endswith(' 0/2 [00:00<--:--, ? entries/s]'), inner
        # each part lines up in all rows, e.g. shorter units are padded
        for part in '/[<,]':
            assert outer.index(part) == inner.index(part), (part, outer, inner)
        assert len(outer) == len(inner), (outer, inner)
        outer, inner = screens[2]
        assert re.search(r' 1/2 +\[', outer), outer
        assert inner.startswith('parsing y.json '), inner
        assert terminal_screen(terminal.getvalue()) == []

    check_logs(test, terminal_screen=terminal_screen)


@pytest.mark.parametrize(
    ('missing', 'expected'),
    [
        ([], 'RichDisplay'),
        (['rich'], 'EnlightenDisplay'),
        (['rich', 'enlighten'], None),
    ],
)
def test_p4_auto(missing: list[str], expected: str | None) -> None:
    """
    KLOGGY_PROGRESS=auto picks rich if it's installed, otherwise enlighten.
    If neither is installed, it's log lines only, without a warning.
    """

    def test(*, missing: list[str], expected: str | None, not_installed: Callable[[list[str]], None]) -> None:
        import os
        import warnings

        import kloggy.progress
        from kloggy import get_logger
        from kloggy.progress import progress

        not_installed(missing)
        os.environ['KLOGGY_PROGRESS'] = 'auto'
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            for _ in progress(['a'], logger=get_logger('pkg.mod')):
                pass
            # LOGS: KLOGGY INFO pkg.mod: processing [1/1] a
        display = kloggy.progress._get_display()
        assert (None if display is None else type(display).__name__) == expected, display

    check_logs(test, missing=missing, expected=expected, not_installed=not_installed)


@pytest.mark.parametrize('value', ['bogus', 'enlighten'])
def test_p3_invalid(value: str) -> None:
    """
    An unknown KLOGGY_PROGRESS value, or a display whose library isn't installed, is ignored with a warning, and items are logged as usual.
    """

    def test(*, value: str, not_installed: Callable[[list[str]], None]) -> None:
        import os
        import warnings

        import pytest

        from kloggy import get_logger
        from kloggy.progress import progress

        not_installed(['enlighten'])
        os.environ['KLOGGY_PROGRESS'] = value
        logger = get_logger('pkg.mod')
        with pytest.warns(UserWarning, match='KLOGGY_PROGRESS: '):
            for _ in progress(['a'], logger=logger):
                pass
        # LOGS: KLOGGY INFO pkg.mod: processing [1/1] a
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            # KLOGGY_PROGRESS is only read once, so it doesn't warn for every loop
            for _ in progress(['b'], logger=logger):
                pass
        # LOGS: KLOGGY INFO pkg.mod: processing [1/1] b

    check_logs(test, value=value, not_installed=not_installed)
