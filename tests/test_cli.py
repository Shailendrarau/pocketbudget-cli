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
    set-budget <category> <limit>     set a spending ceiling; prints
                                      "Budget of $<limit> set for <category>."
                                      The budget is saved and therefore
                                      persists for later commands.
    show-summary                      prints one line per category, e.g.
                                      "Food: $60 / $50", with "(OVER)" when
                                      the budget is exceeded or
                                      "(no budget)" when none was set.

Errors print to stderr and exit with a non-zero status without changing
the saved state.
"""

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
