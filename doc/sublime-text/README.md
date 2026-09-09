# YASDL syntax highlighting for Sublime Text 4

A syntax definition package for `.yasdl` files. It is derived directly from
the lexer (`venus/db/yasdl/lex.py`) and the grammar (`venus/db/yasdl/yacc.py`),
so what you see in the editor is what the parser sees.

There is no plugin code, no linter and no build step - these are plain data
files that Sublime Text loads on its own.

## Installation

Copy the `YASDL` directory into your Sublime Text *packages* directory:

    Linux    ~/.config/sublime-text/Packages/YASDL
    macOS    ~/Library/Application Support/Sublime Text/Packages/YASDL
    Windows  %APPDATA%\Sublime Text\Packages\YASDL

For example, on Linux:

    mkdir -p ~/.config/sublime-text/Packages
    cp -r doc/sublime-text/YASDL ~/.config/sublime-text/Packages/

Sublime Text picks the package up immediately, no restart is needed. Open any
`.yasdl` file; if the syntax is not selected automatically, use
*View / Syntax / YASDL* (or click the syntax name in the status bar).

## What the package contains

| File | Purpose |
| --- | --- |
| `YASDL.sublime-syntax` | The syntax definition itself. |
| `Comments.tmPreferences` | Makes <kbd>Ctrl</kbd>+<kbd>/</kbd> insert `#` line comments. |
| `Indentation Rules.tmPreferences` | Auto-indent after `{`, auto-outdent on `}`. |
| `Symbol List.tmPreferences` | Puts schema/fieldset/field/index names into <kbd>Ctrl</kbd>+<kbd>R</kbd> and <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>R</kbd>. |
| `YASDL.sublime-settings` | 4 space indentation and brace matching for `.yasdl` files. |

## What gets highlighted

* **Declaration keywords** - `schema`, `fieldset`, `field`, `index`,
  `constraint` (`storage.type.*`), and the name that follows each of them is
  scoped as a definition (`entity.name.*`), which is also what feeds the
  symbol list.
* **Modifiers** - `abstract`, `final`, `required` (`storage.modifier`).
* **Imports** - `use` / `require` ... `as` ... (`keyword.control.import`).
* **Ancestors and references** - the names after `:` are scoped as
  `entity.other.inherited-class`, the target after `->` as
  `support.class.reference`, so inheritance and foreign keys are visually
  distinct from plain values.
* **Properties** - property names are highlighted in three groups:
  * `keyword.other.property` for the ones with a special meaning for the
    compiler (`lex.RESERVED_PROPERTY_NAMES`): `ancestors`, `implements`,
    `references`, `unique`, `delindexes`, `cluster`, `fields`;
  * `support.type.property` for well known built-in properties (`type`,
    `guid`, `displaylabel`, `hint`, `ondelete`, `notnull`, `default`,
    `lookupresultindex`, `check`, ...);
  * `variable.other.member.property` for everything else.

  The third group is worth paying attention to: a property name that is
  *not* highlighted like the built-in ones is either a genuinely custom
  property or a typo.
* **Literals** - single, double and triple quoted strings (with `\` escapes),
  integers, floats, and the `none` / `true` / `false` / `all` constants.
* **The `fields` list of an index** - the `+` / `-` sort direction prefixes
  are scoped as operators.
* **`[schema fieldset field index property]`** minimum class restrictions;
  anything else inside the brackets is marked `invalid.illegal`.

## Spotting errors

Sublime Text does not run the YASDL parser, but the syntax definition still
makes the two most common mistakes visible:

* A **`}` that closes nothing** is scoped `invalid.illegal.stray-brace` and
  is shown in the color scheme's error color (usually a red background).
* An **unterminated string** is scoped `invalid.illegal.unclosed-string` at
  the end of the line. This matches the lexer, which cannot tokenize strings
  spanning several lines - not even triple quoted ones, because
  `t_string_tquoted` and `t_string_tfquoted` are not compiled with `DOTALL`.

  This also means that a double quoted string containing unescaped `"`
  characters - for example an SQL `check` expression - will show up as an
  alternating string/identifier mess. That is not a bug in the highlighter:
  the lexer really does end the string at the second `"`.

For a **missing** `}` there is nothing the syntax definition can do on its
own; everything after it simply stays inside the block. Install the
[BracketHighlighter](https://packagecontrol.io/packages/BracketHighlighter)
package if you want unmatched opening braces flagged as well - it works with
this syntax out of the box, because braces are scoped
`punctuation.section.block.begin` / `.end`.

## Customising the colors

If your color scheme does not distinguish some of the groups above, add
rules for the scopes listed there to your color scheme
(*Preferences / Customize Color Scheme*). To find out the scope under the
caret, press <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>P</kbd>.

## See also

`../pycharm_file_type.txt` - the equivalent (much simpler) setup for PyCharm.
