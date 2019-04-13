"""Helper widgets for implementing dialog boxes"""

from __future__ import absolute_import

from functools import partial
from urwid import AttrMap, Overlay, WidgetPlaceholder

from .graphics import PatchedLineBox

__all__ = ("DialogOverlay", )


class DialogOverlay(WidgetPlaceholder):
    """Overlay that can be placed over a main application widget to provide
    a layer that shows modal dialogs.
    """

    def __init__(self, app_widget):
        """Constructor.

        Parameters:
            app_widget (Widget): main application frame widget that the dialog
                overlay will wrap
        """
        super(DialogOverlay, self).__init__(app_widget)
        self._stack = []

    def close(self):
        """Closes all widgets currently in the overlay."""
        while self.has_content:
            if self.close_topmost_dialog() is None:
                return False
        return True

    def close_topmost_dialog(self):
        """Closes the topmost dialog widget from the overlay.

        Returns:
            Optional[Widget]: the widget that was closed or ``None`` if the
                `on_close` callback of the widget prevented the operation
        """
        if not self._stack:
            return None

        widget, on_close = self._stack[-1]
        can_close = on_close() if on_close else True

        if can_close:
            self.original_widget = self.original_widget[0]
            self._stack.pop()
            return widget
        else:
            return None

    @property
    def has_content(self):
        """Returns whether there is at least one dialog open."""
        return len(self._stack) > 0

    def open_dialog(self, dialog, title=None, on_close=None, styled=False):
        """Opens the given dialog widget on top of the overlay.

        Parameters:
            dialog (Widget): the widget to show in the dialog
            title (Optional[str]): optional title of the dialog
            on_close (Optional[callable]): callback to call when the dialog
                is about to be closed. The callback will be called with the
                dialog that is being closed.
            styled (bool): when `True`, it is assumed that the dialog is
                already styled with an appropriate AttrMap_ and a frame.
                When `False`, a frame and an AttrMap_ will be added
                automatically. The title is ignored when `styled` is set to
                `True`.
        """
        if not styled:
            widget = AttrMap(
                PatchedLineBox(dialog, title=title),
                "dialog in background",
                focus_map="dialog"
            )
        else:
            widget = dialog

        self.original_widget = Overlay(
            widget,
            self.original_widget,
            align="center", width="pack",
            valign="middle", height="pack"
        )

        self._stack.append((widget, partial(on_close, dialog)))

    def keypress(self, size, key):
        """Handler called when a key is pressed in the overlay."""
        if key == "esc" and self.has_content:
            self.close_topmost_dialog()
        else:
            return super(DialogOverlay, self).keypress(size, key)
