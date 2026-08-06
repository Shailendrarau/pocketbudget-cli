"""Rule 4 — Category budget limits, matching rules.md.

rules.md §4: "The expense is recorded even if it exceeds the category budget.
The application displays a Budget limit exceeded warning. The category's total
expense is updated as normal."
"""

import pytest

from pocketbudget.account import Account
from pocketbudget.exceptions import InvalidCategoryError

# A spending limit can be set for a category


def test_spending_limit_can_be_set_for_a_category() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50)

    budget_exceeded = account.add_expense(60, "Food")

    assert budget_exceeded is True


def test_categories_without_a_limit_never_warn() -> None:
    account = Account()
    account.add_income(100)

    budget_exceeded = account.add_expense(60, "Food")

    assert budget_exceeded is False


# Recording an expense checks it against that category's remaining budget


def test_expense_within_remaining_budget_is_recorded_without_warning() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50)

    budget_exceeded = account.add_expense(30, "Food")

    assert budget_exceeded is False
    assert account.balance == 70
    assert account.category_total("Food") == 30


def test_expense_exactly_at_the_remaining_budget_is_recorded_without_warning() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50)

    budget_exceeded = account.add_expense(50, "Food")

    assert budget_exceeded is False
    assert account.balance == 50
    assert account.category_total("Food") == 50


def test_expense_over_remaining_budget_is_recorded_with_warning() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50)

    budget_exceeded = account.add_expense(60, "Food")

    assert budget_exceeded is True
    assert account.balance == 40
    assert account.category_total("Food") == 60


def test_remaining_budget_decreases_with_each_expense_in_the_category() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50)

    first = account.add_expense(30, "Food")
    second = account.add_expense(20, "Food")
    third = account.add_expense(10, "Food")

    assert first is False
    assert second is False
    assert third is True
    assert account.balance == 40
    assert account.category_total("Food") == 60


def test_remaining_budget_is_tracked_per_category() -> None:
    account = Account()
    account.add_income(200)
    account.set_budget("Food", 50)
    account.set_budget("Entertainment", 50)

    food_exceeded = account.add_expense(60, "Food")
    entertainment_within = account.add_expense(40, "Entertainment")

    assert food_exceeded is True
    assert entertainment_within is False
    assert account.balance == 100


# Budget limits are validated like every other input


@pytest.mark.parametrize("category", ["Shopping", "Sports"])
def test_set_budget_rejects_invalid_category(category: str) -> None:
    account = Account()
    with pytest.raises(InvalidCategoryError):
        account.set_budget(category, 50)


def test_set_budget_rejects_negative_amount() -> None:
    account = Account()
    with pytest.raises(ValueError):
        account.set_budget("Food", -10)


def test_zero_budget_means_any_expense_warns() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 0)

    budget_exceeded = account.add_expense(1, "Food")

    assert budget_exceeded is True
    assert account.balance == 99
    assert account.category_total("Food") == 1


# An over-budget expense is recorded, not blocked


def test_expense_over_budget_is_recorded_not_blocked() -> None:
    account = Account()
    account.add_income(100)
    account.set_budget("Food", 50)

    budget_exceeded = account.add_expense(60, "Food")

    assert budget_exceeded is True
    assert account.history == [
        {"type": "income", "amount": 100},
        {"type": "expense", "amount": 60, "category": "Food"},
    ]
