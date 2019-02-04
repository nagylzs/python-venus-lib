"""The observable/observer pattern.

Sightly modified version of Michael Kent's observer.

See: http://radio-weblogs.com/0124960/2004/06/15.html

Changes:

#   Remove the "Observer" class

    Formally, you must use addObserver and removeObserver.

    Reasons:

    a.) "There should be only one obvious way to do it."
        http://www.python.org/dev/peps/pep-0020/

        The original code had two ways to do it.

    b.) The observer-observable model is often used to hide implementation details, remove dependencies between
        modules, separate application levels. Any object should be able to observe any observable. The observable should
        be fully functional without knowing anything about its observers. Formally, if we require observers to have a
        given subclass, we assume some property of the observer (its base class), which we should not do.

    Example:

    l = wx.ListCtrl(parent,-1)
    observable.addObserver(l,"ClearAll","emptied")
    observable.notifyObservers("emptied")

    It is much easier to use existing class hierarchy. In this example, you do not really want to subclass each
    wx.* class, create your own "ObserverListCtrl" and "ObserverCheckBox" etc.

#   Add positional and keywords arguments.

    The original signature

    notify_observers(self, event=None, msg=None)

    Is replaced with:

    notify_observers(self, event=None, *args, **kwargs)

    It is recommended to always use keyword arguments with default values (where applicable). This way event handler
    methods with different signatures will be able to receive the same (or different) events. This also removes
    assumed knowledge on the observable's part. (The observable does not really need to know the signatures of its
    observers, in fact ideally it should know nothing about its observers...)

# Added support for using different methods for different events, with the same observer. The original code could
only handle one type of event per observer. The new code is able to call different handlers depending on the type of
the event.

"""
import weakref

import collections

import venus.i18n

_ = venus.i18n.get_my_translator(__file__)

MIN_EVT_ID = 1000
_evt_seq = MIN_EVT_ID


def new_event_id():
    """Creates a new event identifier.

    Use this function to create event identifiers. Do not use constant
    values, if it can be avoided.
    """
    global _evt_seq
    _evt_seq += 1
    return _evt_seq


class Observable:
    """Implements the observer-observable pattern."""

    def __init__(self, *args, **kwargs):
        self._observers = weakref.WeakKeyDictionary()
        self._wildcard_observers = weakref.WeakKeyDictionary()
        self._events = {}
        super().__init__(*args, **kwargs)

    def add_observer(self, observer, cbname, *events):
        """Add an observer for the given event(s).

        :param observer: The observer object.
        :param cbname: Name of the method of the observer objects to be called when the event fires.
        :param events: A list of events. By not giving any event, you may create a wildcard observer that
                listens for everything.

        Please note that one observer can register at most on of its methods for observing. Subsequent add_observer()
        calls will overwrite the previously given handlers.

        The only one exception is when you listen to the 'None' event. This is a wildcard and will match any and all
        events. It will always be called.

        """
        if events:
            if observer in self._observers:
                handlers = self._observers[observer]
            else:
                handlers = self._observers[observer] = {}
            for event in events:
                handlers[event] = cbname
                if event not in self._events:
                    self._events[event] = weakref.WeakSet()
                    self._events[event].add(observer)
        else:
            self._wildcard_observers[observer] = cbname

    def remove_wildcard_observer(self, observer):
        """Remove wildcard observer.

        A wildcard observer listens for any event.
        """
        if observer in self._wildcard_observers:
            del self._wildcard_observers[observer]
            return True

    def remove_observer(self, observer, *events):
        """Remove observer for the given event(s).

        :param observer: Observer to be removed.
        :param events: A list of events. If you do not give any event, then all events will be removed.

        Please note that you cannot remove a wildcard observer with this method. To remove a wildcard observer,
        call remove_wildcard_observer().
        """
        if observer in self._observers:
            if events:
                handlers = self._observers[observer]
                for event in events:
                    if event in handlers:
                        del handlers[event]
                        if event in self._events:
                            self._events[event].remove(observer)
                # If there are no event handlers left, remove the observer.
                if not handlers:
                    del self._observers[observer]
            else:
                del self._observers[observer]

    def notify_observers(self, event=None, *args, **kwargs):
        """Notify all observers about an event.

        :param event: The event. Should be a hashable value. By using an event value of None, you can notify the
            wildcard observers, but not the others.

        You can pass additional positional and keywords arguments. These arguments will be passed to the event
        handler(s) of the observer(s) that are listening for the given event.
        """
        if event in self._events:
            # We iterate over a copy of observers, because observer list may change while we send notifications.
            # E.g. the called event handler is able to add/remove observers
            observers = [observer for observer in self._events[event]]
            for observer in observers:
                handlers = self._observers[observer]
                cbname = handlers[event]
                cb = getattr(observer, cbname, None)
                if cb is None:
                    raise NotImplementedError(_("Observer has no %s method.") % cbname)
                cb(self, event, *args, **kwargs)
        # Wildcard
        for observer in self._wildcard_observers:
            cbname = self._wildcard_observers[observer]
            cb = getattr(observer, cbname, None)
            if cb is None:
                raise NotImplementedError(_("Wildcard observer has no %s method.") % cbname)
            cb(self, event, *args, **kwargs)

    def observed_events(self):
        """Generator over observed events.

        Please note that None will not be listed, even if there is a wildcard observer."""
        for event in self._events:
            yield event

    def is_observed(self):
        """Tells if the observable has any (normal or wildcard) observers."""
        # These are weak references, so we have to find a non-empty one.
        for _ in self._observers:
            return True
        for _ in self._wildcard_observers:
            return True

