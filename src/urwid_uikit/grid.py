from urwid import AttrMap, Filler, GridFlow, WidgetWrap
from urwid.command_map import (
    command_map,
    CURSOR_DOWN,
    CURSOR_LEFT,
    CURSOR_RIGHT,
    CURSOR_UP,
    CURSOR_MAX_LEFT,
    CURSOR_MAX_RIGHT,
)

from .mixins import ObjectContainerMixin

__all__ = ("Grid", "ObjectGrid")


class Grid(WidgetWrap):
    """Grid that shows a set of widgets and has a single focused widget that is
    displayed differently.
    """

    _command_map = command_map
    _selectable = True

    def __init__(self, cell_width, h_sep=0, v_sep=0, align="left", valign="top"):
        """Constructor."""
        self._grid_flow = GridFlow(
            [], cell_width=cell_width, h_sep=h_sep, v_sep=v_sep, align=align
        )
        filler = Filler(self._grid_flow, valign=valign)
        super().__init__(filler)

    def add_widget(self, widget, index=None):
        """Adds a new widget to the list box.

        Parameters:
            widget (urwid.Widget): the widget to add
            index (Optional[int]): the insertion index; ``None`` means the
                end of the list
        """
        # Wrap the widget in an AttrMap before it actually gets inserted
        wrapped_widget = AttrMap(widget, "", "list focus")
        options = self._grid_flow.options()

        # Do the insertion
        if index is None:
            self._grid_flow.contents.append((wrapped_widget, options))
        else:
            self._grid_flow.contents.insert(index, (wrapped_widget, options))

    @property
    def command_map(self):
        return self._command_map

    @property
    def contents(self):
        return self._grid_flow.contents

    @property
    def focus(self):
        return self._grid_flow.focus

    @property
    def focus_position(self):
        return self._grid_flow.focus_position

    @focus_position.setter
    def focus_position(self, value):
        self._grid_flow.focus_position = value

    @property
    def focused_widget(self):
        """Returns the focused widget of the list.

        Returns:
            urwid.Widget: the focused widget
        """
        focused_widget = self.focus
        if hasattr(focused_widget, "base_widget"):
            focused_widget = focused_widget.base_widget
        return focused_widget

    def iterwidgets(self):
        """Iterates over all the widgets objects in the list."""
        for existing_widget, _ in self._grid_flow.contents:
            # Contrary to what the urwid.AttrMap documentation says, AttrMap
            # objects do not forward properties transparently to the wrapped
            # widgets, so we need the base_widget property here (which is
            # the identity function for non-decoration widgets)
            yield existing_widget.base_widget

    def keypress(self, size, key):
        command = self.command_map[key]
        delta, new_pos = None, None

        if command == CURSOR_LEFT:
            delta = -1
        elif command == CURSOR_RIGHT:
            delta = 1
        elif command == CURSOR_UP:
            delta = -self._get_num_columns_from_size(size)
        elif command == CURSOR_DOWN:
            delta = self._get_num_columns_from_size(size)
        elif command == CURSOR_MAX_LEFT:
            num_cols = self._get_num_columns_from_size(size)
            if num_cols > 0:
                new_pos = (self._get_focus_position_safe() // num_cols) * num_cols
        elif command == CURSOR_MAX_RIGHT:
            num_cols = self._get_num_columns_from_size(size)
            if num_cols > 0:
                new_pos = (
                    self._get_focus_position_safe() // num_cols + 1
                ) * num_cols - 1
                new_pos = min(new_pos, len(self.contents) - 1)
        else:
            # Keypress not handled here
            return key

        try:
            if new_pos is not None:
                self.focus_position = new_pos
            elif delta is not None:
                self.focus_position = self._get_focus_position_safe() + delta
        except IndexError:
            # new index is invalid
            pass

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
        self._grid_flow.contents.pop(index)

    def _get_focus_position_safe(self):
        try:
            return self.focus_position
        except IndexError:
            return 0

    def _get_num_columns_from_size(self, size):
        w, _ = size
        return w // (self._grid_flow.h_sep + self._grid_flow.cell_width)


class ObjectGrid(Grid, ObjectContainerMixin):
    """Grid that shows a set of widgets such that each widget is associated to a
    unique object, and the order of the widgets in the grid is determined by a
    function that derives a comparable key from each unique object in the list.

    This is an abstract base class. Derived classes must override at least
    ``_create_widget_for_item()``.
    """

    def __init__(self, *args, **kwds):
        """Constructor."""
        super().__init__(*args, **kwds)
        ObjectContainerMixin.__init__(self)
