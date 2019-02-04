"""SQLite database adapter package.

Uses the sqlite3 extension.

Please make sure that you use sqlite library version 3.6.8 or above.
Savepoint and rollback to doesn't work with lower versions.
"""
import sqlite3

import venus.i18n
from venus.db.dbo import DboException
from venus.db.dbo import connection
_ = venus.i18n.get_my_translator(__file__)

_VERSION_OK = None


def _check_sqlite_version():
    """Check sqlite version.

    Only version above 3.6.8 or above can handle nested
    transactions properly."""
    global _VERSION_OK
    if _VERSION_OK is None:
        parts = list(map(int, sqlite3.sqlite_version.split('.')))
        _VERSION_OK = (
            (parts[0] == 3) and (parts[1] == 6) and
            (parts[2] >= 8)) or ((parts[0] == 3) and (parts[1] > 6))
    if not _VERSION_OK:
        raise DboException(_("You need 4.0 > sqlite_version >= 3.6.8."))


class Connection(connection.Connection):
    """Need to play with transaction handling.

    For details see:

    http://www.gossamer-threads.com/lists/python/python/813666?page=last
    """
    @classmethod
    def create_factory(cls, *params, **kwparams):
        """Create and return a database connection factory object.

        When called, it returns a new Connection instance.

        Example:

        factory = venus.db.dbo.adapter.postgresql.create_factory(":memory:")
        # Now, create two connection objects.
        conn1 = factory()
        conn2 = factory()
        """
        _check_sqlite_version()

        def factory():
            lowlevel = sqlite3.connect(*params, **kwparams)
            lowlevel.isolation_level = None
            conn = cls(sqlite3, lowlevel)
            return conn
        return factory

    def dostarttransaction(self):
        """SQLite requires explicit begin"""
        self.execsql("BEGIN")

    def docommittransaction(self):
        """Then we should use explicit commit..."""
        self.execsql("COMMIT")

    def dorollbacktransaction(self):
        """Then we should use explicit rollback..."""
        self.execsql("ROLLBACK")

    def domakesavepoint(self, level):
        self.execsql('SAVEPOINT sp_%d' % level)

    def docommitsavepoint(self, level):
        self.execsql('RELEASE sp_%d' % level)

    def dorollbacksavepoint(self, level):
        self.execsql('ROLLBACK TO sp_%d' % level)

    typemap = [
        {"nativename": "integer", "names": {"integer", "identifier"}},
        {"nativename": "text", },
        {"nativename": "real", },
        {"nativename": "blob", },
    ]


connection.DATABASE_DRIVERS["sqlite"] = Connection

if __name__ == '__main__':
    test_factory = Connection.create_factory(':memory:')
    # <venus.db.dbo.connection.Connection object at 0x939a7ec>
    print(test_factory())
