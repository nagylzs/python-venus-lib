"""Database connection.

Provides the venus.db.dbo.Connection base class.


This class should not be used directly.
Please use a connection pool instead."""

import base64
import hashlib
import threading

import venus.i18n
from venus.db.dbo import DboTransactionError
from venus.db.dbo.query import Query
from venus.db.yasdl import ast

_ = venus.i18n.get_my_translator(__file__)

# List of database drivers. You can add them by importing.
# For example: "import venus.db.dbo.adapter.postgresql".
DATABASE_DRIVERS = {}


class Connection:
    """Database connection wrapper.

    Contains a DB API 2.0 compilant connection object, its module and
    additional database information.

    Important: any type of DB API 2.0 compilant objects could be used.
    However, the used RDBMS should support these features:

        1. round trip parameters for all basic data types
        2. flat BLOB data support
        3. Nested transactions (savepoint and rollback to)

    To add support for new types of databases, look at 'adapters'.

    """
    name_separator = "$"

    def __init__(self, module, connection):
        """Create a new Database connection wrapper for the given DB API
        module, connection object and database type.

        :param module: a DB API 2.0 compilant module.
        :param connection: an inicialized database connection.
        """
        self.module = module
        self.connection = connection
        self.translock = threading.Lock()
        self.transactionlevel = 0
        self.cursors = []  # Stack of cursors for trans. levels.
        self.closed = False

    def decode_connection_string(self, connection_string):
        """Parse a db driver specific connection string into (args, kwargs).

        :param connection_string: Connection string to be parsed into constructor parameters.
        :return: A tuple of (args,kwargs) that can be passed directly to the DB API 2.0 compilant module's
            connect method.
        """
        raise NotImplementedError

    def _getcursorfor(self, sql, params):
        """@return: a cursor object for the given SQL and parameters.

        Low level method, do not use directly!"""
        cur = self.connection.cursor()
        cur.execute(sql, params)
        return cur

    def _getcursorfields(self, cur):
        """Return a list of the field names in cursor cur.
        :param cur: An opened cursor (SELECT)
        @return: A list of field names in the opened cursor, in order.

        Low level method, do not use!
        """
        return [item[0] for item in cur.description]

    def _closecurs(self, level):
        """Close all cursor objects above the given level.

        :param level: The level about to be removed.

        Closes all cursors until the given level. Also
        truncates "cursors" stack to the given level.

        Low level method, do not use!"""
        # Close cursors create on this level or above.
        assert (len(self.cursors) == self.transactionlevel)
        while len(self.cursors) >= level:
            cursors = self.cursors.pop()
            for cur in cursors:
                self._closecur(cur)

    def _closecur(self, cur):
        """Close one cursor, if possible.

        Exceptions are silently ignored."""
        if hasattr(cur, 'closed'):
            if not cur.closed:
                cur.close()
        else:
            try:
                cur.close()
            except self.module.Error:
                pass
        if self.cursors and (cur in self.cursors[-1]):
            self.cursors[-1].remove(cur)

    def close(self):
        """Close the connection unconditionally.

        The connection will be unusable from this point forward. An
        Error (or subclass) exception will be raised if any operation is
        attempted with the connection. The same applies to all cursor
        objects trying to use the connection. Note that closing a
        connection without committing the changes first will cause an
        implicit rollback to be performed."""
        if not self.closed:
            self.connection.close()
            self.closed = True

    def execsql(self, sql, params=None):
        """Execute an SQL statement.

        You should use this method to execute SQL statements that do not
        return a value. For statements returning values, please look at
        these methods:

            1. getqueryvalue
            2. getqueryvalues
            3. query


        :param sql: The SQL statement to execute
        :param params: Parameters to pass to the sql
        @type  params: list or dict
        @return: the number of rows affected (if available) or None.

        Implementation note: this method immediately closes the cursor
            after executing the SQL statement.
        """
        cur = self._getcursorfor(sql, params or [])
        if hasattr(cur, 'rowcount'):
            res = cur.rowcount
        else:
            res = None
        cur.close()
        return res

    def getqueryvalues(self, sql, params=None, associative=False):
        """Execute a query and return the first row.

        See also:

            1. getqueryvalue
            2. query

        :param sql: The SQL query to execute (usually a SELECT statement)
        @type  sql: string
        :param params: Parameters for the SQL statement. See execsql.
        @type  params: list or dict
        :param associative: If you want to get a dictionary istead of a tuple.
        @return: Return None if the result set is empty, return the
            first tuple from the result set that is defined by the sql
            otherwise. Note: if you set the associative parameter to
            True, you will get a dictionary where the keys will be the
            field names and the values will be the field values.


        Implementation note: this method immediately closes the cursor
            after executing the SQL statement.
        """
        cur = self._getcursorfor(sql, params or [])
        try:
            data = cur.fetchone()
            if data is None:
                return None
            elif associative:
                fields = self._getcursorfields(cur)
                res = {}
                for index in range(len(fields)):
                    res[fields[index]] = data[index]
                return res
            else:
                return data
        finally:
            cur.close()

    def getqueryvalue(self, sql, params=None):
        """Execute a query and return the first value in the first row.

        See also:

            1. getqueryvalues
            2. query

        :param sql: The SQL query to execute
        @type  sql: string
        :param params: Parameters for the SQL statement. See execsql.
        @type  params: list or dict
        @return: Return None if the result set is empty. Return the
            first value of the first tuple from the result set that is
            defined by the sql otherwise.

        Implementation note: this method immediately closes the cursor
            after executing the SQL statement.
        """
        res = self.getqueryvalues(sql, params)
        if res is None:
            return None
        else:
            return res[0]

    def getcursorfor(self, sql, params=None):
        """Return a cursor for the given sql and params.

        This method is very similar to the low level _getcursorfor()
        method, but it manages cursors for the given transaction level.
        E.g. the returned cursor will be closed before its enclosing
        database transaction is committed/rolled back."""
        if self.transactionlevel < 1:
            raise DboTransactionError(
                "connection.getcursorfor():" +
                _("must be in transaction!"))
        res = self._getcursorfor(sql, params or [])
        self.cursors[self.transactionlevel - 1].append(res)
        return res

    def query(self, sql, params=None):
        """Returns a  Query instance.

        You can use query instances to iterate over datasets.

        These are unidirectional, and usable only within their
        containing database transaction.

        See also:

            1. getqueryvalue
            2. getqueryvalues


        Implementation note: Descendants should leave this method as is,
        and implement the _getcursorfor method.
        """
        return Query(self, sql, params)

    def starttransaction(self):
        """This method will start a new transaction block.

        If you call this method outside any active transaction, that
        will raise the current transaction level from zero to one.

        If you call this method inside an active transaction:

            1. If the database supports nested transactions, then a new
                substransaction will be created.
            2. If the database does not support nested transactions, a
                NotImplemented will be raised.

        @return: The new (increased) transaction level.

        Implementation note: Descendants should leave this method as is,
        and implement the dostarttransaction and the domakesavepoint
        method, if applicable.
        """
        with self.translock:
            if self.transactionlevel == 0:
                self.dostarttransaction()
                self.transactionlevel = 1
            else:
                self.transactionlevel += 1
                self.domakesavepoint(self.transactionlevel)

            # Create storage for cursors opened in this transaction.
            self.cursors.append([])
            assert (len(self.cursors) == self.transactionlevel)

            return self.transactionlevel

    def gettransactionlevel(self):
        """Return the current level of transaction.

        Each call to starttransaction increments the transaction level.
        The initial transaction level is zero, which means there is no
        active transaction. Please note that many database drivers will
        start a transaction implicitly, when you execute your first SQL
        statement outside any transaction. Because of this, the
        recommended  usage is to always enclose your data operations
        between starttransaction and commit/rollback. The database
        connection context manager does this for you. Instead of
        direct transaction handling, usage of the context managers
        is recommended: open() and opentrans().

        Also please note that if more threads are using the same
        connection, then you cannot trust in this value."""
        with self.translock:
            return self.transactionlevel

    def committransaction(self, level):
        """Commits the current transaction.

        @level: The level parameter specifies the level that needs to
            be committed. Using None will commit the outermost
            transaction.

        Note: if you call this transaction outside the main transaction,
            a DboTransactionError will be raised.

        @return: The new (decremented) transaction level.

        Implementation note: Descendants should leave this method as is,
        and implement the docommittransaction and docommitsavepoint
        methods.
        """
        with self.translock:
            if level is None:
                level = self.transactionlevel
            if (level < 1) or (level > self.transactionlevel):
                raise DboTransactionError(
                    _("Invalid transaction level " +
                      " (current=%d, to be commited=%d)") %
                    (self.transactionlevel, level))

            # Close cursors for this level
            self._closecurs(level)
            if level == 1:
                self.docommittransaction()
            else:
                self.docommitsavepoint(level)
            self.transactionlevel = level - 1
            return self.transactionlevel

    def rollbacktransaction(self, level):
        """Rollback the current transaction.

        @level: The level parameter specifies the level that needs to
            be rolled back. Specifying None will rollback the
            outermost transaction. Required since version 2.0.

        Note: if you call this transaction outside the main transaction,
            a DboTransactionError will be raised.

        @return: The new (decremented) transaction level.

        Implementation note: Descendants should leave this method as is,
            and implement the dorollbacktransaction and
            dorollbacksavepoint method.
        """
        with self.translock:
            if level is None:
                level = self.transactionlevel
            if (level < 1) or (level > self.transactionlevel):
                raise DboTransactionError(
                    _("Invalid transaction level " +
                      " (current=%d, to be rolled back=%d)") %
                    (self.transactionlevel, level))

            # Close cursors for this level
            self._closecurs(level)
            if level == 1:
                self.dorollbacktransaction()
            else:
                self.dorollbacksavepoint(level)
            self.transactionlevel = level - 1
            return self.transactionlevel

    def dostarttransaction(self):
        """Start a new (main) transaction.

        This method is implemented as a no-operation but descendants
        can override it."""
        pass

    def docommittransaction(self):
        """Commit the main transaction.

        This method is implemented as self.connection.commit(), but
        descendants can override it."""
        self.connection.commit()

    def dorollbacktransaction(self):
        """Rollback the main transaction.

        This method is implemented as self.connection.rollback(), but
        descendants can override it."""
        self.connection.rollback()

    def domakesavepoint(self, level):
        """Create a new savepoint inside a main transaction.

        This method is implemented as
        self.execsql('SAVEPOINT sp_%d' % level), but descendants can
        override it."""
        self.execsql('SAVEPOINT sp_%d' % level)

    def docommitsavepoint(self, level):
        """Commit an existing savepoint inside a main transaction.

        This method is implemented as
        self.execsql('RELEASE sp_%d' % level), but descendants can
        override it."""
        self.execsql('RELEASE sp_%d' % level)

    def dorollbacksavepoint(self, level):
        """Commit an existing savepoint inside a main transaction.

        This method is implemented as
        self.execsql('ROLLBACK TO sp_%d' % level), but descendants can
        override it."""
        self.execsql('ROLLBACK TO sp_%d' % level)

    #
    # General database metadata methods.
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

    def sequence_exists(self, schemaname, sequencename):
        """Tells if the given index exists."""
        raise NotImplementedError

    #
    # YASDL Support methods and attributes.
    #

    max_identifier_length = 31
    # No typemap in base class. Need to override!
    typemap = []
    _typemap_cache = None

    @classmethod
    def _cache_typemap(cls):
        cache = cls._typemap_cache = {}
        for item in cls.typemap:
            # Augment all types with all fields.
            if not "names" in item:
                item["names"] = {item["nativename"]}
            item["need_size"] = bool(item.get("need_size", False))
            item["need_precision"] = bool(item.get("need_precision", False))
            # Update name:type cache.
            for name in item["names"]:
                if name.lower() in cache:
                    raise NameError("Duplicate type for name %s." % name)
                else:
                    cache[name.lower()] = item
        if "identifier" not in cache:
            raise Exception("The 'identifier' type must be supported.")

    @classmethod
    def get_typeinfo(cls, name):
        """Get information about a type, given by its name."""
        if cls._typemap_cache is None:
            cls._cache_typemap()
        return cls._typemap_cache[name.lower()]

    @classmethod
    def hashname(cls, basename):
        """Convert a long name into an unique identifier.

        For details, see makename()."""
        if len(basename) > cls.max_identifier_length:
            tail = base64.b64encode(
                hashlib.sha256(basename.encode("UTF-8")).digest(), b"_$").decode("ascii")[:6]
            return basename[:cls.max_identifier_length - 8] + "__" + tail
        else:
            return basename

    @classmethod
    def makename(cls, *path):
        """Convert a path of definitions into a unique identifier-like name.

        :param *path: Any number of definitions or strings. But you must
            give at least one item. You can mix strings and definitions
            (their name will be used for generation).

        Requirements about this method:

            * It must limit the name to the maximum supported length
                of the underlying database
            * But it should not truncate the name if not necessary
            * When possible, the user should recognize the original
                path from the truncated name.
            * For different input parameters, it should return
                different output values.
            * Output values should be valid identifier-like names
                in the underlying database.

        In general, you should avoid using names that are so long that
        they have to be truncated.

        """
        assert path
        return cls.hashname(cls.name_separator.join([
            (isinstance(item, str) and item) or item.name
            for item in path]))

    @classmethod
    def makeschemaname(cls, schema):
        assert (isinstance(schema, ast.YASDLSchema))
        return cls.makename(*list(schema.package_name.items()))

    @classmethod
    def maketablename(cls, table):
        assert (isinstance(table, ast.YASDLFieldSet))
        assert (table.toplevel and table.realized)
        return cls.makename(table)

    @classmethod
    def makepkname(cls, table):
        assert (isinstance(table, ast.YASDLFieldSet))
        assert (table.toplevel and table.realized)
        return cls.makename("pk", cls.maketablename(table))

    @classmethod
    def makeindexname(cls, table, index):
        assert (isinstance(index, ast.YASDLIndex))
        # TODO: make sure that the index is inside the table
        assert (table.contains(index))
        assert (table.toplevel and table.realized)
        parts = [table.name, index.name]
        for idxfield in index.get_fields():
            parts += idxfield.refpath
        return cls.makename(*parts)

    @classmethod
    def makeconstraintname(cls, table, constraint):
        assert (isinstance(constraint, ast.YASDLConstraint))
        # TODO: make sure that the constraint is inside the table
        assert (table.contains(constraint))
        assert (table.toplevel and table.realized)
        return cls.makename(table.name, constraint.name)

    @classmethod
    def makefieldname(cls, fieldpath):
        return cls.makename(*fieldpath)

    @classmethod
    def makefkname(cls, schema, table, fieldpath):
        field = fieldpath[-1]
        assert (isinstance(schema, ast.YASDLSchema))
        assert (isinstance(table, ast.YASDLFieldSet))
        assert (isinstance(field, ast.YASDLField))
        assert (table.realized and table.toplevel_fieldset is table)
        assert field.realized
        reftbl = field.get_referenced_fieldset()
        assert reftbl
        parts = ["fk", table] + fieldpath
        # Target schema added only if it differs.
        # 2016-10-11 not anymore. It does not matter, the source path is unique for sure.
        # if reftbl.owner is not table.owner:
        #    parts.append(reftbl.owner)
        # parts.append(reftbl)
        return cls.makename(*parts)

    @classmethod
    def get_typespec(cls, field):
        """Get type specification of a field."""
        typ = field.get_type()
        try:
            typeinfo = cls.get_typeinfo(typ)
        except KeyError:
            raise TypeError(
                field.getpath() + ": " +
                "Type '%s' is not supported by this driver." % typ)

        if typeinfo["need_size"] and field.get_size() is None:
            raise AttributeError(
                field.getpath() + ": " +
                "Field of type '%s' must have a size given." % typ)

        if typeinfo["need_precision"] and field.get_precision() is None:
            raise AttributeError(
                field.getpath() + ": " +
                "Field of type '%s' must have a precision given." % typ)

        res = typeinfo["nativename"]
        size = field.get_size()
        prec = field.get_precision()
        if size is not None:
            res += "(%d" % size
            if prec is not None:
                res += ",%d" % prec
            res += ")"
        return res

    @classmethod
    def get_fieldspec(cls, field, include_constraints):
        """Create field specification.

        This includes: type, size, precision and not null constraint."""
        res = cls.get_typespec(field)
        if include_constraints:
            if field.get_notnull():
                res += " NOT NULL"
        # TODO: convert default value to SQL literal?
        defval = field.get_default()
        if defval is not None:
            if isinstance(defval, str):
                defval = "'%s'" % defval.replace("'", "\\'").replace("\\", "\\\\")
            res += " DEFAULT %s" % defval
        return res

    def yasdl_create_schema(self, instance, schema, sqlproc, options):
        sname = instance.get_schema_pname(schema)
        if not self.schema_exists(sname):
            sqlproc.addbuffer('CREATE SCHEMA "%s"' % sname)
            sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_create_table(self, instance, schema, table, sqlproc, options):
        assert (table.realized and table.toplevel_fieldset is table)
        sname = instance.get_schema_pname(schema)
        tname = instance.get_table_pname(table)
        sqlproc.addline('CREATE TABLE "%s"."%s" (' % (
            sname, tname))
        id_typedef = self.get_typeinfo("identifier")
        sqlproc.addline('  %s  %s NOT NULL,' % (
            '"id"'.ljust(30, " "), id_typedef["nativename"]))
        for fieldpath in table.itercontained([ast.YASDLField]):
            field = fieldpath[-1]
            if field.realized:
                fieldspec = self.get_fieldspec(field, False)
                reftbl = field.get_referenced_fieldset()
                comment = " -- " + ".".join([(
                        (isinstance(subitem, ast.YASDLSchema) and
                         subitem.package_name) or subitem.name)
                    for subitem in fieldpath])
                if reftbl:
                    comment += " -> " + reftbl.owner.getpath() + \
                               "." + reftbl.name
                fname = instance.get_field_pname(table, fieldpath)
                self.addline = sqlproc.addline(
                    "  %s  %s, %s" % (('"' + fname + '"').ljust(30, " "), (fieldspec).ljust(30, " "), comment), )
        pkname = instance.get_table_pkname(table)
        sqlproc.addline('  CONSTRAINT "%s" PRIMARY KEY ("id")' % pkname)
        sqlproc.addbuffer(")")
        sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_create_table_triggers(self, instance, schema, table, sqlproc, options):
        pass

    def yasdl_add_field(self, instance, table, fieldpath, sqlproc, options):
        """Create definition in SQL, with ALTER TABLE <table> ADD <fieldspec>

        :param instance: Schema instalce
        :type  instance: YASDLInstance
        :param table: A toplevel realized table.
        :type table: YASDLFieldSet
        :param fieldpath: Field path for a field member inside the table.
        :param sqlproc: An SQLProcessor instance.
        """
        sname = instance.get_schema_pname(table.owner_schema)
        tname = instance.get_table_pname(table)
        fname = instance.get_field_pname(table, fieldpath)
        sqlproc.addline('ALTER TABLE "%s"."%s"  ADD "%s" %s' % (
            sname, tname, fname, self.get_fieldspec(fieldpath[-1], False)))
        sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_field_drop_not_null(self, instance: "YASDLInstance", table: ast.YASDLFieldSet,
                                  fieldpath: ast.YASDLFieldPath, sqlproc, options):
        """Drop NOT NULL constraint on a field."""
        sname = instance.get_schema_pname(table.owner_schema)
        tname = instance.get_table_pname(table)
        fname = instance.get_field_pname(table, fieldpath)
        if self.column_exists(sname, tname, fname):
            sqlproc.addline('ALTER TABLE "%s"."%s"  ALTER COLUMN "%s" DROP NOT NULL' % (
                sname, tname, fname))
            sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_field_set_not_null(self, instance: "YASDLInstance", table: ast.YASDLFieldSet,
                                 fieldpath: ast.YASDLFieldPath, sqlproc, options):
        """SET NOT NULL constraint on a field."""
        sname = instance.get_schema_pname(table.owner_schema)
        tname = instance.get_table_pname(table)
        fname = instance.get_field_pname(table, fieldpath)
        if self.column_exists(sname, tname, fname):
            sqlproc.addline('ALTER TABLE "%s"."%s"  ALTER COLUMN "%s" SET NOT NULL' % (
                sname, tname, fname))
            sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_field_change_type(self, new_instance: "YASDLInstance", new_table: ast.YASDLFieldSet,
                                new_fieldpath: ast.YASDLFieldPath, sqlproc, options):
        sname = new_instance.get_schema_pname(new_table.owner_schema)
        tname = new_instance.get_table_pname(new_table)
        fname = new_instance.get_field_pname(new_table, new_fieldpath)
        if self.column_exists(sname, tname, fname):
            field = new_fieldpath[-1]
            typespec = self.get_typespec(field)
            sqlproc.addline('ALTER TABLE "%s"."%s"  ALTER COLUMN "%s" SET DATA TYPE %s' % (
                sname, tname, fname, typespec))
            sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_field_rename(self,
                           old_instance: "YASDLInstance", old_table: ast.YASDLFieldSet,
                           old_fieldpath: ast.YASDLFieldPath,
                           new_instance: "YASDLInstance", new_table: ast.YASDLFieldSet,
                           new_fieldpath: ast.YASDLFieldPath,
                           sqlproc, options):
        sname = new_instance.get_schema_pname(new_table.owner_schema)
        tname = new_instance.get_table_pname(new_table)
        old_fname = old_instance.get_field_pname(old_table, old_fieldpath)
        new_fname = new_instance.get_field_pname(new_table, new_fieldpath)
        sqlproc.addline('ALTER TABLE "%s"."%s"  RENAME COLUMN "%s" TO "%s"' % (
            sname, tname, old_fname, new_fname))
        sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_create_table_indexes(self, instance, schema, table, sqlproc, options):
        assert (table.realized and table.toplevel_fieldset is table)
        # Only create incides that are defined at outermost level.
        # So we use "members" here instead of "itercontained".
        for index in table.members:
            if isinstance(index, ast.YASDLIndex):
                self.yasdl_create_index(instance, schema, table, index, sqlproc, options)

    def yasdl_create_index(self, instance, schema, table, index, sqlproc, options):
        if index.get_unique():
            cmd = "CREATE UNIQUE INDEX"
        else:
            cmd = "CREATE INDEX"

        sname = instance.get_schema_pname(table.owner)
        tname = instance.get_table_pname(table)
        iname = instance.get_index_pname(table, index)

        fieldexprs = []
        for idxfieldsitem in index.get_fields().items:
            # Direction for this fields item
            if idxfieldsitem.direction == "desc":
                pdir = "DESC"
            else:
                pdir = "ASC"
            # Now we go through all YASDLField instances for this idxfieldsitem.
            fieldpath_prefix = idxfieldsitem.refpath
            container = fieldpath_prefix[-1]
            if isinstance(container, ast.YASDLField):
                # It is a simple YASDLField - add to index.
                fname = instance.get_field_pname(table, fieldpath_prefix)
                fieldexprs.append((fname, pdir))
            else:
                # It a YASDLFieldSet - iterate over its fields and add to index.
                for fieldpath_postfix in container.itercontained(min_classes=[ast.YASDLField]):
                    fname = instance.get_field_pname(table, fieldpath_prefix + fieldpath_postfix)
                    fieldexprs.append((fname, pdir))
        sqlproc.addbuffer('%s "%s" on "%s"."%s"(%s)' % (
            cmd, iname, sname, tname, ",".join([
                '"%s" %s' % (fname, direction)
                for fname, direction in fieldexprs])))
        sqlproc.processbuffer(options["ignore_exceptions"])
        # TODO: how to implement "ALTER TABLE table SET WITHOUT CLUSTER"?
        if (
                table.has_member("cluster") and
                len(table["cluster"].items) == 1 and
                table["cluster"].items[0].ref == index
        ):
            sqlproc.addbuffer('ALTER TABLE "%s"."%s" CLUSTER ON "%s"' % (
                sname, tname, iname))
            sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_create_table_constraints(self, instance, schema, table, sqlproc, options):
        """Create definition constraints in SQL.

        :param item: An YASDL instance.
        :param sqlproc: An SQLProcessor instance.
        """
        assert (isinstance(table, ast.YASDLFieldSet))
        assert (table.realized and table.toplevel_fieldset is table)
        sname = instance.get_schema_pname(table.owner)
        tname = instance.get_table_pname(table)
        for fieldpath in table.itercontained([ast.YASDLField]):
            field = fieldpath[-1]
            reftbl = field.get_referenced_fieldset()
            if reftbl:
                rsname = instance.get_schema_pname(reftbl.owner)
                rtname = instance.get_table_pname(reftbl)
                fname = instance.get_field_pname(table, fieldpath)
                fkname = instance.get_field_fkname(table, fieldpath)
                sqlproc.addline(
                    'ALTER TABLE "%s"."%s" ADD CONSTRAINT "%s" ' %
                    (sname, tname, fkname))

                ondelete = field.get_singleprop("ondelete", "noaction").lower()
                ondelete_kind = {"cascade": "CASCADE", "noaction": "NO ACTION", "setnull": "SET NULL",
                                 "fail": "NO ACTION"}.get(ondelete)
                ondelete_clause = "ON DELETE %s" % ondelete_kind

                deferrable = field.get_singleprop("deferrable", True)
                if deferrable:
                    deferrable_clause = "DEFERRABLE INITIALLY IMMEDIATE"
                else:
                    deferrable_clause = "NOT DEFERRABLE"

                sqlproc.addbuffer(
                    '  FOREIGN KEY ("%s") REFERENCES "%s"."%s"("id") %s %s' %
                    (fname, rsname, rtname, ondelete_clause, deferrable_clause))
                sqlproc.processbuffer(options["ignore_exceptions"])

        for constraint_path in table.itercontained([ast.YASDLConstraint]):
            constraint = constraint_path[-1]
            cname = instance.get_constraint_pname(table, constraint)
            chkprop = constraint["check"]  # TODO: what about non-check constraints?
            content = []
            for item in chkprop.items:
                if isinstance(item, ast.dotted_name):
                    field = item.ref
                    assert (isinstance(field, ast.YASDLField))
                    assert (table.contains(field))
                    # TODO: create a method that returns the physical name at once???
                    fpname = None
                    for fieldpath in table.itercontained([ast.YASDLField]):
                        if fieldpath[-1] is field:
                            fpname = instance.get_field_pname(table, fieldpath)
                            break
                    assert (fpname)
                    content.append('"' + fpname + '"')
                else:
                    content.append(item)

            sqlproc.addline(
                'ALTER TABLE "%s"."%s" ADD CONSTRAINT "%s" CHECK ' %
                (sname, tname, cname))
            sqlproc.addbuffer("".join(content))
            sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_create_all_field_constraints(self, instance, table, sqlproc, options):
        """Create all field level constraints for a table.

        :param item: An YASDL instance.
        :param sqlproc: An SQLProcessor instance.
        """
        assert (isinstance(table, ast.YASDLFieldSet))
        assert (table.realized and table.toplevel_fieldset is table)
        for fieldpath in table.itercontained([ast.YASDLField]):
            field = fieldpath[-1]
            if field.realized and field.get_notnull():
                self.yasdl_field_set_not_null(instance, table, fieldpath, sqlproc, options)

    def yasdl_create_table_comments(self, instance, schema, table, sqlproc, options):
        """Create misc things in SQL.

        :param instance: An YASDL instance.
        :param sqlproc: An SQLProcessor instance.
        """
        assert (isinstance(table, ast.YASDLFieldSet))
        assert (table.realized and table.toplevel_fieldset is table)
        sname = instance.get_schema_pname(table.owner)
        tname = instance.get_table_pname(table)
        comment = self.yasdl_get_comment_for_table(instance, table)
        sqlproc.addbuffer("""COMMENT ON TABLE "%s"."%s" IS %s""" % (
            sname, tname, self.escape_str(comment)))
        sqlproc.processbuffer(options["ignore_exceptions"])

        for fieldpath in table.itercontained([ast.YASDLField]):
            field = fieldpath[-1]
            comment = self.yasdl_get_comment_for_field(instance, table, field)
            fname = instance.get_field_pname(table, fieldpath)
            sqlproc.addbuffer(
                """COMMENT ON COLUMN "%s"."%s"."%s" IS %s""" %
                (sname, tname, fname, self.escape_str(comment)))
            sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_get_comment_for_table(self, instance, table):
        """Get comment for table generation.

        Default is to use the full path of the table as a comment."""
        return table.getpath()

    def yasdl_get_comment_for_field(self, instance, table, field):
        """Get comment for field generation.

        Default is to use the full path of the table as a comment."""
        comment = field.getpath()
        reftbl = field.get_referenced_fieldset()
        if reftbl:
            comment += " -> " + reftbl.getpath()
        return comment

    def yasdl_create_table_triggers(self, instance, schema, table, sqlproc, options):
        pass

    def yasdl_drop_table(self, instance, schema, table, sqlproc, options):
        """Drop table definition in SQL.

        :param table: A realized toplevel table.
        :param sqlproc: An SQLProcessor instance.
        """
        assert (isinstance(table, ast.YASDLFieldSet))
        assert (table.realized and table.toplevel_fieldset is table)
        sname = instance.get_schema_pname(table.owner)
        tname = instance.get_table_pname(table)
        if self.table_exists(sname, tname):
            # TODO: instead of DROP CASCADE, drop the constraints
            # explicitly!
            sqlproc.addbuffer(
                'DROP TABLE IF EXISTS "%s"."%s" CASCADE' % (sname, tname))
            sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_drop_field(self, instance, table, fieldpath, sqlproc, options):
        """Drop field definition in SQL, with ALTER TABLE <table> DROP <fieldname>

        :param instance: Schema instalce
        :type  instance: YASDLInstance
        :param table: A toplevel realized table.
        :type table: YASDLFieldSet
        :param fieldpath: Field path for a field member inside the table.
        :param sqlproc: An SQLProcessor instance.
        """
        field = fieldpath[-1]
        assert (isinstance(table, ast.YASDLFieldSet))
        assert (table.realized and table.toplevel_fieldset is table)
        assert (isinstance(field, ast.YASDLField))
        assert field.realized
        sname = instance.get_schema_pname(table.owner_schema)
        tname = instance.get_table_pname(table)
        cname = instance.get_field_pname(table, fieldpath)
        if self.column_exists(sname, tname, cname):
            if options["force"]:
                sqlproc.addbuffer(
                    'ALTER TABLE "%s"."%s" DROP COLUMN "%s" CASCADE' % (sname, tname, cname))
            else:
                sqlproc.addbuffer(
                    'ALTER TABLE "%s"."%s" DROP COLUMN "%s"' % (sname, tname, cname))
            sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_drop_table_triggers(self, instance, schema, table, sqlproc, options):
        pass

    def yasdl_drop_schema(self, instance, schema, sqlproc, options):
        """Drop schema definition in SQL.

        :param item: An YASDL instance.
        :param sqlproc: An SQLProcessor instance.
        """
        assert (isinstance(schema, ast.YASDLSchema))
        sname = instance.get_schema_pname(schema)
        if self.schema_exists(sname):
            if options["force"]:
                sqlproc.addbuffer('DROP SCHEMA IF EXISTS "%s" CASCADE' % sname)
            else:
                sqlproc.addbuffer('DROP SCHEMA IF EXISTS "%s"' % sname)
            sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_drop_table_indexes(self, instance, schema, table, sqlproc, options):
        assert (table.realized and table.toplevel_fieldset is table)
        # Only create incides that are defined at outermost level.
        # So we use "members" here instead of "itercontained".
        for index in table.members:
            if isinstance(index, ast.YASDLIndex):
                self.yasdl_drop_index(instance, schema, table, index, sqlproc, options)

    def yasdl_drop_index(self, instance, schema, table, index, sqlproc, options):
        cmd = "DROP INDEX IF EXISTS "
        sname = instance.get_schema_pname(table.owner_schema)
        iname = instance.get_index_pname(table, index)
        sqlproc.addbuffer('%s "%s"."%s"' % (cmd, sname, iname))
        sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_drop_table_constraints(self, instance, schema, table, sqlproc, options):
        """DROP definition constraints in SQL.

        :param item: An YASDL instance.
        :param sqlproc: An SQLProcessor instance.
        """
        assert (isinstance(table, ast.YASDLFieldSet))
        assert (table.realized and table.toplevel_fieldset is table)
        sname = instance.get_schema_pname(table.owner)
        tname = instance.get_table_pname(table)
        if self.table_exists(sname, tname):
            for fieldpath in table.itercontained([ast.YASDLField]):
                field = fieldpath[-1]
                reftbl = field.get_referenced_fieldset()
                if reftbl:
                    fkname = instance.get_field_fkname(table, fieldpath)
                    sqlproc.addline(
                        'ALTER TABLE "%s"."%s" DROP CONSTRAINT IF EXISTS "%s" ' %
                        (sname, tname, fkname))
                    sqlproc.processbuffer(options["ignore_exceptions"])

            for constraint_path in table.itercontained([ast.YASDLConstraint]):
                constraint = constraint_path[-1]
                cname = instance.get_constraint_pname(table, constraint)
                sqlproc.addline(
                    'ALTER TABLE "%s"."%s" DROP CONSTRAINT IF EXISTS "%s"' % (sname, tname, cname))
                sqlproc.processbuffer(options["ignore_exceptions"])

    def yasdl_drop_all_field_constraints(self, instance, table, sqlproc, options):
        """Drop all field level constraints for a table.

        :param item: An YASDL instance.
        :param sqlproc: An SQLProcessor instance.
        """
        assert (isinstance(table, ast.YASDLFieldSet))
        assert (table.realized and table.toplevel_fieldset is table)
        for fieldpath in table.itercontained([ast.YASDLField]):
            field = fieldpath[-1]
            if field.realized and field.get_notnull():
                self.yasdl_field_drop_not_null(instance, table, fieldpath, sqlproc, options)

    def escape_str(self, value):
        """Escape a string.

        :param value: A string or None
        :return: Value as a SQL literal.

        It can be used for SQL DDL generation. It should not be used for DML commands."""
        if value is None:
            return 'NULL'
        else:
            # TODO: Maybe %% is not a good thing to replace here?
            return "'" + str(value).replace("'", "''").replace('%', '%%') + "'"
