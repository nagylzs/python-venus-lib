================
Built-in schemas
================

There is a built in schema package that belongs to the venus package itself. This schema contains definitions
that are vial to the venus database access layer. They are translated into tables that store metadata information
in the database instance. The *venus schema package* is divided into several sub-schemas.

The official source code of this built in schema is located under the ``schemas/venus`` directory of your venus
library installation. The ``schemas`` directory is always prepended to your search path. The built in schemas
are always available to the compiler even if you do not configure your search path. (See the YASDL compiler section
for details.) In fact the venus packages are implicitly ``required`` for all compilation sets, and their location
is always prepended to your search path. It also means that you cannot accidentally overwrite the ``venus`` namespace
in your application, because the built in version takes precedence. If you want to create a customized version of your
venus library, then you can place additional sub-schemas under the ``schemas`` directory of your venus library
installation, and they will also be accessible for the compiler.

The compiler determines the location of this directory relative to the python library loaded from the compiler. If
you use multiple versions of the library, then you can also have multiple versions of the built in packages
and they will be selected by the compiler automatically.

venus.core
----------

The ``venus.core`` schema provides the core tools

YASDL database instances are self explaining: the database instance stores the source code for all the schemas that
were used to compile and generate the database instance. It also stores

Universal references
--------------------

YASDL supports universal references. Database fields generated from universal references are able to reference to
*any* table in the database. In order to create a universal reference, you need to inherit a fieldset from the
``venus.core.t_uniref`` base class. This will generate a pair of fields. The first field has a foreign key constraint
to the table generated from the ``venus.core.r_table`` final realized fieldset. Every realized top level fieldset
has a unique row in the ``venus.core.r_table`` table with its unique identifier, and the value of the first field
determines the table which is referenced. The second field is a reference to the row in the referenced table.


.. code-block:: yasdl

    schema anyref {
        use types;
        use venus.core;

        language "en";


        required fieldset document {
            required field name : types.name { requirelevel "mandatory"; }
            required field filepath : types.name { requirelevel "mandatory"; }

            index uidx_document_name {
                fields name;
                unique true;
            }
        }

        required fieldset document_of {
            required field document -> document;
            required fieldset rec : venus.core.t_uniref;
            index uidx_document_of {
                fields document rec;
                unique true;
            }
        }

    }


.. note::

    You can read more about the built-in schemas in the venus schema section.

In our example, the ``anyref_test.document_of.rec`` field translates into something like this:

.. code-block:: sql

    CREATE TABLE "anyref"."document_of" (
      "id"                            bigint NOT NULL,
      "document"                      bigint                        ,  -- document -> anyref.document
      "rec$tbl"                       bigint                        ,  -- rec.tbl -> venus.core.r_table
      "rec$row"                       bigint                        ,  -- rec.row
      CONSTRAINT "pk$document_of" PRIMARY KEY ("id")

    );
    ALTER TABLE "anyref"."document_of" ADD CONSTRAINT "fk$document$document"
      FOREIGN KEY ("document") REFERENCES "anyref"."document"("id");
    ALTER TABLE "anyref"."document_of" ADD CONSTRAINT "fk$rec$tbl$core$r_table"
      FOREIGN KEY ("rec$tbl") REFERENCES "venus$core"."r_table"("id");
    CREATE UNIQUE INDEX "document_of$uidx_document_of" on "anyref"."document_of"("document" ASC,"rec$tbl" ASC,"rec$row" ASC);


The foreign key constraint for the first field value is automatic. For the second field (row reference),
it is usually implemented by triggers, because most relational database systems do not support universal references.
It implies that using universal references can lower database performance, especially when you have to delete
referenced fields frequently.

Universal references can be used to create universal solutions. In the above example, we have created a general
document storage, and we made it possible to connect documents to virtually anything that is stored in the database.
However, you will have to pay the cost for  this flexibility. This cost includes lower database performance and
more difficult semantics. Although the YASDL database access layer has support for making joins to universally
referenced tables (or sets of tables), it is more difficult to handle such queries.

In a concrete implementation, program code can be written to restrict (or at least configure) the list of allowed
tables that can be referenced.

.. todo::

    Create configuration tools for restricting the fieldsets that can be referenced. Using this config,
    it may be possible to increase performance. One tool would be an "interface" declaration that could
    also be used to generate dynamic queries for universal references. But that is a long way down the road.

