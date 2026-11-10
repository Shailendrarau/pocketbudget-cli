"""CLI: end-to-end behaviour of the pocketbudget command-line interface.

The application is invoked as ``python -m pocketbudget <command> [args]``.
Every command follows the same lifecycle:

1. load the saved state from the storage file,
2. run the domain operation,
3. save the result back to the storage file.

Tests isolate their state by pointing the CLI at a throwaway data file
through the ``POCKETBUDGET_DATA_FILE`` environment variable.

Contract:
    add-income <amount> <category>    record a deposit; prints
                                      "Income of $<amount> recorded."
    add-expense <amount> <category>   record an expense; prints
                                      "Expense of $<amount> recorded." and,
                                      when the category budget is exceeded, an
                                      extra "Budget limit exceeded for
                                      <category>." warning
    show-balance                      prints "Balance: $<amount>"
    show-history                      prints one line per transaction, in
                                      order: "income +$<amount> <category>"
                                      or "expense -$<amount> <category>";
                                      an empty account prints
                                      "No transactions recorded."
    set-budget <category> <limit> [--strict]
                                      set a spending ceiling; prints
                                      "Budget of $<limit> set for <category>."
                                      The budget is saved and therefore
                                      persists for later commands. With
                                      ``--strict``, an over-limit expense is
                                      rejected instead of being recorded with a
                                      warning.
    show-summary                      prints one line per category, e.g.
                                      "Food: $60 / $50", with "(OVER)" when
                                      the budget is exceeded or
                                      "(no budget)" when none was set.

Errors print to stderr and exit with a non-zero status without changing
the saved state.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DATA_FILE_ENV = "POCKETBUDGET_DATA_FILE"


def run_cli(data_file: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env[DATA_FILE_ENV] = str(data_file)
    return subprocess.run(
        [sys.executable, "-m", "pocketbudget", *args],
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture()
def data_file(tmp_path: Path) -> Path:
    return tmp_path / "budget.json"


# add-income <amount> <category> — records safe deposits


def test_add_income_records_a_deposit_and_reports_it(data_file: Path) -> None:
    result = run_cli(data_file, "add-income", "100", "Salary")

    assert result.returncode == 0
    assert "Income of $100 recorded." in result.stdout


def test_add_income_deposit_is_persisted_for_the_next_command(
    data_file: Path,
) -> None:
    run_cli(data_file, "add-income", "100", "Salary")

    balance = run_cli(data_file, "show-balance")

    assert "Balance: $100" in balance.stdout


def test_add_income_records_the_deposit_category_in_history(
    data_file: Path,
) -> None:
    run_cli(data_file, "add-income", "100", "Salary")

    history = run_cli(data_file, "show-history")

    assert "income +$100 Salary" in history.stdout


def test_add_income_rejects_a_negative_amount(data_file: Path) -> None:
    result = run_cli(data_file, "add-income", "-10", "Salary")

    assert result.returncode != 0
    assert result.stderr

    balance = run_cli(data_file, "show-balance")
    assert "Balance: $0" in balance.stdout


# add-expense <amount> <category> — records expenses against the balance


def test_add_expense_records_an_expense_and_reports_it(data_file: Path) -> None:
    run_cli(data_file, "add-income", "200", "Salary")

    result = run_cli(data_file, "add-expense", "50", "Food")

    assert result.returncode == 0
    assert "Expense of $50 recorded." in result.stdout

    balance = run_cli(data_file, "show-balance")
    assert "Balance: $150" in balance.stdout


def test_add_expense_records_the_category_in_history(data_file: Path) -> None:
    run_cli(data_file, "add-income", "200", "Salary")
    run_cli(data_file, "add-expense", "50", "Food")

    history = run_cli(data_file, "show-history")

    assert "expense -$50 Food" in history.stdout


def test_add_expense_rejects_an_unknown_category(data_file: Path) -> None:
    run_cli(data_file, "add-income", "200", "Salary")

    result = run_cli(data_file, "add-expense", "10", "Shopping")

    assert result.returncode != 0
    assert result.stderr


def test_add_expense_larger_than_balance_is_rejected(data_file: Path) -> None:
    run_cli(data_file, "add-income", "50", "Salary")

    result = run_cli(data_file, "add-expense", "60", "Food")

    assert result.returncode != 0

    balance = run_cli(data_file, "show-balance")
    assert "Balance: $50" in balance.stdout


# add-expense <amount> <category> — validates against category budgets


def test_add_expense_within_budget_does_not_warn(data_file: Path) -> None:
    run_cli(data_file, "add-income", "100", "Salary")
    run_cli(data_file, "set-budget", "Food", "50")

    result = run_cli(data_file, "add-expense", "30", "Food")

    assert result.returncode == 0
    assert "Expense of $30 recorded." in result.stdout
    assert "Budget limit exceeded" not in result.stdout


def test_add_expense_over_budget_prints_a_warning(data_file: Path) -> None:
    run_cli(data_file, "add-income", "100", "Salary")
    run_cli(data_file, "set-budget", "Food", "50")

    result = run_cli(data_file, "add-expense", "60", "Food")

    assert result.returncode == 0
    assert "Budget limit exceeded for Food." in result.stdout


# show-balance — prints the current safe balance


def test_show_balance_prints_zero_for_a_fresh_account(data_file: Path) -> None:
    result = run_cli(data_file, "show-balance")

    assert result.returncode == 0
    assert "Balance: $0" in result.stdout


def test_show_balance_prints_the_accumulated_balance(data_file: Path) -> None:
    run_cli(data_file, "add-income", "500", "Salary")
    run_cli(data_file, "add-expense", "120", "Food")
    run_cli(data_file, "add-expense", "80", "Transport")

    result = run_cli(data_file, "show-balance")

    assert result.returncode == 0
    assert "Balance: $300" in result.stdout


# show-history — displays all executed transactions


def test_show_history_is_empty_for_a_fresh_account(data_file: Path) -> None:
    result = run_cli(data_file, "show-history")

    assert result.returncode == 0
    assert "No transactions recorded." in result.stdout


def test_show_history_lists_transactions_in_order(data_file: Path) -> None:
    run_cli(data_file, "add-income", "100", "Salary")
    run_cli(data_file, "add-expense", "30", "Food")
    run_cli(data_file, "add-expense", "20", "Entertainment")

    result = run_cli(data_file, "show-history")

    assert result.returncode == 0
    assert "income +$100 Salary" in result.stdout
    assert "expense -$30 Food" in result.stdout
    assert "expense -$20 Entertainment" in result.stdout
    order = [
        result.stdout.index(line)
        for line in (
            "income +$100 Salary",
            "expense -$30 Food",
            "expense -$20 Entertainment",
        )
    ]
    assert order == sorted(order)


# set-budget <category> <limit> — sets a spending ceiling


def test_set_budget_reports_the_new_limit(data_file: Path) -> None:
    result = run_cli(data_file, "set-budget", "Food", "50")

    assert result.returncode == 0
    assert "Budget of $50 set for Food." in result.stdout


def test_set_budget_rejects_an_unknown_category(data_file: Path) -> None:
    result = run_cli(data_file, "set-budget", "Shopping", "50")

    assert result.returncode != 0
    assert result.stderr


def test_set_budget_rejects_a_negative_limit(data_file: Path) -> None:
    result = run_cli(data_file, "set-budget", "Food", "-10")

    assert result.returncode != 0
    assert result.stderr


# show-summary — visualizes spending against established budgets


def test_show_summary_reports_spending_without_a_budget(data_file: Path) -> None:
    run_cli(data_file, "add-income", "100", "Salary")
    run_cli(data_file, "add-expense", "60", "Food")

    result = run_cli(data_file, "show-summary")

    assert result.returncode == 0
    assert "Food: $60 (no budget)" in result.stdout


def test_show_summary_reports_spending_against_the_budget(data_file: Path) -> None:
    run_cli(data_file, "add-income", "200", "Salary")
    run_cli(data_file, "set-budget", "Food", "50")
    run_cli(data_file, "add-expense", "30", "Food")

    result = run_cli(data_file, "show-summary")

    assert "Food: $30 / $50" in result.stdout


def test_show_summary_marks_over_budget_categories(data_file: Path) -> None:
    run_cli(data_file, "add-income", "200", "Salary")
    run_cli(data_file, "set-budget", "Food", "50")
    run_cli(data_file, "add-expense", "60", "Food")

    result = run_cli(data_file, "show-summary")

    assert result.returncode == 0
    assert "Food: $60 / $50 (OVER)" in result.stdout


# Lifecycle — loading, running, saving; failures leave state untouched


def test_each_command_reloads_the_saved_state(data_file: Path) -> None:
    run_cli(data_file, "add-income", "100", "Salary")
    run_cli(data_file, "add-expense", "40", "Food")
    run_cli(data_file, "add-income", "50", "Salary")

    history = run_cli(data_file, "show-history")
    balance = run_cli(data_file, "show-balance")

    assert "expense -$40 Food" in history.stdout
    assert "Balance: $110" in balance.stdout


def test_unknown_command_exits_non_zero_with_an_error(data_file: Path) -> None:
    result = run_cli(data_file, "buy-crypto")

    assert result.returncode != 0
    assert result.stderr


def test_missing_arguments_exit_non_zero_with_an_error(data_file: Path) -> None:
    result = run_cli(data_file, "add-income", "100")

    assert result.returncode != 0
    assert result.stderr


def test_no_command_exits_non_zero_with_an_error(data_file: Path) -> None:
    result = run_cli(data_file)

    assert result.returncode != 0
    assert result.stderr


def test_failed_operation_does_not_change_the_saved_state(
    data_file: Path,
) -> None:
    run_cli(data_file, "add-income", "100", "Salary")
    run_cli(data_file, "add-expense", "200", "Food")

    balance = run_cli(data_file, "show-balance")
    history = run_cli(data_file, "show-history")

    assert "Balance: $100" in balance.stdout
    assert "expense -$200 Food" not in history.stdout


# set-budget <category> <limit> [--strict] — strict mode blocks overspending


def test_strict_budget_blocks_an_expense_in_a_later_invocation(
    data_file: Path,
) -> None:
    income = run_cli(data_file, "add-income", "500", "Salary")
    budget = run_cli(data_file, "set-budget", "Food", "100", "--strict")

    result = run_cli(data_file, "add-expense", "200", "Food")

    assert income.returncode == 0
    assert budget.returncode == 0
    assert budget.stdout == "Budget of $100 set for Food.\n"
    assert result.returncode == 1
    assert result.stdout == ""
    assert (
        "Expense of $200 would exceed the strict budget of $100 for Food."
        in result.stderr
    )


def test_strict_budget_rejection_leaves_the_data_file_unchanged(
    data_file: Path,
) -> None:
    run_cli(data_file, "add-income", "500", "Salary")
    run_cli(data_file, "set-budget", "Food", "100", "--strict")
    before = data_file.read_bytes()

    result = run_cli(data_file, "add-expense", "200", "Food")

    assert result.returncode == 1
    assert data_file.read_bytes() == before


def test_strict_budget_is_persisted_in_the_save_file(data_file: Path) -> None:
    run_cli(data_file, "add-income", "500", "Salary")
    run_cli(data_file, "set-budget", "Food", "100", "--strict")

    data = json.loads(data_file.read_text())

    assert data["strict"] == ["Food"]


def test_strict_budget_only_blocks_the_marked_categories(data_file: Path) -> None:
    run_cli(data_file, "add-income", "500", "Salary")
    run_cli(data_file, "set-budget", "Food", "100", "--strict")
    run_cli(data_file, "set-budget", "Transport", "100", "--strict")

    blocked = run_cli(data_file, "add-expense", "150", "Transport")
    allowed = run_cli(data_file, "add-expense", "50", "Food")

    assert blocked.returncode == 1
    assert allowed.returncode == 0
    assert "Expense of $50 recorded." in allowed.stdout


def test_set_budget_without_the_flag_reverts_to_non_strict(data_file: Path) -> None:
    run_cli(data_file, "add-income", "500", "Salary")
    run_cli(data_file, "set-budget", "Food", "100", "--strict")
    run_cli(data_file, "set-budget", "Food", "100")

    result = run_cli(data_file, "add-expense", "200", "Food")

    assert result.returncode == 0
    assert "Expense of $200 recorded." in result.stdout
    assert "Budget limit exceeded for Food." in result.stdout
    assert "strict" not in json.loads(data_file.read_text())


def test_non_strict_budget_still_warns_and_persists(data_file: Path) -> None:
    run_cli(data_file, "add-income", "500", "Salary")
    run_cli(data_file, "set-budget", "Food", "100")

    result = run_cli(data_file, "add-expense", "120", "Food")
    summary = run_cli(data_file, "show-summary")

    assert result.returncode == 0
    assert "Expense of $120 recorded." in result.stdout
    assert "Budget limit exceeded for Food." in result.stdout
    assert "Food: $120 / $100 (OVER)" in summary.stdout


def test_legacy_file_can_become_strict_through_the_cli(data_file: Path) -> None:
    data_file.write_text(
        json.dumps(
            {
                "history": [{"type": "income", "amount": 500}],
                "budgets": {"Food": 100},
            }
        )
    )

    legacy = run_cli(data_file, "add-expense", "200", "Food")
    run_cli(data_file, "set-budget", "Food", "100", "--strict")
    upgraded = run_cli(data_file, "add-expense", "200", "Food")

    assert legacy.returncode == 0
    assert "Budget limit exceeded for Food." in legacy.stdout
    assert upgraded.returncode == 1
    assert "would exceed the strict budget" in upgraded.stderr


@pytest.mark.parametrize(
    "args",
    [
        ("set-budget", "Food"),
        ("set-budget", "Food", "100", "--strict", "extra"),
        ("set-budget", "--strict", "Food", "100"),
        ("set-budget", "Food", "100", "--STRICT"),
    ],
)
def test_set_budget_rejects_invalid_flag_shapes(
    data_file: Path, args: tuple[str, ...]
) -> None:
    run_cli(data_file, "add-income", "100", "Salary")
    before = data_file.read_bytes()

    result = run_cli(data_file, *args)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == (
        "Usage: pocketbudget set-budget <category> <limit> [--strict]"
    )
    assert data_file.read_bytes() == before


def test_set_budget_rejects_a_non_numeric_limit_with_the_flag(
    data_file: Path,
) -> None:
    result = run_cli(data_file, "set-budget", "Food", "abc", "--strict")

    assert result.returncode == 1
    assert "Invalid amount: abc" in result.stderr
    assert not data_file.exists()


def test_set_budget_rejects_an_unknown_category_with_the_flag(
    data_file: Path,
) -> None:
    result = run_cli(data_file, "set-budget", "Shopping", "100", "--strict")

    assert result.returncode == 1
    assert result.stderr
    assert not data_file.exists()


def test_failed_expense_does_not_create_a_data_file(data_file: Path) -> None:
    result = run_cli(data_file, "add-expense", "10", "Food")

    assert result.returncode == 1
    assert not data_file.exists()
