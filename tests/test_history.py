"""History is exposed as a read-only snapshot, not a live view."""

from pocketbudget.account import Account


def test_mutating_returned_history_does_not_change_account_history() -> None:
    account = Account()
    account.add_income(100)
    account.add_expense(30, "Food")

    snapshot = list(account.history)

    history = account.history
    history.append({"type": "income", "amount": 1000})

    assert account.history == snapshot
