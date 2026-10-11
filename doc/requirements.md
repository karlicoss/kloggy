# kloggy requirements


- [Principles](#principles)
- [Definitions](#definitions)
  - [Configured](#configured)
- [L: library-side API](#l-library-side-api)
  - [L1: Existing configuration is left untouched](#l1)
  - [L2: INFO by default](#l2)
  - [L3: The app's levels apply once it configures logging](#l3)
  - [L4: Named `get_logger`](#l4)
  - [L5: `KLOGGY_DISABLE` opts out of kloggy completely](#l5)
  - [L6: Per-module default levels](#l6)
- [Z: zero-config output](#z-zero-config-output)
  - [Z1: No bare messages](#z1)
  - [Z2: kloggy steps aside for good once logging is configured](#z2)
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
- [C: concurrency](#c-concurrency)
  - [C1: Logging from several threads at once](#c1)
  - [C2: Logging from several processes](#c2)

kloggy is developed requirements-first: requirements are agreed on before they are implemented, and link to the tests validating them.
Implementation: [`src/kloggy/__init__.py`](../src/kloggy/__init__.py), tests: [`src/kloggy/tests/`](../src/kloggy/tests/).

Requirement IDs are stable: don't renumber, retire instead.

## Principles

- **The app always wins:** kloggy's output is only a fallback while logging isn't configured.
  Once the app configures logging, its handlers and levels apply ([L1](#l1), [L3](#l3), [Z2](#z2)), and so does its own `setLevel()` ([V1](#v1)).
- **Stdlib-shaped:** library code only deals with plain `logging.Logger` objects ([L2](#l2)),
  so kloggy can be switched off without changing any code ([L5](#l5)).

## Definitions

### Configured

Logging is configured for a logger if its records would reach some handler other than the one kloggy's `get_logger()` adds:
walking up from the logger to root, stopping at the first logger with `propagate = False`.
Except root's default `basicConfig()` handler doesn't count, see [Z3](#z3).
The one `setup()` adds does count, see [A1](#a1).

This is the notion stdlib itself uses: `Logger.callHandlers` falls back to `logging.lastResort` only when that walk finds no handlers,
and `Logger.hasHandlers()` does the same walk.
Note that `basicConfig()` uses a narrower check (`root.handlers` is non-empty).

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

- logging configured *after* kloggy set up: see [L3](#l3), [Z2](#z2)

<a id="l2"></a>

### L2: INFO by default

Loggers returned by `get_logger()` show INFO while logging isn't configured, rather than stdlib's default WARNING (test: [`l2_info_by_default`](../src/kloggy/tests/test_library.py#L73 "test_l2_info_by_default")).
This is a deliberate, opinionated choice: INFO gives a sense of progress (e.g. `processing [3/100] ...`) without any setup.

kloggy never sets any levels on its own: the INFO default isn't stored on any logger, so there's nothing the app could mistake for its own.
It only sets levels the user explicitly asks for via `KLOGGY_LEVEL` ([V1](#v1)).

Levels set explicitly (e.g. by the app, on the logger itself or an ancestor below root) still apply
(tests: [`l2_explicit_level`](../src/kloggy/tests/test_library.py#L281 "test_l2_explicit_level"), [`l2_level_changed_since`](../src/kloggy/tests/test_library.py#L262 "test_l2_level_changed_since")).

In a package where some modules use `get_logger()`, modules still using plain `logging.getLogger()` keep stdlib's levels
(tests: [`l3_configured_after_plain_logger`](../src/kloggy/tests/test_library.py#L114 "test_l3_configured_after_plain_logger"), [`l3_configured_after_on_module_logger_plain_logger`](../src/kloggy/tests/test_library.py#L164 "test_l3_configured_after_on_module_logger_plain_logger")).
Their records are still printed by kloggy while logging isn't configured, so a package can migrate one module at a time
(test: [`l2_plain_logger`](../src/kloggy/tests/test_library.py#L328 "test_l2_plain_logger")).
That only changes how their records look, never which ones are shown.

**Mechanism:** `get_logger()` returns the same object as `logging.getLogger()`, switched to a kloggy subclass of `logging.Logger`.
If the app installed its own logger class (`logging.setLoggerClass()`), kloggy uses a subclass of both, so it keeps its behaviour
(test: [`l2_app_logger_class`](../src/kloggy/tests/test_library.py#L304 "test_l2_app_logger_class")).
kloggy doesn't call `logging.setLoggerClass()` itself:
that would affect every logger created afterwards, including other libraries', and the app may need it for its own class.

<a id="l3"></a>

### L3: The app's levels apply once it configures logging

Once the app configures logging, its levels apply straight away, e.g. after `basicConfig(level=ERROR)` in `main()` after imports
(tests: [`l3_configured_after`](../src/kloggy/tests/test_library.py#L91 "test_l3_configured_after"), [`l3_configured_after_on_module_logger`](../src/kloggy/tests/test_library.py#L138 "test_l3_configured_after_on_module_logger"), [`l3_effective_level`](../src/kloggy/tests/test_library.py#L399 "test_l3_effective_level")).
Both ways: no stray INFO if the app wants less, and e.g. DEBUG right after `basicConfig(level=DEBUG)` if it wants more
(test: [`l3_configured_after_more_verbose`](../src/kloggy/tests/test_library.py#L187 "test_l3_configured_after_more_verbose")).

This is per logger, same as kloggy stepping aside in [Z2](#z2) (test: [`l3_configured_after_on_subpackage`](../src/kloggy/tests/test_library.py#L209 "test_l3_configured_after_on_subpackage")).

Records created at kloggy's INFO just before the app configured logging, but reaching the handlers after (e.g. in another thread), are dropped,
so the app never gets records below its levels (tests: [`l3_created_before_configured`](../src/kloggy/tests/test_library.py#L350 "test_l3_created_before_configured"), [`l3_concurrent`](../src/kloggy/tests/test_library.py#L234 "test_l3_concurrent")).

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

- it isn't a pure stdlib passthrough ([L2](#l2), and it may set up the package handler),
  so the call site should make it obvious it's kloggy's, unlike `from kloggy import getLogger` vs `from logging import getLogger`
- snake_case is PEP 8 and what newer libraries use (e.g. `structlog.get_logger`); stdlib's camelCase is legacy

<a id="l5"></a>

### L5: `KLOGGY_DISABLE` opts out of kloggy completely

With `KLOGGY_DISABLE=1`, `get_logger()` returns plain `logging.getLogger()` loggers without touching anything:
no handler, no class switch, and `KLOGGY_LEVEL` is ignored (test: [`l5_disabled`](../src/kloggy/tests/test_disable.py#L10 "test_l5_disabled")).
So logging behaves exactly as plain stdlib, e.g. if kloggy causes problems, without changing any code.

Values are the usual boolean words, as in systemd: `1`, `true`, `yes`, `on` disable kloggy, `0`, `false`, `no`, `off` don't, case-insensitive.
Empty means not set (test: [`l5_values`](../src/kloggy/tests/test_disable.py#L50 "test_l5_values")).
Anything else is ignored with a warning naming `KLOGGY_DISABLE` (test: [`l5_invalid`](../src/kloggy/tests/test_disable.py#L69 "test_l5_invalid")).
It's read once, on the first `get_logger()` or `setup()` call.

**Rejected alternatives:**

- an empty `KLOGGY_LEVEL`: variables often end up empty by accident (e.g. wrapper scripts passing through an unset variable),
  and empty usually means unset
- `KLOGGY_LEVEL=off`: `off` means silence, while opting out still prints warnings via stdlib's `logging.lastResort`
- any non-empty value disables, like many `PYTHON*` variables: then `KLOGGY_DISABLE=0` would disable kloggy too

<a id="l6"></a>

### L6: Per-module default levels

A module can pick its own default instead of INFO, e.g. `get_logger(__name__, default_level='warning')` for a module whose INFO is too chatty in a typical run
(test: [`l6_default_level`](../src/kloggy/tests/test_library.py#L421 "test_l6_default_level")).
Child loggers inherit it, and the nearest default wins (test: [`l6_nearest_default`](../src/kloggy/tests/test_library.py#L441 "test_l6_nearest_default")).
It also applies to records other code logs through the module's logger, e.g. cachew logs through the decorated function's module logger
(test: [`l6_other_code`](../src/kloggy/tests/test_library.py#L459 "test_l6_other_code")).

Like INFO ([L2](#l2)), it's only a default for kloggy's output, never set on the logger itself, so:

- levels set explicitly, on the logger or an ancestor below root, win, also if the app set them before the module was imported
  (test: [`l6_explicit_level`](../src/kloggy/tests/test_library.py#L477 "test_l6_explicit_level"))
- that includes `KLOGGY_LEVEL` ([V1](#v1)), e.g. `KLOGGY_LEVEL=debug` shows DEBUG from such modules too (test: [`l6_kloggy_level`](../src/kloggy/tests/test_library.py#L503 "test_l6_kloggy_level"))
- once the app configures logging, the app's levels apply, same as for INFO ([L3](#l3)) (test: [`l6_app_configured`](../src/kloggy/tests/test_library.py#L520 "test_l6_app_configured"))

If several calls pass different defaults for the same logger, the last one wins (test: [`l6_last_wins`](../src/kloggy/tests/test_library.py#L538 "test_l6_last_wins")).
Level names are the same as in `KLOGGY_LEVEL`, case-insensitive, and `logging` constants work too.
An unknown name is an error, since it's a bug in the code (test: [`l6_invalid`](../src/kloggy/tests/test_library.py#L555 "test_l6_invalid")).

It's named `default_level`, since stdlib's `level` means a level set on the logger.

**Considered alternatives:**

- `setLevel()` in the module: the app's `basicConfig(level=DEBUG)` doesn't reach the module, since it only sets root's level.
  It also overwrites levels set before the module was imported (e.g. with lazy imports, or pytest's `caplog`), including `KLOGGY_LEVEL`'s.
- no per-module defaults, demoting chatty messages to DEBUG instead:
  doesn't help with records other code logs through the module's logger, e.g. cachew's

## Z: zero-config output

<a id="z1"></a>

### Z1: No bare messages

If logging isn't [configured](#configured), records from kloggy loggers are never printed as a bare message:
the output includes at least the level and the logger name (test: [`z1_not_bare`](../src/kloggy/tests/test_zero_config.py#L29 "test_z1_not_bare")).
This holds until kloggy steps aside for a logger ([Z2](#z2)).

Stdlib's fallback in that case (`logging.lastResort`) has no formatter, i.e. `%(message)s`:
`logger.error('some error')` prints just `some error`, which looks the same as a warning and can't be traced to where it came from
(test: [`z1_stdlib_baseline`](../src/kloggy/tests/test_zero_config.py#L15 "test_z1_stdlib_baseline")).
Even `basicConfig()`'s default `logging.BASIC_FORMAT` (`%(levelname)s:%(name)s:%(message)s`, i.e. `ERROR:__main__:some error`) satisfies this.

**Related:**

- the specific format: see [F1](#f1)
- which levels are shown when nothing is configured: see [L2](#l2)

<a id="z2"></a>

### Z2: kloggy steps aside for good once logging is configured

Once logging is [configured](#configured) for a logger, kloggy steps aside for that logger for good:
its handler leaves the logger's records to the app's handlers, and its levels are stdlib's ([L3](#l3)).
So configuring logging *after* kloggy set up switches kloggy output off, and each record is printed exactly once, by the app's handlers.
E.g. `basicConfig()` in the app's `main()`, a handler on the package logger or the record's own logger, a `NullHandler` (explicitly asking for silence), pytest's log capture
(test: [`z2_configured_after`](../src/kloggy/tests/test_zero_config.py#L47 "test_z2_configured_after")).

This is per logger: if the app only configures `pkg.sub` (e.g. a handler on it), kloggy keeps handling `pkg.other` (test: [`z2_stays_off_per_logger`](../src/kloggy/tests/test_zero_config.py#L143 "test_z2_stays_off_per_logger")).

Removing the app's handlers later doesn't switch kloggy back on: output is then what it would be without kloggy, i.e. stdlib's `logging.lastResort`
(test: [`z2_stays_off_when_unconfigured`](../src/kloggy/tests/test_zero_config.py#L98 "test_z2_stays_off_when_unconfigured")).
So output doesn't depend on whether logging was configured before or after `get_logger()` (test: [`z2_stays_off_when_configured_at_setup`](../src/kloggy/tests/test_zero_config.py#L121 "test_z2_stays_off_when_configured_at_setup")).

kloggy notices configuration when it looks: in `get_logger()`, in a level check, or when a record reaches its handler.
Also if another thread removes the app's handler right in the middle of a level check (test: [`z2_configuration_changes_during_level_check`](../src/kloggy/tests/test_zero_config.py#L191 "test_z2_configuration_changes_during_level_check")).
If the app adds and then removes handlers without logging anything in between, kloggy carries on.

**Rejected alternatives:**

- resuming kloggy output once the app's handlers are removed, i.e. deciding per record like stdlib's `lastResort`:
  output then depended on whether logging was configured before or after `get_logger()`.
  The motivation was pytest `caplog`, but pytest keeps its own handlers on root for the whole session,
  so removing caplog's handler doesn't leave logging unconfigured anyway.

<a id="z3"></a>

### Z3: Default `basicConfig()` handler doesn't count as configured

Root having only the handler a default `basicConfig()` creates doesn't count as [configured](#configured)
(tests: [`z3_stray_call_before`](../src/kloggy/tests/test_zero_config.py#L244 "test_z3_stray_call_before"), [`z3_stray_call_after`](../src/kloggy/tests/test_zero_config.py#L263 "test_z3_stray_call_after")).

**Motivation:** bare root-level calls like `logging.warning(...)` call `basicConfig()` implicitly if root has no handlers.
Without this, one such stray call anywhere (e.g. in a dependency) would switch kloggy off for the rest of the process,
with no fix short of an explicit setup call.
Code should use a module logger instead (ruff's [`LOG015`](https://docs.astral.sh/ruff/rules/root-logger-call/) flags such calls), but a dependency may still make them.

**Detection:** root's only handler is exactly what a bare `basicConfig()` creates, and root's level is still `WARNING`.
Any customisation counts as configured: format, level other than `WARNING`, file, handlers, or changing that handler afterwards
(test: [`z3_configured_after_stray_call`](../src/kloggy/tests/test_zero_config.py#L288 "test_z3_configured_after_stray_call")).

**Accepted misfires**, since the state is indistinguishable: an explicit `basicConfig()`, `basicConfig(level=WARNING)` or `basicConfig(stream=sys.stderr)`.
Then kloggy's records keep kloggy's output, while the rest of the app's output is in `BASIC_FORMAT` (test: [`z3_explicit_bare_basic_config`](../src/kloggy/tests/test_zero_config.py#L320 "test_z3_explicit_bare_basic_config")).

Levels follow the same rule, no special case: with only the default handler, kloggy keeps its INFO default (test: [`z3_stray_call_keeps_info`](../src/kloggy/tests/test_zero_config.py#L337 "test_z3_stray_call_keeps_info")).
So the accepted misfires also get INFO from kloggy packages.

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

Some tools replace `sys.stderr` for a while: e.g. `contextlib.redirect_stderr` or pytest's `capsys` to capture output,
or a [rich](https://github.com/Textualize/rich) progress bar, which prints everything written to it above the bar.
kloggy's output goes to the replacement too, also when kloggy set up before it (test: [`z4_replaced_stderr`](../src/kloggy/tests/test_zero_config.py#L356 "test_z4_replaced_stderr")).
So a rich progress bar doesn't mangle it (test: [`z4_rich`](../src/kloggy/tests/test_zero_config.py#L435 "test_z4_rich")).
Colour ([F2](#f2)) is decided for the replacement as well, e.g. no colour codes in captured output (test: [`z4_colour_follows`](../src/kloggy/tests/test_zero_config.py#L379 "test_z4_colour_follows")).
Once `sys.stderr` is switched back, kloggy doesn't hold on to the replacement, so e.g. a buffer with lots of captured output can be freed (test: [`z4_not_kept_alive`](../src/kloggy/tests/test_zero_config.py#L410 "test_z4_not_kept_alive")).

That's the same as stdlib's own fallback, `logging.lastResort`: it writes to whatever `sys.stderr` is when each record is printed.

This is **unlike** `basicConfig()`'s `StreamHandler`, which keeps the `sys.stderr` it saw when it was created.
So its output bypasses later replacements, e.g. each line gets glued onto a frozen copy of a rich progress bar.

Python considers this `StreamHandler` behaviour deliberate, it was closed as not a bug in [bpo-36193](https://bugs.python.org/issue36193):
a `StreamHandler` writes to exactly the stream it was given, which suits an app's own configuration, set up once at startup.

kloggy's handler is more like `lastResort`: it's created when a library is imported, and only prints while nothing is configured.

One consequence, the same as with `lastResort`: code that redirects `sys.stderr` to silence something silences kloggy's output too
(test: [`z4_replaced_stderr`](../src/kloggy/tests/test_zero_config.py#L356 "test_z4_replaced_stderr")).

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
  (`RUST_LOG` applies it to everything, and switches off everything without a matching entry)
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

An app can call `kloggy.setup()` in its `main()` instead of `basicConfig()`,
so every logger's output looks the same, also from libraries not using kloggy (test: [`a1_setup`](../src/kloggy/tests/test_app.py#L12 "test_a1_setup")).

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
  kloggy packages keep INFO and per-module defaults while other libraries stay at WARNING,
  but then records need deduplicating between the package's handler and root's.
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

In kloggy's own output, an exception logged as the message at ERROR and above shows its traceback, even outside an `except` block,
e.g. errors collected as values and logged later (test: [`x1_error`](../src/kloggy/tests/test_exceptions.py#L25 "test_x1_error")).
That includes `logger.exception(e)` outside an `except` block, which stdlib would print with `NoneType: None` instead
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

## C: concurrency

<a id="c1"></a>

### C1: Logging from several threads at once

Several threads can log at once, also with free-threaded Python: each record is printed whole, on its own line,
e.g. through a rich progress bar ([Z4](#z4)) (test: [`c1_threads`](../src/kloggy/tests/test_concurrency.py#L15 "test_c1_threads")).
Concurrent logging configuration doesn't deadlock (test: [`c1_no_deadlock_with_dict_config`](../src/kloggy/tests/test_concurrency.py#L66 "test_c1_no_deadlock_with_dict_config")).

<a id="c2"></a>

### C2: Logging from several processes

Other processes can't print through the main process's terminal handling, e.g. its rich progress bar: their output goes straight to the terminal.
So workers should send their records to the main process,
e.g. with stdlib's [`QueueHandler` recipe](https://docs.python.org/3/howto/logging-cookbook.html#logging-to-a-single-file-from-multiple-processes).
kloggy works with that: in a worker, the `QueueHandler` counts as configured, so kloggy doesn't print there,
and the main process prints the workers' records (test: [`c2_processes`](../src/kloggy/tests/test_concurrency.py#L113 "test_c2_processes")).
