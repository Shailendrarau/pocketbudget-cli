"""Custom domain exceptions."""


class InvalidCategoryError(Exception):
    """Raised when an expense uses a category that is not allowed."""


class InsufficientBalanceError(Exception):
    """Raised when an expense is larger than the account's total balance."""
