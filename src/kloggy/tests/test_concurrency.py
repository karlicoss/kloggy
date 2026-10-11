"""
C: concurrency, i.e. threads and processes.
"""

import sys
from collections.abc import Callable
from typing import Any, TextIO

import pytest
from rich.console import Console

from .common import check_logs, rich_console, terminal_screen


def test_c1_threads() -> None:
    """
    Several threads can log at once, also with free-threaded Python: each record is printed whole, on its own line.
    E.g. through a rich progress bar, which prints each line above the bar (Z4).
    """

    def test(*, terminal_screen: Callable[..., list[str]], rich_console: Callable[[TextIO], Console]) -> None:
        import contextlib
        import io
        import threading

        from rich.progress import Progress

        from kloggy import get_logger

        threads, items = 4, 25

        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        # one terminal, which both kloggy (via sys.stderr) and rich write to, like in practice
        terminal = Terminal()
        with contextlib.redirect_stderr(terminal):
            logger = get_logger('pkg.mod')  # before the progress bar starts, like a module-level logger
            # rich also redraws the bar from its own thread meanwhile
            with Progress(console=rich_console(terminal)) as progress:
                task = progress.add_task('processing', total=threads * items)

                def work(thread: int) -> None:
                    for item in range(items):
                        logger.info('thread %d item %d', thread, item)
                        progress.advance(task)

                workers = [threading.Thread(target=work, args=(t,)) for t in range(threads)]
                for w in workers:
                    w.start()
                for w in workers:
                    w.join()

        *logged, bar = terminal_screen(terminal.getvalue(), rows=threads * items + 10)
        # in no particular order, but each one whole, and no progress bars interleaved with them, e.g. frozen copies
        expected = sorted(f'KLOGGY INFO pkg.mod: thread {t} item {i}' for t in range(threads) for i in range(items))
        assert sorted(logged) == expected, logged
        # a single bar, at the bottom
        assert bar.startswith('processing ━'), bar
        assert '100%' in bar, bar

    check_logs(test, terminal_screen=terminal_screen, rich_console=rich_console)


def rich_worker(*, worker: int, items: int, queue: Any) -> None:
    """
    Sends its log records to the main process, stdlib's recipe for logging from several processes.
    """
    import logging
    import logging.handlers

    from kloggy import get_logger

    root = logging.getLogger()
    root.addHandler(logging.handlers.QueueHandler(queue))
    root.setLevel(logging.INFO)
    logger = get_logger('pkg.mod')
    for item in range(items):
        logger.info('worker %d item %d', worker, item)


@pytest.mark.skipif(
    sys.platform == 'win32',
    reason='needs fork: the test code runs via python -c, which spawned processes can\'t import',
)
def test_c2_processes() -> None:
    """
    Several processes, using stdlib's recipe for logging from them: workers send their records to the main process, which logs them.
    In the workers, the QueueHandler counts as configured, so kloggy doesn't print there.
    That matters e.g. with a rich progress bar in the main process: the workers' output would go straight to the terminal, through the bar.
    """

    def test(
        *,
        terminal_screen: Callable[..., list[str]],
        rich_console: Callable[[TextIO], Console],
        rich_worker: Callable[..., None],
    ) -> None:
        import contextlib
        import io
        import logging
        import multiprocessing
        import sys

        from rich.progress import Progress

        from kloggy import get_logger

        workers, items = 3, 20

        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        # for type checkers: there's no fork on Windows, so get_context('fork') isn't typed as a fork context there
        # an if rather than an assert, since mypy only understands platform asserts at the top level of a module
        if sys.platform == 'win32':
            raise AssertionError('needs fork')

        get_logger('pkg.mod')  # kloggy sets up in the main process, before forking
        context = multiprocessing.get_context('fork')
        queue = context.Queue()
        # started before the progress bar, so its refresh thread doesn't exist yet when forking
        processes = [
            context.Process(target=rich_worker, kwargs={'worker': w, 'items': items, 'queue': queue})
            for w in range(workers)
        ]
        for p in processes:
            p.start()
        # one terminal, which both kloggy (via sys.stderr) and rich write to, like in practice
        # only in the main process: the workers keep the real stderr, so anything kloggy printed there would show up below
        terminal = Terminal()
        with contextlib.redirect_stderr(terminal), Progress(console=rich_console(terminal)) as progress:
            task = progress.add_task('processing', total=workers * items)
            for _ in range(workers * items):
                record = queue.get(timeout=10)
                logging.getLogger(record.name).handle(record)
                progress.advance(task)
        for p in processes:
            p.join(timeout=10)

        *logged, bar = terminal_screen(terminal.getvalue(), rows=workers * items + 10)
        # in no particular order, but each one whole, and no progress bars interleaved with them, e.g. frozen copies
        expected = sorted(f'KLOGGY INFO pkg.mod: worker {w} item {i}' for w in range(workers) for i in range(items))
        assert sorted(logged) == expected, logged
        # a single bar, at the bottom
        assert bar.startswith('processing ━'), bar
        assert '100%' in bar, bar

    # and nothing went to the real stderr, i.e. kloggy didn't print in the workers
    check_logs(test, terminal_screen=terminal_screen, rich_console=rich_console, rich_worker=rich_worker)
