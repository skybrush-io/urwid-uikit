from typing import Any, Optional, Sequence, Tuple, Union

__all__ = ("ColumnOptions", "TextOrMarkup")


#: Type alias for objects returned from Columns.options() in urwid
ColumnOptions = Optional[Union[int, float, Tuple[Any, ...]]]

#: Type alias for urwid text or markup
TextOrMarkup = Union[str, Tuple[str, str], Sequence[Union[str, Tuple[str, str]]]]
