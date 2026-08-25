# llm-cost-carbon — Implementation Plan (Revised: Cost-Only v1)

> **Revision note, 2026-07-29:** the original v1 scope (5 MCP tools, dual
> capture-and-model sources, carbon/energy modeling via an adapted aienergy
> FLOP methodology, three-tier provenance tagging, an append-only ledger)
> was judged more than a first ship needs. This revision cuts the plan down
> to a simple AI inference **cost** tool — no carbon/energy — while keeping
> everything from Step 1 that doesn't depend on the cut scope. The project
> name (`llm-cost-carbon`) predates this cut and is not changed here; that's
> a separate decision. See "What changed from the original plan" below for
> the full list of cuts and why each one is safe to make.

## What this is

An MCP (Model Context Protocol) server that answers one question about LLM
inference: "what did this cost in dollars" — reconciling real, captured
usage (via the `ccusage` CLI) with manual token-count estimates, in one
place. It ships as an MCP tool layer only: a local Python process, stdio
transport, no proxy, no daemon, no paid APIs, no cloud infrastructure. An
agent (e.g. Claude Code) calls tools on demand.

## Why this design

Real cost/token capture delegates to the `ccusage` CLI (MIT, pinned to
`ccusage@20.0.19`), which already parses local session logs for supported
hosts and exposes `--json` output — this project doesn't reinvent that.
This project's own contribution is small and honest about it: normalizing
`ccusage`'s per-source output shapes into one schema, and a manual-estimate
fallback (`list_models()`'s pricing table) for models/hosts `ccusage`
doesn't capture, tagged clearly as an estimate rather than real usage.

## What changed from the original plan (cuts, stated explicitly)

- **Carbon/energy modeling is cut entirely** — no Wh, no gCO2, no aienergy
  FLOP methodology, no `implied_markup()` (that metric compared price
  against a physics-derived compute-cost floor; without carbon/energy
  modeling there's no floor left to compare against). The two constants
  research had sourced for it (Lambda Labs H100 $/GPU-hour, a Cerebrium
  throughput benchmark) are moot and not carried forward.
- **`methodology()` as a dedicated tool is cut** — it mainly existed to
  explain carbon/energy assumptions. A cost-only tool's pricing sources
  fold into `list_models()`'s output instead of needing a 5th tool.
- **The append-only ledger and `export_ledger()` are cut** — the ledger was
  an auditability feature for a multi-tier provenance system. With
  carbon/energy gone there's one provenance question left ("was this real
  usage or a manual estimate?"), answered inline in the return value, no
  standing ledger file needed.
- **Three-tier `measured`/`modeled`/`assumed` provenance is cut**, replaced
  by a two-value tag on `estimate`/`compare` output: `"captured"` (real
  usage pulled from `ccusage`) or `"estimated"` (a manual token-count
  input). No formal tagging system, no separate plan section for it.
- **`constants.py`'s physical constants are mostly cut** (H100 FLOPs/J,
  PUE, grid carbon intensity, the implied_markup baseline) — these only
  existed for carbon/energy math. Two survived the cut on inspection, not
  by category assumption: `CCUSAGE_VERSION` (a pinned dependency version,
  not a physical constant) and `STALENESS_THRESHOLD_DAYS` (pricing-data
  freshness matters exactly as much for a cost-only tool).
- **`aienergy` is dropped as a dependency entirely** — `ccusage` becomes
  the only external dependency this project wraps.

**Resulting tool count: 3** (`estimate`, `compare`, `list_models`) — down
from 5. This is a named decision, not a silent drift.

## What's unchanged

- The 5-source host list validated in Step 1 (Claude Code, Codex,
  OpenCode, pi-agent, Amp) — cost-relevant regardless of carbon scope.
- The `ccusage` pin (`20.0.19`, not `@latest`) and the reasoning for it
  (a program depending on stable JSON shape needs to fail loudly on drift).
- Fixture-based contract testing for the adapter layer.
- Output precision: USD to 6 decimal places.
- Zero-cost, local-only, stdio-transport constraints.

## An open finding, not yet acted on

The original model-table selection (5 dense, published-parameter,
open-weight models: Llama 3.1 8B/70B/405B, Mistral 7B, Qwen2.5 72B) was
constrained by needing FLOP-computable parameter counts, which mattered
only for carbon/energy modeling. That constraint is gone. A cost-only
tool's model list should probably prioritize the models people actually
ask about cost for — including Claude and GPT, which have real published
API pricing even without public parameter counts. Not reshaped in this
revision (the user chose to leave it as a flagged follow-up rather than
redo the research pass now) — worth revisiting before Step 2 if the model
list feels thin for real usage.

## Directory structure

```
llm-cost-carbon/
  src/
    llm_cost_carbon/
      __init__.py
      adapters/
        ccusage.py         # subprocess wrapper around pinned ccusage binary
      calc/
        reconcile.py         # reconcile() -- pure functions, cost only now
        constants.py          # CCUSAGE_VERSION, staleness threshold only
      data/
        models.json            # hand-picked model table: pricing + source only
      server.py               # MCP server: registers the 3 tools
  tests/
    fixtures/
      ccusage_claude_daily.json
      ccusage_codex_daily.json
      ccusage_opencode_daily.json
      ccusage_pi_daily.json
      ccusage_amp_daily.json
    test_ccusage_adapter.py
    test_calc.py
    test_server.py
    test_models_data.py
  scripts/
    smoke_ccusage.py          # Step 1 smoke script (unchanged)
  README.md
  pyproject.toml
```

No `ledger.py` — cut along with the ledger.

## Data model

`UsageRecord` (adapter output, internal) — unchanged in shape from the
original plan's cache-token fix, since cache tokens affect cost capture
independent of carbon modeling:
```python
@dataclass
class UsageRecord:
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int   # 0 with a "not reported by this source"
    cache_read_tokens: int       # marker if the source doesn't expose these
    usd_cost: float
    source: str          # e.g. "claude", "codex"
    window_start: str    # ISO-8601 UTC
    window_end: str      # ISO-8601 UTC
```

`ReconciledResult` (internal, returned by `reconcile()`, consumed by
`estimate`/`compare`) — the carbon fields, discrepancy fields, and
three-tier provenance dict are gone; replaced by a single two-value tag:
```python
@dataclass
class ReconciledResult:
    model: str
    usd_cost: float
    source: str            # "captured" (from ccusage) | "estimated" (manual tokens)
    capture_status: str    # "captured" | "unavailable" | "not_covered"
    capture_reason: str | None
    citations: list[str]
    stale: bool             # true if the model row's last_verified > 90 days
```
Resolution rule (unchanged from the pre-cut version, still applies): a
capture failure (timeout, missing host, parse error) does not raise — it
populates `capture_status`/`capture_reason` and falls through to the
manual-estimate path.

No `LedgerEntry` — cut along with the ledger.

## Constants (`calc/constants.py`, trimmed 2026-07-29)

- `CCUSAGE_VERSION = "20.0.19"` — pinned exactly, not `@latest`.
- `OUTPUT_PRECISION_USD_DECIMALS = 6`.
- `STALENESS_THRESHOLD_DAYS = 90`.

Everything else from the pre-cut constants file (H100 FLOPs/J, PUE, grid
carbon intensity, the implied_markup baseline) is deleted, not deprecated
in place — there's no future call site for it in this scope.

## The 3 MCP tools

```python
def list_models() -> ModelTable:
    """Table of covered models: usd_price_per_million_output_tokens,
    price_source, last_verified. No energy/carbon columns.
    """

def estimate(
    model: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    host: str | None = None,
    window: str = "today",       # "today" (default, UTC) | "all" | explicit ISO date
) -> EstimateResult:
    """$ cost, tagged 'captured' or 'estimated'.

    Two modes:
    - host given AND covered by ccusage: input/output_tokens optional,
      pulls real usage via the ccusage adapter for the given window,
      tagged 'captured'. If the requested model isn't present in that
      window, returns zero cost (not an error).
    - host omitted, or host not covered by ccusage, or capture fails:
      input/output_tokens required, uses the manual pricing table, tagged
      'estimated'. Never raises on an uncovered host or capture failure --
      sets capture_status/capture_reason as a structured field.

    host is validated against the 5 known ccusage subcommands before
    reaching subprocess construction (whitelist, not passthrough).
    """

def compare(
    models: list[str],
    input_tokens: int,
    output_tokens: int,
) -> ComparisonTable:
    """Ranked $ cost table across models, always 'estimated' mode (no host
    argument -- comparing hypothetical token counts isn't a capture use
    case).
    """
```

Internal-only (not an MCP tool): `reconcile(usage: UsageRecord | None,
model: str, input_tokens: int, output_tokens: int) -> ReconciledResult` in
`calc/reconcile.py`, called by `estimate`/`compare`.

## Response type sketch

```python
@dataclass
class EstimateResult:
    model: str
    usd_cost: float
    source: str             # "captured" | "estimated"
    capture_status: str
    capture_reason: str | None
    citations: list[str]
    last_verified: str
    stale: bool
```

## Reliability hardening (unchanged from the pre-cut plan, still applies)

- Pin `ccusage@20.0.19` exactly (lockfile) — not `@latest`.
- Fixture-based contract tests: one checked-in `--json` fixture per tested
  source subcommand, generated fresh against `ccusage@20.0.19` (any fixture
  predating 2026-07-09 is stale due to a per-model-breakdown JSON shape
  change in v20.0.15).
- Subprocess construction: `subprocess.run(args_list, shell=False,
  timeout=<stated>, capture_output=True)` — `host` is agent-supplied
  input, whitelisted against the 5 known subcommands before reaching the
  argument list. A timeout degrades to the estimated path, not a raise.
- `npx ccusage@20.0.19` performs a registry lookup on each run — a real
  network call. README states this explicitly, or the adapter requires a
  local `npm i -g ccusage@20.0.19` install and invokes the binary directly.
- Every model table entry carries `last_verified`; the 90-day staleness
  check runs as a scheduled job / `make verify` target (not push-triggered
  CI), and the runtime response carries `stale: true` past the threshold.

## Build order (5 steps — Step "6" from the original plan collapses into
## Step 5, since methodology()/ledger content that used to pad it out is
## gone)

### Step 1 — Repo scaffold + dependency check (DONE, carried forward)
Directory structure, `pyproject.toml`, pinned `ccusage@20.0.19`, hand-picked
model table. Completed under the pre-cut scope; trimmed in this revision
to drop carbon/energy fields (`params`, `params_provenance`, `precision`,
`wh_per_1k_output_tokens`, `gco2_per_1k_output_tokens`). Verify condition
(smoke script + model table shape) re-confirmed passing after the trim —
see this session's Review Agent report.

### Step 2 — Adapter layer
`adapters/ccusage.py`: thin parser turning ccusage's JSON output into
`UsageRecord`, including cache-token fields and window bounds. Unchanged
from the pre-cut plan — cost capture never depended on carbon modeling.
Real fixtures already captured in Step 1 (`tests/fixtures/`): `claude` and
`codex` have genuine non-empty usage data on this machine; `opencode`,
`pi`, `amp` are validly-empty (no local usage history here), which is a
pass per Step 1's relaxed verify bar but weaker as a contract test.

**Verify:** a contract test per tested source subcommand loads its
checked-in fixture and asserts every `UsageRecord` field is present and
correctly typed, including cache-token fields (zeroed with a "not reported
by this source" marker where the source doesn't expose them). Tests fail
loudly (not silently coerce/drop) on a missing field.

### Step 3 — Core synthesis calc module
`calc/reconcile.py`: `reconcile()` only now (`token_breakdown()` and
`implied_markup()` are cut along with carbon/energy scope). Pure function,
no MCP imports. Tests written first (TDD).

**Verify:** zero-token input returns zero, not an error; an unknown model
raises a named exception rather than returning null; a host not covered by
ccusage returns an `'estimated'`-tagged result via the manual pricing
table rather than crashing.

### Step 4 — MCP server
`server.py`: wraps the adapter + calc module, registers the 3 tools
(`list_models`, `estimate`, `compare`). No ledger writes — cut.

**Verify:** MCP Inspector round-trips each tool; returned numbers match a
hand-computed example to 6 decimal places (USD).

### Step 5 — Validate against Claude Code, then README + one written finding
`claude mcp add` the server to a real Claude Code session; ask it to
compare cost/1K tokens across 3 models (name the tool explicitly if it
doesn't reach for it unprompted) — transcript shows the tool actually
invoked, numbers match Step 4's hand-check. Then write the README:
what the tool does, install/setup, `ccusage` attribution (MIT), a Data
Handling section (what's read locally, the `npx` network-lookup
disclosure, telemetry status: none), and this revision's written finding
(the scope cut from cost-and-carbon to cost-only, and why — the same kind
of honest scope narrowing the original plan already did once for the
aienergy-dataset gap).

**Verify (run bar — the sole pass/fail condition, carried from the
pre-cut plan):** someone willing to try it can go from the install command
to a correct `estimate()` result in under 5 minutes, including installing
the pinned `ccusage` dependency.

## Testing approach

pytest throughout (`pythonpath = ["src"]` set in `pyproject.toml` so
`pytest` runs standalone without manual `PYTHONPATH`). Contract tests for
the adapter run against checked-in fixtures, never live `ccusage` calls.
Calc-module tests are pure unit tests with no I/O. Server-level tests
(`tests/test_server.py`) use an in-process MCP client against a temp
directory — no ledger file to manage now.

## Step 3/4 design detail (system-design pass, added after Step 2 completion)

Steps 3 and 4 above state the *what* (`reconcile()` exists, capture
failures fall through to the estimated path, three tools get registered)
but not the *how*. This section fills that gap without reopening any
decision already made above — tool count, cuts, and data-model shapes are
unchanged.

**`reconcile()`'s actual contract.** `reconcile()` does not decide
`capture_status` itself — that's the caller's (`estimate()`'s) job, since
only the caller knows *why* capture didn't happen (host omitted vs.
uncovered vs. subprocess timeout vs. parse error). `reconcile()` takes
`capture_status` as an input and stays a pure function — no subprocess
awareness inside it at all, satisfying Step 3's own verify bar.

```python
def reconcile(
    usage: UsageRecord | None,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    capture_status: str,       # decided by the caller, not here
    capture_reason: str | None,
) -> ReconciledResult:
```

Inside:
1. Look up `model` in `models.json`. Not found raises `ModelNotFoundError(model)`
   — the one exception allowed to reach the MCP boundary as a real error
   rather than a fallback.
2. If `usage` is present (captured path): `usd_cost = usage.usd_cost`
   directly. `ccusage`'s own figure is used as-is, **not** recomputed from
   tokens × list price. This can look inconsistent at a glance — it isn't:
   captured and estimated answer different questions (what you were
   actually billed vs. a hypothetical at public list price), and
   substituting list price into a known-real number would be a silent
   downgrade, not a simplification.
3. If `usage` is absent (estimated path): `usd_cost = tokens × models.json
   price`. Missing `input_tokens`/`output_tokens` is caught in `estimate()`
   *before* `reconcile()` is called — a tool-boundary input-validation
   concern, not a reconciliation concern.
4. `citations`/`stale` always populate from the model row
   (`price_source`, `last_verified` vs. `STALENESS_THRESHOLD_DAYS`).

**`estimate()`'s orchestration** (Step 4, logic belongs conceptually with
reconcile's design):

```
if host is None: capture_status, usage = "not_covered", None
elif host not in KNOWN_CCUSAGE_SOURCES:      # whitelist BEFORE subprocess construction
    capture_status, usage = "not_covered", None
else:
    try:
        usage = adapter.get_usage(host, model, window)
        capture_status = "captured"          # zero rows -> captured, usd_cost 0 -- not an error
    except (TimeoutExpired, JSONDecodeError) as e:
        usage, capture_status, capture_reason = None, "unavailable", str(e)

if capture_status != "captured" and (input_tokens is None or output_tokens is None):
    raise ValueError("input_tokens/output_tokens required when capture unavailable")

return reconcile(usage, model, input_tokens, output_tokens, capture_status, capture_reason)
```

**`server.py` boundary.** pydantic validates the MCP-facing
request/response; internal types stay plain dataclasses (already this
project's convention per `adapters/ccusage.py`'s own comment: pydantic at
the MCP surface, dataclasses internally). `ModelNotFoundError` and the
missing-tokens `ValueError` both become normal MCP tool-error responses,
not server crashes.

**Trade-offs made in this design:**
- Trusting `ccusage`'s own cost figure in the captured path vs.
  recomputing for internal consistency — chose trusting it, per point 2
  above.
- Host whitelist before subprocess construction vs. passing it through —
  whitelist, because `host` is agent-supplied input reaching a subprocess
  argument list; closing off that injection-shaped mistake on principle,
  even though `ccusage` would likely reject a bad value anyway.
- `capture_status` decided by `estimate()`, not `reconcile()` — keeps
  `reconcile()` pure and trivially unit-testable, at the cost of slightly
  more branching in `estimate()` itself.

**Scale & reliability — deliberately short.** Single-user, single-process,
local stdio server: no load estimation, no horizontal scaling, no
failover needed, and forcing that framework on here would be the same
overengineering this whole revision has been cutting away. The one real
reliability concern is that the `ccusage` subprocess call is a genuine
network call (npx registry lookup) with real latency/failure modes —
which is exactly why capture failures degrade to the estimated path
instead of raising (see `estimate()`'s orchestration above).

**What to revisit as this grows:** a 6th `ccusage`-covered host means
updating the whitelist and the adapter dispatch together — worth one
shared constant between `adapters/ccusage.py` and `server.py` rather than
two literals, when that day comes. If the model table grows past ~10-15
entries (see "An open finding, not yet acted on" above), `list_models()`
may want filtering — not needed at today's 5 entries.

## Corrections from Step 3/4 implementation (verified against committed code, 2026-08-03)

**`mcp` package API naming.** The design section above and this plan both
assumed a `FastMCP` decorator class. The installed `mcp==2.0.0` has no such
class — it ships `mcp.server.mcpserver.MCPServer` (server-side tool
registration) and `mcp.client.Client` (in-process test client) instead,
same roles, different names. `server.py` and `tests/test_server.py` are
built against the real installed API. Any future prompt referencing
"FastMCP" for this project is wrong — use `MCPServer`/`Client`.

**Confirmed bug: `estimate()`'s `window` parameter was never implemented.**
The signature above specifies `window: str = "today" | "all" | explicit
date`, but the committed `server.py` has no `window` argument at all. The
captured-path code reduces `PARSERS[host](data)` (a list, one record per
(date, model) pair) to a single record via `next((r for r in records if
r.model == model), None)` — which returns whichever matching record comes
first in `fetch_daily()`'s date-ordered output, not today's.

Verified against `tests/fixtures/ccusage_claude_daily.json`: `"claude-sonnet-5"`
appears on 14 different days between 2026-07-09 and 2026-07-29 at different
costs each day ($10.54 on 07-09, $20.80 on 07-29 — the fixture's most
recent/"today" entry). `estimate(model="claude-sonnet-5", host="claude")`
as committed silently returns **$10.54 from 2026-07-09**, not today's
$20.80. None of the 5 passing `test_server.py` tests catch this — the only
host-based test mocks `fetch_daily` to raise an exception, so the real
multi-day reduction logic was never exercised against fixture data with
more than one matching day.

**Status: fixed and verified (Step 4b, 2026-08-03).** `_select_window()`
landed in `adapters/ccusage.py` exactly as specified below; `estimate()`
gained `window` with pre-fetch validation. Confirmed by hand: summing all
14 matching `claude-sonnet-5` rows gives `214.11233100000004`, matching the
`window="all"` test exactly. The zero-match/mislabeled-`source` issue is
fixed as a side effect — `_select_window()` never returns `None`, so
`reconcile()` always takes the "usage present" branch and reports
`source="captured"` correctly. Test suite added a `_FrozenDate` shim
(monkeypatches `_date.today()` to 2026-07-29) so the "today" test doesn't
rot as real time moves past the fixture's last date — a test-longevity
concern the original prompt didn't anticipate. `calc/reconcile.py`
confirmed byte-for-byte unchanged.

This also exposes a design gap, not just an implementation shortcut:
`reconcile()`'s contract takes a single `UsageRecord | None`, but a correct
`"today"` filter needs to select by date, and `"all"` needs to *sum* across
every matching record — a singular-record contract can't represent that
without an aggregation step this plan never specified. The fix belongs
entirely in `server.py`'s orchestration, not in `reconcile()`:

```python
def _select_window(records: list[UsageRecord], model: str, host: str, window: str) -> UsageRecord:
    """Filters to the requested window, summing across days for "all".
    Never returns None -- a captured result with no matching usage is a
    legitimate zero-cost record, not an absence. Cache-token fields on the
    returned record are irrelevant here (reconcile() never reads them) and
    are set to None rather than aggregated."""
    matches = [r for r in records if r.model == model]
    if window != "all":
        target_date = date.today().isoformat() if window == "today" else window
        matches = [r for r in matches if r.window_start.startswith(target_date)]

    if not matches:
        today = f"{date.today().isoformat()}T00:00:00Z"
        return UsageRecord(model=model, input_tokens=0, output_tokens=0,
                            cache_creation_tokens=None, cache_read_tokens=None,
                            usd_cost=0.0, source=host,
                            window_start=today, window_end=today)
    return UsageRecord(
        model=model,
        input_tokens=sum(r.input_tokens for r in matches),
        output_tokens=sum(r.output_tokens for r in matches),
        cache_creation_tokens=None, cache_read_tokens=None,
        usd_cost=sum(r.usd_cost for r in matches),
        source=host,
        window_start=min(r.window_start for r in matches),
        window_end=max(r.window_end for r in matches),
    )
```

`window` not in `{"today", "all"}` and not matching an ISO date string
raises `ValueError` before `fetch_daily()` is even called. Fix tracked as
Step 4b, not yet built.

## Automation-tooling decisions (post-v1 cleanup round, 2026-08-20/21)

Dispatched via `/agents`-style subagent tasks, then re-checked by hand
against real repo state. Recorded here so future reconsideration starts
from this reasoning instead of re-deriving it.

- **context7 MCP, GitHub MCP — dropped.** `gh issue list` / `gh pr list`
  both empty, single branch, no PR/issue workflow exists in this repo.
  Nothing for either to do.
- **`models.json`-guard hook (PreToolUse, warn/block on price edits
  without a `last_verified` bump) — deferred.** Revisit when
  `models.json` maintenance is actually in scope, i.e. when the table
  starts seeing repeat price-update edits rather than one-off additions.
- **`mcp-contract-reviewer` subagent (checks new/changed MCP tool
  signatures against this plan doc) — deferred again, trigger tightened.**
  Originally deferred with trigger "a new/changed MCP tool" (2026-08 early
  round). That trigger fired when the ledger revival added
  `ledger_summary`/`export_ledger` (2 new tools). Reconsidered 2026-08-21,
  against the live 5-tool/10-model server, not from memory:
  - Checked whether real plan-vs-reality drift recurred with this build.
    It did not — the ledger section here and what got built track closely,
    including every stated verify condition. The one real deviation
    (`compare()` initially written as one ledger entry per model instead
    of one per call) was caught and fixed by hand, same session, before
    commit — by manually diffing this plan doc, not by any automated tool.
  - The two incidents that originally motivated this subagent (the
    FastMCP/MCPServer naming mismatch, the `window` param gap above) were
    both *silent* drift — nothing caught them until something broke
    downstream. This time the drift was loud: caught same-session, before
    commit, by manual plan-diffing. A reviewer only earns its keep against
    the silent kind.
  - Conclusion: "a new tool ships" was too broad a trigger — it's
    effectively always true. **Tightened trigger: revisit only if a
    future tool ships without being diffed against this plan doc before
    commit** — not "a new tool ships." At 5 tools, manual review remains
    cheap and has, in practice, already worked.
