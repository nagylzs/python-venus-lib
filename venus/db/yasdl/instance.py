"""Create database instance from compiled YASDL schema set."""
from typing import Set, Dict, List, NamedTuple
import base64

from venus.db.dbo.connectionpool import ConnectionPool
from venus.db.yasdl import ast
from venus.db.yasdl.parser import YASDLParseResult
from venus.db.dbo.sqlprocessor import SQLProcessor
import venus.i18n

_ = venus.i18n.get_my_translator(__file__)

IGNORE_VENUS = False  # TODO: this is a hack, remove!
PARSED_SCHEMA_KEY = "parsed_schema"


class NotRealizedError(KeyError):
    """Raised when you try to access a not realized item."""
    pass


class YASDLUpgradeTablePair(NamedTuple):
    """Represents a pair of fieldsets, used for upgrading databases."""
    old_table: ast.YASDLFieldSet
    new_table: ast.YASDLFieldSet


class YASDLSchemaDiffResult(NamedTuple):
    """Represents a set of schemas to be dropped and to be created.

    Calculated by YASDLInstance.diff_schemas."""
    old_instance: "YASDLInstance"  # old instance to be upgraded
    new_instance: "YASDLInstance"  # new instance to be upgraded to
    old_schemas: Dict[str, ast.YASDLSchema]  # maps guid values to old schemas
    new_schemas: Dict[str, ast.YASDLSchema]  # maps guid values to new schemas
    to_drop: Set[str]  # set of guid values
    to_create: Set[str]  # set of guid values


class YASDLTableDiffResult(NamedTuple):
    """Represents sets of tables that needs to be dropped, create or upgraded in an instance that is to be upgraded.

    Calculated by YASDLInstance.diff_tables."""
    old_instance: "YASDLInstance"  # old instance to be upgraded
    new_instance: "YASDLInstance"  # new instance to be upgraded to
    old_tables: Dict[str, ast.YASDLFieldSet]  # maps guid values to old tables
    new_tables: Dict[str, ast.YASDLFieldSet]  # maps guid values to new tables
    common_tables: Dict[str, YASDLUpgradeTablePair]  # maps guid values to table pairs
    to_drop: Set[str]  # set of guid values
    to_create: Set[str]  # set of guid values


class YASDLFieldPathPair(NamedTuple):
    """Represent the old and the new version of a field path that is realized in a table that is to be upgraded."""
    old: List[ast.YASDLFieldPath]
    new: List[ast.YASDLFieldPath]


class YASDLFieldDiffResult(NamedTuple):
    """Contains all possible field level upgrades between the old and new version of a table that is to be upgraded.

    Calculated by YASDLInstance.diff_fields."""
    old_instance: "YASDLInstance"  # old instance to be upgraded
    new_instance: "YASDLInstance"  # new instance to be upgraded to
    old_table: ast.YASDLFieldSet
    new_table: ast.YASDLFieldSet
    to_drop: List[ast.YASDLFieldPath]  # New fields to be created
    to_create: List[ast.YASDLFieldPath]  # Old fields to be dropped
    to_rename: List[YASDLFieldPathPair]  # Fields to be renamed
    to_retype: List[YASDLFieldPathPair]  # Fields to be type changed
    to_drop_notnull: List[ast.YASDLFieldPath]  # Fields where not null constraint needs to be dropped
    to_create_notnull: List[ast.YASDLFieldPath]  # Fields where not null constraint needs to be create
    has_change: bool


class YASDLUpgradeContext(NamedTuple):
    old_instance: "YASDLInstance"
    new_instance: "YASDLInstance"
    schema_diff: YASDLSchemaDiffResult
    table_diff: YASDLTableDiffResult
    field_diffs: List[YASDLFieldDiffResult]
    sqlprocessor: SQLProcessor
    options: Dict


class YASDLInstance:
    """YASDL Instance representation.

    A YASDL instance is a concrete database that was created from a compiled YASDL schema set (or about to be
    created/destroyed now). A YASDLInstance encapsulates the parsed schema set, and also a connection pool to the
    database.

    Instances of this class are able to:

    * create the database using the database connection pool
    * drop the database using the database connection pool
    * upgrade the database using the old instance and the database connection pool
    * generate SQL scripts for later use for the above operations
    * provide an interface to access the database, by mapping YASDLDefinition objects to names of database objects.

    In the context of a YASDLInstance, we use the term "physical" refers to objects that are created in the database
    instance. Their names may be different from the names of the definitions they were created from. There is a
    mapping between physical names and definition names, accessible through get_*_pname() methods.

    Order of database object generation:

    * CREATE:
        * 01 before_all
        * 02 schema
        * 03 table
        * 04 data_raw - insert data before constraints, indexes or triggers are enabled
        * 05 constraint
        * 06 index
        * 07 trigger
        * 08 view
        * 09 comment
        * 10 data - insert data after triggers are enabled
        * 11 after_all

    * DROP:
        * 01 before_all
        * 02 data - before triggers are disabled
        * 03 comment
        * 04 view
        * 05 trigger
        * 06 constraint
        * 07 index
        * 08 data_raw - after triggers are disabled
        * 09 table
        * 10 schema

    * UPGRADE:

        * 10_create_toplevel - create new top-level objects
            * 10_upgrade_before_all - before anything is changed (upgrade_before_all)
			* 20_upgrade_create_schemas
			* 30_upgrade_create_tables
			* 40_upgrade_data_raw

		* 20_drop_inner - drop unwanted constraints indexes and triggers for old tables,
						and for existing tables that had any fields changed

			* 10_upgrade_drop_field_constraints
			* 20_upgrade_drop_table_constraints
			* 30_upgrade_drop_indexes
			* 40_upgrade_drop_triggers
			* 50_upgrade_drop_views

		* 30_upgrade_inner - upgrade fields

			* 10_upgrade_create_fields
			* 20_upgrade_change_field_types
			* 30_upgrade_drop_fields

		* 40 create_inner - for new tables, and for all tables that had any
				fields added/dropped/changed

			* 10_upgrade_create_table_constraints
			* 20_upgrade_create_field_constraints
			* 30_upgrade_create_indexes
			* 40_upgrade_create_triggers
			* 50_upgrade_create_views
			* 60_upgrade_create_comments
			* 70_upgrade_data

		* 50_drop_toplevel

			* 10_upgrade_drop_tables
			* 20_upgrade_drop_schemas

    """

    def __init__(self, parseresult: YASDLParseResult, connectionpool: ConnectionPool):
        """Create an YASDL instance.

        :param parseresult: An YASDLParseResult instance, that contains a successfully compiled schema set.
        :param connectionpool: A ConnectionPool or AsyncConnectionPool object.

        You can also pass None to parseresult. In that case, the definition of the database will be
        loaded from the database itself. See also `store_parsed` and `load_parsed`.
        """
        if parseresult is None:
            self.parsed = self.load_parsed(connectionpool)
        else:
            self.parsed = parseresult
        self.cpool = connectionpool
        # Make sure that physical name mappings are created.
        self._cache_pnames()

    def _cache_pnames(self):
        """Cache physical names.

        Create a cache that maps YASDL definition objects to physical database object names.
        This method is called automatically from the constructor.
        """
        # First we setup unique identifiers for all definition objects.
        # These are used for hashing them.
        self._pnames = {}
        self._pknames = {}
        self._fknames = {}
        self._idxnames = {}
        self._constraintnames = {}
        with self.cpool.open() as conn:
            for schema in self.parsed.iterate([ast.YASDLSchema]):
                # Schema name
                self._pnames[schema] = conn.makeschemaname(schema)

            # Table names and field names
            for schema, table in self.toplevel_realized_fieldsets():
                # for schema in self.parsed.iterate([ast.YASDLSchema]):
                #    for table in self.parsed.toplevel_fieldsets:
                #        if table.realized and table.owner is schema:
                self._pnames[table] = conn.maketablename(table)
                self._pknames[table] = conn.makepkname(table)
                self._cache_fields_pnames(conn, schema, table)
                self._cache_incides_pnames(conn, table)

    def _cache_fields_pnames(self, conn, schema, table):
        """Cache physical names of all realized fields of a top-level table."""
        for fieldpath in table.itercontained([ast.YASDLField]):
            field = fieldpath[-1]
            if field.realized:
                key = tuple([table] + fieldpath)
                # Normal field: store its physical name.
                self._pnames[key] = conn.makefieldname(fieldpath)
                reftbl = field.get_referenced_fieldset()
                if reftbl:
                    self._fknames[key] = conn.makefkname(
                        schema, table, fieldpath)

    def _cache_incides_pnames(self, conn, table):
        for member in table.members:
            if isinstance(member, ast.YASDLIndex):
                self._idxnames[(table, member)] = conn.makeindexname(table, member)
            if isinstance(member, ast.YASDLConstraint):
                self._constraintnames[(table, member)] = conn.makeconstraintname(table, member)

    def get_schema_pname(self, schema):
        """Get physical name for a schema.

        :param schema: The schema
        :type schema: YASDLSchema
        :return: Physical name of the schema
        :rtype: str
        """
        return self._pnames[schema]

    def get_table_pname(self, table):
        """Get physical name for a table.

        :param table: The table
        :type table: YASDLFieldSet
        :return: Physical name of the table
        :rtype: str

        If the table is not realized, then NotRealizedError is raised."""
        try:
            return self._pnames[table]
        except KeyError:
            raise NotRealizedError()

    def get_table_pkname(self, table):
        """Get primary key constraint name for a table.

        :param table: The table
        :type table: YASDLFieldSet
        :return: Physical name of the table's primary key constraint.
        :rtype: str

        If the table is not realized, then NotRealizedError is raised."""
        try:
            return self._pknames[table]
        except KeyError:
            raise NotRealizedError()

    def get_field_pname(self, table, fieldpath):
        """Get physical name for a field.

        :param table: realized top-level YASDLField definition
        :param fieldpath: Path to the field in the compilation relative to the top-level fieldset.
            The path is a list containing YASDLDefinition items, as returned by itercontained().
            Last item in the path must be a YASDLField instance. Passing the full path is required because a single
            definition can be contained inside a table multiple times.
        :return: It returns the physical name of the field in the database.

        If the field is not realized, then NotRealizedError is raised."""
        try:
            return self._pnames[tuple([table] + fieldpath)]
        except KeyError:
            raise NotRealizedError(table.getpath() + " " + fieldpath[-1].getpath())

    def get_index_pname(self, table, index):
        """Get physical name for an index.

        :param table: realized top-level YASDLTable definition
        :param index: a YASDLIndex instance that belongs to the table

        If the index is not realized, then NotRealizedError is raised. You need to pass the table too because the
        same YASDLIndex can be inherited by several fieldsets, so the name of the YASDLIndex is not unique alone,
        only together with its container table. """
        try:
            return self._idxnames[(table, index)]
        except KeyError:
            raise NotRealizedError()

    def get_constraint_pname(self, table, constraint):
        """Get physical name for a constraint.

        :param table: realized top-level YASDLTable definition
        :param constraint: a YASDLConstraint instance that belongs to the table

        If the constraint is not realized, then NotRealizedError is raised. You need to pass the table too because the
        same YASDLConstraint can be inherited by several fieldsets, so the name of the YASDLConstraint is not unique
        alone, only together with its container table. """
        try:
            return self._constraintnames[(table, constraint)]
        except KeyError:
            raise NotRealizedError()

    def get_field_fkname(self, table, fieldpath):
        """Get physical name for a foreign key constraint.

        :param table: realized top-level YASDLField definition
        :param fieldpath: Path to the field in the compilation relative to the top-level fieldset.
            The path is a list containing YASDLDefinition items, as returned by itercontained().
            Last item in the path must be a YASDLField instance. Passing the full path is required because a single
            definition can be contained inside a table multiple times.

        If the field is not realized, then NotRealizedError is raised. If the field is not referencing to a
        fieldset, then None is returned. Otherwise the physical name for the foreign key field constraint is
        returned.
        """
        if not fieldpath[-1].realized:
            raise NotRealizedError()
        try:
            return self._fknames[tuple([table] + fieldpath)]
        except KeyError:
            return None

    def toplevel_realized_fieldsets(self) -> (ast.YASDLSchema, ast.YASDLFieldSet):
        """Generator that iterates over realized toplevel fieldsets."""
        for schema in self.parsed.iterate([ast.YASDLSchema]):
            for table in self.parsed.toplevel_fieldsets:
                if table.realized and table.owner is schema:
                    yield schema, table

    def schemas_with_toplevel_realized_fieldsets(self):
        """Yield a list of schemas that have at least one toplevel fieldset."""
        for schema in set([scm for scm, tbl in self.toplevel_realized_fieldsets()]):
            yield schema

    def get_fk_referers(self, ref_to_table):
        """Iterate over realized fields that reference the given table.

        :param instance: Compiled YASDLInstance
        :param ref_to_table: A table we search foreign key references for.
        :return: This is a generator that yields (schema, table, fieldpath) tuples.
            The last element in the fieldpath is the field that references ref_to_table with foreign key.
            Only realized fields of realized tables are yielded.
        """
        for schema, table in self.toplevel_realized_fieldsets():
            if schema.getpath().startswith("venus."):
                continue
            for fieldno, fieldpath in enumerate(table.itercontained([ast.YASDLField])):
                field = fieldpath[-1]
                if field.realized:
                    if field.get_referenced_fieldset() is ref_to_table:
                        yield (schema, table, fieldpath)

    def create_before_all(self, sqlprocessor, options):
        """Before anything is created.

        The default implementation does nothing."""
        pass

    def create_schemas(self, sqlprocessor, options):
        """Create schemas, but only for the ones that have realized toplevel fieldsets."""
        for scm in self.schemas_with_toplevel_realized_fieldsets():
            with self.cpool.open() as conn:
                conn.yasdl_create_schema(self, scm, sqlprocessor, options)

    def create_tables(self, sqlprocessor, options):
        """Create tables for realized toplevel fieldset definitions."""
        for scm, tbl in self.toplevel_realized_fieldsets():
            with self.cpool.open() as conn:
                conn.yasdl_create_table(
                    self, scm, tbl, sqlprocessor, options)

    def create_data_raw(self, sqlprocessor, options):
        """Create raw data before constraints, indexes or triggers are enabled.

        The default implementation does nothing."""
        pass

    def create_constraints(self, sqlprocessor, options):
        """Create constraints for all tables.

        This method is called after initial rows have been added."""
        for scm, tbl in self.toplevel_realized_fieldsets():
            with self.cpool.open() as conn:
                conn.yasdl_create_table_constraints(
                    self, scm, tbl, sqlprocessor, options)
                conn.yasdl_create_all_field_constraints(self, tbl, sqlprocessor, options)

    def create_indexes(self, sqlprocessor, options):
        """Create indexes for all tables.

        This method is called after initial rows have been added."""
        for scm, tbl in self.toplevel_realized_fieldsets():
            with self.cpool.open() as conn:
                conn.yasdl_create_table_indexes(self, scm, tbl, sqlprocessor, options)

    def create_triggers(self, sqlprocessor, options):
        """Create triggers on all tables and their fields."""
        for scm, tbl in self.toplevel_realized_fieldsets():
            with self.cpool.open() as conn:
                conn.yasdl_create_table_triggers(self, scm, tbl, sqlprocessor, options)

    def create_views(self, sqlprocessor, options):
        """Create views for realized toplevel fieldset definitions.

        The default implementation does nothing."""
        pass

    def create_comments(self, sqlprocessor, options):
        """Create comments on all tables and their fields."""
        for scm, tbl in self.toplevel_realized_fieldsets():
            with self.cpool.open() as conn:
                conn.yasdl_create_table_comments(
                    self, scm, tbl, sqlprocessor, options)

    def create_data(self, sqlprocessor, options):
        """Manipulate data after constraints, indexes or triggers are enabled.

        The default implementation does nothing."""
        pass

    def create_after_all(self, sqlprocessor, options):
        """Manipulate data after constraints, indexes or triggers are enabled.

        The default implementation does nothing."""
        pass

    def create(self, sqlprocessor, options=None):
        """Create objects in a database.

        :param sqlprocessor: SQLProcessor object. This will be used for executing SQL commands.
        :param options: When given, it should be a dict with options.

        Currently only the ``ignore_exceptions`` option is supported:

        * ignore_exceptions=True - ignore exceptions (raised by SQLProcessor)
        * ignore_exceptions=False - do not ignore exceptions (default)

        """
        if options is None:
            options = {}
        options["ignore_exceptions"] = options.get("ignore_exceptions", False)

        self.create_before_all(sqlprocessor, options)
        self.create_schemas(sqlprocessor, options)
        self.create_tables(sqlprocessor, options)
        self.create_data_raw(sqlprocessor, options)
        self.create_constraints(sqlprocessor, options)
        self.create_indexes(sqlprocessor, options)
        self.create_triggers(sqlprocessor, options)
        self.create_views(sqlprocessor, options)
        self.create_comments(sqlprocessor, options)
        self.create_data(sqlprocessor, options)
        self.create_after_all(sqlprocessor, options)

    def drop_before_all(self, sqlprocessor, options):
        """Before anything is dropped.

        The default implementation does nothing."""
        pass

    def drop_data(self, sqlprocessor, options):
        """Manipulate raw data before constraints, indexes or triggers are disabled.

        The default implementation does nothing."""
        pass

    def drop_comments(self, sqlprocessor, options):
        """Drop comments

        The default implementation does nothing."""
        pass

    def drop_views(self, sqlprocessor, options):
        """Drop all views for all tables.

        The default implementation does nothing."""
        pass

    def drop_triggers(self, sqlprocessor, options):
        """Drop all triggers for all tables."""
        for scm, tbl in self.toplevel_realized_fieldsets():
            with self.cpool.open() as conn:
                conn.yasdl_drop_table_triggers(
                    self, scm, tbl, sqlprocessor, options)

    def drop_constraints(self, sqlprocessor, options):
        """Drop all constraints for all tables."""
        for scm, tbl in self.toplevel_realized_fieldsets():
            if not IGNORE_VENUS or scm.getpath() != "venus.core":
                with self.cpool.open() as conn:
                    conn.yasdl_drop_table_constraints(
                        self, scm, tbl, sqlprocessor, options)
                    conn.yasdl_drop_all_field_constraints(self, tbl, sqlprocessor, options)

    def drop_indexes(self, sqlprocessor, options):
        """Drop all indexes for all tables."""
        for scm, tbl in self.toplevel_realized_fieldsets():
            if not IGNORE_VENUS or scm.getpath() != "venus.core":
                with self.cpool.open() as conn:
                    conn.yasdl_drop_table_indexes(
                        self, scm, tbl, sqlprocessor, options)

    def drop_data_raw(self, sqlprocessor, options):
        """Manipulate raw data after constraints, indexes or triggers are disabled.

        The default implementation does nothing."""
        pass

    def drop_tables(self, sqlprocessor, options):
        """Drop all tables."""
        for scm, tbl in self.toplevel_realized_fieldsets():
            if not IGNORE_VENUS or scm.getpath() != "venus.core":
                with self.cpool.open() as conn:
                    conn.yasdl_drop_table(
                        self, scm, tbl, sqlprocessor, options)

    def drop_schemas(self, sqlprocessor, options):
        """Drop all schemas."""
        for schema in self.parsed.iterate([ast.YASDLSchema]):
            with self.cpool.open() as conn:
                conn.yasdl_drop_schema(
                    self, schema, sqlprocessor, options)

    def drop_after_all(self, sqlprocessor, options):
        """Before after all is dropped.

        The default implementation does nothing."""
        pass

    def drop(self, sqlprocessor, options=None):
        """Drop objects in a database instance.

        :param sqlprocessor: SQLProcessor object. This will be used for executing SQL commands.
        :param options: When given, it should be a dict with options.

        Currently only the ``ignore_exceptions`` option is supported:

        * ignore_exceptions=True - ignore exceptions (raised by SQLProcessor)
        * ignore_exceptions=False - do not ignore exceptions (default)
        * force=False             - force drop, this will directly drop all schemas and not execute
                                    anything else.

        Note: the factory's connectionpool will be used to check existence of database objects.
        Only existent objects will be dropped.
        """
        # Drop constraints
        # Right now, they are dropped with cascaded table drops...
        if options is None:
            options = {}
        options["ignore_exceptions"] = options.get("ignore_exceptions", False)

        if options["force"]:
            self.drop_schemas(sqlprocessor, options)
        else:
            self.drop_before_all(sqlprocessor, options)
            self.drop_data(sqlprocessor, options)
            self.drop_comments(sqlprocessor, options)
            self.drop_views(sqlprocessor, options)
            self.drop_triggers(sqlprocessor, options)
            self.drop_constraints(sqlprocessor, options)
            self.drop_indexes(sqlprocessor, options)
            self.drop_data_raw(sqlprocessor, options)
            self.drop_tables(sqlprocessor, options)
            self.drop_schemas(sqlprocessor, options)
            self.drop_after_all(sqlprocessor, options)

    @classmethod
    def diff_schemas(cls, old_instance: "YASDLInstance", new_instance: "YASDLInstance") -> YASDLSchemaDiffResult:
        """Calculate the schemas that need to dropped and created."""
        new_schemas = {scm.get_guid(): scm for scm in new_instance.schemas_with_toplevel_realized_fieldsets()}
        old_schemas = {scm.get_guid(): scm for scm in old_instance.schemas_with_toplevel_realized_fieldsets()}

        scm_to_create = set(new_schemas.keys()) - set(old_schemas.keys())
        scm_to_drop = set(old_schemas.keys()) - set(new_schemas.keys())

        return YASDLSchemaDiffResult(old_instance, new_instance, old_schemas, new_schemas, scm_to_drop, scm_to_create)

    @classmethod
    def diff_tables(cls, old_instance: "YASDLInstance", new_instance: "YASDLInstance") -> YASDLTableDiffResult:
        """Calculate tables that need to be dropped, upgraded and created."""
        new_tables = {tbl.get_guid(): tbl for scm, tbl in new_instance.toplevel_realized_fieldsets()}
        old_tables = {tbl.get_guid(): tbl for scm, tbl in old_instance.toplevel_realized_fieldsets()}

        new_guids = set(new_tables.keys())
        old_guids = set(old_tables.keys())

        to_create = new_guids - old_guids
        to_drop = old_guids - new_guids
        common = old_guids & new_guids

        common_tables = {guid: YASDLUpgradeTablePair(old_tables[guid], new_tables[guid]) for guid in common}

        return YASDLTableDiffResult(old_instance, new_instance, old_tables, new_tables, common_tables, to_drop,
                                    to_create)

    @classmethod
    def diff_fields(cls, table_diff: YASDLTableDiffResult) -> List[YASDLFieldDiffResult]:
        """Calculate field level upgrades for tables that are common to the old and the new schema (of an upgrade)."""
        result = []

        # Go over all common table pairs
        for guid, (old_table, new_table) in table_diff.common_tables.items():
            # We need to check for field changes only if the table is present in the
            # old and the new version too.
            old_schema, new_schema = old_table.owner_schema, new_table.owner_schema
            if not IGNORE_VENUS or new_schema.getpath() != "venus.core":
                if old_schema.getpath() != new_schema.getpath():
                    raise Exception("Moving tables between schemas is not supported. (Not even in SQL anyway...)")

                # Field paths in the new table, keyed by physical name
                new_fields_by_pname = {}
                field_pname_order = []
                for fieldpath in new_table.itercontained([ast.YASDLField]):
                    field = fieldpath[-1]
                    if field.realized:
                        pname = table_diff.new_instance.get_field_pname(new_table, fieldpath)
                        new_fields_by_pname[pname] = fieldpath
                        field_pname_order.append(pname)

                # Field paths in the old table, keyed by physical name
                old_fields_by_pname = {}
                for fieldpath in old_table.itercontained([ast.YASDLField]):
                    field = fieldpath[-1]
                    if field.realized:
                        pname = table_diff.old_instance.get_field_pname(old_table, fieldpath)
                        old_fields_by_pname[pname] = fieldpath
                        if pname not in field_pname_order:
                            field_pname_order.append(pname)

                # All physical field names in old and new tables
                old_field_pnames = set(old_fields_by_pname.keys())
                new_field_pnames = set(new_fields_by_pname.keys())

                # Fields to be created, dropped and upgraded
                to_drop = old_field_pnames - new_field_pnames
                to_create = new_field_pnames - old_field_pnames
                to_upgrade = new_field_pnames & old_field_pnames

                # Calculate field paths in the good order.
                to_drop_paths = []
                to_create_paths = []
                for pname in field_pname_order:
                    if pname in to_drop:
                        to_drop_paths.append(old_fields_by_pname[pname])
                    if pname in to_create:
                        to_create_paths.append(new_fields_by_pname[pname])

                # TODO: the to_rename remains empty until we can identify fields with guids.
                # Right not, it is not implemented, and they are identified by their physical names.
                # So renaming won't ever happen.
                to_rename = []
                to_retype = []
                to_drop_notnull = []
                to_create_notnull = []

                # Process fields to be upgraded
                for pname in to_upgrade:
                    old_upg_fieldpath = old_fields_by_pname[pname]
                    new_upg_fieldpath = new_fields_by_pname[pname]
                    path_pair = YASDLFieldPathPair(old_upg_fieldpath, new_upg_fieldpath)
                    old_field = old_upg_fieldpath[-1]
                    new_field = new_upg_fieldpath[-1]
                    with table_diff.old_instance.cpool.open() as oldconn:
                        with table_diff.new_instance.cpool.open() as newconn:
                            old_typespec = oldconn.get_typespec(old_field)
                            new_typespec = newconn.get_typespec(new_field)
                            if old_typespec != new_typespec:
                                to_retype.append(path_pair)
                            old_notnull = old_field.get_notnull()
                            new_notnull = new_field.get_notnull()
                            if old_notnull and not new_notnull:
                                to_drop_notnull.append(old_upg_fieldpath)
                            if not old_notnull and new_notnull:
                                to_create_notnull.append(new_upg_fieldpath)

                # Process fields to be added
                for pname in to_create:
                    new_upg_fieldpath = new_fields_by_pname[pname]
                    new_field = new_upg_fieldpath[-1]
                    new_notnull = new_field.get_notnull()
                    if new_notnull:
                        to_create_notnull.append(new_upg_fieldpath)

                # Process fields to be dropped
                for pname in to_drop:
                    old_upg_fieldpath = old_fields_by_pname[pname]
                    old_field = old_upg_fieldpath[-1]
                    old_notnull = old_field.get_notnull()
                    if old_notnull:
                        to_drop_notnull.append(old_upg_fieldpath)

                has_change = bool(
                    to_drop_paths or to_create_paths or to_rename or to_retype or to_drop_notnull or to_create_notnull)
                result.append(YASDLFieldDiffResult(table_diff.old_instance, table_diff.new_instance,
                                                   old_table, new_table,
                                                   to_drop_paths, to_create_paths,
                                                   to_rename, to_retype,
                                                   to_drop_notnull, to_create_notnull, has_change))

        return result

    @classmethod
    def calc_upgrade_context(cls, old_instance: "YASDLInstance", new_instance: "YASDLInstance",
                             sqlprocessor: SQLProcessor, options: Dict):
        schema_diff = cls.diff_schemas(old_instance, new_instance)
        table_diff = cls.diff_tables(old_instance, new_instance)
        field_diffs = cls.diff_fields(table_diff)
        return YASDLUpgradeContext(old_instance, new_instance, schema_diff, table_diff, field_diffs, sqlprocessor,
                                   options)

    @classmethod
    def upgrade(cls, old_instance: "YASDLInstance", new_instance: "YASDLInstance", sqlprocessor, options=None):
        """Upgrade objects in a database.

        :param old_instance: The old database instance, as it was created in the old version.
            Hint: you can use `load_parsed` to load the YASDLParseResult of the database,
            and create a new YASDLInstance from that. See `store_parsed` and `load_parsed` for details.
        :param new_instance: The new database instance, in most cases you will pass the result of a new
            compilation here.

        :param sqlprocessor: SQLProcessor object. This will be used for executing SQL commands.
        :param options: When given, it should be a dict with options.

        Currently only the ``ignore_exceptions`` option is supported:

        * ignore_exceptions=True - ignore exceptions (raised by SQLProcessor)
        * ignore_exceptions=False - do not ignore exceptions (default)

        This method will calculate all differences between the old and the new instance, and execute all methods
        that are required to upgrade the schema from the old version to the new version.

        """
        if options is None:
            options = {}
        options["ignore_exceptions"] = options.get("ignore_exceptions", False)

        upgrade_context = cls.calc_upgrade_context(old_instance, new_instance, sqlprocessor, options)

        #
        # 01 create_toplevel
        #
        cls.upgrade_before_all(upgrade_context)
        cls.upgrade_create_schemas(upgrade_context)  # Create new schemas
        cls.upgrade_create_tables(upgrade_context)  # Create new tables
        cls.upgrade_data_raw(upgrade_context)  # For new tables, without triggers

        #
        # 02 drop_inner
        #
        cls.upgrade_drop_field_constraints(upgrade_context)
        cls.upgrade_drop_table_constraints(upgrade_context)  # Drop table level constraints
        # TODO: what about tables that only had indexes changed???
        cls.upgrade_drop_indexes(upgrade_context)  # For tables with fields changed or to be dropped
        cls.upgrade_drop_triggers(upgrade_context)
        cls.upgrade_drop_views(upgrade_context)

        #
        # 30 upgrade_inner
        #
        cls.upgrade_create_fields(upgrade_context)  # Create new fields
        cls.upgrade_change_field_types(upgrade_context)  # Change field types
        cls.upgrade_drop_fields(upgrade_context)  # Drop old fields

        #
        # 40 create_inner
        #
        cls.upgrade_create_table_constraints(upgrade_context)
        cls.upgrade_create_field_constraints(upgrade_context)
        # TODO: what about tables that only had indexes changed???
        cls.upgrade_create_indexes(upgrade_context)
        cls.upgrade_create_triggers(upgrade_context)
        cls.upgrade_create_views(upgrade_context)
        cls.upgrade_create_comments(upgrade_context)
        # TODO: what about index changes?
        cls.upgrade_data(upgrade_context)  # For new tables, with triggers

        #
        # 50 drop_toplevel
        #
        cls.upgrade_drop_tables(upgrade_context)  # Drop unwanted tables
        cls.upgrade_drop_schemas(upgrade_context)  # Drop unused schemas

    @classmethod
    def upgrade_before_all(self, upgrade_context: YASDLUpgradeContext):
        """Before anything is created in the upgrade process.

        The default implementation does nothing."""
        pass

    @classmethod
    def upgrade_create_schemas(cls, upgrade_context: YASDLUpgradeContext):
        """Create new schemas."""
        schema_diff = upgrade_context.schema_diff
        new_instance = upgrade_context.new_instance
        with new_instance.cpool.open() as conn:
            for guid in schema_diff.to_create:
                conn.yasdl_create_schema(new_instance, schema_diff.new_schemas[guid],
                                         upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_drop_schemas(cls, upgrade_context: YASDLUpgradeContext):
        """Drop old schemas, but only for the ones that have realized toplevel fieldsets."""
        schema_diff = upgrade_context.schema_diff
        old_instance = upgrade_context.old_instance
        with old_instance.cpool.open() as conn:
            for guid in schema_diff.to_drop:
                conn.yasdl_drop_schema(old_instance, schema_diff.old_schemas[guid],
                                       upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_create_tables(cls, upgrade_context: YASDLUpgradeContext):
        """Upgrade tables, but only for the ones that have realized toplevel fieldsets.

        By passing create=True or drop=True, you can create new tables and drop old tables.
        """
        table_diff = upgrade_context.table_diff
        new_instance = upgrade_context.new_instance
        with new_instance.cpool.open() as conn:
            for guid in table_diff.to_create:
                tbl = table_diff.new_tables[guid]
                conn.yasdl_create_table(new_instance, tbl.owner_schema, tbl,
                                        upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_drop_tables(cls, upgrade_context: YASDLUpgradeContext):
        """Upgrade tables, but only for the ones that have realized toplevel fieldsets.

        By passing create=True or drop=True, you can create new tables and drop old tables.
        """
        table_diff = upgrade_context.table_diff
        old_instance = upgrade_context.old_instance
        with old_instance.cpool.open() as conn:
            for guid in table_diff.to_drop:
                tbl = table_diff.old_tables[guid]
                conn.yasdl_drop_table(table_diff.old_instance, tbl.owner_schema, tbl,
                                      upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_data_raw(cls, upgrade_context: YASDLUpgradeContext):
        """Raw data for new tables, before triggers indexes and constraints are added to new tables."""
        pass

    @classmethod
    def upgrade_drop_field_constraints(cls, upgrade_context: YASDLUpgradeContext):
        """Drop unwanted field level (not null) constraints."""
        instance = upgrade_context.old_instance

        for field_diff in upgrade_context.field_diffs:
            with instance.cpool.open() as conn:
                for fieldpath in field_diff.to_drop_notnull:
                    conn.yasdl_field_drop_not_null(instance, field_diff.old_table, fieldpath,
                                                   upgrade_context.sqlprocessor, upgrade_context.options)


        for guid in upgrade_context.table_diff.to_drop:
            old_table = upgrade_context.table_diff.old_tables[guid]
            with instance.cpool.open() as conn:
                conn.yasdl_drop_all_field_constraints(instance, old_table,
                                                        upgrade_context.sqlprocessor, upgrade_context.options)


    @classmethod
    def upgrade_drop_table_constraints(cls, upgrade_context: YASDLUpgradeContext):
        """Drop table level constraints for all tables that have any field level changes."""
        instance = upgrade_context.old_instance
        for field_diff in upgrade_context.field_diffs:
            if field_diff.has_change:
                table = field_diff.old_table
                schema = table.owner_schema
                if not IGNORE_VENUS or schema.getpath() != "venus.core":
                    with instance.cpool.open() as conn:
                        conn.yasdl_drop_table_constraints(
                            instance, schema, table,
                            upgrade_context.sqlprocessor, upgrade_context.options)


        for guid in upgrade_context.table_diff.to_drop:
            old_table = upgrade_context.table_diff.old_tables[guid]
            with instance.cpool.open() as conn:
                conn.yasdl_drop_table_constraints(instance, old_table.owner_schema, old_table,
                                                  upgrade_context.sqlprocessor, upgrade_context.options)


    @classmethod
    def upgrade_drop_indexes(cls, upgrade_context: YASDLUpgradeContext):
        """Drop indexes for all tables that have any field level changes."""
        for field_diff in upgrade_context.field_diffs:
            if field_diff.has_change:
                table = field_diff.old_table
                schema = table.owner_schema
                if not IGNORE_VENUS or schema.getpath() != "venus.core":
                    with field_diff.old_instance.cpool.open() as conn:
                        conn.yasdl_drop_table_indexes(
                            field_diff.old_instance, schema, table,
                            upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_drop_triggers(cls, upgrade_context: YASDLUpgradeContext):
        """Drop triggers for all tables that had any fields changed PLUS for all tables that will be dropped."""
        dropped = set([])

        # Tables with any field level changes
        for field_diff in upgrade_context.field_diffs:
            if field_diff.has_change:
                table = field_diff.old_table
                schema = table.owner_schema
                if not IGNORE_VENUS or schema.getpath() != "venus.core":
                    dropped.add(table)
                    with field_diff.old_instance.cpool.open() as conn:
                        conn.yasdl_drop_table_triggers(
                            field_diff.old_instance, schema, table,
                            upgrade_context.sqlprocessor, upgrade_context.options)

        # Tables that will be dropped
        table_diff = upgrade_context.table_diff
        old_instance = upgrade_context.old_instance
        for guid in table_diff.to_drop:
            table = table_diff.old_tables[guid]
            if table not in dropped:
                schema = table.owner_schema
                if not IGNORE_VENUS or schema.getpath() != "venus.core":
                    dropped.add(table)
                    with old_instance.cpool.open() as conn:
                        conn.yasdl_drop_table_triggers(
                            old_instance, schema, table,
                            upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_drop_views(cls, upgrade_context: YASDLUpgradeContext):
        """Drop views for all tables that had any fields changed PLUS for all tables that will be dropped."""
        pass

    @classmethod
    def upgrade_create_fields(cls, upgrade_context: YASDLUpgradeContext):
        """Create new fields in existing tables."""
        for field_diff in upgrade_context.field_diffs:
            for field_path in field_diff.to_create:
                table = field_diff.new_table
                schema = table.owner_schema
                if not IGNORE_VENUS or schema.getpath() != "venus.core":
                    with field_diff.new_instance.cpool.open() as conn:
                        conn.yasdl_add_field(field_diff.new_instance, table, field_path,
                                             upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_change_field_types(cls, upgrade_context: YASDLUpgradeContext):
        """Change field types in existing tables."""
        for field_diff in upgrade_context.field_diffs:
            for old_field_path, new_field_path in field_diff.to_retype:
                new_table = field_diff.new_table
                new_schema = new_table.owner_schema
                if not IGNORE_VENUS or new_schema.getpath() != "venus.core":
                    with field_diff.new_instance.cpool.open() as conn:
                        conn.yasdl_field_change_type(field_diff.new_instance, new_table, new_field_path,
                                                     upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_drop_fields(cls, upgrade_context: YASDLUpgradeContext):
        """Change field types in existing tables."""
        for field_diff in upgrade_context.field_diffs:
            for field_path in field_diff.to_drop:
                table = field_diff.old_table
                schema = table.owner_schema
                if not IGNORE_VENUS or schema.getpath() != "venus.core":
                    with field_diff.old_instance.cpool.open() as conn:
                        conn.yasdl_drop_field(field_diff.old_instance, table, field_path,
                                              upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_create_table_constraints(cls, upgrade_context: YASDLUpgradeContext):
        """Create table level constraints for all tables that have any field level changes."""
        instance = upgrade_context.new_instance
        for field_diff in upgrade_context.field_diffs:
            if field_diff.has_change:
                table = field_diff.new_table
                schema = table.owner_schema
                if not IGNORE_VENUS or schema.getpath() != "venus.core":
                    with instance.cpool.open() as conn:
                        conn.yasdl_create_table_constraints(
                            instance, schema, table,
                            upgrade_context.sqlprocessor, upgrade_context.options)

        for guid in upgrade_context.table_diff.to_create:
            new_table = upgrade_context.table_diff.new_tables[guid]
            with instance.cpool.open() as conn:
                conn.yasdl_create_table_constraints(instance, new_table.owner_schema, new_table,
                                                    upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_create_field_constraints(cls, upgrade_context: YASDLUpgradeContext):
        """Create new field level (not null) constraints."""
        instance = upgrade_context.new_instance

        for field_diff in upgrade_context.field_diffs:
            with instance.cpool.open() as conn:
                for fieldpath in field_diff.to_create_notnull:
                    conn.yasdl_field_set_not_null(instance, field_diff.new_table, fieldpath,
                                                  upgrade_context.sqlprocessor, upgrade_context.options)

        for guid in upgrade_context.table_diff.to_create:
            new_table = upgrade_context.table_diff.new_tables[guid]
            with instance.cpool.open() as conn:
                conn.yasdl_create_all_field_constraints(instance, new_table,
                                                        upgrade_context.sqlprocessor, upgrade_context.options)


    @classmethod
    def upgrade_create_indexes(cls, upgrade_context: YASDLUpgradeContext):
        """Create indexes for all tables that have any field level changes."""
        created = set([])
        for field_diff in upgrade_context.field_diffs:
            if field_diff.has_change:
                table = field_diff.new_table
                schema = table.owner_schema
                if not IGNORE_VENUS or schema.getpath() != "venus.core":
                    created.add(table)
                    with field_diff.new_instance.cpool.open() as conn:
                        conn.yasdl_create_table_indexes(
                            field_diff.new_instance, schema, table,
                            upgrade_context.sqlprocessor, upgrade_context.options)

        # Tables that will were created
        table_diff = upgrade_context.table_diff
        new_instance = upgrade_context.new_instance
        for guid in table_diff.to_create:
            table = table_diff.new_tables[guid]
            if table not in created:
                schema = table.owner_schema
                if not IGNORE_VENUS or schema.getpath() != "venus.core":
                    created.add(table)
                    with new_instance.cpool.open() as conn:
                        conn.yasdl_create_table_indexes(new_instance, schema, table,
                                                         upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_create_triggers(cls, upgrade_context: YASDLUpgradeContext):
        """Create triggers for all tables that had any fields changed PLUS for all tables that will be dropped."""
        created = set([])

        # Tables with any field level changes
        for field_diff in upgrade_context.field_diffs:
            if field_diff.has_change:
                table = field_diff.new_table
                schema = table.owner_schema
                if not IGNORE_VENUS or schema.getpath() != "venus.core":
                    created.add(table)
                    with field_diff.new_instance.cpool.open() as conn:
                        conn.yasdl_create_table_triggers(
                            field_diff.new_instance, schema, table,
                            upgrade_context.sqlprocessor, upgrade_context.options)

        # Tables that will were created
        table_diff = upgrade_context.table_diff
        new_instance = upgrade_context.new_instance
        for guid in table_diff.to_create:
            table = table_diff.new_tables[guid]
            if table not in created:
                schema = table.owner_schema
                if not IGNORE_VENUS or schema.getpath() != "venus.core":
                    created.add(table)
                    with new_instance.cpool.open() as conn:
                        conn.yasdl_create_table_triggers(new_instance, schema, table,
                                                         upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_create_views(cls, upgrade_context: YASDLUpgradeContext):
        """Create views for all tables that had any fields changed PLUS for all new tables that has been created."""
        pass

    @classmethod
    def upgrade_create_comments(cls, upgrade_context: YASDLUpgradeContext):
        table_diff = upgrade_context.table_diff
        new_instance = upgrade_context.new_instance
        with new_instance.cpool.open() as conn:
            for guid in table_diff.to_create:
                tbl = table_diff.new_tables[guid]
                conn.yasdl_create_table_comments(new_instance, tbl.owner_schema, tbl,
                                                 upgrade_context.sqlprocessor, upgrade_context.options)

    @classmethod
    def upgrade_data(cls, upgrade_context: YASDLUpgradeContext):
        """Data for new tables, after triggers indexes and constraints are added to new tables."""
        pass

    def check(self, options=None):
        """Check that all required tables and fields exist."""
        for scm in self.schemas_with_toplevel_realized_fieldsets():
            if not IGNORE_VENUS or scm.getpath() != "venus.core":
                sname = self.get_schema_pname(scm)
                with self.cpool.open() as conn:
                    if not conn.schema_exists(sname):
                        raise AttributeError(_("Schema %s does not exist." % sname))
                    else:
                        print("SCHEMA %s" % sname)
        for scm, tbl in self.toplevel_realized_fieldsets():
            if not IGNORE_VENUS or scm.getpath() != "venus.core":
                sname = self.get_schema_pname(scm)
                tname = self.get_table_pname(tbl)
                with self.cpool.open() as conn:
                    if not conn.table_exists(sname, tname):
                        raise AttributeError(_("Table %s.%s does not exist." % (sname, tname)))
                    else:
                        print("    TABLE %s" % tname)
                    for fieldpath in tbl.itercontained([ast.YASDLField]):
                        field = fieldpath[-1]
                        if field.realized:
                            fname = self.get_field_pname(tbl, fieldpath)
                            if not conn.column_exists(sname, tname, fname):
                                raise AttributeError(_("Field %s.%s.%s does not exist." % (sname, tname, fname)))
                            else:
                                print("        FIELD %s" % fname)

                    for index in tbl.members:
                        if isinstance(index, ast.YASDLIndex):
                            iname = self.get_index_pname(tbl, index)
                            if not conn.index_exists(sname, tname, iname):
                                raise AttributeError(_("Index %s.%s.%s does not exist." % (sname, tname, iname)))
                            else:
                                print("        INDEX %s" % iname)

    def store_parsed(self):
        """Save the contained YASDLParseResult into the database for later use.

        By saving the whole parse result into the database instance, it will contain
        its own defitions. It makes auto-upgrading easier.
        """
        parsed_schema_value = base64.b64encode(self.parsed.dumps()).decode('ascii')
        # TODO: make this easier! Should be a method of the instance!
        venus_core = self.parsed.get_schema("venus.core")
        sys_parameter = venus_core.bind("sys_parameter")
        sname = self.get_schema_pname(sys_parameter.owner_schema)
        tname = self.get_table_pname(sys_parameter)
        fullname = '"%s"."%s"' % (sname, tname)

        with self.cpool.opentrans() as conn:
            sys_parameter_id = conn.getqueryvalue(
                "select id from "+fullname+" where param_key=%s", [PARSED_SCHEMA_KEY])
            if sys_parameter_id is None:
                conn.execsql(
                    "insert into "+fullname+"(id,param_key, param_value, description) values ("
                    "nextval('sys.id_seq'),%s,%s,%s)",
                    [PARSED_SCHEMA_KEY, parsed_schema_value, "Parsed Schema"]
                )
            else:
                conn.execsql(
                    "update "+fullname+" set param_value=%s where id=%s",
                    [parsed_schema_value, sys_parameter_id]
                )

    @classmethod
    def load_parsed(cls, connectionpool: ConnectionPool) -> YASDLParseResult:
    #def load_parsed(self) -> YASDLParseResult:
        """Load the definition of a database from the database.

        Note: the definition must have been saved with save_parsed previously."""
        with connectionpool.open() as conn:
            sname = "venus%score" % conn.name_separator
            tname = "sys_parameter"
            fullname = '"%s"."%s"' % (sname, tname)

            parsed_schema_value = conn.getqueryvalue(
                "select param_value from " + fullname + " where param_key=%s",
                [PARSED_SCHEMA_KEY]
            )
            if parsed_schema_value is not None:
                return YASDLParseResult.loads(base64.b64decode(parsed_schema_value.encode('ascii')))

