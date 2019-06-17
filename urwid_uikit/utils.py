"""Utility functions and classes for the implementation of urwid widgets."""

__all__ = ("extract_base_widget", "StyledLabelFormatter")


def extract_base_widget(widget):
    """If the widget is a decorator widget, attempts to extract the base
    widget that the decorator decorates by retrieving its ``base_widget``
    attribute.

    Note that if the base widget is decorated by multiple decorators, this
    function will cut through all of them and still retrieve the innermost
    widget that is not decorated.

    Parameters:
        widget (Widget): a decorator widget

    Returns:
        Widget: the widget that the decorator widget decorates
    """
    try:
        return widget.base_widget
    except AttributeError:
        return widget


def tuplify(obj):
    """Ensures that the given object is a tuple. If it is not a tuple, wraps
    it in a tuple.

    Parameters:
        obj (object): the input

    Returns:
        tuple: if object is already a tuple, returns the object itself.
            Otherwise it returns the object wrapped in a tuple.
    """
    return obj if isinstance(obj, tuple) else (obj,)


class StyledLabelFormatter(object):
    """Helper object that takes a format string (curlybraces-style, just like
    the ones used in ``str.format()`` and replaces the tokens in them with
    values taken from the properties of an object.

    Note that this formatter is more restrictive than Python's ``str.format()``
    as it does not handle sub-properties and positional arguments, but on the
    other hand it behaves correctly if the property of the object being
    formatted returns an ``urwid`` markup.
    """

    def __init__(self, format=""):
        """Constructor.

        Parameters:
            format (str): the format string to use
        """
        self._format = None
        self.format = format

    @property
    def format(self):
        """Returns the format string of the formatter."""
        return self._format

    @format.setter
    def format(self, value):
        if self._format == value:
            return

        self._format = value
        self._compile()

    def _compile(self):
        """Creates a compiled representation of the format string so we don't
        have to parse it every time a new object is formatted.
        """
        if not self._format:
            self._compiled_format = []
            return

        n = len(self._format)
        start = 0
        next_is_literal = True
        parts = []
        while start < n:
            if next_is_literal:
                next_brace = self._format.find("{", start)
                if next_brace == -1:
                    literal = self._format[start:]
                    start = n
                else:
                    literal = self._format[start:next_brace]
                    start = next_brace + 1
                parts.append(literal)
                next_is_literal = False
            else:
                if self._format[start] == "{":
                    next_brace = self._format.find("}}", start)
                    if next_brace == -1:
                        raise ValueError("Single '}' encountered in format " "string")
                    parts[-1] += self._format[start : (next_brace + 1)]
                    start = next_brace + 2
                else:
                    next_brace = self._format.find("}", start)
                    if next_brace == -1:
                        raise ValueError("Single '}' encountered in format " "string")
                    token, sep, modifier = self._format[start:next_brace].partition(":")
                    if sep:
                        parts.append((token, ("{0:%s}" % modifier).format))
                    else:
                        parts.append((token, str))
                    start = next_brace + 1
                    next_is_literal = True

        self._compiled_format = parts

    def __call__(self, obj):
        """Formats the given object using the format string of this formatter.

        Parameters:
            obj (object): the object to format
        """
        parts = []
        for idx, part in enumerate(self._compiled_format):
            if idx % 2:
                attrname, formatter = part
                part = getattr(obj, attrname)
                if formatter:
                    if isinstance(part, tuple):
                        style, value = part
                        part = style, formatter(value)
                    else:
                        part = formatter(part)
            if part:
                parts.append(part)
        return parts or ""
