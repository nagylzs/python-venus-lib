"""Internationalization utilities."""
import os
import gettext
import locale
import warnings

current_locale, encoding = locale.getdefaultlocale()
mydir = os.path.split(__file__)[0]
topdir = os.path.abspath(os.path.join(mydir, os.pardir))
locale_path = os.path.join(topdir, "messages")


def get_translator(domain):
    """Get translator function for a given domain.

    :param domain: The domain for the translator. This will usually be a (sub)package name."""
    global locale_path
    if current_locale is None:
        warnings.warn("Current locale is undefined.")
        return lambda *args: args[0]
    try:
        t = gettext.translation(domain, locale_path, [current_locale])
    except FileNotFoundError:
        print("domain=%s, locale_path=%s" % (domain, locale_path))
        raise
    return t.gettext


def get_domain_for_path(fpath):
    """Extract message domain from module path.

    :param fpath: Path to the module, ususally given as __file__"""
    global topdir
    fpath = os.path.abspath(fpath)
    if not fpath.startswith(topdir):
        raise Exception("venus.i18n.get_domain_for_path may only be used for paths inside venus")
    return "messages"


#    relpath = fpath[len(TOPDIR+os.sep):]
#    parts = relpath.split(os.sep)
#    print(parts)
#    if parts[-1]=='__init__.py':
#        parts.pop()
#    elif parts[-1].endswith(".py"):
#        parts[-1] = parts[-1][:len(".py")]
#    return ".".join(parts)

def get_my_translator(fpath):
    """This function is used to determine the domain for the current venus module and return a translator for it.

    :param fpath: Path to the module, ususally given as __file__"""
    return get_translator(get_domain_for_path(fpath))

def _t(s):
    """A dummy translator that can be used for message extraction without actually doing the translation."""
    return s


if __name__ == "__main__":
    print(get_domain_for_path(__file__))
