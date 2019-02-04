
============================
Source files and basic types
============================

Source files
============

YASDL documents are textual. They can be stored in plain text files, or published using an URL.
In order to avoid encoding problems, source files (and other resources) **must be encoded in UTF-8**.

Internationalization support is built into the language. The default language of a schema should always be given,
using the language property and a two letter ISO compilant country code. If you do not give the language property,
then "en" language is assumed and a compiler warning is issued.

.. code-block:: yasdl

    schema some_schema {
        language "hu";
        # ...more definitions here
    }

The name of the file should always match the name of the schema, and have .yasdl extension.

Case sensitivity
================

YASDL is case insensitive. Case of characters in names are preserved. It was designed this way
because most relational database systems work exactly the same way.

.. note::
    Implementation note: names and dotted names are converted to lowercase internally. Comparison is made
    case sensitively between these converted values. On some systems, this conversion may depend on the current locale.
    We recommend that you always use lowercase names. This recommendation is for names and dotted names only, not for
    string literals.


Reserved words
==============

As in all languages, YASDL defines some reserved words. They have their unchangeable meaning and you cannot use them
for anything else. (Some of them are reserved for future use.)::

    none true false all any
    schema fieldset field index fields
    modifiers abstract final fallback required
    use require as
    rename delete

Tokens
======

Booleans
--------

Syntax::

    BOOLEAN ::= "true" | "false"

The two reserved words true and false can be used as boolean values for properties.

Strings
-------

String literals are always quoted. Strings can be represented with single quotes, double quotes, triple single and
triple double quotes. You can place newline characters inside triple quoted strings. You can escape special
characters with backslashes.

Examples::

    'With quote'
    "Double quoted string"
    '''Triple quoted is "possible"'''
    """Double triple 'quoted' also"""
    """Triple and triple double quoted strings
    can contain newlines, carriage returns, tabs etc."""
    "Double and single quoted strings can use \"backspace\" for escaping."


.. note::
    For double and single quoted strings, Python's builtin eval() function is used to
    decode escape sequences in string literals.

Integers and floats
-------------------

Syntax::

    unary_plus   ::= "+"
    unary_minus   ::= "-"
    digit   ::= "0"|"1"|"2"|"3"|"4"|"5"|"6"|"7"|"8"|"9"
    integer ::= [unary_minus|unary_plus] digit+
    float_exponent ::= ("E"|"e") [unary_minus|unary_plus] digit+
    float   ::= float_with_exponent | float_without_exponent
    float_without_exponent ::= (digit* "." digit+)|(digit+ ".")
    float_with_exponent ::= [unary_minus|unary_plus] ((digit+ "." digit*)|(digit* "." digit+)) float_exponent

Integers always start with a minus sign or a digit, they never contain a dot "." character and they are always followed
by a non-dot character. Floats always contain a dot "." character followed by a digit. They can contain an exponent part.

None
----

Syntax::

    none    ::= "none"

None is a special type and its value is represented with the reserved word "none". Its meaning is the absence of any
value.

.. note::
    Missing an object, and having an object with ``none`` value is not the same. For example, a property that has
    no value given and a property that has ``none`` value are differentiated.

All
---

Syntax::

    all    ::= "all"

*All* is a special type and its value is represented with the reserved word "all". It can be used instead of a list of
references to all possible definitions.


Comments
--------

Example::

    # This is a comment.

Any line starting with the hashmark "#" character that is not part of a string is a comment. Comments are not tokens,
they are ignored by the lexer.

Names - name, dotted name, imp_name, package name and absolute name
-------------------------------------------------------------------

As it was shown in the introduction, names are used to identify definitions and properties. Names are
also used to reference definitions and properties from other definitions. There are different kinds of names.

Formally::

    name ::= [A-Za-z_][A-Za-z0-9_]*
    package_name ::= name ["." name]*
    min_classes ::= "[" minclass+ "]"
    minclass ::= "schema" | "fieldset" | "field" | "index" | "property"
    dotted_name ::= ["schema" "." ] name ["." name]* [min_classes]
    imp_name ::= ["="] dotted_name
    alias_name ::= [A-Za-z_][A-Za-z0-9_]*

Examples::

    a_name
    a.dotted.name
    =a.dotted.imp.name
    name.with.min_classes[field fieldset]
    =a.dotted.imp.name.with.min_classes[schema property]
    schema.an.absolute_name
    =schema.an.absolute_imp_name

**Definition names are not quoted in any way.** Definition names always start with an ASCII letter or an underscore.
You cannot use reserved words as definition names. Even though an alias name of a use or require statement is not
strictly a definition name, it is used like a definition name so the same rules apply. (Use and require statements are
described later in this document.)

A dotted name contains one ore more names, connected with dot characters.

Naming schemas inside packages
..............................

Multiple schemas can be packaged into packages. Inside those packages, every schema must specify its exact absolute
location inside its package. For example, if your package has a "security" schema inside the "yasdl" directory, then
that schema must look like this:

.. code-block:: yasdl

    schema yasdl.security {
        # ... more definitions and properties here
    }

Whenever you ``use`` or ``require`` such a schema, you must import it with its full package path, and the name of the
schema must match its relative path. (Relative to the root of the package.) However, you can use the "as" keyword to
create an alias for it. For example:

.. code-block:: yasdl

    schema another_schema {
        use yasdl.security;  # Use the full name directly.
        use myschema.properties.propertybag as pb; # Use it with an alias.
        # Usage examples
        fieldset my_user : yasdl.security.user;
        fieldset my_bag : pb.bag;
    }

Absolute dotted names
.....................

Using the schema keyword followed by a dot can be the starting part of a dotted name. This construct is called an
absolute dotted name and it means that search for referenced definition starts from the schema that (statically)
contains the given absolute dotted name. This can be used to create totally unambiguous references. Absolute
references to other schemas. Alias names of used/required schemas are placed in the namespace of the schema that
uses/requires, so you can use absolute names to reference external schemas, as shown below:

.. code-block:: yasdl

    schema test {
        use person as per;
        use "http://www.yasdlschemas.org/schemas/isbn.yasdl" as isbn;
        fieldset book {
            field isbn : schema.isbn.isbn;     # Absolute reference to an external definition.
            field owner -> schema.per.person;  # Absolute reference to an external definition.
        }
        fieldset author {
            field book -> schema.book;         # Absolute reference within *this* schema
            # ...
        }
    }


Imp names
.........

You can prefix a dotted name with an equal sign. This construct is called an `imp_name`. This modified dotted name means
the final implementation of the named definition.

**This form can only be used for giving ancestors.**

Example:

.. code-block:: yasdl

    use types;
    field name {type types.varchar; size 100; }
    fieldset person {
        field firstname : =name { # Ask "firstname" to be inherited
                                  # from the final implementation of "name"
            reqlevel "mandatory";
        }
    }
    final field goodname {
        implements name; # This may be the final implementation of "name"
        type types.text;
    }

The person.firstname field will have ``type text`` (inherited from ``goodname``, which is the
final implementation of ``name``) and it will also have ``reqlevel "mandatory"`` (specified directly).

Restrict bindings of names to certain classes
.............................................

You can also specify so called *min_classes* with square brackets. They control what kind of object can a dotted name be
referring to. Using an empty set of classes is invalid - to match any class, you need to omit min_classes. Consider
the following example:

.. code-block:: yasdl

    schema a {
        fieldset test; # It has name 'test', and class 'fieldset'.
        fieldset inner {
            field test; # It has name 'test', and class 'field'.
            someproperty test[fieldset]; # The value of this property will be a
                                         # reference to a.test, because we asked
                                         # to find a reference to a fieldset,
                                         # and not a field.
        }
    }


Special names
.............

The following names are special. They are not keywords, but they have special meanings that cannot be changed::

    notnull immutable reqlevel guid
    ancestors implements
    references ondelete onupdate deferrable
    all
    type size precision
    fields unique
    language
    venus

The name ``venus`` is the name of the built in schema that comes with the
venus library. The directory of the built in schemas is always prepended to the search path of the compiler, and the
compiler implicitly ``require`` these built in schemas for any compilation. It means that you cannot use the name
``venus`` for anything but to access the built in schemas. Otherwise the name ``venus`` is not special, but it was
listed here because its meaning is fixed by the environment.

.. note::

    You will notice that most of the special names are property names. Almost all property names are simple names
    that can be freely defined anywhere in the source code. In other words: property names are regular names,
    not keywords. By making them keywords, the language syntax would be more difficult (because then keywords could
    also be used for identifying properties, and because

    ). So the above names have a special meaning, but they are not keywords
    for a good reason.

.. todo::

    Categorize the above list: reserved property names that affect the compiler, reserved properties that
    affect database generation, and other names.

.. todo::

    Describe new special names! language notnull immutable label longlabel cluster ondelete onupdate deferrable
    What to do with the "all" keyword? What is that anyway??? It is not a keyword. When used, they should be
    property names, and their meaning is defined by the compiler or other database generation tools.


