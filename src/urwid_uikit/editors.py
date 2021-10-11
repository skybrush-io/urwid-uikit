from collections import deque
from urwid import Edit, connect_signal
from typing import Deque, Optional, Sequence, TypeVar

__all__ = ("EditWithHistory",)

C = TypeVar("C", bound="HistoryItem")


class HistoryItem:
    """Single history item in a History_ object.

    Each history item contains a string and an optional "edited" string. When
    the "edited" string is not provided, the item is said to be in a so-called
    _pristine_ state. Updating the item will change the "edited" string but
    keep the original string intact. The original string is _never_ modified.

    One can commit the changes of the item -- this will create a _new_ history
    item that contains the "edited" string from the current item as the
    original value. One can also revert the changes of the item -- this will
    throw away the "edited" string.
    """

    _original_value: str
    _edited_value: Optional[str]

    def __init__(self, value: str = ""):
        """Constructor.

        Parameters:
            value: the initial value of the item
        """
        self._original_value = value if value is not None else ""
        self._edited_value = None

    def commit(self: C) -> C:
        """Commits the changes to this history item and returns a new history
        item with its edited value as the original one.

        When the item is not dirty, returns the same item.
        """
        if self.dirty:
            assert self._edited_value is not None
            return self.__class__(self._edited_value)
        else:
            return self

    @property
    def dirty(self) -> bool:
        """Returns whether the item is dirty, i.e. its edited value is
        different from the original one.
        """
        return self._edited_value is not None

    @property
    def original_value(self) -> str:
        """The original value in the history item, even if it is dirty."""
        return self._original_value

    def revert(self) -> None:
        """Reverts the history item to its pristine state."""
        self._edited_value = None

    @property
    def value(self) -> str:
        """The current value in the history item. When the item is pristine,
        this will be the original value; otherwise this will be the edited
        value.
        """
        if self._edited_value is not None:
            return self._edited_value
        else:
            return self._original_value

    @value.setter
    def value(self, new_value):
        if new_value is None:
            raise ValueError("cannot set new value to ``None``, use revert()")

        if new_value == self._original_value:
            self._edited_value = None
        else:
            self._edited_value = new_value

    def __repr__(self):
        return (
            "{0.__class__.__name__}(value={0.value!r}, "
            "original_value={0.original_value!r})".format(self)
        )


class History(Sequence[HistoryItem]):
    """Object modelling the history of an EditWithHistory_ component."""

    _items: Deque[HistoryItem]
    _index: int

    def __init__(self, max_size: Optional[int] = None):
        """Constructor.

        Parameters:
            max_size: the maximum number of items to keep in the history
        """
        if max_size is not None:
            self._items = deque([], max_size)
        else:
            self._items = deque([])
        self._index = 0
        self._ensure_current_item_is_empty()

    def __getitem__(self, index: int) -> HistoryItem:
        """Returns the item in the history at the given index. Zero belongs to
        the current item being edited; negative numbers correspond to earlier
        items, positive numbers correspond to later items.
        """
        return self._items[self._index + index]

    def __len__(self) -> int:
        """Returns the number of items in the history."""
        return len(self._items)

    def commit(self) -> None:
        """Commits the changes of the current item in the history, and reverts
        all edits in all non-selected items. When the current item is dirty, a
        copy is created and added to the end of the history. When the current
        item is pristine, it is moved to the end of the history. In both cases,
        a new, empty item is appended to the history, and optionally the
        earliest item in the history is discarded if the history has a length
        limit.
        """
        current_item = self.current
        new_item = current_item.commit()

        for item in self._items:
            item.revert()

        if new_item is current_item:
            self._items.remove(current_item)
        self._ensure_last_item_is_not_empty()
        self._items.append(new_item)

        self._index = len(self._items) - 1
        self._ensure_current_item_is_empty()

    @property
    def current(self) -> HistoryItem:
        """Returns the current history item."""
        return self._items[self._index]

    def select_next(self) -> HistoryItem:
        """Selects the next item in the history if there is one. Otherwise
        it is a no-op.

        Returns:
            the new selected item
        """
        if self._index < len(self) - 1:
            self._index += 1
        return self.current

    def select_previous(self) -> HistoryItem:
        """Selects the previous item in the history if there is one. Otherwise
        it is a no-op.

        Returns:
            the new selected item
        """
        if self._index > 0:
            self._index -= 1
        return self.current

    def cancel_editing(self) -> None:
        """Stops the current editing session, restores all history items to
        their original state, and jumps to the end of the history.
        """
        for item in self._items:
            item.revert()

        self._index = len(self._items) - 1
        self._ensure_current_item_is_empty()

    def update(self, value) -> None:
        """Updates the current item such that its value becomes the one given
        in the argument.

        Parameters:
            value: the new value of the current item
        """
        self.current.value = value

    def _ensure_current_item_is_empty(self) -> None:
        if not self._items or self.current.original_value != "":
            self._items.append(HistoryItem())
            self._index = len(self._items) - 1

    def _ensure_last_item_is_not_empty(self) -> None:
        while self._items and self._items[-1].original_value == "":
            self._items.pop()
        self._index = min(self._index, len(self._items) - 1)


class EditWithHistory(Edit):
    """Extension of urwid's default Edit widget with support for a history."""

    _history: History
    _updating_text_from_history: bool

    def __init__(self, *args, **kwds):
        self._history = History()
        self._updating_text_from_history = False

        super().__init__(*args, **kwds)
        connect_signal(self, "postchange", self._on_text_changed)

        self._update_history_from_text()

    def cancel_editing(self) -> None:
        """Stops the current editing session, restores all history items to
        their original state, and jumps to the end of the history.
        """
        self._history.cancel_editing()
        self._update_text_from_history()

    def commit_history(self) -> None:
        """Commits the current text to the history of the edit box, and clears
        the edit box itself.
        """
        self._history.commit()
        self._update_text_from_history()

    def keypress(self, size, key: str):
        """Handle keypresses in the text field so we can treat arrow-up,
        arrow-down and Enter appropriately.
        """
        if key == "up":
            self._history.select_previous()
            self._update_text_from_history()
        elif key == "down":
            self._history.select_next()
            self._update_text_from_history()
        else:
            return super().keypress(size, key)

    def _on_text_changed(self, old_text, new_text):
        self._update_history_from_text()

    def _update_history_from_text(self) -> None:
        if not self._updating_text_from_history:
            self._history.current.value = self.get_edit_text()

    def _update_text_from_history(self) -> None:
        self._updating_text_from_history = True
        try:
            self.set_edit_text(self._history.current.value)
            self.set_edit_pos(len(self.get_edit_text()))
        finally:
            self._updating_text_from_history = False
