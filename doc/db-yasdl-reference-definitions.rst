
Structure of a YASDL document
=============================

Introduction
------------

The root definition **must** be a schema definition. Inside the schema definition, you can place multiple field and
fieldset definitions. Fieldset definitions can contain field and nested fieldset definitions. Index definitions can
only occur inside fieldset definitions.

Formally::

    schemadef  ::= schema name "{" use_require_stmt* outermost_definition* "}"
    outermost_definition ::= fielddef | fieldsetdef | simpleprop

Intuitively:

.. code-block:: yasdl

    schema myschema {
        use anotherschema;
        require anotherschema;

        field fieldname {}
        fieldset fieldsetname {}

        property1 value1 value2;
        property2 value3 value4 value5;
    }

Schema definitions
------------------

The purpose of a schema is to define a set of definitions that allow to solve a task.

The schema definition does not need to be complete. If you want bottom-up composition, then you can start with a small
schema that solves a very simple task. For example, you define a fieldset that can store "postal address"
information, including the country, county/state, address lines, zip code etc. Then you can develop a default
editor, a viewer widget, program code to find zip code by name etc. and finally publish your widgets and program
code together with your schema definition. It is up to the end user to decide if he wants to use your schema
untouched, or create a descendant and modify it, add third party widgets that do different zip code validation etc.
He can also decide if he wants to use separate table(s) for addresses (for one-to-many and many-to-many) or embed
a "postal adress" fieldset into his table(s) (for one-to-one). The motto is: everything should work as expected out
of the box, everything should be re-usable, and everything should be possible.

Every schema has a name. A schema can contain any number of use/require statements and outermost definitions.
Outermost definitions can be field definitions and fieldset definitions. (Use and require statements are
described later in this document.)

When stored in a text file, the name of the text file should reflect the name of the schema definition, and should
have .yasdl file extension.

Field definitions
-----------------

Formally::

    fielddef ::= normal_fielddef | reference_fielddef
    normal_fielddef ::= [modifiers] "field" name [typedef] properties
    reference_fielddef ::= [modifiers] "field" name -> referenced_name properties
    general_fielddef ::= [modifiers] "field" name [typedef] -> referenced_name properties
    properties ::= ";" | ( "{" property+ "}" )
    property ::= name [value*] ";"
    modifiers ::= modifier+
    modifier ::= "abstract" | "final" | "required"

Typedef was already defined at the colon operator section above.

Intuitively:

.. code-block:: yasdl

    field field1 : ancestor1;
    field field2 : ancestor2 { property1 property2 propertyN }
    field field3 { property1 property2 ... propertyN }
    field field4 -> fieldset4;
    field field5 -> fieldset5 { poperty1 property2 propertyN }
    abstract required field field6 : ancestor6 -> fieldset6 { property1 property2 propertyN }

Normal (non-referencing) field definitions
..........................................

The first construct with normal_fielddef tells that the field has the given ancestors, if any. Ancestors can be other
field definitions. The field being defined will inherit properties from its ancestors, and may override them or add new ones.

The built-in type (like varchar, integer, float etc.), of a field is not an ancestor. For specifying the built-in type
of a field, you must use the "type" property. The "type" property can be inherited from ancestors. Any realized (final
implementation) field must have exaclty one built-in field type assigned (inherited or specified directly).

In order for a field definition to be instantiated (successfully used for generation), certain properties must exist.
For example, fields with varchar type cannot be instantiated unless they have a size. Hovewer, such "incomplete" field
definitions can be defined and used as ancestors for other fields. Here is an example:

.. code-block:: yasdl

    field longtext : { size: 255; }
    field description { type varchar; label "Description"; reqlevel optional; }
    field hint : description longtext; # This has size=255 and type=varchar

In our first example we have used { type varchar; size 100; reqlevel mandatory; } three times. We could have created
a new "name" field definition instead:

.. code-block:: yasdl

    schema naming_test {
        field name { type varchar; size 100; reqlevel mandatory; }
        fieldset country { field name : name; }
        fieldset person {
            field name : name;
            field country -> naming_test.country { reqlevel mandatory; }
        }
        fieldset carowner : person {
            field birthdate { type date; reqlevel mandatory; }
        }
        fieldset car {
            field make : name { reqlevel optional; }
            owner -> person { reqlevel mandatory; }
        }
    }

Referencing field definitions
.............................

The second construct with reference_fielddef ("-> name") tells that the field is a reference to the definition given by
name. To be more precise, the value of the corresponding database field holds a reference to a row that lives inside a
database table that was generated from the final implementation of the referenced fieldset definition. In the database
instance, it realizes a foreign key constraint. The referenced definition must be an outermost fieldset definition.
You cannot reference a field definition. (And of course the referencer must be a field definition - using the
references property in a fieldset ismeaningless.) If the referencing field is realized, then the referenced fieldset
definition must also be realized. This check is forced because foreign key constraints cannot be possibly created on
non-existent objects. If a field is a referencing field, then it must have type "identifier" property given, or not
assigned a type at all. (In that case, "identifier" will be assumed.)

Combining inheritance and reference
...................................

The third construct with general_fielddef shows how to combine the arrow and the colon operators. E.g.

.. code-block:: yasdl

    field owner_ish { label "Owner"; ondelete "cascade"; } # Owned things cannot live without the owner.
    field owner : owner_ish -> person;

Adding and changing properties in field definitions
...................................................

For both normal and referencing field definitions, you can give additional properties inside curly braces, or close the
definition with a semicolon. Properties specified in a definition will overwrite the values of the same properties
defined in its ancestors. If a property is not specified in a definition, it will be inherited from its ancestor (with
the exception of the implements and ancestors properties - they are not inherited). When there are more ancestors
present, the first listed ancestor will take precedence.

Field definition modifiers
..........................

Modifiers of field definitions will be discussed together with fieldset definition modifiers later in this document.

Use of field definitions
........................

One usage of a field definition is to place it inside a fieldset definition. The other usage is to define an abstract
field type, that can be used as an ancestor for other field definitions.

Fieldset definitions
--------------------

Formally::

    fieldsetdef ::= [modifiers] "fieldset" name [typedef] ";"
    fieldsetdef ::= [modifiers] "fieldset" name [typedef] "{" fsitems "}"
    deletion ::= "delete" name ";"
    fsitems  ::= fsitem+
    fsitem   ::= fieldsetdef | fielddef | indexdef | deletion | property

NOTE: index definitions will be discussed later.

Intuitively:

.. code-block:: yasdl

    fieldset myfieldset {
        field field1 : achestor;
        field field2 : ancestor1 ancestor2 { property1; property2; propertyN; }
        fieldset fieldset3 : anotherfieldset;
        fieldset fieldset4 {
            field subfield1 : ancestor21;
            field subfield2 : ancestor22;
            # ...
        }
        # ...
        property1;
        property2;
        # ...
        propertyM;
        # ...
        index idx1 {
            #...
        }
        index idx2 {
            #...
        }
        # ...
        delete name1;
        delete name2;
        # ...
    }
    final fieldset country { field name:name; field code : varchar { size 2; } }
    abstract fieldset person;


As you can see, fieldset definitions can be placed inside schema definitions or nested inside other fieldset definitions.
They can contain field definitions, fieldset definitions, index definitions, name deletions and properties.

Fieldsets can be used for different purposes:

* To form a database table.
* For making a complex type, to be embedded into other fieldsets.
* For making an abstract type, specifying some requirements about another (not yet known) implementation.
* Any of the above at the same time (use it as a table in one case, embed it into a table as a complex type and use it
  as the ancestor of another table at the same time)

Adding and changing properties in fieldset definitions
......................................................

It is not very different from field definitions. Most important difference is that the references property is not
available for fieldsets.

Fieldset definition modifiers
.............................

Fieldset definition modifiers and field definition modifiers are discussed together in the following section.


Index definitions
-----------------

Formally::

    index ::= "index" name properties
    fields_prop ::= "fields" [ "+" | "-" ] dotted_name

Intuitively:

.. code-block:: yasdl

    index uidx_owner_make {
        fields field1 field2 field3;
        unique true;
        property1;
        property2;
        # ...
        property M;
    }

    index uidx_owner_make_2 {
        fields +field4 -field5 field6;
        unique true;
        property1;
        property2;
        # ...
        propertyM;
    }

Rules:

* Index definitions are valid inside fieldset definitions only.
* The special property fields must be used inside all index defintions and it must contain a non-zero-length list of
  field or fieldset names of the fieldset, optionally prefixed with a plus or minus sign.
* By specifying a fieldset instead of a field, you can express that the index should be created on all of the
  fields contained in the given fieldset.
* You can list multiple fields or fieldsets. The contained fields will be unified for index creation.
* Prefixing the field/fieldset name with a minus sign will add the field(s) to the index in descending order.
* The special property unique can be used to make an index unique. This generates a "unique check constraint" or a
  "unique index" in the corresponding database table.

Indexes are created for fieldsets that are realized final definitions, and only when they are defined in the outermost
level of the fieldset. Consider this example:

.. code-block:: yasdl

    schema indexes_01 {
        language "en";

        abstract field text {
            type "text";
            reqlevel "mandatory";
            notnull true;
        }

        fieldset inner_1 {
            field code : text;
            field name : text;
            index uidx_code {
                fields code;
                unique true;
            }
            index idx_name {
                fields name;
                unique true;
            }
        }

        required fieldset outer_1 {
            fieldset inner : inner_1;
            field description : text;
            index idx_description {
                fields description;
            }
        }
    }


In this example, the realization of the outer_1 fieldset will have the idx_description index generated, because it was
defined in the outermost level. But uidx_code and idx_name will not be created, because they are defined at an inner level.

Inheriting index definitions
............................

You cannot inherit an index from another index, but when you inherit a fieldset from another, then contained index
definitions of the ancestors will be inherited (together with other contained definitions). Consider this second example:

.. code-block:: yasdl

    schema indexes_02 {
        language "en";

        abstract field text {
            type "text";
            reqlevel "mandatory";
            notnull true;
        }

        fieldset base_2 {
            field code : text;
            field name : text;
            index uidx_code {
                fields code;
                unique true;
            }
            index idx_name {
                fields name;
                unique true;
            }
        }

        required fieldset outer_2 : base_2 {
            field description : text;
            index idx_description {
                fields description;
            }
        }
    }


In this second example, the realization of the outer_2 fieldset will have all of the incides generated
``(uidx_code, idx_name, idx_description)`` because all of them were defined at the outermost level of the realized
fieldset.

Incides and field realizations
..............................

Whenever an index is realized (used for database object generation), all of its fields must be realized.
Look at this third example:

.. code-block:: yasdl

    schema indexes_03 {
        language "en";

        abstract field text {
            type "text";
            reqlevel "mandatory";
            notnull true;
        }

        fieldset base_3 {
            field code : text;
            field name : text;
            index uidx_code {
                fields code;
                unique true;
            }
            index idx_name {
                fields name;
                unique true;
            }
        }

        required fieldset outer_3 : base_3 {
            field code : text { label "Special code"; }
            field description : text;
            index idx_description {
                fields description;
            }
        }
    }


The above schema cannot be successfuly compiled. Explanation:

* The base_3.uidx_code index lists the base_3.code field in its fields property. So the index cannot be created unless
  that field is realized.
* The outer_3.code field hides the base_3.code field. So a field that is part of an index is not realized. So the index
  cannot be created for the table that is generated from the required outer_3 fieldset.

One solution to this problem would be to rename your outer_3.code field so that base_3.code will not be hidden.

Another possibility would be to rename the base_3.code field. For this, the base_3 fieldset must be used as a stub, and
it must be referenced with imp_name constructs:

.. code-block:: yasdl

    schema indexes_04 {
        language "en";

        abstract field text {
            type "text";
            reqlevel "mandatory";
            notnull true;
        }

        fieldset base_3 {
            field code : text;
            field name : text;
            index uidx_code {
                fields code;
                unique true;
            }
            index idx_name {
                fields name;
                unique true;
            }
        }

        # This is how you can rename a field *within an implementation tree*.
        fieldset base_3_new : base_3 {
            implements all;
            field code3 : text { implements base_3.code; }
            field name3 : text { implements base_3.name; }
        }

        # And of course, anybody who uses the original specification
        # should use an imp_name.
        required fieldset outer_3 : =base_3 {
            field code : text { label "Special code"; }
            # This will "rename" the original field.  ;-)
            field description : text;
            index idx_description {
                fields description;
            }
        }
    }


Remember: whenever you want others to be able to modify a definition, you should create a stub from it and inherit with imp_name.
The above schema will now compile, and it will create these fields::

    code3 (inherited from base_3_new.code3)
    name3 (inherited from base_3_new.name3)
    code (directly given as outer_3.code)

and it will also have these incides::

    outer_3.uidx_code(outer3.code3) - defined at base_3
    outer_3.idx_name(outer3.name3) - defined at base_3

Notice that although the definition of ``base3.uidx_code`` references the ``base_3.code`` field, its actual
realization will reference the realization of the same field. That is, ``outer_3.code3``. Other users (outsiders?) of
the ``base_3`` fieldset can still rely on the uniqueness of the realization of the ``base_3.code`` field,
regardless of how it was named.

Another possibility would be to use the ``rename`` keyword. But that was not implemented yet. It is a planned feature
that might be implemented sometime. For now, you can only do a reimplementation with a different name, and that will
change the name of the realization too.

Changing index fields through reimplementation
..............................................

Consider the following example:

.. code-block:: yasdl

    schema indexes_05 {
        language "en";

        abstract field text {
            type "text";
            reqlevel "mandatory";
            notnull true;
        }

        abstract fieldset prod_id_fields {
            # This fieldset describes what identifies a product.
            field code: text;
            field name: text;
            field region : text;
        }

        required fieldset product {
            required fieldset ids : =prod_id_fields;
            required field description : text;
            index uidx {
                fields ids;
                unique true;
            }
        }


        abstract fieldset my_prod_id_fields : prod_id_fields {
            # I have decided to remove region from the identifying fields
            # abstract type, because it is not really neeed: my application
            # will be used in a single region only.
            implements all;
            delete region;
            # Rename code to prodcode
            field prodcode :  prod_id_fields.code {
                implements all;
            }
        }


    }

The product table will be something like this:

.. code-block:: sql

    CREATE TABLE "indexes_05"."product" (
      "id"                            bigint NOT NULL,
      "ids$prodcode"                  text                          ,  -- ids.prodcode
      "ids$name"                      text                          ,  -- ids.name
      "description"                   text                          ,  -- description
      CONSTRAINT "pk$product" PRIMARY KEY ("id")

    );
    CREATE UNIQUE INDEX "product$uidx" on "indexes_05"."product"("ids$prodcode" ASC,"ids$name" ASC);


Originally, the ``prod_id_fields`` defined all the fields that together identify a product. We have used this
as an abstract fieldset type in the ``product`` fieldset, and defined an unique index on it.

In this example, we have demonstrated that an and user may alter the identifying fields: remove the ``region``,
change name of ``code`` to ``prodcode``. The ``product.uidx_product`` index is expressed as "create it for all
the fields for the final implementation of ``prod_id_fields``". As a result, the modifications will affect not just
the fields created in the ``product`` table, but also the fields of the index.

So this is another usage of fieldsets: group identifying fields so that one can define a unique index on them.
Whenever the identification changes, the index automatically changes.

Removing contained definitions and properties
---------------------------------------------

Using the delete keyword, it is possible to delete an inherited definition. Deleting and re-defining the same name
inside the same {} block is an error. Example:


.. code-block:: yasdl

    schema delete_test {
        language "en";

        fieldset a {
            field f1;
            field f2;
            field f3;
        }

        fieldset b : a {
            # This removes f2. Leaves f1 and f3.
            delete f2;
        }

        fieldset c : a {
            delete f2;
            # This is an error, cannot delete and redefine the same name
            # inside the same {} block.
            fieldset f2;
        }
    }


If you try to delete a name that is not inherited, then you will get a compiler warning message.

.. todo::

    It should be possible to make this an error, with a special compiler setting.

.. todo::

    Make sure that the delete keyword binds statically. (Or not?) Document here that the binding is static or
    dynamic.

Deletion works only in the namespace of the containing block. It is important to understand that you can only delete
simple names. E.g. you cannot put dotted names after the delete keyword. If you need to delete something from an
inner definition, then you must do it inside the inner definition.

