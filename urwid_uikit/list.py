"""Widgets containing lists of various things."""

from functools import cmp_to_key
from past.builtins import cmp
from urwid import AttrMap, ListBox, SimpleFocusListWalker

__all__ = ("List", "ObjectList")


class List(ListBox):
    """List box that shows a list of widgets and has a single focused
    widget that is displayed differently.
    """

    def __init__(self):
        """Constructor."""
        super(List, self).__init__(SimpleFocusListWalker([]))

    def add_widget(self, widget, index=None):
        """Adds a new widget to the list box.

        Parameters:
            widget (urwid.Widget): the widget to add
            index (Optional[int]): the insertion index; ``None`` means the
                end of the list
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
    def focused_widget(self):
        """Returns the focused widget of the list.

        Returns:
            urwid.Widget: the focused widget
        """
        focused_widget, _ = self.get_focus()
        if hasattr(focused_widget, "base_widget"):
            focused_widget = focused_widget.base_widget
        return focused_widget

    def iterwidgets(self):
        """Iterates over all the widgets objects in the list."""
        for existing_widget in self.body:
            # Contrary to what the urwid.AttrMap documentation says, AttrMap
            # objects do not forward properties transparently to the wrapped
            # widgets, so we need the base_widget property here (which is
            # the identity function for non-decoration widgets)
            yield existing_widget.base_widget

    def refresh(self):
        """Refreshes all the widgets in the list."""
        for widget in self.iterwidgets():
            if hasattr(widget, "refresh"):
                widget.refresh()

    def remove_widget(self, widget):
        """Removes the given widget from the list box.

        Parameters:
            widget (urwid.Widget): the widget to remove
        """
        removal_index = None
        for index, existing_widget in enumerate(self.iterwidgets()):
            if existing_widget is widget:
                removal_index = index
                break

        if removal_index is not None:
            self.remove_widget_at(removal_index)

    def remove_widget_at(self, index):
        """Removes the widget with the given index from the list box.

        Parameters:
            index (int): the index of the widget to remove
        """
        self.body.pop(index)


class ObjectList(List):
    """List box that shows a list of widgets such that each widget is
    associated to a unique object, and the order of the widgets in the list
    is determined by a function that derives a comparable key from each
    unique object in the list.

    This is an abstract base class. Derived classes must override at least
    ``_create_widget_for_item()``.
    """

    def __init__(self):
        """Constructor."""
        super(ObjectList, self).__init__()
        self._key_function = self._default_key_function

        self._items_by_widgets = {}
        self._widgets_by_items = {}

    def _compare_items(self, first, second):
        """Compares two items in order to determine the order in which they
        should appear in the list.

        Parameters:
            first (object): the first item
            second (object): the second item

        Returns:
            int: 0 if the two items are the same or have the same key, negative
                number if the first item should appear first, positive number
                if the second item should appear first
        """
        key_of_first = self._key_function(first)
        key_of_second = self._key_function(second)
        if key_of_first == key_of_second:
            return 0
        elif key_of_first > key_of_second:
            return 1
        else:
            return -1

    def _compare_widgets(self, first, second):
        """Compares two widgets in the list in order to determine the order
        in which they should appear in the list.

        Parameters:
            first (urwid.Widget): the first widget
            second (urwid.Widget): the second widget

        Returns:
            int: 0 if the two widgets are the same, negative number if the
                first widget should appear first, positive number if the
                second widget should appear first
        """
        first_item = self._extract_item_from_widget(first)
        second_item = self._extract_item_from_widget(second)
        return self._compare_items(first_item, second_item) or cmp(
            id(first), id(second)
        )

    def _create_and_insert_widget_for_item(self, item):
        """Creates a widget that will represent the given item and inserts it
        into the appropriate place in the list.

        Parameters:
            item (object): the item for which we want to create a widget

        Returns:
            urwid.Widget: the widget that was created for the UAV

        Throws:
            ValueError: if the item was already in the list
        """
        # Create the widget for the item and store it in the widget dict
        self._widgets_by_items[item] = widget = self._create_widget_for_item(item)
        self._items_by_widgets[widget] = item

        # TODO: UAVList uses a call to _prepare_widget() here

        # Insert the widget into the list so that the list appears sorted by
        # key
        insertion_index = self._get_insertion_index_for_item(item)
        self.add_widget(widget, insertion_index)

        # Return the widget
        return widget

    def _create_widget_for_item(self, item):
        """Creates a widget that will represent the given item.

        Must be overridden in subclasses.

        Parameters:
            item (object): the item for which we want to create a widget

        Returns:
            urwid.Widget: the widget that corresponds to the given UAV
        """
        raise NotImplementedError

    def _default_key_function(self, item):
        """Returns the key to be used shown for an item if the user did not
        override the value in the ``key_function`` property.
        """
        if hasattr(item, "id"):
            return item.id
        else:
            return id(item)

    def _get_insertion_index_for_item(self, item):
        """Given a new item that is not in the list yet, determines the
        insertion point where the item should be inserted in order to keep
        the list sorted.

        Parameters:
            item (object): the item to insert

        Returns:
            Optional[int]: the index where the item should be inserted or
                ``None`` if the item should be inserted at the end

        Throws:
            ValueError: if the item is already in the list
        """
        for index, existing_widget in enumerate(self.iterwidgets()):
            existing_item = self._extract_item_from_widget(existing_widget)
            if existing_item is item:
                raise ValueError("item is already in the list")
            if self._compare_items(existing_item, item) > 0:
                return index
        return None

    def _extract_item_from_widget(self, widget):
        """Extracts the item that a given widget in the list represents,
        given the widget. Can be overridden in subclasses if there is an
        easy way to retrieve the item from the widget.

        Parameters:
            widget (urwid.Widget): the widget to extract the item from

        Returns:
            object: the item that the widget represents
        """
        return self._items_by_widgets[widget]

    def add_item(self, item):
        """Adds the given item (or, more precisely, a widget that represents
        the item) into the list.

        The item object will be inserted in a way that keeps the list
        sorted. The operation will not add another widget for an item if the
        item is already in the list.

        Parameters:
            item (object): the item that is about to be added.

        Returns:
            urwid.Widget: the widget that corresponds to the given UAV.
        """
        return self.get_widget_for_item(item, create_if_missing=True)

    def clear(self):
        """Removes all the widgets from the list."""
        self._widgets_by_items = {}
        self.body = []

    def contains_item(self, item):
        """Returns whether the list already contains a widget for the given
        item.

        Parameters:
            item (object): the item that we are interested in

        Returns:
            bool: whether the list contains a widget for the given item
        """
        return self.get_widget_for_item(item) is not None

    def get_widget_for_item(self, item, create_if_missing=False):
        """Retrieves the widget corresponding to the given item, optionally
        creating it if it does not exist yet.

        Parameters:
            item (object): the item for which we want to retrieve or create a
                widget
            create_if_missing (bool): whether we want to create a widget if
                there is no widget for the item yet

        Returns:
            Optional[urwid.Widget]: the widget that corresponds to the given
                item, or ``None`` if the item has no widget and we haven't
                created one
        """
        widget = self._widgets_by_items.get(item)
        if widget is None and create_if_missing:
            try:
                widget = self._create_and_insert_widget_for_item(item)
            except ValueError:
                # Should not happen but we don't want to crash
                pass
        return widget

    @property
    def key_function(self):
        """Returns the function that determines the sort key that is used to
        decide the ordering of widgets.
        """
        return self._key_function

    @key_function.setter
    def key_function(self, value):
        if value == self._key_function:
            return

        self._key_function = value

        # TODO: UAVList uses a call to _prepare_widget() here

        self.update_order()

    def refresh_item(self, item, create_if_missing=False):
        """Refreshes the widget corresponding to the given item, optionally
        creating it if needed.

        This needs the widget to have a ``refresh()`` method.

        Parameters:
            item (object): the item whose widget is to be refreshed
            create_if_missing (bool): when True, the widget will be created if
                it does not exist yet
        """
        widget = self.get_widget_for_item(item, create_if_missing)
        if widget is not None and hasattr(widget, "refresh"):
            widget.refresh()

    def remove_item(self, item):
        """Removes the widget that represents the given item and returns it.

        Parameters:
            item (object): the item that is about to be removed.

        Returns:
            Optional[urwid.Widget]: the widget that corresponded to the
                item or ``None`` if there was no widget for the item in the
                list
        """
        widget = self._get_widget_for_uav(item, create_if_missing=False)
        self.remove_widget(widget)
        del self._widgets_by_items[item]
        return widget

    @property
    def selected_item(self):
        """Returns the item represented by the focused widget, or
        ``None`` if there is no selected widget.
        """
        widget = self.focus
        if widget is None:
            return None

        return self._extract_item_from_widget(widget.base_widget)

    def update_order(self):
        """Notifies the widget that the list may have to be re-sorted based
        on the shown IDs of the UAVs.
        """
        focused_widget = self.focused_widget

        widgets = sorted(self.iterwidgets(), key=cmp_to_key(self._compare_widgets))
        self.body[:] = []

        for widget in widgets:
            self.add_widget(widget)

        if focused_widget in widgets:
            self.set_focus(widgets.index(focused_widget))

        self.refresh()
