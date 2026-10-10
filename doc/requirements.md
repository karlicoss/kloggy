# klogging requirements


klogging is developed requirements-first: requirements are agreed on before they are implemented, and link to the tests validating them.
Implementation: [`src/klogging/__init__.py`](../src/klogging/__init__.py), tests: [`src/klogging/tests/`](../src/klogging/tests/).

Requirement IDs are stable: don't renumber, retire instead.

## Definitions

### Configured

Logging is configured for a logger if its records would reach some handler other than klogging's own:
walking up from the logger to root, stopping at the first logger with `propagate = False`.
Except root's default `basicConfig()` handler doesn't count, see [Z3](#z3).

This is the notion stdlib itself uses: `Logger.callHandlers` falls back to `logging.lastResort` only when that walk finds no handlers,
and `Logger.hasHandlers()` does the same walk.
Note that `basicConfig()` uses a narrower check (`root.handlers` is non-empty).

## L: library-side API

### <a id="l1"></a>L1: Existing configuration is left untouched

If logging is already [configured](#configured) for a logger when `get_logger()` is called for it, klogging doesn't touch logging state:
no handlers added, no levels set, and the logger's class isn't switched ([L2](#l2)).
Output is then exactly what it would be without klogging, for good (test: [`l1_configured_before_untouched`](../src/klogging/tests/test_library.py#L13 "test_l1_configured_before_untouched")).

E.g. after `basicConfig(level=ERROR)`, the app only gets errors from `pkg.*`, in its own format.

**Edge case:** a bare `basicConfig()`, e.g. called implicitly by a stray `logging.warning(...)`, doesn't count as configured, see [Z3](#z3).

**Related:**

- levels the user asks for, e.g. via an environment variable, are a separate question, not decided yet
- logging configured *after* klogging set up: see [L3](#l3), [Z2](#z2)

### <a id="l2"></a>L2: INFO by default

Loggers returned by `get_logger()` show INFO while logging isn't configured, rather than stdlib's default WARNING (test: [`l2_info_by_default`](../src/klogging/tests/test_library.py#L73 "test_l2_info_by_default")).
This is a deliberate, opinionated choice: INFO gives a sense of progress (e.g. `processing [3/100] ...`) without any setup.

klogging never sets any levels itself: the INFO default isn't stored on any logger, so there's nothing the app could mistake for its own.

Levels set explicitly (e.g. by the app, on the logger itself or an ancestor below root) still apply
(tests: [`l2_explicit_level`](../src/klogging/tests/test_library.py#L281 "test_l2_explicit_level"), [`l2_level_changed_since`](../src/klogging/tests/test_library.py#L262 "test_l2_level_changed_since")).

Plain `logging.getLogger()` loggers in the package keep stdlib's levels
(tests: [`l2_plain_logger`](../src/klogging/tests/test_library.py#L328 "test_l2_plain_logger"), [`l3_configured_after_plain_logger`](../src/klogging/tests/test_library.py#L114 "test_l3_configured_after_plain_logger"), [`l3_configured_after_on_module_logger_plain_logger`](../src/klogging/tests/test_library.py#L164 "test_l3_configured_after_on_module_logger_plain_logger")).

**Mechanism:** `get_logger()` returns the same object as `logging.getLogger()`, switched to a klogging subclass of `logging.Logger`.
If the app installed its own logger class (`logging.setLoggerClass()`), klogging uses a subclass of both, so it keeps its behaviour
(test: [`l2_app_logger_class`](../src/klogging/tests/test_library.py#L304 "test_l2_app_logger_class")).
klogging doesn't call `logging.setLoggerClass()` itself:
that would affect every logger created afterwards, including other libraries', and the app may need it for its own class.

### <a id="l3"></a>L3: The app's levels apply once it configures logging

Once the app configures logging, its levels apply straight away, e.g. after `basicConfig(level=ERROR)` in `main()` after imports
(tests: [`l3_configured_after`](../src/klogging/tests/test_library.py#L91 "test_l3_configured_after"), [`l3_configured_after_on_module_logger`](../src/klogging/tests/test_library.py#L138 "test_l3_configured_after_on_module_logger"), [`l3_effective_level`](../src/klogging/tests/test_library.py#L399 "test_l3_effective_level")).
Both ways: no stray INFO if the app wants less, and e.g. DEBUG right after `basicConfig(level=DEBUG)` if it wants more
(test: [`l3_configured_after_more_verbose`](../src/klogging/tests/test_library.py#L187 "test_l3_configured_after_more_verbose")).

This is per logger, same as klogging stepping aside in [Z2](#z2) (test: [`l3_configured_after_on_subpackage`](../src/klogging/tests/test_library.py#L209 "test_l3_configured_after_on_subpackage")).

Records created at klogging's INFO just before the app configured logging, but reaching the handlers after (e.g. in another thread), are dropped,
so the app never gets records below its levels (tests: [`l3_created_before_configured`](../src/klogging/tests/test_library.py#L350 "test_l3_created_before_configured"), [`l3_concurrent`](../src/klogging/tests/test_library.py#L234 "test_l3_concurrent")).

**Caveats:**

- a disabled call, e.g. `logger.debug(...)`, costs ~0.6-0.9 µs instead of stdlib's ~0.1 µs:
  whether it's enabled depends on whether logging is configured, so stdlib's cached level checks can't be used.
  Once klogging steps aside for the logger ([Z2](#z2)), it costs ~0.25 µs.
- a record passed to `Logger.handle()` by hand, below its logger's level, is dropped once logging is configured:
  klogging can't tell it from one created just before the app configured logging (see above)

**Rejected alternatives:**

- setting INFO on the package logger, and resetting it once klogging notices the app's configuration:
  it only notices via records, so stray INFO and lost DEBUG around the switch,
  and configuring one subpackage takes INFO away from the whole package
- a special level comparing as INFO until logging is configured, and as the app's level after:
  leaks via `getEffectiveLevel()`, where it compares inconsistently (equal to INFO, yet not above DEBUG)

### <a id="l4"></a>L4: Named `get_logger`

The function is named `get_logger`, not `getLogger`:

- it isn't a pure stdlib passthrough ([L2](#l2), and it may set up the package handler),
  so the call site should make it obvious it's klogging's, unlike `from klogging import getLogger` vs `from logging import getLogger`
- snake_case is PEP 8 and what newer libraries use (e.g. `structlog.get_logger`); stdlib's camelCase is legacy

## Z: zero-config output

### <a id="z1"></a>Z1: No bare messages

If logging isn't [configured](#configured), records from klogging loggers are never printed as a bare message:
the output includes at least the level and the logger name (test: [`z1_not_bare`](../src/klogging/tests/test_zero_config.py#L27 "test_z1_not_bare")).
This holds until klogging steps aside for a logger ([Z2](#z2)).

Stdlib's fallback in that case (`logging.lastResort`) has no formatter, i.e. `%(message)s`:
`logger.error('some error')` prints just `some error`, which looks the same as a warning and can't be traced to where it came from
(test: [`z1_stdlib_baseline`](../src/klogging/tests/test_zero_config.py#L13 "test_z1_stdlib_baseline")).
Even `basicConfig()`'s default `logging.BASIC_FORMAT` (`%(levelname)s:%(name)s:%(message)s`, i.e. `ERROR:__main__:some error`) satisfies this.

**Related:**

- the specific format is a separate concern, not decided yet
- which levels are shown when nothing is configured: see [L2](#l2)

### <a id="z2"></a>Z2: klogging steps aside for good once logging is configured

Once logging is [configured](#configured) for a logger, klogging steps aside for that logger for good:
its handler leaves the logger's records to the app's handlers, and its levels are stdlib's ([L3](#l3)).
So configuring logging *after* klogging set up switches klogging output off, and each record is printed exactly once, by the app's handlers.
E.g. `basicConfig()` in the app's `main()`, a handler on the package logger or the record's own logger, a `NullHandler` (explicitly asking for silence), pytest's log capture
(test: [`z2_configured_after`](../src/klogging/tests/test_zero_config.py#L45 "test_z2_configured_after")).

This is per logger: if the app only configures `pkg.sub` (e.g. a handler on it), klogging keeps handling `pkg.other` (test: [`z2_stays_off_per_logger`](../src/klogging/tests/test_zero_config.py#L141 "test_z2_stays_off_per_logger")).

Removing the app's handlers later doesn't switch klogging back on: output is then what it would be without klogging, i.e. stdlib's `logging.lastResort`
(test: [`z2_stays_off_when_unconfigured`](../src/klogging/tests/test_zero_config.py#L96 "test_z2_stays_off_when_unconfigured")).
So output doesn't depend on whether logging was configured before or after `get_logger()` (test: [`z2_stays_off_when_configured_at_setup`](../src/klogging/tests/test_zero_config.py#L119 "test_z2_stays_off_when_configured_at_setup")).

klogging notices configuration when it looks: in `get_logger()`, in a level check, or when a record reaches its handler.
Also if another thread removes the app's handler right in the middle of a level check (test: [`z2_configuration_changes_during_level_check`](../src/klogging/tests/test_zero_config.py#L189 "test_z2_configuration_changes_during_level_check")).
If the app adds and then removes handlers without logging anything in between, klogging carries on.

**Rejected alternatives:**

- resuming klogging output once the app's handlers are removed, i.e. deciding per record like stdlib's `lastResort`:
  output then depended on whether logging was configured before or after `get_logger()`.
  The motivation was pytest `caplog`, but pytest keeps its own handlers on root for the whole session,
  so removing caplog's handler doesn't leave logging unconfigured anyway.

### <a id="z3"></a>Z3: Default `basicConfig()` handler doesn't count as configured

Root having only the handler a default `basicConfig()` creates doesn't count as [configured](#configured)
(tests: [`z3_stray_call_before`](../src/klogging/tests/test_zero_config.py#L242 "test_z3_stray_call_before"), [`z3_stray_call_after`](../src/klogging/tests/test_zero_config.py#L261 "test_z3_stray_call_after")).

**Motivation:** bare root-level calls like `logging.warning(...)` call `basicConfig()` implicitly if root has no handlers.
Without this, one such stray call anywhere (e.g. in a dependency) would switch klogging off for the rest of the process,
with no fix short of an explicit setup call.
Code should use a module logger instead (ruff's [`LOG015`](https://docs.astral.sh/ruff/rules/root-logger-call/) flags such calls), but a dependency may still make them.

**Detection:** root's only handler is exactly what a bare `basicConfig()` creates, and root's level is still `WARNING`.
Any customisation counts as configured: format, level other than `WARNING`, file, handlers, or changing that handler afterwards
(test: [`z3_configured_after_stray_call`](../src/klogging/tests/test_zero_config.py#L286 "test_z3_configured_after_stray_call")).

**Accepted misfires**, since the state is indistinguishable: an explicit `basicConfig()`, `basicConfig(level=WARNING)` or `basicConfig(stream=sys.stderr)`.
Then klogging's records keep klogging's output, while the rest of the app's output is in `BASIC_FORMAT` (test: [`z3_explicit_bare_basic_config`](../src/klogging/tests/test_zero_config.py#L318 "test_z3_explicit_bare_basic_config")).

Levels follow the same rule, no special case: with only the default handler, klogging keeps its INFO default (test: [`z3_stray_call_keeps_info`](../src/klogging/tests/test_zero_config.py#L335 "test_z3_stray_call_keeps_info")).
So the accepted misfires also get INFO from klogging packages.

To avoid both, use any non-default `basicConfig()` argument; for just the levels, e.g. `logging.getLogger('pkg').setLevel(...)`.

**Duplicates:** after printing a record klogging drops it, so that default handler skips it.
So klogging doesn't touch root's handler, and other loggers' records are unaffected.

**Rejected alternatives:**

- telling implicit `basicConfig()` calls from explicit ones by watching calls via `sys.monitoring`: precise, but too hacky
- `propagate = False` on the package logger while root only has the default handler:
  interferes with the "configured" walk, which stops at `propagate = False`, so klogging would have to track which flag it set itself
- a filter on that default handler dropping records klogging marked as printed: works, but touches root's handler
