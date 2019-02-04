"""Model-Viewer-Controller implementation.

See: http://en.wikipedia.org/wiki/Model%E2%80%93view%E2%80%93controller

It is a bit modified: one Controller can have many views assigned.

Should be used this way:

Initialization:

    - Create one model
    - Create one controller for the model
    - Create one or more viewers for the model & controller

Rules:

    - Model must store all state information.
    - Viewer should NEVER store any state information.
    - Controller should NEVER store any state information.
    - Model must have methods for get and set state.


    - Moldel should never subscribe to any event
    - Viewer can subscribe to model and controller events
    - Controller can subscribe to model events
        (possibly not controller events)

    - Model may send notifications to subscribers (viewers&controller)
    - Viewer should never send any notification
    - Controller may send notifications to subscribers

    - Model should never receive any notification
    - Viewer may receive notifications from model or controller
    - Controller may receive notifications from model

Information flow:

    - The model sends notifications to viewers, telling them that
        the state has been changed.
    - Viewers use model's methods to get state, for rendering.
    - Viewers send events on user interaction.
    - Controllers respond to user interaction events, and use model's
        methods to set (change) its model's state.
    - Business rules are located in the model. When setting its state,
        it checks business constraints and applies business rules.

    Question: how to prevent this problem?

        user interaction (press one characer)
        viewer notifies controller
        controller stores data into model
        state changes in data model
        model sends notification to viewer about the change
        viewer renders again (clearing cursor position)

        Then the user cannot continue typing?

        The anwser is the venus.awx.misc.VisualUpdate class.
        Visual widets should always use a VisualUpdate instance
        to maintain their own state E.g. make a difference between
        "change controls because the model changed and needs updating"
        vs. "change controls because of user interaction, model needs
        to be notified".


"""
from venus.misc.observable import Observable


class MVC:
    """Base class for model-controller-view."""
    pass


class Model(MVC, Observable):
    """Stateful object that adds meaning to raw data.

    When a model changes its state, it notifies its associated views so
    they can be refreshed."""

    def __init__(self):
        super(Model, self).__init__()


class ModelRefererMixin:
    """Mixin for classes that can reference model."""

    def mvc_getModel(self):
        return self._model

    def mvc_setModel(self, model):
        """Override to prevent changing model."""
        self._model = model
        self.mvc_modelChanged()

    def mvc_modelChanged(self):
        """Override to do something when model is changed."""
        pass

    def _mvc_getModel(self):
        """Property virtualizer"""
        return self.mvc_getModel()

    def _mvc_setModel(self, model):
        """Property virtualizer"""
        self.mvc_setModel(model)

    model = property(_mvc_getModel, _mvc_setModel,
                     doc="Change model of the viewer")


class Viewer(MVC, Observable, ModelRefererMixin):
    """Stateless object that renders the model into a form suitable for interaction.

    A viewer always has exactly one model assigned.
    Multiple views can exist for a single model for different purposes."""

    def __init__(self, model):
        super(Viewer, self).__init__()
        self.model = model


class Controller(MVC, ModelRefererMixin):
    """Controller receives input and initiates a response by making calls on model objects.

    A controller always has exactly one model assigned.
    Multiple controllers can exist for a single model for different purposes."""

    def __init__(self, model):
        super(Controller, self).__init__()
        self.model = model
        self.views = []

    def add_view(self, view):
        self.views.append(view)

    def remove_view(self, view):
        self.views.remove(view)
