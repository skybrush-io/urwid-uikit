"""Concurrency- and threading-related classes and functions."""

from __future__ import annotations

import errno
import logging
import os
import queue

from threading import Condition, Event, Thread
from typing import Callable, Generic, List, Optional, Tuple, TypeVar, Union

__all__ = (
    "AtomicCounter",
    "CancellableThread",
    "SelectableQueue",
    "ThreadPool",
    "WorkerThread",
)

log = logging.getLogger(__name__)


T = TypeVar("T")


class AtomicCounter:
    """Integer counter object that can be increased and decreased atomically
    and that provides an atomic "wait until nonzero and then clear" method
    as well.
    """

    _value: int
    _condition: Condition

    def __init__(self, value: int = 0):
        """Constructor.

        Parameters:
            value (int): the initial value
        """
        self._value = value
        self._condition = Condition()

    def decrease(self, delta: int = 1) -> None:
        """Increases the value of the counter atomically with the given value.

        Parameters:
            delta: the number to increase the counter with
        """
        return self.increase(-delta)

    def increase(self, delta: int = 1) -> None:
        """Increases the value of the counter atomically with the given value.

        Parameters:
            delta: the number to increase the counter with
        """
        with self._condition:
            self._value += delta
            self._condition.notify_all()

    @property
    def value(self) -> int:
        """The current value of the counter."""
        return self._value

    @value.setter
    def value(self, new_value: int) -> None:
        with self._condition:
            self._value = new_value
            self._condition.notify_all()

    def wait(self, timeout: Optional[float] = None) -> int:
        """Waits until the counter becomes nonzero, then returns the value of
        the counter.

        Parameters:
            timeout: when not `None`, specifies the maximum number of seconds to
                wait for the counter to become nonzero

        Returns:
            the value of the counter
        """
        with self._condition:
            if timeout is None:
                while self._value == 0:
                    self._condition.wait()
            else:
                if self._value == 0:
                    self._condition.wait(timeout)
            return self._value

    def wait_and_reset(self, timeout: Optional[float] = None) -> int:
        """Waits until the counter becomes nonzero, then returns the value of
        the counter and resets the counter to zero.

        Parameters:
            timeout: when not `None`, specifies the maximum number of seconds to
                wait for the counter to become nonzero

        Returns:
            the value of the counter before it was reset to zero
        """
        with self._condition:
            if timeout is None:
                while self._value == 0:
                    self._condition.wait()
            else:
                if self._value == 0:
                    self._condition.wait(timeout)

            result = self._value
            self._value = 0
            if result != 0:
                self._condition.notify_all()

            return result


class CancellableThread(Thread):
    """A thread subclass that can be cancelled by invoking its
    ``request_stop()`` method, assuming that the body of the thread
    regularly checks the ``is_stop_requested`` property.
    """

    def __init__(self, *args, **kwds):
        super(CancellableThread, self).__init__(*args, **kwds)
        self._stop_event = Event()

    @property
    def is_stop_requested(self) -> bool:
        """Returns whether the thread was requested to stop."""
        return self._stop_event.is_set()

    def request_stop(self) -> None:
        """Requests the thread to stop as soon as possible."""
        self._stop_event.set()


class SelectableQueue(Generic[T]):
    """Python queue class that wraps another queue and provides a file
    descriptor that becomes readable when the queue becomes non-empty.
    """

    _notifier: "FDNotifier"
    _queue: queue.Queue[T]

    def __init__(
        self,
        queue_or_factory: Union[
            Callable[[], queue.Queue[T]], queue.Queue[T]
        ] = queue.Queue,
    ):
        """Constructor.

        Parameters:
            queue_or_factory: a Python queue class to wrap or a callable
                that creates such a queue when called.
        """
        if callable(queue_or_factory):
            self._queue = queue_or_factory()
        else:
            self._queue = queue_or_factory
        self._notifier = FDNotifier()

    def __del__(self):
        self.close()

    def close(self) -> None:
        """Closes the queue. No items should be added to the queue after it was
        closed.
        """
        self._notifier.close()

    @property
    def fd(self) -> int:
        """The file descriptor that becomes readable when items are put
        into the queue.
        """
        return self._notifier.fd

    def get_all(self) -> List[T]:
        """Returns all pending items from the queue without blocking.

        Returns:
            the list of items retrieved from the queue; may be empty
        """
        # We are draining the notifier first. This is important -- if someone
        # else calls put() while we are running get_all(), it may happen
        # that the notifier remains readable while there are no more items
        # in the queue, but in the worst case the user calls get_all()
        # again and gets an empty list. If we drained the notifier at the
        # end, it could have happened that someone calls put() after the
        # result vector was created but before the notifier was drained,
        # and we end up with some items in the queue without the notifier
        # fd being readable.

        self._notifier.drain()

        result: List[T] = []
        try:
            while True:
                result.append(self._queue.get_nowait())
        except queue.Empty:
            pass

        return result

    def put(self, item: T, block: bool = True, timeout: Optional[float] = None) -> None:
        """Puts an item in the queue.

        Parameters:
            item (object): the item to put in the queue
            block (bool): whether to block if necessary until a free slot
                is available
            timeout (Optional[float]): maximum number of seconds to wait for
                a free slot

        Raises:
            Queue.Full: if the queue is full and no slot became available
                within the given timeout (or if we were not allowed to block)
        """
        self._queue.put(item, block, timeout)
        self._notifier.notify()

    def put_nowait(self, item: T) -> None:
        """Puts an item in the queue if it is not full.

        Parameters:
            item: the item to put in the queue

        Raises:
            Queue.Full: if the queue is full
        """
        return self.put(item, block=False)


class WorkerThread(CancellableThread):
    """Worker thread that receives callable objects from a queue and executes
    them one by one.
    """

    def __init__(self, queue, *args, **kwds):
        """Constructor.

        Parameters:
            queue (Queue): the queue from which the worker thread receives
                its jobs
        """
        super(WorkerThread, self).__init__(*args, **kwds)
        self.daemon = True
        self._queue = queue

    def request_stop(self):
        """Requests the thread to stop as soon as possible."""
        super(WorkerThread, self).request_stop()
        self._queue.put(None)  # to unblock the main loop

    def run(self):
        while not self.is_stop_requested:
            job = self._queue.get()
            if job is None:
                continue

            error, result = None, None
            try:
                result = job._execute()
            except Exception as ex:
                error = ex
            finally:
                self._queue.task_done()

            job._notify(result, error)


class ThreadPoolJob(Generic[T]):
    """Object representing a job that was submitted to the thread pool."""

    _func: Callable[..., T]
    _result_and_error: Optional[Tuple[Optional[T], Optional[Exception]]]

    _on_error: Optional[Callable[[Exception], None]]
    _on_result: Optional[Callable[[T], None]]
    _on_terminated: Optional[Callable[[Optional[Exception]], None]]

    def __init__(self, func: Callable[..., T], args, kwds):
        """Constructor.

        Parameters:
            func (callable): the function to call
            args: positional arguments to pass to the function
            kwds: keyword arguments to pass to the function
        """
        self._func = func
        self._args = args
        self._kwds = kwds

        self._result_and_error = None

        self._on_result = None
        self._on_error = None
        self._on_terminated = None

    def _execute(self) -> T:
        """Executes the job in the current thread."""
        return self._func(*self._args, **self._kwds)

    def _notify(self, result: Optional[T], error: Optional[Exception]) -> None:
        """Notifies the job about its execution result so it can call the
        appropriate handlers.
        """
        if self._result_and_error is not None:
            raise ValueError("job cannot be resolved twice")

        self._result_and_error = result, error

        self._call_result_handler_if_needed()
        self._call_error_handler_if_needed()
        self._call_termination_handler_if_needed()

    def _call_error_handler_if_needed(self) -> None:
        if self._result_and_error is None or self._on_error is None:
            return

        _, error = self._result_and_error
        if error is not None:
            self._on_error(error)

    def _call_result_handler_if_needed(self) -> None:
        if self._result_and_error is None or self._on_result is None:
            return

        result, error = self._result_and_error
        if error is None:
            self._on_result(result)

    def _call_termination_handler_if_needed(self) -> None:
        if self._result_and_error is None or self._on_terminated is None:
            return

        _, error = self._result_and_error
        self._on_terminated(error)

    def then(
        self,
        func: Callable[[T], None],
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        """Registers a handler function to call when the job has finished
        successfully.

        Parameters:
            func: the callable to call when the job has finished successfully.
                It will be called with the return value of the job function as
                its only argument.
            on_error: the callable to call when the job has terminated with an
                error (i.e. when an exception was thrown). It will be called
                with the exception as its only argument.
        """
        if self._on_result is not None:
            raise ValueError("multiple result handlers are not supported")
        if not callable(func):
            raise TypeError("result handler must be callable")
        self._on_result = func

        self._call_result_handler_if_needed()

        if on_error is not None:
            self.catch_(on_error)

    def catch_(self, func: Callable[[Exception], None]) -> None:
        """Registers a handler function to call when the job has finished
        with an error.

        Parameters:
            func: the callable to call when the job has terminated with an
                error (i.e. when an exception was thrown). It will be called
                with the exception as its only argument.
        """
        if self._on_error is not None:
            raise ValueError("multiple error handlers are not supported")
        if not callable(func):
            raise TypeError("error handler must be callable")
        self._on_error = func

        self._call_error_handler_if_needed()

    def finally_(self, func: Callable[[Optional[Exception]], None]) -> None:
        """Registers a handler function to call when the job has finished,
        irrespectively of whether it has finished with an error it has
        finished successfully.

        Parameters:
            func (callable): the callable to call. It will be called with a
                single argument, which is `None` if the execution was successsful
                or the error that happened if the execution was not successful.
        """
        if self._on_terminated is not None:
            raise ValueError("multiple termination handlers are not supported")
        if not callable(func):
            raise TypeError("termination handler must be callable")
        self._on_terminated = func

        self._call_termination_handler_if_needed()


class ThreadPool:
    """Simple thread pool object that manages multiple worker threads and
    distributes tasks between them.
    """

    _queue: queue.Queue[ThreadPoolJob]
    _threads: List[WorkerThread]

    def __init__(self, num_threads: int = 5):
        """Constructor.

        Parameters:
            num_threads: the number of threads in the pool
        """
        self._queue = queue.Queue(num_threads)
        self._threads = [WorkerThread(self._queue) for _ in range(num_threads)]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        while self._threads:
            thread = self._threads.pop()
            thread.request_stop()

    def submit(self, *args, **kwds) -> ThreadPoolJob:
        """Submits a new job to the thread pool.

        The first positional argument is the function to call when the job is
        executed. Additional positional and keyword arguments are passed down
        to the function being called.
        """
        if not args:
            raise TypeError("at least one positional argument is needed")

        job = ThreadPoolJob(args[0], args[1:], kwds)
        self._queue.put(job)

        return job

    def wait_for_completion(self) -> None:
        self._queue.join()

    def __del__(self):
        self.stop()


class _PosixFDNotifier:
    """Notifier object that provides a file descriptor that becomes ready
    for reading whenever the user calls the ``notify()`` method of the
    notifier.

    This is useful in situations when we want to wait for an event in one
    thread while another thread is blocked in a ``select()`` call. We can
    then add the file descriptor to the ``select()`` call to ensure that
    the call returns whenever ``notify()`` is called from another thread.

    This class works on POSIX-compatible platforms only. In case you are
    curious, this class implements the "self-pipe trick". We create a dummy
    anonymous pipe, then return the readable end of the pipe to the user.
    Calling ``notify()`` writes a character to the writable end of the
    pipe, unblocking the readable end.

    It is the responsibility of the user to call ``drain()`` when the
    readable end becomes readable.

    Attributes:
        fd (int): the file descriptor to block on in a ``select()`` call
    """

    _readable_pipe: Optional[int]
    _writable_pipe: Optional[int]

    def __init__(self):
        self._readable_pipe, self._writable_pipe = self._prepare_pipes()

    def __del__(self):
        self.close()

    def drain(self) -> None:
        """Drains the readable end of the pipe by reading everything that is
        currently available.
        """
        pipe = self._readable_pipe
        if not pipe:
            return

        while True:
            try:
                os.read(pipe, 1)
            except OSError as ex:
                if ex.errno == errno.EAGAIN:
                    # The pipe is drained
                    return
                else:
                    raise

    @property
    def fd(self) -> int:
        assert self._readable_pipe is not None, "queue is already closed"
        return self._readable_pipe

    def _prepare_pipes(self):
        """Prepares the input and output pipes."""
        rd, wr = os.pipe()
        os.set_blocking(rd, False)
        os.set_blocking(wr, False)
        return rd, wr

    def close(self) -> None:
        """Closes the notifier. No-op if the notifier is already closed."""
        if self._readable_pipe is not None:
            pipe, self._readable_pipe = self._readable_pipe, None
            os.close(pipe)
        if self._writable_pipe is not None:
            pipe, self._writable_pipe = self._writable_pipe, None
            os.close(pipe)

    def notify(self) -> None:
        assert self._writable_pipe is not None, "queue is already closed"
        os.write(self._writable_pipe, b"x")


FDNotifier = _PosixFDNotifier
