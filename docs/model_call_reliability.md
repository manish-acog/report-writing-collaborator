# Design — Model Call Timeout and Retry

## Purpose

For whoever wires request timeout/retry into `_run_bounded_call_async`.
Fixes an observed production failure: a `write_report()` run hangs
indefinitely, no error, when the connection to the model provider is reset
mid-request (`ConnectionResetError: [WinError 10054]`, observed on a
Windows host). For whoever changes `report_orchestrator.py`.

## Why

`runner.run_async(...)` (`report_orchestrator.py`) is called with no
`run_config` — traced through ADK's own code: `RunConfig.http_options`
defaults to `None` (`run_config.py:69`), and `LiteLlm` only sets a timeout
or retry count on the underlying `litellm.completion()` call *if*
`http_opts.timeout`/`http_opts.retry_options` are set
(`lite_llm.py:2988-2997`). With neither ever set, a reset or stalled
connection has nothing bounding the wait and nothing retrying it — the run
just hangs, silently, with `.tasks/<task_id>/sessions.db` frozen at
whatever size it reached before the connection died. Confirmed via a real
run: `.tasks/` showed only `sessions.db`, size unchanging, no
`values.json` — consistent with a stall inside the bootstrap or first
`call_group` turn, not a crash.

## Shape

- **`_run_bounded_call_async`** (`report_orchestrator.py`) — passes
  `run_config=RunConfig(http_options=HttpOptions(timeout=..., retry_options=HttpRetryOptions(attempts=...)))`
  to every `runner.run_async(...)` call.
  - exposes: no signature change — internal to the function.
  - hands off: nothing new; failure still surfaces as `RuntimeError`
    through the existing `except Exception` path once retries are
    exhausted.

This uses a mechanism ADK already ships (`google.genai.types.HttpOptions`/
`HttpRetryOptions`, read directly by `LiteLlm`) — not new machinery.

## State

None new.

## Scenarios

**A connection reset mid-request.** `litellm.completion()` retries the
HTTP call itself, up to the configured attempt count, before raising.
`_run_bounded_call_async`'s existing `except Exception` catches an
eventual real failure and raises `RuntimeError` — the run fails loud
instead of hanging forever with no signal.

**A slow but healthy call.** The timeout must be generous enough that a
real 61-field extraction turn (full workspace context, multiple tool
calls) doesn't get killed mid-flight for legitimately taking a while — not
tuned here to an exact number; see Open questions.

## Decisions

### Use ADK's own `http_options`, not a hand-rolled wrapper

- **Options:** A — wrap `runner.run_async(...)` in `asyncio.wait_for(...)`
  and a custom retry loop. B (chosen) — pass `RunConfig(http_options=...)`,
  which `LiteLlm` already reads and forwards to `litellm.completion()`.
- **Chose:** B.
- **Consequences:** no new retry/timeout code to maintain; the mechanism
  is already implemented, tested, and owned by ADK/litellm. A hand-rolled
  wrapper (A) would duplicate what's already there and risk timing out at
  the wrong layer (e.g. mid-tool-call instead of per HTTP request).

### This is a separate retry loop from `_VALIDATION_RETRY_LIMIT`, not a merge

- **Options:** A — fold network retry into the same loop/counter that
  already retries on citation-marker validation failures
  (`docs/citation_marker_retry.md`). B (chosen) — keep them distinct:
  `retry_options` retries at the HTTP-request layer, inside one
  `litellm.completion()` call; `_VALIDATION_RETRY_LIMIT` retries at the
  turn layer, after a successful response fails schema validation.
- **Chose:** B.
- **Consequences:** the two address different failure classes — a reset
  connection (nothing came back) versus a well-formed but invalid response
  (something came back, it was wrong). Conflating them into one counter
  would make retry behavior harder to reason about for either case.

## Not doing

- **Exposing timeout/retry as CLI flags** — no stated need yet; a
  reasonable fixed default plus code-level tuning is enough until a real
  case wants it configurable per run.
- **Retrying `ValidationError`s here** — already owned by
  `docs/citation_marker_retry.md`'s separate mechanism.

## Open questions

- **Exact timeout and retry-count values.** No data yet on real per-turn
  latency for a 61-field, 10-`call_group` run against this project's
  actual model/network. Start with a generous timeout (several minutes)
  and a small retry count (2-3), tune against what's actually observed —
  not decided precisely here.

## Implementation

`_MODEL_CALL_RUN_CONFIG = RunConfig(http_options=HttpOptions(timeout=300_000,
retry_options=HttpRetryOptions(attempts=3)))`, built once at module load,
passed as `run_config=` to the single `runner.run_async(...)` call site in
`_run_bounded_call_async` (the retry loop covers every turn -- bootstrap
and each `call_group` -- there's only one call site, not two). 5 minutes,
3 attempts (2 retries): starting values per the Open Question above, not
tuned against real observed latency yet.

No network condition to simulate a mid-request reset was available here.
Verified the values are wired correctly instead: a fake `Runner.run_async`
captures its `run_config` kwarg; asserted `http_options.timeout` and
`http_options.retry_options.attempts` match the constants
(`test_run_bounded_call_passes_bounded_http_timeout_and_retries`). Traced
the propagation path in ADK's own source
(`base_llm_flow.py`/`basic.py`/`lite_llm.py`) confirming
`RunConfig.http_options` reaches `litellm.completion()`'s `timeout`/
`num_retries` kwargs, matching this doc's own Why section. Relying on the
next real run for confirmation against an actual reset, per this doc's
own "Next" plan.
