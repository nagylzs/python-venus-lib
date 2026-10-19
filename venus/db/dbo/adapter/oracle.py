"""Oracle database adapter package.

Uses python-oracledb (the successor of cx_Oracle)."""
import copy
import getpass
import os
import re
import sys

import oracledb

from venus.db.dbo import connection

# Positional parameters of create_factory, in the order of cx_Oracle.connect(user, password, dsn).
# oracledb.connect() accepts only dsn as a positional parameter.
_POSITIONAL_PARAMS = ("user", "password", "dsn")
# cx_Oracle only parameters, python-oracledb always uses UTF-8.
_DESUPPORTED_PARAMS = ("encoding", "nencoding")

_client_mode_initialized = False


def _init_client_mode():
    """Select thin or thick mode before the first connection.

    python-oracledb runs in thin mode by default: it does not need the Oracle Instant Client, but it needs
    Oracle Database 12.1 or later. Set the VENUS_ORACLE_THICK environment variable to 1 to use thick mode
    instead (it loads the Oracle Instant Client from the system library path, e.g. LD_LIBRARY_PATH).
    """
    global _client_mode_initialized
    if _client_mode_initialized:
        return
    if os.environ.get("VENUS_ORACLE_THICK", "").lower() in ("1", "true", "yes"):
        oracledb.init_oracle_client()
    _client_mode_initialized = True


class Connection(connection.Connection):
    """Oracle database adapter."""

    @classmethod
    def create_factory(cls, *params, **kwparams):
        """Create and return a database connection factory object.

        When called, it returns a new Connection instance.

        Positional parameters are user, password and dsn, like in cx_Oracle.connect(). For keyword parameters, see
        https://python-oracledb.readthedocs.io/en/latest/api_manual/module.html#oracledb.connect

        """
        if len(params) > len(_POSITIONAL_PARAMS):
            raise TypeError("create_factory() takes at most %d positional parameters (%s)" % (
                len(_POSITIONAL_PARAMS), ", ".join(_POSITIONAL_PARAMS)))
        kwparams = dict(kwparams)
        for name, value in zip(_POSITIONAL_PARAMS, params):
            if name in kwparams:
                raise TypeError("create_factory() got multiple values for parameter %r" % name)
            kwparams[name] = value
        for name in _DESUPPORTED_PARAMS:
            kwparams.pop(name, None)
        _init_client_mode()

        def factory():
            lowlevel = oracledb.connect(**kwparams)
            conn = cls(oracledb, lowlevel)
            trans_id = conn.starttransaction()
            conn.execsql("set transaction isolation level read committed")
            conn.committransaction(trans_id)
            return conn

        return factory

    # Max length of identifiers in SQL.
    max_identifier_length = 63
    # Map that converts logical types to physical types.
    #
    # Possible fields:
    #
    #    nativename - preferred native name of the type
    #    names - other aliases understood by the database (optional)
    #    need_size - set True if the field needs a size (optional)
    #    need_precision - set True if the field needs a precision (optional)
    #

    # http://www.postgresql.org/docs/9.2/static/datatype.html
    typemap = [
        # Numeric types.
        # http://www.postgresql.org/docs/9.2/static/datatype-numeric.html
        {"nativename": "smallint", "names": {"smallint", "int2"}, },
        {"nativename": "integer", "names": {"integer", "int4"}, },
        {"nativename": "bigint",
         "names": {"bigint", "int8", "identifier"}, },
        {"nativename": "numeric", "names": {"numeric", "decimal"},
         "need_size": True, "need_precision": True, },
        {"nativename": "real", "names": {"real", "single", "float4"}, },
        {"nativename": "double precision",
         "names": {"double", "double precision", "float8"}, },
        # Character types
        # http://www.postgresql.org/docs/8.2/static/datatype-character.html
        {"nativename": "text", },
        {"nativename": "varchar",
         "names": {"varchar", "character varying"},
         "need_size": True, },
        # Binary (flat blob) types
        # http://www.postgresql.org/docs/9.2/static/datatype-binary.html
        {"nativename": "bytea", "names": {"blob", "bytea"}, },
        # Date/Time types
        # http://www.postgresql.org/docs/9.2/static/datatype-datetime.html
        {"nativename": "timestamp",
         "names": {"timestamp without time zone", "timestamp"}, },
        {"nativename": "timestamptz",
         "names": {"timestamp with time zone", "timestamptz"}, },
        {"nativename": "date", },
        {"nativename": "time",
         "names": {"time without time zone", "time"}},
        {"nativename": "timetz",
         "names": {"time with time zone", "timetz"}},
        {"nativename": "interval", },
        # Boolean types
        # http://www.postgresql.org/docs/9.2/static/datatype-boolean.html
        {"nativename": "boolean", },
        # Geometric types
        {"nativename": "point", },
        {"nativename": "line", },
        {"nativename": "lseg", },
        {"nativename": "box", },
        {"nativename": "path", },
        {"nativename": "polygon", },
        {"nativename": "circle", },
        # Network address types
        # http://www.postgresql.org/docs/9.2/static/datatype-net-types.html
        {"nativename": "cidr", },
        {"nativename": "inet", },
        {"nativename": "macaddr", },
        # TODO: add bitstring and text search types.
        # How is it supported by psycopg2?
        # UUID type
        # http://www.postgresql.org/docs/9.2/static/datatype-uuid.html
        {"nativename": "uuid", },
        # TODO: add XML type. How is it supported by psycopg2?
        # JSON type
        # http://www.postgresql.org/docs/9.2/static/datatype-json.html
        {"nativename": "json", },
        {"nativename": "jsonb", },
        {"nativename": "bigint[]", "names": {"int8[]", "bigint[]"}, },
    ]

    # Existence methods.
    # To explore use these:
    #
    # select table_name from information_schema.tables
    # where  table_schema='information_schema' order by 1
    #
    # and
    # select table_name from information_schema.tables where
    # table_name ilike 'pg_%'
    #

    def schema_exists(self, schemaname):
        """Tells if the given schema exists."""
        raise NotImplementedError

    def table_exists(self, schemaname, tablename):
        """Tells if the given table exists."""
        raise NotImplementedError

    def column_exists(self, schemaname, tablename, columname):
        """Tells if the given column exists."""
        raise NotImplementedError

    def index_exists(self, schemaname, tablename, indexname):
        """Tells if the given index exists."""
        raise NotImplementedError


connection.DATABASE_DRIVERS["oracle"] = Connection

if __name__ == '__main__':
    test_factory = Connection.create_factory(
        "my_user", "my_password", "my_host:1521/db_name")
    print(test_factory())
