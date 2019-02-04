
Arrow operator, referencing definitions
=======================================

What it means
-------------

The arrow operator can only be used in the context of a field and an outermost fieldset definition. Outermost fieldset
definitions are the ones placed at the schema level. Implementation note: YASDLDefinition.is_outermost().
The arrow operator tells that the field must have a special identifier type that can reference a fieldset.
Practically, in the database instance this translates into a foreign key constraint to another (or the same) table
and makes the field's type compatible with the referenced table's primary key.

There can be special properties given for these "reference" fields for defining "on delete cascade" etc.

.. todo::
    list these special properties here or elsewhere.

It is important to understand, that names after the arrow operator mean the final implementation of the referenced
definition that is realized as database table. This meaning is forced semantically - you cannot possibly have a
reference to something that does not exist in the database. (You can read more about dynamic binding later in this document.)

The references property
-----------------------

It must be noted that the arrow operator is syntactic sugar. The same thing can be achieved by using the references
property. The arrow operator was introduced to emphasize the importance of the referencing connections between
definitions. Referencing a definition by using both the arrow operator and the references property is an error.
Since the arrow operator defines a property and properties are inheritable, descendants will inherit the value of this
property. For example:

.. code-block:: yasdl

    field customer_ref -> person { label "customer"; }
    # Same as: field customer_ref { references person; label "customer"; }

    fieldset company {
        field name : name;
        field best_customer : customer_ref; # This will be a reference to a person...
    }


Although it is possible to clear the value of the references property, this is probably something you will never want to do:

.. code-block:: yasdl

    field customer_ref -> person { label "customer"; }
    fieldset company {
        field name : name;
        field best_customer : customer_ref{
            references; # best_customer **will not be** a reference to a person
        }
    }


.. note::

    YASDL has support for so called universal references. They can reference any row in any table in the database
    instance. For details, please read the built-in schemas section.

