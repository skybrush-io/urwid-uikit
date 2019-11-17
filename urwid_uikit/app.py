"""Base application class and application frame widget."""

from __future__ import absolute_import

import logging

from argparse import Namespace
from heapq import heapify
from inspect import getargspec
from urwid import (
    AttrMap,
    Columns,
    ExitMainLoop,
    Frame,
    MainLoop,
    Padding,
    SolidFill,
    Text,
    set_encoding,
)
from threading import current_thread
from time import time

from .concurrency import CancellableThread, SelectableQueue
from .menus import MenuOverlay

log = logging.getLogger(__name__)

__all__ = ("Application", "ApplicationFrame")


class Application(object):
    """Base class for urwid-based applications.

    Attributes:
        frame (urwid.Widget): the main widget of the application
        loop (urwid.MainLoop): the ``urwid`` main loop. Set to ``None``
            when the loop was not constructed yet.
        on_menu_invoked (callable): a function to call when the application is
            about to open a menu. It must return an urwid widget to show in the
            menu box, or ``None`` if the application does not have a menu.
    """

    palette = [
        ("bg", "light gray", "black"),
        ("header", "white", "dark blue", "standout"),
        ("footer", "white", "dark blue"),
        ("debug", "light gray", "dark gray"),
        ("dim", "black, bold", ""),
        ("error", "light red, bold", "", "standout"),
        ("success", "light green, bold", "", ""),
        ("title", "bold", ""),
        ("warning", "yellow", "", ""),
        ("list focus", "black", "dark cyan", "standout"),
        ("progress bar normal", "", "black", ""),
        ("progress bar complete", "black", "dark cyan", ""),
        ("progress bar smoothed part", "dark cyan", "black", ""),
        ("progress bar successful", "black", "dark green", ""),
        ("progress bar warning", "black", "brown", ""),
        ("progress bar error", "white", "dark red", ""),
        ("prompt", "white, bold", "", "standout"),
        ("prompt_error", "light red, bold", "", "standout"),
        ("standout", "white, bold", "", "standout"),
        ("download", "light green, bold", ""),
        ("upload", "light red, bold", ""),
        ("dialog", "white", "dark blue"),
        ("dialog in background", "black", "dark gray"),
        ("menu", "white", "dark blue"),
        ("menu in background", "black", "dark gray"),
        ("menu disabled", "dark gray", "dark blue"),
        ("menu focus", "black", "light cyan"),
    ]

    _REFRESH_EVENT = object()
    _WAKE_UP_EVENT = object()

    def __init__(self, encoding="utf8"):
        """Constructor."""
        self._auto_refresh = 0
        self._auto_refresh_timer = None
        self._events = SelectableQueue()
        self._menu_overlay = None
        self._my_thread = None
        self.loop = None
        self.frame = self.create_ui()
        self._menu_overlay = MenuOverlay(self.frame)
        self.loop = self._create_loop()

        if encoding:
            set_encoding(encoding)

    @property
    def auto_refresh(self):
        """Returns the value of the auto-refresh interval. When this
        property is set to a positive value X, the screen will be re-drawn
        automatically after every X seconds. When this property is set to
        ``False``, 0 or a negative number, the screen will not be re-drawn
        automatically; only when the urwid main loop decides to run an
        iteration. ``True`` means 0.1, meaning an automatic refresh ten
        times every second.
        """
        return self._auto_refresh

    @auto_refresh.setter
    def auto_refresh(self, value):
        if value is None or value is False:
            value = 0
        if value is True:
            value = 0.1
        value = max(value, 0)

        if value == self._auto_refresh:
            return

        if self._auto_refresh_timer is not None:
            self._auto_refresh_timer.cancel()
            self._auto_refresh_timer = None

        self._auto_refresh = value
        if value > 0:
            self._auto_refresh_timer = self.call_later(
                self.refresh, after=value, every=value
            )

    def call_later(self, callback, after=None, at=None, every=None, *args, **kwds):
        """Schedules a callback function to be called by the main loop of
        the application after a given number of seconds.

        Parameters:
            callback (callable): the callback to call
            after (Optional[float]): number of seconds after which the callback
                should be called. Negative or zero means that the callback
                is called immediately. When this parameter is given, ``to``
                must be ``None``.
            at (Optional[float]): the exact time (measured in the number of
                seconds elapsed since the UNIX epoch) when the callback
                should be called. When this parameter is given, ``after``
                must be ``None``.
            every (Optional[float]): when given, the callback will be
                recurrent and will be called every X seconds after the
                first call until the callback handle is cancelled.

        Returns:
            CallbackHandle: a handle to the scheduled callback function that
                can be used to reschedule it if needed
        """
        assert self.loop is not None, "main loop must be running"
        if after is None and at is None:
            if every is None:
                raise ValueError("exactly one of 'after' and 'at' must be " "given")
            else:
                after = 0
        if after is not None and at is not None:
            raise ValueError("exactly one of 'after' and 'at' must be given")
        if after is None:
            after = at - time()
        handle = CallbackHandle(self, callback, every, args, kwds)
        handle.reschedule(after=after)
        return handle

    def call_on_ui_thread(self, func, *args, **kwds):
        """Schedules the given function to be called by the main loop of
        the application as soon as possible, i.e. in the next iteration of
        the main loop.

        Parameters:
            func (callable): the function to call

        Returns:
            CallbackHandle: a handle to the scheduled function that can be
                used to reschedule it if needed
        """
        assert self.loop is not None, "main loop must be running"
        handle = CallbackHandle(self, func, None, args, kwds)
        handle.reschedule_now()
        return handle

    def cleanup_main_loop(self):
        """Cleans the ``urwid`` main loop after it has exited."""
        pass

    def configure_main_loop(self):
        """Configures the ``urwid`` main loop after it was created."""
        pass

    def create_daemon(self, func, thread_factory=CancellableThread, *args, **kwds):
        """Creates a daemon thread that will execute the given function
        and exits as soon as there are only other daemon threads left in
        the application (i.e. all non-daemon threads, including the main
        thread of the application, have exited).

        Refer to the documentation of ``create_worker()`` for more details
        about the arguments.

        Parameters:
            func (callable): the function to execute in the daemon thread.
            thread_factory (callable): the function that is used to create
                a new thread. It will be called in a manner similar to the
                constructor of the Thread_ class.

        Returns:
            Thread: a daemon thread that is ready to be started
        """
        daemon = self.create_worker(func, thread_factory=thread_factory, *args, **kwds)
        daemon.daemon = True
        return daemon

    def create_worker(self, func, thread_factory=CancellableThread, *args, **kwds):
        """Creates a worker thread that will execute the given function.
        Any remaining positional and keyword arguments are passed on to the
        function when it is invoked by the worker thread.

        When the function has a keyword argument named ``ui``, it will
        be given an object with the following methods:

        - ``call()`` -- calls a function on the UI thread (i.e. the thread
          running the ``urwid`` main loop). The signature of this function
          is equivalent to the ``call_ui_thread()`` function of the
          Application_ class.

        - ``call_later()`` -- calls a function on the UI thread after a
          delay. The signature of this function is equivalent to the
          ``call_later()`` function of the Application_ class.

        - ``inject_event()`` -- injects an event into the event loop of the
          UI thread. The signature of this function is equivalent to the
          ``inject_event()`` function of the Application_ class.

        - ``is_stop_requested()`` -- returns whether the user has requested
          the worker to stop whatever it is doing and return at the earliest
          possible occasion

        - ``refresh()`` -- forces a refresh of the user interface displayed
          by the Application_ class.

        Parameters:
            func (callable): the function to execute in the worker thread.
            thread_factory (callable): the function that is used to create
                a new thread. It will be called in a manner similar to the
                constructor of the Thread_ class.

        Returns:
            Thread: a worker thread that is ready to be started
        """
        arg_names, _, _, _ = getargspec(func)
        context = Namespace(
            call=self.call_on_ui_thread,
            call_later=self.call_later,
            inject_event=self.inject_event,
            is_stop_requested=None,
            refresh=self.refresh,
        )

        if "ui" in arg_names:
            if not kwds:
                kwds = {}
            kwds["ui"] = context

        thread = thread_factory(target=func, args=args, kwargs=kwds)
        context.is_stop_requested = lambda: thread.is_stop_requested

        return thread

    def create_ui(self):
        """Creates the main widget of the application that will be run by
        the ``urwid`` main loop.

        Returns:
            urwid.Widget: the main widget of the application
        """
        raise NotImplementedError

    def get_event_loop(self):
        """Returns the event loop instance to register in the main loop.
        Default is a new SelectEventLoop instance. Override this method if
        you need a different event loop, e.g., for integration with asyncio.
        """
        return None

    def inject_event(self, event):
        """Injects an arbitrary event object into the event queue of the
        application. This will make urwid run another iteration of its
        event loop and also force a screen refresh.

        Injected events may be processed by overriding ``process_event()``.
        It will be called for every event injected via ``inject_event()``
        before the screen is redrawn the next time. The ordering of events
        is preserved.
        """
        self._events.put(event)

    def invoke_menu(self):
        """Invokes the main menu of the application.

        Returns:
            bool: whether the main menu was shown. If the application has
                no attribute named `on_menu_invoked()`, returns ``False`` as
                there is no main menu associated to the application.
        """
        func = getattr(self, "on_menu_invoked", None)
        if func is not None:
            items = func()
            if items:
                self._menu_overlay.open_menu(items, title="Main menu")
            return True
        else:
            return False

    def on_input(self, input):
        """Callback method that is called by ``urwid`` for unhandled
        keyboard input.

        The default implementation treats ``q`` and ``Q`` as a command to quit
        the main application so it terminates the main loop. ``Esc`` will open
        the main menu of the application if it has one, otherwise it will also
        quit the main application.
        """
        if input in ("q", "Q"):
            self.quit()
        elif input == "esc":
            self.invoke_menu() or self.quit()

    def process_event(self, event):
        """Processes the given event that was dispatched via
        ``inject_event()`` into the main loop of the application.
        """
        pass

    def refresh(self):
        """Forces the application to refresh its main widget. Useful when
        the state of a widget changed in another thread.
        """
        self.inject_event(self._REFRESH_EVENT)

    def run(self):
        """Creates and runs the main loop of the console GUI."""
        self._my_thread = current_thread()

        self.loop.watch_file(self._events.fd, self._event_callback)

        self.configure_main_loop()
        try:
            self.loop.run()
        finally:
            self.loop.remove_watch_file(self._events.fd)
            self.cleanup_main_loop()

    def quit(self):
        """Quits the application."""
        raise ExitMainLoop()

    def _create_loop(self):
        """Creates the main loop of the application. Not to be overridden;
        override ``configure_main_loop()``, ``cleanup_main_loop()`` and
        ``get_event_loop()`` instead.
        """
        event_loop = self.get_event_loop()
        return MainLoop(self._menu_overlay, self.palette, event_loop=event_loop, unhandled_input=self.on_input)

    def _event_callback(self):
        """Handler called by the main loop when some events were injected
        into the main loop via ``inject_event()``, before the next screen
        refresh.
        """
        pending_events = self._events.get_all()
        for event in pending_events:
            if event is self._REFRESH_EVENT:
                pass
            elif event is self._WAKE_UP_EVENT:
                pass
            else:
                self.process_event(event)

    def _wake_up(self):
        """Forces the application to wake up if the main loop is currently
        in the idle state. Useful when another thread scheduled a new alarm
        or added a new file descriptor to watch.
        """
        if self._my_thread is None:
            return
        if current_thread() is not self._my_thread:
            self.inject_event(self._WAKE_UP_EVENT)


class CallbackHandle(object):
    """Handle to the invocation of a callback function scheduled with
    ``Application.call_later()``.

    Attributes:
        callback (callable): the callable to call
        args: the positional arguments to pass to the callable
        kwds: the keyword arguments to pass to the callable
        interval (Optional[float]): the delay between consecutive calls to
            the callback if the callback is recurrent, or ``None`` if the
            callback is one-shot
        called (bool): whether the callback was called at least once
        num_called (int): the number of times the callback was called
    """

    def __init__(self, app, callback, interval, args, kwds):
        """Constructor."""
        self._app = app
        self._num_called = 0

        self._handle = None
        self._next_call_at = None

        self.debug = False

        self.callback = callback
        self.interval = interval
        self.args = args
        self.kwds = kwds

    def _call(self, loop, user_data):
        """Calls the callback stored in the handle right now."""
        # Fix a bug in urwid.SelectEventLoop
        if hasattr(loop, "event_loop"):
            if hasattr(loop.event_loop, "_alarms"):
                heapify(loop.event_loop._alarms)

        self._num_called += 1
        self._handle = None
        self._next_call_at = None
        try:
            self.callback(*self.args, **self.kwds)
        finally:
            if self.interval is not None and self.interval > 0:
                self.reschedule(after=self.interval)

    @property
    def called(self):
        """Returns whether the callback was called at least once."""
        return self._num_called > 0

    def cancel(self):
        """Cancels any scheduled call to the callback.

        If the callback was called already and it is not recurrent, this
        function is a no-op.
        """
        handle, self._handle = self._handle, None
        self._next_call_at = None
        if handle is not None:
            self._app.loop.remove_alarm(handle)
            self._app._wake_up()

    def delay_next_call(self, by):
        """Delays the next scheduled call of the callback with the given
        number of seconds.

        If the callback was called already and it is not recurrent, this
        function is a no-op. The function is also a no-op if the callback
        has no scheduled next call.

        Parameters:
            by (float): the number of seconds to delay the next call by

        Returns:
            bool: True if a new call was scheduled, False otherwise
        """
        if self._next_call_at is None:
            return False
        elif self.interval is None and self.called:
            return False
        else:
            return self.reschedule(to=self._next_call_at + by)

    @property
    def num_called(self):
        """Returns how many times the callback was called so far."""
        return self._num_called

    def reschedule(self, after=None, to=None):
        """Reschedules the callback to the current time plus the given
        number of seconds, or to a given timestamp.

        Parameters:
            after (Optional[float]): the number of seconds that must pass
                before the callback is called, starting from now. If this
                parameter is given, ``to`` must be ``None``.
            to (Optional[float]): the exact time (measured in seconds since
                the UNIX epoch) when the callback must be called. If this
                parameter is given, ``after`` must be ``None``.

        Returns:
            bool: True if the rescheduling was successful, False if the
                callback was called already
        """
        if after is None and to is None:
            raise ValueError("exactly one of 'after' or 'to' must be given")
        if after is not None and to is not None:
            raise ValueError("exactly one of 'after' or 'to' must be given")

        self.cancel()

        now = time()
        if to is not None:
            after = to - now
        after = max(after, 0)
        self._next_call_at = now + after

        # Even if after == 0, we cannot call the callback directly because
        # we want to ensure that it is called by the urwid main thread.
        # So we schedule the callback no matter what.
        if self.debug:
            log.info("%r: Setting alarm in %.4f" % (self, after))

        self._handle = self._app.loop.set_alarm_in(after, self._call)
        self._app._wake_up()

        return True

    def reschedule_now(self):
        """Schedules the callback to be called as soon as possible in the
        next iteration of the urwid main loop.
        """
        return self.reschedule(after=0)

    @property
    def seconds_left(self):
        """Returns the number of seconds left till the next call."""
        if self._next_call_at is not None:
            return max(self._next_call_at - time(), 0.0)
        else:
            return 0.0


class ApplicationFrame(Frame):
    """Frame for the main application with a configurable header and a
    status bar.

    Attributes:
        header_label (urwid.Text): the default label in the header component
        footer_label (urwid.Text): the default label in the footer component
    """

    def __init__(self, body=None):
        """Constructor."""
        self.header_columns = self._construct_header()
        self.footer_columns = self._construct_footer()

        super(ApplicationFrame, self).__init__(
            body or SolidFill(),
            AttrMap(Padding(self.header_columns, left=1, right=1), "header"),
            AttrMap(Padding(self.footer_columns, left=1, right=1), "footer"),
        )

    def _construct_header(self):
        """Constructs and returns the urwid component to place in the
        header of the application.
        """
        self.header_label = Text(("header", ""), wrap="clip")
        return Columns([self.header_label], dividechars=1)

    def _construct_footer(self):
        """Constructs and returns the urwid component to place in the
        footer of the application.
        """
        self.footer_label = Text(("footer", ""), wrap="clip")
        return Columns([self.footer_label], dividechars=1)

    def add_header_widget(self, widget, options=None, index=None):
        """Adds a new widget to the header.

        Parameters:
            widget (urwid.Widget): the widget to add
            options (tuple): an options tuple for the widget, as returned
                by the ``options()`` method of ``urwid.Columns()``
            index (Optional[int]): the index where the new widget will be
                added in the header. ``None`` means the end of the header.
        """
        self._add_widget_to(self.header_columns, widget, options, index)

    def add_footer_widget(self, widget, options=None, index=None):
        """Adds a new widget to the footer.

        Parameters:
            widget (urwid.Widget): the widget to add
            options (tuple): an options tuple for the widget, as returned
                by the ``options()`` method of ``urwid.Columns()``
            index (Optional[int]): the index where the new widget will be
                added in the header. ``None`` means the end of the header.
        """
        self._add_widget_to(self.footer_columns, widget, options, index)

    def _add_widget_to(self, parent, widget, options, index):
        if options is None:
            options = parent.options("pack")
        elif isinstance(options, int):
            options = parent.options("given", options)
        elif isinstance(options, float):
            options = parent.options("weight", options)
        elif isinstance(options, tuple):
            pass
        else:
            raise TypeError(
                "expected None, int, float or tuple as "
                "options, got: {0!r}".format(type(options))
            )

        if index is None:
            parent.contents.append((widget, options))
        else:
            parent.contents.insert(index, (widget, options))

    @property
    def status(self):
        """Status message shown in the footer."""
        return self.footer_label.get_text()

    @status.setter
    def status(self, value):
        """Sets the status message shown in the footer."""
        self.footer_label.set_text(value)

    @property
    def title(self):
        """Title text shown in the header."""
        return self.header_label.get_text()

    @title.setter
    def title(self, value):
        """Sets the title text shown in the header."""
        self.header_label.set_text(value)
