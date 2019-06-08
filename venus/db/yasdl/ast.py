"""Abstract Syntax Tree for YASDL."""
from typing import List, Union

import venus.i18n

_ = venus.i18n.get_my_translator(__file__)


# noinspection PyPep8Naming
class dotted_name(str):
    """This is a special string type that represents a dotted name.

    The imp attribute is set if the name is an imp_name.
    The absolute attribute is set if the dotted name is absolute
        (e.g. starts with the "schema" keyword.)
    The min_classes attribute is set if the dotted name has
        a min_classes specification. In that case, it should be a set
        of ast.YASDLItem subclasses.
    The ref attribute should point to the statically bound definition.
    When not bound, it should be None.
    """

    def __init__(self, *args, **kwargs):
        str.__init__(*args, **kwargs)
        self.imp = False
        self.absolute = False
        self.min_classes = None
        self.ref = None
        self.refpath = None
        self.lineno = None
        self.colno = None
        self.owner_schema = None

    def items(self):
        """Return a list of items that make up the dotted name."""
        return self.split(".")

    def get_source_line(self):
        """Get source line code for the dotted name."""
        return self.owner_schema.get_source_line_of(self)


#
# This would allow us to store debug information in STRING literals. Also see comments in lex.py
# But we don't do this because it is not elegant. Also for singletons like True or None this method would not work.
#
# class token_str(str):
#     """This is a special string that knows where it came from.
#
#     The yacc parser assigns the lineno and colno attributes of this object when a string token is created
#     from a string literal in the source code."""
#     def __init__(self, *args, **kwargs):
#         str.__init__(*args, **kwargs)
#         self.lineno = None
#         self.colno = None
#         self.owner_schema = None
#
#     def get_source_line(self):
#         """Get source line code for the dotted name."""
#         return self.owner_schema.get_source_line_of(self)


def is_minclass(obj, min_classes=None):
    """Return if an object is instance of any classes listed.

    :param obj: The object to be examined
    :param min_classes: List of classes, or None.
    :return: Passing an empty list will always return False. Passing None will always return True.
             E.g. None means "no restriction", and empty list means "do not accept anything".
    """
    if min_classes is None:
        return True
    else:
        return True in [isinstance(obj, cls) for cls in min_classes]


class YASDLSymbol:
    """Represents a special symbol."""

    def __init___(self):
        self.lineno = None
        self.colno = None


class YASDLAll(YASDLSymbol):
    """Represents the ALL symbol."""
    pass


class YASDLItem:
    """Base class for AST elements.

    AST elements have a name, zero or more modifiers and zero or more
    owner items. This forms an ownership tree. Owned items can be
    YASDLItem instances, string literals (unicode), integers, floats etc.
    """

    def __init__(self, name, items=None):
        # Name of the item
        self.name = name
        # Owned items
        if items:
            self.items = items
        else:
            self.items = []
        self.lineno = -1  # Will be set by yacc
        self.colno = -1  # Will be set by yacc
        self._hash = None  # Will be set by parser
        self.owner = None  # Will be setup later with setup_owners
        # These below will be set later by the compiler
        self.modifiers = []
        self.ancestors = []
        self.descendants = set([])
        self.specifications = set([])
        self.implementations = set([])
        # This will be set by _cache_static_names() later.
        self._snc = {}
        # These will be set by _cache_members() later.
        self._mbn, self.members = {}, []
        self._members_cached = False
        self.unused_deletions = None
        self.deletions = None

    def __iter__(self):
        """Iterate over subitems.

        These subitems are all items in the ownership tree, given by the
        object. Traversal is depth first.

        Please note that the object itself is NOT returned!

        See also: iterate(), members, itercontained()
        """
        for item in self.items:
            if isinstance(item, YASDLItem):
                for subitem in item:
                    yield subitem
                yield item

    def iterate(self, min_classes=None):
        """Iterate over subitems.

        These subitems are all items in the ownership tree, given by the object. Traversal is depth first.

        :param min_classes: A list of acceptable classes to return. When None, items of all classes are returned.

        This method does NOT yield any inherited members. Unlike __iter__, this method can return itself!

        See also: itercontained(), has_member(), contains(), owns()
        See also: items, members
        """
        for item in self:
            if is_minclass(item, min_classes):
                yield item
        if is_minclass(self, min_classes):
            yield self

    def owns(self, item):
        """Item is owned the called object, directly or indirectly.

        :param item: The item to be tested.

        This corresponds to the statical containment in the YASDL source code.

        This is NOT a real dynamic containment check, since contained
        items can be defined in ancestors or implementors that are
        not statically contained.

        Please note that obj.owns(obj) returns False!

        See also: itercontained(), has_member(), contains(), owns()
        See also: items, members
        """
        for subitem in iter(self):
            if subitem is item:
                return True
        return False

    def _cache_members(self):
        """Cache members and set the members attribute.

        Should not be called manually. Should be called by the compiler.

        Members are the YASDLItem instances that are specified directly
        statically, OR inherited from ancestors. The order of members is
        important. First the members defined statically in the definition are
        listed. Then members defined by the first listed ancestor are listed.
        Then members of the second listed ancestor are listed. Etc.

        Each member has a name, and every name is defined only once.
        E.g. if "displaylabel" is defined in the object, then it is not
        inherited. If "type" is defined in the second ancestor, then it is
        not inherited from the third and fourth ancestors etc.

        You should only use this method after successful call to
        compiler.compile().

        Please note that this method does NOT traverse over the ownership tree!
        For that, see iterate().

        Please also note that this method only iterates over the direct
        members. If you also want to iterate over members of members etc.
        recursively, then use itercontained().
        """
        if self._members_cached:
            return

        self.deletions = set([])
        for item in self.items:
            if isinstance(item, YASDLDeletion):
                self.deletions.add(item.name)
        used_deletions = set([])

        self._mbn, self.members = {}, []

        # Recursive step: inherit members from ancestors.
        if hasattr(self, 'ancestors'):
            for ancestor in self.ancestors:
                # noinspection PyProtectedMember
                ancestor._cache_members()
                for inherited_member in ancestor.members:
                    if isinstance(inherited_member, YASDLItem):
                        if (inherited_member.name != 'implements') and \
                                (inherited_member.name != 'ancestors'):
                            if inherited_member.name in self.deletions:
                                used_deletions.add(inherited_member.name)
                            elif inherited_member.name in self._mbn:
                                old = self._mbn[inherited_member.name]
                                idx = self.members.index(old)
                                self._mbn[inherited_member.name] = \
                                    inherited_member
                                self.members[idx] = inherited_member
                            else:
                                self._mbn[inherited_member.name] = \
                                    inherited_member
                                self.members.append(inherited_member)
        # Normal step: our statically defined names.
        for item in self.items:
            item = getattr(item, 'final_implementor', item)
            if isinstance(item, YASDLItem) and \
                    not isinstance(item, YASDLDeletion):
                if item.name in self._mbn:
                    old = self._mbn[item.name]
                    idx = self.members.index(old)  # TODO: might cache the index too, to speed up replacement!
                    self._mbn[item.name] = item
                    self.members[idx] = item
                else:
                    self._mbn[item.name] = item
                    self.members.append(item)

        self.unused_deletions = self.deletions - used_deletions
        self._members_cached = True

    def has_member(self, name, min_classes=None):
        """Tells if there is a member with the given name.

        :param name: Name of the member to search for.
        :param min_classes: List of min_classes, or None.

        See also: itercontained(), has_member(), contains(), owns()
        See also: items, members
        """
        if name in self._mbn:
            member = self._mbn[name]
            if is_minclass(member, min_classes):
                return True
        return False

    def __getitem__(self, name):
        return self._mbn[name]

    def itercontained(self, min_classes=None):
        """Similar to members, but it traverses through all
        contained definitions, and lists all members of all submembers
        recursively, in the right order.

        :param min_classes: An iterable of classes. When given, only contained items of the given subclasses will
            be yielded.

        Yielded values are non-empty lists. These lists contain the
        paths that can be used to access the members. To get the member
        itself, use the last item of the list.

        The most useful way to use this generator is to iterate over
        all field definitions in a fieldset, and contained fieldsets,
        in the right order.

        Please note that this method does NOT return self!

        See also: itercontained(), has_member(), contains(), owns()
        See also: items, members
        """
        for member in self.members:
            if is_minclass(member, min_classes):
                yield [member]
            # if isinstance(member, YASDLFieldSet): ???
            for submember_path in member.itercontained(min_classes):
                submember_path.insert(0, member)
                yield submember_path

    def contains(self, item):
        """Tells if the given item is contained within.

        :param item: Item to look for

        This goes over members. For static containment, use the owns() method.

        See also: itercontained(), has_member(), contains(), owns()
        See also: items, members
        """
        for member_path in self.itercontained():
            if member_path[-1] is item:
                return True
        return False

    def setup_owners(self):
        """Setup owner properties of all child objects.

        After loading and AST, you need to call this method.
        This will setup the 'owner' attribute in the whole ownership
        tree. (Only for YASDLItem instances)
        """
        for item in self.items:
            if isinstance(item, YASDLItem):
                item.owner = self
                item.setup_owners()

    def getpath(self, show_src=False):
        """Return full name path of the item.

        :param show_src: when set, then the return value also includes
            the source file location.

        The path starts with the package name of the schema which is unique. (It is made sure by the YASDL parser.)
        Then it continues with the containing definitions, ending with the name of the item. The compiler makes
        sure that there are no definitions with the same name inside the same block. So the path of any item
        is unambiguous, and it identifies the item.

        The path is also used to create a hash of the item.
        """
        res = ""
        if getattr(self, 'owner', None):
            res += self.owner.getpath(show_src) + "." + self.name
        else:
            # res += self.name
            # When there is no owner, it can only be a schema.
            assert isinstance(self, YASDLSchema)
            res += self.package_name

        if show_src and hasattr(self, "src"):
            res = "in " + getattr(self, "src") + ": " + res

        return res

    def getsourcefile(self):
        """Get source file path for the item."""
        obj = self
        while obj and not hasattr(obj, "src"):
            obj = obj.owner
        if obj:
            return getattr(obj, "src")
        else:
            return ""

    def getdebugpath(self):
        """Similar to getpath() but it tries to tell the line number."""
        msg = self.getpath(True)
        if hasattr(self, 'lineno'):
            msg += _(" at line %d ") % self.lineno
        return msg

    def get_source_line(self):
        """Get source line code for the item."""
        return self.owner_schema.get_source_line_of(self)

    def __repr__(self):
        return "%s(%s @ %s)" % (self.__class__.__name__, self.getpath(), id(self))

    def _get_outermost_owner(self, min_classes):
        """Return the outermost owner that has the given class."""
        res = self
        while res is not None and not is_minclass(res, min_classes):
            res = res.owner
        return res

    def _get_owner_schema(self):
        """Get the schema that owns this item."""
        return self._get_outermost_owner([YASDLSchema])

    owner_schema = property(_get_owner_schema, None,
                            doc="Owner schema, if any.")

    def _get_toplevel_fieldset(self):
        """Get the toplevel fieldset that owns this definition (if any)."""
        return self._get_outermost_owner([YASDLFieldSet])

    toplevel_fieldset = property(_get_toplevel_fieldset, None,
                                 doc="Owner toplevel fieldset, if any.")

    def is_outermost(self):
        """Tells if the definition is outermost (defined at schema level)."""
        return isinstance(self.owner, YASDLSchema)

    def _cache_static_names(self):
        """Create a cache of statically bound local names."""
        self._snc.clear()
        for item in self.items:
            if isinstance(item, YASDLItem):
                if hasattr(item, 'name'):
                    self._snc[item.name] = item
                item._cache_static_names()

    def bind_static(self, name, min_classes=None, recursive=True,
                    excludes=None):
        """Bind a name to an object statically.

        @param name: A dotted name, or a list containing a name path.
        @param min_classes: When given, only objects with the given class
            will be returned. E.g. if there is an object with the given
            name, but with the wrong class, then it won't be bound to
            the name.
        @param recursive: When set, search for name will continue in
        owner definitions recursively. When not set, the call can
        only return self or one of its subitems with the given name.
        @param excludes: When given, then it should be a list of objects.
            Those objects will be excluded from the search.
        @result: The object found for the name, or None if nothing found.
            It is important to understand that this method can return
            specifications and final implementations as well.

        Please note that this method starts binding from the current
        (called) object. You may want to start binding from the
        owner schema level, regardless of what level the name occured
        inside the schema.
        """
        res = self.bindpath_static(name, min_classes, recursive, excludes)
        if res:
            return res[-1]
        else:
            return None

    def bindpath_static(self, name, min_classes=None, recursive=True,
                        excludes=None):
        """Bind a name to an object statically.

        :param name: The name to be bound
        :param min_classes: When given, only instances of the given classes will match.
        :param recursive: Set this flag to search down recursively in all contained items.
            Clear this flag to search directly contained items only.
        :param excludes: You can pass an iterable of instances here that will be excluded from the search.
        :return: A path (list) of items. The last item in the path will be the bound object.

        This is very similar to bind_static(), but it returns a path of
        items instead of a single item. This might be needed in some cases,
        because sometimes the same definition is contained multiple
        times inside another definition. So by just binding a name to
        a contained definition, it is not clear what realization is
        meant under the given name. This method returns the whole path
        for the bound object, making the realization unambiguous.
        """
        if len(name) == 0:
            raise Exception(_("Cannot bind an empty name!"))
        if excludes is None:
            excludes = []
        if isinstance(name, str):
            name = name.split(".")
        firstname = name[0]

        # This has been superseded by the static name cache self._snc
        # for item in self.items:
        #    if hasattr(item, 'name') and (item.name == firstname):

        if firstname in self._snc:
            item = self._snc[firstname]
            if len(name) == 1:
                if is_minclass(item, min_classes):
                    if item not in excludes:
                        return [item]
            else:
                head = item
                res = head.bindpath_static(name[1:], min_classes, False, excludes)
                if res:
                    res.insert(0, head)
                    return res

        if recursive and self.owner:
            return self.owner.bindpath_static(name, min_classes, True, excludes)
        else:
            return None

    def bind(self, name, min_classes=None, recursive=True, excludes=None):
        """Bind a name to an object dynamically.

        @param name: A dotted name, or a list containing a name path.
        @param min_classes: When given, only objects with the given class
            will be returned. E.g. if there is an object with the given
            name, but with the wrong class, then it won't be bound to
            the name.
        @param recursive: When set, search for name will continue in
        owner definitions recursively. When not set, the call can
        only return self or one of its subitems with the given name.
        @param excludes: When given, then it should be a list of objects.
            Those objects will be excluded from the search.
        @result: The object found for the name, or None if nothing found.
            It is important to understand that this method returns
            final implementations only!

        Please note that this method starts binding from the current
        (called) object. You may want to start binding from the
        owner schema level, regardless of what level the name occured
        inside the schema.

        """
        res = self.bindpath(name, min_classes, recursive, excludes)
        if res:
            return res[-1]
        else:
            return None

    def bindpath(self, name, min_classes=None, recursive=True, excludes=None):
        """Bind a name to an object dynamically.

        :param name: The name to be bound
        :param min_classes: When given, only instances of the given classes will match.
        :param recursive: Set this flag to search down recursively in all contained items.
            Clear this flag to search directly contained items only.
        :param excludes: You can pass an iterable of instances here that will be excluded from the search.
        :return: The item bound, or None

        This is very similar to bind(), but it returns a path of items
        instead of a single item. This might be needed in some cases,
        because sometimes the same definition is contained multiple
        times inside another definition. So by just binding a name to
        a contained definition, it is not clear what realization is
        meant under the given name. This method returns the whole path
        for the bound object, making the realization unambiguous.
        """
        if len(name) == 0:
            raise Exception(_("Cannot bind an empty name!"))
        if excludes is None:
            excludes = []
        if isinstance(name, str):
            name = name.split(".")
        firstname = name[0]

        #
        # Normal: find object starting from the called object.
        #

        # Try to bind firstname dynamically, and go deeper if needed.
        if self.has_member(firstname, min_classes):
            if len(name) == 1:
                res = [self[firstname]]
            else:
                head = self[firstname]
                res = head.bindpath(name[1:], min_classes, False, excludes)
                if res:
                    res.insert(0, head)
            if res:
                return res

        # Try to bind firstname statically, and go deeper if needed.
        if len(name) == 1:
            # This is the last item, use min_classes and return if found.
            res = self.bind_static(firstname, min_classes, False, excludes)
            if res:
                return [res.final_implementor]
        else:
            # This is not the last item. Bind the first name, and
            # continue to bind with the remaining names.
            head = self.bind_static(firstname, None, False)
            if head:
                res = head.bindpath(name[1:], min_classes, False, excludes)
                if res:
                    res.insert(0, head)
                    return res

        #
        # Recursive step "a la aquisition" - find object starting from
        # the owner of the called object.
        #
        if recursive and self.owner:
            return self.owner.bindpath(name, min_classes, True, excludes)

        # Nothing found.
        return None

    def iterspecifications(self):
        """Iterate over specifications.

        This method is not available before compile phase 2 has finished."""
        return iter(self.specifications)

    def iterimplementations(self):
        """Iterate over implementations.

        This method is not available before compile phase 2 has finished."""
        return iter(self.implementations)

    def is_specification_of(self, obj):
        """Tells if the called object is a specification of the argument.

        :param obj: The supposed specification
        :return: True when obj is a specification of the object called, False otherwise.
        """
        return obj in self.specifications

    def is_implementation_of(self, obj):
        """Tells if the called object is a implementation of the argument.

        :param obj: The supposed implementation
        :return: True when obj is an implementation of the object called, False otherwise."""
        return obj in self.implementations


class YASDLUse(YASDLItem):
    """Use statement for a schema - not a definition."""

    def __init__(self, name, alias=None):
        super(YASDLUse, self).__init__(name, [])
        self.alias = alias


class YASDLProperty(YASDLItem):
    """Property of an object - not a definition."""
    pass


class YASDLDeletion(YASDLItem):
    """Deletion of a name - not a definition."""
    pass


class YASDLDefinition(YASDLItem):
    """Definition object."""

    def get_singleprop(self, name, defval=None):
        """Get first value of a property.

        :param name: Name of the property
        :type name: str
        :param defval: Default value for the property

        If there is a property with the given name, then its first value is returned. Otherwise defval is returned.
        If there is a property with the given name, but it does not have any value assigned, then KeyError is raised.
        If there is another definition (non-property), then TypeError is raised.
        """
        if name in self._mbn:
            obj = self._mbn[name]
            if not isinstance(obj, YASDLProperty):
                raise TypeError(_("%s is not a property") % name)
            return obj.items[0]
        else:
            return defval

    def get_guid(self) -> str:
        """Get guid of the field."""
        return self.get_singleprop("guid")


class YASDLSchema(YASDLDefinition):
    """YASDL schema definition object."""

    def __init__(self, package_name, uses, items=None):
        if items is None:
            items = []
        self.package_name = package_name
        name = package_name.split(".")[-1]
        super(YASDLSchema, self).__init__(name, items)
        self.uses = uses
        self._source_lines = None  # A list of source code lines. Set by parser.YASDLResult.parse_str

    def set_source_lines(self, source_lines):
        self._source_lines = source_lines

    def get_source_line_of(self, item):
        """Get source code line for an item.

        :param item: A YASDLItem that is contained within the schema.
        :return: Source code line where the definition of the item happened.
        :rtype: str
        """
        assert item.owner_schema is self
        if item.lineno is not None:
            return self._source_lines[item.lineno - 1]

    def setup_owners(self):
        """Setup owner properties of all child objects."""
        self.owner = None
        YASDLDefinition.setup_owners(self)
        for use in self.uses:
            use.owner = self
            use.setup_owners()


class YASDLField(YASDLDefinition):
    """YASDL field definition object."""

    def get_referenced_fieldset(self) -> "YASDLFieldSet":
        """Get referenced fieldset (with "references" property).

        This method will return None for universal references."""
        if "references" in self._mbn:
            if self._mbn["references"].items:
                ref_obj = self._mbn["references"].items[0]
                return ref_obj.ref

    def get_type(self) -> str:
        """Get type of the field."""
        if self.get_referenced_fieldset():
            return "identifier"
        return self.get_singleprop("type")

    def get_size(self):
        """Get type of the field."""
        return self.get_singleprop("size")

    def get_precision(self):
        """Get precision of the field."""
        return self.get_singleprop("precision")

    def get_reqlevel(self):
        """Get requirement level of the field."""
        return self.get_singleprop("reqlevel", "optional")

    def get_notnull(self) -> bool:
        """Get notnull value of the field."""
        return self.get_singleprop("notnull", False)

    def get_immutable(self) -> bool:
        """Get immutable value of the field."""
        return self.get_singleprop("immutable", False)

    def get_default(self):
        """Get default value of the field."""
        return self.get_singleprop("default", None)

    def get_ondelete(self):
        """Get value of the ondelete property, or the default action."""
        return self.get_singleprop("ondelete", "noaction")

    def get_onupdate(self):
        """Get value of the onupdate property, or the default action."""
        return self.get_singleprop("onupdate", "noaction")


class YASDLFieldSet(YASDLDefinition):
    """YASDL fieldset definition object."""
    realized = False


YASDLFieldPath = List[Union[YASDLFieldSet, YASDLField]]


class YASDLIndex(YASDLDefinition):
    """YASDL index definition object."""

    def get_fields(self):
        """Get the "fields" property of the index."""
        try:
            return self["fields"]
        except KeyError:
            return None

    def get_unique(self):
        """Get requirement level of the field."""
        return bool(self.get_singleprop("unique", False))


class YASDLConstraint(YASDLDefinition):
    """YASDL constraint definition object."""

    def get_check(self):
        """Get the "check" property of the constraint."""
        try:
            return self["check"]
        except KeyError:
            return None
