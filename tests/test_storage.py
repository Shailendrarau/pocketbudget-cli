"""Storage: saving and loading account state to the data folder."""

import json
from pathlib import Path

import pytest

from pocketbudget.account import Account
from pocketbudget.exceptions import InsufficientBalanceError, InvalidCategoryError
from pocketbudget.storage import STORAGE_PATH, StorageError, load, save


def _used_account() -> Account:
    account = Account()
    account.add_income(100)
    account.add_expense(30, "Food")
    account.add_expense(20, "Transport")
    return account


# Saving writes the account's state to a file in the dedicated data folder


def test_default_storage_path_is_the_dedicated_data_folder() -> None:
    assert STORAGE_PATH == Path("data/budget.json")


def test_save_writes_account_state_to_file(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    save(_used_account(), path)

    assert path.is_file()
    data = json.loads(path.read_text())
    assert data == {
        "history": [
            {"type": "income", "amount": 100},
            {"type": "expense", "amount": 30, "category": "Food"},
            {"type": "expense", "amount": 20, "category": "Transport"},
        ]
    }


def test_save_creates_the_data_folder_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "data" / "budget.json"
    save(_used_account(), path)

    assert path.is_file()


# Loading rebuilds an Account whose balance and history match what was saved


def test_load_rebuilds_account_with_saved_balance_and_history(tmp_path: Path) -> None:
    account = _used_account()
    path = tmp_path / "budget.json"
    save(account, path)

    loaded = load(path)

    assert loaded.balance == account.balance
    assert loaded.history == account.history


def test_loaded_account_is_a_usable_account(tmp_path: Path) -> None:
    account = _used_account()
    path = tmp_path / "budget.json"
    save(account, path)

    loaded = load(path)
    loaded.add_income(10)

    assert loaded.balance == account.balance + 10


# If the save file does not exist, the app starts with a clean empty account


def test_load_with_missing_file_returns_clean_empty_account(tmp_path: Path) -> None:
    path = tmp_path / "does-not-exist" / "budget.json"

    account = load(path)

    assert account.balance == 0
    assert account.history == []


# If the file exists but is corrupted, loading reports it instead of crashing
# or silently returning a wrong balance


def test_load_raises_storage_error_for_corrupted_file(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text("{this is not json")

    with pytest.raises(StorageError):
        load(path)


def test_load_raises_storage_error_for_non_object_json(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(json.dumps([1, 2, 3]))

    with pytest.raises(StorageError):
        load(path)


def test_load_does_not_silently_produce_a_wrong_balance(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(json.dumps({"balance": 9999}))

    with pytest.raises(StorageError):
        load(path)


# Loaded data passes through the same validation as live data


def test_loaded_data_rejects_invalid_category_like_live_data(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(
        json.dumps(
            {
                "history": [
                    {"type": "income", "amount": 50},
                    {"type": "expense", "amount": 20, "category": "Shopping"},
                ]
            }
        )
    )

    with pytest.raises(InvalidCategoryError):
        load(path)


def test_loaded_data_rejects_negative_amount_like_live_data(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(json.dumps({"history": [{"type": "income", "amount": -50}]}))

    with pytest.raises(ValueError):
        load(path)


def test_loaded_data_rejects_overdraw_like_live_data(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(
        json.dumps(
            {
                "history": [
                    {"type": "income", "amount": 20},
                    {"type": "expense", "amount": 50, "category": "Food"},
                ]
            }
        )
    )

    with pytest.raises(InsufficientBalanceError):
        load(path)
