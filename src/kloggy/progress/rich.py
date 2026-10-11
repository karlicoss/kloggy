"""
Progress bars via [rich](https://github.com/Textualize/rich).
"""

from __future__ import annotations

import atexit
import sys
import threading
from collections.abc import Iterable
from typing import Any

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    Task,
    TaskID,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table
from rich.text import Text


def _minutes(seconds: float | None) -> str:
    if seconds is None:
        return '--:--'
    minutes, seconds = divmod(int(seconds), 60)
    return f'{minutes:02d}:{seconds:02d}'


def _parts(task: Task) -> dict[str, str]:
    """
    Parts of the count and stats columns, each padded to the same width in all rows, so they line up.
    """
    return {
        'completed': f'{task.completed:.0f}',
        'total': '?' if task.total is None else f'{task.total:.0f}',
        'elapsed': _minutes(task.elapsed),
        'remaining': _minutes(task.time_remaining),
        'rate': '?' if task.speed is None else f'{task.speed:.2f}',
        'unit': task.fields['unit'],
    }


class _CountColumn(ProgressColumn):
    """
    Like rich's MofNCompleteColumn, but the '/' lines up in all rows, also with different totals, e.g. '4708/?' and '  94/1725'.
    """

    def __init__(self, *, widths: dict[str, int]) -> None:
        super().__init__()
        # set by _Progress before each render
        self._widths = widths

    def render(self, task: Task) -> Text:
        parts = _parts(task)
        w = self._widths
        return Text(f'{parts["completed"]:>{w["completed"]}}/{parts["total"]:<{w["total"]}}')


class _StatsColumn(ProgressColumn):
    """
    Like enlighten's '[00:01<00:02, 4.07 files/s]': elapsed, remaining, and items per second.
    Rich's own columns show the times without telling which is which, and its speed column is for bytes.
    Each part lines up in all rows.
    """

    def __init__(self, *, widths: dict[str, int]) -> None:
        super().__init__()
        # set by _Progress before each render
        self._widths = widths

    def render(self, task: Task) -> Text:
        parts = _parts(task)
        w = self._widths
        times = f'{parts["elapsed"]:>{w["elapsed"]}}<{parts["remaining"]:>{w["remaining"]}}'
        return Text(f'[{times}, {parts["rate"]:>{w["rate"]}} {parts["unit"]:>{w["unit"]}}/s]')


class _Progress(Progress):
    def __init__(self, *columns: ProgressColumn, console: Console, widths: dict[str, int], **kwargs: Any) -> None:
        # rich already calls make_tasks_table() in __init__, before self.console works
        self._width_console = console
        # shared with the count and stats columns
        self._widths = widths
        super().__init__(*columns, console=console, **kwargs)

    def make_tasks_table(self, tasks: Iterable[Task]) -> Table:
        tasks = list(tasks)
        # widest of each part in all rows, so e.g. the '/' in '4708/?' lines up with the one in '  94/1725'
        self._widths.clear()
        for task in tasks:
            for name, part in _parts(task).items():
                self._widths[name] = max(self._widths.get(name, 0), len(part))
        table = super().make_tasks_table(tasks)
        # two characters short of the full width, since on Ctrl-C the terminal shows '^C' where the cursor is, i.e. after the bars.
        # If that wrapped onto a new line, rich would lose track of where the bars are, and leave a stale copy of one on the screen.
        table.width = self._width_console.width - 2
        return table


class RichDisplay:
    """
    Shows bars at the bottom of the terminal while any loop is in progress, and removes them once it's done.
    Bars of loops that didn't finish stay on the screen.
    Meanwhile rich replaces sys.stderr, so it can print anything written to it above the bars, e.g. kloggy's output (Z4).
    """

    def __init__(self, *, console: Console | None = None) -> None:
        # stderr like logs, so bars don't mix with data printed to stdout
        self.console = Console(stderr=True) if console is None else console
        self._lock = threading.Lock()
        self._progress: Progress | None = None
        # loops still in progress, the other tasks are bars kept on the screen
        self._running: set[TaskID] = set()
        # e.g. if loops are never cleaned up before the process exits, otherwise the cursor would stay hidden
        atexit.register(self.freeze)

    def bar(self, *, desc: str, total: int | None, unit: str) -> _RichBar | None:
        if not self.console.is_terminal:
            return None
        with self._lock:
            if self._progress is None:
                widths: dict[str, int] = {}
                self._progress = _Progress(
                    # otherwise rich would treat e.g. '[saved]' in 'rexport.dal[saved]' as markup, and drop it
                    TextColumn('{task.description}', markup=False),
                    # percentage, nothing if the total isn't known
                    TaskProgressColumn(),
                    # None: takes whatever width the other columns leave, see expand below
                    BarColumn(bar_width=None),
                    _CountColumn(widths=widths),
                    _StatsColumn(widths=widths),
                    console=self.console,
                    widths=widths,
                    # full terminal width (almost, see _Progress), rather than just as wide as the columns need
                    expand=True,
                    # otherwise the last state of the bars would stay on the screen once all loops are done
                    # changed when stopping if some bars should stay, see _stop()
                    transient=True,
                    # otherwise rich would print stdout via its console, i.e. to stderr, e.g. even if stdout is piped into another program
                    redirect_stdout=sys.stdout.isatty(),
                )
                self._progress.start()
            task = self._progress.add_task(desc, total=total, unit=unit)
            self._running.add(task)
            return _RichBar(display=self, progress=self._progress, task=task)

    def freeze(self) -> None:
        with self._lock:
            if self._progress is not None:
                self._stop()

    def _close(self, *, progress: Progress, task: TaskID, keep: bool) -> None:
        with self._lock:
            if progress is not self._progress:
                # frozen since, so it's already on the screen as it was
                return
            if keep:
                # so its elapsed time and rate stop changing
                progress.stop_task(task)
            else:
                progress.remove_task(task)
            self._running.remove(task)
            if len(self._running) == 0:
                # so between loops, the terminal and sys.stderr are back to normal
                self._stop()

    def _stop(self) -> None:
        progress = self._progress
        assert progress is not None
        # i.e. unless some bars should stay on the screen: finished ones are removed by then
        progress.live.transient = len(progress.tasks) == len(self._running) == 0
        progress.stop()
        self._progress = None
        self._running = set()


class _RichBar:
    def __init__(self, *, display: RichDisplay, progress: Progress, task: TaskID) -> None:
        self._display = display
        self._progress = progress
        self._task = task

    def advance(self) -> None:
        self._progress.advance(self._task)

    def close(self, *, keep: bool) -> None:
        self._display._close(progress=self._progress, task=self._task, keep=keep)
