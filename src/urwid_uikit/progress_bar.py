"""Customized progress bar widgets."""

from urwid import ProgressBar


__all__ = ("CustomTextProgressBar",)


class CustomTextProgressBar(ProgressBar):
    """Progress bar that allows custom text to be placed on it."""

    _has_error: bool
    _has_warning: bool
    _successful: bool
    _template: str

    def __init__(self, done: float = 100):
        """Constructor."""
        super().__init__(
            normal="progress bar normal",
            complete="progress bar complete",
            done=done,
            satt="progress bar smoothed part",
        )
        self._template = "{0} %"
        self._successful = False
        self._has_error = False
        self._has_warning = False

    def get_text(self) -> str:
        """Returns the text to be shown on the progress bar."""
        percent = min(100, max(0, int(self.current * 100 / self.done)))
        return self._template.format(percent)

    @property
    def has_error(self) -> bool:
        """Returns whether the operation represented by the progress bar
        encountered an error. Alters the color of the progress bar if set.
        """
        return self._has_error

    @has_error.setter
    def has_error(self, value):
        if value == self._has_error:
            return

        self._has_error = bool(value)
        self._update_style()

    @property
    def has_warning(self) -> bool:
        """Returns whether the operation represented by the progress bar
        encountered a minor issue that does not consistute an error on its
        own. Alters the color of the progress bar if set.
        """
        return self._has_warning

    @has_warning.setter
    def has_warning(self, value):
        if value == self._has_warning:
            return

        self._has_warning = bool(value)
        self._update_style()

    @property
    def successful(self) -> bool:
        """Returns whether the operation represented by the progress bar
        was successful. Alters the color of the progress bar if set.
        """
        return self._successful

    @successful.setter
    def successful(self, value):
        if value == self._successful:
            return

        self._successful = value
        self._update_style()

    def _update_style(self) -> None:
        """Updates the style of the progress bar after the ``successful``
        or ``has_error`` flags were altered.
        """
        self.complete = "progress bar {0}".format(
            "error"
            if self._has_error
            else "warning"
            if self._has_warning
            else "successful"
            if self._successful
            else "complete"
        )
        self._invalidate()

    @property
    def template(self) -> str:
        """Text template that is used to create the text of the progress
        bar. It can contain a placeholder ``{0}`` that is replaced with
        the current progress.
        """
        return self._template

    @template.setter
    def template(self, value: str):
        if value == self._template:
            return

        self._template = value
        self._invalidate()
