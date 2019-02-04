import codecs
import re
import sys


def warn(s):
    sys.stderr.write(s)
    sys.stderr.flush()


class CfgParserError(Exception):
    pass


_name_pat = re.compile("[a-z][a-z0-9]*", re.UNICODE)


class CfgParser:
    """Important note: parser related methods and attributes are capitalized.

    You can access (get and set) actual configuration values using
    lower case letters.

    @param ancestor: use this parameter to specify default config values on the same level. E.g. you can merge
        two different config files by giving an ancestor. If the actual config file does not have a value
        for a given key, then its ancestor will be queried.

    """

    def __init__(self, ancestor=None):
        self.Values = {}
        self.Ancestor = ancestor
        self.Fpaths = []
        self.Fpath = None
        self.Lineno = -1

    def __str__(self):
        return "CfgParser(%s)" % self.Fpaths

    def ParseFile(self, fpath, encoding="UTF-8"):
        """Note: we use capital letters here so that we do not collide with keys."""
        self.Fpath = fpath
        self.Fpaths.append(fpath)
        try:
            fin = codecs.open(fpath, "r", encoding=encoding)
            self.Lineno = 0
            for line in fin:
                self.Lineno += 1
                if line.strip() and not line.strip().startswith("#"):
                    pos = line.strip().find("=")
                    if pos < 0:
                        raise CfgParserError("%s: invalid syntax at line %d" % (
                            fpath, self.Lineno))
                    key = line[:pos].strip()
                    value = line[pos + 1:].strip()  # remove \n ???
                    if not key:
                        raise CfgParserError("%s: empty key at line %d" % (
                            fpath, self.Lineno))
                    names = key.split('.')
                    self.SetValue(names, value)
        finally:
            self.Lineno = -1
        return self

    def SetValue(self, names, value):
        if isinstance(names, str):
            self.SetValue(names.split("."), value)
        else:
            key = []
            for name in names:
                key.append(self.CheckName(name))
            key = tuple(key)
            self.Values[key] = self.CheckValue(value)

    def GetValue(self, names):
        if isinstance(names, str):
            return self.GetValue(names.split("."))
        else:
            key = tuple(names)
            if key in self.Values:
                return self.Values[key]
            elif self.Ancestor:
                return self.Ancestor.GetValue(key)
            else:
                raise AttributeError("no such config key: %s" % ".".join(key))

    def CheckName(self, name):
        global _name_pat
        if name == "value":
            raise CfgParserError("%s: reserved key 'value' at line %d" % (
                self.Fpath, self.Lineno))
        if not _name_pat.match(name):
            raise CfgParserError("%s: invalid key at line %d" % (
                self.Fpath, self.Lineno))
        return str(name)

    def CheckValue(self, value):
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    def __getattr__(self, key):
        return CfgResolver(self, [key])


class CfgResolver:
    """Resolver allows attribute-style access."""

    def __init__(self, cfgparser, namepath):
        self._cfgparser = cfgparser
        self._namepath = tuple(namepath)

    def __getattr__(self, name):
        if name == "value":
            return self.GetValue()
        else:
            return CfgResolver(self._cfgparser, list(self._namepath) + [name])

    def __setattr__(self, name, value):
        if name in ["_cfgparser", "_namepath"]:
            self.__dict__[name] = value
        elif name == "value":
            self.SetValue(value)
        else:
            raise AttributeError("Cannot set any attribute except 'value'.")

    def GetValue(self):
        return self._cfgparser.GetValue(self._namepath)

    def SetValue(self, value):
        self._cfgparser.SetValue(self._namepath, value)
