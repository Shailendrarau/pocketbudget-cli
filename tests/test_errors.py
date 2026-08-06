"""Domain error handling: bad input raises the right custom exception,
and validation happens before any state changes."""

import json
from pathlib import Path

import pytest

from pocketbudget.account import Account
from pocketbudget.exceptions import (
    BudgetLimitExceededError,
    InvalidAmountError,
    StorageError,
)
from pocketbudget.storage import load

# A negative transaction amount is rejected with InvalidAmountError


def test_negative_income_raises_invalid_amount_error() -> None:
    with pytest.raises(InvalidAmountError):
        Account().add_income(-1)


def test_negative_expense_raises_invalid_amount_error() -> None:
    with pytest.raises(InvalidAmountError):
        Account().add_expense(-1, "Food")


def test_negative_budget_raises_invalid_amount_error() -> None:
    with pytest.raises(InvalidAmountError):
        Account().set_budget("Food", -1)


def test_negative_amount_is_rejected_before_state_changes() -> None:
    account = Account()
    account.add_income(50)

    with pytest.raises(InvalidAmountError):
        account.add_expense(-10, "Food")

    assert account.balance == 50
    assert account.history == [{"type": "income", "amount": 50}]
    assert account.category_total("Food") == 0


# An expense that blows past a strict budget is rejected with
# BudgetLimitExceededError, before any state changes


def test_expense_over_strict_budget_raises_budget_limit_exceeded_error() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50, strict=True)

    with pytest.raises(BudgetLimitExceededError):
        account.add_expense(60, "Food")


def test_expense_over_strict_budget_leaves_state_unchanged() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50, strict=True)

    with pytest.raises(BudgetLimitExceededError):
        account.add_expense(60, "Food")

    assert account.balance == 100
    assert account.category_total("Food") == 0
    assert account.history == [{"type": "income", "amount": 100}]


def test_strict_budget_blocks_an_expense_that_crosses_the_limit() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50, strict=True)

    assert account.add_expense(40, "Food") is False
    with pytest.raises(BudgetLimitExceededError):
        account.add_expense(20, "Food")

    assert account.balance == 60
    assert account.category_total("Food") == 40


def test_expense_up_to_strict_budget_is_allowed() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50, strict=True)

    budget_exceeded = account.add_expense(50, "Food")

    assert budget_exceeded is False
    assert account.balance == 50
    assert account.category_total("Food") == 50


def test_non_strict_budget_still_warns_instead_of_raising() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50)

    budget_exceeded = account.add_expense(60, "Food")

    assert budget_exceeded is True
    assert account.balance == 40


# A corrupted data file is reported as StorageError, never a wrong balance


def test_corrupted_json_file_raises_storage_error(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text("{this is not json")

    with pytest.raises(StorageError):
        load(path)


def test_non_object_save_file_raises_storage_error(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(json.dumps([1, 2, 3]))

    with pytest.raises(StorageError):
        load(path)


def test_save_file_without_history_raises_storage_error(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(json.dumps({"balance": 100}))

    with pytest.raises(StorageError):
        load(path)
