Modifiers
=========

Introduction
------------

Before we can explain what kind of animals they are, we need to clarify some things. We were talking about definitions,
specifications and implementations. Now it becomes very important to understand the meaning of these terms, and the
differences between them.

* **Definition** is not semantic. It is defined by the syntax of the language. There are four main types of definitions:
  schema, fieldset field and index. (Properties are not definitions, most of them cannot be realized as concrete database
  objects.)
* The terms **specification** and **implementation** are only meaningful for fields and fieldsets. We we talk about
  implementation or specification, we assume that "definition" either means a field definition or a fieldset definition.
* **Self implementation** - we say that every definition I is a possible implementation of itself, because it exactly
  implements all of its specifications. We also say that I is self implemented or implementor of itself. Self
  implementation mathematically forms a reflexive binary relation between definitions.
* **Direct implementation** - we say that a definition I is a direct implementation of another definition D if and only
  if D is listed after the implements property in I ( either explicitly, or with the all reserved word, or both). We
  also say that I is a direct implementor of D. Direct implementation mathematically forms an antireflexive
  antitransitive binary relation between definitions.
* **Implementation** - we say that a definition I is an implementation of another definition D if and only if (I,D) is
  part of the reflexive transitive closure of the directly implements relation. In other words, when any of the
  following conditions are met:
  - I and D are the same
  - or I directly implements D
  - or there is a D2 for that I directly implements D2 and D2 directly implements D
  - or there are D2 and D3 that connects I to D in two steps (e.g. I directly implements D2, and D2 directly implements D2, and D3 directly implements D)
  - Or there is a finite number of definitions D1,D2,...DN that connect I to D in N steps.
* **Indirect implementation** - It means: "I is an implementation of D, but it is not a direct imementation and I and D are different".
  Formally::

        indirectly_implements(I,D) ::= (I!=D) and implements(I,D) and not (directly_implements(I,D))


* **Specification** - The "S is a specification of D" relation is the inverse relation of the "D is an implementation
  of S" relation. Certainly, terms such as direct specification, indirect specification and self specification do exist
  and their meaning should be obvious by now.
* **Final implementation** - The relation called I finally implements D means the following thing::

        finally_implements(I,D) ::= implements(I,D) and not exists I2: (I2<>I and implements(I2,I))

  In other words: I it is the one that implements D, but is implemented by itself only.
  Some things you do not really need to think about The "finally implements" relation contains final implementations
  on the left side, and all of their specifications on the right side. This relation is homogeneous binary reflexive
  and antitransitive. Reflexive because final implementations are always final implementations of themselves.
  Antitransitive, because final implementations on the right side are never connected to anything on the left side
  but themselves, preventing any kind of transitivity. Relations having such properties are called classifying
  relations, because they create classes over the set they are defined on. In our case, all definitions are
  classified with their final implementation. In other words, every definition has exactly one final implementation
  assigned. The number of classes and the number of final implementations are the same. Visually, you really can
  think these classes as trees, where the root node is the final implementation, and each node is a definition
  connected to one implementor and (possibly) many specifications. A complete schema set is in fact a forest of
  implementation trees.

Using inheritance, you can create definitions that are "similar" in a way, but these definitions may
**mean different things**. This lets you specify only the formal differences between definitions - this is for reusing your
code statically. In contrast, definitions in the same implementation tree **mean the same thing**. They expose
different ways for accessing the same thing, creating "aspects" of the same thing (thing=an acutal database object,
that is a realization of the corresponding final implementation) in different contexts - this is for reusing your code
dynamically.

Now that we have the precise definitions of these terms, we can tell what these modifiers are doing.

The abstract modifier
---------------------

``abstract D`` instructs the compiler to throw an error whenever D is selected as a final implementation. When you
define an abstract fieldset or field, you do this so that you can reference it after the arrow or the colon operator,
or in a property. However, you want to force the end user to change it some way, or not use it at all. E.g. the end
user will not be able to use it directly. She has to specify an implementation for it (or not use it). In most cases,
the end user will subclass the abstract fieldset or field, specify "implements all" and add new fields or change its
properties. This way you can specify that you need certain fields in the implementation by adding fields/sub-fieldsets
to the abstract fieldset. But it is not required: it is legal to define a totally empty abstract definition without any
field or property contained within.

It must be noted, that using the abstract modifier for fields is not as often used as it is used for fieldsets. The
reason for this is that field definitions are often used for prototyping. E.g. you define a field, then use it as a
base class for another field, then do it again and again, not thinking about the possibilities of the implements
property. It is common to create hierarchies of field definitions without using the implements property at all.
From implementation view, these fields are copies of each other, they have their own implementation trees. They are
different prototypes, but they are barely used directly for anything. They will be dropped into fieldsets in the
same style - without specifying the implements property. This loose syntax can work because these prototyes are
usually defined right into a schema, outside all fieldset definitions. As a result, they cannot and won't be directly
used for database field generation. It would be impossible to create a database field without a corresponding database
table. For the same reasons, the same prototyping technique doesn't work well with fieldsets. When it comes to
fieldsets, you should really start thinking about implementations and modifiers.

The final modifier
------------------

``final D tells`` the complier to throw an error whenever it finds an I definition that tries to list D after the
implements property. When you define a final field or fieldset, you are telling that the field/fieldset must not be
customized. Certain applications may require this (for example, because changing the type of a field would break
business logic). Please note that using a final field or final fieldset as an ancestor is perfectly legal, until you do
not try to put its name after the implements property.

Fallback definitions
--------------------

Fallback definitions do not have a corresponding modifier. This is the default behaviour. Being a fallback definition
means that the definition can be a final implementation, but it does not have to be. For future usages, the fallback
and modifiers keywords are reserved.

**The abstract and final modifiers are mutually exclusive. Specifying both for the same definition will result in semantic check error.**

The required modifier
---------------------

This modifier has a sightly different meaning for fielsets and fields.

The required modifier for fieldsets means that the fieldset must have realization (e.g. a final implementation that is
used for database object generation). But it is effective only if the schema is itself required implicitely (e.g. it
is passed to the YASDL compiler) or explicitly (e.g. it is required by the "require" statement from a required schema).
You can read more about this at the description of the YASDL compiler below.

The required modifier for fields should not be used unless the field definition is placed inside a fieldset definition.
In that case, it means that whenever its containing fieldset is realized, the field must be realized. You can read more
about this at the description of the YASDL compiler below.

