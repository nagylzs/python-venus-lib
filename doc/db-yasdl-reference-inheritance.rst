
Inheritance in YASDL
====================

Inheritance operator, type definition
-------------------------------------

Syntax::

    typedef ::= "" | colon_expr
    colon = ":"
    ancestor ::= imp_name
    colon_expr ::= colon ancestor+

Inheritance operator is the colon ``:``. On the left side, there is the descendant. On the right side, you can list one
or more ancestors, separated by whitespace. If you do not have any ancestor to list, you must not use the colon
operator. Instead of that, use an empty typedef. That is, nothing.

Examples:

.. code-block:: yasdl

    field firstname : name;                   # One ancestor.
    fieldset person : nameditem locateditem;  # Two ancestors.
    fieldset person;                          # No ancestors, empty typedef
    fieldset person {
        field firstname : =tname;             # Ancestor of firstname is the
    }                                         # final implementation of tname

What inheritance means
----------------------

By inheritance, the descendants will inherit all the containing definitions and properties of their ancestors.
When there are more definitions with the same name in
different ancestors, then the definition of the first listed ancestor is inherited. The others are hidden.

.. note::
    A precise algorithmic definition of inheritance is given in the "YASDL compiler" section.

It is important to understand, that names after the colon operator are bound to definitions. When talking
about inheritance, an ancestor means a YASDL definition. We **do not** mean the database object that will be generated
for the named definition.


The ancestors property
----------------------

It must be noted that the colon operator is syntactic sugar. The same thing can be achieved by using the ancestors
property:

.. code-block:: yasdl

    field firstname {
        ancestors name;
        size 100;
    }
    fieldset person {
        ancestors nameditem locateditem;
    }

The colon operator was introduced to emphasize the importance of inheritance. Specifying ancestors with both the colon
operator and the ancestors property is an error.

Ancestors can be specified for fieldsets and fields as well. Ancestors for fieldsets must be fieldsets, and ancestors
for fields must be fields.

It is somewhat evident that if definition ``D1`` has a descendant ``D2``, then ``D2`` must have
listed ``D1`` in its ancestors list, and that listing overwrites the value of the ancestors property.
If you do not specify any ancestor then the ancestors property will implicitly created: it will be set
to an empty list. Conclusion: the value of the ancestors property is never inherited by descendants.


**The ancestors is a special property that cannot be inherited**.

Circular ancestors
------------------

Specifying circular inheritance is invalid. For example, the following schema is invalid:

.. code-block:: yasdl

    schema s {
        field a : b;
        field b: c;
        field c: a; # Creates a circle, invalid!
    }
