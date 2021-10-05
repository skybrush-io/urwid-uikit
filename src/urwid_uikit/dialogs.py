"""Helper widgets for implementing dialog boxes"""

from functools import partial
from urwid import AttrMap, Overlay, Widget, WidgetPlaceholder
from typing import Callable, List, Optional, Tuple

from .graphics import PatchedLineBox
from .types import TextOrMarkup

__all__ = ("DialogOverlay",)


#: Type alias for on_close callbacks in a dialog overlay
CloseCallback = Callable[[Widget], bool]

#: Type alias for on_close callbacks in a dialog overlay
BoundCloseCallback = Callable[[], bool]


class DialogOverlay(WidgetPlaceholder):
    """Overlay that can be placed over a main application widget to provide
    a layer that shows modal dialogs.
    """

    _stack: List[Tuple[Widget, Optional[BoundCloseCallback]]]

    def __init__(self, app_widget: Widget):
        """Constructor.

        Parameters:
            app_widget (Widget): main application frame widget that the dialog
                overlay will wrap
        """
        super().__init__(app_widget)
        self._stack = []

    def close(self) -> bool:
        """Closes all widgets currently in the overlay.

        Returns:
            whether the overlay was closed; `False` if the `on_close` callback
            of some widget in the overlay prevented the close operation
        """
        while self.has_content:
            if self.close_topmost_dialog() is None:
                return False
        return True

    def close_topmost_dialog(self) -> Optional[Widget]:
        """Closes the topmost dialog widget from the overlay.

        Returns:
            the widget that was closed or ``None`` if the overlay was empty or
            if the `on_close` callback of the topmost widget prevented the
            operation
        """
        if not self._stack:
            return None

        widget, on_close = self._stack[-1]
        can_close = on_close() if on_close else True

        if can_close:
            self.original_widget = self.original_widget.bottom_w
            self._stack.pop()
            return widget
        else:
            return None

    @property
    def has_content(self) -> bool:
        """Returns whether there is at least one dialog open."""
        return len(self._stack) > 0

    def open_dialog(
        self,
        dialog: Widget,
        title: Optional[TextOrMarkup] = None,
        on_close: Optional[CloseCallback] = None,
        styled: bool = False,
    ) -> None:
        """Opens the given dialog widget on top of the overlay.

        Parameters:
            dialog (Widget): the widget to show in the dialog
            title (Optional[str]): optional title of the dialog
            on_close: callback to call when the dialog is about to be closed.
                The callback will be called with the dialog that is being closed
                as its only argument.
            styled: when `True`, it is assumed that the dialog is
                already styled with an appropriate AttrMap_ and a frame.
                When `False`, a frame and an AttrMap_ will be added
                automatically. The title is ignored when `styled` is set to
                `True`.
        """
        if not styled:
            widget = AttrMap(
                PatchedLineBox(dialog, title=title),
                "dialog in background",
                focus_map="dialog",
            )
        else:
            widget = dialog

        self.original_widget = Overlay(
            widget,
            self.original_widget,
            align="center",
            width="pack",
            valign="middle",
            height="pack",
        )

        self._stack.append((widget, partial(on_close, dialog) if on_close else None))

    def keypress(self, size, key: str):
        """Handler called when a key is pressed in the overlay."""
        if key == "esc" and self.has_content:
            self.close_topmost_dialog()
        else:
            return super().keypress(size, key)
