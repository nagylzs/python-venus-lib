
Implementations of definitions
==============================

Please note that this section does not completely define the implements property. It introduces some terms, states some
rules about this property, and helps you to get the idea. If you are a language lawyer and want to get a more
formal and complete definition in mind, then read the YASDL compiler section.

Introduction
------------

YASDL is a declarative language. You express your requirements in formal definitions. For example, you are working on
a schema that will be used for invoicing. You need to store customers in your database, so you create a
"customer" fieldset
in your schema:


.. literalinclude:: /../demos/yasdl/doc_examples/reference/invoicing_01.yasdl
   :language: yasdl

In the above example, we have specified that the ``customer`` fieldset should have three fields:
``name``, ``address`` and ``taxno``. It does not mean that a concrete ``customer`` table will only have these
three field in a concrete database.
YASDL focuses on code reuse, and the end user can add/modify/remove definitions in a trivial way, without touching
the original schema. Your schema defines how to handle invoicing, but an end user may need additional things to
store for his customers. For example, Bob may create a different version of this fieldset - let's call it
``mycustomer`` - that also has a comment field:

.. literalinclude:: /../demos/yasdl/doc_examples/reference/invoicing_02_bob.yasdl
   :language: yasdl


His intention is to change the schema, so that in his *implementation* also has a comment field.

Let's say that Alice wants to do invoicing, but she also wants to create a database of contacts for her crm system.
What she thinks is that contacts are very similar to customers, except that they also have a phone number where
they can be reached. She wants to store them it two separate tables. She creates her own schema:

.. literalinclude:: /../demos/yasdl/doc_examples/reference/invoicing_and_crm_03_alice.yasdl
   :language: yasdl


Using inheritance, Alice could express her thoughts precisely: if the original ``invoicing.person`` fieldset is changed,
then Alice's ``contact`` fieldset will also inherit the changes.

There is an important difference between Bob's and Alice's intention: Bob wants to *replace* the original ``person``
fieldset. He wants to change the invoicing. Alice wants to *create a modified copy* of the customers, and use it
as contacts for cmr. She does not want to change the invoicing. They want to do different things, but
there is no difference in the syntax of the examples above. Something is missing.

Somehow we need to have a way to tell which definitions are **copies** that result in generation of **distinct** tables,
and which definitions are simple **modifications** of other definition(s) that will affect the generation of
**the same** table. For this purpose, the *implements property* can be used.

Syntax of the implements property
---------------------------------

The implements property is syntactically very similar to the ancestors property: you can give one or more definition
names after the implements keyword:

.. code-block:: yasdl

    fieldset myperson {
        implements basic.invoicing.person;
        # ...
    }

In many cases, schema developers will only want to add some fields to an existing table in the database.
The easiest way to do it is to create a descendant of the original fieldset that is also the implementation,
and do the modifications there. This scenario is so common, that the ``all`` keyword has been
introduced to tell that the new definition implements all of its ancestors. For example, this code:

.. code-block:: yasdl

    fieldset myperson : basic.invoicing.person calendar.person {
        implements all;
        # ...
    }

is equivalent to the following:

.. code-block:: yasdl

    fieldset myperson : basic.invoicing.person calendar.person {
        implements basic.invoicing.person calendar.person;
        # ...
    }


There is a strict rule: *imp_name* constructs cannot be given after the ``implements`` property. They can only be
given after ``ancestors``. This also means that using an imp_name ancestor and using ``implements all`` in the
same definition is invalid.

Meaning of the implements property
----------------------------------

The implements property tells what definition can be the implementation of what specification. E.g. the above example
tells that the newly defined ``myperson`` fieldset takes the role of the ``basic.invoicing.person`` fieldset.
In other words, ``myperson`` should be used for database object generation, instead of
``basic.invoicing.person``. If we do not have ``myperson`` listed after the implements property in any other
definition in the same compilation, the following statements are true:

* ``basic.invoicing.person`` won't be a final implementation (e.g. it won't be directly used for generating
  a database table)
* ``myperson`` will be a final implementation (instead of ``basic.invoicing.person``)
* Any field that is referencing ``basic.invoicing.person`` with the arrow operator will form a foreign key constraint to
  the ``myperson`` database table, generated from the ``myperson`` fieldset definition. Most likely, such
  references will be found in the ``basic.invoicing schema``.
* Any normal property argument that references ``basic.invoicing.person`` will be dynamically bound to
  ``myperson``. (By normal property we  mean anything but *implements* and *ancestors*).

Would ``myperson`` be listed after the implements property in another definition, the selection for final
implementation that other definition will be, transitively. More precise definition about implementations,
specifications and definitions will be provided later in this document.

.. note::

    If you are a programmer, then you have probably already used the term *implements* and *implementation*
    in conjunction with interfaces. The meaning of *implementation* is different in most languages. Java,
    Object Pascal and many other languages define *interfaces* that express requirements, and for one interface
    many *implementations* can coexist. Those languages usually the ones that do not allow multiple inheritance,
    but they provide a many-to-many relationship between interfaces and their implementations.

    YASDL allows multiple inheritance, so using interfaces is not needed. In YASDL, the meaning of *implementation*
    is a bit different. A definition can be the implementation of many others, but - given a set of schemas that
    are compiled together -  a specification cannot have more then one implementation. If we do not
    fix the set of schemas that are compiled together, then there can be many definitions (in different schemas)
    implementing the same specification. So the relation is many-to-many in general, but it is a one-to-many
    for any given successful compilation. The one-to-many relationship means that now matter how many modification
    we make to a definition, it must have a concrete implementation in a concrete database instance. The many-to-many
    relationship means that a specification can have multiple implementations in different database instances, as
    long as the implementations fulfill all the requirements given in the original specification.

The ``implements`` property is used to build the implementation tree of definitions, and in the end it helps the
compiler finding the final implementations. The ``implements`` property will be parsed and analyzed by the
YASDL compiler before final implementations are determined. It is somewhat obvious that you cannot use *imp_name*
constructs after the ``implements`` property, because the ``implements`` property must first be used to determine
the specification-implementation relationships between definitions, and only then can we reference to the
"final implementation of" a definition.

Implementation compatibility
----------------------------

Fieldsets cannot be implemented by fields and vice versa. This is required because some built-in functions can only be
used for certain definition types. It is determined by their semantics. For example, a fieldset can never be a reference
(foreign key constraint) to another fieldset, just because a fieldset it is unable to reference to anything (only
containing fields can).

Circular implements
-------------------

The implements property builds a graph between definitions. This graph must be a tree. A set of schemas that circularly
use the implements property are incorrect and will result in semantic check error. For example, the
schema below is invalid:

.. code-block:: yasdl

  schema s {
    field a { implements b; }
    field b { implements c; }
    field c { implements a; } # invalid, creates a circle
  }


Multiple implementations
------------------------

Before you can generate a database instance, you need to compile a set of schemas into an abstract syntax tree.
It is done by the YASDL compiler called ``yasdlc``. The files of the schemas that needs to be *fully realized*
are passed as arguments to the compiler. This set of schemas is called a compilation.

Within the same compilation, every definition can be listed after the ``implements`` property once at most.
This restriction means that multiple modifications of the same definition cannot coexist in the same compilation.

For example, the following schema is invalid:

.. code-block:: yasdl

  schema s {
    field a;
    field b { implements a; }
    field c { implements a; } # invalid, "a" can be listed once at most.
  }

The following schemas set is also invalid if ``s, b, c`` schemas are used in the same compilation:

.. code-block:: yasdl

  schema s {
    field a;
  }

  schema b {
    use s;
    field b { implements s.a;}
  }

  schema c {
    use s;
    field c { implements s.a;}
  }


But it would be fine to compile ``s + b`` for one database, and ``s + c`` for another database.

The definition standing at the root of an implementation tree is the *final implementation* of all
definitions in the tree.

When to use the implements property
...................................

The ``implements`` property modifies definitions from the outside. You may think that this works against encapsulation.
When used incorrectly, it can very well make your schemas (and also your program code) an impenetrable mess.
The ``implements`` property was
invented so that a general idea can be expressed in a base schema in the most general form, and further modifications
(specializations) can be requested in multiple different derived schemas. First of all, this is useful if the basic
idea was formulated by somebody else, because you can move your modifications to a new schema, and separate your
changes and ideas from his changes.
It is also useful when you have a general idea and several specializations. The basic idea can be described with an
abstract data structure (base YASDL schema) and an abstract program code (program module attached to the base schema).
They can be packed together and handled as an entity. Generalizations and specializations can be both described with
derived schemas and their corresponding program codes. Their relationships can be expressed with OO tools not just
in the program code, but also in the database structure. In this case the implements property can increase
the encapsulation of data structure and program code, and it can separate these entities into layers.
As far as we know, this is something innovative.

Whenever the basic idea is improved, it is enough to modify the base schema. All derived schemas will automatically
enjoy the benefits of the improvements. Whenever the derived schema is modified, you do not need to touch the
base schema - this makes your change a local change and it has obvious advantages.

But be warned: if you cannot clearly separate layers in your database structure, then you probably do not
need to use the implements property to modify definitions from the outside, or at least you should think twice
before doing it. Misusing or over-using the implements property can result in code that is hard to understand.


How to use the implements property
----------------------------------

As it was already mentioned above, in most cases, schema developers will want to add some fields to a fieldset
definition, or change some things, but leave the rest of the definition intact. In this case, they can use a
combination of ancestors and implements all. Below is a common pattern:

.. code-block:: yasdl

    fieldset myperson : basic.invoicing.person calendar.person; {
        implements all; # Use myperson to connect invoicing and calendar schemas
                        # through a person.
        field extra_description : text;
    }


This will instruct the compiler to create the table for ``myperson``. This table will be used for implementing
the ``person`` fieldset defined in ``basic.invoicing``. It will also be used to impement the
``calendar.person fieldset``. The ``basic.invoicing`` and ``calendar`` schemas can be designed to solve
two different tasks (invoicing and calendar) without knowing anything about each other. However, in this
particular compilation, they will share the same database table for storing persons.

It is perfectly legal to combine ``all`` with other names:

.. code-block:: yasdl

    fieldset myperson : basic.invoicing.person calendar.person {
        implements all anotherschema.anotherperson;
        # ...
    }


It is also possible to re-implement a definition from scratch, instead of changing it by inheritance, as shown below:

.. code-block:: yasdl

    fieldset myperson {
        implements anotherschema.anotherperson;

        field field1; # ...
        field field2; # ...
        # ...
    }


You can have some ancestors and use them for the reimplementation of a totally different definition. For example,
the definition below tells that the final implementation of ``anotherschema.anotherperson`` should be very
similar to ``basic.invoicing.person``, but have an extra comments field:

.. code-block:: yasdl

    fieldset myperson : basic.invoicing.person {
        implements anotherschema.anotherperson;
        field comments : memo;
    }

In this example, ``myperson`` and ``basic.invoicing.person`` will be realized in different tables, but
``anotherschema.anotherperson`` will share the same database table with ``anotherschema.anotherperson``.

It is possible to make a "copy" of a definition, e.g. have both the original definition and its descendant
to be part of a separate implementation tree. The following example would probably result in creating two separate
database tables, with exactly the same fields:

.. code-block:: yasdl

    fieldset customer {
        field name  { type "text"; }
        field address : { type "text"; }
    }
    fieldset shipper : customer;

Implementing and re-implementing field definitions is also possible. Below you can find an ugly, parasitic approach.

.. code-block:: yasdl

    schema invoicing {
        fieldset customer {
            field name :  { type "char"; size: 100; }
            field address : { type "text"; }
        }
        fieldset product {
            field name : { type "char"; size: 100; }
            field partno : { type "text"; }
            # ...
        }
        # ...
    }

    # The app schema should have varchar type for name fields, instead of char.
    schema app {
        require invoicing;
        field myname {
            implements invoicing.customer.name invoicing.product.name;
            type "varchar";
        }
    }

It is parasitic because we are implementing something in a schema that is defined in the inner level of another schema.
In order to do this, you need to know what is inside another schema. Which is wrong, because if something changes inside
the invoicing schema, then your app schema becomes invalid. Or even worse, starts working in unexpected ways, and then
you will have a hard time figuring out what is wrong. Of course, you could examine all the changes made to the
invoicing schema by hand, and refactor your code in order to make it correct. But that is very far from efficient,
and it is against Demeter's law: only talk to your friends! ( http://en.wikipedia.org/wiki/Law_of_Demeter )

What to do then? You could create something like this:

.. code-block:: yasdl

    schema invoicing {
        field name { type "char"; size 100; }
        fieldset customer {
            field name : schema.name; # Same as invoicing.name, just better ;-)
            field address : { type "text"; }
        }
        fieldset product {
            field name : schema.name; # Same as invoicing.name, just better ;-)
            field partno : { type "text"; }
            # ...
        }
        # ...
    }

    schema app {
        require invoicing;
        field myname : invoicing.name {
            implements all; # override name fields in invoicing...
            type "varchar";    # ...to have a different type
        }
    }


But it won't work. It is true that ``invoicing.name`` will be implemented by ``app.myname``. But the problem is that
``invocing.customer.name`` will not be implemented by ``invoicing.name``. They belong to two different implementation
trees (although they belong to the same inheritance graph). How to overcome this problem? YASDL provides you a way
to define stubs. By using an *imp_name* construct, you can express that a given definition is only a stub,
that needs (or can) be replaced by an external definition:

.. code-block:: yasdl

    schema invoicing {
        use types;
        # This is a stub, its modifications will affect invoicing.
        abstract field name { type "char"; size 100; }


        fieldset customer {
            field name : =name { # ancestor is the final implementation of the stub
                reqlevel "mandatory";
            }
            field address : types.address;
        }
        fieldset product {
            field name : =name; # ancestor is the final implementation of the stub
            field partno : types.text;
            # ...
        }
        # ...
    }

    schema app {
        require invoicing;
        final field myname : invoicing.name {
            implements all; # this will implement the stub
            type "varchar";    # ...and change its type
        }
    }


.. note::
    The above pattern is commonly used when the ``invoicing`` schema was created by a distributor of an application,
    and the end user wants to create his own version of it with small modifications. The good reason for putting
    modifications into a separate schema is that the original distributor will be allowed to make updates to
    the distribution, and send it to all end users.

In this example, for field ``invoicing.customer.name`` the following conditions are true:

* It is still not implemented by ``app.myname`` - it belongs to a different implementation tree.
* Its direct ancestor is "the final implementation of ``invoicing.name``" which happens to be ``app.myname``
* Has ``type "varchar"`` inherited from ``app.myname``
* Has ``size 100`` inherited from ``invoicing.name``
* Has ``reqlevel "mandatory"`` (specified directly)

Notice the following achievements - they will save you a lot of time by optimally re-using code as much as possible:

* The ``app`` schema does not need to know how ``invoicing.name`` is referenced inside the ``invoicing`` schema,
  how it is used, how many times etc. All it needs to know is that ``invoicing.name`` is a stub that has been
  extracted to the top level. It means that you can make changes to the implementation of the ``invoicing`` schema,
  without actually  knowing too much about it.
* The ``app`` schema can safely add/modify the behaviour of the entire ``invoicing`` schema under certain
  circumstances, without touching its source code.
* Those circumstances should be obvious (e.g. do not change the type of a "name" field to boolean) or should be
  documented by the author of the schema. (Of course if a schema author creates stubs in his/her schema, then she
  will put them on the top, and document how it can be changed for what reasons, without corrupting her solution.)

Please note that this is the only correct way to do it. E.g. the designer of the schema should decide what definitions
can be changed by other users:

* For definitions that **must** be changed, create a stub and specify the ``abstract`` modifier. Inside the schema,
  reference it with an *imp_name*.
* For definitions that **can** be changed, create a stub, with the ``fallback`` modifier, or without any modifiers.
  Inside the schema, reference it with an *imp_name*.
* For definitions that **must not** be changed, create a stub with the ``final`` modifier. Inside the schema, reference
  it with either an *imp_name* or a normal dotted name.
* If you want others to be able to change your definition in the parasitic way only, use the "brainless" solution:
  do not create a stub.

.. note::
    Modifiers are described later in this document.


Implements property and inheritance
-----------------------------------

**The implements property is NOT inherited by descendants.** Reasons for this are obvious.

Other notes on the implements property
--------------------------------------

Unlike with ancestors, the order of the names given after implements is not significant. Following things do the same:

.. code-block:: yasdl

    field d : a {
        implements a,b;
    }
    field d : a{
        implements b,a;
    }
    field d : a {
        implements b,a,b;
    }
    field d : a {
        implements all,b;
    }
    field d : a {
        implements all,a,b;
    }


Advanced usage
--------------

You cannot change a definition that has an imp_name ancestor but you change a copy of it. Please see the example below.

.. literalinclude:: /../demos/yasdl/doc_examples/reference/abstr_implementation.yasdl
   :language: yasdl

And here is how an end user can use this.

.. literalinclude:: /../demos/yasdl/doc_examples/reference/concrete_implementation.yasdl
   :language: yasdl


With the pattern above, there is a two way communication between the involved schemas:

* ``concrete_implementation`` defines a fieldset (called ``something_to_be_changed``)
* ``concrete_implementation`` gives this to ``abstr_implementation`` for further modification
* ``abstr_implementation`` modifies it, and saves it as ``changed_thing``
* Both of them can use the changed thing that the created together.

This has much higher level of abstraction (compared to what you could do with SQL), but it is meaningful in a
few special cases only. So you should use the above pattern very carefully.

.. note::
    The *imp_name* construct means the final implementation of the referenced definition.
    Binding the names after the implements property (e.g. the process of building the implementation tree) must happen
    before building the inheritance graph. Formally, YASDL does not allow you to put *imp_name* constructs after the
    implements property. Only normal names are allowed there, and they are bound statically.
