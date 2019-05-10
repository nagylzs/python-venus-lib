from venus.db.dbo import DboException
from venus.db.dbo import connection
# TODO: import all drivers here, but how?
from venus.db.dbo.connectionpool import ConnectionPool, AsyncConnectionPool

class DboDriverMissingError(DboException):
    pass

def decode_dbdriver(dbtype):
    """Get a database driver for the given dbtype name.

    @param dbtype: name of the driver. For example "postgresql" or
        "sqlite". See the venus.db.dbo.adapter package for details.
    """
    if dbtype not in connection.DATABASE_DRIVERS:
        raise DboDriverMissingError(
            "Invalid database type. Valid types are: %s" %
            list(connection.DATABASE_DRIVERS.keys()))
    return connection.DATABASE_DRIVERS[dbtype]

def get_connection_factory(dbtype, connection_string):
    """Create a connection factory.

    :param dbtype: See decode_dbdriver().
    :param connection_string: See decode_connection_string().
    :return: a factory function that returns a connection object
    """
    db_driver = decode_dbdriver(dbtype)
    args, kwargs = db_driver.decode_connection_string(connection_string)
    return db_driver.create_factory(*args, **kwargs)


def create_asyncpool(dbtype, connstring) -> AsyncConnectionPool:
    """Create an AsyncConnectionPool for a set of parameters.

    Warning: for thread-safe applications, use create_pool().

    :param dbtype: See decode_dbdriver().
    :param connection_string: See decode_connection_string().
    :return: an async connection pool
    :rtype: AsyncConnectionPool
    """
    return AsyncConnectionPool(get_connection_factory(dbtype, connstring))


def create_pool(dbtype, connstring) -> ConnectionPool:
    """Create an ConnectionPool for a set of parameters.

    Warning: for async applications, use create_asyncpool().

    :param dbtype: See decode_dbdriver().
    :param connection_string: See decode_connection_string().
    :return: a connection pool
    :rtype: ConnectionPool
    """
    return ConnectionPool(get_connection_factory(dbtype, connstring))
