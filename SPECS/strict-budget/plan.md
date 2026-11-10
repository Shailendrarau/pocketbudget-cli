# Implementation Plan — Strict budgets: expose and persist

**Spec:** `SPECS/strict-budget/requirements.md`
**Branch:** `fix/strict-budget` (base `main` @ `af3f7eb`)
**Methodology:** Red/Green TDD, as evidenced by the repository's own history
(`test: …` commits preceding `feat: …` commits) and the `rules.md` "TDD loop" convention.

All commands are run from the repository root with the project virtualenv active. The
repository's tooling is fixed by convention: `pytest` (`pytest.ini`: `pythonpath = .`,
`testpaths = tests`), `ruff check` / `ruff format` (`ruff.toml`: `E,F,I,C90`,
`max-complexity = 7`), `mypy --strict` (`.pre-commit-config.yaml`), and
`pre-commit run --all-files`. No new scripts are introduced.

---

## TG-0 — Baseline and constraint guard

**Goal:** prove the starting point before touching anything.

1. `pytest -q` → expect **82 passed**.
2. `ruff check .` → expect clean. `ruff format --check .` → expect clean.
3. `mypy --strict pocketbudget tests` → expect clean.
4. Record the production line counts of the three target files for the diff budget
   (`account.py` 87, `storage.py` 100, `cli.py` 179) and confirm `git status` is clean.

**Outcome:** a green baseline and a recorded line budget (requirements §11.1). Stop and report
if the baseline is not green — do not "fix" pre-existing failures in this change.

---

## TG-1 — Red: persistence behaviour and payload shape

**Goal:** failing tests that describe the persistence defect, written before any production
change.

Add to `tests/test_storage.py` (follow the existing module conventions: plain functions,
`tmp_path: Path`, `#`-banner comments, explicit imports from `pocketbudget.exceptions`):

1. **Round-trip enforcement** — build an account with income, `set_budget("Food", 100,
   strict=True)`, `save`, `load`, then assert `add_expense(200, "Food")` raises
   `BudgetLimitExceededError` on the reloaded account and leaves its balance/history unchanged.
2. **Per-category identity** — two categories, only one strict; assert
   `loaded.strict_budgets == ["Food"]` and that the non-strict category still warns (returns
   `True`) rather than raising.
3. **Payload contains the key when strict exists** — parse the file and assert
   `data["strict"] == ["Food"]` and that the array is sorted for multiple categories.
4. **Payload omits the key when nothing is strict** — assert `"strict" not in data`
   (regression guard for the byte-identical legacy payload; expected green from the start —
   mark it explicitly as a guard, not a Red test).
5. **Legacy file loads non-strict** — hand-written JSON with only `history`/`budgets`; assert
   `loaded.strict_budgets == []` and an over-limit expense returns `True` (warn) instead of
   raising.
6. **Malformed shapes** — parametrised over `"strict": {}`, `"strict": "Food"`,
   `"strict": [1]`, `"strict": [None]`, `"strict": ["Food"]` where `budgets` lacks `Food`;
   each asserts `StorageError`.
7. **Duplicates dedupe** — `"strict": ["Food", "Food"]` loads with a single entry.
8. **Unknown category that has a budget** — `budgets: {"Shopping": 50}`, `strict: ["Shopping"]`
   asserts `InvalidCategoryError` (same-validation-as-live-data convention already used by
   `test_loaded_data_rejects_invalid_category_like_live_data`).

**Red evidence (expected failure reasons):**
- Tests 1–3 and 7 fail behaviourally: the reloaded account **accepts** the over-limit expense
  (`DID NOT RAISE`) and `strict_budgets` is either empty or the attribute is missing.
  Record whichever occurs; an `AttributeError` on the new property is acceptable **only** for
  test 2/3 (the property is part of the specified API) — but tests 1, 5 and 7 must fail with a
  behavioural assertion, never with a setup typo.
- Test 6 fails as specified: the current loader ignores unknown top-level keys, so no
  `StorageError`/`InvalidCategoryError` is raised → `pytest.raises` fails. That is the correct
  Red signal (malformed persisted data is currently silently tolerated).
- Test 4 is a guard, not a Red test: `"strict"` is already absent for accounts without strict
  budgets, so it passes from the start. Keep it as the byte-identical-payload regression lock.

Run: `pytest tests/test_storage.py -q` and paste the failure summary into the PR body.

---

## TG-2 — Red: CLI behaviour

Add to `tests/test_cli.py`, reusing its existing fixtures/helpers for
`POCKETBUDGET_DATA_FILE` isolation and its subprocess invocation style:

1. **Strict blocks across invocations** — `set-budget Food 100 --strict` (exit 0, same success
   message), then a **separate** `add-expense 200 Food` → exit 1, stderr contains
   `would exceed the strict budget`, stdout empty.
2. **State untouched on rejection** — capture the data-file bytes before the rejected
   `add-expense` and assert they are identical afterwards.
3. **Revert to non-strict** — after `--strict`, re-issue `set-budget Food 100` and assert a
   subsequent over-limit expense exits 0 with `Budget limit exceeded for Food.`
4. **Usage errors** — `set-budget Food`, `set-budget Food 100 --strict extra`,
   `set-budget --strict Food 100`, `set-budget Food 100 --STRICT`: each exits 1, prints
   `Usage: pocketbudget set-budget <category> <limit> [--strict]` on stderr, and leaves any
   existing data file unchanged.
5. **Non-strict regression** — unchanged path: over-limit expense exits 0, prints both lines,
   and `show-summary` shows `(OVER)`.

Allowed non-behavioural edit: the contract block in the `tests/test_cli.py` module docstring
(line 27) may be extended to show `[--strict]`. No existing assertion may change (AC-11).

**Red evidence:** tests 1–3 fail because the current CLI rejects `--strict` as a usage error
(exit 1 with the usage message) — 1–3 are behavioural Red. Tests 4–5 pass already (guards).
Run `pytest tests/test_cli.py -q` and record the expected-failure list.

---

## TG-3 — Green: domain read-only accessor

**File:** `pocketbudget/account.py` (≤ 4 added lines, no other edits).

Add, adjacent to the existing `budgets` property (`account.py:35–37`):

- `@property def strict_budgets(self) -> list[str]` returning a **sorted list copy** of
  `_strict_budgets` (requirements §8.3, D7, FR-9).

Constraints: no signature changes to `set_budget`/`add_expense`; no rename; no docstring style
invented beyond what neighbouring methods use; `mypy --strict` clean (the property must be
fully annotated).

**Verification:** `pytest tests/test_storage.py -q` — the identity/payload tests that depend on
the property may now progress; behavioural round-trip tests still Red for the right reason
(missing persistence).

---

## TG-4 — Green: persistence

**File:** `pocketbudget/storage.py` (≤ 16 added lines).

1. **`save`** (`storage.py:14–21`): after the existing `budgets` block, conditionally add
   `data["strict"] = account.strict_budgets` **only when** `account.strict_budgets` is
   non-empty. Do not touch the `history`/`budgets` construction.
2. **New private helper `_apply_strict_budgets(account, raw)`**, called from `load`
   immediately after `_apply_budgets` (`storage.py:44`):
   - absent key → return;
   - value must be a `list`, else `StorageError` with a message in the module's existing style
     (e.g. `"Save file contains an invalid strict entry."`);
   - every element must be `str`, else `StorageError`;
   - every element must already be a budget category (`account.budgets`), else `StorageError`;
   - apply with `account.set_budget(category, account.budgets[category], strict=True)` —
     **reuse the already-restored amount** rather than reading a second amount from the file,
     so the limit cannot be applied twice or diverge. Because `set_budget` runs the domain's
     category validation, unknown-but-budgeted categories still raise `InvalidCategoryError`
     from the domain (requirements §10).

Keep each function's mccabe complexity ≤ 7 (`ruff.toml`): the helper must use early returns,
mirroring `_apply_budgets` and `_amount`/`_category` style. No changes to `_account_from_history`
or to the history payload.

**Verification:** `pytest tests/test_storage.py -q` → all Green, including the omit-when-empty
guard and the exact-payload test, which must pass **unmodified**.

---

## TG-5 — Green: CLI surface

**File:** `pocketbudget/cli.py` (≤ 8 added lines).

In `_set_budget` (`cli.py:89–97`):
- replace the arity guard with one that accepts exactly `2` arguments, or `3` where the third
  is the literal `"--strict"`; everything else calls `_error` with
  `"Usage: pocketbudget set-budget <category> <limit> [--strict]"`;
- derive `strict` from the presence of the flag and pass it as the third argument to
  `account.set_budget(...)`;
- leave the success message byte-identical (`Budget of $<limit> set for <category>.`).

No changes to `_add_expense`, `_load`, `_save`, `_error`, `_COMMANDS`, or any other handler.
No new command entries. No `argparse`.

**Verification:** `pytest tests/test_cli.py -q` → all Green; `pytest -q` → full suite Green.

---

## TG-6 — Documentation (after behaviour exists)

**File:** `README.md` only (2–5 added lines).
- Extend the usage/commands section to show `python -m pocketbudget set-budget Food 100
  --strict` and one sentence on the blocking behaviour.
- Do **not** fix the pre-existing `python main.py` line (line 18) or the hedged test sentence
  (line 29) here; they are unrelated defects and out of scope (see "Deferred findings" below).
- Do **not** edit `rules.md`: §4 remains accurate for the default mode, and AC-12 requires it
  to stay untouched.

---

## TG-7 — Gate, sweeps closure, and reconciliation

1. `pytest -q` → all Green (expected ~90–94 tests: 82 existing + 8–12 new).
2. `ruff check .`; `ruff format --check .`; `mypy --strict pocketbudget tests`;
   `pre-commit run --all-files`.
3. **H1 sweep closure:** `grep -n "account\.\(add_income\|add_expense\|set_budget\|category_total\)" pocketbudget/cli.py`
   — confirm every domain parameter needed by each handler is supplied (only `set_budget`'s
   `strict` was dropped).
4. **H2 sweep closure:** re-run the state inventory —
   `grep -n "self\._[a-z_]* =" pocketbudget/account.py` versus the keys written in
   `storage.save`; confirm every mutable field is either persisted or derivable by replay. Note
   the result in `validation.md`.
5. **Diff budget check:** `git diff --stat main` — exactly three production files, within the
   line budget; no accidental edits to config, `rules.md`, or existing tests beyond added
   functions.
6. **Spec reconciliation:** walk `validation.md`'s AC table; if any acceptance criterion was
   implemented differently, stop and report to the user before editing the spec.

---

## Commit plan (conventional commits, matching repo history)

1. `test: cover strict budget persistence and CLI enforcement` — TG-1 + TG-2 (Red).
2. `feat: expose strict budgets in the CLI and persist them` — TG-3 + TG-4 + TG-5 (Green).
3. `docs: document the set-budget --strict flag` — TG-6.
4. Optionally amend commits 1–3 into the repository's usual granularity; do not squash into one
   `feat` commit, because the repo's history keeps test and feature commits separate.

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| `test_save_writes_account_state_to_file` exact-payload equality breaks | Medium | FR-9/AC-7: omit `"strict"` when empty; TG-4 step 1 makes this explicit |
| `mypy --strict` rejects the new property or `raw.get` narrowing | Medium | Annotate `-> list[str]`; use `isinstance` narrowing exactly as `_amount`/`_category` do |
| mccabe C901 complexity breach in `_apply_strict_budgets` | Medium | Early returns; single-purpose helper (mirrors `_apply_budgets`) |
| Flag parsing accidentally changes other commands' arity checks | Low | Only `_set_budget` is touched; TG-5 forbids edits elsewhere |
| Duplicate amount application on load (double-validating the limit) | Low | Reuse `account.budgets[category]`; never re-read a second amount from the file |
| Error message drift breaks CLI output contract | Low | Messages are owned by `Account`/`_error`; no rewording in this change |
| Legacy file misinterpreted as strict | Low | AC-6 + TG-1 test 5; absence is explicitly non-strict |
| Scope creep into README's unrelated defects | Medium | TG-6 limits edits to the new flag; deferred findings listed below |

## Deferred findings (explicitly out of scope)

- `README.md:18` instructs `python main.py`; the entry point is `python -m pocketbudget`.
- `README.md:29` hedged test wording ("If the project uses pytest").
- `rules.md` §2 self-contradiction (Shopping/Sports listed alongside the allowed set) and §3's
  truncated sentence.
- `tests/test_placeholder.py` is a no-op (`assert True`).
- Structural alternative to prevention: deriving the save payload from a single account
  accessor (`to_dict()`), which would make future lossy projections impossible. Deferred
  because it is a refactor.
