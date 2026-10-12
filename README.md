# kloggy

Logging helper: nice zero-config output for libraries, without fighting the app's logging setup.
It started as a shared helper for [HPI](https://github.com/karlicoss/HPI), [promnesia](https://github.com/karlicoss/promnesia),
  [orger](https://github.com/karlicoss/orger), [cachew](https://github.com/karlicoss/cachew) and data exporters like [rexport](https://github.com/karlicoss/rexport),
  but nothing in it is specific to them.

It's developed requirements-first: see [requirements](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md), linked to the tests validating them.
Work in progress, only the requirements listed there are implemented so far.

Install with `pip install kloggy` (or `uv add kloggy`).

Library code gets plain stdlib loggers:

```python
# mypkg/parse.py
from kloggy import get_logger

logger = get_logger(__name__)


def parse(paths: list[str]) -> None:
    for i, path in enumerate(paths, start=1):
        logger.info('processing [%d/%d] %s', i, len(paths), path)
        logger.debug('not shown by default')
```

Without any logging setup, `parse(['a.json', 'b.json'])` prints to stderr
  ([F1](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#f1)):

```text
[INFO    2026-10-11 20:20:01,730 mypkg.parse parse.py:8   ] processing [1/2] a.json
[INFO    2026-10-11 20:20:01,730 mypkg.parse parse.py:8   ] processing [2/2] b.json
```

Plain stdlib would print nothing here, since INFO is below its default WARNING.

- if logging isn't configured, records are never printed as bare messages ([Z1](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#z1)),
    and INFO is shown, e.g. for progress ([L2](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#l2))
- if the app configures logging later (e.g. `basicConfig(level=logging.DEBUG)` in `main()`), kloggy steps aside for good:
    no duplicates ([Z2](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#z2)),
    and the app's levels apply ([L3](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#l3))
- a stray `logging.warning(...)` (which implicitly calls `basicConfig()`) doesn't make kloggy step aside ([Z3](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#z3)).
  Neither does a bare `basicConfig()` in the app, since kloggy can't tell it apart from a stray one:
    pass some non-default argument, e.g. `level=logging.INFO` or `format=...`, or use `kloggy.setup()` instead (see below)
- if the app already configured logging, kloggy doesn't touch it ([L1](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#l1))

## Using kloggy in a package

Create a module-level logger in each module with `get_logger(__name__)`, same as the usual stdlib convention `logging.getLogger(__name__)`.

kloggy attaches its handler to the top-level package logger, i.e. the first dotted component of the name (`pkg` for `pkg.sub.module`).
Levels can be configured for the whole package or for individual modules as usual:

```python
logging.getLogger('pkg').setLevel(logging.DEBUG)  # all of pkg.*
logging.getLogger('pkg.module').setLevel(logging.WARNING)  # just this module
```

A module whose INFO is too chatty can pick its own default instead, e.g. `get_logger(__name__, default_level='warning')` ([L6](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#l6)).
Unlike `setLevel()` in the module, it's only kloggy's default, so levels set by the app or via [`KLOGGY_LEVEL`](#environment-variables) still win.

### Recommendations

- use `get_logger(__name__)`, not `get_logger(__package__)`:
  - records would lose their module name (`pkg.sub` instead of `pkg.sub.module`), so individual modules can't be configured
  - `__package__` is `''` under `python -m` (i.e. the root logger) and `None` in a script run directly
  - kloggy refuses the root logger, so those are an error ([L7](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#l7))
- outside `except` blocks, pass the exception explicitly, e.g. `logger.error('while parsing %s', path, exc_info=e)`, so the traceback is kept with any logging setup
    (kloggy's output adds it for `logger.error(e)` anyway, [X1](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#x1))
- log via the module logger, not the root logger (`logging.warning(...)` etc.), ruff rule [`LOG015`](https://docs.astral.sh/ruff/rules/root-logger-call/) catches these.
  Such calls implicitly call `basicConfig()`.
  kloggy copes with that ([Z3](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#z3)), but an app's own `basicConfig(...)` called later is then silently ignored.
- for warnings from code that runs repeatedly, e.g. a check in a function called for every file, use `kloggy.warnings.warn_once()`:
    same arguments as `warnings.warn()`, but each distinct warning is shown once,
    also if something changes warning filters in between, which makes stdlib show it again ([W2](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#w2))

## Using kloggy in an app

Call `kloggy.setup()` in `main()` instead of `logging.basicConfig()` ([A1](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#a1)):

```python
import kloggy


def main() -> None:
    kloggy.setup()  # or e.g. kloggy.setup(level='debug')
```

Every logger then gets kloggy's output, also in libraries not using kloggy.
Like with `basicConfig()`, root's level (INFO by default) applies to every logger, unless it or an ancestor has its own level set,
  e.g. via `logging.getLogger('pkg').setLevel(...)`.
[`KLOGGY_LEVEL`](#environment-variables) still only applies to packages using kloggy:
  e.g. `KLOGGY_LEVEL=vendor=off` doesn't silence a `vendor` library which doesn't use kloggy, use `logging.getLogger('vendor').setLevel(...)` for that.

`setup()` does nothing if logging is already configured, e.g. by an earlier `setup()` call.
The exception is root's default handler from a bare `basicConfig()`, e.g. a stray `logging.warning(...)`: `setup()` replaces it.

`datefmt` works as in `basicConfig()`, e.g. `datefmt='%Y-%m-%d %H:%M:%S'` drops the milliseconds.

To make warnings stand out too, call `kloggy.warnings.setup()` (after `import kloggy.warnings`) ([W1](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#w1)):
  each warning is then shown on one line, coloured on a terminal, without the source line stdlib prints under it.

## Environment variables

Users running a program can adjust kloggy's behaviour without changing any code:

- `KLOGGY_LEVEL` sets levels for packages using kloggy, e.g. `KLOGGY_LEVEL=warning,pkg.sub=debug,pkg.noisy=off`
    ([V1](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#v1)).
  The syntax follows Rust's `RUST_LOG`: `off` silences a logger completely, and the most specific entry wins.
  These levels apply even if the app configures logging.
- `KLOGGY_DISABLE=1` disables kloggy completely, so logging behaves exactly as plain stdlib, e.g. if kloggy causes problems
    ([L5](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#l5))
- `NO_COLOR` and `FORCE_COLOR`: output is coloured by level on a terminal, via colorlog, which honours these to disable or force colour
    ([F2](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#f2))

`KLOGGY_LEVEL` and `KLOGGY_DISABLE` are read once, on the first `get_logger()` call (`KLOGGY_DISABLE` also on `setup()`), so set them before the program starts:
  setting `os.environ` in `main()` is usually too late, since imports have already called `get_logger()`.

## Alternatives

- [logzero](https://github.com/metachris/logzero) and [coloredlogs](https://github.com/xolox/python-coloredlogs): coloured output, but unmaintained
    (logzero's repo was archived in 2022, coloredlogs' last release was in 2021).
  logzero also sets up its own handlers with `propagate = False`, so the app's configuration doesn't reach them.
- [loguru](https://github.com/Delgan/loguru) and [structlog](https://www.structlog.org): replace stdlib's logging model, so library code would depend on them.
  kloggy's loggers are plain `logging.Logger` objects.
- [daiquiri](https://daiquiri.readthedocs.io): app-side setup only, like `setup()`, without zero-config output for libraries or levels from an env variable.
- [envlog](https://pypi.org/project/envlog/): levels from a `RUST_LOG`-like env variable, but it configures root itself.

## Development

The tooling follows [pymplate](https://github.com/karlicoss/pymplate).
Install tox with its uv plugin once:

```bash
uv tool install --with tox-uv tox
```

Run the local checks with:

```bash
tox -e ruff,format,tests,mypy,ty
```

For a targeted test run, use `tox -e tests -- -k <pattern>`.

The requirements doc is rendered from `doc/requirements.qmd` with [Quarto](https://quarto.org), run `tox -e quarto` after changing it or the tests.
The rendered `doc/requirements.md` is committed, and CI checks it's up to date.

## Releases

Pushes to the default branch publish to TestPyPI, and version tags such as `v0.1.20261010` publish to PyPI, via GitHub Actions.
The setup (Trusted Publishing, release scripts in `.ci/`) follows [pymplate](https://github.com/karlicoss/pymplate).
