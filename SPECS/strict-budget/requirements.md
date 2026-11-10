# Requirements — Strict budgets: expose and persist

**Status:** Draft for approval
**Branch:** `fix/strict-budget`
**Bug reference:** `/BUG_SPEC.md` (workspace) — "strict budget unreachable from CLI"
**Base:** `main` @ `af3f7eb`

---

## 1. Context

`pocketbudget-cli` is a single-user, offline budgeting CLI. Its domain model supports two
budget behaviours:

- **Non-strict** (default): an over-limit expense is recorded, the category total is updated,
  and the CLI prints a warning. This is the behaviour documented in `rules.md` §4 and covered
  by the existing suite.
- **Strict**: an expense that would push a category past its limit raises
  `BudgetLimitExceededError` before any mutation.

The strict behaviour exists in `Account` (`account.py:58–64`, `set_budget(...,
strict=False)` at `account.py:75–84`), is covered by five domain tests
(`tests/test_errors.py:47–110`), and its exception is already caught by the CLI
(`cli.py:17`, `cli.py:32`). It is nonetheless unreachable and non-durable:

1. **Wiring gap** — `cli._set_budget` (`cli.py:89–97`) calls
   `account.set_budget(category, amount)` and never passes `strict=True`. No CLI input can
   create a strict budget.
2. **Persistence gap** — `storage.save` (`storage.py:14–21`) serialises only `history` and
   `budgets`; `_apply_budgets` (`storage.py:64–75`) replays budgets via
   `set_budget(category, amount)`, defaulting to non-strict. Because every CLI command loads
   from disk before acting (`cli.py:116–121`), strictness is discarded between invocations.

Fixing either gap alone leaves the capability unusable, so both are in scope.

## 2. Problem statement

A user cannot configure a category budget that blocks overspending, and the application
silently ignores the domain's strict mode. The failure is silent: no error, no warning, and
no persisted trace. The bug category is **lossy persistence projection** — a domain field
that mutates through public methods but is absent from the storage payload
(`_strict_budgets` is the only such field; see §9).

## 3. Goals

- Make strict mode reachable from the CLI and durable across process invocations.
- Preserve, byte-for-byte where possible, the existing non-strict behaviour and the existing
  save-file format.
- Fix the whole bug category (both halves) and lock it with regression tests.

## 4. Non-goals

- Changing `rules.md` §4 or the default (non-strict) semantics.
- Displaying strictness in `show-summary`, `show-balance`, or `show-history`.
- Adding a dedicated "un-strict" command (`--strict` omitted reverts; see FR-4).
- Migrating or rewriting existing save files.
- Refactoring `save()` behind a `to_dict()`/single-derivation helper, or any other
  restructuring (explicitly forbidden by the implementation constraints; noted in §10 as the
  structural alternative that was considered and deferred).
- New runtime dependencies, new CLI frameworks, or `argparse`.

## 5. Governing constraints (project constitution)

| Source | Constraint | Effect on this change |
|---|---|---|
| `rules.md` §4 | Non-strict expense is recorded with a warning; totals update | Default path MUST remain unchanged |
| `rules.md` §2 | `ALLOWED_CATEGORIES = Food, Transport, Entertainment` | Both modes validate categories via existing `set_budget` checks |
| Architecture (`account.py` ← `storage.py` ← `cli.py`) | Domain has no I/O; storage depends on domain only; acyclic | Strictness lives in `account`; serialisation stays in `storage` |
| Event-sourced replay (`storage.py:48–61`) | State is rebuilt through the same mutators as live data | Strict budgets MUST be restored through `set_budget(...)`, not by poking internals |
| `storage.py` validation style | Structural problems → `StorageError`; domain-value problems propagate from the domain (`InvalidCategoryError`, `ValueError`) | New structural checks use `StorageError`; unknown categories still surface as `InvalidCategoryError` |
| `ruff.toml` | `E,F,I,C90`, `max-complexity = 7` | New helpers stay small and single-purpose |
| `.pre-commit-config.yaml` | ruff (`--fix`), ruff-format, `mypy --strict`, full pytest | All four must pass |
| Repository history | Conventional commits (`feat:`, `test:`, `docs:`), direct commits, single author | Commits follow the same convention; work on `fix/strict-budget` |
| User directive | Touch as few lines as possible; no refactors; no new dependencies; match existing style | Line budget in §11; no unrelated edits |

## 6. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Repair** strict mode rather than remove it | Domain API and five tests already exist; CLI already catches the exception; removal would delete tested public behaviour |
| D2 | Persist strictness as an **additive optional top-level key** `"strict": [<category>, …]`, written only when at least one strict budget exists | Old files remain valid and unmodified; files with no strict budgets remain byte-identical, which keeps the existing exact-payload test (`test_save_writes_account_state_to_file`) passing unedited |
| D3 | CLI surface is a **trailing `--strict` flag** on the existing command | Smallest diff; does not alter `len(args)` checks in any other handler; self-documenting |
| D4 | **Omitting `--strict` reverts** a category to non-strict | Follows directly from the existing `strict: bool = False` default; avoids an extra flag or command |
| D5 | Success message text is **unchanged** | Preserves the existing output contract and CLI tests; strictness is an input mode, not new output |
| D6 | Strictness is **not displayed** anywhere | YAGNI; no requirement, no display contract change |
| D7 | `Account` gains one read-only property, `strict_budgets` | `storage` needs to read the flag without touching `_strict_budgets`; property preserves encapsulation, mirroring the existing `budgets` property |

## 7. Functional requirements

**FR-1 — CLI accepts strict mode.**
`python -m pocketbudget set-budget <category> <limit> --strict` records the budget for
`<category>` with the given `<limit>` and marks that category strict.
Success output remains exactly `Budget of $<limit> set for <category>.` and exit status 0.

**FR-2 — CLI default is unchanged.**
`python -m pocketbudget set-budget <category> <limit>` behaves exactly as today: records a
non-strict budget, prints the same message, exits 0. `rules.md` §4 semantics apply.

**FR-3 — Usage validation.**
`set-budget` accepts exactly two positional arguments, optionally followed by the literal
`--strict`. Any other shape (extra arguments, a different flag, `--strict` in a non-trailing
position) is a usage error: message on stderr, exit 1, no state change.
Usage string becomes: `Usage: pocketbudget set-budget <category> <limit> [--strict]`.

**FR-4 — Strictness is per-category and revocable.**
Setting an existing budget again without `--strict` reverts that category to non-strict while
updating the limit. Other categories' strictness is unaffected.

**FR-5 — Strictness persists.**
`save()` writes the strict categories; `load()` restores them so that a subsequent invocation
enforces them. Round-trip identity holds: for every category,
`load(save(account)).strict_budgets == account.strict_budgets`, and the behavioural outcome of
`add_expense` is identical before and after the round-trip.

**FR-6 — Strict enforcement is all-or-nothing at the CLI.**
With a strict budget active, an expense that would exceed the category limit:
- prints the `BudgetLimitExceededError` message to stderr,
- exits 1,
- leaves the save file byte-identical to its pre-invocation content (or absent, if it did not
  exist), because no `_save` occurs after the exception.

**FR-7 — Non-strict enforcement is unchanged.**
With only non-strict budgets, an over-limit expense prints
`Expense of $<amount> recorded.` followed by `Budget limit exceeded for <category>.` on
stdout, exits 0, persists the expense, and `show-summary` reports `(OVER)` as today.

**FR-8 — Backward-compatible loading.**
Save files without a `"strict"` key load exactly as today (all categories non-strict). Save
files with `"strict": []` are equivalent to absence. Adding strictness later to a legacy file
via the CLI must work without any migration step.

**FR-9 — Deterministic serialisation.**
The `"strict"` array is written in sorted order (the categories are `str`), so identical
account states serialise identically.

## 8. Contracts

### 8.1 CLI contract

| Invocation | stdout | stderr | exit | state |
|---|---|---|---|---|
| `set-budget Food 100` | `Budget of $100 set for Food.` | — | 0 | budget set, non-strict |
| `set-budget Food 100 --strict` | `Budget of $100 set for Food.` | — | 0 | budget set, strict |
| `set-budget Food 100 --strict extra` | — | `Usage: pocketbudget set-budget <category> <limit> [--strict]` | 1 | unchanged |
| `set-budget Food` / `set-budget a b c` / `set-budget Food 100 --STRICT` | — | same usage line | 1 | unchanged |
| `add-expense 30 Food` (strict, over limit) | — | `Expense of $30 would exceed the strict budget of $100 for Food.` | 1 | unchanged |
| `add-expense 30 Food` (non-strict, over limit) | `Expense of $30 recorded.` + `Budget limit exceeded for Food.` | — | 0 | expense persisted |
| `add-expense 200 Food` (strict, under limit) | `Expense of $200 recorded.` | — | 0 | expense persisted |

Notes: the error text is the exception's own message (the CLI prints `str(exc)` via `_error`),
so it MUST NOT be reworded. Non-numeric limits continue to produce `Invalid amount: <raw>`.
Unknown categories continue to produce `InvalidCategoryError`'s message.

### 8.2 Persistence contract

Current payload:
```json
{
  "history": [{"type": "income", "amount": 100}],
  "budgets": {"Food": 100}
}
```

Extended payload (only when at least one strict budget exists):
```json
{
  "history": [{"type": "income", "amount": 100}],
  "budgets": {"Food": 100},
  "strict": ["Food"]
}
```

Rules:
- `"strict"` is an optional top-level key; absence means "no strict categories".
- Value MUST be a JSON array of strings.
- Each entry MUST name a category that also appears in `"budgets"`.
- Duplicates are tolerated and collapse via set semantics (no error).
- Ordering is sorted (FR-9).
- The key MUST be omitted entirely when no category is strict, so payloads for accounts
  without strict budgets are identical to today's.

### 8.3 Domain API contract

- New read-only property `Account.strict_budgets -> list[str]`: sorted snapshot of the strict
  category names. Returns a copy; mutating it MUST NOT affect account state (mirrors
  `history`/`budgets` immutability).
- `Account.set_budget(category, amount, strict=False)` is unchanged in signature, validation,
  and error types.
- `Account.add_expense` is unchanged except that it is now reachable in strict mode from the
  CLI.

## 9. Bug category, sweeps, and prevention

**Category name:** lossy persistence projection.
**Signature:** a field mutated by a public `Account` method and read back on load, but absent
from the `storage.save` payload (or restored with a non-default value dropped).

**H0 (instance):** `_strict_budgets` is dropped by `save()`/restored as empty by
`_apply_budgets` (`storage.py:18–21`, `storage.py:75`).

**H1 (narrow radius):** `_set_budget` is the only handler that drops a domain parameter
(`cli.py:95`). `_add_income` omits the domain's optional `category=None` deliberately — the
CLI requires a category and `tests/test_cli.py` asserts that contract; not a defect.
`_add_expense` passes every parameter.

**H2 (codebase-wide):** all `Account` state was inventoried — `_balance` (derived by replay),
`_history` (persisted), `_category_totals` (derived by replay), `_budgets` (persisted),
`_strict_budgets` (**affected**). No other persistence boundary exists in the repository.
No siblings remain after this fix.

**Prevention (required):** a behavioural round-trip regression test for strictness plus a
payload-shape test, so the projection cannot silently narrow again without a red test. Because
the structural guard (a single `Account` → payload derivation) would require the refactor the
constraints forbid, it is documented here as the deferred alternative, not implemented.

**Silence gap addressed:** `tests/test_storage.py` contained 13 round-trip/validation tests and
none referenced `strict`; the new tests close that specific blind spot rather than adding
generic coverage.

## 10. Edge cases and failure modes

| Case | Expected |
|---|---|
| `"strict"` is not a list (object, string, number) | `StorageError` |
| `"strict": null` | Treated as absent (equivalent to the key being missing) |
| `"strict"` contains a non-string (int, bool, null, list) | `StorageError` |
| `"strict"` names a category with no budget | `StorageError` (structurally inconsistent file) |
| `"strict"` names an unknown category that **has** a budget | `InvalidCategoryError` from `set_budget` (matches "same validation as live data") |
| `"strict"` contains duplicates | Deduped; load succeeds; property returns one entry |
| `"strict"` is `[]` | Treated as absent; load succeeds |
| Legacy file, no `"strict"` | Loads; `strict_budgets == []`; non-strict behaviour |
| Strict budget set, then expense equals the limit exactly | Allowed (existing rule is `> limit`, `account.py:60`) |
| Strict budget set, then `set-budget` without flag | Reverts to non-strict |
| Rejection when no save file exists yet (e.g. expense against a zero balance) | Exit 1; no file is created, proving nothing is saved on failure |
| Rejected expense when save file exists | File bytes unchanged |
| `--strict` before positionals (`set-budget --strict Food 100`) | Usage error (flag is trailing only) |
| `show-summary` with strict budgets | Unchanged output; strictness not shown |

## 11. Implementation constraints (from the user)

1. **Minimal diff.** Production changes limited to three files — `pocketbudget/account.py`,
   `pocketbudget/storage.py`, `pocketbudget/cli.py` — with a net budget of **≤ 30 added lines**
   (guideline: `account.py` ≤ 4, `storage.py` ≤ 16, `cli.py` ≤ 8).
2. **No refactoring.** Do not restructure existing functions, rename anything, or extract
   helpers unrelated to strictness. Existing control flow and message text stay as-is.
3. **No new dependencies.** `requirements.txt` is untouched; standard library only.
4. **Match existing style.** Type hints everywhere, `X | None` unions, module/function
   docstrings where the surrounding code has them, error messages ending in a period,
   `StorageError` structural guards using `isinstance`, tests as plain functions with
   `tmp_path` fixtures and comment-banner grouping.
5. **Lint/format/type clean.** `ruff check`, `ruff format --check`, `mypy --strict`, and the
   full pytest suite must pass; mccabe complexity ≤ 7 per function.
6. **No documentation of unimplemented behaviour.** `README.md` is updated only after the
   behaviour exists.

## 12. Acceptance criteria

- **AC-1** Default `set-budget` behaviour, message, and exit status are unchanged; the
  existing 82 tests pass unmodified.
- **AC-2** `set-budget … --strict` succeeds and the category remains strict across a **separate
  CLI invocation** using the same data file.
- **AC-3** With a strict budget, an over-limit `add-expense` exits 1, writes the exception
  message to stderr, writes nothing to stdout, and leaves the data file byte-identical.
- **AC-4** With a non-strict budget, an over-limit `add-expense` exits 0 with the warning on
  stdout and persists the expense (regression).
- **AC-5** Re-issuing `set-budget` without `--strict` reverts the category to non-strict, proven
  behaviourally after reload.
- **AC-6** A legacy save file (no `"strict"` key) loads and behaves non-strict; strictness can
  then be added through the CLI without migration.
- **AC-7** Accounts with no strict budgets serialise to a payload identical to today's
  (existing exact-equality test passes unmodified).
- **AC-8** Every malformed `"strict"` shape in §10 raises `StorageError`; unknown-but-budgeted
  categories raise `InvalidCategoryError`; duplicates are deduped.
- **AC-9** Invalid `set-budget` usage shapes produce the documented usage error and change no
  state.
- **AC-10** `pytest`, `ruff check`, `ruff format --check`, `mypy --strict`, and
  `pre-commit run --all-files` all pass.
- **AC-11** The production diff touches exactly the three permitted files and stays within the
  line budget; `requirements.txt`, `pytest.ini`, `ruff.toml`, `.pre-commit-config.yaml`,
  `rules.md`, and every existing test assertion are untouched. Test files may gain new
  functions, and the contract block in `tests/test_cli.py`'s module docstring (line 27) may be
  extended to show `[--strict]`; no existing assertion may change.
- **AC-12** `README.md` documents the `--strict` flag; `rules.md` §4 remains accurate and is
  not edited.
