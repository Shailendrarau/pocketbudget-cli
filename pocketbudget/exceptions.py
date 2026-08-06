"""Custom domain exceptions."""


class InvalidCategoryError(Exception):
    """Raised when an expense uses a category that is not allowed."""


class InsufficientBalanceError(Exception):
    """Raised when an expense is larger than the account's total balance."""


class InvalidAmountError(ValueError):
    """Raised when a transaction or budget amount is negative.

    Subclasses ``ValueError`` so existing callers that validated input with
    ``ValueError`` keep working.
    """


class BudgetLimitExceededError(Exception):
    """Raised when an expense would blow past a strict category budget."""


class StorageError(Exception):
    """Raised when a save file cannot be read as valid account state."""
