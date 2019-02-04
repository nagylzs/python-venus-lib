"""Observable collections"""
from contextlib import contextmanager
from venus.misc.observable import Observable, new_event_id

EVT_BEFORE_COLLECTION_CHANGED = new_event_id()
EVT_AFTER_COLLECTION_CHANGED = new_event_id()


def wrap_notify(*names):
    def wrap_methods(cls):
        for name in names:
            method = wrap_method(getattr(cls, name), name)
            setattr(cls, name, method)
        return cls
    return wrap_methods


def wrap_method(method, name):
    def wrapped_method(self, *args, **kw):
        with self.notify():
            return method(self, *args, **kw)
    return wrapped_method


class ObservableCollection(Observable):
    @contextmanager
    def notify(self):
        self.notify_observers(EVT_BEFORE_COLLECTION_CHANGED)
        yield
        self.notify_observers(EVT_AFTER_COLLECTION_CHANGED)


@wrap_notify('remove', 'clear', 'append', 'extend', 'insert', 'sort', 'reverse', 'pop', '__delitem__',
             '__add__', '__iadd__', '__mul__', '__imul__', '__rmul__', '__setitem__')
class ObservableList(ObservableCollection, list):
    __slots__ = []


@wrap_notify('pop', 'popitem', 'setdefault', 'update', '__delitem__', '__setitem__')
class ObservableDict(ObservableCollection, dict):
    __slots__ = []

@wrap_notify('__iand__', '__ior__', '__isub__', '__ixor__', '__rand__', '__ror__', '__rsub__', '__rxor__',
             'add', 'clear', 'difference_update', 'discard', 'intersection_update', 'pop', 'remove',
             'symmetric_difference_update')
class ObservableSet(ObservableCollection, set):
    __slots__ = []

