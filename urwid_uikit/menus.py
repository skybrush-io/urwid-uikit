"""Helper widgets for implementing dropdown menus"""

from urwid import (
    AttrMap,
    Button,
    Divider,
    ListBox,
    SimpleFocusListWalker,
    Text,
    WidgetWrap,
    connect_signal,
    disconnect_signal,
)

from .dialogs import DialogOverlay
from .graphics import PatchedLineBox
from .utils import extract_base_widget, tuplify


class Menu(WidgetWrap):
    """urwid widget that represents a menu with a ListBox_."""

    def __init__(self, items=()):
        """Creates a menu widget from the given list of items.

        Parameters:
            items (List[str]): the list of menu items to show

        Returns:
            Widget: a menu widget
        """
        if callable(items):
            items = items()
        self.items = [create_menu_item_from_spec(item) for item in items]
        super(Menu, self).__init__(ListBox(SimpleFocusListWalker(self.items)))

    def keypress(self, size, key):
        if len(size) != 2:
            size = self.pack(size)
        return super(Menu, self).keypress(size, key)

    def pack(self, size, focus=False):
        if not size:
            # Fixed widget; we get to choose our own size
            if self.items:
                max_width = max(self._get_item_width(item) for item in self.items)
            else:
                max_width = 0
            return max_width, self.rows(size, focus)
        elif len(size) == 1:
            # Flow widget; we get to choose our own height
            return (size[0], self.rows(size, focus))
        else:
            # Box widget; parent chooses a size for us and we respect that
            return size

    def render(self, size, focus=False):
        if len(size) != 2:
            size = self.pack(size, focus)
        return super(Menu, self).render(size, focus)

    def rows(self, size, focus=False):
        return len(self.items)

    @staticmethod
    def _get_item_width(item):
        item = extract_base_widget(item)
        if isinstance(item, Button):
            return len(item.get_label()) + 5
        elif isinstance(item, Text):
            return len(item.text) + 3
        else:
            return 0


class MenuItemButton(Button):
    button_left = Text("")
    button_right = Text("")


class SubmenuButton(Button):
    button_left = Text("")
    button_right = Text(">")

    def open_with(self, overlay):
        overlay.open_menu(self.items, title=self.label)


class MenuOverlay(DialogOverlay):
    """Overlay that can be placed over a main application widget to provide
    a cascading dropdown menu (as well as ordinary dialogs).
    """

    def __init__(self, app_widget, menu_factory=Menu):
        """Constructor.

        Parameters:
            app_widget (Widget): main application frame widget that the menu
                overlay will wrap
            menu_factory (callable): factory function that can be invoked with
                a list of items and that will create an appropriate widget to
                be shown in the overlay containing the given items
        """
        super(MenuOverlay, self).__init__(app_widget)
        self._menu_factory = menu_factory

    def _on_menu_closed(self, menu):
        """Callback to call when a menu widget was closed."""
        menu = menu.base_widget
        for item in menu.items:
            item = extract_base_widget(item)
            if isinstance(item, SubmenuButton):
                disconnect_signal(item, "click", self._open_submenu)
            elif isinstance(item, MenuItemButton):
                disconnect_signal(item, "click", self._close_all_menus)
        return True

    def open_menu(self, items, title=None):
        """Opens the given menu widget on top of the overlay.

        Parameters:
            items (List): the items in the menu to open
            title (Optional[str]): optional title of the menu
        """
        menu = self._menu_factory(items)

        for item in menu.items:
            item = extract_base_widget(item)
            if isinstance(item, SubmenuButton):
                connect_signal(item, "click", self._open_submenu)
            elif isinstance(item, MenuItemButton):
                connect_signal(item, "click", self._close_all_menus)

        widget = AttrMap(
            PatchedLineBox(menu, title=title), "menu in background", focus_map="menu"
        )

        return self.open_dialog(widget, on_close=self._on_menu_closed, styled=True)

    def _close_all_menus(self, item):
        self.close()

    def _open_submenu(self, item):
        item.open_with(self)


def create_separator():
    """Creates a widget in a menu that can be used as a horizontal
    separator.
    """
    return Divider(u"\u2015")


def create_submenu(title, items):
    """Creates a widget in a menu that will open a submenu with the given
    items when invoked.

    Parameters:
        title (str): the title of the submenu; it will be used both for the
            label of the menu widget and the label of the submenu box.
        items (Union[List, callable]): the list of items to show in the menu,
            or a function that will return such a list when invoked with no
            arguments. Each item in the list will be passed through to
            `create_menu_item_from_spec()` so you can use anything there that
            is accepted by `create_menu_item_from_spec()`.

    Returns:
        Widget: a widget that will open the submenu when invoked
    """
    if items:
        button = SubmenuButton(title)
        button.items = items
        return AttrMap(button, None, focus_map="menu focus")
    else:
        return AttrMap(Text("  " + title), "menu disabled")


def create_submenu_from_enum(title, items, getter, setter):
    """Creates an array representing a submenu in a menu structure where each
    item corresponds to a possible element of an enum, and at most one of
    these elements is marked as the currently selected one.

    Parameters:
        title (str): the title of the submenu
        items (Iterable[object, str]): an iterable that yields object-string
            pairs such that the first element of the pair is a possible value
            of the enum and the second element is the label of the
            corresponding menu item.
        getter (Union[object, callable]): an object that denotes the current
            value of the enum, or a callable that returns such a value when
            invoked with no arguments
        setter (callable): a function that can be called with the new value of
            the enum in order to activate the corresponding menu item

    Returns:
        object: an opaque object that describes a submenu containing one item
            for each possible value of the enum such that the current one is
            marked. This object can safely be passed to
            `create_menu_item_from_spec()`.
    """
    current = getter() if callable(getter) else getter
    if not title.endswith(">"):
        title += ">"

    return (
        title,
        [
            (
                "({0}) {1}".format("*" if item is current else " ", item_title),
                setter,
                item,
            )
            for item, item_title in items
        ],
    )


def create_menu_item(title=None, callback=None, *args, **kwds):
    """Creates a widget in a menu with the given title.

    Parameters:
        title (Optional[str]): the title of the menu item.
        callback (Optional[callable]): a function to call when the menu item
            was selected. When it is ``None``, the item is assumed to be
            disabled.

    Additional arguments are forwarded to the callback.

    Returns:
        Widget: the constructed menu widget
    """
    enabled = callback is not None

    if enabled:

        def wrapper(button):
            return callback(*args, **kwds)

        button = MenuItemButton(title, wrapper)
        return AttrMap(button, None, focus_map="menu focus")
    else:
        return AttrMap(Text("  " + title), "menu disabled")


def create_menu_item_from_spec(spec=None):
    """Creates a widget in a menu from a specification object.

    The specification object is a tuple where the first element of the tuple
    specifies how the menu item will look like.

    When the first element is ``None`` or a single dash, the returned widget
    will be a separator.

    When the first element is a string ending with `>`, the returned widget
    is a menu item that opens a submenu. In this case, the second item of the
    tuple must be either a list of items in the submenu (each of which will be
    passed through `create_menu_item_from_spec()` when the submenu is opened,
    or a function that returns such a list when invoked with no items.

    In all other cases, the first element is assumed to be the title of the
    menu item, and the second element must be a callback function to invoke
    when the menu item is selected. Additional elements in the tuple will be
    forwarded to the callback function as positional arguments.

    Returns:
        Widget: the constructed menu widget
    """
    spec = tuplify(spec)

    title = spec[0]

    if title is None or title == "-":
        return create_separator()

    if title.endswith(">"):
        title = title[:-1].rstrip()
        return create_submenu(title, spec[1] if len(spec) > 1 else None)

    return create_menu_item(title, spec[1] if len(spec) > 1 else None, *spec[2:])
