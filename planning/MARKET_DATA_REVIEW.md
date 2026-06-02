# Market Data Backend — Code Review

**Reviewer:** Claude (Opus 4.8)
**Date:** 2026-06-02
**Scope:** `backend/app/market/` (8 modules), `backend/app/main.py`, `backend/tests/market/` (7 modules), `backend/market_data_demo.py`, `backend/pyproject.toml`, and the planning docs that describe them.

## Verdict

The market data backend is **well-built and functional**. The architecture matches PLAN §6 and MARKET_INTERFACE.md: one background producer writes a shared in-memory cache; SSE readers only ever read the cache; the source is selected by env var behind a clean ABC. Code is small, readable, and idiomatic — consistent with the project's "don't over-engineer" rule. **All 92 tests pass** (~2.3s).

No correctness bugs were found in the runtime code. The issues below are **documentation drift** and **dependency/tooling hygiene** — none block the next stage of the build, but several should be tidied.

## Test Run

```
cd backend && uv run pytest -q
92 passed in 2.34s
```

| Module | Focus |
|--------|-------|
| test_types.py | Quote properties, `to_event`, immutability |
| test_cache.py | version counter, change detection, open/prev capture, uppercasing |
| test_simulator.py | GBM math, determinism, positivity, event shocks, rounding |
| test_simulator_source.py | async run/prime/cancel, validate_symbol |
| test_massive.py | price/ts extraction, poll behavior, error handling, validate_symbol |
| test_factory.py | env-var source selection, interval override |
| test_stream.py | SSE wire format, snapshot, change-only emit, keepalive, disconnect |

Coverage is good by inspection — happy paths and the important edge cases (HTTP 429, missing price keys, empty watchlist, zero `open_price` guard, disconnect) are all exercised.

## What's Good

- **Clean separation of concerns.** `MarketSource` ABC + `PriceCache` are the only things consumers import; the two concrete sources are interchangeable. The factory is the single decision point.
- **Cache as single source of truth**, exactly per the interface contract. The version counter + per-ticker version map gives O(changed) "emit only on change" (PLAN §13.3) without diffing full snapshots.
- **Correct async hygiene.** Both sources loop with `await asyncio.sleep(...)` and re-raise `CancelledError`; the lifespan in `main.py` cancels and awaits the task on shutdown. The Massive client uses `httpx.AsyncClient` (non-blocking) rather than the synchronous official client — the right call, and documented in the code.
- **Massive client matches the documented Polygon/Massive contract** (MASSIVE_API.md): `lastTrade.p` preferred, `day.c` fallback, ns→s timestamp conversion, missing-key guards, graceful 429/HTTP-error handling that preserves the last good cache value.
- **Session-open baseline** (PLAN §13.2) is captured once on first sighting in `PriceCache.set_price` and never mutated — correct, and resets on restart by design.
- **Tests are clear and well-targeted**, using `httpx.MockTransport` for the realistic poll path and `unittest.mock` for the validate-symbol path.

## Findings

### 1. Demo declares a dependency it doesn't have — `rich` is not installed (Medium)

`market_data_demo.py` imports `rich` and its docstring says *"Requires: rich (included in dev dependencies)"*, but `rich` is **not** in `pyproject.toml`. Verified: `uv run python -c "import rich"` → `ModuleNotFoundError`. Running the documented demo command fails immediately with the "Install rich" message.

**Fix:** add `rich` to the dev dependency group (or correct the docstring to instruct `uv add --dev rich` first). The MARKET_DATA_SUMMARY.md "Demo" section is similarly misleading.

### 2. `respx` dev dependency is unused (Low)

`pyproject.toml` lists `respx>=0.21.0` as a dev dependency, but no test imports it (the HTTP tests use `httpx.MockTransport` and `unittest.mock` instead). Dead dependency.

**Fix:** remove `respx`, or use it where it would simplify the Massive HTTP tests.

### 3. `tool.uv.dev-dependencies` is deprecated (Low)

pytest/uv emits: *"The `tool.uv.dev-dependencies` field … is deprecated … use `dependency-groups.dev` instead."*

**Fix:** migrate to:
```toml
[dependency-groups]
dev = ["pytest>=8.0.0", "pytest-asyncio>=0.24.0", "rich>=13.0.0"]
```

### 4. MARKET_DATA_SUMMARY.md is stale and inaccurate (Medium — docs)

The summary no longer matches the code. Concretely:

- **Module names are wrong.** Summary lists `models.py`, `interface.py`, `seed_prices.py`, `massive_client.py`. Actual files are `types.py`, `base.py`, `sim_config.py`, `massive.py`. The exported type is `Quote`, not `PriceUpdate`.
- **Test count is stale:** summary says "73 tests"; the suite now has **92**.
- **Coverage claims are unverifiable:** summary cites "84% overall" and per-file percentages, but **no coverage plugin is installed** (`pytest-cov` is absent; `--cov` fails). Either add `pytest-cov` and regenerate the numbers, or drop the coverage table.
- **"`massive` package is a core dependency"** (point #2 of its "fixes" list) is false. The implementation deliberately uses `httpx` directly; `massive` is not in `pyproject.toml` and is not imported anywhere.
- **Correlation method mismatch** (see #5).

**Fix:** regenerate the summary from the current code, or mark it as a point-in-time snapshot.

### 5. Simulator correlation differs from its documented design (Low — docs)

MARKET_DATA_SUMMARY.md describes "Cholesky decomposition of a sector correlation matrix; tech 0.6, finance 0.5, cross-sector 0.3." The actual `simulator.py` uses a simpler and perfectly valid **factor model**:

```
z = 0.5·z_market + 0.4·z_sector + 0.768·z_idio
```

This yields same-sector correlation ≈ 0.41 (0.5²+0.4²), cross-sector ≈ 0.25 (0.5²), and preserves unit variance (0.25+0.16+0.59 = 1.0). The factor model is arguably the better choice here (simpler, no matrix algebra) — but the doc claims an implementation that isn't there. Update the doc to describe the factor model and its actual correlation values.

### 6. No `.env.example` in the repo (Medium — scope-adjacent)

PLAN §5 states `.env.example` should be committed and mirror the env block. It does not exist. `.env` exists but only contains one of the documented keys. This may belong to a later stage, but flagging it since the factory and PLAN both depend on `MASSIVE_API_KEY` / `MASSIVE_POLL_SECONDS` semantics.

### 7. No linter configured (Low)

No `ruff`/`mypy` config in `pyproject.toml`. For a course capstone demonstrating production practices, adding `ruff` (lint + format) would be cheap and valuable. Optional.

## Minor Notes (no action required)

- **`MassiveSource.run`** sets `base_url=BASE_URL` on the client but then passes the absolute `SNAPSHOT_URL`. httpx handles this correctly (absolute URL wins); slightly redundant.
- **`validate_symbol`** opens a fresh `AsyncClient` per call rather than reusing the poller's client. Acceptable — it's an infrequent watchlist-add path — but a shared client would be marginally cleaner.
- **`MASSIVE_POLL_SECONDS`** is parsed with bare `float(...)` (no error handling). Consistent with the project's "don't program defensively" rule; fine.
- **Cache "no lock needed"** reasoning is sound for the current single-loop design and is well-documented in the docstring, including the upgrade note for a future threaded poller.
- **`test_stream.py`** lines 116–118 contain a confusing leftover comment ("Actually in this test the prices don't change…") that contradicts the test name; harmless but worth cleaning.
- **`main.py`** uses `_placeholder_watchlist()` — expected at this stage; will be replaced when the DB/watchlist module lands.

## Recommended Actions (priority order)

1. Add `rich` to dev deps (or fix the demo docstring) so the documented demo runs. *(Finding 1)*
2. Regenerate / correct MARKET_DATA_SUMMARY.md — file names, test count, coverage claims, `massive` dependency, correlation method. *(Findings 4, 5)*
3. Remove unused `respx`; migrate to `[dependency-groups]`. *(Findings 2, 3)*
4. Add `.env.example` if it's in scope for this stage. *(Finding 6)*
5. Optional: add `pytest-cov` and `ruff`. *(Findings 4, 7)*

**Bottom line:** the runtime code is solid and ready to build on. The cleanup is almost entirely in docs and dependency declarations.
