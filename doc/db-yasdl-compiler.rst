==================
The YASDL Compiler
==================

This section contains implementation details of the YASDL language. It is more likely a list of instructions that tells
how to write a compiler that parse and analyzes YASDL documents, and build a DOM from them. This section has two
purposes:

* This is also a reference that helps development: to documents how the compiler should work.
* It can also be used to build a category tree of compiler messages, and help the advanced user to understand what
  these messages mean exactly, and in what phase of the compilation they were created.

Introduction
============

Let's say we want to solve several tasks, and we have schemas defined for those tasks. We want to have a program -
the YASDL complier - that creates a formal database definition automatically. So we have some YASDL documents that we
pass to the complier program. The schemas found in these documents are called the *top schemas*. They can reference
other schemas using the use and require statements. Of course we do not want to generate unnecessary things into
the database. For example, we used a schema just because we liked one of its fieldsets, and used this fieldset as
an ancestor. We do not really need this schema for anything else. It would be bad to generate tables for all
of its outermost fieldsets. But we do want to put in everything that is required to solve the task. The
compiler needs to decide what definitions will be used for database generation. The compiler selects a subset
from the final implementations and use them for database generation.

The compiler loads the source code, does a general semantic analysis, then divides definitions into two groups:
final implementations and their specifications. Then it uses the required modifier and recursive steps to determine
what needs to be generated.

So the compiler works in phases. Phases contain multiple steps. Below we are going to document the phases, one by one.

Phase 0 - load all referenced schemas
=====================================

Top schemas are loaded first. They are syntax checked and parsed into an abstract syntax tree. Other used schemas
(see the use and require statements above) will be loaded and syntax checked recursively until there will be no more
references to unloaded schemas. Syntax is checked immediately - syntactically incorrect documents will cause the
compiler to stop loading further documents.

While loading used schemas stored in local files, their source file names are converted to full file paths. The full
file path (or the URI for uri use statements) is used to decide if a schema was already loaded or not, resulting in a
graph of use statements between loaded schemas. You should never use multiple symbolic links, URL redirection, host
alias names and similar techniques unless you want to crash the compiler completely. Under unix systems, you should
also not use directory names where only character cases are different. By convention, you should always use lower case
names for directories and files that contain YASDL schemas.

While loading schemas, referenced names after all arrow operators are converted to references properties and ancestors
listed after the colon operator are converted to ancestors properties.

After all schemas are loaded, their package names are checked. Any locally stored schema that was used or required from
another schema, must have an exactly matching package name given after the schema keyword. Any schema that was loaded
from an URI must have a package name that follows the reverse domain name notation (and the www suffix is not needed).

Schemas are also checked for package name duplication. There can be no package name duplications throughout the whole
schema set that is about to be compiled.

This is called "phase zero" because it is not really part of the compiling. It is just about loading the sources into
a syntax tree, nothing semantic. This part is implemented in venus.db.yasdl.parser.Parser.YASDLParser.parse and in fact
you can create your own AST in other ways and pass the AST to the compiler. Formally, the compiler expects an
SSDParseResult as its argument.

Phase 1 - per schema semantic checks
====================================

In this phase, the AST is checked against several rules. Some of them were already mentioned in the reference
documentation. These rules are checked in the order given below. For a given step, all schemas are checked one by one,
and all errors are listed (not just the first one). If a step fails, then further steps will not be taken (the compiler
exits with an error code).

1. Nothing can use/require itself. Within one schema, you cannot have multiple use statements, referencing to the same
   schema document.
2. Use/require statements can be used to create circular references between schemas. (In the previous version,  it
   was not allowed.)
3. Cannot have invalid names for definition names and alias names. Invalid names are id, all reserved words and anything
   with the "." dot character inside. Usage of names of special properties ( ancestors, references, implements, unique,
   fields, index, property) for non-properties is also forbidden. (Some but not all of these constraints are also
   enforced by the syntax of the language.)
4. Cannot have duplicate names within a {} block. Names can be names of field definitions, fieldset definitions, use
   statement aliases, name deletions and properties, and they are not distinguished. E.g. these are invalid:

   .. code-block:: yasdl

      schema s {
        use q;      # Defines the name 'q' here, athough it is not a definition.
        use r.s.t;  # Defines the name 'r' here, athough it is not a definition.

        fieldset a;
        field a; # Invalid - 'a' already defined in this block.
        fieldset b {
            field c;
            c 12; # Invalid, 'c' already defined in this block.
        }
        fieldset d {
            field e;
            delete e; # Invalid, 'e' already defined in this block.
        }

        fieldset q;   # Invalid, q is already defined in this block.
        fieldset r;   # Invalid, r is already defined in this block.
      }

   E.g. you cannot have more definitions (field, fieldset, index, deletion, property) with the same name inside the
   same schema, fieldset or index. NOTE: Upon successful check, dotted names become unambiguous. Although they are not
   yet bound to definitions by the compiler. Although name deletions are not real definitions, and they don't have
   a name, because they don't define one.

   .. todo::

      We should also check if the used/required schema's package name matches
      the name that was used in the use/require statement. For web based resources, the only criterion is that the package
      name starts with the domain name. E.g. when downloaded from "www.my.domain.com" then the package should start with
      "com.domain.my". (www can be left out).

5. Any object with the name references ancestors implements unique or fields must be a property.

  .. todo::

    add other checks for special properties!

6. You can never specify both the abstract and the final modifiers for the same definition.
7. Then the all keywords in implements property definitions are converted to actual names. A set of names after is
   determined for every implements occurence. In this step, the compiler also checks if any imp_name was used after
   any implements property. If so, then it is an error and the compiler stops. Using an argument after implements that
   is not a dotted name is also  prohibited, and results in an error. Specifying min_classes is not needed. The compiler
   automatically sets min_classes to match the owner of the implements property. In other words, fields can only be
   implementing fields, and fieldsets can only be implementing fieldsets. It is not an error to give min_classes, but
   then its value must be appropiate.
8. Bind names statically in every implements property to definitions. All names after the implements property must not
   be imp_names by now, and they cannot refer to any inherited name (by design). In this complex step, the following
   things happen:

   *  The definition containing the implements property is checked. It must be a field or a fieldset definition.
   *  Then all arguments are interpreted as names and statically bound to other definitions. These names can be
      relative names (accessing definitions inside the containing schema), or they can be absolute names, accessing
      definitions in others schemas that were used or required. Will only search for field and fieldset definitions.
      E.g. when relative names are used, then other elements (e.g. property, index) will not be found even if they
      can be accessed with the given relative static name. The definition that contains the actual implements property
      will always be excluded from the search.
   *  If the name cannot be bound to a definition, then an error is reported.
   *  Nothing can explicitly implement itself.
   *  A specification cannot statically contain its implementation.
   *  An implementation cannot statically contain its specification.

   Upon successful check, all arguments of all implements properties will be bound to definitions.

   Implementation note: the bound reference for the ``index``th member of ``defobj`` definition stored as
   ``defobj["implements"].items[index].refpath`` and ``defobj["implements"].items[index].ref``

9. Cannot have circular references through the implements property. Note: the compiler will only list the first error.

More implementation notes:

* ``venus.db.yasdl.ast.YASDLItem.bind_static`` is used for statically binding names, but that doesn't support alias
  names.
* To bind statically with alias names support, use ``YASDLParseResult.bind_static()``. It has an extra starting
  parameter that determines the starting point of the search.
* For more info, see these methods in the source code: ``venus.db.yasdl.compiler.Compiler._phase1_step*``

Phase 2 - building implementation trees
=======================================

In this phase, the whole AST is checked (e.g. not just individual schemas). The purpose of this phase is to build up
the implementation trees, and determine all "implementation-specification" relationships between all definitions.

1. No definition can be listed more than once after the implements property. All multiple implementation requests are
   searched in this step and all of them are listed as errors. When successful, this step will connect definitions with
   their direct implementors, forming a forest of implementation trees.

   Implementation note: in this step, all definitions will be assigned the direct_implementor property. It can be
   None (because nothing can explicitly implement itself, so if a definition is not implemented by another definition
   explicitly then direct_implementor becomes None

2. Cannot explicitly implement a definition that has imp_name ancestor(s).
3. Final implementations are determined for all definitions: for every implementation tree in the forest, the root is
   selected.

   Implementation note: Using the direct_implementor attributes created in the previous step, every definition gets
   assigned the final_implementor attribute. Please note that this attribute will never be None. E.g. a definition
   can be its own final implementation, then it will have a reference to itself.

4. Next, final and abstract modifiers are checked:

   * A definition that has the final modifier must be the final implementation of itself
   * A definition that has the abstract and required modifiers must not be the final implementation of itself

5. Static containment is checked. Within one implementation tree, no definition can statically contain another
   definition. The compiler will only list the first error, then exits.
6. Cache implementations and specifications. In this step, special attributes sets are created that are caching
   implementation/specification relationships. From this point, the following things become available:

   * ``specification_of`` method
   * ``implementation_of`` method
   * ``iterspecifications`` generator
   * ``iterimplementations`` generator

Implementation note:  source code in ``venus.db.yasdl.compiler.Compiler._phase2_step*``

Phase 3 - building inheritance graph
====================================

In this step, the compiler analyzes the arguments of the ancestors property for all definitions, and builds an
acyclic inheritance graph between the definitions.

1. Bind names in every ancestors property to definitions. This bind is neither static, neither dynamic (see explanation
    below). In this complex step, the following things happen:
    * The definition containing the ancestors property is checked. It must be a field or a fieldset definition.
    * If you don't specify min_classes after the ancestors property (or the colon operator) then the compiler will
      automatically match the class of the owner of the ancestors property. It is not an error to specify min_classes,
      but then it must contain the appropiate class (e.g. fields can only be inherited from fields, and fieldsets can
      only be inherited from fieldsets.)
    * Then all arguments are interpreted as names and first they are statically bound. These names can be relative
      names (accessing definitions inside the containing schema), or they can be absolute names, accessing definitions
      in others schemas that were used or required. Will only search for field and fieldset definitions. Other
      definitions will be excluded from the search. E.g. when relative names are used, then other elements (e.g.
      property, index) will not be found even if they can be accessed with the given relative static name. The
      definition that contains the actual ancestors property will always be excluded from the search.
      So consider the following example:

      .. code-block:: yasdl

           schema test {
               # more definitions here...

               fieldset location {
                   field city -> city;
                   field zip  { type "varchar"; size 10; }
                   field address1 { type "varchar"; size 200; }
               }

               # more definitions here...

               required fieldset person_location {
                   fieldset location : location;
                   # more definitions here...
               }
            }

      The main point: it is safe to use ``location : location`` here. The first ``location`` will be the name of a new
      fieldset. The second location is an ancestor, and it will be statically bound to test.location, because the
      newly created fieldset ``test.person_location.location`` is the owner of the (implicit) ancestors property, and
      so it is excluded from the search. This exclusion allows you to define a definition whose name matches the
      name of its ancestor. But please keep in mind that it works for ancestors and implements only.

    * If no definition can be found for the name, then an error is reported.
    * Nothing can be the ancestor of itself.
    * Ancestor cannot statically contain its (statically bound) descendant.
    * Descendant cannot statically contain its (statically bound) ancestor.

    Upon successful check, all arguments of all ancestors properties will be bound to definitions. It is very similar
    to the static binding of the implements property (phase 1 step 8), with one big difference: if an ``imp_name`` was
    used, then the argument will be bound statically by name, and then its ``final_implementor`` will be looked up to
    find the effective ancestor.

    Implementation note: Ancestors will be stored as ast.dotted_name instances, available as
    ``ancestor_ref = defobj["ancestors"].items[index]`` where:

    * ``ancestor_ref`` is a dotted name
    * ``ancestor_ref.refpath`` is a path containing the path of the static bind.
    * ``ancestor_ref.ref`` is a reference to the (statically bound) definition (this is the last element of refpath)
    * ``ancestor_ref.ref.final_implementor`` will actually be used as an ancestor: for searching/inheriting members.

2. Cannot have circular references through the ancestors property. Note: the compiler will only list the first error.
3. Definitions with imp_name ancestor(s) cannot implement other definitions.
4. Ancestors and descendants are fully calculated for all definitions. They are assigned an ancestors attribute which
   is a list, and a descendants attribute which is a set. It is important to understand that an ancestor can be given
   with an imp_name. In that case, the ancestor is the final implementation, and that ancestor is used for enumerating
   inherited members.
5. Containment is checked again. Within one inheritance graph, no definition can statically contain another definition.
   Please note that this is different from what we have done in step 1. Because in step 1, we have checked the
   statical containment between definitions and their statically bound ancestors/descendants. But in this new step,
   we check containment between descendants and their real ancestors. Because ancestors can be given with imp_name
   constructs, the real ancestor and the statically bound ancestor can be at different places in the source code.
6. So called ``members`` of all definitions are determined. (See the explanation below.) Every item in the AST is
   assigned a ``members`` attribute. That is a list of its members (in the right order). An internal cache is also
   created that allows fast dict-like access to members by their names, and the ``has_member(name)`` method becomes
   available.
7. Deletions that were not used to delete inherited definitions are listed as compiler warnings.

Implementation note: ``venus.db.yasdl.compiler.Compiler._phase3_step*``

Definition members
------------------

In phase 3 we create a cache of the so called members. A member is a reference to a definition (schema field fieldset
or property) and it is accessed through its own name. (That is, the name of the member). For any D definition,
members are defined as:

1. Any definition that is member of the first ancestor of D and not listed in a name deletion in D is a member of
   D with its own name.
2. Any definition that is member of the second ancestor of D and not listed in a name deletion in D is a member of D
   with its own name. If the same name was already listed in the previous step, then its value is overwritten.
3. Any definition that is member of the third ancestor of D and not listed in a name deletion in D is a member of D
   with its own name. If the same name was already listed in any of the previous steps, then its value is overwritten.
4. Continues recursively, ending with the last ancestor. E.g. any definition that is a member of the last ancestor of
   D and not listed in a name deletion in D is a member of D with its own name. If the same name was already listed
   in any of the previous steps, then its value is overwritten.
5. Finally, any definition that is placed directly inside the enclosing curly braces of D, is a member of D with its
   own name. It can overwrite any name that was inherited from any ancestor.
6. Actually, not these inherited/directly given definitions, but their final implementations are considered as members.
   When referenced definitions are determined by the above 5 steps, then their final implementations are taken and
   they are stored as actual members.

**All members are final implementations!**

A definition can override names from its ancestors. An ancestor listed later can override names from other ancestors
listed sooner. But the order of the members goes the other way: members of the first ancestor come first, then member
of the second ancestor etc. The only exception is when an ancestor (or the definition itself) overwrites a member with
the same name. In that case, the member's position will be changed too, not just its value.

The order of the members is also important because they reflect the order of the definitions (merged from different
ancestors) as they appear in the source code. Especially for tables generated from fieldset definitions, the order of
fields inside the table will be determined by the order of the members. Subclassing is (mostly) used for making general
things more specific, and it makes sense to list the more general fields (inherited from the fist ancestor) first,
and continue with more specific fields.

Containment (AKA "Dynamic containment")
---------------------------------------

After phase 3, we can also check for containment. Definition D contains definition C:

1. if C is a member of D
2. or if C is a member of a member of D (etc. recursively)

Note that this definition of containment is only possible if the definitions do not contain each other. For members
can be inherited, we must not allow definitions in the same inheritance graph to contain each other.

It is important to understand that dynamic containment is very different from static containment. Dynamic containment
is affected by ancestors, and ancestors can be anywhere in the source code (spread across different schemas). In
contrast, static containment means that a definition is inside the ``{}`` block of another definition. To emphasize
the difference, we always write out **static containment** when we mean it.

The ``YASDLItem.itercontained()`` generator can be used to iterate over all contained items. This is a post order
traversal: directly contained items are yielded first, the their contained items are yielded in the same order.

Dynamic binding
---------------

After phase 3, we can also bind dynamically. Dynamic binding means that we try to find an object for a dotted name as
described below:

1. The first name of the dotted name is taken
2. A member with that name is looked up. (But see notes below.) If no member can be found with that name, then the
   binding is unsuccessful (KeyError is raised).
3. If there is a remaining part of the dotted name, then dynamic binding continues on the member with that remaining
   part. Otherwise that member is bound to the name, given that it matches the minclass specification of the dotted
   name (if any).

The result of the binding is not just a single object, but a path to the object. This may be needed in some cases,
because a definition can contain another definition multiple times. Consider the following example:

.. code-block:: yasdl

  schema test  {
      language "en";
      abstract fieldset a {
          required field f1 {
              type "text";
          }
      }
      required fieldset b {
          fieldset a1 : a;
          fieldset a2 : a;
          index i_a1f1_a2f1 {
              fields a1.f1 a2.f1;
              unique true;
          }
      }
  }

In this example, the ``test.b`` fieldset contains the ``test.a.f1`` field two times. The index ``i_a1f1_a2f1`` is
defined on two different realizations of the same field definition! If you want to create a table from the
``test.b`` fieldset then then you must create two different database fields from the
``test.a.f1`` field definition. They cannot have the same name in the database table. It implies that when the
AST is used to generate objects (tables and fields etc.) in the database, then the names of those objects must
be a function of the definition paths, and not just the definition names. (Because the definition names are not
unique in this context.) For this purpose, not just ``bind()`` and ``bind_static()`` methods are provided
in the API, but also ``bindpath()`` and ``bindpath_static()``. They return paths of objects instead of simple objects.
In most cases, you do not need to care about the difference between them, because you will be iterating over fields
using the ``iter()`` or ``itercontained()`` generator methods, and they already return membership paths. Just if you
are curious why we are using paths instead of simple definition objects, well this is the reason.

Notes on member lookup by name
------------------------------

Consider this example:

.. code-block:: yasdl

    schema person {
        use types;

        author "Bob";

        # Simple table.
        fieldset person {
            field name : types.name { reqlevel "mandatory"; }
            index uidx_name {
                fields name;
                unique true;
            }
        }

    }

    schema crm {
        require person as per;

        author "Alice";

        fieldset myperson : per.person {
            implements per.person;
            field phone : types.name;
        }

        required fieldset person_location {
            field person -> per.person;
            fieldset location : location;
            field locationtype -> types.locationtype;
        }

        # More definitions here

    }

Here, the ``crm.person_location.person`` field has a reference to ``per.person``. However, the ``person as per``
schema does not have a member with that name. It is because ``per.person`` is implemented by ``crm.myperson``,
and because members are always final implementations. But ``per.person`` is not a final implementation, so it cannot
be a member! However, the above code still compiles. When we try to look up a member by its name, then not just
names of members are checked, but also names of statically contained definitions. (However, when found, their
final implementations will be used to continue the search.) In the above example, these would all work and do the
same thing:

.. code-block:: yasdl

    field person -> myperson;    # Bound directly to a member by its name
    field person -> per.person;  # Looked up by name of statical contained definition,
                                 # but bound to its final implementation
    field person -> per.myperson;# Looked up by name of its member.
                                 # The "person" schema does not statically
                                 # contain a "myperson" definition, but
                                 # it does have a member with that name.)

When using relative names, this might be ambiguous, and sometimes an object that is accessible in a mixed way (e.g.
static+dynamic name path) will take precedence over another object that would otherwise accessible with a pure dynamic
name. However, relative names are already ambiguous, and such conflicts are not a problem unless you have a very bad
naming and a bad schema design. Such ambiguities can always be eliminated by using absolute names.

The (maybe not so obvious) advantage of mixed binding is that other schemas does not need to know how the referenced
definitions has been modified by other schemas.  For example, let's add a third schema:

.. code-block:: yasdl

    schema invoicing {
        require person as per;

        author "Carol";

        require fieldset invoice {
            required field issuer -> per.person;
            # ....
        }
        # ...
    }

In this example, Bob has made the "person" schema, Alice made the "crm" schema, and Carol made the "invoicing" schema.
Alice is working on an extension of the "person" schema, and she re-implements (modifies) parts of it. She will not
be in conflict with Carol, until Carol also tries to re-implement person.person. Of course, if they both want to modify
the same implementation of persons, then they will have to discuss the changes. They have two options: if they are
at the same level in the company, then they can create their common derived schema that contains all changes that
they need, and work in collaboration:

.. code-block:: yasdl


    # Bob is the boss at the company, he defines standards for storing persons.
    schema person {
        use types;

        author "Bob";

        # Simple table.
        fieldset person {
            field name : types.name { reqlevel "mandatory"; }
            index uidx_name {
                fields name;
                unique true;
            }
        }

    }

    # Alice and Carol talked about this, and they will put their changes into a common schema
    # for their new projects. They are working together on this.
    schema invoice_and_crm_project {
        use types;
        require person as per;

        author "Alice, Carol";

        # Alice and Carol tells: this is required for both of them.
        # They may also agree in that this should be the final implementation.
        final required fieldset person : per.person {
            implements per.person;
            required field phone : types.name; # Alice tells: this is required for crm.
            required field taxno : types.text; # Carol tells: this is required for invoicing.
        }

    }

    # Alice is working on the crm parts that are independent of invoicing.
    schema crm {
        use types;
        require invoice_and_crm_project as base;

        author "Alice";

        required fieldset person_location {
            field person -> base.person;
            fieldset location : location;
            field locationtype -> types.locationtype;
        }

        # More definitions here

    }

    # Carol is working on the invoicing parts that are independent of crm.
    schema invoicing {
        use types;
        require invoice_and_crm_project as base;

        author "Carol";

        require fieldset invoice {
            required field issuer -> base.person;
            # ....
        }
        # ...
    }


If Alice is the boss of Carol, then she can say: look, my changes are more important than yours. I'm going to
change the person.person fieldset as I please. You can make further modifications, but only if they do not conflict
with mine. In this situation, Carol is required to use Alice's schema instead of their common schema:

.. code-block:: yasdl

    # Bob is the boss at the company, he defines standards for storing persons.
    schema person {
        use types;
        author "Bob";
        fieldset person {
            # ...
        }
        # ...
    }

    # Alice is working on the crm parts and se does not care, nor wants to know about invoicing.
    schema crm {
        use types;
        require person as per;

        author "Alice";


        required fieldset person : per.person {
            implements per.person;
            final required field phone : types.name; # Alice tells: this is required for crm, and most not be changed.
        }

        # More definitions here
    }


    # Carol is forced to accept Alice's changes
    schema invoicing {
        use types;
        require person as per;
        require crm;

        author "Carol";

        required fieldset person : crm.person {
            implements all;
            required field taxno : types.text; # Carol tells: this is required for invoicing.
        }

        require fieldset invoice {
            required field issuer -> person;
            # ....
        }
        # ...
    }


In this scenario, Carol cannot re-implement ``person.person``, because Alice already re-implemented it. Carol can
only re-implement ``crm.person``, but that already contains Alice's changes.

If Alice is a hard person and does not want Carol to make any changes to the implementation of person, then she
can specify the final modifier: ``final required fieldset person``. Then Carol won't be able to change that
implementation at all. However, she can still create a totally new implementation tree by doing this:


.. code-block:: yasdl

    schema invoicing {
        use types;
        require person as per;
        require crm;

        author "Carol";

        # Carol wants to use a structure that is very similar to the final implementation of crm.person.
        required fieldset person : =crm.person { # In this case, crm.person would be the same because crm.person is final.
            required field taxno : types.text; # Carol tells: this is required for invoicing.
        }

        require fieldset invoice {
            required field issuer -> person;
            # ....
        }
        # ...
    }

But this will form a new database table, and persons for invoicing will be independent from persons for crm.

Recursive dynamic binding
-------------------------

Recursive dynamic binding is also possible. It means that the search can traceback to the containing definition.
If the object cannot be found with the given relative name at the point of its occurence, then the search is
restarted from the point of its static container. In the above example, we have used ``field person -> per.person``
isinde the ``person_location`` fieldset. But ``per`` is not a member of ``person_location``. It is a member of its
parent. (If you are familiar with Zope, you will notice that this "recursive" search is analogous to Zope's aquisition.)

To prevent recursive binding, you can start the dotted name with the schema keyword, and use an absolute dotted name.
That will make sure that the search will start from the schema level. We could have used this absolute name to access
the same definition:

.. code-block:: yasdl

    field person -> schema.per.person;

Implementation notes
....................

* The ``venus.db.yasdl.ast.YASDLItem.bind()`` method implements dynamic binding (as opposed to
  ``venus.db.yasdl.ast.YASDLItem.bind_static()`` ).
* It also implements recursive binding (AKA "aquisition"). You just need to set the argument ``recursive=True``.
* Be aware that you have to pass a dotted name to these methods. The min_classes attribute (when given) will be used
  to narrow down the search.
* The ``YASDLItem.bind()`` method does not consider alias names. In order to bind with alias names support, you have to
  use ``YASDLParseResult.bind()``. It has an extra starting parameter that determines the starting point of the search,
  and it also knows the current schema and all of the alias names bound by use and require statements.

Phase 4 - binding all other names
=================================


1. All ``references`` properties are checked. They must have zero or one argument. The only argument (if present) must
   be a name bound to a fieldset definition. If you don't give min_classes, then the compiler will set it to [fieldset].
   It is not an error to specify min_classes for a dotted name after the references property (or the arrow operator),
   but then it must be [fieldset]. E.g. only fieldsets can be given after the references property. NOTE: by
   redefining the references property in a descendant with zero arguments, it is possible to clear the reference to the
   fieldset. This is the only reason why argumentlessness is allowed.
2. All remaining dotted names are bound dynamically. They are all the names after all property definitions, except for
   ``ancestors`` and ``implements``. They are given references to other definitions. Their min_classes are used to
   narrow down the search.
3. ``references`` are checked again. The single argument of a ``references`` property must either be ``any``, or a
   fieldset definition that has an outermost final implementation. Referencing a fieldset that is not outermost
   is an error. (Only outermost fieldset definitions should be realized final implementations.)
4. Index definitions are checked:

   * Must have a fields property
   * The fields property must have at least one argument.
   * All arguments of the fields property must be references to fields
   * Those field must be contained in the fieldset that contains the index definition. (Can only create index on fields
     that are inside the table the index is defined on.)
   * Cannot be field duplicates inside a single index definition.
5. Constraint definitions are checked:
    * Must have a check property
    * The check property must have at least one argument.
    * All arguments of the check property must be either normal strings, or fields that are contained in the
      fieldset that contains the constraint definition. (Can only check constraint on a field that is inside the
      table the constraint is defined on.)

You must keep in mind that there are three different kinds of name bindings:

* For the ``implements`` property, binding is always static.
* For the ``ancestors`` property, the binding is static, but imp_name constructs can be used to subclass the
  final implementations of the statically bound definitions.
* All other names are dynamically bound. They can access any member with relative and absolute dotted names. (But a
  dynamically bound dotted name can contain static elements, as described above in the "Notes on member lookup by name"
  section above.)

Phase 5 - finding out what should be realized
=============================================

This is done in several steps.

1. First the compiler determines which schemas are realized:
   a. All top schemas are marked as realized. (Top schemas are the ones passed directly to the compiler.)
   b. All schemas that were loaded with the require statement from schemas that are marked as realized, are also marked
     realized. This is applied repeatedly until no more new schemas are marked as realized.
2. At the end of this step, all schema definitions will have the "realized" attribute set (True or False). The meaning
   for this: these schemas should be **fully realized**. Other schemas will be used as needed: all, some or none of
   their inner definitions can be realized.
3. Then the compiler determines which fieldset and field implementations are realized and which are *top-level*. Please
   note that this algorithm selects final implementations only.

   a. If an outermost fieldset definition has the required modifier and is placed in a schema that is marked realized,
      then its final implementation is marked realized and top-level. In this step, it is also checked that the
      final implementation is outermost. Having a required outermost fieldset definition with a non-outermost
      final implementation is invalid, and results in an error.
   b. If a fieldset is marked as realized, then all of its contained members (fields and fieldsets) are marked as
      realized. However, they are not marked as top-level (at least not in this step).

      Implementation note: see ``YASDLItem.itercontained()``

   c. If a field is marked realized, and references another F fieldset with the references property (or the arrow
      operator), then the final implementation of the F fieldset is marked realized and top-level. (Please note that
      in phase 4 step 3, we already checked that referenced final fieldsets are outermost, so we don't need to check
      it here.) This step ignores all universal references. Universal references do not generate requirements,
      but they can only reference rows stored realized fieldsets.
   d. All steps above except the first one are applied repeatedly until no new definitions are marked as realized.

4. Finally, the compiler checks all realized definitions that are final implementations. None of them should have the
   abstract modifier given.

Please note that being a "top-level" and being an "outermost" definition are different. Outermost means that the
static container of the definition is a schema. Top-level means an outermost definition that will be directly used to
generate a table in a database. Not all outermost fieldsets are top-level or realized, and not all realized fieldsets
are outermost. But all top-level fieldsets are outermost and realized.

Output from this phase:
.......................

* a set of schemas that are fully realized
* a set of top-level fieldsets that are realized. They will be used directly for creating database tables.
* a set of non top-level fieldsets that are realized. They will be used directly for grouping fields inside database
  tables.
* a set of fields that are realized. They will be used directly for creating fields inside database tables.

Implementation note
...................

In the end of phase 5, top-level realized fieldsets are saved in the ``toplevel_fieldsets`` attribute of the parsed
schema set. Also the ``realized`` attribute is set to True or False for every fieldset and field.

Phase 6 - checking if required definitions are realized
=======================================================

In this step, we check all requirements.

* Implementation trees are enumerated.
* For every tree, the final implementation is examined.
* If it is realized, then the whole tree is checked, the following way:

  1. All definitions in the tree are examined.
  2. Their direct members are examined for the required modifier. Direct members are the ones that are defined on
     the same level, e.g. owned by the given definition. In other words, members of members are not examined here,
     but members inherited from ancestors and defined directly in the definition are examined.
  3. Such required direct members must be realized. If such a member is not realized, then it is a compile time error:
     a specification requested that member to be realized, but this requirement was not fulfilled. In most cases
     it won't be realized because it is hidden by another member with the same name. In some other cases, they won't
     be realized because an implementation used its name in a deletion.

Phase 7 - other checks
======================

    1. Realized top level fieldsets must contain at least one field. (Error)
    2. Realized non top-level fieldsets must contain at least one field. (If you do not need any contained fields
       then you need to ``delete`` the whole fieldset from its container.) (Error)
    3. Outermost field definitions should not have the required modifier. It would be meaningless. (Warning)
    4. Top level realized fieldset definitions should not have any specification that is not outermost. This may result
       in realizing multiple copies of fields. (Notice.) (Actual copying happens when a top-level fieldset contains the
       specification of another top-level fieldset.)
    5. Check "type" property of all fields:
        a. When given, the "type" property must have exactly one string argument, or no argument at all.
        b. If the field is referencing a concrete fieldset with the references property, then they "type" must be
           "identifier" or not specified at all. If the type is not specified directly, then "identifier" will
           be set as the default type.
        c. If the field is an universal reference that can reference to ``any`` fieldset, then it must not have
           a type. (The field definition will result in the generation of two database fields with "identifier"
           type.)
        d. All realized fields (except universal referencing fields) must have a type. E.g. they must have a value
           given to the ``type`` property explicitly, or be a referencing field to a concrete fieldset.
    6. Check "size" property for all fields. When given, the "size" property must have exactly one integer argument.
    7. Check "precision" property for all fields. When given, the "precision" property must have exactly one integer argument.
    8. Check "notnull" property for all definitions. When given, it must be inside a field definition, and it must have exactly one boolean argument.
    9. Check "unique" property for all definitions. When given, it must be inside an index definition, and it must have exactly one boolean argument.
    10. Check "immutable" property for all definitions. When given, it must be inside an index definition, and it must have exactly one boolean argument.
    11. Check "guid" property for all definitions.
        a. When given, it must have exactly one non-empty string argument.
        b. The given guid values must be unique in the compilation set.
    12. Check "ondelete" and "onupdate" property for all definitions.
        a. It can only be given inside a fieldset definition.
        b. It must have exactly one string argument from this list of values: "cascade" "setnull" "noaction"
        When given, it must be inside an index definition, and it must have exactly one boolean argument.
    13. The index definitions that are (first level) members of realized final implementations are checked. These are
        the indexes that will be used for database object generation. Their fields are examined. They must all be
        realized.
    14. Every schema should have a language property defined. Not giving this property will result in a warning message,
        and "en" will be assumed.
    15. The language property can only be defined at schema level.
    16. The cluster property can only be defined at fieldset level. It can only have zero or one argument. When an
        argument is given, then it must reference to an index definition that was defined at the same level (e.g.
        inside the same fieldset).
    17. The "reqlevel" property should only have these values: "optional", "desired", "required". (Results in
        compiler notice). If the level is "required", then the notnull property should be true. (Results in
        compiler notice)
    18. Must not have "notnull true" and "ondelete/onupdate setnull" combination. It would be impossible.
        TODO change default ondelete/onupdate rule for notnull fields to cascade.
    19. Check for required guid values:
        a. All schemas (realized or not) must have a guid property set. (Error)
        b. All self-realized toplevel fieldsets must have a guid property set. (Error)
    20. !!! TODO A realized field that references a fieldset and is not part of any index definition, generates a
        notice: possibly missing index on a foreign key, unless it has the "need_index false" property set. (Notice)
    21. !!! TODO check for reintroduction 1: a name that was deleted in an ancestor is reintroduced in a descendant. (Notice)
    22. !!! TODO check for reintroduction 2: a name that was deleted in a specification is reintroduced in an implementation. (Notice)
    23. !!! TODO realized fields must have a label property defined.


Phase 8 - database driver specific checks
=========================================

In this step, database driver specific checks are performed. This step can only be ran if a database driver was
specified for the compilation.

* Types of realized final implementation fields are checked. The database driver is used to determine if the given
  type is valid for the driver or not. Using an invalid/unknown type results in a compiler error.
* The driver is also used to check if the field needs a size or a precision. For example, the "varchar" type must have
  a size. Or the "decimal" type must have a precision given. Such errors are reported by the compiler.

You don't have to give the database driver type to compile a schema set, but it is advised. If you do not give the
database driver type, then these checks will be performed during database instance creation, and they may not be
fixed easily (e.g. because the database is half-ready, and no debug information is available for the YASDL source code).

Implementation note
...................

Available types are given in database adapter classes in the ``typemap`` attribute.

.. todo::
    We should define basic type names as they appear in Python: datetime, timedelta, complex etc. should all
    be the same in Python and in YASDL, and converted to native types by database adapter classes.


Debugging the parsed schema set
===============================

TODO! The compiler should have a --debug option. That option should allow the user to

* Request detailed compilation map to be written into a map file.
* Start an interactive shell, where the user can search for definitions, and inspect their properties. (Maybe a GUI???)

Using a compilation - the output of the compiler
What is inside
Standard properties
Like reqlevel and similars.
How to create a new instance from a compilation
How to load and access its components (with examples)
Python connectivity.

    Show how to load it from an instance. Introduce GUIDs.
    Show how to load it from a compilation.
    Show how to assign python module to schema. (with URI or with file path)
    Show some introdutionary aspect orientation aspects here ;-)
