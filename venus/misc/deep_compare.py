"""Compare data structures deeply.

Scalars: basestring, float, complex, None, int
Structs: list,tuple,dict

Main method is diff(o1,o2).

Cannot be used on recursive structures!

TODO: add support for sets.
"""
import math
import datetime


def is_number(o):
    return isinstance(o, float) or isinstance(o, int)


def is_date_related(o):
    return isinstance(o, datetime.datetime) or \
           isinstance(o, datetime.date) or \
           isinstance(o, datetime.time) or \
           isinstance(o, datetime.timedelta)


def is_scalar(o):
    return (o is None) or isinstance(o, str) or isinstance(o, bytes) or \
           is_number(o) or isinstance(o, complex) or is_date_related(o)


def is_struct(o):
    return isinstance(o, list) or isinstance(o, tuple) or isinstance(o, dict)


def diff(o1, o2):
    """Compare two objects, return differences.

    If both are scalars, returns True (different)/False (not different).
    If both are structs, returns diff_struct(o1,o2)
    Otherwise returns True (different).
    """
    if o1 is o2:
        return False

    scalar1, struct1 = is_scalar(o1), is_struct(o1)
    scalar2, struct2 = is_scalar(o2), is_struct(o2)
    if scalar1 and scalar1:
        # return difference_scalars(o1,o2) ???
        return diff_scalar(o1, o2)
    elif struct1 and struct2:
        return diff_struct(o1, o2)
    else:
        return True


def diff_scalar(o1, o2, eps=1e-6):
    """Almost like the != operator.

    The only difference is that if one object is a float and the other is
    float, int then both are converted to floats and if their
    abs difference is less than eps, then False is returned.

    Please note that in the current implementation, date related values
    are considered scalars. This might change in the future, and we
    might implement a diff_date_related function instead.
    """
    if o1 is o2:
        return False

    compare_floats = False
    if isinstance(o1, float) or isinstance(o2, float):
        if is_number(o1) and is_number(o2):
            compare_floats = True

    if compare_floats:
        absdiff = math.fabs(o1 - o2)
        return absdiff > eps
    else:
        return o1 != o2


def diff_struct(o1, o2):
    """Return difference of structs.

    If their type differs, returns (o1,o2) (old value/new value)
    If they are lists, returns diff_seqs(o1,o2)
    If they are tuples, returns diff_seqs(o1,o2)
    If they are dicts, returns diff_dicts(o1,o2)
    """
    if o1 is o2:
        return False

    if type(o1) != type(o2):
        return True

    if isinstance(o1, list):
        return diff_seqs(o1, o2)
    elif isinstance(o1, tuple):
        return diff_seqs(o1, o2)
    elif isinstance(o1, dict):
        return diff_dicts(o1, o2)
    else:
        return False


def diff_seqs(o1, o2):
    """Compare sequences.

    Returns True (different) or False (not different).

    Elements are compared with diff().
    """
    if o1 is o2:
        return False
    if len(o1) != len(o2):
        return True
    for idx, e1 in enumerate(o1):
        if diff(e1, o2[idx]):
            return True
    return False


def diff_dicts(o1, o2):
    """Compare dicts.

    If o1 and o2 are different, then a tuple is returned:

    (added, updated, deleted)

    Where:

    - added is a dict
    - updated is a dict of key: (oldvalue, newvalue)
    - deleted is a set of keys

    You can get o2 from o1 by applying these changes (add,update,delete).

    If they are the same, then False is returned instead.
    """
    if o1 is o2:
        return False
    added = {}
    updated = {}
    deleted = set([])
    for key in o1:
        if key in o2:
            value1, value2 = o1[key], o2[key]
            if diff(value1, value2):
                updated[key] = (value1, value2)
                # else: pass
        else:
            deleted.add(key)
    for key in o2:
        if key not in o1:
            added[key] = o2[key]

    if added or updated or deleted:
        return added, updated, deleted
    else:
        return False


if __name__ == "__main__":
    assert (not diff(1, 1))
    assert (diff(1, 2))
    assert (not diff(1, 1.000001))
    assert (diff(-1, 1.000001))
    assert (not diff(-1, -1.000001))
    assert (diff(-1, -1.0001))

    v1 = {1: 1, 2: 2, 3: 3}
    v2 = {1: 1, 3: 4, 10: 10}
    d = diff(v1, v2)
    print
    "v1", v1
    print
    "v2", v2
    print
    "diff", diff(v1, v2)

    assert (d == ([(10, 10)], [(3, (3, 4))], [2]))

    v1 = {'dimensions': [1, 2, 3]}
    v2 = {'dimensions': [1, 2, 3]}
    d = diff(v1, v2)
    print
    "should be False:", d
