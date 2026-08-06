"""Source of truth for the Account balance and the rules in rules.md."""

import pytest

from pocketbudget.account import Account, format_amount
from pocketbudget.exceptions import InsufficientBalanceError, InvalidCategoryError

# Rule 1 — Currency symbol


def test_amounts_are_formatted_with_dollar_symbol() -> None:
    assert format_amount(55) == "$55"


# Balance is readable but never assignable from outside


def test_balance_starts_at_zero() -> None:
    assert Account().balance == 0


def test_balance_is_readable_after_transactions() -> None:
    account = Account()
    account.add_income(100)
    account.add_expense(30, "Food")
    assert account.balance == 70


def test_balance_cannot_be_assigned_from_outside() -> None:
    account = Account()
    account.add_income(100)
    with pytest.raises(AttributeError):
        setattr(account, "balance", 500)
    assert account.balance == 100


# add_income and add_expense are the only mutators


def test_add_income_increases_balance() -> None:
    account = Account()
    account.add_income(50)
    assert account.balance == 50


def test_add_expense_decreases_balance() -> None:
    account = Account()
    account.add_income(50)
    account.add_expense(20, "Food")
    assert account.balance == 30


# Every transaction is validated before it touches the balance


def test_negative_income_is_rejected() -> None:
    account = Account()
    with pytest.raises(ValueError):
        account.add_income(-5)
    assert account.balance == 0


def test_negative_expense_is_rejected() -> None:
    account = Account()
    account.add_income(50)
    with pytest.raises(ValueError):
        account.add_expense(-5, "Food")
    assert account.balance == 50


# Rule 2 — Allowed categories


@pytest.mark.parametrize("category", ["Food", "Transport", "Entertainment"])
def test_allowed_categories_are_accepted(category: str) -> None:
    account = Account()
    account.add_income(50)
    account.add_expense(10, category)
    assert account.balance == 40


@pytest.mark.parametrize("category", ["Shopping", "Sports"])
def test_disallowed_category_is_rejected(category: str) -> None:
    account = Account()
    account.add_income(50)
    with pytest.raises(InvalidCategoryError):
        account.add_expense(10, category)
    assert account.balance == 50


# Rule 3 — Overspending the total balance


def test_expense_equal_to_balance_is_allowed() -> None:
    account = Account()
    account.add_income(100)
    account.add_expense(100, "Food")
    assert account.balance == 0


def test_expense_larger_than_balance_is_rejected() -> None:
    account = Account()
    account.add_income(100)
    with pytest.raises(InsufficientBalanceError):
        account.add_expense(101, "Food")


def test_rejected_overdraw_leaves_balance_and_totals_unchanged() -> None:
    account = Account()
    account.add_income(100)
    with pytest.raises(InsufficientBalanceError):
        account.add_expense(200, "Food")
    assert account.balance == 100
    assert account.category_total("Food") == 0


# Rule 4 — Budget limits


def test_expense_within_budget_is_recorded_without_warning() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50)
    budget_exceeded = account.add_expense(30, "Food")
    assert budget_exceeded is False
    assert account.balance == 70
    assert account.category_total("Food") == 30


def test_expense_over_budget_is_recorded_with_warning() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50)
    budget_exceeded = account.add_expense(60, "Food")
    assert budget_exceeded is True
    assert account.balance == 40
    assert account.category_total("Food") == 60
