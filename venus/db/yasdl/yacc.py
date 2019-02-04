import ply.yacc as yacc

import venus.i18n
from venus.db.yasdl import ast
from venus.db.yasdl import lex

_ = venus.i18n.get_my_translator(__file__)

tokens = lex.tokens


class YASDLParseError(Exception):
    # TODO: add support for column numbers?
    def __init__(self, filepath, lineno, colno, message):
        self.filepath = filepath
        self.lineno = lineno
        self.colno = colno
        self.message = message

    def gnu_format(self):
        """Format the parser error message according to GNU standards."""
        # http://www.gnu.org/prep/standards/standards.html#Errors
        return '"%s":%s:%s:%s' % (
            self.filepath, self.lineno, self.colno, self.message, )

    def python_format(self):
        """Format the őarser error message as a Python error.

        This maybe useful in some IDEs so that they can generate navigational messages."""
        line = lex.get_line_by_lineno(self.lineno)
        caret = " "*self.colno + "^"
        return 'File "%s", line %s in column %s:\n%s\n%s\n    YASDLParseError: %s' % (
            self.filepath, self.lineno, self.colno, line, caret, self.message, )


def p_dotted_name_absolute_1(p):
    r"""dotted_name : SCHEMA DOT simple_dotted_name"""
    p[0] = p[3]
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))
    p[0].absolute = True


def p_dotted_name_simple_dotted_name(p):
    r"""dotted_name : simple_dotted_name"""
    p[0] = p[1]


def p_dotted_name_dotted_name(p):
    r"""simple_dotted_name : NAME DOT simple_dotted_name"""
    p[0] = ast.dotted_name(p[1] + "." + p[3])
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))
    p[0].min_classes = p[3].min_classes
    p[0].absolute = False


def p_dotted_name_name(p):
    r"""simple_dotted_name : NAME min_classes"""
    p[0] = ast.dotted_name(p[1])
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))
    if p[2]:
        p[0].min_classes = set(p[2])
    else:
        p[0].min_classes = None
    p[0].absolute = False


def p_min_classes_empty(p):
    r"""min_classes : """
    p[0] = None


def p_min_classes_items(p):
    r"""min_classes : LBRACKET minclassitems RBRACKET """
    p[0] = p[2]


def p_minclassitems_item(p):
    r"""minclassitems : minclassitem minclassitems """
    p[0] = [p[1]] + p[2]


def p_minclassitems_single(p):
    r"""minclassitems : minclassitem """
    p[0] = [p[1]]


def p_minclassitem_schema(p):
    r"""minclassitem : SCHEMA """
    p[0] = ast.YASDLSchema


def p_minclassitem_fieldset(p):
    r"""minclassitem : FIELDSET """
    p[0] = ast.YASDLFieldSet


def p_minclassitem_field(p):
    r"""minclassitem : FIELD """
    p[0] = ast.YASDLField


def p_minclassitem_index(p):
    r"""minclassitem : INDEX """
    p[0] = ast.YASDLIndex


def p_minclassitem_property(p):
    r"""minclassitem : PROPERTY """
    p[0] = ast.YASDLProperty


def p_imp_name_eq_dotted_name(p):
    r"""imp_name : EQUALS dotted_name"""
    p[0] = p[2]
    #p[0].lineno = p[2].lineno - same object!
    p[0].imp = True


def p_imp_name_dotted_name(p):
    r"""imp_name : dotted_name"""
    p[0] = p[1]
    #p[0].lineno = p[1].lineno - same object!
    p[0].imp = False


def p_schema_simple_name(p):
    r"""schema_name : NAME"""
    p[0] = ast.dotted_name(p[1])
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))
    p[0].min_classes = None
    p[0].absolute = False


def p_schema_package_name(p):
    r"""schema_name : NAME DOT schema_name"""
    p[0] = ast.dotted_name(p[1] + "." + p[3])
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))
    p[0].min_classes = None
    p[0].absolute = False


def p_yasd(p):
    r"""yasd : SCHEMA schema_name LBRACE uses defs RBRACE """
    p[0] = ast.YASDLSchema(p[2], p[4], p[5])
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))


def p_uses(p):
    r"""uses : use uses """
    p[0] = p[1] + p[2]


def p_uses_use(p):
    r"""uses : use """
    p[0] = p[1]


def p_use_as(p):
    r"""use : USE schema_name AS NAME SEMICOLON
            | REQUIRE schema_name AS NAME SEMICOLON
            | USE STRING AS NAME SEMICOLON
            | REQUIRE STRING AS NAME SEMICOLON
            """
    use = ast.YASDLUse(p[2], p[4])
    if p[1] == 'require':
        use.modifiers.append('required')
    use.lineno = p.lineno(1)
    use.colno = lex.find_column_by_lexpos(p.lexpos(1))
    p[0] = [use]


def p_use(p):
    r"""use : USE NAME SEMICOLON
            | REQUIRE NAME SEMICOLON"""
    use = ast.YASDLUse(p[2])
    if p[1] == 'require':
        use.modifiers.append('required')
    use.lineno = p.lineno(1)
    use.colno = lex.find_column_by_lexpos(p.lexpos(1))
    p[0] = [use]


def p_use_empty(p):
    r"""use : """
    p[0] = []


def p_modifiers_modifiers(p):
    r"""modifiers : modifier modifiers"""
    p[0] = p[1] + p[2]


def p_modifiers_modifier(p):
    r"""modifiers : modifier"""
    p[0] = p[1]


def p_modifier_empty(p):
    r"""modifier : """
    p[0] = []


def p_modifier(p):
    r"""modifier : ABSTRACT
                 | FINAL
                 | REQUIRED"""
    p[0] = [p[1]]


def p_defs(p):
    r"""defs : def defs """
    p[0] = [p[1]] + p[2]


def p_defs_def(p):
    r"""defs : def """
    p[0] = [p[1]]


def p_def(p):
    r"""def : fielddef
            | fieldsetdef
            | simpleprop
    """
    p[0] = p[1]
    p[0].lineno = p[1].lineno
    # This is a real hack - need colum position of a symbol instead of a token.
    p[0].colno = p.slice[1].value.colno


def p_defs_empty(p):
    r"""defs : """
    p[0] = []


def p_fielddef_simple(p):
    r"""fielddef : modifiers FIELD NAME typedef fieldprops"""
    items = p[5]
    if p[4]:
        ancprop = ast.YASDLProperty('ancestors', p[4])
        ancprop.lineno = p.lineno(2)
        ancprop.colno = lex.find_column_by_lexpos(p.lexpos(2))
        items.append(ancprop)
    f = p[0] = ast.YASDLField(p[3], items)
    f.lineno = p.lineno(2)
    f.colno = lex.find_column_by_lexpos(p.lexpos(2))
    f.modifiers[:] = p[1]


def p_fielddef_ref(p):
    r"""fielddef : modifiers FIELD NAME typedef ARROW imp_name fieldprops"""
    items = p[7]
    if p[4]:
        ancprop = ast.YASDLProperty('ancestors', p[4])
        ancprop.lineno = p.lineno(2)
        ancprop.colno = lex.find_column_by_lexpos(p.lexpos(2))
        items.append(ancprop)
    if p[6]:
        refprop = ast.YASDLProperty('references', [p[6]])
        refprop.lineno = p[6].lineno
        # This is a real hack - need colum position of a symbol instead of a token.
        refprop.colno = p.slice[6].value.colno
        #refprop.colno = lex.find_column_by_lexpos(p.lexpos(6))
        items.append(refprop)
    p[0] = ast.YASDLField(p[3], items)  # Add identifier type here???
    p[0].lineno = p.lineno(2)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(2))
    p[0].modifiers[:] = p[1]


def p_fieldprops_empty(p):
    r"""fieldprops : SEMICOLON"""
    p[0] = []


def p_fieldprops(p):
    r"""fieldprops : LBRACE simpleprops RBRACE """
    p[0] = p[2]


def p_fieldsetdef_simple(p):
    r"""fieldsetdef : modifiers FIELDSET NAME typedef SEMICOLON"""
    items = []
    if p[4]:
        ancprop = ast.YASDLProperty('ancestors', p[4])
        ancprop.lineno = p.lineno(2)
        ancprop.colno = lex.find_column_by_lexpos(p.lexpos(2))
        items.append(ancprop)
    fs = p[0] = ast.YASDLFieldSet(p[3], items)
    fs.lineno = p.lineno(2)
    fs.colno = lex.find_column_by_lexpos(p.lexpos(2))
    fs.modifiers[:] = p[1]


def p_fieldsetdef_complex(p):
    r"""fieldsetdef : modifiers FIELDSET NAME typedef LBRACE fsitems RBRACE """
    items = p[6]
    if p[4]:
        ancprop = ast.YASDLProperty('ancestors', p[4])
        ancprop.lineno = p.lineno(2)
        ancprop.colno = lex.find_column_by_lexpos(p.lexpos(2))
        items.append(ancprop)
    p[0] = ast.YASDLFieldSet(p[3], items)
    p[0].lineno = p.lineno(2)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(2))
    p[0].modifiers[:] = p[1]


def p_fsitems_many(p):
    r"""fsitems : fsitem fsitems """
    p[0] = [p[1]] + p[2]


def p_fsitems_one(p):
    r"""fsitems : fsitem """
    p[0] = [p[1]]


def p_fsitem_simpleprop(p):
    r"""fsitem : simpleprop """
    p[0] = p[1]


def p_fsitem_defs(p):
    r"""fsitem : fielddef
               | fieldsetdef
               | indexdef """
    p[0] = p[1]


def p_fsitem_deletion(p):
    r"""fsitem : deletion"""
    p[0] = p[1]


def p_deletion(p):
    r"""deletion : DELETE NAME SEMICOLON"""
    p[0] = ast.YASDLDeletion(p[2])
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))


def p_indexdef(p):
    r"""indexdef : INDEX NAME LBRACE idxitems RBRACE """
    items = p[4]
    p[0] = ast.YASDLIndex(p[2], items)
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))


def p_idxitems_many(p):
    r"""idxitems : idxitem idxitems """
    p[0] = [p[1]] + p[2]


def p_idxitems_one(p):
    r"""idxitems : idxitem """
    p[0] = [p[1]]


def p_idxitem_simpleprop(p):
    r"""idxitem : simpleprop """
    p[0] = p[1]


def p_constraintdef(p):
    r"""indexdef : CONSTRAINT NAME LBRACE constraintitems RBRACE """
    items = p[4]
    p[0] = ast.YASDLConstraint(p[2], items)
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))


def p_constraintitems_many(p):
    r"""constraintitems : constraintitem constraintitems """
    p[0] = [p[1]] + p[2]


def p_constraintitems_one(p):
    r"""constraintitems : constraintitem """
    p[0] = [p[1]]


# At least one item is required
#def p_constraintitems_empty(p):
#    r"""constraintitems : """
#    p[0] = []

def p_constraintitem_simpleprop(p):
    r"""constraintitem : simpleprop """
    p[0] = p[1]

def p_typedef(p):
    r"""typedef : COLON typedef_items """
    p[0] = p[2]


def p_typedef_empty(p):
    r"""typedef : """
    p[0] = None


def p_typedef_items_many(p):
    r"""typedef_items : imp_name typedef_items """
    p[0] = [p[1]] + p[2]


def p_typedef_items_one(p):
    r"""typedef_items : imp_name """
    p[0] = [p[1]]


def p_indexdef_simple(p):
    r"""indexdef : INDEX NAME indexprops"""
    items = p[3]
    i = p[0] = ast.YASDLIndex(p[2], items)
    i.lineno = p.lineno(1)
    i.colno = lex.find_column_by_lexpos(p.lexpos(1))


# indexprops cannot be empty, it must have fields listed!
#def p_indexprops_empty(p):
#    r"""indexprops : SEMICOLON"""
#    p[0] = []


def p_indexprops(p):
    r"""indexprops : LBRACE simpleprops RBRACE """
    p[0] = p[2]


def p_simpleprops_many(p):
    r"""simpleprops : simpleprop simpleprops"""
    p[0] = [p[1]] + p[2]


def p_simpleprops_one(p):
    r"""simpleprops : simpleprop """
    p[0] = [p[1]]


def p_simpleprops_empty(p):
    r"""simpleprops : """
    p[0] = []


def p_simpleprop_one(p):
    r"""simpleprop : NAME propvalues SEMICOLON"""
    p[0] = ast.YASDLProperty(p[1], p[2])
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))


def p_simpleprop_fields(p):
    r"""simpleprop : FIELDS idxfields SEMICOLON"""
    p[0] = ast.YASDLProperty(p[1], p[2])
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))


def p_idxfields_many(p):
    r"""idxfields : idxfield idxfields"""
    p[0] = [p[1]] + p[2]


def p_idxfields_one(p):
    r"""idxfields : idxfield"""
    p[0] = [p[1]]


def p_idxfield_asc(p):
    r"""idxfield : PLUS dotted_name"""
    p[0] = p[2]
    p[0].direction = "asc"
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))


def p_idxfield_desc(p):
    r"""idxfield : MINUS dotted_name"""
    p[0] = p[2]
    p[0].direction = "desc"
    p[0].lineno = p.lineno(1)
    p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))


def p_idxfield_simple(p):
    r"""idxfield : dotted_name"""
    p[0] = p[1]
    p[0].direction = "asc"
    p[0].lineno = p.lineno(1)
    # This is a real hack - need colum position of a symbol instead of a token.
    p[0].colno = p.slice[1].value.colno
    #p[0].colno = lex.find_column_by_lexpos(p.lexpos(1))

def p_propvalues_many(p):
    r"""propvalues : propvalue propvalues"""
    p[0] = [p[1]] + p[2]


def p_propvalues_one(p):
    r"""propvalues : propvalue """
    p[0] = [p[1]]


def p_propvalues_empty(p):
    r"""propvalues : """
    p[0] = []


def p_propvalue_float(p):
    r"""propvalue : FLOAT"""
    # TODO: How to determine lineno and colno here?
    p[0] = float(p[1])


def p_propvalue_int(p):
    r"""propvalue : INT"""
    # TODO: How to determine lineno and colno here?
    p[0] = int(p[1])


def p_propvalue_none(p):
    r"""propvalue : NONE"""
    # TODO: How to determine lineno and colno here?
    p[0] = None

def p_propvalue_all(p):
    r"""propvalue : ALL"""
    # TODO: How to determine lineno and colno here?
    p[0] = ast.YASDLAll()

def p_propvalue_string(p):
    r"""propvalue : STRING"""
    # TODO: How to determine lineno and colno here?
    p[0] = p[1]


def p_propvalue_true(p):
    r"""propvalue : TRUE"""
    # TODO: How to determine lineno and colno here?
    p[0] = True


def p_propvalue_false(p):
    r"""propvalue : FALSE"""
    # TODO: How to determine lineno and colno here?
    p[0] = False


def p_propvalue_imp_name(p):
    r"""propvalue : imp_name"""
    p[0] = p[1]


# Error rule for syntax errors
def p_error(p):
    colno = lex.find_column(p)
    # Ugly!
    raise YASDLParseError(lex._src, p.lineno, colno, _("Syntax error"))


# build the parser
yacc.yacc(start='yasd', debug=0)
