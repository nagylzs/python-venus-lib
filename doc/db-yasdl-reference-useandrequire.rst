The use and the require statements
==================================

Introduction
------------

A key point in YASDL is reusability. Although you can only define one schema per YASDL document, you can use elements
from other schemas. As described before, definitions can be referenced with their dotted names. The use and require
statements make it possible to reference definitions in external schemas. The difference between a use an a require
statement is semantic, and will be described later in this document.

Formally::

    use__require_stmnt ::= local_use_stmnt | local_require_stmnt | uri_use_stmnt | uri_require_stmnt
    local_use_stmnt ::= "use" (dotted_name "as" NAME)|(NAME) ";"
    local_require_stmnt ::= "require" (dotted_name "as" NAME)|(NAME) ";"
    uri_use_stmnt ::= "use" uri_string "as" NAME ";"
    uri_require_stmnt ::= "require" uri_string "as" NAME ";"
    uri_string ::= STRING

Here ``uri_string`` should be a well formed URL.

Intuitively:

.. code-block:: yasdl

    schema "myschema" {
        use mytypes; # No alias is required here.
        require products; # No alias is required here.
        require basic.calendar as cal;
        require basic.invoicing as inv;
        use "http://www.YASDLschemas.org/schemas/isbn.YASDL" as isbn;

        fieldset person : basic.calendar.person inv.person isbn.author {
            implements all;
            owner : mytypes.owner;
            products 12;                        # Example property the hides the name
                                                # of an alias, but inside a different
                                                # definition.
            product -> schema.products.product; # Absolute access
                                                # of a definition contained
                                                # in a required schema.

        }

        fieldset products; # This is invalid, "products" name is already used by a require statement.
    }

You **must** give an alias name for any use/require statement, except when you use/require a schema that has a simple
name. It is because the name of the used/required schema is placed in the namespace of the schema using/requiring it.
Only simple names can be placed in a namespace, so either you have to use/import a schema that has a simple name,
or specify an alias name.

Using or requiring local schemas
--------------------------------

The local_use_stmnt (or local_require_stmnt) loads definitions from a schema that is stored on the local filesystem.
Search for an appropiate schema will start in the current directory, then in the directories specified by the
~/.yasdlrc file. Each part in the dotted name should be a directory, except for the last one which should be a file
with ".yasdl" extension. The name (package name) of a locally stored schema must match the name it was used/required with.

Using/requiring remote schemas
------------------------------

The uri_use_stmnt (or uri_require_stmnt) loads definitions from the given URI. This can be a http, https or ftp address.
(No authentication.) The name of (package name) of the schema must begin with the reversed domain name. (Similar to
java. So if the schema was downloaded from www.some.domain.com then the package name must start with com.domain.some)

TODO: Use keyrings or any other way to allow authentication.

The alias name of a used schema
-------------------------------

The word after the as reserved word is called the alias of the used schema. The alias is an abbreviation of the used
schema and it can be used for referencing its namespace. When the alias is not given, the used schema's namespace can
be accessed using its full dotted name (the dotted name given before the as reserved word.) For uri use statements,
the alias name is mandatory (because an URI is not a valid dotted name).

Semantic rules of the use and require statements
------------------------------------------------

Use and require statements must build up into an acyclic graph. Syntactically, a set of YASDL files can be correct,
but they will fail semantic check if circular references are detected.
