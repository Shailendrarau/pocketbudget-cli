"""Domain: budgeting rules and protected account state."""

from copy import deepcopy

from pocketbudget.exceptions import InsufficientBalanceError, InvalidCategoryError

ALLOWED_CATEGORIES = ("Food", "Transport", "Entertainment")


def format_amount(amount: int) -> str:
    return f"${amount}"


class Account:
    def __init__(self) -> None:
        self._balance = 0
        self._history: list[dict[str, object]] = []
        self._category_totals: dict[str, int] = {}
        self._budgets: dict[str, int] = {}

    @property
    def balance(self) -> int:
        return self._balance

    @property
    def history(self) -> list[dict[str, object]]:
        return deepcopy(self._history)

    def add_income(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("Income amount cannot be negative.")
        self._balance += amount
        self._history.append({"type": "income", "amount": amount})

    def add_expense(self, amount: int, category: str) -> bool:
        if amount < 0:
            raise ValueError("Expense amount cannot be negative.")
        if category not in ALLOWED_CATEGORIES:
            raise InvalidCategoryError(category)
        if amount > self._balance:
            raise InsufficientBalanceError(
                f"Expense of {format_amount(amount)} exceeds the balance of "
                f"{format_amount(self._balance)}."
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

    def set_budget(self, category: str, amount: int) -> None:
        self._budgets[category] = amount

    def category_total(self, category: str) -> int:
        return self._category_totals.get(category, 0)
