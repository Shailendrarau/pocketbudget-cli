# Validation — Strict budgets: expose and persist

**Spec:** `SPECS/strict-budget/requirements.md`
**Plan:** `SPECS/strict-budget/plan.md`
**Branch:** `fix/strict-budget`
**Rule:** a criterion is verified by *running* something and recording the outcome. "Looks
correct" is not evidence. Do not mark an AC verified by reading the diff alone.

Run everything from the repository root with the virtualenv active
(`pip install -r requirements.txt` once).

---

## 1. Preconditions

| Check | Command | Expected |
|---|---|---|
| Work is on the feature branch | `git rev-parse --abbrev-ref HEAD` | `fix/strict-budget` |
| Base is the repo default branch | `git merge-base --is-ancestor main HEAD && echo ok` | `ok` |
| Baseline still green before new tests | `pytest -q` (on the base commit) | 82 passed |
| Data file is not the user's | `echo "$POCKETBUDGET_DATA_FILE"` in every CLI check | a `/tmp` path, never `data/budget.json` |

CLI verification MUST use `POCKETBUDGET_DATA_FILE=<tmp>` so the working tree's
`data/budget.json` (git-ignored) is never touched.

---

## 2. Acceptance-criteria verification

### AC-1 — Default behaviour unchanged
1. `pytest -q` → all tests pass, including the pre-existing ones **unmodified**
   (`git diff main -- tests/ | grep -E '^-[^-]'` returns nothing: no existing test line was
   deleted or changed).
2. CLI: `add-income 500 Food`, `set-budget Food 100`, `add-expense 120 Food`,
   `add-expense 30 Food`, `show-summary`
   → messages byte-identical to today; `Food: $150 / $100 (OVER)`; each command exit 0.
3. Payload after those commands contains exactly `history` and `budgets` (no `strict` key).

### AC-2 — Strict mode reachable and durable across invocations
```bash
export POCKETBUDGET_DATA_FILE=/tmp/val-strict.json
python -m pocketbudget add-income 500 Food          # exit 0
python -m pocketbudget set-budget Food 100 --strict # exit 0, "Budget of $100 set for Food."
python -m pocketbudget add-expense 200 Food         # separate process
```
Expected: the third command exits **1**, stderr is
`Expense of $200 would exceed the strict budget of $100 for Food.`, stdout empty.
Also inspect the file: `"strict": ["Food"]` present alongside `"budgets"`.

### AC-3 — Rejection is all-or-nothing at the CLI
With a data file that already exists: copy it (`cp`), run the rejected `add-expense`, then
`cmp` the copy with the live file → **identical**. Stdout MUST be empty on the rejection path.
Separately, prove nothing is written on failure when no file exists yet: point
`POCKETBUDGET_DATA_FILE` at a fresh path, run `add-expense 10 Food` with a zero balance
(rejected by `InsufficientBalanceError`), and assert exit 1 leaves the path **absent**. (A
strict rejection always implies a previously saved budget, so the "absent file" case is
exercised through the insufficient-balance path; the invariant under test is "no save on
failure", which is shared by both.)

### AC-4 — Non-strict over-limit regression
```bash
export POCKETBUDGET_DATA_FILE=/tmp/val-nonstrict.json
python -m pocketbudget add-income 500 Food
python -m pocketbudget set-budget Food 100          # no flag
python -m pocketbudget add-expense 120 Food
python -m pocketbudget add-expense 30 Food
python -m pocketbudget show-summary
```
Expected: both expenses exit 0; each prints its record line; the second also prints
`Budget limit exceeded for Food.`; summary shows `Food: $150 / $100 (OVER)`.

### AC-5 — Reverting to non-strict
Continue from AC-2's file: `python -m pocketbudget set-budget Food 100` (no flag), then
`python -m pocketbudget add-expense 200 Food` → exit **0** with the warning, and the payload no
longer contains `"strict"` (assuming no other strict category exists).

### AC-6 — Legacy file compatibility
Create the file by hand (no `strict` key):
```bash
printf '%s' '{"history":[{"type":"income","amount":500}],"budgets":{"Food":100}}' \
  > /tmp/val-legacy.json
export POCKETBUDGET_DATA_FILE=/tmp/val-legacy.json
python -m pocketbudget add-expense 200 Food   # exit 0, warns: legacy == non-strict
python -m pocketbudget set-budget Food 100 --strict
python -m pocketbudget add-expense 200 Food   # exit 1: can be upgraded in place
```
No migration command, no error, no rewrite of history.

### AC-7 — Byte-identical payload when nothing is strict
`pytest tests/test_storage.py::test_save_writes_account_state_to_file -q` → passes
**unmodified** (the assertion compares the full payload dict). Also round-trip an account with
income/expenses only and diff the generated JSON against the format in requirements §8.2.

### AC-8 — Malformed persisted data
These are covered by TG-1 tests; verify they fail for the documented reason, not incidentally:
```bash
pytest tests/test_storage.py -q -k "strict"
```
| Payload `strict` value | Expected |
|---|---|
| `{}` / `"Food"` / `7` | `StorageError` |
| `[1]` / `[None]` / `[["Food"]]` | `StorageError` |
| `["Food"]` with no `Food` in `budgets` | `StorageError` |
| duplicates `["Food","Food"]` | loads; `strict_budgets == ["Food"]` |
| `[]` | loads; equivalent to absent |
| `null` (top-level) | treated as absent; loads non-strict |
| `["Shopping"]` with `budgets: {"Shopping": 50}` | `InvalidCategoryError` |
| `["Food"]` with `budgets: {"Food": 100}` | loads; still blocks after reload |

Error messages follow the module's existing phrasing and end with a period
(`storage.py:37–42`, `69`, `72`).

### AC-9 — CLI usage errors
| Invocation | Expected |
|---|---|
| `set-budget Food` | exit 1; usage on stderr; no state change |
| `set-budget Food 100 --strict extra` | exit 1; usage |
| `set-budget --strict Food 100` | exit 1; usage |
| `set-budget Food 100 --STRICT` | exit 1; usage |
| `set-budget Food abc` | exit 1; `Invalid amount: abc` (existing behaviour) |
| `set-budget Shopping 100 --strict` | exit 1; `InvalidCategoryError` message (existing behaviour) |

Usage line exactly: `Usage: pocketbudget set-budget <category> <limit> [--strict]`.
"No state change" is checked by byte-comparing the data file before/after.

### AC-10 — Tooling gate
```bash
pytest -q
ruff check .
ruff format --check .
mypy --strict pocketbudget tests
pre-commit run --all-files
```
All five must exit 0. Record the pytest total (expected 82 + new tests, ≈ 90–94).
`ruff format --check` must report every file formatted; if it reformats anything, the commit
must include the formatted result and the diff must not touch unrelated lines.

### AC-11 — Diff budget and scope discipline
```bash
git diff --stat main
git diff --numstat main -- pocketbudget/
```
- Production files changed: exactly `pocketbudget/account.py`, `pocketbudget/storage.py`,
  `pocketbudget/cli.py`.
- Added lines total ≤ 30; no deleted lines outside the `_set_budget` arity guard.
- `git diff main -- requirements.txt pytest.ini ruff.toml .pre-commit-config.yaml rules.md`
  → empty.
- Test files may only gain functions (plus imports if strictly needed), and the module-level
  contract block in `tests/test_cli.py` (line 27) may show `[--strict]`; no existing assertion
  may change.
- `SPECS/` is the only new directory.

### AC-12 — Documentation consistency
- `README.md` shows the `--strict` flag with a working example; the example's claimed output
  matches AC-2.
- `rules.md` is unmodified (`git diff main -- rules.md` empty) and its §4 statement remains
  literally true for the default mode.
- No document claims strictness appears in `show-summary`/`show-balance`/`show-history`.

---

## 3. Edge-case and failure-mode validation

| # | Case | Method | Expected |
|---|---|---|---|
| E1 | Expense exactly equals the strict limit | library call `add_expense(limit, cat)` | allowed (`>` comparison, `account.py:60`) |
| E2 | Expense one unit over the strict limit | library call | `BudgetLimitExceededError` |
| E3 | Strict + insufficient balance simultaneously | balance 50, strict budget 100, expense 80 | `InsufficientBalanceError` wins (balance checked before budget, `account.py:53–64`) — ordering preserved |
| E4 | Strict category has no budget entry in saved data | hand-written JSON | `StorageError` |
| E5 | `strict` key present but empty | hand-written JSON | loads; non-strict |
| E6 | Rejected expense does not corrupt history | compare `history` before/after rejected call | identical |
| E7 | `strict_budgets` snapshot is immutable | mutate returned list, re-read property | unchanged |
| E8 | Two strict categories, expense on one | CLI | only the targeted category blocks |
| E9 | Legacy file, then strict set, then unset | CLI sequence | key appears then disappears; other categories unaffected |
| E10 | Save path inside a missing directory, strict set | `tmp_path/"nested"/"budget.json"` | directory created (existing behaviour preserved) |

E1–E3, E6–E7, E10 are unit-level; E4–E5, E8–E9 may be CLI- or storage-level. All must be
covered by automated tests, not manual steps.

---

## 4. Bug-class closure (sweeps)

Run and record the output of each:

1. **H1 — adapter completeness**
   `grep -n "account\.\(add_income\|add_expense\|set_budget\|category_total\)" pocketbudget/cli.py`
   → every handler supplies all required domain parameters; `_set_budget` now supplies `strict`.
   Confirm `_add_income`'s deliberate omission of the optional `category=None` is still
   consistent with `tests/test_cli.py`'s documented contract (not a defect).
2. **H2 — state inventory**
   `grep -n "self\._[a-z_]* =" pocketbudget/account.py` versus the keys written by
   `storage.save` → each mutable field is persisted or derivable by history replay. After this
   change: `_balance` (replay), `_history` (persisted), `_category_totals` (replay),
   `_budgets` (persisted), `_strict_budgets` (persisted). **Zero unprojected fields remain.**
3. **Silence gap** — prove the new coverage is real:
   `pytest tests/test_storage.py -q -k strict` and
   `pytest tests/test_cli.py -q -k "strict or budget"` → non-empty selection, all pass. A
   `-k` selection that collects nothing is a failure of this validation step.

Attach the three outputs to the PR body under "Category closure".

---

## 5. Regression suite

| Suite | Command | Expected |
|---|---|---|
| Full tests | `pytest -q` | all pass; 82 pre-existing present and unmodified |
| Domain rules | `pytest tests/test_account.py tests/test_budgets.py tests/test_errors.py -q` | pass; strict domain tests (5) still pass |
| Storage | `pytest tests/test_storage.py -q` | pass, including exact-payload test |
| CLI E2E | `pytest tests/test_cli.py -q` | pass, including prior non-strict warnings |
| Entry point | `pytest tests/test_basic.py -q` | pass (still exits non-zero with usage when called bare) |

---

## 6. Manual verification (only what cannot be automated)

One recorded transcript, using a fresh `POCKETBUDGET_DATA_FILE` under `/tmp`:

1. `add-income 500 Food` → `Income of $500 recorded.`
2. `set-budget Food 100 --strict` → `Budget of $100 set for Food.`
3. `add-expense 40 Food` → `Expense of $40 recorded.`
4. `add-expense 70 Food` → rejected, exit 1, stderr as specified, file unchanged.
5. `set-budget Food 100` → success message unchanged.
6. `add-expense 70 Food` → `Expense of $70 recorded.` + `Budget limit exceeded for Food.`, exit 0.
7. `show-summary` → `Food: $110 / $100 (OVER)`.
8. `show-history` → three lines: income, expense 40, expense 70.
9. `set-budget Food 100 --strict --verbose` → usage error, exit 1.

Paste the transcript into the PR body. Steps 1–9 are the human-readable confirmation that the
automated suite matches real usage; they MUST NOT contradict the tests — a contradiction is a
spec-drift finding, not a "flaky manual check".

---

## 7. Definition of done

- [ ] All AC-1 … AC-12 verified with recorded evidence (command + output).
- [ ] Every edge case E1 … E10 covered by an automated test.
- [ ] Category closure outputs attached (§4); zero unprojected `Account` fields.
- [ ] `pytest`, `ruff check`, `ruff format --check`, `mypy --strict`, `pre-commit run --all-files`
      all pass on the final commit.
- [ ] Diff budget respected: 3 production files, ≤ 30 added lines, no unrelated edits.
- [ ] No new dependencies; `requirements.txt` unchanged.
- [ ] `README.md` updated only after behaviour exists; `rules.md` untouched.
- [ ] Existing tests unmodified; new tests are additive.
- [ ] `validation.md` reflects what was actually implemented — discrepancies reported to the
      user **before** editing `requirements.md` or this file.
- [ ] Commits follow the repo's conventional-commit style and are pushed to `fix/strict-budget`
      for review (not merged by the implementer).

---

## 8. Spec reconciliation protocol

After implementation, compare the code against `requirements.md` §7–§8 line by line:

1. If the implementation matches → tick the ACs and note the evidence commit SHA.
2. If behaviour differs but is defensible (e.g. a different `StorageError` wording) → record the
   difference, explain the impact, and **ask the user** before updating the spec.
3. If a requirement was not implemented → treat as a blocker; do not quietly delete the
   acceptance criterion.
4. If new behaviour appeared that the spec did not request → flag as scope drift; either revert
   it or get approval to extend the spec.

The specification is the agreement; the implementation does not get to redefine it unilaterally.
