"""CLI: user input and command routing.

Every command follows the same lifecycle: load the saved state from the
storage file, run the domain operation, then save the result back to the
storage file.
"""

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

from pocketbudget import storage
from pocketbudget.account import Account, format_amount
from pocketbudget.exceptions import (
    BudgetLimitExceededError,
    InsufficientBalanceError,
    InvalidCategoryError,
)

DATA_FILE_ENV = "POCKETBUDGET_DATA_FILE"


def main(argv: list[str] | None = None) -> None:
    """Run the CLI, optionally with an explicit argument list."""
    args = sys.argv[1:] if argv is None else argv
    try:
        _run(args)
    except (
        ValueError,
        BudgetLimitExceededError,
        InvalidCategoryError,
        InsufficientBalanceError,
        storage.StorageError,
    ) as exc:
        _error(str(exc))


def _run(args: list[str]) -> None:
    if not args:
        _error("Usage: pocketbudget <command> [args]")
    command, rest = args[0], args[1:]
    handler = _COMMANDS.get(command)
    if handler is None:
        _error(f"Unknown command: {command}")
    handler(rest)


def _data_file() -> Path:
    override = os.environ.get(DATA_FILE_ENV)
    return Path(override) if override else storage.STORAGE_PATH


def _add_income(args: list[str]) -> None:
    amount, category = _parse_amount_and_category(args, "add-income")
    account = _load()
    account.add_income(amount, category)
    _save(account)
    print(f"Income of {format_amount(amount)} recorded.")


def _add_expense(args: list[str]) -> None:
    amount, category = _parse_amount_and_category(args, "add-expense")
    account = _load()
    budget_exceeded = account.add_expense(amount, category)
    _save(account)
    print(f"Expense of {format_amount(amount)} recorded.")
    if budget_exceeded:
        print(f"Budget limit exceeded for {category}.")


def _show_balance(args: list[str]) -> None:
    _expect_no_args(args, "show-balance")
    account = _load()
    print(f"Balance: {format_amount(account.balance)}")


def _show_history(args: list[str]) -> None:
    _expect_no_args(args, "show-history")
    account = _load()
    if not account.history:
        print("No transactions recorded.")
        return
    for entry in account.history:
        print(_format_history_entry(entry))


def _set_budget(args: list[str]) -> None:
    if len(args) != 2:
        _error("Usage: pocketbudget set-budget <category> <limit>")
    category = args[0]
    amount = _parse_amount(args[1])
    account = _load()
    account.set_budget(category, amount)
    _save(account)
    print(f"Budget of {format_amount(amount)} set for {category}.")


def _show_summary(args: list[str]) -> None:
    _expect_no_args(args, "show-summary")
    account = _load()
    for category in sorted(_summary_categories(account)):
        spent = account.category_total(category)
        budget = account.budgets.get(category)
        if budget is None:
            print(f"{category}: {format_amount(spent)} (no budget)")
        elif spent > budget:
            print(
                f"{category}: {format_amount(spent)} / {format_amount(budget)} (OVER)"
            )
        else:
            print(f"{category}: {format_amount(spent)} / {format_amount(budget)}")


def _load() -> Account:
    return storage.load(_data_file())


def _save(account: Account) -> None:
    storage.save(account, _data_file())


def _parse_amount_and_category(args: list[str], command: str) -> tuple[int, str]:
    if len(args) != 2:
        _error(f"Usage: pocketbudget {command} <amount> <category>")
    return _parse_amount(args[0]), args[1]


def _parse_amount(raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        _error(f"Invalid amount: {raw}")


def _expect_no_args(args: list[str], command: str) -> None:
    if args:
        _error(f"Usage: pocketbudget {command} takes no arguments")


def _summary_categories(account: Account) -> set[str]:
    categories = set(account.budgets)
    for entry in account.history:
        if entry.get("type") == "expense":
            category = entry.get("category")
            if isinstance(category, str):
                categories.add(category)
    return categories


def _format_history_entry(entry: dict[str, object]) -> str:
    entry_type = entry.get("type")
    amount = entry.get("amount")
    if entry_type == "income" and isinstance(amount, int):
        line = f"income +{format_amount(amount)}"
    elif entry_type == "expense" and isinstance(amount, int):
        line = f"expense -{format_amount(amount)}"
    else:
        return ""
    category = entry.get("category")
    if isinstance(category, str) and category:
        return f"{line} {category}"
    return line


def _error(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(1)


_COMMANDS: dict[str, Callable[[list[str]], None]] = {
    "add-income": _add_income,
    "add-expense": _add_expense,
    "show-balance": _show_balance,
    "show-history": _show_history,
    "set-budget": _set_budget,
    "show-summary": _show_summary,
}
