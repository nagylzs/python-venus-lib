import re

import ply.lex as lex

import venus.i18n

_ = venus.i18n.get_my_translator(__file__)

tokens = (
    'NAME', 'DOT', 'EQUALS', 'MINUS', 'PLUS',
    'STRING', 'FLOAT', 'INT', 'NONE', 'TRUE', 'FALSE', 'ALL',
    'COLON', 'SEMICOLON', 'ARROW',
    'LBRACE', 'RBRACE',
    'LBRACKET', 'RBRACKET',
    'SCHEMA', 'FIELDSET', 'FIELD', 'INDEX', 'PROPERTY',
    'FINAL', 'ABSTRACT', 'REQUIRED',
    'USE', 'REQUIRE', 'AS',
    'DELETE',
    'FIELDS',
    'CONSTRAINT',
    # 'references,ancestors and implements are NOT tokens!
    # They are names of special properties.
    # See RESERVED_PROPERTY_NAMES below.
)

reserved = {
    'none': 'NONE',
    'true': 'TRUE',
    'false': 'FALSE',
    'all': 'ALL',
    'schema': 'SCHEMA',
    'fieldset': 'FIELDSET',
    'field': 'FIELD',
    'index': 'INDEX',
    'constraint': 'CONSTRAINT',
    'use': 'USE',
    'require': 'REQUIRE',
    'as': 'AS',
    'final': 'FINAL',
    'abstract': 'ABSTRACT',
    'required': 'REQUIRED',
    'rename': 'RENAME',
    'delete': 'DELETE',
    'fields': 'FIELDS',
}
# noinspection PySingleQuotedDocstring

# Note: "fields" is special because it is a property name,
# but on the source code it is represented with a keyword.
RESERVED_PROPERTY_NAMES = ['ancestors', 'implements', 'references',
                           'unique', 'delindexes', 'fields', 'cluster']


def t_comment(t):
    r"\#[^\n]*\n"
    t.lexer.lineno += 1
    # We do not return anything - comments are ignored.


# Define a rule so we can track line numbers
def t_newline(t):
    r'\n+'
    t.lexer.lineno += len(t.value)


def t_string_tquoted(t):
    r"\'\'\'.*?\'\'\'"
    # t.value = value = ast.token_str(t.value[3:-3])
    # value.lineno = t.lexer.lineno
    # value.colno = find_column(t)
    # Hack: cannot set owner_schema right now, but will set it later in yacc.
    t.value = t.value[3:-3]
    t.type = 'STRING'
    return t


def t_string_tfquoted(t):
    r'\"\"\".*?\"\"\"'
    # t.value = value = ast.token_str(t.value[3:-3])
    # value.lineno = t.lexer.lineno
    # value.colno = find_column(t)
    # Hack: cannot set owner_schema right now, but will set it later in yacc.
    t.value = t.value[3:-3]
    t.type = 'STRING'
    return t


def t_string_quoted(t):
    r"\'([^\'\\]|(\\.))*\'"
    # t.value = value = ast.token_str(eval(t.value))
    # value.lineno = t.lexer.lineno
    # value.colno = find_column(t)
    # Hack: cannot set owner_schema right now, but will set it later in yacc.
    t.value = eval(t.value)
    t.type = 'STRING'
    return t


def t_string_dquoted(t):
    r'\"([^\"\\]|(\\.))*\"'
    # t.value = value = ast.token_str(eval(t.value))
    # value.lineno = t.lexer.lineno
    # value.colno = find_column(t)
    # Hack: cannot set owner_schema right now, but will set it later in yacc.
    t.value = eval(t.value)
    t.type = 'STRING'
    return t


def t_name(t):
    r'[a-zA-Z_][a-zA-Z_0-9]*'
    t.value = t.value.lower()
    if t.value in reserved:
        t.type = reserved[t.value]
    else:
        t.type = 'NAME'
    return t


t_FLOAT = r'[\+-]?((((\d*\.\d+)|(\d+\.\d*))' + \
          r'([Ee][\+-]?\d+)?)|(\d+[Ee][\+-]?\d+))'
t_INT = r'([\+-]?\d+)'
t_NONE = r'[Nn][Oo][Nn][Ee]'
t_TRUE = r'[Tt][Rr][Uu][Ee]'
t_FALSE = r'[Ff][Aa][Ll][Ss][Ee]'
t_ALL = r'[Aa][Ll][Ll]'


# Whitespace is mostly ignored, except inside quoted words.
def t_ws(t):
    r'[\r\t ]+'
    # We do not return anything so this will be ignored.


t_DOT = r'\.'
t_COLON = r'\:'
t_EQUALS = r'\='
t_SEMICOLON = r'\;'
t_ARROW = r'\-\>'
t_LBRACE = r'\{'
t_RBRACE = r'\}'
t_LBRACKET = r'\['
t_RBRACKET = r'\]'
t_MINUS = r"\-"
t_PLUS = r"\+"


class YASDLLexerError(Exception):
    def __init__(self, filepath, lineno, colno, message):
        self.filepath = filepath
        self.lineno = lineno
        self.colno = colno
        self.message = message

    def gnu_format(self):
        """Format the lexer error message according to GNU standards."""
        # http://www.gnu.org/prep/standards/standards.html#Errors
        return '"%s":%s:%s:%s' % (
            self.filepath, self.lineno, self.colno, self.message,)

    def python_format(self):
        """Format the lexer error message as a Python error.

        This maybe useful in some IDEs so that they can generate navigational messages."""
        line = get_line_by_lineno(self.lineno)
        caret = " " * self.colno + "^"
        return 'File "%s", line %s in column %s:\n%s\n%s\n    YASDLLexerError: %s' % (
            self.filepath, self.lineno, self.colno, line, caret, self.message,)


# TODO: how to make this thread-safe???
_src = None
_data = None


def lexer_init(src, data):
    """You need to call this before you call yacc.yacc.

    Why: because this is the only way to raise a proper exception that
    contains the location of the error. (???)"""
    global _src
    global _data
    global lexer
    _src = src
    _data = data
    lexer.lineno = 1


# Error handling rule
def t_error(t):
    global _src
    colno = find_column(t)
    raise YASDLLexerError(_src, t.lineno, colno,
                          _("Illegal character: %s") % repr(t.value[0]))


def find_column(token):
    """This function tells the column number for a token."""
    return find_column_by_lexpos(token.lexpos)


def find_column_by_lexpos(lexpos):
    """This function tells the column number for a lex position."""
    global _data
    # i = lexpos
    # while i > 0:
    #    if _data[i] == '\n':
    #        break
    #    i -= 1
    # return (lexpos - i)
    last_cr = _data.rfind('\n', 0, lexpos) + 1
    return (lexpos - last_cr)


def get_line_by_lineno(lineno):
    """Get the given line.

    :param lineno: Line number of input. Indexing starts from 1.
    :return: the line

    This method can only be used for the currently tokenized file!
    """
    global _data
    return _data.split("\n")[lineno - 1]


def get_line_for_token(token):
    """Returns the line in which the token can be found.

    :param token: The token.
    :return: The input line where the token is located.

    .. note::

        If you want to display a caret that shows the token in the line, then you need to replace tabs
        by spaces manually. One horizontal tab character may be replaced with 4 spaces.
    """
    global _data
    last_cr = _data.rfind('\n', 0, token.lexpos)
    if last_cr < 0:
        last_cr = 0
    next_cr = _data.rfind('\n', last_cr)
    if next_cr < 0:
        return _data[last_cr:]
    else:
        return _data[last_cr:next_cr - 1]


def dump(src, data):
    """This function dumps the token list."""
    lexer_init(src, data)
    lex.input(data)
    print("TOKENS:")
    while 1:
        tok = lex.token()
        # No more input
        if not tok:
            break
        print("    ", tok.type, repr(tok.value),
              ' at position [%d:%d]' % (tok.lineno, find_column(tok)))


lexer = lex.lex(reflags=re.UNICODE)
