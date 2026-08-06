"""Storage: saving and loading application state."""

import json
from pathlib import Path

from pocketbudget.account import Account

STORAGE_PATH = Path("data/budget.json")


class StorageError(Exception):
    """Raised when a save file cannot be read as valid account state."""


def save(account: Account, path: str | Path = STORAGE_PATH) -> None:
    """Write the account's state to ``path``, creating the data folder if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"history": account.history}, indent=2))


def load(path: str | Path = STORAGE_PATH) -> Account:
    """Rebuild an Account from ``path``.

    A missing save file means a fresh start, so an empty Account is returned.
    A file that exists but is corrupted is reported as StorageError rather
    than silently producing a wrong balance.
    """
    path = Path(path)
    if not path.is_file():
        return Account()
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"Could not read save file {path}.") from exc
    if not isinstance(raw, dict):
        raise StorageError(f"Save file {path} does not describe an account.")
    history = raw.get("history")
    if not isinstance(history, list):
        raise StorageError(f"Save file {path} does not contain a valid history.")
    return _account_from_history(history)


def _account_from_history(history: list[object]) -> Account:
    """Replay a saved history through the same mutators live data uses."""
    account = Account()
    for entry in history:
        if not isinstance(entry, dict):
            raise StorageError("History contains an invalid entry.")
        entry_type = entry.get("type")
        if entry_type == "income":
            account.add_income(_amount(entry))
        elif entry_type == "expense":
            account.add_expense(_amount(entry), _category(entry))
        else:
            raise StorageError("History contains an unknown entry type.")
    return account


def _amount(entry: dict[str, object]) -> int:
    amount = entry.get("amount")
    if isinstance(amount, bool):
        raise StorageError("History entry has an invalid amount.")
    if not isinstance(amount, int):
        raise StorageError("History entry has an invalid amount.")
    return amount


def _category(entry: dict[str, object]) -> str:
    category = entry.get("category")
    if not isinstance(category, str):
        raise StorageError("History entry has an invalid category.")
    return category
