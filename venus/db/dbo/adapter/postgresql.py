"""PostgreSQL database adapter package.

Uses the psycopg2 extension."""
import copy
import getpass
import os
import re
import sys

import psycopg2

from venus.db.dbo import connection

# http://www.postgresql.org/docs/9.2/static/libpq-pgpass.html
_PGPASS_PAT = re.compile(r"([^:]+):([^:]+):([^:]+):([^:]+):([^:]+)")

_CONNSTRING_PATTERN = pat = re.compile(r"([^=]+)=([^\s]*)")


def _read_pgpass():
    """Read valid lines from the user's .pgpass file."""
    if sys.platform == "win32":
        fpath = os.path.join(
            os.environ["APPDATA"], "postgresql",
            "pgpass.conf")
    elif "PGPASSFILE" in os.environ:
        fpath = os.environ["PGPASSFILE"]
    elif "HOME" in os.environ:
        fpath = os.path.join(os.environ["HOME"], ".pgpass")
    else:
        fpath = None

    if fpath and os.path.isfile(fpath):
        for line in open(fpath, "r").readlines():
            hit = _PGPASS_PAT.match(line.strip())
            if hit:
                yield hit.groups()


def _get_pgpass(params):
    """Find a password for the given connection parameters.

    The params parameter MUST be a dict!"""

    def _matchparam(name, value, defval=""):
        """Match .pgpass parameter with a value."""
        if value == '*':
            return True
        else:
            return value == str(params.get(name, defval))

    for host, port, database, user, password in _read_pgpass():
        if _matchparam("host", host) and \
                _matchparam("port", port, "5432") and \
                _matchparam("database", database) and _matchparam("user", user):
            return password


class Connection(connection.Connection):
    """Postgresql database adapter."""

    @classmethod
    def decode_connection_string(cls, connection_string):
        """Parse a db driver specific connection string into (args, kwargs).

        This version works with PostgreSQL, and it tries to use the .pgpass file (when available).
        The connection string parameters are parsed into keywords arguments.

        :param connection_string: Connection string to be parsed into constructor parameters.
        :return: A tuple of (args,kwargs) that can be passed directly to the DB API 2.0 compilant module's
            connect method.
        """
        # return ((connection_string,),{}) # Use this to disable .pgpass support and defaults.
        global _CONNSTRING_PATTERN
        res = {}
        for item in connection_string.split():
            hit = _CONNSTRING_PATTERN.match(item.strip())
            if hit:
                name, connection_string = hit.groups()
                res[name] = connection_string
        return ((), res)

    @classmethod
    def create_factory(cls, *params, **kwparams):
        """Create and return a database connection factory object.

        When called, it returns a new Connection instance.
        When connection parameters given as keywords arguments and password
        is not given, then it tries to read the user's .pgpass file and
        find a password.

        When connection parameters are given as positional arguments (e.g. dsn) then they are used as is.

        Example:

        factory = venus.db.dbo.adapter.postgresql.create_factory(
                host='127.0.0.1',database='template1',
                user='my_user',password='not_telling')
        # Now, create two connection objects.
        conn1 = factory()
        conn2 = factory()
        """
        if kwparams:
            kwparams = copy.deepcopy(kwparams)
            if "user" not in kwparams:
                kwparams["user"] = getpass.getuser()
            if "database" not in kwparams:
                kwparams["database"] = kwparams["user"]
            if "password" not in kwparams:
                password = _get_pgpass(kwparams)
                if password:
                    kwparams['password'] = password

        def factory():
            lowlevel = psycopg2.connect(*params, **kwparams)
            conn = cls(psycopg2, lowlevel)
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
        return bool(self.getqueryvalue("""select oid from pg_namespace
            where nspname=%s""", [schemaname]))

    def table_exists(self, schemaname, tablename):
        """Tells if the given table exists."""
        return bool(self.getqueryvalue("""

            select table_type
            from information_schema.tables
            where
                    table_catalog=current_database()
                and table_schema=lower(%s)
                and table_name=lower(%s)
        """, [schemaname, tablename]))

    def column_exists(self, schemaname, tablename, columname):
        """Tells if the given column exists."""
        return bool(self.getqueryvalue("""
            select column_name from information_schema.columns
            where
                    table_catalog=current_database()
                and table_schema=lower(%s)
                and table_name=lower(%s)
                and column_name=lower(%s)
        """, [schemaname, tablename, columname]))

    def index_exists(self, schemaname, tablename, indexname):
        """Tells if the given index exists."""
        # TODO: create a method to list index fields, e.g. a.attname as column_name
        return bool(self.getqueryvalue("""
            select t.oid
            from
                pg_catalog.pg_namespace s,
                pg_class t,
                pg_class i,
                pg_index ix,
                pg_attribute a
            where
                t.oid = ix.indrelid
                and i.oid = ix.indexrelid
             and a.attrelid = t.oid
             and a.attnum = ANY(ix.indkey)
             and t.relkind = 'r'
             and s.oid = t.relnamespace
            
             and lower(s.nspname)=%s
             and lower(t.relname)=%s
            and lower(i.relname)=%s 
            """, [schemaname, tablename, indexname]))


connection.DATABASE_DRIVERS["postgresql"] = Connection

if __name__ == '__main__':
    test_factory = Connection.create_factory(
        host='127.0.0.1',
        database='template1', user='postgres', password='postgres')
    # <venus.db.dbo.connection.Connection object at 0x939a7ec>
    print(test_factory())
