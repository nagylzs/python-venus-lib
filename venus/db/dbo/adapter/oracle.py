"""PostgreSQL database adapter package.

Uses the psycopg2 extension."""
import copy
import getpass
import os
import re
import sys

import cx_Oracle

from venus.db.dbo import connection


class Connection(connection.Connection):
    """Oracle database adapter."""

    @classmethod
    def create_factory(cls, *params, **kwparams):
        """Create and return a database connection factory object.

        When called, it returns a new Connection instance.

        For arguments, see https://cx-oracle.readthedocs.io/en/latest/user_guide/connection_handling.html

        """

        def factory():
            lowlevel = cx_Oracle.connect(*params, **kwparams)
            conn = cls(cx_Oracle, lowlevel)
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
        "my_user", "my_password", "my_host:1521/db_name", encoding="UTF-8")
    print(test_factory())
