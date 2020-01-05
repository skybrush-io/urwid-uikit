"""Customized progress bar widgets."""

from urwid import ProgressBar, Text, CLIP
from urwid.compat import ord2


__all__ = ("CustomTextProgressBar",)


class CustomTextProgressBar(ProgressBar):
    """Progress bar that allows custom text to be placed on it."""

    def __init__(self, done=100):
        """Constructor."""
        super(CustomTextProgressBar, self).__init__(
            normal="progress bar normal",
            complete="progress bar complete",
            done=done,
            satt="progress bar smoothed part",
        )
        self._template = u"{0} %"
        self._successful = False
        self._has_error = False
        self._has_warning = False

    def render(self, size, focus=False):
        """
        Render the progress bar.
        """
        # This is copied straight from urwid after incorporating a fix
        # for Github issue #317. This can be removed once a fix is merged.
        (maxcol,) = size
        txt = Text(self.get_text(), self.text_align, CLIP)
        c = txt.render((maxcol,))

        cf = float(self.current) * maxcol / self.done
        ccol_dirty = int(cf)
        ccol = len(c._text[0][:ccol_dirty].decode("utf-8", "ignore").encode("utf-8"))
        cs = 0
        if self.satt is not None:
            cs = int((cf - ccol) * 8)
        if ccol < 0 or (ccol == 0 and cs == 0):
            c._attr = [[(self.normal, maxcol)]]
        elif ccol >= maxcol:
            c._attr = [[(self.complete, maxcol)]]
        elif cs and ord2(c._text[0][ccol]) == 32:
            t = c._text[0]
            cenc = self.eighths[cs].encode("utf-8")
            c._text[0] = t[:ccol] + cenc + t[ccol + 1 :]
            a = []
            if ccol > 0:
                a.append((self.complete, ccol))
            a.append((self.satt, len(cenc)))
            if maxcol - ccol - 1 > 0:
                a.append((self.normal, maxcol - ccol - 1))
            c._attr = [a]
            c._cs = [[(None, len(c._text[0]))]]
        else:
            c._attr = [[(self.complete, ccol), (self.normal, maxcol - ccol)]]
        return c

    def get_text(self):
        """Returns the text to be shown on the progress bar."""
        percent = min(100, max(0, int(self.current * 100 / self.done)))
        return self._template.format(percent)

    @property
    def has_error(self):
        """Returns whether the operation represented by the progress bar
        encountered an error. Alters the color of the progress bar if set.
        """
        return self._has_error

    @has_error.setter
    def has_error(self, value):
        if value == self._has_error:
            return

        self._has_error = value
        self._update_style()

    @has_error.setter
    def has_error(self, value):
        if value == self._has_error:
            return

        self._has_error = value
        self._update_style()

    @property
    def has_warning(self):
        """Returns whether the operation represented by the progress bar
        encountered a minor issue that does not consistute an error on its
        own. Alters the color of the progress bar if set.
        """
        return self._has_warning

    @has_warning.setter
    def has_warning(self, value):
        if value == self._has_warning:
            return

        self._has_warning = value
        self._update_style()

    @property
    def successful(self):
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

    def _update_style(self):
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
    def template(self):
        """Text template that is used to create the text of the progress
        bar. It can contain a placeholder ``{0}`` that is replaced with
        the current progress.
        """
        return self._template

    @template.setter
    def template(self, value):
        if value == self._template:
            return

        self._template = value
        self._invalidate()
