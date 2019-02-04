
Realization of definitions
==========================

This is an advanced topic. You have been warned.

Introduction
------------

Being realized means that the final implementation of a definition is actually used to create an object (field or table)
in a database. All definitions are part of an implementation tree, even if the tree contains just one definition. The
root of the tree is the final implementation. If the final implementation is selected for database object generation,
then the definition is said to be realized. If a fieldset definition is realized, then all of its contained definitions
are realized (because they are also used to generate concrete objects in the database). You have the power to tell the
compiler that a given definition should be realized. This is done via the ``required`` modifier. You can read more about
that later. For this section, the important thing to know is that not all definitions are realized. The compiler selects
some final implementations and generates database objects from them. They together solve a task. Things that are not
really required for solving the task will not be realized. A realization is always connected to exactly one final
implementation, but it is the realization of all of its specifications.

Suppose we have the following schemas:

.. code-block:: yasdl

    schema types1 {
        # ...
    }

    schema types2 {
        # ...
    }

    schema invoicing {
        use types1;
        fieldset customer {
            field name : =types1.name { history true; };
            fieldset cust_address := types1.address;
            field account_number := types1.name;
            field annotation : types1.text;
            # ... (other fields here)
        }
        fieldset product {
            # ...
        }
        # ...
    }

    schema cmr {
        use types2;
        fieldset partner {
            field name : =types2.name;
            fieldset part_address := types2.address;
            field company -> company;
            # ... (other fields here)
        }
        fieldset company {
            # ...
        }
    }

Let's suppose that cmr and invoicing were supplied by different vendors together with modules and libraries for
creating, printing and digitally signing invoices, and for storing phone caller ids automatically etc. As an end user,
we want to unify invoicing and cmr capabilities. Certainly we want cmr.partner and invoicing.customer to be the very
same thing in our application. We don't want to keep a separate list of our customers of invoices, and list of
partners for other documents/events, because they will be the same persons, and we want to avoid data duplication.
So this is what we try first:

.. code-block:: yasdl

    schema end_user_schema {
        require cmr;
        require invoicing;
        fieldset myperson : invoicing.customer cmr.partner {
            implements all;
        }
    }

Well, we have serious problems with this.

* The ``invoicing.customer.name`` field hides the ``cmr.partner.name`` field. It is because
  ``invoicing.customer`` was listed first in the ancestors list and both of them have a name field.
  It can be a problem because the program code for the ``cmr`` schema may want to access the
  ``cmr.partner.name`` field. But it is not realized. It is not used to generate an actual field in a database table.
  Although the ``cmr.partner`` fieldset is realized as a table. So the code that tries to access the
  ``cmr.partner.name`` field will fail.
* Most of these problems with hidden names are solved by accessing elements with their names. For example, you do not
  access the field as ``cmr.partner.name`` but you access it as the name field of the final implementation of
  ``cmr.partner``. However, nothing guarantees that it will work. For example, because ``types1.name`` and
  ``types2.name`` can be totally different, and the program code for the ``cmr`` schema may require the ``name``
  field to have a property that was defined in ``types2.name``, but not in ``types1.name``. In our example,
  the realized ``name`` field will not have the property ``history true`` present.
* Even worse, a property can hide a fieldset with the same name, or a field can hide a property with the same name etc.
  A code that tries to access a fieldset by its name, but gets a reference to a property will certainly fail.
* The resulting ``myperson`` fieldset will have a ``part_address`` and a ``cust_address`` field, inherited from
  two different ancestors. Both of them represent the same thing: "the address of my person". What if we want to have
  a single address field instead? How do we do that without breaking the business logic/program code of ``invoicing``
  and ``cmr`` schemas? The business logic code won't even be able to access such a field realization by its name,
  since it will certainly have a different name. So both program codes will fail because they will try to access the
  values of unrealized things. We could - in theory - inspect their program code, create subclasses
  programatically, and adapt the code to deal with the changed definition. We would possibly have to alter the
  original code: make properties from attributes, make accessor methods from attributes and refactor the original
  code etc. This is not too efficient. One would have to know how to write computer programs, understand how the
  original code works, then break into it, change it. What makes it even worse is that a definition like
  ``cust_address`` is probably referenced from a dozen places in the program code. So we should have to override a
  dozen of methods. All of that because we changed the name of a definition? Later of course when the developer of
  the invoicing system decides to update his code, we would have to start over again. It would be much better to
  adapt the definitions instead of the code!

So one problem is to guarantee that realization of definitions that are required. Another problem is to avoid
"whole in the visibility" and let the user realize definitions under different names, but in a way that permits reuse of
program code to the greatest possible extent.

The code should be accessing all realizations through their specifications. All definitions should know where their
realizations are. Even when the final implementation of a definition changes, its specification is not changed, and
the original code still works without any modification, because it uses the specification for accessing the realization.
This is exactly what you can do with YASDL.

Using the required modifier in specifications
---------------------------------------------

In order to guarantee realization of definitions, you need to use the ``required`` modifier. For all realized final
implementations, the compiler goes over their specifications, and checks if their required members are realized.
(You can read the complete description of this process at section "compiler phase 6".) If some of them are not realized,
then you will get a compile time error, telling that the specification requires that definition to be realized.
In our example, we can add these modifiers to certain fields:

.. code-block:: yasdl

    schema types1 {
        # ...
    }

    schema types2 {
        # ...
    }

    schema invoicing {
        use types1;
        fieldset customer {
            required field name : =types1.name { history true; };
            required fieldset cust_address := types1.address;
            required field account_number := types1.name;
            required field annotation : types1.text;
            # ... (other fields here)
        }
        fieldset product {
            # ...
        }
        # ...
    }

    schema cmr {
        use types2;
        fieldset partner {
            required field name : =types2.name;
            required fieldset part_address := types2.address;
            required field company -> company;
            # ... (other fields here)
        }
        fieldset company {
            # ...
        }
    }

    # ...

    schema end_user_schema {
        require cmr;
        require invoicing;
        fieldset myperson : invoicing.customer cmr.partner {
            implements all;
        }
    }

This will now result in a compile time error, because ``cmr.partner.name`` is required, but not realized.
We will have to come up with a different ``end_user_schema``, because it won't compile until all required
fields are realized.

Please note that the required modifier can be used for outermost fieldset definitions too. The meaning of that is given
later in this document.

Explicit realization
--------------------

Using the pattern below, you are able to fulfill all requirements:

.. code-block:: yasdl

    schema end_user_schema {
        require cmr;
        require invoicing;
        fieldset myperson {
            implements cmr.partner invoicing.customer;
            # Fields common in both fieldsets
            required field name : invoicing.customer.name {
                implements cmr.partner.name invoicing.customer.name;
            }
            required fieldset address : invoicing.customer.address {
                    implements cmr.partner.part_address invoicing.customer.cust_address;
            }
            # Fields in invoicing
            required field account_number : invoicing.customer.account_number {
                implements invoicing.customer.account_number;
            }
            required field annotation : invoicing.customer.annotation {
                implements all;
            }
            # ...
            # Fields in cmr
            required field company -> cmr.partner.company;
            # ...
        }
    }

Here we have reimplemented ``cmr.partner`` and ``invoicing.customer`` from scratch. The newly created
``myperson`` fieldset is not inherited from anything. But its contents are copied from the above fieldsets,
and they explicitly implement definitions contained in those fieldsets. So all required fields become realized.

We have used the ``implements`` property to connect specifications with their implementations. Using explicit
realization, one can always make sure that every required field and fieldset gets realized. This is the most general
way to do it. In this example, you had to have knowledge about the inner structure of the required ``cmr`` and
``invoicing`` schemas. It is also true that whenever they change, you will have to refactor ``end_user_schema`` as
well. But this cannot be avoided, because it is not possible to unify two fieldsets from two different schemas
without extra knowledge. However, this refactoring happens at the YASDL level, and the compiler makes sure that all
required specifications are met. Chances are slim that you will be able to do it the wrong way without getting
error messages from the YASDL compiler.

.. todo::

    It is a planned feature to introduce keywords for implementing "all remaining definitions" from the
    specifications. There would be two forms of this. One would be ``implement all from all`` and
    ``implement all from <definition_reference>``. The second  form would be ``implement required from all``
    and ``implement required from <definition_reference>``.

    The first form would copy and re-implement all the not-yet-reimplemented statically contained definitions from
    all specifications, or from the given specification. By "copy and reimplement" we mean: create a descendant
    that changes nothing, just re-implements the definition. The second form would do the same, but only with the
    required definitions.

    Using these planned constructs, it would be possible to express that "all other things should be placed
    here", instead of listing all of them by name.

There are huge benefits of this approach. We could unify the required fields and fieldsets at the YASDL level. Using
the ``implements`` property, you can specify how a definition can adapt itself to a given specification. All other
program code is able to use the realizations through any of their specifications. Regardless of the way they are
realized. The business logic program code that wants to access the realization of ``invoicing.customer.cust_address``
field will actually be using the database field that was generated from ``end_user_schema.myperson.address``.

**We have merged schemas in a way so that their corresponding business logic code still works, and it does not need
to be changed.** It doesn't matter that in the generated database, ``invoicing.customer.cust_address`` is realized
with a different name ``end_user_schema.myperson.address``. The program code that was created for the invoicing schema
will access that table field through the interface of the ``invoicing`` schema. Whenever that code wants to access
``invoicing.customer.cust_address``, it can be sure that it is there, because it was marked with the ``require``
statement. In the background, the API will translate references of the definitions to the names of their realizations.

The developer of the ``invoicing`` schema can change his solution. First of all, he can add new fields to the
``customer`` fieldset, and they will appear in the ``end_user_schema`` as well. When designed properly, GUI will
query the available members in the fieldset and also update itself to display the new fields. If the developer
decides to rename ``cust_address`` to something else, it's not a problem: you just need to change one name in the
"implements" line. Nothing else to refactor! If you forget to do it: you will get an error message, telling that
something required is not realized.

The developer of the ``invoicing`` schema is responsible for writing code that accesses the database through the
interface of the ``invoicing`` schema. Apart from that, he can refactor the program code, even change method signatures.
The user of the ``end_user_schema`` schema will likely have to do nothing to get all the benefits of the updates.
Touching the source code is not needed at all. Almost everything works automatically. What doesn't work
automatically is something that you would want to check manually anyway.

If you are familiar with Windows programming, then you will notice that this is somewhat similar to what you can do
with COM objects. You can always call ``IUnknown::QueryInterface`` on a COM object to see if it supports a given
interface. If so, then you can use the object through that interface. However, YASDL is more declarative and
less imperative. Instead of writing interface methods manually, YASDL uses implementation trees to tell how an
implementation realizes its specification. Given a database table and one of its specifications, you can request
an object that accesses data inside the database table through the given specification.

Interfaces and implementations are not new. Most programming languages use them to raise the level of abstraction.
The new thing in YASDL is that the structure of the database schema is defined in an OO language that supports
interfaces, specifications and implementations. Almost all database applications are bound to a specific database
structure, and it is usually impossible to use the same program code with a different database structure. YASDL
provides an object oriented layer between database oriented code and the database itself. It separates the
realization of the database objects and their formal definitions, and makes it possible to bind program code
to the formal definitions instead of the database objects. Formal definitions can then be manipulated using OO tools.
(Database objects cannot.) With YASDL, it is possible to create a solution - a new formal database schema and a
program code - for a problem domain. Then it is possible to combine, merge and reuse these solutions with the least
effort possible.

.. todo::
    Put the figure about program merging and refactoring here!
