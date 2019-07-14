"""Database connection pool.

How to create:

from venus.db.dbo.adapter.sqlite import get_factory
from venus.db.dbo.connectionpool import ConnectionPool
factory = get_factory(':memory:')
pool = ConnectionPool(factory)

How to use:

Higher level interface - use the pool as a context manager.
Ensures correct transaction handling, makes writing code easier.

Methods for higher level interface:

    pool.open(): borrow connection, execute something then give it back:
    pool.opentrans(): similar to open() but also do BEGIN + COMMIT
        or BEGIN + ROLLBACK + raise if there was an exception

Examples:

with pool.open() as conn:
    conn.query(....)

with pool.opentrans() as conn:
    conn.execsql(....)

with pool.open(anotherconnn) as conn:
    conn.query(....)

with pool.opentrans(anotherconnn) as conn:
    conn.execsql(....)

See detailed documentation of the open() and opentrans() methods!

Low level interface (not recommended):

conn = pool.borrow() # Borrow connection from pool
try:
    conn.query(...)
    conn.execsql(...)
finally:
    pool.giveback(conn) # Give connection back to pool

IMPORTANT! The database module's threadsafety level MUST be at least 1,
and SHOULD be at least 2.

Aged out connections are collected and closed from a different thread.
Although you can use connection poools with threadsafety=1, but
this will be implemented as a non-pool. E.g. connections given back
to the pool will be unconditionally closed.


"""
import threading
import time

import venus.i18n
from venus.db.dbo import DboException
from venus.db.dbo.connection import Connection

_ = venus.i18n.get_my_translator(__file__)


class ConnectionPoolContextManager:
    """This context manager manages a database connection.

    - It is able to borrow it from a connection pool and give it back.
    - It is able to start a transaction, and commit (or rollback on exception)
    - It can also be used with an an already existing connection,
        instead of borrowing one from the pool!

    For details, see the documentation of its constructor.
    """

    def __init__(self, pool, start_trans, preconn, debug):
        """Create a new ConnectionPoolContextManager.

        @param pool: A ConnectionPool instance.
        @param start_trans: When set, a new transaction will be started
            with the connection's starttransaction() method. This
            transaction will be then commited or rolled back (if there
            was an exception in the 'with' block, using the context.)
            Please note that starttransaction() may create a new
            savepoint instead of creating a new transaction.
            Behaves like a subtransaction!
        @param preconn: Should be an opened connection. When given,
            it will be used. No connection will be borrowed/given back
            to pool.

        """
        self.pool = pool
        self.start_trans = start_trans
        self.preconn = preconn
        self.debug = debug

    def __enter__(self) -> Connection:
        if self.preconn:
            self.conn = self.preconn
        else:
            self.conn = self.pool.borrow()
        if self.start_trans:
            if self.debug:
                print(_("ConnectionPoolContextManager BEGIN"))
            self.trans_id = self.conn.starttransaction()
        return self.conn

    def __exit__(self, typ, value, traceback):
        if self.start_trans:
            if typ:
                if self.debug:
                    print(_("ConnectionPoolContextManager ROLLBACK"))
                self.conn.rollbacktransaction(self.trans_id)
            else:
                if self.debug:
                    print(_("ConnectionPoolContextManager COMMIT"))
                self.conn.committransaction(self.trans_id)
        if not self.preconn:
            self.pool.giveback(self.conn)
        return False


class BaseConnectionPool:
    """Base connection pool object.

    Do not use directly. Use ConnectionPool or AsyncConnectionPool instead."""
    debug = False

    def __init__(self, conn_factory, max_age=60):
        """Create a new connection pool.

        @param conn_factory: A factory function. When called, it must
            return a new venus.db.dbo.connection.Connection
            instance.
        @param max_age: Maximum age for connection to keep alive.
            This is in seconds. Default is 60 (=1 minute).
            Borrowed connections may live a bit longer.
            Resolution for max_age is one second, and it should not
            be less than 1 second.
        """
        assert (max_age >= 1.0)
        self.max_age = max_age
        self.held = []
        self.borrowed = []
        self.conn_factory = conn_factory

    def borrow(self):
        """Borrow a connection for the given database name."""
        now = time.time()
        # Pop/create connection
        while self.held:
            res = self.held.pop()
            if now > res.created + self.max_age:
                if self.debug:
                    print(_("borrow(): closing aged out connection"))
                res.close()
            else:
                break
        else:
            if self.debug:
                print(_("Creating new connection"))
            res = self.conn_factory()
            res.created = time.time()
            if res.module.threadsafety < 1:
                raise DboException(
                    _("DB API: threadsafety should be " +
                      "at least one! Two is highly recommended."))
        # Move to borrowed
        self.borrowed.append(res)
        return res

    def giveback(self, conn):
        """Give a connection back."""
        if conn in self.borrowed:
            self.borrowed.remove(conn)
            now = time.time()
            if conn.module.threadsafety < 2:
                if self.debug:
                    print(
                        _("giveback(): closing connection because " +
                          "cannot be shared between threads"))
                conn.close()
            # Put back to held ONLY if not aged out!
            elif now > conn.created + self.max_age:
                if self.debug:
                    print(_("giveback(): closing aged out connection"))
                conn.close()
            else:
                self.held.append(conn)
        else:
            raise ValueError(_(
                "Giving back something that is not borrowed?"))

    def collect(self):
        """Do garbage collection on connections in the pool."""
        if self.debug:
            print(_("connectionpool.collect() - START"))
        now = time.time()
        examined = []
        while self.held:
            conn = self.held.pop()
            if now > conn.created + self.max_age:
                if self.debug:
                    print(
                        "    " +
                        _("connectionpool.collect(): " +
                          " closing aged out connection"))
                conn.close()
            else:
                examined.append(conn)
        self.held[:] = examined
        if self.debug:
            print(_("connectionpool.collect() - END"))

    def open(self, preconn=None) -> ConnectionPoolContextManager:
        """Return a context manager.

        The context manager enters into a new transaction ONLY if
            preconn was not given, e.g. if the connection was just
            borrowed from the pool.

        @param preconn: When given, this will be used, instead of
            borrowing from the pool. Useful for writting simpler code
            for methods that can use a given connection, or fall back
            to a connectionpool if needed.

        For details, see ConnectionPoolContextManager."""
        if preconn:
            return ConnectionPoolContextManager(
                self, False, preconn, self.debug)
        else:
            return ConnectionPoolContextManager(
                self, True, preconn, self.debug)

    def opentrans(self, preconn: Connection = None) -> ConnectionPoolContextManager:
        """Return a context manager, that enters a new database transaction.

        @param preconn: When given, this will be used, instead of
            borrowing from the pool. Useful for writting simpler code
            for methods that can use a given connection, or fall back
            to a dbpool if needed.

        For details, see ConnectionPoolContextManager.

        """
        return ConnectionPoolContextManager(
            self, True, preconn, self.debug)


class AsyncConnectionPool(BaseConnectionPool):
    """Async connection pool.

    This is a non-thread safe version. It does not use any locks, but
    you need to call its collect() method manually, periodically."""
    pass


class ConnectionPoolCollector(threading.Thread):
    """Daemonic thread that closes outdated connections."""

    def __init__(self, pool):
        """@param pool: ConnectionPool instance."""
        self.pool = pool
        threading.Thread.__init__(self)

    def run(self):
        if self.pool.max_age >= 10.0:
            wait = self.pool.max_age / 10.0
        else:
            wait = 1.0
        while True:
            time.sleep(wait)
            self.pool.collect()


class ConnectionPool(BaseConnectionPool):
    """Thread-safe connection pool."""

    def __init__(self, conn_factory, max_age=60):
        """Create a new connection pool.

        @param conn_factory: A factory function. When called, it must
            return a new venus.db.dbo.connection.Connection
            instance.
        @param max_age: Maximum age for connection to keep alive.
            This is in seconds. Default is 60 (=1 minute).
            Borrowed connections may live a bit longer.
            Resolution for max_age is one second, and it should not
            be less than 1 second.
        """
        self.lock = threading.Lock()
        BaseConnectionPool.__init__(self, conn_factory, max_age)
        collector = ConnectionPoolCollector(self)
        collector.setDaemon(True)
        collector.start()

    def borrow(self):
        """Borrow a connection for the given database name."""
        with self.lock:
            return BaseConnectionPool.borrow(self)

    def giveback(self, conn):
        """Give a connection back."""
        with self.lock:
            return BaseConnectionPool.giveback(self, conn)

    def collect(self):
        """Do garbage collection on connections in the pool."""
        with self.lock:
            return super().collect()


if __name__ == '__main__':
    test_sqlite = True
    test_postgresql = False

    if test_sqlite:
        print("Testing sqlite")
        import os
        import tempfile
        from venus.db.dbo.adapter import sqlite

        fpath = os.path.join(tempfile.gettempdir(), 'test.sqlite')
        print("Test database:", fpath)
        if os.path.isfile(fpath):
            os.unlink(fpath)
        factory = sqlite.Connection.create_factory(fpath)
        pool = ConnectionPool(factory, 1)
        pool.debug = True
        with pool.open() as conn:
            print(conn)
            conn.execsql("create table test(a integer)")
            conn.execsql("insert into test values (1)")
            print("inserted 1")
            try:
                with pool.opentrans(conn):
                    conn.execsql("insert into test values (2)")
                    print("inserted 2")
                    raise Exception("2 should be rolled back...")
            except Exception as e:
                print(e)
            conn.execsql("insert into test values (4)")
            print("inserted 4")

        with pool.opentrans() as conn:
            # Test iterdicts
            print("Test iterdicts: should print {a:1},{a:4}")
            q = conn.query("select * from test")
            for d in q.iterdicts():
                print("    ", d)
            print("Test iterrows: should print (1,),(4,)")
            q = conn.query("select * from test")
            for row in q.iterrows():
                print("    ", row)
            print("Test QueryIterator: should print (1,1),(4,4)")
            q = conn.query("select * from test")
            for qi in q:
                print(qi[0], qi['a'])

        # Testing savepoint/rollback!
        with pool.opentrans() as conn:
            q = conn.query("select * from test")
            for d in q.iterdicts():
                print(d)

    if test_postgresql:
        print("Testing postgresql")
        from venus.db.dbo.adapter import postgresql

        factory = postgresql.Connection.create_factory(
            host='127.0.0.1', database='template1',
            user='postgres', password='postgres')
        pool = ConnectionPool(factory, 1)  # One sec timeout!
        pool.debug = True
        with pool.open() as conn:
            print(conn)
            print(conn.getqueryvalues("select * from pg_stat_activity",
                                      associative=True))
        print("Wait some...")
        time.sleep(0.8)
        print("Should age out soon...")
        time.sleep(2)
        print("Should be aged out by now.")
        print()
        print()
        pool.debug = False  # Turn off debugging
        with pool.open() as conn:
            q = conn.query("select datname from pg_database")
            for d in q.iterdicts():
                print(d)
