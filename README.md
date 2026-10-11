# kloggy

Logging helper: nice zero-config output for libraries, without fighting the app's logging setup.
It started as a shared helper for [HPI](https://github.com/karlicoss/HPI), [promnesia](https://github.com/karlicoss/promnesia),
  [orger](https://github.com/karlicoss/orger), [cachew](https://github.com/karlicoss/cachew) and data exporters like [rexport](https://github.com/karlicoss/rexport),
  but nothing in it is specific to them.

It's developed requirements-first: see [requirements](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md), linked to the tests validating them.
Work in progress, only the requirements listed there are implemented so far.

Library code gets plain stdlib loggers:

```python
from kloggy import get_logger

logger = get_logger(__name__)
```

- if logging isn't configured, records are never printed as bare messages ([Z1](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#z1)),
    and INFO is shown, e.g. for progress ([L2](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#l2))
- if the app configures logging later (e.g. `basicConfig()` in `main()`), kloggy steps aside for good:
    no duplicates ([Z2](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#z2)),
    and the app's levels apply ([L3](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#l3))
- a stray `logging.warning(...)` (which implicitly calls `basicConfig()`) doesn't make kloggy step aside ([Z3](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#z3))
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
Unlike `setLevel()` in the module, it's only kloggy's default, so levels set by the app or via `KLOGGY_LEVEL` still win.

Users can set levels for packages using kloggy via the `KLOGGY_LEVEL` environment variable,
  e.g. `KLOGGY_LEVEL=warning,pkg.sub=debug,pkg.noisy=off` ([V1](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#v1)).
The syntax follows Rust's `RUST_LOG`: `off` silences a logger completely, and the most specific entry wins.
These apply even if the app configures logging.

Output is coloured by level on a terminal, via colorlog, which also honours `NO_COLOR` and `FORCE_COLOR`
  ([F2](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#f2)).

If kloggy causes problems, `KLOGGY_DISABLE=1` disables it completely, so logging behaves exactly as plain stdlib,
  without changing any code ([L5](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#l5)).

Avoid `get_logger(__package__)`:
- records lose their module name (`pkg.sub` instead of `pkg.sub.module`), so individual modules can't be configured
- it's `''` under `python -m` (i.e. the root logger) and `None` in a script run directly

Outside `except` blocks, log exceptions with `exc_info=e`, e.g. `logger.error('while parsing %s', path, exc_info=e)`, so the traceback is kept with any logging setup
  (kloggy's output adds it for `logger.error(e)` anyway, [X1](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#x1)).

Avoid logging via the root logger (`logging.warning(...)` etc.), use the module logger instead (ruff rule [`LOG015`](https://docs.astral.sh/ruff/rules/root-logger-call/) catches these).
Such calls implicitly call `basicConfig()`.
kloggy copes with that ([Z3](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#z3)), but an app's own `basicConfig(...)` called later is then silently ignored.

## Using kloggy in an app

Call `kloggy.setup()` in `main()` instead of `logging.basicConfig()` ([A1](https://github.com/karlicoss/kloggy/blob/master/doc/requirements.md#a1)):

```python
import kloggy


def main() -> None:
    kloggy.setup()  # or e.g. kloggy.setup(level='debug')
```

Every logger then gets kloggy's output, also libraries not using kloggy, at INFO by default.
Like `basicConfig()`, root's level applies to every logger, and `setup()` does nothing if logging is already configured.
`datefmt` works as in `basicConfig()`, e.g. `datefmt='%Y-%m-%d %H:%M:%S'` drops the milliseconds.

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
