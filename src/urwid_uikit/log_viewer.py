"""Log viewer widget that shows the last N entries of a Python logger."""

from __future__ import annotations

from logging import getLogger, Formatter, Handler, Logger, LogRecord
from typing import Dict, Optional, Union, TYPE_CHECKING
from urwid import Divider, Widget, WidgetWrap

from .list import List
from .text import SelectableText
from .types import TextOrMarkup

if TYPE_CHECKING:
    from .app import Application


def _create_marker():
    return Divider(u"\u2015")


class ColoredFormatterWrapper(Formatter):
    """Logging formatter that takes another formatter and wraps it such that
    the formatted result is color-coded according to the log level of the
    entry being formatted.
    """

    _formatter: Formatter

    _level_to_prefix: Dict[str, TextOrMarkup] = {
        "CRITICAL": ("error", u" \N{BLACK CIRCLE} "),
        "DEBUG": ("debug", u" \N{BLACK RIGHT-POINTING TRIANGLE} "),
        "WARNING": ("warning", u" \N{BLACK UP-POINTING TRIANGLE} "),
        "ERROR": ("error", " \N{BLACK CIRCLE} "),
    }

    def __init__(self, formatter: Optional[Union[str, Formatter]] = None):
        """Constructor.

        Parameters:
            formatter (Optional[str, Formatter]): the formatter that this
                instance wraps, or a format string. Defaults to
                `%(message)s`.
        """
        self._formatter = self._process_formatter(formatter)

    def format(self, record):
        result = self._formatter.format(record)
        prefix = self._level_to_prefix.get(record.levelname, "   ")
        return [prefix, result]

    def _process_formatter(
        self, formatter: Optional[Union[str, Formatter]]
    ) -> Formatter:
        if formatter is None:
            formatter = " %(message)s"
        if not isinstance(formatter, Formatter):
            formatter = Formatter(formatter)
        return formatter


class LogViewerWidgetHandler(Handler):
    """Logging handler that sends emitted log entries to a LogViewerWidget_."""

    _widget: "LogViewerWidget"

    def __init__(self, widget: "LogViewerWidget"):
        """Constructor.

        Parameters:
            widget: the widget to send the entries to
        """
        super().__init__()
        self._widget = widget

    def emit(self, record: LogRecord) -> None:
        try:
            msg = self.format(record)
            self._widget._add_entry(msg)
        except RecursionError:  # Python issue 36272
            raise
        except Exception:
            self.handleError(record)


class LogViewerWidget(WidgetWrap):
    """Log viewer widget that shows the last N entries of a Python logger."""

    _app: "Application"
    _handler: LogViewerWidgetHandler
    _list: List
    _logger: Optional[Logger]
    _max_items: int

    def __init__(
        self, app: "Application", logger: Optional[Logger] = None, max_items: int = 2048
    ):
        """Constructor.

        Parameters:
            app: the application that the widget lives in. It is used by the
                widget to ensure that the log entry list is updated only from
                the UI thread.
            logger: a Python logger whose records will be shown in this widget.
                Defaults to the top-level logger.
            max_items: maximum number of log items to show in the widget.
        """
        if logger is None:
            logger = getLogger()

        self._app = app
        self._handler = LogViewerWidgetHandler(self)
        self._list = List()
        self._logger = None
        self._max_items = int(max_items)

        self._handler.setFormatter(ColoredFormatterWrapper())

        super().__init__(self._list)

        self.logger = logger

    def add_marker(self) -> None:
        """Adds a new marker to the end of the list."""
        self._app.call_on_ui_thread(self._add_item_on_ui_thread, _create_marker())

    def focus_most_recent_item(self) -> None:
        """Sets the focus of the log viewer widget to the most recent item.

        This item is assumed to be at the bottom of the list of log items. The
        function is a no-op if the list is empty.
        """
        num_items = len(self._list.body)
        if num_items > 0:
            self._list.focus_position = num_items - 1

    @property
    def logger(self) -> Optional[Logger]:
        """The logger whose log entries the widget is showing."""
        return self._logger

    @logger.setter
    def logger(self, value):
        if self._logger is value:
            return

        if self._logger:
            self._logger.removeHandler(self._handler)

        self._logger = value

        if self._logger:
            self._logger.addHandler(self._handler)

    def _add_entry(self, text: str) -> None:
        """Adds a new log record to the end of the list.

        Parameters:
            text (str): the formatted text of the log record
        """
        self._app.call_on_ui_thread(self._add_item_on_ui_thread, SelectableText(text))

    def _add_item_on_ui_thread(self, widget: Widget) -> None:
        """Adds a new item to the end of the list.

        This method *must* be called on the UI thread. It may remove some of
        the topmost items from the list if there are too many items in the log.

        Parameters:
            widget (Widget): the widget to add
        """
        num_items = len(self._list.body)

        at_bottom = num_items == 0 or self._list.focus_position == (num_items - 1)

        self._list.add_widget(widget)

        if num_items >= self._max_items:
            self._list.remove_widget_at(0)
        else:
            num_items += 1

        if num_items > 0 and at_bottom:
            self._list.focus_position = num_items - 1
