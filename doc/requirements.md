# kloggy requirements


- [Principles](#principles)
- [Definitions](#definitions)
  - [Fallback handler](#fallback-handler)
  - [Configured](#configured)
  - [Steps aside](#steps-aside)
  - [kloggy's output](#output)
- [L: library-side API](#l-library-side-api)
  - [L1: Existing configuration is left untouched](#l1)
  - [L2: INFO by default](#l2)
  - [L3: The app's levels apply once it configures logging](#l3)
  - [L4: Named `get_logger`](#l4)
  - [L5: `KLOGGY_DISABLE` opts out of kloggy completely](#l5)
  - [L6: Per-module default levels](#l6)
  - [L7: `get_logger()` refuses the root logger](#l7)
- [Z: zero-config output](#z-zero-config-output)
  - [Z1: No bare messages](#z1)
  - [Z2: kloggy steps aside permanently once logging is configured](#z2)
  - [Z3: Default `basicConfig()` handler doesn't count as configured](#z3)
  - [Z4: Output goes to the current `sys.stderr`](#z4)
- [V: verbosity](#v-verbosity)
  - [V1: `KLOGGY_LEVEL` sets levels for packages using kloggy](#v1)
- [A: application-side setup](#a-application-side-setup)
  - [A1: `setup()` sets up logging for the whole app](#a1)
- [F: output format](#f-output-format)
  - [F1: Level, time, logger and source location](#f1)
  - [F2: Coloured by level on a terminal](#f2)
- [X: exceptions](#x-exceptions)
  - [X1: Exceptions logged as the message show their traceback](#x1)
- [W: warnings](#w-warnings)
  - [W1: `kloggy.warnings.setup()` makes warnings stand out](#w1)
  - [W2: `warn_once()` warns once per message](#w2)
- [C: concurrency](#c-concurrency)
  - [C1: Logging from several threads at once](#c1)
  - [C2: Logging from several processes](#c2)
- [P: progress (experimental)](#p)
  - [P1: Logging progress through a loop](#p1)
  - [P2: Progress bars on a terminal](#p2)
  - [P3: One display for the whole process](#p3)
  - [P4: Picking a display automatically](#p4)

kloggy is developed requirements-first: requirements are agreed on before they are implemented, and link to the tests validating them.
Implementation: [`src/kloggy/__init__.py`](../src/kloggy/__init__.py), tests: [`src/kloggy/tests/`](../src/kloggy/tests/),
and [`src/kloggy/progress/tests/`](../src/kloggy/progress/tests/) for progress ([P](#p)).

Requirement IDs are stable: don't renumber, retire instead.

## Principles

- **The app always wins:** kloggy's output is only a fallback while logging isn't configured.
  Once the app configures logging, its handlers and levels apply ([L1](#l1), [L3](#l3), [Z2](#z2)), and so does its own `setLevel()` ([V1](#v1)).
- **Stdlib-shaped:** library code only deals with plain `logging.Logger` objects ([L2](#l2)),
  so kloggy can be disabled without changing any code ([L5](#l5)).

## Definitions

### Fallback handler

The handler `get_logger()` adds on the top-level package logger (`pkg` for `pkg.sub.module`), once per package.
It prints records while logging isn't [configured](#configured) ([Z1](#z1)), until kloggy [steps aside](#steps-aside).
The handler `setup()` adds on root ([A1](#a1)) is a different one: an ordinary configuration, like `basicConfig()`'s.

### Configured

Logging is configured for a logger if its records would reach some handler other than the [fallback handler](#fallback-handler):
walking up from the logger to root, stopping at the first logger with `propagate = False`.
Except root's default `basicConfig()` handler doesn't count, see [Z3](#z3).
The one `setup()` adds does count, see [A1](#a1).

This is the notion stdlib itself uses: `Logger.callHandlers` falls back to `logging.lastResort` only when that walk finds no handlers,
and `Logger.hasHandlers()` does the same walk.
Note that `basicConfig()` uses a narrower check (`root.handlers` is non-empty).

### Steps aside

kloggy steps aside for a logger the first time it notices logging [configured](#configured) for it, and that's permanent ([Z2](#z2)).
From then on, the fallback handler leaves the logger's records to the app's handlers, and the logger's levels are stdlib's ([L3](#l3)):
kloggy's default levels ([L2](#l2), [L6](#l6)) no longer apply.
Levels from `KLOGGY_LEVEL` still do, since they're real logger levels ([V1](#v1)).

<a id="output"></a>

### kloggy's output

What kloggy's handlers print: the [fallback handler](#fallback-handler), and the one `setup()` adds ([A1](#a1)).
That's the format from [F1](#f1), coloured on a terminal ([F2](#f2)), with tracebacks for exceptions logged as the message ([X1](#x1)),
written to the current `sys.stderr` ([Z4](#z4)).

## L: library-side API

<a id="l1"></a>

### L1: Existing configuration is left untouched

If logging is already [configured](#configured) for a logger when `get_logger()` is called for it, kloggy doesn't touch logging state:
no handlers added, no levels set, and the logger's class isn't switched ([L2](#l2)).
The only exception are levels the user explicitly asks for via `KLOGGY_LEVEL` ([V1](#v1)).
Output is then exactly what it would be without kloggy, for good (test: [`l1_configured_before_untouched`](../src/kloggy/tests/test_library.py#L13 "test_l1_configured_before_untouched")).

E.g. after `basicConfig(level=ERROR)`, the app only gets errors from `pkg.*`, in its own format.

**Edge case:** a bare `basicConfig()`, e.g. called implicitly by a stray `logging.warning(...)`, doesn't count as configured, see [Z3](#z3).

**Related:**

- logging configured *after* `get_logger()`: see [L3](#l3), [Z2](#z2)

<a id="l2"></a>

### L2: INFO by default

While logging isn't [configured](#configured), loggers returned by `get_logger()` show INFO, rather than stdlib's default WARNING (test: [`l2_info_by_default`](../src/kloggy/tests/test_library.py#L71 "test_l2_info_by_default")).
This is a deliberate, opinionated choice: INFO gives a sense of progress (e.g. `processing [3/100] ...`) without any setup.

kloggy never sets any levels on its own: the INFO default isn't stored on any logger, so there's nothing the app could mistake for its own.
It only sets levels the user explicitly asks for via `KLOGGY_LEVEL` ([V1](#v1)).

Levels set explicitly (e.g. by the app, on the logger itself or an ancestor below root) still apply
(tests: [`l2_explicit_level`](../src/kloggy/tests/test_library.py#L288 "test_l2_explicit_level"), [`l2_level_changed_since`](../src/kloggy/tests/test_library.py#L269 "test_l2_level_changed_since")).

In a package where some modules use `get_logger()`, modules still using plain `logging.getLogger()` keep stdlib's levels
(tests: [`l3_configured_after_plain_logger`](../src/kloggy/tests/test_library.py#L114 "test_l3_configured_after_plain_logger"), [`l3_configured_after_on_module_logger_plain_logger`](../src/kloggy/tests/test_library.py#L166 "test_l3_configured_after_on_module_logger_plain_logger")).
Their records are still printed by kloggy while logging isn't configured, so a package can migrate one module at a time
(test: [`l2_plain_logger`](../src/kloggy/tests/test_library.py#L334 "test_l2_plain_logger")).
That only changes how their records look, never which ones are shown.

**Mechanism:** `get_logger()` returns the same object as `logging.getLogger()`, switched to a kloggy subclass of `logging.Logger`.
If the app installed its own logger class (`logging.setLoggerClass()`), kloggy uses a subclass of both, so it keeps its behaviour
(test: [`l2_app_logger_class`](../src/kloggy/tests/test_library.py#L311 "test_l2_app_logger_class")).
kloggy doesn't call `logging.setLoggerClass()` itself:
that would affect every logger created afterwards, including other libraries', and the app may need it for its own class.

<a id="l3"></a>

### L3: The app's levels apply once it configures logging

Once the app configures logging, its levels apply straight away, e.g. after `basicConfig(level=ERROR)` in `main()` after imports
(tests: [`l3_configured_after`](../src/kloggy/tests/test_library.py#L89 "test_l3_configured_after"), [`l3_configured_after_on_module_logger`](../src/kloggy/tests/test_library.py#L138 "test_l3_configured_after_on_module_logger"), [`l3_effective_level`](../src/kloggy/tests/test_library.py#L405 "test_l3_effective_level")).
Both ways: no stray INFO if the app wants less, and e.g. DEBUG right after `basicConfig(level=DEBUG)` if it wants more
(test: [`l3_configured_after_more_verbose`](../src/kloggy/tests/test_library.py#L191 "test_l3_configured_after_more_verbose")).

This is per logger, same as kloggy stepping aside in [Z2](#z2) (test: [`l3_configured_after_on_subpackage`](../src/kloggy/tests/test_library.py#L213 "test_l3_configured_after_on_subpackage")).

Records created at kloggy's INFO just before the app configured logging, but reaching the handlers after (e.g. in another thread), are dropped,
so the app never gets records below its levels (tests: [`l3_created_before_configured`](../src/kloggy/tests/test_library.py#L356 "test_l3_created_before_configured"), [`l3_concurrent`](../src/kloggy/tests/test_library.py#L238 "test_l3_concurrent")).

**Caveats:**

- a disabled call, e.g. `logger.debug(...)`, costs ~0.6-0.9 µs instead of stdlib's ~0.1 µs:
  whether it's enabled depends on whether logging is configured, so stdlib's cached level checks can't be used.
  Once kloggy steps aside for the logger ([Z2](#z2)), it costs ~0.25 µs.
- a record passed to `Logger.handle()` by hand, below its logger's level, is dropped once logging is configured:
  kloggy can't tell it from one created just before the app configured logging (see above)

**Rejected alternatives:**

- setting INFO on the package logger, and resetting it once kloggy notices the app's configuration:
  it only notices via records, so stray INFO and lost DEBUG around the switch,
  and configuring one subpackage takes INFO away from the whole package
- a special level comparing as INFO until logging is configured, and as the app's level after:
  leaks via `getEffectiveLevel()`, where it compares inconsistently (equal to INFO, yet not above DEBUG)

<a id="l4"></a>

### L4: Named `get_logger`

The function is named `get_logger`, not `getLogger`:

- it isn't a pure stdlib passthrough ([L2](#l2), and it may add the [fallback handler](#fallback-handler)),
  so the call site should make it obvious it's kloggy's, unlike `from kloggy import getLogger` vs `from logging import getLogger`
- snake_case is PEP 8 and what newer libraries use (e.g. `structlog.get_logger`); stdlib's camelCase is legacy

<a id="l5"></a>

### L5: `KLOGGY_DISABLE` opts out of kloggy completely

With `KLOGGY_DISABLE=1`, `get_logger()` returns plain `logging.getLogger()` loggers without touching anything:
no handler, no class switch, and `KLOGGY_LEVEL` is ignored (test: [`l5_disabled`](../src/kloggy/tests/test_disable.py#L10 "test_l5_disabled")).
So logging behaves exactly as plain stdlib, e.g. if kloggy causes problems, without changing any code.

Values are the usual boolean words, as in systemd: `1`, `true`, `yes`, `on` disable kloggy, `0`, `false`, `no`, `off` don't, case-insensitive.
Empty means not set (test: [`l5_values`](../src/kloggy/tests/test_disable.py#L53 "test_l5_values")).
Anything else is ignored with a warning naming `KLOGGY_DISABLE` (test: [`l5_invalid`](../src/kloggy/tests/test_disable.py#L72 "test_l5_invalid")).
It's read once, on the first `get_logger()` or `setup()` call.

**Rejected alternatives:**

- an empty `KLOGGY_LEVEL`: variables often end up empty by accident (e.g. wrapper scripts passing through an unset variable),
  and empty usually means unset
- `KLOGGY_LEVEL=off`: `off` means silence, while opting out still prints warnings via stdlib's `logging.lastResort`
- any non-empty value disables, like many `PYTHON*` variables: then `KLOGGY_DISABLE=0` would disable kloggy too

<a id="l6"></a>

### L6: Per-module default levels

With `get_logger(__name__, default_level=...)`, a module picks its own default instead of INFO ([L2](#l2)),
e.g. `default_level='warning'` for a module whose INFO is too chatty in a typical run (test: [`l6_default_level`](../src/kloggy/tests/test_library.py#L427 "test_l6_default_level")).
Child loggers inherit it, and the nearest default wins (test: [`l6_nearest_default`](../src/kloggy/tests/test_library.py#L447 "test_l6_nearest_default")).
It also applies to records other code logs through the module's logger, e.g. cachew logs through the decorated function's module logger
(test: [`l6_other_code`](../src/kloggy/tests/test_library.py#L465 "test_l6_other_code")).

Like INFO ([L2](#l2)), it's only a default for kloggy's output, never set on the logger itself, so:

- levels set explicitly, on the logger or an ancestor below root, win, also if the app set them before the module was imported
  (test: [`l6_explicit_level`](../src/kloggy/tests/test_library.py#L483 "test_l6_explicit_level"))
- that includes `KLOGGY_LEVEL` ([V1](#v1)), e.g. `KLOGGY_LEVEL=debug` shows DEBUG from such modules too (test: [`l6_kloggy_level`](../src/kloggy/tests/test_library.py#L509 "test_l6_kloggy_level"))
- once the app configures logging, the app's levels apply, same as for INFO ([L3](#l3)) (test: [`l6_app_configured`](../src/kloggy/tests/test_library.py#L526 "test_l6_app_configured"))

If several calls pass different defaults for the same logger, the last one wins (test: [`l6_last_wins`](../src/kloggy/tests/test_library.py#L546 "test_l6_last_wins")).
Level names are the same as in `KLOGGY_LEVEL`, case-insensitive, and `logging` constants work too.
An unknown name is an error, since it's a bug in the code (test: [`l6_invalid`](../src/kloggy/tests/test_library.py#L563 "test_l6_invalid")).

It's named `default_level`, since stdlib's `level` means a level set on the logger.

**Considered alternatives:**

- `setLevel()` in the module: the app's `basicConfig(level=DEBUG)` doesn't reach the module, since it only sets root's level.
  It also overwrites levels set before the module was imported (e.g. with lazy imports, or pytest's `caplog`), including `KLOGGY_LEVEL`'s.
- no per-module defaults, demoting chatty messages to DEBUG instead:
  doesn't help with records other code logs through the module's logger, e.g. cachew's

<a id="l7"></a>

### L7: `get_logger()` refuses the root logger

`get_logger()` with a name stdlib maps to the root logger (`''`, `None` or `'root'`) is an error (test: [`l7_root_logger`](../src/kloggy/tests/test_library.py#L580 "test_l7_root_logger")):
a library never owns the root logger, so it's always a mistake,
e.g. `get_logger(__package__)`, since `__package__` is `''` under `python -m` and `None` in a script run directly.

Otherwise kloggy would add its handler to root, so it would print every library's records,
and the app's `basicConfig()` would silently do nothing, since root already has a handler.

Plain `logging.getLogger('')` stays fine: that's how an app gets the root logger to configure it.
With `KLOGGY_DISABLE` ([L5](#l5)), `get_logger()` is plain `logging.getLogger()`, without this check (test: [`l7_disabled`](../src/kloggy/tests/test_library.py#L596 "test_l7_disabled")).

## Z: zero-config output

<a id="z1"></a>

### Z1: No bare messages

While logging isn't [configured](#configured), records from packages using kloggy are never printed as a bare message:
the output includes at least the level and the logger name (test: [`z1_not_bare`](../src/kloggy/tests/test_zero_config.py#L36 "test_z1_not_bare")).
This holds until kloggy [steps aside](#steps-aside) for the record's logger ([Z2](#z2)).

Stdlib's fallback in that case (`logging.lastResort`) has no formatter, i.e. `%(message)s`:
`logger.error('some error')` prints just `some error`, which looks the same as a warning and can't be traced to where it came from
(test: [`z1_stdlib_baseline`](../src/kloggy/tests/test_zero_config.py#L22 "test_z1_stdlib_baseline")).
Even `basicConfig()`'s default `logging.BASIC_FORMAT` (`%(levelname)s:%(name)s:%(message)s`, i.e. `ERROR:__main__:some error`) satisfies this.

**Related:**

- the specific format: see [F1](#f1)
- which levels are shown when nothing is configured: see [L2](#l2)

<a id="z2"></a>

### Z2: kloggy steps aside permanently once logging is configured

Once logging is [configured](#configured) for a logger, kloggy [steps aside](#steps-aside) for that logger, for the rest of the process:
the fallback handler leaves the logger's records to the app's handlers, and the logger's levels are stdlib's ([L3](#l3)).
So when the app configures logging *after* `get_logger()`, kloggy's output stops, and each record is printed exactly once, by the app's handlers.
E.g. `basicConfig(format=...)` in the app's `main()` (a bare `basicConfig()` is an exception, see [Z3](#z3)), a handler on the package logger or the record's own logger, a `NullHandler` (explicitly asking for silence), pytest's log capture
(test: [`z2_configured_after`](../src/kloggy/tests/test_zero_config.py#L54 "test_z2_configured_after")).

This is per logger: if the app only configures `pkg.sub` (e.g. a handler on it), kloggy keeps handling `pkg.other` (test: [`z2_stays_off_per_logger`](../src/kloggy/tests/test_zero_config.py#L155 "test_z2_stays_off_per_logger")).

Removing the app's handlers later doesn't bring kloggy back: output is then what it would be without kloggy, i.e. stdlib's `logging.lastResort`
(test: [`z2_stays_off_when_unconfigured`](../src/kloggy/tests/test_zero_config.py#L110 "test_z2_stays_off_when_unconfigured")).
So output doesn't depend on whether logging was configured before or after `get_logger()` (test: [`z2_stays_off_when_configured_at_setup`](../src/kloggy/tests/test_zero_config.py#L133 "test_z2_stays_off_when_configured_at_setup")).

kloggy notices configuration when it looks: in `get_logger()`, in a level check, or when a record reaches its handler.
Also if another thread removes the app's handler right in the middle of a level check (test: [`z2_configuration_changes_during_level_check`](../src/kloggy/tests/test_zero_config.py#L203 "test_z2_configuration_changes_during_level_check")).
If the app adds and then removes handlers without logging anything in between, kloggy carries on.

**Rejected alternatives:**

- resuming kloggy's output once the app's handlers are removed, i.e. deciding per record like stdlib's `lastResort`:
  output then depended on whether logging was configured before or after `get_logger()`.
  The motivation was pytest `caplog`, but pytest keeps its own handlers on root for the whole session,
  so removing caplog's handler doesn't leave logging unconfigured anyway.

<a id="z3"></a>

### Z3: Default `basicConfig()` handler doesn't count as configured

If root's only handler is the one a default `basicConfig()` creates, that handler doesn't count towards logging being [configured](#configured)
(tests: [`z3_stray_call_before`](../src/kloggy/tests/test_zero_config.py#L256 "test_z3_stray_call_before"), [`z3_stray_call_after`](../src/kloggy/tests/test_zero_config.py#L275 "test_z3_stray_call_after")).

**Motivation:** bare root-level calls like `logging.warning(...)` call `basicConfig()` implicitly if root has no handlers.
Without this, one such stray call anywhere (e.g. in a dependency) would make kloggy step aside for every logger, for the rest of the process,
with no fix short of an explicit setup call.
Code should use a module logger instead (ruff's [`LOG015`](https://docs.astral.sh/ruff/rules/root-logger-call/) flags such calls), but a dependency may still make them.

**Detection:** root's only handler is exactly what a bare `basicConfig()` creates, and root's level is still `WARNING`.
Any customisation counts as configured: format, level other than `WARNING`, file, handlers, or changing that handler afterwards
(test: [`z3_configured_after_stray_call`](../src/kloggy/tests/test_zero_config.py#L300 "test_z3_configured_after_stray_call")).

**Accepted misfires**, since the state is indistinguishable: an explicit `basicConfig()`, `basicConfig(level=WARNING)` or `basicConfig(stream=sys.stderr)`.
Then kloggy's records keep kloggy's output, while the rest of the app's output is in `BASIC_FORMAT` (test: [`z3_explicit_bare_basic_config`](../src/kloggy/tests/test_zero_config.py#L332 "test_z3_explicit_bare_basic_config")).

Levels follow the same rule, no special case: with only the default handler, kloggy keeps its INFO default (test: [`z3_stray_call_keeps_info`](../src/kloggy/tests/test_zero_config.py#L349 "test_z3_stray_call_keeps_info")).
So the accepted misfires also get INFO from packages using kloggy.

To avoid both, use any non-default `basicConfig()` argument; for just the levels, e.g. `logging.getLogger('pkg').setLevel(...)`.

**Duplicates:** after printing a record kloggy drops it, so that default handler skips it.
So kloggy doesn't touch root's handler, and other loggers' records are unaffected.

**Rejected alternatives:**

- telling implicit `basicConfig()` calls from explicit ones by watching calls via `sys.monitoring`: precise, but too hacky
- `propagate = False` on the package logger while root only has the default handler:
  interferes with the "configured" walk, which stops at `propagate = False`, so kloggy would have to track which flag it set itself
- a filter on that default handler dropping records kloggy marked as printed: works, but touches root's handler

<a id="z4"></a>

### Z4: Output goes to the current `sys.stderr`

When `sys.stderr` is replaced, [kloggy's output](#output) goes to the replacement, also if kloggy's handler was created before that
(test: [`z4_replaced_stderr`](../src/kloggy/tests/test_zero_config.py#L368 "test_z4_replaced_stderr")).

Some tools replace `sys.stderr` for a while: e.g. `contextlib.redirect_stderr` or pytest's `capsys` to capture output,
or a [rich](https://github.com/Textualize/rich) progress bar, which prints everything written to it above the bar.
So a rich progress bar doesn't mangle kloggy's output (test: [`z4_rich`](../src/kloggy/tests/test_zero_config.py#L447 "test_z4_rich")).
Colour ([F2](#f2)) is decided for the replacement as well, e.g. no colour codes in captured output (test: [`z4_colour_follows`](../src/kloggy/tests/test_zero_config.py#L391 "test_z4_colour_follows")).
Once `sys.stderr` is switched back, kloggy doesn't hold on to the replacement, so e.g. a buffer with lots of captured output can be freed (test: [`z4_not_kept_alive`](../src/kloggy/tests/test_zero_config.py#L422 "test_z4_not_kept_alive")).

That's the same as stdlib's own fallback, `logging.lastResort`: it writes to whatever `sys.stderr` is when each record is printed.

This is **unlike** `basicConfig()`'s `StreamHandler`, which keeps the `sys.stderr` it saw when it was created.
So its output bypasses later replacements, e.g. each line gets glued onto a frozen copy of a rich progress bar.

Python considers this `StreamHandler` behaviour deliberate, it was closed as not a bug in [bpo-36193](https://bugs.python.org/issue36193):
a `StreamHandler` writes to exactly the stream it was given, which suits an app's own configuration, set up once at startup.

The [fallback handler](#fallback-handler) is more like `lastResort`: it's created when a library is imported, and only prints while nothing is configured.

One consequence, the same as with `lastResort`: code that redirects `sys.stderr` to silence something silences kloggy's output too
(test: [`z4_replaced_stderr`](../src/kloggy/tests/test_zero_config.py#L368 "test_z4_replaced_stderr")).

## V: verbosity

<a id="v1"></a>

### V1: `KLOGGY_LEVEL` sets levels for packages using kloggy

The `KLOGGY_LEVEL` environment variable sets levels for packages using kloggy, i.e. where some module calls `get_logger()`, e.g. `KLOGGY_LEVEL=warning,pkg.sub=debug`.
A level without a logger name is the default for each such package (test: [`v1_default`](../src/kloggy/tests/test_level_control.py#L10 "test_v1_default")).
Other entries set the level of a specific logger in it, hierarchically, and the most specific one wins regardless of order
(test: [`v1_entries`](../src/kloggy/tests/test_level_control.py#L28 "test_v1_entries")).

Packages which don't use kloggy aren't affected, even if they're named in the spec (test: [`v1_other_packages`](../src/kloggy/tests/test_level_control.py#L47 "test_v1_other_packages")):
kloggy only changes code that opted into it.

The syntax and precedence follow Rust's `RUST_LOG` (as in [env_logger](https://docs.rs/env_logger)), so they're familiar:

- level names are case-insensitive, `warn` works too, and `off` silences a logger completely (test: [`v1_level_names`](../src/kloggy/tests/test_level_control.py#L71 "test_v1_level_names"))
- a later entry for the same logger wins, and empty entries (e.g. a trailing comma) are skipped (test: [`v1_later_wins`](../src/kloggy/tests/test_level_control.py#L92 "test_v1_later_wins"))
- invalid entries, e.g. an unknown level, are ignored with a warning naming `KLOGGY_LEVEL`, and the rest still applies
  (test: [`v1_invalid`](../src/kloggy/tests/test_level_control.py#L124 "test_v1_invalid")).
  The spec is read once, on the first `get_logger()` call, so it doesn't warn for every package.

Differences from `RUST_LOG`:

- entries match by dotted name: `pkg` matches `pkg.sub`, but not `pkgfoo` (`RUST_LOG` matches by string prefix)
- a level without a logger name only applies to packages using kloggy, and loggers without a matching entry keep their levels
  (`RUST_LOG` applies it to everything, and silences everything without a matching entry)
- Python's level names, so no `trace`

These are levels the user explicitly asks for, so unlike kloggy's INFO default ([L2](#l2)) they're real logger levels.
So they apply even if the app configures logging, before or after the package calls `get_logger()` (test: [`v1_app_configured`](../src/kloggy/tests/test_level_control.py#L151 "test_v1_app_configured")).
But the app always wins: levels already set explicitly aren't overridden (test: [`v1_app_set_level_before`](../src/kloggy/tests/test_level_control.py#L197 "test_v1_app_set_level_before")),
and since they're set when a package first calls `get_logger()`, the app's own `setLevel()` after that wins too (test: [`v1_app_set_level_later`](../src/kloggy/tests/test_level_control.py#L174 "test_v1_app_set_level_later")).

**Rejected alternatives:**

- `LOGGING_LEVEL`: too common a name for one library to claim
- applying entries to any logger, including packages not using kloggy: it would change code that never opted into kloggy

## A: application-side setup

<a id="a1"></a>

### A1: `setup()` sets up logging for the whole app

When the app calls `kloggy.setup()`, e.g. in its `main()` instead of `basicConfig()`,
every logger gets [kloggy's output](#output), also in libraries not using kloggy (test: [`a1_setup`](../src/kloggy/tests/test_app.py#L12 "test_a1_setup")).

Like `basicConfig()`, it adds a handler on root and sets root's level, INFO by default (test: [`a1_level`](../src/kloggy/tests/test_app.py#L31 "test_a1_level")).
So it's an ordinary configuration: kloggy steps aside ([Z2](#z2)), and root's level applies to every logger,
also instead of kloggy's own defaults ([L2](#l2), [L6](#l6)) (test: [`a1_default_level`](../src/kloggy/tests/test_app.py#L50 "test_a1_default_level")).
`KLOGGY_LEVEL` still applies, since it sets real levels ([V1](#v1)) (test: [`a1_kloggy_level`](../src/kloggy/tests/test_app.py#L65 "test_a1_kloggy_level")).

Unlike `basicConfig()`'s handler, the output is kloggy's: the format ([F1](#f1)), colour ([F2](#f2)) and tracebacks ([X1](#x1)),
and it goes to the current `sys.stderr` ([Z4](#z4)), e.g. through a rich progress bar (test: [`a1_current_stderr`](../src/kloggy/tests/test_app.py#L86 "test_a1_current_stderr")).
The time format can be changed as in `basicConfig()`, e.g. `setup(datefmt='%Y-%m-%d %H:%M:%S')` without milliseconds,
and by default it's F1's, with milliseconds (test: [`a1_datefmt`](../src/kloggy/tests/test_app.py#L114 "test_a1_datefmt")).

Also like `basicConfig()`, it does nothing if logging is already configured, e.g. by the app or an earlier `setup()` call,
so nothing is printed twice (tests: [`a1_already_configured`](../src/kloggy/tests/test_app.py#L132 "test_a1_already_configured"), [`a1_twice`](../src/kloggy/tests/test_app.py#L150 "test_a1_twice")).
Except root's default `basicConfig()` handler, e.g. from a stray `logging.warning()` ([Z3](#z3)), which it replaces
(test: [`a1_stray_basic_config`](../src/kloggy/tests/test_app.py#L168 "test_a1_stray_basic_config")).

With `KLOGGY_DISABLE` ([L5](#l5)), it's plain `basicConfig(level=...)` (test: [`a1_disabled`](../src/kloggy/tests/test_app.py#L186 "test_a1_disabled")).

**Considered alternatives:**

- kloggy keeps handling its packages' levels after `setup()`, i.e. root's handler doesn't count as configured:
  packages using kloggy keep INFO and per-module defaults while other libraries stay at WARNING,
  but then records need deduplicating between the fallback handler and root's.
  Root's level for every logger is simpler, and libraries rarely log at INFO.

## F: output format

<a id="f1"></a>

### F1: Level, time, logger and source location

kloggy's output shows the level, time, logger name and source location of each record (test: [`f1_format`](../src/kloggy/tests/test_output_format.py#L13 "test_f1_format")):

``` text
[INFO    2026-10-10 12:00:00,123 pkg.sub.mod mod.py:42  ] some message
```

i.e. `[%(levelname)-7s %(asctime)s %(name)s %(filename)s:%(lineno)-4d] %(message)s`:

- the level is padded to 7 characters, so DEBUG, INFO, WARNING and ERROR line up.
  The rare CRITICAL is one character wider, rather than truncated.
- the timestamp includes milliseconds: only 4 characters, and handy as a rough profiler
- both the logger name and the file: mostly redundant, but not when a record is logged via another module's logger,
  e.g. cachew logs through the decorated module's logger, and the file still shows where it came from (test: [`f1_file`](../src/kloggy/tests/test_output_format.py#L32 "test_f1_file"))
- the line number is padded to 4 characters, so messages mostly line up

<a id="f2"></a>

### F2: Coloured by level on a terminal

On a terminal, the prefix in brackets is coloured by level (test: [`f2_tty`](../src/kloggy/tests/test_output_format.py#L57 "test_f2_tty")).
[colorlog](https://github.com/borntyping/python-colorlog) does the colouring, and decides when:
`FORCE_COLOR` colours even if the stream isn't a terminal (test: [`f2_force_color`](../src/kloggy/tests/test_output_format.py#L89 "test_f2_force_color")),
`NO_COLOR` disables colour, and otherwise only a terminal gets colour, e.g. not output redirected to a file (test: [`f1_format`](../src/kloggy/tests/test_output_format.py#L13 "test_f1_format")).

colorlog is a hard dependency, so output looks the same everywhere.
It's small, has no dependencies except `colorama` on Windows, and is actively maintained (several releases in 2026).

## X: exceptions

<a id="x1"></a>

### X1: Exceptions logged as the message show their traceback

When an exception is logged as the message at ERROR or above, [kloggy's output](#output) shows its traceback, even outside an `except` block
(test: [`x1_error`](../src/kloggy/tests/test_exceptions.py#L25 "test_x1_error")).

E.g. errors collected while processing, to keep going and report them at the end:

``` python
errors = []
for path in paths:
    try:
        parse(path)
    except ValueError as e:
        errors.append(e)
for e in errors:
    logger.error(e)
```

Plain stdlib formats the message as `str(e)`, so it prints just `malformed file: b.json`:
not even the exception type, let alone where it was raised.
That's especially bad for terse exceptions, e.g. a `KeyError` prints just `'id'`.
The traceback is still there, in `e.__traceback__`, but stdlib only shows it if the call passes `exc_info`.

kloggy's output includes it:

``` text
[ERROR   2026-10-10 21:36:28,639 pkg.mod mod.py:22  ] malformed file: b.json
Traceback (most recent call last):
  File "mod.py", line 14, in collect
    parse(path)
  File "mod.py", line 7, in parse
    raise ValueError(f'malformed file: {path}')
ValueError: malformed file: b.json
```

This includes `logger.exception(e)` outside an `except` block, which stdlib would print with `NoneType: None` instead
(test: [`x1_exception_outside_handler`](../src/kloggy/tests/test_exceptions.py#L41 "test_x1_exception_outside_handler")).

Below ERROR, it's just the message: e.g. warnings are often expected failures, like a skipped file (test: [`x1_warning`](../src/kloggy/tests/test_exceptions.py#L57 "test_x1_warning")).
An explicit `exc_info` always wins, also `exc_info=False` asking for no traceback (test: [`x1_explicit_exc_info`](../src/kloggy/tests/test_exceptions.py#L71 "test_x1_explicit_exc_info")).

The record itself isn't changed, only kloggy's output: once the app configures logging, its handlers get the usual stdlib behaviour
(test: [`x1_app_configured`](../src/kloggy/tests/test_exceptions.py#L92 "test_x1_app_configured")).

**Recommendation:** outside `except` blocks, pass the exception explicitly, whether you use kloggy or not,
e.g. `logger.error('while parsing %s', path, exc_info=e)`, which keeps the traceback with any logging setup.
ruff's `LOG` rules catch most mistakes here, but only on objects ruff knows are loggers:
e.g. `logger = get_logger(__name__)` in the same module works,
but a logger imported from another module (`from .common import logger`) has to be listed in ruff's
[`lint.logger-objects`](https://docs.astral.sh/ruff/settings/#lint_logger-objects) setting, otherwise its calls are silently skipped.

| Call, outside an `except` block  | ruff                                                                                                                |
|----------------------------------|---------------------------------------------------------------------------------------------------------------------|
| `logger.exception(e)`            | [`LOG004`](https://docs.astral.sh/ruff/rules/log-exception-outside-except-handler/): stdlib prints `NoneType: None` |
| `logger.error(e, exc_info=True)` | [`LOG014`](https://docs.astral.sh/ruff/rules/exc-info-outside-except-handler/): same                                |
| `logger.error(e, exc_info=e)`    | fine                                                                                                                |
| `logger.error(e)`                | not caught: the traceback is silently lost, hence X1                                                                |

**Considered alternatives:**

- adding the traceback to the record itself, for all handlers:
  then the app's handlers would get tracebacks the code never asked for, unlike plain stdlib ([L1](#l1))
- a lint check instead, so that call sites always pass `exc_info=e`:
  ruff can't tell `e` is an exception outside an `except` block, that needs type information.
  ty has no plugin system, and a mypy plugin works, but every project would have to enable it in its mypy configuration.

Worth reconsidering once static checks can use type information, e.g. if ruff gets type-aware rules on top of ty:
then a lint rule could flag `logger.error(e)` as well, and fixing call sites might be enough.

## W: warnings

<a id="w1"></a>

### W1: `kloggy.warnings.setup()` makes warnings stand out

An app can call `kloggy.warnings.setup()` (after `import kloggy.warnings`) to show each warning on one line, coloured on a terminal: the location dimmed, the category and message red.
It's stdlib's first line, so terminals and editors can still jump to the location,
without the source line stdlib prints under it (test: [`w1_format`](../src/kloggy/tests/test_warnings.py#L12 "test_w1_format")):

``` text
/path/to/config.py:12: FutureWarning: my.cfg is deprecated, import my.config instead
```

That source line is often just the `warnings.warn(...)` call repeating the message, e.g. for a module-level warning in a deprecated module.
And stdlib doesn't colour warnings at all, unlike tracebacks, so they're easy to miss among log lines.

Colour follows the same rules as kloggy's log output ([F2](#f2)), for the current `sys.stderr` ([Z4](#z4)) (test: [`w1_colour`](../src/kloggy/tests/test_warnings.py#L38 "test_w1_colour")).

It's separate from `setup()` ([A1](#a1)): how warnings are shown is one global for the whole process, so the app opts in explicitly.
It does nothing if something already customised it (`warnings.showwarning`), e.g. the app, IPython or pytest (test: [`w1_customised`](../src/kloggy/tests/test_warnings.py#L68 "test_w1_customised")),
and the app can still replace it afterwards.
Only how warnings are shown changes: which ones are shown (filters, `-W`) doesn't,
and `logging.captureWarnings()` and `catch_warnings(record=True)` work as usual, without colour codes in what they get (test: [`w1_capture`](../src/kloggy/tests/test_warnings.py#L97 "test_w1_capture")).
With `KLOGGY_DISABLE` ([L5](#l5)), it does nothing (test: [`w1_disabled`](../src/kloggy/tests/test_warnings.py#L126 "test_w1_disabled")).

**Considered alternatives:**

- overriding `warnings.formatwarning` rather than `showwarning`: `logging.captureWarnings()` and pytest's warnings summary format warnings with it,
  so colour codes would end up there.
- colour codes in the message itself, like HPI's `my.core.warnings`: they break filters matching on the message, and end up in captured output
- part of `setup()`, or on import: it would restyle every library's warnings, whether the app wants that or not

<a id="w2"></a>

### W2: `warn_once()` warns once per message

`kloggy.warnings.warn_once()` takes the same arguments as `warnings.warn()`, and shows each distinct warning once per process,
at the same location `warnings.warn()` would (test: [`w2_once`](../src/kloggy/tests/test_warnings.py#L148 "test_w2_once")).
It's meant for code that runs repeatedly, e.g. a check in a function called for every file.
Elsewhere, plain `warnings.warn()` is enough, e.g. a module-level warning in a deprecated module is shown once anyway, since the module is imported once.

stdlib also shows a warning once per message and location by default,
but it forgets what it has shown whenever warning filters change anywhere, e.g. a library calling `warnings.catch_warnings()`,
so the same warning shows again (test: [`w2_filters_changed`](../src/kloggy/tests/test_warnings.py#L174 "test_w2_filters_changed")).
That's deliberate: stdlib leaves deduplication to the app's filters (e.g. `-W always`), and clears its records so that changed filters take effect
([bpo-4180](https://bugs.python.org/issue4180)).

**Caveats:**

- once per distinct arguments, not per location, like stdlib's `once` action: the same message from another place isn't shown again
- it overrides the app's choice: even `-W always` doesn't show repeats
- a call whose warning was filtered out (e.g. by an `ignore` filter, or inside `pytest.warns()`) counts too
- tests can start afresh with `warn_once.cache_clear()`

**Considered alternatives:**

- once per message and location, like stdlib's default: needs computing the warning's location the way `warnings.warn()` does
  (`stacklevel`, `skip_file_prefixes`), rather than leaving it to stdlib
- deduplicating in kloggy's display ([W1](#w1)): would only work with it set up, and would also hide repeats of every other library's warnings

## C: concurrency

<a id="c1"></a>

### C1: Logging from several threads at once

When several threads log at once, also with free-threaded Python, each record is printed whole, on its own line,
e.g. through a rich progress bar ([Z4](#z4)) (test: [`c1_threads`](../src/kloggy/tests/test_concurrency.py#L15 "test_c1_threads")).
Concurrent logging configuration doesn't deadlock (test: [`c1_no_deadlock_with_dict_config`](../src/kloggy/tests/test_concurrency.py#L66 "test_c1_no_deadlock_with_dict_config")).

<a id="c2"></a>

### C2: Logging from several processes

When worker processes send their records to the main process,
e.g. with stdlib's [`QueueHandler` recipe](https://docs.python.org/3/howto/logging-cookbook.html#logging-to-a-single-file-from-multiple-processes),
the main process prints them, and kloggy doesn't print them in the workers, where the `QueueHandler` counts as [configured](#configured)
(test: [`c2_processes`](../src/kloggy/tests/test_concurrency.py#L113 "test_c2_processes")).

Workers should do that: other processes can't print through the main process's terminal handling, e.g. its rich progress bar,
so their output would go straight to the terminal.

<a id="p"></a>

## P: progress (experimental)

**Experimental:** `kloggy.progress` may still change a lot, or move to a separate package, so it's not in the README.

<a id="p1"></a>

### P1: Logging progress through a loop

When library code wraps a loop in `progress(items, logger=...)`, each item is logged before it's processed,
e.g. `processing [ 3/10] /path/to/file` (test: [`p1_log_lines`](../src/kloggy/progress/tests/test_progress.py#L42 "test_p1_log_lines")).
Items are numbered from 1, padded to the width of the total, so the lines line up.
Without a total, e.g. for a generator, they're just numbered, unless `total=` is passed (test: [`p1_no_length`](../src/kloggy/progress/tests/test_progress.py#L65 "test_p1_no_length")).
Stopping early, e.g. via `break`, is fine.

The records point at the loop in the caller rather than into kloggy, e.g. in the source location of kloggy's output ([F1](#f1))
(test: [`p1_location`](../src/kloggy/progress/tests/test_progress.py#L123 "test_p1_location")).

What's logged for an item can be changed, e.g. to just the path for `(path, result)` pairs (test: [`p1_describe`](../src/kloggy/progress/tests/test_progress.py#L87 "test_p1_describe")).
The `processing [i/n] ...` lines can be turned off, so there's only the bar, if a display shows one ([P2](#p2)),
e.g. for thousands of events parsed from export files, where a log line for each would flood the output (test: [`p1_log_items`](../src/kloggy/progress/tests/test_progress.py#L106 "test_p1_log_items")).

**Motivation:** a `processing [i/n] path` line before each file is copy-pasted in about a dozen HPI modules and exporter DALs,
e.g. to see which file is slow, or where processing stopped.

**Recommendation:** when the results come from somewhere else, e.g. an executor parsing files ahead,
wrap the sources and zip them with the results, e.g. `zip(progress(paths, logger=logger), results, strict=True)`.
Then each file is logged just before its results are needed, i.e. right before parsing it without an executor.
Logging from the function an executor runs isn't a good fit: it doesn't know the item's number, nor whether a bar is shown,
and in a process pool, its output doesn't go through the main process's terminal handling ([C2](#c2)).

<a id="p2"></a>

### P2: Progress bars on a terminal

While a display shows a bar for a loop ([P3](#p3)), e.g. [rich](https://github.com/Textualize/rich) or [enlighten](https://github.com/Rockhopper-Technologies/enlighten) on a terminal,
its items are logged at DEBUG rather than INFO, since the bar already shows progress (tests: [`p2_rich`](../src/kloggy/progress/tests/test_progress.py#L141 "test_p2_rich"), [`p2_enlighten`](../src/kloggy/progress/tests/test_progress.py#L247 "test_p2_enlighten")).
If stderr isn't a terminal, e.g. redirected to a file, there's no bar, and items are logged at INFO (test: [`p2_not_terminal`](../src/kloggy/progress/tests/test_progress.py#L348 "test_p2_not_terminal")).

The bars:

- are at the bottom of the terminal, on stderr like kloggy's output, and other output goes above them.
  rich prints what's written to the current `sys.stderr` above them ([Z4](#z4)), and enlighten limits scrolling to the rest of the terminal.
  stdout is left alone unless it's a terminal too, e.g. if it's piped into another program (test: [`p2_rich`](../src/kloggy/progress/tests/test_progress.py#L141 "test_p2_rich"))
- take the full width of the terminal, and the parts of all the bars line up, e.g. the `/` in `4708/?` and `94/1725`
  (tests: [`p2_rich`](../src/kloggy/progress/tests/test_progress.py#L141 "test_p2_rich"), [`p2_enlighten`](../src/kloggy/progress/tests/test_progress.py#L247 "test_p2_enlighten"), [`p3_shared`](../src/kloggy/progress/tests/test_progress.py#L368 "test_p3_shared"))
- show the stats like enlighten does: `[elapsed<remaining, rate unit/s]`
- disappear once their loop is done (test: [`p2_rich`](../src/kloggy/progress/tests/test_progress.py#L141 "test_p2_rich"))

If a loop doesn't finish, e.g. on an error, or if it stops early, its bar stays on the screen as it was, so it's visible where it stopped.
On Ctrl-C, all the bars stay, and output after that goes below them (tests: [`p2_rich_unfinished`](../src/kloggy/progress/tests/test_progress.py#L193 "test_p2_rich_unfinished"), [`p2_enlighten`](../src/kloggy/progress/tests/test_progress.py#L247 "test_p2_enlighten")).

**Caveats:**

- a loop stopping early, e.g. with `hpi query --limit`, leaves its bar on the screen too:
  from inside `progress()`, that looks the same as Ctrl-C landing outside it, e.g. in the loop's body
- rich's bars leave the last two columns free: on Ctrl-C the terminal shows `^C` at the cursor, i.e. after the bars,
  and if that wrapped onto a new line, rich would leave a stale copy of a bar on the screen
- enlighten keeps the space for its bars until the process exits, since starting it again queries the terminal, which may take a while
- enlighten shows times past an hour as e.g. `1h 01:56`, so those bars don't line up with the others
- an app's own handler writing to the `sys.stderr` it saw when it was created, e.g. `basicConfig()`'s, bypasses rich,
  so its lines get glued onto the bars ([Z4](#z4)).
  Use `kloggy.setup()` instead ([A1](#a1)).

<a id="p3"></a>

### P3: One display for the whole process

There's one display for the whole process, picked by the app via `kloggy.progress.set_display()`, or by the user via `KLOGGY_PROGRESS`, e.g. `KLOGGY_PROGRESS=rich`.
So the bars of nested or concurrent loops show together, also from different packages (test: [`p3_shared`](../src/kloggy/progress/tests/test_progress.py#L368 "test_p3_shared")).
Without either, there's no display, i.e. log lines only.

Values are `rich`, `enlighten` and `off`, or `auto` for whichever is installed ([P4](#p4)), case-insensitive.
`KLOGGY_PROGRESS` is read on the first `progress()` call.
The app's `set_display()` takes precedence.
An unknown value, or a display whose library isn't installed, is ignored with a warning naming `KLOGGY_PROGRESS` (test: [`p3_invalid`](../src/kloggy/progress/tests/test_progress.py#L450 "test_p3_invalid")).
The libraries are optional dependencies: `kloggy[rich]` and `kloggy[enlighten]`.

**Motivation:** replaces HPI's `get_enlighten()`: an enlighten manager shared by storing it on the `enlighten` module,
a `Mock` stub if enlighten isn't installed, and `ENLIGHTEN_ENABLE` to turn it on.
Separate enlighten managers in different packages don't work together.

**Considered alternatives:**

- a bar drawn by kloggy itself, without dependencies: the same problem as HPI's retired `CollapseLogsHandler`,
  which redrew log lines in place, and broke with any other output in between
- [tqdm](https://github.com/tqdm/tqdm): it doesn't replace `sys.stderr`, so log lines would have to go through `tqdm.write()`,
  i.e. kloggy's handler would have to know about it

**Caveats:**

- `progress()` in a process-pool worker would get its own display there, fighting the main process's bars over the terminal
- the user can't turn off bars the app picked via `set_display()`

<a id="p4"></a>

### P4: Picking a display automatically

With `KLOGGY_PROGRESS=auto`, the display is rich if it's installed, otherwise enlighten, otherwise there's none, without a warning
(test: [`p4_auto`](../src/kloggy/progress/tests/test_progress.py#L422 "test_p4_auto")).
It's opt-in while progress is experimental.

**rich first**, since it wins on most counts:

|                        | rich                                                          | enlighten                                                                     | Winner        |
|------------------------|---------------------------------------------------------------|-------------------------------------------------------------------------------|---------------|
| already installed      | more often, many command-line tools depend on it              | less often                                                                    | **rich**      |
| starting               | nothing to wait for                                           | queries the terminal: up to 5s if it doesn't answer                           | **rich**      |
| terminal between loops | back to normal                                                | keeps the space for its bars until exit, rather than query the terminal again | **rich**      |
| output from elsewhere  | only output via `sys.stdout`/`sys.stderr` goes above the bars | anything written to the terminal goes above the bars                          | **enlighten** |

The exception is output from elsewhere, e.g. process-pool workers logging straight to the terminal,
or an app's own handler holding on to the original `sys.stderr` ([Z4](#z4)), which would get glued onto rich's bars.
Then pick enlighten explicitly, i.e. `KLOGGY_PROGRESS=enlighten`.

**Considered alternatives:**

- `auto` by default, i.e. bars whenever rich or enlighten is installed and stderr is a terminal: maybe later, once it's not experimental.
  Anyone with rich installed would get bars, and output from elsewhere would get glued onto them.
