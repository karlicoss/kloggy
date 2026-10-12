"""
X: exceptions.
"""

from collections.abc import Callable

from .common import check_logs, check_logs_same_as_stdlib, run


def raised() -> ValueError:
    """
    An exception which has a traceback, since it was raised.
    """

    def fail() -> None:
        raise ValueError('boom')

    try:
        fail()
    except ValueError as e:
        return e
    raise AssertionError('unreachable')


def test_x1_error() -> None:
    """
    An exception logged as the message at ERROR shows its traceback, even outside an except block.
    """

    def test(*, raised: Callable[[], ValueError]) -> None:
        from kloggy import get_logger

        error = raised()
        get_logger('pkg.mod').error(error)

    lines = run(test, raised=raised)
    assert lines[:2] == ['KLOGGY ERROR pkg.mod: boom', 'Traceback (most recent call last):'], lines
    assert lines[-1] == 'ValueError: boom', lines


def test_x1_exception_outside_handler() -> None:
    """
    Same for logger.exception() outside an except block, which stdlib would print with 'NoneType: None' instead.
    """

    def test(*, raised: Callable[[], ValueError]) -> None:
        from kloggy import get_logger

        error = raised()
        get_logger('pkg.mod').exception(error)  # deliberately outside an except block

    lines = run(test, raised=raised)
    assert lines[:2] == ['KLOGGY ERROR pkg.mod: boom', 'Traceback (most recent call last):'], lines
    assert lines[-1] == 'ValueError: boom', lines


def test_x1_warning() -> None:
    """
    Below ERROR, it's just the message: e.g. warnings are often expected failures, like a file that's skipped.
    """

    def test(*, raised: Callable[[], ValueError]) -> None:
        from kloggy import get_logger

        error = raised()
        get_logger('pkg.mod').warning(error)  # LOGS: KLOGGY WARNING pkg.mod: boom

    check_logs(test, raised=raised)


def test_x1_explicit_exc_info() -> None:
    """
    An explicit exc_info always wins, also exc_info=False asking for no traceback.
    """

    def test(*, raised: Callable[[], ValueError]) -> None:
        from kloggy import get_logger

        error = raised()
        logger = get_logger('pkg.mod')
        logger.error(error, exc_info=False)
        logger.error(error, exc_info=KeyError('other'))

    lines = run(test, raised=raised)
    assert lines == [
        'KLOGGY ERROR pkg.mod: boom',
        'KLOGGY ERROR pkg.mod: boom',
        "KeyError: 'other'",
    ], lines


def test_x1_app_configured() -> None:
    """
    Only kloggy's own output shows the traceback: once the app configures logging, its handlers get the usual stdlib behaviour.
    So library code should still pass exc_info=e.
    """

    def test(*, raised: Callable[[], ValueError], use_kloggy: bool) -> None:
        import logging

        from kloggy import get_logger

        error = raised()
        logging.basicConfig(format='APP %(levelname)s %(name)s: %(message)s')
        (get_logger if use_kloggy else logging.getLogger)('pkg.mod').error(error)  # LOGS: APP ERROR pkg.mod: boom

    check_logs_same_as_stdlib(test, raised=raised)
