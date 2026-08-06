"""Domain: budgeting rules and protected account state."""

from copy import deepcopy

from pocketbudget.exceptions import (
    BudgetLimitExceededError,
    InsufficientBalanceError,
    InvalidAmountError,
    InvalidCategoryError,
)

ALLOWED_CATEGORIES = ("Food", "Transport", "Entertainment")


def format_amount(amount: int) -> str:
    return f"${amount}"


class Account:
    def __init__(self) -> None:
        self._balance = 0
        self._history: list[dict[str, object]] = []
        self._category_totals: dict[str, int] = {}
        self._budgets: dict[str, int] = {}
        self._strict_budgets: set[str] = set()

    @property
    def balance(self) -> int:
        return self._balance

    @property
    def history(self) -> list[dict[str, object]]:
        return deepcopy(self._history)

    @property
    def budgets(self) -> dict[str, int]:
        return dict(self._budgets)

    def add_income(self, amount: int, category: str | None = None) -> None:
        if amount < 0:
            raise InvalidAmountError("Income amount cannot be negative.")
        self._balance += amount
        entry: dict[str, object] = {"type": "income", "amount": amount}
        if category is not None:
            entry["category"] = category
        self._history.append(entry)

    def add_expense(self, amount: int, category: str) -> bool:
        if amount < 0:
            raise InvalidAmountError("Expense amount cannot be negative.")
        if category not in ALLOWED_CATEGORIES:
            raise InvalidCategoryError(category)
        if amount > self._balance:
            raise InsufficientBalanceError(
                f"Expense of {format_amount(amount)} exceeds the balance of "
                f"{format_amount(self._balance)}."
            )
        if category in self._strict_budgets:
            limit = self._budgets[category]
            if self._category_totals.get(category, 0) + amount > limit:
                raise BudgetLimitExceededError(
                    f"Expense of {format_amount(amount)} would exceed the "
                    f"strict budget of {format_amount(limit)} for {category}."
                )
        self._balance -= amount
        self._category_totals[category] = (
            self._category_totals.get(category, 0) + amount
        )
        self._history.append(
            {"type": "expense", "amount": amount, "category": category}
        )
        budget = self._budgets.get(category)
        return budget is not None and self._category_totals[category] > budget

    def set_budget(self, category: str, amount: int, strict: bool = False) -> None:
        if category not in ALLOWED_CATEGORIES:
            raise InvalidCategoryError(category)
        if amount < 0:
            raise InvalidAmountError("Budget amount cannot be negative.")
        self._budgets[category] = amount
        if strict:
            self._strict_budgets.add(category)
        else:
            self._strict_budgets.discard(category)

    def category_total(self, category: str) -> int:
        return self._category_totals.get(category, 0)
