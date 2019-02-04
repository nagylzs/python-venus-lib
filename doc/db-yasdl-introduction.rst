
Introduction
============

YASDL is a formal language. It can be used to describe database definitions including tablespaces, tables, fields,
foreign key constraints, indexes etc.

Many existing database schema designer systems are suffering from their lack of reusability. YASDL focuses on
reusability and integration. YASDL allows the developer to define subschemas, and use some kind of inheritance
between schemas and contained definitions.


Features
--------

* OO design with higher level of abstraction
* Semantically rich definition language (compared to pure SQL DDL)
* Easy integration with application frameworks
* Dynamically extensible
* Batteries included - it comes with a schema package that is ready to use for many applications.

Basic elements of the language
------------------------------

Definitions: schemas, fields, fieldsets and indexes
...................................................

There are four main kind of definitions in yasdl: schema, fieldset, field and index.
The schema is at the highest level: a schema defines how a database (or a bigger
part of it) should be created. A fieldset defines a set of fields, and many fieldsets are directly used to create
tables in databases. Fieldset can also be embedded inside other fieldsets. This is a way of grouping fields.
Relational databases systems can only hold atomic values in fields, but you can use embedded fieldsets for
grouping them. A field definition defines how a field (or a class of fields) should be created in a
database, and - of course - an index definition defines how an index should be created for a table (or for
a class of tables).

Properties
..........

Properties are similar to class level properties found in other OO languages. They are not considered definitions,
but they are contained in all other definitions. Example: the long description of a fieldset can be set by a property.
The purpose of properties is to provide information about the database at the highest level of abstraction.
Properties and their values can be accessed not just from the YASDL document, but also from all
other levels: from the compiled schema set, from the database instance and also from the program that accesses the
database. By introducing metadata at the YASDL level, you can make sure that they are available at all levels of
the system, and you also get support for their manipulation with OO tools.

Some properties have special meaning in YASDL and you cannot change that. Some properties are used by the data
access layer: software layer that accesses database instances created from YASDL documents. There are properties that
are used by GUI tool kits that display or modify data through the data access layer.
**Properties are tools of extension.** You can freely create or modify properties inside definitions, and use them
from other layers. For example, you can add your own program code that accesses the database through the data access
layer, or you can write your own GUI widgets that will access your custom properties through the GUI toolkit.


Naming
------

All definitions and properties have a name. Names are used to identify them. This section shows how names are used
to reference definitions and properties. Please see the example YASDL document below. Don't worry, you do not need
to understand every detail of the document.

.. literalinclude:: /../demos/yasdl/doc_examples/introduction/naming_test.yasdl
   :language: yasdl

As you can see, a YASDL document statically contains an outermost schema definition, and other definitions which
may contain other definitions etc. Definitions are always prefixed with a keyword (``schema``, ``fieldset``,
``field``and ``index``) and they have a simple *name*. The contents of a definition are enclosed in braces.
Properties can be freely created just by giving them a *name*.

There are places where one definition references another. This is mostly done after the ``:`` colon or ``->`` arrow
operators. You can also use references in property values and after some special keywords.

You cannot have two definitions with the same name inside the same `{}` block. However, definition names are not
unique - you can see in the above example that there is a field called ``name`` inside the ``country`` fieldset, and also
inside the ``person`` fieldset. When referencing other definitions, we want to be unambiguous. So we are going to use
the so called *dotted name notation*. In the above example, ``naming_test`` is the schema,
``naming_test.country.name`` is the ``name`` field inside the ``country`` fieldset that lives in the ``naming_test``
schema. In the ``car`` fieldset you can see that you do not need to give the full path in all cases - you can use
relative names. E.g. ``-> carowner`` instead of ``-> naming_test.carowner``. Static binding of names to definitions will
happen at compile time, and the search for the definition will start inside the given definition where the name is
located, traversing up in containing definitions. There is also dynamic binding is YASDL, you can read about that later.

Well it was just an example to demonstrate object naming. More precise documentation follows.

Foreign key constraints
-----------------------

Foreign key constraints are defined with the arrow operator ``->`` or with the references property. (They are
equivalent.) In the above example, this line:

.. code-block:: yasdl

    field country -> naming_test.country

Specified that the ``country`` field in the ``person`` fieldset should generate a foreign key field to the
database table that is generated from the ``country`` fieldset. In SQL, it will be similar to:

 .. code-block:: sql

    CREATE TABLE "naming_test"."country" (
      "id"                            bigint NOT NULL,
      "name"                          varchar(100)                  ,  -- name
      CONSTRAINT "pk$country" PRIMARY KEY ("id")

    );
    CREATE TABLE "naming_test"."carowner" (
      "id"                            bigint NOT NULL,
      "name"                          varchar(100)                  ,  -- name
      "country"                       bigint                        ,  -- country -> naming_test.country
      "birthdate"                     date                          ,  -- birthdate
      CONSTRAINT "pk$carowner" PRIMARY KEY ("id")

    );
    ALTER TABLE "naming_test"."car" ADD CONSTRAINT "fk$owner$carowner"
      FOREIGN KEY ("owner") REFERENCES "naming_test"."carowner"("id");
    ALTER TABLE "naming_test"."carowner" ADD CONSTRAINT "fk$country$country"
      FOREIGN KEY ("country") REFERENCES "naming_test"."country"("id");


Reserved properties can be used to change the details of these foreign key constraints: on delete action, deferrablity
etc.

Self containment
----------------

Every YASDL database instance has some special tables that store metadata information about the database instance.
These tables reside under the ``venus.*`` schemas. As long as the database gets created and modified by venus/YASDL
tools, the database structure is described is stored in the database. It includes source code for the schemas used,
and all definitions and properties used to generate the schema. In other words: the database defines itself in
YASDL, and the venus library can connect to any database and discover its structure.

Built-in schemas
----------------

The built in schemas contain many other realized and not realized fieldset definitions that can be used as building
blocks for new schemas.

OO Concepts
-----------

The most popular, and probably the best tool so far to achieve reusability is object orientation. YASDL is a language
that uses an OO model to describe the structure and behaviour of a database. Database instances created from YASDL
documents are plain relational databases. They just contain much more metadata and have better documentation.

We will assume that you are familiar with object oriented programming. If not, there are many good books about OOP.
We are just going to draw paralel between OOP and YASDL terms.



Inheritance
...........

In OOP, a class can have ancestors and descendants. YASDL definitions can also have ancestors and descendants, and
you can rename/add/remove members and properties in descendants. YASDL uses multiple inheritance. In our example above,
the ``carowner`` fieldset was inherited from the ``person`` fieldset.

Object construction
...................

An *instance of a YASDL document* is a database definition that was generated from the document.  Each table has a
corresponding fieldset definition in the document, and each field has a corresponding field definition in the document
etc. Roughly speaking, a definition that is directly used for database object generation is called an *implementation*.

.. note::

    The above explanation for *implementation is for introduction only. The precise definitions of
    *implementation* and *realization* are given in the reference section.

    The action of the construction happens when you run your compiled schema set using the ``yasdlr`` tool.
    There is no visible "constructor call" in YASDL documents, because the YASDL document only describes
    a class of instances, and not the instances.

Polymorphism
............

When combining several YASDL schemas into one YASDL instance, references can mean different database objects, depending
on which definition references to what name in what context.

Other concepts
..............

Other concepts like *abstract class* or *standard template library* also exists. You can read about them in
this document.

The abstraction level of YASDL
..............................

There have been attempts in the past to make relational databases "object relational". There already exist object
relational mappers (so called ORMs) that map tables to classes and rows to objects. The level of abstraction in
YASDL is not at the same level. In YASDL, tables, fields and indexes are instances and their classes are formal
definitions in one or more YASDL documents. YASDL classes are "above" the database instance: they are formal definitions
that cannot be represented in a single database instance.

Theoretical OOP example
-----------------------

To demonstrate the power of YASDL and introduce some terms, we are going to present an example use case. New terms wil
be *showing up in italic*.

In our example, Bob defines a *schema* that can handle invoicing. This schema can be defined with a single textual file.
The schema contains detailed definitions for
storing invoice data. Bob also provides a program module that is able to handle invoicing. This program module uses
the compiled version of the invoicing schema document as an interface to the database, and accesses conforming
databases through that interface. There is an application framework called YAAF that already knows how to handle
YASDL database instances, so Bob only needs to
write code that is specific to invoicing. Bob is concentrating on the invoicing part, and he creates a
solution that handles invoicing perfectly. He does not want to be too specific about the parts that are not strictly
related to invoicing. His schema also contains basic definitions for storing customers, shipping
locations etc. but these are only  *fallback definitions*. For example, a table is needed for
storing customers of invoices, but the provided "customer" *fieldset definition* only contains the fields that are
*required* to do invoicing. The end user is encouraged to *use* Bob's schema as a basic solution, and override some
definitions: add things that are needed to a specific application. The end user is able to do this without
touching Bob's source code for the original invoicing schema or his program code.

Suppose that we have another developer - Alice - who already has her schema with customer information. Let's say this
is an existing customer relationship management (AKA "CRM") system with time tables, collision handling, project
management etc. This schema is capable of storing detailed customer information but it doesn't have support for
invoicing.

Carol would like to have a complex system that knows how to do CMR and invoicing. She can create a third
schema, and combine Alice's and Bob's documents with just a few lines of code. Instead of copying and merging
their schemas (YASDL files) by hand, she can use OO tools to tell that she wants to *use* Alice's and Bob's schema, and
that the customers table should be *re-implemented* (merged and modified) from them. The program code created by Alice
accesses the database instance through the interface of Alice's original schema, and it does not need to be
refactored - it will work umodified with Carol's database instance, even if it has different field names or somewhat
modified structure.

Specification and implementation in more detail
-----------------------------------------------

For each table in the database instance, there is always a concrete definition that was directly used to create the
table. That definition is selected by a clever algorithm. (This algorithm is ran by a program called the
*YASDL compiler*.) The selected definition is called *the final implementation*. There can be other definitions (in our
example: "person" in the "invoicing" schema) that are *specifications* - they can specify or enforce requirements.
Specifications play an important role in the database instance generation.

.. note::

    Specification/implementation is only meaningful when we are talking about an instance that was created
    from a set of schemas, using the YASDL compiler. Given a single YASDL schema, usually you cannot tell which
    definitions will be final implementations, because this is subject to polymorphism. A definition in a given
    schema can be a final implementation in one configuration, and it can be a not-even-used specification in
    another configuration.

