"""YASDL parser"""
import codecs
import copy
import os
import re
import sys
import gzip
import io
import urllib.error
import urllib.parse
import urllib.request

import pickle

import venus.i18n
from venus.db.yasdl import ast
from venus.db.yasdl.lex import lexer_init, dump
from venus.db.yasdl.yacc import yacc

_ = venus.i18n.get_my_translator(__file__)

_URI_PATTERN = re.compile(r"""([^:]+)://(.*)""")

_MY_DIR = os.path.abspath(os.path.split(__file__)[0])
BUILTIN_SCHEMA_SEARCH_PATH = os.path.abspath(os.path.join(_MY_DIR, os.pardir, os.pardir, "schemas"))
BUILTIN_SCHEMA_PATHS = list(map(lambda items: os.path.join(*items), [
    ["venus", "core.yasdl"]
]))


def parse(fpaths, options=None, search_path=None):
    """Parse schema definition stored in a file.

    :param fpaths: A list of file paths to ".yasdl" files or an URIs.
    :param search_path: A list of directories containing definition files for used schemas. (See the use
        and require statement of the YASDL reference). The path for buult-in schemas BUILTIN_SCHEMAS_PATH
        will always be prepended to this. When not given, the current directory is appended, and also
        all directories found in your ~/.yasdlrc file.
    :return: YASDLParseResult instance.

    ..note::

        The returned schema set is guaranteed to be syntactically correct, but it may have semantic errors.
        After parsing the schema set, the compiler can be used on the returned YASDLParseResult.
    """
    global BUILTIN_SCHEMA_SEARCH_PATH
    if not search_path:
        search_path = ['.']
        yasdlrc = os.path.expanduser('~/.yasdlrc')
        if os.path.isfile(yasdlrc):
            for line in open(yasdlrc, 'r'):
                dpath = line.strip()
                if os.path.isdir(dpath):
                    search_path.append(dpath)

    # Built in schemas are alway preprended to the search path.
    search_path.insert(0, BUILTIN_SCHEMA_SEARCH_PATH)

    if not isinstance(fpaths, list):
        raise ValueError(_("fpaths parameter of YASDLParser.parse " + \
                           "must be a list, not %s") % type(fpaths))

    # The core venus schemas are always prepended to the list of schemas.
    fpaths = BUILTIN_SCHEMA_PATHS + fpaths

    result = YASDLParseResult(options)
    if result.parse(fpaths, search_path):
        return result
    else:
        raise YASDLParserError(_("Parser exited with errors."))


class YASDLParserError(Exception):
    """Base class for parser errors."""
    pass


class YASDLSchemaLocationError(YASDLParserError):
    """Raised when a referenced schema cannot be located."""
    pass


class YASDLParseResult:
    """Parse result.

    In fact, this object does the parsing, but it also
    manages parsing state information.

    YASDLParseResult has the following attributes:

        schemas - a dict, where keys are sources (full file path
            for .ssd file or an URI) and values are SSDSchema objects
        main_srcs - sources for the main schemas, the ones that where
            originally passed to the parse() method.

    Each parsed schema has the following extra attributes:

        src - the source of the schema
        use_stack - list of sources, showing the stack of "use" statements
            that resulted this schema to be loaded

    After successfully compiling an YASDLParseResult with a compiler.Compiler,
    the following methods can be used:

        bind(obj, name, recursive, excludes)
        bind_static(obj, name, recursive, excludes)

    """

    def __init__(self, options):
        self.schemas = {}
        self.options = {
            "debug": options.debug,
            "verbose": options.verbose,
        }
        self.main_srcs = None  # Will be set later.
        self.errorcount = 0

    def __str__(self):
        res = "YASDLParseResult("
        for main_src in self.main_srcs:
            main_schema = self.schemas[main_src]
            res += repr(main_schema.name)
            res += _(" for %s") % repr(main_schema.src)
            res += ","
        # schema_names = [ repr(src)
        # for src,schema in self.schemas.iteritems()  ]
        # res += ",".join(schema_names)
        res += ")"
        return res

    def error(self, msg):
        """Print debug message to stderr."""
        sys.stderr.write(msg)
        sys.stderr.write("\n")
        sys.stderr.flush()
        self.errorcount += 1

    def debug(self, msg):
        """Print debug message to stdout."""
        if self.options.get("debug", False):
            print(msg)

    def log(self, msg):
        """Print verbose message to stdout."""
        if self.options.get("verbose", False):
            print(msg)

    def locate_used_schema(self, name, search_path):
        """Locate schema source.

        :param name: Schema name, as occurs in the use/require YASDL statement.
        :param search_path: A list of directories to be used for searching.
        @return: URL of full path of the file that contains the referenced schema.

        If the name is an URI (e.g. begins with http:// or ftp://) then the URI is returned. Otherwise the
        file is searched on the given search path.

        If cannot be found, an exception is raised.
        """
        if _URI_PATTERN.match(name):
            return name
        else:
            return self.locate_local(name, search_path)

    @classmethod
    def locate_local(cls, name, search_path):
        """Locate local schema source (file).

        :param name: Schema name, as occurs in the uses statement.
        :param search_path: A list of directories to be used for
            searching.
        @return: Full path of the file that contains
            the referenced schema. It is very important to return
            the full path, because it will be used to identify
            which schemas has been parsed (e.g. it must be a key!)

        If cannot be found, an exception is raised.
        """
        name = name.replace('.', os.sep)
        for dpath in search_path:
            fpath = os.path.join(dpath, name) + ".yasdl"
            if os.path.isfile(fpath):
                res = os.path.abspath(os.path.normpath(fpath))
                # Unfortunately, some programs use "C:" and others "c:".
                # We also need to normalize for case sensitivity
                if sys.platform == "win32":
                    res = res.lower()
                return res
        raise YASDLSchemaLocationError(_("Schema %s cannot be located. Search path=%s") % (repr(name), search_path))

    @classmethod
    def load_data_local(cls, fpath):
        """Load a file from the given path."""
        fin = codecs.open(fpath, "rb", encoding="UTF-8")
        return fin.read()

    @classmethod
    def load_data_uri(cls, uri):
        """Load schema definition from an URI.

        This method uses urllib2 to load the data from the specified uri.
        You can override this method to implement your own protocol
        handler and/or do authentication."""
        req = urllib.request.Request(url=uri)
        fin = urllib.request.urlopen(req)
        # TODO: get server encoding, and decode from the right encoding!
        # Although it is against the documentation, some fools will
        # put up their schemas on an Apache server with DefaultCharset
        # set to iso8859-1 ...
        return fin.read().decode("UTF-8")

    def parse(self, fpaths, search_path=None):
        """Parse a set of schema definitions, given by their names.

        :param fpaths: As returned by locate_used_schema.
        """
        srcs = []
        for fpath in fpaths:
            if _URI_PATTERN.match(fpath):
                name = fpath
            else:
                if not fpath.endswith('.yasdl'):
                    raise Exception(
                            _("Invalid fpath to import (%s).") % repr(fpath) + \
                            " " + _("Must be an URI or a .yasdl file path."))
                name = fpath.replace(os.sep, '.')[:-len(".yasdl")]
                # search_path = copy.copy(search_path)
                # fpath = os.path.abspath(fpath)
                # search_path.insert(0, os.path.split(fpath)[0])
            src = self.locate_used_schema(name, search_path or [])
            if src in srcs:
                self.debug("duplicate_source: %s" % src)
            else:
                self.debug("parse_needed:%s" % src)
                srcs.append(src)
        parse_needed = [[src] for src in srcs]
        self.main_srcs = srcs

        # Recursively parse all (sub)schemas.
        while parse_needed:
            new_schemas = []
            for use_stack in parse_needed:
                src = use_stack[0]
                if src not in self.schemas:
                    if _URI_PATTERN.match(src):
                        data = self.load_data_uri(src)
                        self.debug("parse_str:%s" % src)
                        # First we tokenize. So there is a lexer error
                        # then we can raise a proper exception.
                        schema = self.schemas[src] = self.parse_str(
                                src, data, search_path)
                    else:
                        self.debug("parse_file:%s" % src)
                        schema = self.schemas[src] = self.parse_file(
                                src, search_path)
                    schema.use_stack = use_stack
                    schema.src = src
                    new_schemas.append(schema)
            parse_needed = []
            for schema in new_schemas:
                for use in schema.uses:
                    try:
                        src = self.locate_used_schema(
                                use.name, schema.search_path)
                    except YASDLSchemaLocationError as e:
                        # Re-raise with the correct source file reference.
                        raise YASDLSchemaLocationError('"%s": %s' % (schema.getsourcefile(), str(e)))
                    use_stack = [src] + schema.use_stack
                    use.src = src
                    if not src in list(self.schemas.keys()):
                        for item in use_stack:
                            self.debug("parse_needed:%s" % item)
                        parse_needed.append(use_stack)

        # Set schema attribute for all use statements.
        for src, schema in self.schemas.items():
            for use in schema.uses:
                use.schema = self.schemas[use.src]

        # Check if package names are correct.
        for ref_from in list(self.schemas.values()):
            for use in ref_from.uses:
                ref_to = use.schema
                if _URI_PATTERN.match(use.name):
                    raise NotImplementedError("Implement reverse domain " + \
                                              "name checking here!")
                elif use.name != ref_to.package_name:
                    # Try to conform to GNU message format, so IDE can
                    # jump to file.
                    msg = '"%s":%s:%s:%s:%s' % (
                        ref_to.getsourcefile(),
                        ref_to.lineno,
                        "E001",
                        use.getpath(False),
                        ("Invalid package name: %s is referenced as %s " +
                         "from %s") % (ref_to.package_name, use.name,
                                       ref_from.src))
                    self.error(msg)

        # Check if we have no package name duplication.
        names = {}
        for schema in list(self.schemas.values()):
            if schema.package_name in names:
                names[schema.package_name].append(schema)
            else:
                names[schema.package_name] = [schema]
        for name, schemas in names.items():
            if len(schemas) > 1:
                for schema in schemas:
                    msg = '"%s":%s:%s:%s:%s' % (
                        schema.getsourcefile(),
                        schema.lineno,
                        "E002",
                        schema.getpath(False),
                        _("Error: duplicate package name %s:" % name))
                    self.error(msg)

        # Setup owners of all schemas
        for schema in list(self.schemas.values()):
            schema.setup_owners()

        # Setup cache for static binding
        for schema in list(self.schemas.values()):
            schema._cache_static_names()

        return self.errorcount == 0

    def parse_file(self, filepath, search_path=None):
        """Parse schema definition stored in a file.

        :param filepath: Path to the YASDL file.
        :param search_path: A list of directories containing
            definition files for used schemas. (See the use statement).

        @return: The parsed YASDLSchema. Its "search_path" attribute
            will be set to its schema search path.
        """
        data = codecs.open(filepath, "rb", encoding="UTF-8").read()
        search_path = copy.copy(search_path or [])
        srcdir = os.path.abspath(os.path.split(filepath)[0])
        if srcdir in search_path:
            search_path.remove(srcdir)
        search_path.insert(0, srcdir)
        return self.parse_str(filepath, data, search_path)

    def parse_str(self, src, data, search_path=None):
        """Parse schema definition stored in an unicode data string.

        :param src: Original file name, or other source of data.
        :param data: Unicode data string, containing an YASDL schema
          definition.
        :param search_path: A list of directories containing
            definition files for used schemas. (See the use statement).

        @return: The parsed MSDSchema. Its "search_path" attribute
            will be set to its schema search path.
        """
        # Needed to make useful messages.
        if self.options.get("debug", False):
            dump(src, data)
        lexer_init(src, data)
        ast_obj = yacc.parse(data)
        if ast_obj:
            ast_obj.search_path = search_path or []
            assert isinstance(ast_obj, ast.YASDLSchema)  # Top level element can only be a schema instance.
            ast_obj.set_source_lines(data.split("\n"))  # We store the source code line in the schema
        return ast_obj

    def iterate(self, min_classes=None):
        """Iterate over all items.

        It is the chain of iterate(min_classes) for all parsed schemas.
        """
        for schema in list(self.schemas.values()):
            for item in schema.iterate(min_classes):
                yield item

    @classmethod
    def bind(cls, obj, name, recursive=True, excludes=None):
        """Dynamic binding.

        :param obj: An YASDLDefinition object. This defines the context
            where the name is "used". So binding starts at the context
            of the definition given here.

        :param name: An ast.dotted_name instance.

        This method is similar to ast.YASDLItem.bind, but it considers
        alias names of used/required schemas. The name parameter MUST be
        a dotted name, and its min_classes attribute is used to narrow
        down the search. (name.absolute is also effective).

        Implementation note: a very similar method exists in the
        compiler.Compiler class.
        """
        assert (isinstance(name, ast.dotted_name))
        if obj:
            schema = obj.owner_schema
            # First, try to find by normal dynamic binding.
            if name.absolute:
                result = schema.bind(name, name.min_classes, recursive,
                                     excludes)
            else:
                result = obj.bind(name, name.min_classes, recursive, excludes)
            if result:
                return result

            # Then, try to find in in used schemas.
            for use in schema.uses:
                if use.alias is None:
                    prefix = use.package_name
                else:
                    prefix = use.alias
                if name.startswith(prefix):
                    subname = name[len(prefix) + 1:]
                    result = use.schema.bind(subname, name.min_classes,
                                             recursive, excludes)
                    if result:
                        return result

            # Finally, we check if the name is prefixed with the name
            # of the owner schema.
            if not name.absolute:
                if name.startswith(schema.package_name):
                    subname = name[len(schema.package_name) + 1:]
                    result = schema.bind(subname, name.min_classes,
                                         recursive, excludes)
                    if result:
                        return result

        return None

    @classmethod
    def bind_static(cls, obj, name, recursive=True, excludes=None):
        """Static binding.

        :param obj: An YASDLDefinition object. This defines the context
            where the name is "used". So binding starts at the context
            of the definition given here.

        :param name: An ast.dotted_name instance.

        This method is similar to ast.YASDLItem.bind_static, but it
        considers alias names of used/required schemas. The name
        parameter MUST be a dotted name, and its min_classes attribute is
        used to narrow down the search. (name.absolute is also
        effective).

        Implementation note: a very similar method exists in the
        compiler.Compiler class.

        """
        assert (isinstance(name, ast.dotted_name))
        if obj:
            schema = obj.owner_schema
            if name.absolute:
                result = schema.bind_static(name, name.min_classes,
                                            recursive=recursive, excludes=excludes)
            else:
                # First, try to find in in containing definitions,
                # traversing upwards.
                result = obj.bind_static(name, name.min_classes,
                                         recursive=recursive, excludes=excludes)
            if result:
                return result

            # Then, try to find in in used schemas.
            for use in schema.uses:
                if use.alias is None:
                    prefix = use.package_name
                else:
                    prefix = use.alias
                if name.startswith(prefix):
                    subname = name[len(prefix) + 1:]
                    result = use.schema.bind_static(
                            subname, name.min_classes,
                            recursive=recursive, excludes=excludes)
                    if result:
                        return result

            # Finally, we check if the name is prefixed with the name
            # of the owner schema.
            if not name.absolute:
                if name.startswith(schema.package_name):
                    subname = name[len(schema.package_name) + 1:]
                    # print "search",schema.getdebugpath()
                    result = schema.bind_static(
                            subname, name.min_classes,
                            recursive=recursive, excludes=excludes)
                    if result:
                        return result

        return None

    def get_schema(self, fullname):
        """Get a schema by its full name."""
        if not isinstance(fullname, ast.dotted_name):
            fullname = ast.dotted_name(fullname)
        for src in self.schemas:
            schema = self.schemas[src]
            if schema.getpath() == fullname:
                return schema

    @classmethod
    def _gzip_bytes(cls, data):
        out = io.BytesIO()
        with gzip.GzipFile(fileobj=out, mode='w') as fo:
            fo.write(data)
        return out.getvalue()

    @classmethod
    def _gunzip_bytes(cls, data):
        in_ = io.BytesIO()
        in_.write(data)
        in_.seek(0)
        with gzip.GzipFile(fileobj=in_, mode='rb') as fo:
            return fo.read()

    def dumps(self) -> bytes:
        """Dump into a binary string."""
        return self._gzip_bytes(pickle.dumps(self))

    @classmethod
    def loads(cls, data) -> "YASDLParseResult":
        result = pickle.loads(cls._gunzip_bytes(data))
        assert isinstance(result, cls)
        return result