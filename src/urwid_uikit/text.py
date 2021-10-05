"""Text-related urwid widgets."""

from urwid import Text

__all__ = ("SelectableText",)


class SelectableText(Text):
    """Subclass of Text_ that can be selectable. Useful as a child widget in
    list boxes.
    """

    def selectable(self) -> bool:
        return True

    def keypress(self, size, key: str) -> str:
        return key
