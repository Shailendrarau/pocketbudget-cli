# PocketBudget

PocketBudget is a command-line budgeting tool that tracks income and expenses across a fixed set of categories (Food, Transport, Entertainment), lets you set per-category budgets, and reports warnings when a category's spending exceeds its budget. All state is persisted to a JSON file, so your balance and transaction history survive between runs.

## Installation & Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pre-commit install
```

The save file is created automatically at `data/budget.json` the first time you run a command. Set the `POCKETBUDGET_DATA_FILE` environment variable to use a different location.

## Usage

```bash
# Add income
python -m pocketbudget add-income 1000 Salary

# Record an expense
python -m pocketbudget add-expense 25 Food

# Set a category budget
python -m pocketbudget set-budget Food 300

# View the current balance
python -m pocketbudget show-balance

# View the full transaction history
python -m pocketbudget show-history

# View a per-category spending summary (marks OVER when a budget is exceeded)
python -m pocketbudget show-summary
```

Amounts are whole dollars. Expenses use only the allowed categories (`Food`, `Transport`, `Entertainment`); anything else is rejected with an error, as is any expense larger than the current balance.

## Running the Tests

```bash
python -m pytest
```

A passing run finishes with all tests green, e.g. `82 passed in 4.21s`. You can also run the full quality gate used by pre-commit:

```bash
ruff check . && ruff format --check . && mypy --strict pocketbudget
```

## Design Decisions

**How the balance stays protected.** `Account` keeps its balance in a private `_balance` attribute exposed only through a read-only `balance` property (`account.py:28`). Nothing outside the class can assign to it, and the only ways to change it are the `add_income` and `add_expense` mutators, which enforce the domain rules (no negative amounts, no spending more than the balance, valid categories) before touching the value.

**How the history is protected from mutation.** The `history` property returns a `deepcopy` of the internal `_history` list (`account.py:33`), so callers receive a snapshot and any edits they make to it are discarded. The same copies are handed to `storage.save`, which serializes the snapshot without ever exposing a reference to the live list.

**Why these calls.** Keeping the state private and exposing only explicit mutators concentrates every business rule in one place, so an expense can never bypass category, balance, or budget checks by writing directly to the account. This also lets `storage.load` rebuild state by replaying the saved history through the same mutators live data uses, guaranteeing that a freshly loaded account is subject to the exact same invariants.
