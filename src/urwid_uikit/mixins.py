__all__ = ("ObjectContainerMixin",)

from functools import cmp_to_key
from urwid import emit_signal, Widget
from typing import Callable, Dict, Generic, Optional, TypeVar


def cmp(a, b):
    """Replacement of `cmp()` from Python 2.x."""
    return (a > b) - (a < b)


T = TypeVar("T")


class ObjectContainerMixin(Generic[T]):
    """Mixin class for urwid widgets that contain other widgets related to
    some business objectss such that there is a 1:1 mapping between business
    objects and widgets.
    """

    _items_by_widgets: Dict[Widget, T]
    _widgets_by_items: Dict[T, Widget]
    _key_function: Callable[[T], int]

    def __init__(self):
        """Constructor."""
        self._key_function = self._default_key_function

        self._items_by_widgets = {}
        self._widgets_by_items = {}

    def _clear_body(self) -> None:
        if hasattr(self, "body"):
            # For ListBox; maybe "contents" also works there? Need to check.
            self.body[:] = []  # type: ignore
        else:
            self.contents[:] = []  # type: ignore

    def _compare_items(self, first, second) -> int:
        """Compares two items in order to determine the order in which they
        should appear in the list.

        Parameters:
            first: the first item
            second: the second item

        Returns:
            0 if the two items are the same or have the same key, negative
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

    def _compare_widgets(self, first: Widget, second: Widget) -> int:
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

    def _create_and_insert_widget_for_item(self, item: T) -> Widget:
        """Creates a widget that will represent the given item and inserts it
        into the appropriate place in the list.

        Parameters:
            item: the item for which we want to create a widget

        Returns:
            the widget that was created for the itme

        Throws:
            ValueError: if the item was already in the list
        """
        # Create the widget for the item and store it in the widget dict
        self._widgets_by_items[item] = widget = self._create_widget_for_item(item)
        self._items_by_widgets[widget] = item
        self._prepare_widget(widget)

        # Insert the widget into the list so that the list appears sorted by
        # key
        insertion_index = self._get_insertion_index_for_item(item)
        self.add_widget(widget, insertion_index)  # type: ignore

        # Return the widget
        return widget

    def _create_widget_for_item(self, item: T) -> Widget:
        """Creates a widget that will represent the given item.

        Must be overridden in subclasses.

        Parameters:
            item: the item for which we want to create a widget

        Returns:
            the widget that corresponds to the given item
        """
        raise NotImplementedError

    def _default_key_function(self, item: T) -> int:
        """Returns the key to be used shown for an item if the user did not
        override the value in the ``key_function`` property.
        """
        if hasattr(item, "id"):
            return item.id  # type: ignore
        else:
            return id(item)

    def _emit_item_selected_signal(self) -> None:
        focus = self.focused_widget  # type: ignore
        item = self._extract_item_from_widget(focus) if focus else None
        if item:
            emit_signal(self, "selected", item)

    def _extract_item_from_widget(self, widget: Widget) -> T:
        """Extracts the item that a given widget in the list represents,
        given the widget. Can be overridden in subclasses if there is an
        easy way to retrieve the item from the widget.

        Parameters:
            widget (urwid.Widget): the widget to extract the item from

        Returns:
            object: the item that the widget represents
        """
        return self._items_by_widgets[widget]

    def _get_insertion_index_for_item(self, item: T) -> Optional[int]:
        """Given a new item that is not in the list yet, determines the
        insertion point where the item should be inserted in order to keep
        the list sorted.

        Parameters:
            item: the item to insert

        Returns:
            the index where the item should be inserted or ``None`` if the item
            should be inserted at the end

        Throws:
            ValueError: if the item is already in the list
        """
        for index, existing_widget in enumerate(self.iterwidgets()):  # type: ignore
            existing_item = self._extract_item_from_widget(existing_widget)
            if existing_item is item:
                raise ValueError("item is already in the list")
            if self._compare_items(existing_item, item) > 0:
                return index
        return None

    def _prepare_widget(self, widget: Widget) -> None:
        pass

    def add_item(self, item: T) -> Widget:
        """Adds the given item (or, more precisely, a widget that represents
        the item) into the list.

        The item object will be inserted in a way that keeps the list
        sorted. The operation will not add another widget for an item if the
        item is already in the list.

        Parameters:
            item: the item that is about to be added.

        Returns:
            Widget: the widget that corresponds to the given item
        """
        return self.get_widget_for_item(item, create_if_missing=True)  # type: ignore

    def clear(self):
        """Removes all the widgets from the list."""
        self._widgets_by_items = {}
        self._clear_body()

    def contains_item(self, item):
        """Returns whether the list already contains a widget for the given
        item.

        Parameters:
            item (object): the item that we are interested in

        Returns:
            bool: whether the list contains a widget for the given item
        """
        return self.get_widget_for_item(item) is not None

    def get_widget_for_item(
        self, item: T, create_if_missing: bool = False
    ) -> Optional[Widget]:
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

        for widget in self.iterwidgets():  # type: ignore
            self._prepare_widget(widget)

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
        widget = self.get_widget_for_item(item, create_if_missing=False)
        self.remove_widget(widget)  # type: ignore
        del self._widgets_by_items[item]
        return widget

    @property
    def selected_item(self) -> Optional[T]:
        """Returns the item represented by the focused widget, or
        ``None`` if there is no selected widget.
        """
        widget = self.focused_widget  # type: ignore
        if widget is None:
            return None

        return self._extract_item_from_widget(widget.base_widget)

    def update_order(self) -> None:
        """Notifies the widget that the list may have to be re-sorted if the
        sorting function has changed.
        """
        focused_widget: Optional[Widget] = self.focused_widget  # type: ignore

        widgets = sorted(self.iterwidgets(), key=cmp_to_key(self._compare_widgets))  # type: ignore
        self._clear_body()

        for widget in widgets:
            self.add_widget(widget)  # type: ignore

        if focused_widget in widgets:
            self.focus_position = widgets.index(focused_widget)

        self.refresh()  # type: ignore
