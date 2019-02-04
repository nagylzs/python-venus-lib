

class DboException(Exception):
    """Base class for venus database access objects"""
    pass


class DboTransactionError(DboException):
    """Transaction error for venus database access objects."""
    pass
