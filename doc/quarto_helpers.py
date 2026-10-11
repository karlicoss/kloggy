"""
Helpers for .qmd cells, linking requirements to the tests validating them.
Tests are named after requirement IDs, e.g. `test_l3_configured_after` validates L3.
"""

import ast
import re
from pathlib import Path

from IPython.display import Markdown

DOC = Path(__file__).parent
REPO = DOC.parent
PACKAGE = REPO / 'src' / 'kloggy'


def _collect_tests() -> dict[str, str]:
    """
    Test name -> link target relative to the doc.
    """
    res = {}
    # also tests of subpackages, e.g. kloggy/progress/tests
    for path in sorted(PACKAGE.rglob('tests/test_*.py')):
        for node in ast.parse(path.read_text()).body:
            if not (isinstance(node, ast.FunctionDef) and node.name.startswith('test_')):
                continue
            assert node.name not in res, node.name
            # relative, so links work on any branch on GitHub, and locally
            res[node.name] = f'../{path.relative_to(REPO).as_posix()}#L{node.lineno}'
    assert len(res) > 0, PACKAGE
    return res


_tests = _collect_tests()
_linked: set[str] = set()


def _test_link(name: str) -> str:
    _linked.add(name)
    # 'test_' is just noise in prose, the full name is in the link title
    return f'[`{name.removeprefix("test_")}`]({_tests[name]} "{name}")'


# NOTE: returning Markdown, otherwise quarto escapes inline output
def tests(*names: str) -> Markdown:
    """
    Links to tests validating a statement, e.g. `(tests: l3_configured_after, l3_effective_level)`.
    """
    assert len(names) > 0
    label = 'test' if len(names) == 1 else 'tests'
    links = ', '.join(_test_link(name) for name in names)
    return Markdown(f'({label}: {links})')


def check_all_tests_linked() -> None:
    """
    Every test of an approved requirement (ID below 20) should be linked from the doc.
    Draft requirements (ID 20 and up) aren't in the doc.
    """
    unlinked = []
    for name in _tests:
        m = re.fullmatch(r'test_[a-z](\d+)_\w+', name)
        assert m is not None, f'{name} should be named after a requirement, e.g. test_l3_...'
        if int(m.group(1)) < 20 and name not in _linked:
            unlinked.append(name)
    assert len(unlinked) == 0, unlinked
