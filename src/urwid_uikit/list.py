"""Widgets containing lists of various things."""

from typing import Iterator, Optional
from urwid import AttrMap, ListBox, SimpleFocusListWalker, Widget

from .mixins import ObjectContainerMixin

__all__ = ("List", "ObjectList")


class List(ListBox):
    """List box that shows a list of widgets and has a single focused
    widget that is displayed differently.
    """

    def __init__(self):
        """Constructor."""
        super().__init__(SimpleFocusListWalker([]))

    def add_widget(self, widget: Widget, index: Optional[int] = None) -> None:
        """Adds a new widget to the list box.

        Parameters:
            widget: the widget to add
            index: the insertion index; ``None`` means the end of the list
        """
        # Wrap the widget in an AttrMap before it actually gets inserted
        wrapped_widget = AttrMap(widget, "", "list focus")

        # Do the insertion
        if index is None:
            self.body.append(wrapped_widget)
        else:
            self.body.insert(index, wrapped_widget)
        self._invalidate()

    @property
    def focused_widget(self) -> Optional[Widget]:
        """Returns the focused widget of the list.

        Returns:
            urwid.Widget: the focused widget
        """
        focused_widget, _ = self.get_focus()
        if hasattr(focused_widget, "base_widget"):
            focused_widget = focused_widget.base_widget  # type: ignore
        return focused_widget

    def iterwidgets(self) -> Iterator[Widget]:
        """Iterates over all the widgets objects in the list."""
        for existing_widget in self.body:
            # Contrary to what the urwid.AttrMap documentation says, AttrMap
            # objects do not forward properties transparently to the wrapped
            # widgets, so we need the base_widget property here (which is
            # the identity function for non-decoration widgets)
            yield existing_widget.base_widget

    def refresh(self) -> None:
        """Refreshes all the widgets in the list."""
        for widget in self.iterwidgets():
            if hasattr(widget, "refresh"):
                widget.refresh()

    def remove_widget(self, widget: Widget) -> None:
        """Removes the given widget from the list box.

        Parameters:
            widget: the widget to remove
        """
        removal_index = None
        for index, existing_widget in enumerate(self.iterwidgets()):
            if existing_widget is widget:
                removal_index = index
                break

        if removal_index is not None:
            self.remove_widget_at(removal_index)

    def remove_widget_at(self, index: int) -> None:
        """Removes the widget with the given index from the list box.

        Parameters:
            index: the index of the widget to remove
        """
        self.body.pop(index)


class ObjectList(List, ObjectContainerMixin):
    """List box that shows a list of widgets such that each widget is
    associated to a unique object, and the order of the widgets in the list
    is determined by a function that derives a comparable key from each
    unique object in the list.

    This is an abstract base class. Derived classes must override at least
    ``_create_widget_for_item()``.
    """

    def __init__(self):
        """Constructor."""
        super().__init__()
        ObjectContainerMixin.__init__(self)
