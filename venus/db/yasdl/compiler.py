"""YASDL Compiler"""
import copy
import functools

import venus.i18n
from venus.db.yasdl import ast
from venus.db.yasdl import lex

_ = venus.i18n.get_my_translator(__file__)


class CompilerMessage:
    """A compiler message (error, warning, notice)."""

    def __init__(self, origin, message, code):
        self.origin = origin
        self.message = message
        self.code = code

    def get_message_kind(self):
        raise NotImplementedError

    def gnu_format(self):
        """Format the compiler message according to GNU standards."""
        # http://www.gnu.org/prep/standards/standards.html#Errors
        orig = self.origin
        return '"%s":%s:%s:%s:%s' % (
            orig.getsourcefile(),
            orig.lineno,
            self.get_message_kind() + (self.code or ""),
            orig.getpath(False),
            self.message
        )

    def python_format(self):
        """Format the compiler message as a Python error.

        This maybe useful in some IDEs so that they can generate navigational messages."""
        origin = self.origin
        line = origin.get_source_line()
        if origin.colno >= 0:
            caret = "\n" + " " * origin.colno + "^"
        else:
            caret = ""

        return 'File "%s", line %s column %s in %s:\n%s%s\n%s %s: %s' % (
            origin.getsourcefile(),
            origin.lineno, origin.colno,
            origin.getpath(False),
            line, caret,
            self.__class__.__name__,
            self.get_message_kind() + (self.code or ""),
            self.message
        )


class CompilerError(CompilerMessage):
    """YASDL compiler error message."""

    def get_message_kind(self):
        return "E"


class CompilerWarning(CompilerMessage):
    """YASDL compiler warning message."""

    def get_message_kind(self):
        return "W"


class CompilerNotice(CompilerMessage):
    """YASDL compiler notice."""

    def get_message_kind(self):
        return "N"


class Compiler:
    """Semantic schema checker and compiler."""

    def __init__(self, parsed, dbdriver=None):
        """Initialize a compiler.

        :param parsed: A parsed syntax tree, as returned by yacc.parse().
        :param dbdriver: A database driver (subclass of
            venus.db.dbo.connection.Connection). When not given,
            driver specific checks won't be performed.
        """
        self.parsed = parsed
        self.dbdriver = dbdriver
        self.schemas = parsed.schemas
        self.messages = []
        self.has_notice, self.has_warning, self.has_error = False, False, False

    def append_error(self, origin, message, code=None):
        self.messages.append(CompilerError(origin, message, code))
        self.has_error = True

    def append_warning(self, origin, message, code=None):
        self.messages.append(CompilerWarning(origin, message, code))
        self.has_warning = True

    def append_notice(self, origin, message, code=None):
        self.messages.append(CompilerNotice(origin, message, code))
        self.has_notice = True

    def iterate(self, min_classes=None):
        """Iterate over YASDLItem objects of the compilation.

        :param min_classes: When given, it should be a list of YASDLItem subclasses. Only instances of the
            given classess will be yielded.

        Very similar to YASDLItem.iterate, but works with the whole compilation (possibly over multiple top schemas)."""
        for schema in self.schemas.values():
            for item in schema.iterate(min_classes):
                yield item

    def _phase1_step1(self):
        """Nothing can use itself. Within one schema, you cannot have
        multiple use statements, referencing the same schema document."""
        # Check for multiple use statements
        for schema in self.schemas.values():
            for use in schema.uses:
                if use.src == schema.src:
                    self.append_error(use,
                                      _("Nothing can 'use' or 'require' itself."), "01011")
            use_srcs = {}
            for use in schema.uses:
                if use.src in use_srcs:
                    msg = _("Multiple use statements for the same source is not allowed.")
                    self.append_error(use, msg, "0102")
                    self.append_error(use_srcs[use.src], msg, "01012")
                else:
                    use_srcs[use.src] = use

    def _phase1_step3(self, obj):
        """Check for invalid definition names.

        Cannot have "." in the name.
        Cannot use reserved words as a name.
        Cannot use special property names for anything else.

        """

        def _chk(attrname, label):
            if isinstance(obj, ast.YASDLItem) and hasattr(obj, attrname):
                attrvalue = getattr(obj, attrname)
                if "." in attrvalue:
                    self.append_error(obj, _("Cannot have '.' in %s") % label,
                                     "01031")
                for word in list(lex.reserved.keys()) + lex.RESERVED_PROPERTY_NAMES:
                    if word == attrvalue:
                        if not isinstance(obj, ast.YASDLProperty) or \
                                not (word in lex.RESERVED_PROPERTY_NAMES):
                            self.append_error(obj,
                                              _("'%s' is a reserved property name.") % \
                                              word, "01032")
                if attrvalue == "id":
                    self.append_error(obj,
                                      _("'id' is an invalid name in %s") % label,
                                     "01033")

        if isinstance(obj, ast.YASDLItem):
            _chk("name", "name")
        if isinstance(obj, ast.YASDLUse):
            _chk("alias", "alias")

    def _phase1_step4(self, obj):
        """Check for name duplicates.

        Cannot have more definitions (field,fieldset) with the same name inside
        the same schema or fieldset. Cannot have more properties with the same
        name inside the same schema,field or fieldset. Alias names of
        used/required schemas, or starting names in those package names
        of used/required schemas cannot collide with outermost definitions
        of the schema being defined.
        """
        if isinstance(obj, ast.YASDLDefinition):
            names = []
            if isinstance(obj, ast.YASDLSchema):
                for use in obj.uses:
                    if use.alias:
                        name = use.alias
                    else:
                        name = use.name
                    if name in names:
                        self.append_error(use, _("Duplicated name %s." % repr(name)), "01041")
                    else:
                        names.append(name)

            for item in obj.items:
                name = item.name
                if name in names:
                    self.append_error(item, _("Duplicated name %s." % repr(name)), "01041")
                else:
                    names.append(name)

    def _phase1_step5(self, obj):
        """Check special property names.

        Any object with reserved name can only be a property."""
        if isinstance(obj, ast.YASDLItem):
            if obj.name in lex.RESERVED_PROPERTY_NAMES:
                if not isinstance(obj, ast.YASDLProperty):
                    self.append_error(obj, _("The name '%s' should belong to a property.") % obj.name, "01051")

    def _phase1_step6(self, obj):
        """Cannot have both abstract and final modifiers for the same def."""
        if isinstance(obj, ast.YASDLItem):
            if "abstract" in obj.modifiers and "final" in obj.modifiers:
                self.append_error(obj,
                                  _("Cannot have 'abstract' and 'final' modifiers at the same time."), "01061")

    def _phase1_step7(self, obj):
        """Convert arguments of "implements" into a set of dotted names."""
        if isinstance(obj, ast.YASDLProperty):
            if obj.name == "implements":
                good_min_classes = {obj.owner.__class__}

                # First replace "all" with ancestors, flatten the
                # implements names list.
                all_names = set([])
                for name in obj.items:
                    if isinstance(name, ast.YASDLAll):
                        # Convert "all" to list of ancestors.
                        prop_ancestors = obj.owner.bind_static(
                            "ancestors", recursive=False)
                        if prop_ancestors:
                            _newnames = list(map(
                                ast.dotted_name, prop_ancestors.items))
                        else:
                            _newnames = []
                    else:
                        if name.min_classes is None:
                            name.min_classes = good_min_classes
                        elif name.min_classes != good_min_classes:
                            if isinstance(obj.owner, ast.YASDLField):
                                self.append_error(obj, _("Fields can only be implemented by fields."), "01071")
                            else:
                                self.append_error(obj,
                                                  _("Fieldsets can only be implemented by fieldsets."), "01072")
                            continue
                        _newnames = [name]

                    for _newname in _newnames:
                        all_names.add(_newname)

                # Then replace obj.items with the flattened list.
                for name in all_names:
                    if not isinstance(name, ast.dotted_name):
                        self.append_error(obj,
                                          _("Only dotted names can be used after '%s'.") % \
                                          obj.name, "01073")
                    elif name.imp:
                        self.append_error(obj,
                                          _("Cannot use imp_name '=%s' for %s.") % \
                                          (name, obj.name), "01074")
                    else:
                        name.min_classes = good_min_classes
                obj.items = all_names

    # This method is commented out, because it is not needed.
    # When binding statically, we must always use the bind path for the result,
    # and not the bound object itself.
    # def _bind_static(self, obj, name, recursive=True, excludes=None):
    #    """Static binding.
    #
    #    Simiar to AST.bind_static, but it considers alias names of
    #    used/required schemas.
    #
    #    The name parameter MUST be an ast.dotted_name instance,
    #    and its min_classes attribute is used to narrow down the search.
    #
    #    """
    #    res = self._bindpath_static(name, recursive, excludes)
    #    if res:
    #        return res[-1]
    #    else:
    #        return None

    def _bindpath_static(self, obj, name, recursive=True, excludes=None):
        """Static binding.

        Simiar to AST.bindpath_static, but it considers alias names of
        used/required schemas.

        The name parameter MUST be an ast.dotted_name instance,
        and its min_classes attribute is used to narrow down the search.

        """
        assert (isinstance(name, ast.dotted_name))
        if obj:
            schema = obj.owner_schema
            if name.absolute:
                path = schema.bindpath_static(name, name.min_classes,
                                              recursive=recursive, excludes=excludes)
            else:
                # First, try to find in in containing definitions,
                # traversing upwards.
                path = obj.bindpath_static(name, name.min_classes,
                                           recursive=recursive, excludes=excludes)
            if path:
                return path

            # Then, try to find it in used schemas.
            for use in schema.uses:
                if use.alias is None:
                    prefix = use.name
                else:
                    prefix = use.alias
                if name.startswith(prefix):
                    subname = name[len(prefix) + 1:]
                    # print "search",subname,use.schema.getdebugpath()
                    path = use.schema.bindpath_static(
                        subname, name.min_classes,
                        recursive=recursive, excludes=excludes)
                    if path:
                        path.insert(0, use.schema)
                        return path

            # Finally, we check if the name is prefixed with the
            # package name of the owner schema.
            if not name.absolute:
                if name.startswith(schema.package_name):
                    subname = name[len(schema.package_name) + 1:]
                    # print "search",schema.getdebugpath()
                    path = schema.bindpath_static(
                        subname, name.min_classes,
                        recursive=recursive, excludes=excludes)
                    if path:
                        self.append_warning(obj,
                                            _("Absolute name used to access an object " +
                                             "inside the same schema (instead of " +
                                             "'schema.<name>')."), "99011")
                        path.insert(0, schema)
                        return path

        return None

    def _phase1_step8(self, obj):
        """Bind names in "implements".

        In this step, the checker statically binds names to objects,
        but only for the names listed after the implements property!
        These names are guaranteed to be static (e.g. name.imp is False)
        and they cannot refer to any inherited name. They can only refer
        to another definition outside the containing definition."""
        if isinstance(obj, ast.YASDLProperty) and obj.name == "implements":
            pif = isinstance(obj.owner, ast.YASDLField)
            pifs = isinstance(obj.owner, ast.YASDLFieldSet)
            if not pif and not pifs:
                self.append_error(obj, _("Can only use 'implements' " +
                                        "inside fields and fieldsets."), "01081")
                return
            for name in obj.items:
                if isinstance(name, ast.dotted_name):
                    path = self._bindpath_static(obj, name, recursive=True,
                                                 excludes=[obj.owner])
                    name.refpath = path
                    if path:
                        name.ref = o = path[-1]
                    else:
                        name.ref = o = None

                    if o is None:
                        self.append_error(obj,
                                          _("Definition %s not found (#1) ") % name,
                                         "01082")
                    # Should not happen because of min_classes.
                    elif pif and not isinstance(o, ast.YASDLField):
                        msg = _("A field cannot implement a non-field.")
                        code = "01083"
                        self.append_error(o, msg, code)
                        self.append_error(obj, msg, code)
                    # Should not happen because of min_classes.
                    elif pifs and not isinstance(o, ast.YASDLFieldSet):
                        msg = _("A fieldset cannot implement a non-fieldset.")
                        code = "01084"
                        self.append_error(o, msg, code)
                        self.append_error(obj, msg, code)
                    elif o is obj.owner:
                        self.append_error(obj,
                                          _("Nothing can explicitly implement itself."),
                                         "01085")
                    elif o.owns(obj):
                        self.append_error(obj,
                                          _("Implementation cannot statically contain " +
                                           "its specification. (implementation)"), "01086")
                        self.append_error(o,
                                          _("Implementation cannot statically contain " +
                                           "its specification. (specification)"), "01086")
                    elif (obj.owns(o)):
                        self.append_error(o,
                                          _("Specification cannot statically contain " +
                                           "its implementation. (specification)"), "01087")
                        self.append_error(obj,
                                          _("Specification cannot statically contain " +
                                           "its implementation. (implementation)"), "01087")
                else:
                    self.append_error(obj,
                                      _("Definition %s not found (#2).") % name, "01088")

    def _prop_closure(self, obj, propname):
        allprops = []
        # First the direct parents.
        prop = obj.bind_static(propname, min_classes={ast.YASDLProperty},
                               recursive=False)
        if prop:
            for item in prop.items:
                allprops.append(item.ref)
        # Then the indirect ones.
        while True:
            items_before = len(allprops)
            for obj in allprops:
                prop = obj.bind_static(propname,
                                       min_classes={ast.YASDLProperty}, recursive=False)
                if prop:
                    for item in prop.items:
                        if not item.ref in allprops:
                            allprops.append(item.ref)
            items_after = len(allprops)
            if items_before == items_after:
                break
        return allprops

    def _check_circular(self, obj, propname, errorcode):
        if isinstance(obj, ast.YASDLItem):
            closure = self._prop_closure(obj, propname)
            if obj in closure:
                msg = _("Circular reference for '%s' was detected ") % \
                      propname
                self.append_error(obj, msg + " (#0)", errorcode)
                for idx, item in enumerate(closure):
                    self.append_error(item, msg + " (#%d)" % (idx + 1),
                                      errorcode)
                return False
            for item in obj.items:
                if not self._check_circular(item, propname, errorcode):
                    return False
        return True

    def _phase1_step9(self):
        """No circular implements.

        Nothing can be the implementor of itself. Cannot have circular
        implementors.
        Note: the checker only displays the first error.
        """
        for obj in self.iterate([ast.YASDLField, ast.YASDLFieldSet]):
            if not self._check_circular(obj, 'implements', "01091"):
                break

    def _get_all_implementors(self, what, obj=None):
        """Return a list of defs that list obj after 'implements'.

        :param what: Look for implementors of this.
        :param obj: Examine this object and its subtree.
        :return:  Actually the ``implements`` properties of the definitions are returned instead of the definitions.
            This makes debugging easier.
        """
        res = []
        if obj is None:
            for src, schema in self.schemas.items():
                res += self._get_all_implementors(what, schema)
        elif isinstance(obj, ast.YASDLItem):
            # No need for min_classes here, because we'll check for identity.
            implements = obj.bind_static('implements', recursive=False)
            if implements:
                is_lister = False
                for item in implements.items:
                    if item.ref is what:
                        is_lister = True
                        break
                if is_lister:
                    res.append(implements)
            for item in obj.items:
                res += self._get_all_implementors(what, item)
        return res

    def _check_multiple_implementors(self, obj):
        allimp = self._get_all_implementors(obj)
        if len(allimp) > 1:
            self.append_error(obj,
                              _("Multiple definitions want to implement this."), "02011")
            for idx, item in enumerate(allimp):
                self.append_error(item, _("Multiple implementation."), "02011")

        elif len(allimp) == 1:
            obj.direct_implementor = allimp[0].owner
        else:
            obj.direct_implementor = None

    def _phase2_step1(self):
        """No multiple implementations."""
        for obj in self.iterate([ast.YASDLField, ast.YASDLFieldSet]):
            self._check_multiple_implementors(obj)

    def _has_imp_ancestor(self, obj):
        """Tells if obj has an imp_name listed in its ancestors.

        :param obj: The object to be examined. Must by a YASDLField or a YASDLFieldSet

        """
        # No need for min_classes because 'ancestors' can only be a property.
        prop_ancestors = obj.bind_static("ancestors", recursive=False)
        if prop_ancestors:
            for name in prop_ancestors.items:
                if name.imp:
                    return True
        return False

    def _phase2_step2(self):
        """Cannot implement a definition that has imp_name ancestor(s)."""
        for obj in self.iterate([ast.YASDLField, ast.YASDLFieldSet]):
            if obj.direct_implementor is not None:
                if self._has_imp_ancestor(obj):
                    self.append_error(obj,
                                      _("Cannot explicitly implement a definition " +
                                       "that has imp_name ancestor(s). "), "02021")

    def set_final_implementation_of(self, obj):
        """Find final implementation of a definition.

        :param obj: The definition object
        :return: The final implementation of the object.

        This method has a side effect: it sets the ``final_implementor`` attribute of the object.
        This method is called by the compiler, you do not need to call it directly. After successful compilation,
        use the ``final_implementor`` instead.
        """
        if obj.direct_implementor:
            obj.final_implementor = self.set_final_implementation_of(
                obj.direct_implementor)
        else:
            obj.final_implementor = obj  # Implements itself
        return obj.final_implementor

    def _phase2_step3(self):
        # Finding final implementations
        for obj in self.iterate([ast.YASDLField, ast.YASDLFieldSet]):
            if not hasattr(obj, 'final_implementor'):
                self.set_final_implementation_of(obj)

    def _phase2_step4(self):
        # Check final an abstract modifiers
        for obj in self.iterate([ast.YASDLField, ast.YASDLFieldSet]):
            if (obj.final_implementor == obj) and \
                    ('abstract' in obj.modifiers) and \
                    ('required' in obj.modifiers):
                self.append_error(obj,
                                  _("Abstract definition has no implementation defined "),
                                 "02041")
            if (obj.final_implementor != obj) and \
                    ('final' in obj.modifiers):
                msg = _("Trying to implement a final definition.")
                code = "02042"
                self.append_error(obj, msg, code)
                self.append_error(obj.final_implementor, msg, code)

    def _phase2_step5(self):
        """Implementations and specifications cannot contain each other."""
        # First we divide definitions by their final implementors.
        trees = {}
        for obj in self.iterate([ast.YASDLField, ast.YASDLFieldSet]):
            fi = obj.final_implementor
            if fi in trees:
                trees[fi].add(obj)
            else:
                trees[fi] = {obj}

        for fi, items in trees.items():
            # This may look slow. However, implementation trees usually
            # contain a few items only, so it is not that slow.
            for i1 in items:
                for i2 in items:
                    if id(i1) > id(i2):
                        if i1.owns(i2):
                            msg = _("Definitions in the same " +
                                    "implementation tree cannot contain each other.")
                            code = "02051"
                            self.append_error(i1, msg, code)
                            self.append_error(i2, msg, code)

        # In the documentation, this is step 6. But since we already have
        # the trees, it is much faster to do it here.
        for fi, items in trees.items():
            for item in items:
                while True:
                    added = 0

                    for spec in items:
                        if (spec.direct_implementor is item) or \
                                (spec.direct_implementor in item.specifications):
                            if not spec in item.specifications:
                                item.specifications.add(spec)
                                added += 1

                    for imp in items:
                        if (item.direct_implementor is imp) or \
                                (item.direct_implementor in imp.specifications):
                            if not imp in item.implementations:
                                item.implementations.add(imp)
                                added += 1

                    if not added:
                        break

    def _phase3_step1(self, obj):
        if isinstance(obj, ast.YASDLProperty) and obj.name == "ancestors":
            pif = isinstance(obj.owner, ast.YASDLField)
            pifs = isinstance(obj.owner, ast.YASDLFieldSet)
            if not pif and not pifs:
                self.append_error(obj,
                                  _("Can only use 'ancestors' inside fields and fieldsets."),
                                 "03011")
                return

            good_min_classes = {obj.owner.__class__}

            for name in obj.items:
                if isinstance(name, ast.dotted_name):

                    if name.min_classes is None:
                        name.min_classes = good_min_classes
                    elif name.min_classes != good_min_classes:
                        if isinstance(obj.owner, ast.YASDLField):
                            self.append_error(obj,
                                              _("Fields can only be inherted from fields."),
                                             "03012")
                        else:
                            self.append_error(obj, _("Fieldsets can only " +
                                                    "be inherited from fieldsets."), "03012")
                        continue

                    path = self._bindpath_static(obj, name, recursive=True,
                                                 excludes=[obj.owner])
                    # Actually this "means" o.final_implementor
                    name.refpath = path
                    if path:
                        name.ref = o = path[-1]
                    else:
                        name.ref = o = None

                    if o is None:
                        self.append_error(obj,
                                          _("Definition %s not found (#3) ") % name, "03013")
                    # Should not happen because of min_classes.
                    elif pif and not isinstance(o, ast.YASDLField):
                        msg = _("A field cannot be the ancestor " +
                                "of a non-field.")
                        code = "03014"
                        self.append_error(o, msg, code)
                        self.append_error(obj, msg, code)
                    # Should not happen because of min_classes.
                    elif pifs and not isinstance(o, ast.YASDLFieldSet):
                        msg = _("A fieldset %s cannot be the ancestor " +
                                "of a non-fieldset.")
                        code = "03015"
                        self.append_error(o, msg, code)
                        self.append_error(obj, msg, code)
                    elif o is obj.owner:
                        self.append_error(obj,
                                          _("Nothing can be the ancestor of itself."),
                                         "03016")
                    elif o.owns(obj):
                        msg = _("Descendant cannot statically contain " +
                                "its ancestor.")
                        code = "03017"
                        self.append_error(obj, msg + " (" +
                                          _("decendant") + ")", code)
                        self.append_error(o, msg + " (" + _("ancestor") + ")",
                                          code)
                    elif obj.owns(o):
                        msg = _("Ancestor cannot statically contain " +
                                "its descendant.") + " (%s)"
                        code = "03018"
                        self.append_error(o, msg % _("ancestor"), code)
                        self.append_error(obj, msg % _("decendant"), code)
                else:
                    self.append_error(obj,
                                      _("Definition %s not found (#4) ") % name, "03019")

    def _phase3_step2(self):
        """No circular ancestors.

        Nothing can be the ancestor of itself. Cannot have circular
        references by ancestors statements or the colon operator.
        Note: the checker only displays the first error.
        """
        for obj in self.iterate([ast.YASDLField, ast.YASDLFieldSet]):
            if not self._check_circular(obj, 'ancestors', "03021"):
                break

    def _phase3_step3(self):
        """Def with imp_name ancestors cannot implement other definitions."""
        for obj in self.iterate([ast.YASDLField, ast.YASDLFieldSet]):
            # No need to check for min_classes because "implements"
            # can only be a property.
            implements = obj.bind_static("implements", recursive=False)
            if implements and implements.items:
                if self._has_imp_ancestor(obj):
                    self.append_error(obj,
                                      _("Definitions with imp_name ancestors cannot " +
                                       "implement other definitions."), "03031")

    def _phase3_step4(self):
        """Calculate all ancestors and descendants."""
        # First we determine inheritance graphs. This is very tricky, indeed!
        # Calculate all ancestors in the right order.
        defiter = functools.partial(self.iterate,
                                    [ast.YASDLField, ast.YASDLFieldSet])
        for obj in defiter():
            # obj.ancestors = []
            # No need to check for min_classes because "ancestors"
            # can only be a property.
            prop_ancestors = obj.bind_static("ancestors", recursive=False)
            if prop_ancestors:
                for item in prop_ancestors.items:
                    if item.imp:
                        obj.ancestors.append(item.ref.final_implementor)
                    else:
                        obj.ancestors.append(item.ref)
        # Calculate all descendants.
        for ancestor in defiter():
            ancestor.descendants = set([])
            for descendant in defiter():
                if ancestor in descendant.ancestors:
                    ancestor.descendants.add(descendant)

    def _phase3_step5(self):
        """Within one inheritance graph, no def can contain another def."""
        # We need to classify definitions into graphs.
        # This is very tricky indeed!
        alldefs = set([obj for obj in self.iterate(
            [ast.YASDLField, ast.YASDLFieldSet])])
        graphs = []
        while alldefs:
            item = alldefs.pop()  # Get one element
            unprocessed, processed = {item}, set([])
            # Now, process.
            while unprocessed:
                item = unprocessed.pop()
                for ancestor in item.ancestors:
                    if ancestor in alldefs:
                        alldefs.remove(ancestor)
                        unprocessed.add(ancestor)
                for descendant in item.descendants:
                    if descendant in alldefs:
                        alldefs.remove(descendant)
                        unprocessed.add(descendant)
                processed.add(item)
            graphs.append(processed)

        for graph in graphs:
            # This may look slow. However, implementation trees usually
            # contain a few items only, so it is not that slow.
            for i1 in graph:
                for i2 in graph:
                    if id(i1) > id(i2):
                        if i1.owns(i2):
                            msg = _("Definitions in the same inheritance " +
                                    "graph cannot contain each other.")
                            code = "03051"
                            self.append_error(i1, msg, code)
                            self.append_error(i2, msg, code)

    def _phase3_step6(self):
        """Cache all members of all definitions."""
        for obj in self.iterate():
            obj._cache_members()

    def _phase3_step7(self):
        """List unused deletions as compiler warnings."""
        for obj in self.iterate():
            if obj.unused_deletions:
                for item in obj.items:
                    if item.name in obj.unused_deletions:
                        self.append_warning(item,
                                            _("Useless use of name deletion."), "03071")

    def _bind(self, obj, name, recursive=True, excludes=None):
        """Dynamic binding.

        Similar to ast.bind, but it considers alias names of
        used/required schemas. The name parameter MUST be a dotted
        name, and its min_classes attribute is used to narrow down
        the search.
        """
        res = self._bindpath(obj, name, recursive, excludes)
        if res:
            return res[-1]
        else:
            return None

    def _bindpath(self, obj, name, recursive=True, excludes=None):
        """Dynamic binding.

        Similar to ast.bindpath, but it considers alias names of
        used/required schemas. The name parameter MUST be a dotted
        name, and its min_classes attribute is used to narrow down
        the search.
        """
        assert (isinstance(name, ast.dotted_name))
        if obj:
            schema = obj.owner_schema
            # First, try to find by normal dynamic binding.
            if name.absolute:
                path = schema.bindpath(name, name.min_classes, recursive,
                                       excludes)
            else:
                path = obj.bindpath(name, name.min_classes, recursive,
                                    excludes)
            if path:
                return path

            # Then, try to find in in used schemas.
            for use in schema.uses:
                if use.alias is None:
                    prefix = use.name
                else:
                    prefix = use.alias
                if name.startswith(prefix):
                    subname = name[len(prefix) + 1:]
                    path = use.schema.bindpath(subname, name.min_classes,
                                               recursive, excludes)
                    if path:
                        path.insert(0, schema)
                        return path

            # Finally, we check if the name is prefixed with the
            # package name of the owner schema.
            if not name.absolute:
                if name.startswith(schema.package_name):
                    subname = name[len(schema.package_name) + 1:]
                    path = schema.bindpath(subname, name.min_classes,
                                           recursive, excludes)
                    if path:
                        self.append_warning(obj,
                                            _("Absolute name used to access an object " +
                                             "inside the same schema (instead of " +
                                             "'schema.<name>')."), "99012")
                        path.insert(0, schema)
                        return path

        return None

    def _phase4_step1(self, obj):
        if isinstance(obj, ast.YASDLProperty) and (obj.name == "references"):
            if len(obj.items) > 1:
                self.append_error(obj, _("The references property cannot " +
                                        "have more than one argument."), "04011")
            elif len(obj.items) == 1:
                name = obj.items[0]
                if isinstance(name, ast.dotted_name):
                    if name.min_classes is None:
                        name.min_classes = {ast.YASDLFieldSet}
                    elif name.min_classes != {ast.YASDLFieldSet}:
                        self.append_error(obj,
                                          _("Only fieldsets can be referenced."), "04012")
                else:
                    self.append_error(obj,
                                      _("Argument of the references property must be " +
                                       "a definition."), "04013")
            else:
                pass  # elif len(obj.items)==0: -- remove reference to fieldset

    def _phase4_step2(self, obj):
        if isinstance(obj, ast.YASDLProperty) and \
                (obj.name != "implements") and (obj.name != "ancestors"):
            for name in obj.items:
                if isinstance(name, ast.dotted_name):
                    path = self._bindpath(obj, name, recursive=True)
                    name.refpath = path
                    if path:
                        name.ref = path[-1]
                    else:
                        name.ref = None
                        self.append_error(obj,
                                          _("Definition %s not found (#5).") % name, "04021")

    def _phase4_step3(self, obj):
        if isinstance(obj, ast.YASDLProperty) and (obj.name == "references"):
            if len(obj.items) == 1:
                ref_obj = obj.items[0]
                ref = ref_obj.ref.final_implementor
                if not ref.is_outermost():
                    msg = _("Trying to reference a non-outermost definition.")
                    msg += " (%s)"
                    code = "04031"
                    self.append_error(ref, msg % _("referenced from"), code)
                    self.append_error(obj, msg % _("references to"), code)

    def _phase4_step4(self, obj):
        if isinstance(obj, ast.YASDLIndex):
            fields = obj.get_fields()
            if not fields:
                self.append_error(obj,
                                  _("Index definition must specify its fields."), "04041")
                return
            if not fields.items:
                self.append_error(obj,
                                  _("Index definition must have at least one field."),
                                 "04042")
                return
            for item in fields.items:
                if not isinstance(item, ast.dotted_name) or (
                            not isinstance(item.ref, ast.YASDLField) and
                            not isinstance(item.ref, ast.YASDLFieldSet)):
                    self.append_error(fields, _("Arguments of the " +
                                               "'fields' property must be fields or fieldsets."), "04043")
                    return
            for item in fields.items:
                if not obj.owner.contains(item.ref):
                    if isinstance(item.ref, ast.YASDLField):
                        msg = _("Trying to index on a field that is " +
                                "not contained the fieldset.")
                    else:
                        msg = _("Trying to index on a fieldset that is " +
                                "not contained the fieldset.")
                    msg += " (%s)"
                    code = "04044"
                    self.append_error(fields, msg % _("referenced from"), code)
                    self.append_error(item.ref, msg % _("references to"), code)
                    return
            fset = set([])
            for item in fields.items:
                if item.ref in fset:
                    msg = _("Duplicate field in index definition. (%s)")
                    code = "04045"
                    self.append_error(obj, msg % _("referenced from"), code)
                    self.append_error(item.ref, msg % _("references to"), code)
                else:
                    fset.add(item.ref)


    def _phase4_step5(self, obj):
        if isinstance(obj, ast.YASDLConstraint):
            check = obj.get_check()
            if not check:
                self.append_error(obj,
                                  _("Constraint definition must specify its check condition."), "04051")
                return
            if not check.items:
                self.append_error(obj, _("Empty check"), "04052")
                return
            for item in check.items:
                if isinstance(item, ast.dotted_name):
                    if not isinstance(item.ref, ast.YASDLField):
                        self.append_error(check, _("Arguments of the " +
                                               "'check' property must be strings or fields."), "04053")
                    return
            for item in check.items:
                if isinstance(item, ast.dotted_name):
                    if not obj.owner.contains(item.ref):
                        self.append_error(check,
                                          _("Trying to use a field in a check constraint " +
                                          "that is not contained by the fieldset"), "04054")
                    return

    def _phase5_step1_and_step2_and_step3(self):
        # Finding out what schemas are required.
        #
        # Schemas
        #
        realized_schemas = set([])
        # Top schemas are realized.
        for main_src in self.parsed.main_srcs:
            main_schema = self.parsed.schemas[main_src]
            realized_schemas.add(main_schema)
        # Now the recursive steps: if a required schema is requiring
        # another schema...
        while True:
            req_before = len(realized_schemas)
            for schema in copy.copy(realized_schemas):
                for use in schema.uses:
                    if 'required' in use.modifiers:
                        realized_schemas.add(use.schema)
            req_after = len(realized_schemas)
            if req_before == req_after:
                break

        for schema in self.iterate([ast.YASDLSchema]):
            schema.realized = schema in realized_schemas

        #
        # Finding out what final implementations are required.
        #
        # Note: this is "phase 5 step 2" in the documentation
        #

        #
        # Fieldsets
        #
        realized_fieldsets = set([])
        toplevel_fieldsets = set([])
        realized_fields = set([])

        # First step: if an outermost fieldset definition has the required
        # modifier and is placed in a realized schema, then its
        # final implementation must be realized. (Outermost means:
        # defined at schema level, not inside another fieldset.)
        for schema in realized_schemas:
            for item in schema.items:
                if isinstance(item, ast.YASDLFieldSet):
                    if 'required' in item.modifiers and item.is_outermost():
                        if item.final_implementor.is_outermost():
                            realized_fieldsets.add(item.final_implementor)
                            toplevel_fieldsets.add(item.final_implementor)
                        else:
                            msg = _("Final implementation of required " +
                                    "outermost fieldset sould be outermost, " +
                                    "but it is not.") + " (%s)"
                            code = "05011"
                            self.append_error(item, msg % _("specification"),
                                              code)
                            self.append_error(item.final_implementor,
                                              msg % _("implementation"), code)

        #
        # Recursive sub-steps
        #
        while True:
            req_before = len(realized_fieldsets) + len(realized_fieldsets)

            # If a fieldset is realized, then all of its members
            # are realized. And they are not top level...
            for item in copy.copy(realized_fieldsets):
                for member_path in item.itercontained([ast.YASDLField]):
                    realized_fields.add(member_path[-1])
                for member_path in item.itercontained([ast.YASDLFieldSet]):
                    realized_fieldsets.add(member_path[-1])

            # If a realized field references another F fieldset with the
            # references property (or the arrow operator), then the
            # final implementation of the F fieldset is must be realized.
            # And it must be outermost, but we have already checked that
            # in phase 4 step 3. Universal references are ignored - they
            # do not generate requirements, but they can only reference to rows
            # stored in realized fieldsets.
            #
            for item in copy.copy(realized_fieldsets):
                for member_path in item.itercontained([ast.YASDLField]):
                    member = member_path[-1]
                    prop_ref = member.bind_static('references', None, False)
                    if prop_ref:
                        ref_obj = prop_ref.items[0]
                        referenced = ref_obj.ref.final_implementor
                        realized_fieldsets.add(referenced)
                        toplevel_fieldsets.add(referenced)

            req_after = len(realized_fieldsets) + len(realized_fieldsets)

            if req_before == req_after:
                break

        # Set some important attributes.
        self.parsed.toplevel_fieldsets = toplevel_fieldsets
        for item in self.parsed.iterate([ast.YASDLFieldSet]):
            item.realized = item in realized_fieldsets
            item.toplevel = item in toplevel_fieldsets
        for item in self.parsed.iterate([ast.YASDLField]):
            item.realized = item in realized_fields
        while True:
            added = 0
            for item in self.parsed.iterate(
                    [ast.YASDLField, ast.YASDLFieldSet]):
                if item.realized:
                    for spec in item.specifications:
                        if not spec.realized:
                            spec.realized = True
                            added += 1
            if not added:
                break

    def _phase5_step4(self, obj):
        if isinstance(obj, ast.YASDLField) or \
                isinstance(obj, ast.YASDLFieldSet):
            if obj.realized and obj.final_implementor is obj:
                if "abstract" in obj.modifiers:
                    msg = _("This abstract definition must be realized, " +
                            " but it has no fallback implementation.")
                    code = "05031"
                    self.append_error(obj, msg, code)

    def _phase6_step1(self):
        """Check realization of required defs.

        For every realized fieldset, required members of its
        specifications must be realized."""
        for obj in self.iterate([ast.YASDLFieldSet]):
            if obj.realized:
                for spec in obj.iterspecifications():
                    # Iterate over members of the specification, e.g.
                    # it will also contain items that are hidden
                    # by its implementation.
                    #
                    for item in spec.items:
                        if isinstance(item, ast.YASDLField) or \
                                isinstance(item, ast.YASDLFieldSet):
                            if ("required" in item.modifiers) and \
                                    (not item.realized):
                                msg = _("Required definition is not realized.")
                                msg += " (%s)"
                                code = "06011"
                                self.append_error(item, msg % \
                                                  _("required"), code)
                                self.append_error(spec, msg % \
                                                  _("specification of owner"), code)
                                self.append_error(obj, msg % \
                                                  _("realization of owner"), code)

    def _phase7_step1(self, obj):
        if isinstance(obj, ast.YASDLFieldSet) and \
                obj.realized and obj.toplevel:
            has_field = False
            for member_path in obj.itercontained():
                if isinstance(member_path[-1], ast.YASDLField):
                    has_field = True
                    break
            if not has_field:
                self.append_error(obj, _("Realized top level fieldsets " +
                                        "must contain at least one field."), "07011")

    def _phase7_step2(self, obj):
        if isinstance(obj, ast.YASDLFieldSet) and obj.realized and \
                not obj.toplevel:
            has_field = False
            for member_path in obj.itercontained():
                if isinstance(member_path[-1], ast.YASDLField):
                    has_field = True
                    break
            if not has_field:
                self.append_warning(obj, _("Realized non-toplevel " +
                                          "fieldsets should contain at least one field."), "07021")

    def _phase7_step3(self, obj):
        if isinstance(obj, ast.YASDLField) and obj.is_outermost():
            if "required" in obj.modifiers:
                self.append_warning(obj, _("Outermost field definitions " +
                                          "should not be required - it is meaningless."), "07031")

    def _phase7_step4(self, obj):
        if isinstance(obj, ast.YASDLFieldSet) and \
                obj.realized and obj.toplevel:
            for spec in obj.specifications:
                if not spec.is_outermost():
                    msg = _("Top level realized fieldset definition " +
                            "should not have any specification that is " +
                            "not outermost.")
                    msg += " " + _("May result in realizing copies of its contents.")
                    msg += " " + _("Indicates bad design.")
                    msg += " (%s)"
                    code = "07041"
                    self.append_notice(spec, msg % _("specification"), code)
                    self.append_notice(obj, msg % _("realization"), code)

    def _phase7_step5(self, obj):
        if isinstance(obj, ast.YASDLField):
            has_ref = obj.get_referenced_fieldset() is not None
            if obj.has_member("type"):
                typ = obj["type"]
                if len(typ.items) != 1 or not isinstance(typ.items[0], str):
                    self.append_error(obj,
                                      _("Type property must have a " +
                                       "single string argument, or no argument at all."), "07051")

                if has_ref and typ.items and typ.items[0] != "identifier":
                    self.append_error(obj,
                                      _("Referencing field must have " +
                                       "'identifier' type."), "07052")

            if obj.realized:
                if not obj.get_type():
                    self.append_error(obj,
                                      _("Realized fields must have a type."), "07054")

    def _phase7_step6(self, obj):
        if isinstance(obj, ast.YASDLField):
            if obj.has_member("size"):
                size = obj["size"]
                if len(size.items) != 1 or not isinstance(size.items[0], int):
                    self.append_error(size,
                                      _("'size' property must have " +
                                       "a single integer argument."), "07061")

    def _phase7_step7(self, obj):
        if isinstance(obj, ast.YASDLField):
            if obj.has_member("precision"):
                precision = obj["precision"]
                if len(precision.items) != 1 or \
                        not isinstance(precision.items[0], int):
                    self.append_error(precision,
                                      _("'precision' property must have " +
                                       "a single integer argument."), "07071")

    def _phase7_step8(self, obj):
        if not isinstance(obj, ast.YASDLField):
            if obj.has_member("notnull"):
                self.append_error(obj["notnull"],
                                  _("'notnull' property can only be used " +
                                   "inside field definitions."), "07081")
        else:
            if obj.has_member("notnull"):
                notnull = obj["notnull"]
                if len(notnull.items) != 1 or \
                        not isinstance(notnull.items[0], bool):
                    self.append_error(notnull,
                                      _("'notnull' property must have " +
                                       "a single boolean argument."), "07082")

    def _phase7_step9(self, obj):
        if not isinstance(obj, ast.YASDLIndex):
            if obj.has_member("unique"):
                self.append_error(obj["unique"],
                                  _("'unique' property can only be used " +
                                   "inside index definitions."), "07091")
        else:
            if obj.has_member("unique"):
                unique = obj["unique"]
                if len(unique.items) != 1 or \
                        not isinstance(unique.items[0], bool):
                    self.append_error(unique,
                                      _("'unique' property must have " +
                                       "a single boolean argument."), "07092")

    def _phase7_step10(self, obj):
        if not isinstance(obj, ast.YASDLField):
            if obj.has_member("immutable"):
                self.append_error(obj["immutable"],
                                  _("'immutable' property can only be used " +
                                   "inside field definitions."), "07101")
        else:
            if obj.has_member("immutable"):
                immutable = obj["immutable"]
                if len(immutable.items) != 1 or \
                        not isinstance(immutable.items[0], bool):
                    self.append_error(immutable,
                                      _("'immutable' property must have " +
                                       "a single boolean argument."), "07102")

    def _phase7_step11(self, obj):
        if obj.has_member("guid"):
            guid = obj["guid"]
            if len(guid.items) != 1 or \
                    not isinstance(guid.items[0], str):
                self.append_error(guid,
                                  _("'guid' property must have " +
                                   "a single non-empty string argument."), "07111")
            else:
                if guid in self.parsed.all_guids:
                    self.append_error(obj,
                                      _("Values of the guid property must be unique in the compilation set."),
                                      "07112")
                    self.append_error(self.parsed.all_guids[guid],
                                      _("Values of the guid property must be unique in the compilation set."),
                                      "07112")
                else:
                    self.parsed.all_guids[guid.items[0]] = obj


    def _phase7_step12(self, obj):
        if not isinstance(obj, ast.YASDLField):
            if obj.has_member("ondelete"):
                self.append_error(obj["ondelete"],
                                  _("'ondelete' property can only be used " +
                                   "inside field definitions."), "07121")
            if obj.has_member("onupdate"):
                self.append_error(obj["onupdate"],
                                  _("'onupdate' property can only be used " +
                                   "inside field definitions."), "07122")
        else:
            if obj.has_member("ondelete"):
                ondelete = obj["ondelete"]
                if len(ondelete.items) != 1 or \
                        not isinstance(ondelete.items[0], str) or \
                        (ondelete.items[0] not in ["cascade", "setnull", "noaction"]):
                    self.append_error(ondelete,
                                      _("Argument of 'ondelete' property must be in " +
                                       "['cascade','setnull','noaction']"), "07123")
            if obj.has_member("onupdate"):
                onupdate = obj["onupdate"]
                if len(onupdate.items) != 1 or \
                        not isinstance(onupdate.items[0], str) or \
                        (onupdate.items[0] not in ["cascade", "setnull", "noaction"]):
                    self.append_error(onupdate,
                                      _("Argument of 'onupdate' property must be in " +
                                       "['cascade','setnull','noaction']"), "07123")

    def _phase7_step13(self, obj):
        msg = _("Index is part of a realized final implementation, " +
                "so it should be created, but its field is not realized.")
        msg += " (%s)"
        code = "07131"
        if isinstance(obj, ast.YASDLFieldSet) and obj.realized \
                and obj.final_implementor is obj:
            for idx in obj.members:
                if isinstance(idx, ast.YASDLIndex):
                    fields = idx.get_fields()
                    for fieldref in fields.items:
                        field = fieldref.ref
                        if not field.realized:
                            self.append_error(obj, msg % _("table"), code)
                            self.append_error(fields, msg % _("index"), code)
                            self.append_error(field, msg % _("field"), code)

    def _phase7_step14(self, obj):
        msg = _("The 'language' property is not defined for this schema, " +
                "assuming 'en'.")
        code = "07141"
        if isinstance(obj, ast.YASDLSchema):
            langprop = obj.bind_static("language", [ast.YASDLProperty], False)
            if langprop is None:
                self.append_warning(obj, msg, code)

    def _phase7_step15(self, obj):
        if isinstance(obj, ast.YASDLProperty) and obj.name == "language":
            if not isinstance(obj.owner, ast.YASDLSchema):
                self.append_error(obj, _("The language property can " +
                                        "only be defined at schema level."), "07151")

    def _phase7_step16(self, obj):
        if isinstance(obj, ast.YASDLProperty) and obj.name == "cluster":
            if not isinstance(obj.owner, ast.YASDLFieldSet):
                self.append_error(obj, _("The cluster property can " +
                                        "only be defined at fieldset level."), "07161")
            elif len(obj.items) == 0:
                # No clustering
                pass
            elif len(obj.items) > 1:
                self.append_error(obj, _("The cluster property " +
                                        "can only have zero or one argument."), "07162")
            else:
                item = obj.items[0]
                if not isinstance(item, ast.dotted_name) or \
                        not isinstance(item.ref, ast.YASDLIndex) or \
                                item.ref.owner.final_implementor \
                                is not obj.owner.final_implementor:
                    self.append_error(obj, _("The cluster property's " +
                                            "argument must be an index that is defined on the " +
                                            "same level"), "07163")

    def _phase7_step17(self, obj):
        if isinstance(obj, ast.YASDLProperty) and obj.name == "reqlevel":
            reqlevel = obj
            if len(reqlevel.items) != 1 or \
                    not isinstance(reqlevel.items[0], str) or \
                    (reqlevel.items[0] not in ["required", "desired", "optional"]):
                self.append_notice(reqlevel,
                                  _("Argument of 'reqlevel' property shoud be in " +
                                    "['required', 'desired', 'optional']"), "07171")
            else:
                if (reqlevel.items[0]=="required") and not obj.owner.get_singleprop("notnull", False):
                    self.append_notice(reqlevel,
                                       _("Required fields should also be 'notnull true'."), "07172")

    def _phase7_step18(self, obj):
        if isinstance(obj, ast.YASDLField):
            prop_notnull = obj.get_singleprop("notnull")
            prop_ondelete = obj.get_singleprop("ondelete")
            prop_onupdate = obj.get_singleprop("onupdate")
            if prop_notnull:
                if prop_ondelete == 'setnull':
                    self.append_error(prop_notnull,
                                      _("Must not have 'notnull true' and 'ondelete setnull' combination."),
                                      "07181")
                    self.append_error(prop_ondelete,
                                      _("Must not have 'notnull true' and 'ondelete setnull' combination."),
                                      "07181")
                if prop_onupdate == 'setnull':
                    self.append_error(prop_notnull,
                                      _("Must not have 'notnull true' and 'onupdate setnull' combination."),
                                      "07182")
                    self.append_error(prop_onupdate,
                                      _("Must not have 'notnull true' and 'onupdate setnull' combination."),
                                      "07182")

    def _phase7_step19(self, obj):
        if isinstance(obj, ast.YASDLSchema):
            guid = obj.get_singleprop("guid", None)
            if guid is None:
                self.append_error(obj,
                                  _("All schemas must have a guid property."),
                                  "07181")
        elif isinstance(obj, ast.YASDLFieldSet) and obj.realized and obj.toplevel and obj.final_implementor is obj:
            guid = obj.get_singleprop("guid", None)
            if guid is None:
                self.append_error(obj,
                                  _("All self-realized toplevel fieldsets must have a guid property."),
                                  "07182")

    def _phase8_step1(self, obj):
        """Database driver specific checks."""
        if self.dbdriver and isinstance(obj, ast.YASDLField) and obj.realized:
            typ = obj.get_type()
            try:
                typeinfo = self.dbdriver.get_typeinfo(typ)
            except KeyError:
                self.append_error(obj["type"],
                                  _("Type '%s' is not supported by this diver.") % typ,
                                 "08011")
                return

            if typeinfo["need_size"] and obj.get_size() is None:
                self.append_error(obj,
                                  _("Field of type '%s' must have a size given.") % typ,
                                 "08012")
            if typeinfo["need_precision"] and obj.get_precision() is None:
                self.append_error(obj, _("Field of type '%s' must have a precision given.") % typ, "08013")

    def compile(self, strict=False):
        """Compile the schema.

        :param strict: Set this flag if you want to treat warnings as errors, e.g. warnings will also result
            in False return value.
        :return: True if the compilation was successful, False otherwise.

        This method finds final implementations and creates cross references between specifications and their
        final implementations. For a detailed description about the compilation process, see the "YASDL Compiler"
        section in the reference documentation.

        """
        # Phase 1 - general semantic check.
        self._phase1_step1()

        #self._phase1_step2() # 2017-12-13 - we allow circular references, from now on.

        for step in range(6):
            phase_method = getattr(self, '_phase1_step' + str(step + 3))
            for item in self.iterate():
                phase_method(item)
            if self.has_error or (strict and self.has_warning):
                return False
        self._phase1_step9()
        if self.has_error or (strict and self.has_warning):
            return False

        # Phase 2 - building implementation trees
        for step in range(5):
            phase_method = getattr(self, '_phase2_step' + str(step + 1))
            phase_method()
            if self.has_error or (strict and self.has_warning):
                return False

        # Phase 3 - building inheritance graph
        for item in self.iterate():
            self._phase3_step1(item)
        if self.has_error or (strict and self.has_warning):
            return False
        for step in range(6):
            phase_method = getattr(self, '_phase3_step' + str(step + 2))
            phase_method()
            if self.has_error or (strict and self.has_warning):
                return False

        # Phase 4 - binding all other names dynamically.
        for step in range(5):
            phase_method = getattr(self, '_phase4_step' + str(step + 1))
            for item in self.iterate():
                phase_method(item)
            if self.has_error or (strict and self.has_warning):
                return False

        # Phase 5 - find out what is realized
        self._phase5_step1_and_step2_and_step3()
        if self.has_error or (strict and self.has_warning):
            return False
        for item in self.iterate():
            self._phase5_step4(item)
        if self.has_error or (strict and self.has_warning):
            return False

        # Phase 6 - check if required definitions are realized.
        self._phase6_step1()
        if self.has_error or (strict and self.has_warning):
            return False

        # Phase 7 - other checks
        self.parsed.all_guids = {}
        step = 0
        while True:
            phase_method = getattr(self, '_phase7_step' + str(step + 1), None)
            if phase_method is None:
                break
            for obj in self.iterate():
                phase_method(obj)
            if self.has_error or (strict and self.has_warning):
                return False
            step += 1

        # Phase 8 - database type dependent checks.
        for item in self.iterate():
            self._phase8_step1(item)
        if self.has_error or (strict and self.has_warning):
            return False

        return True
