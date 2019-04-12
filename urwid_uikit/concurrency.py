"""Concurrency- and threading-related classes and functions."""

import errno
import logging
import os
import queue

from threading import Condition, Event, Thread


__all__ = (
    "AtomicCounter", "CancellableThread", "SelectableQueue", "ThreadPool",
    "WorkerThread"
)

log = logging.getLogger(__name__)


class AtomicCounter(object):
    """Integer counter object that can be increased and decreased atomically
    and that provides an atomic "wait until nonzero and then clear" method
    as well.
    """

    def __init__(self, value=0):
        """Constructor.

        Parameters:
            value (int): the initial value
        """
        self._value = value
        self._condition = Condition()

    def decrease(self, delta=1):
        """Increases the value of the counter atomically with the given value.

        Parameters:
            delta (int): the number to increase the counter with
        """
        return self.increase(-delta)

    def increase(self, delta=1):
        """Increases the value of the counter atomically with the given value.

        Parameters:
            delta (int): the number to increase the counter with
        """
        with self._condition:
            self._value += delta
            self._condition.notify_all()

    @property
    def value(self):
        """The current value of the counter."""
        return self._value

    @value.setter
    def value(self, new_value):
        with self._condition:
            self._value = new_value
            self._condition.notify_all()

    def wait(self, timeout=None):
        """Waits until the counter becomes nonzero, then returns the value of
        the counter.

        Parameters:
            timeout (Optional[float]): when not `None`, specifies the maximum
                number of seconds to wait for the counter to become nonzero
        """
        with self._condition:
            if timeout is None:
                while self._value == 0:
                    self._condition.wait()
            else:
                if self._value == 0:
                    self._condition.wait(timeout)
            return self._value

    def wait_and_reset(self, timeout=None):
        """Waits until the counter becomes nonzero, then returns the value of
        the counter and resets the counter to zero.

        Parameters:
            timeout (Optional[float]): when not `None`, specifies the maximum
                number of seconds to wait for the counter to become nonzero
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
    def is_stop_requested(self):
        """Returns whether the thread was requested to stop."""
        return self._stop_event.is_set()

    def request_stop(self):
        """Requests the thread to stop as soon as possible."""
        self._stop_event.set()


class SelectableQueue(object):
    """Python queue class that wraps another queue and provides a file
    descriptor that becomes readable when the queue becomes non-empty.
    """

    def __init__(self, queue_or_factory=queue.Queue):
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
        self._notifier.close()

    @property
    def fd(self):
        """The file descriptor that becomes readable when items are put
        into the queue.
        """
        return self._notifier.fd

    def get_all(self, block=True, timeout=None):
        """Returns all pending items from the queue without blocking.

        Returns:
            List[object]: the list of items retrieved from the queue; may be
                empty if ``block`` is ``False``
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

        result = []
        try:
            while True:
                result.append(self._queue.get_nowait())
        except queue.Empty:
            pass

        return result

    def put(self, item, block=True, timeout=None):
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

    def put_nowait(self, item):
        """Puts an item in the queue if it is not full.

        Parameters:
            item (object): the item to put in the queue

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
        self._queue.put(None)      # to unblock the main loop

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


class ThreadPoolJob(object):
    """Object representing a job that was submitted to the thread pool."""

    def __init__(self, func, args, kwds):
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

    def _execute(self):
        """Executes the job in the current thread."""
        return self._func(*self._args, **self._kwds)

    def _notify(self, result, error):
        """Notifies the job about its execution result so it can call the
        appropriate handlers.
        """
        if self._result_and_error is not None:
            raise ValueError("job cannot be resolved twice")

        self._result_and_error = result, error

        self._call_result_handler_if_needed()
        self._call_error_handler_if_needed()
        self._call_termination_handler_if_needed()

    def _call_error_handler_if_needed(self):
        if self._result_and_error is None or self._on_error is None:
            return

        _, error = self._result_and_error
        if error is not None:
            self._on_error(error)

    def _call_result_handler_if_needed(self):
        if self._result_and_error is None or self._on_result is None:
            return

        result, error = self._result_and_error
        if error is None:
            self._on_result(result)

    def _call_termination_handler_if_needed(self):
        if self._result_and_error is None or self._on_terminated is None:
            return

        _, error = self._result_and_error
        if error is None:
            self._on_terminated()
        else:
            self._on_terminated(error)

    def then(self, func, on_error=None):
        """Registers a handler function to call when the job has finished
        successfully.

        Parameters:
            func (callable): the callable to call when the job has
                finished successfully. It will be called with the return value
                of the job function as its only argument.
            on_error (Optional[callable]): the callable to call when the
                job has terminated with an error (i.e. when an exception was)
                thrown. It will be called with the exception as its only
                argument.
        """
        if self._on_result is not None:
            raise ValueError("multiple result handlers are not supported")
        if not callable(func):
            raise TypeError("result handler must be callable")
        self._on_result = func

        self._call_result_handler_if_needed()

        if on_error is not None:
            self.catch_(on_error)

    def catch_(self, func):
        """Registers a handler function to call when the job has finished
        with an error.

        Parameters:
            func (callable): the callable to call when the job has terminated
                with an error (i.e. when an exception was) thrown. It will be
                called with the exception as its only argument.
        """
        if self._on_error is not None:
            raise ValueError("multiple error handlers are not supported")
        if not callable(func):
            raise TypeError("error handler must be callable")
        self._on_error = func

        self._call_error_handler_if_needed()

    def finally_(self, func):
        """Registers a handler function to call when the job has finished,
        irrespectively of whether it has finished with an error it has
        finished successfully.

        Parameters:
            func (callable): the callable to call. It will be called with no
                arguments if the execution was successful, otherwise it will be
                called with the error as its only argument.
        """
        if self._on_terminated is not None:
            raise ValueError("multiple termination handlers are not supported")
        if not callable(func):
            raise TypeError("termination handler must be callable")
        self._on_terminated = func

        self._call_termination_handler_if_needed()


class ThreadPool(object):
    """Simple thread pool object that manages multiple worker threads and
    distributes tasks between them.
    """

    def __init__(self, num_threads=5):
        """Constructor.

        Parameters:
            num_threads (int): the number of threads in the pool
        """
        self._queue = queue.Queue(num_threads)
        self._threads = [WorkerThread(self._queue) for _ in range(num_threads)]
        for thread in self._threads:
            thread.start()

    def stop(self):
        while self._threads:
            thread = self._threads.pop()
            thread.request_stop()

    def submit(self, *args, **kwds):
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

    def wait_for_completion(self):
        self._queue.join()

    def __del__(self):
        self.stop()


class _PosixFDNotifier(object):
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

    def __init__(self):
        self._readable_pipe, self._writable_pipe = None, None
        self._readable_pipe, self._writable_pipe = self._prepare_pipes()

    def __del__(self):
        self.close()

    def drain(self):
        """Drains the readable end of the pipe by reading everything that is
        currently available.
        """
        while True:
            try:
                os.read(self._readable_pipe, 1)
            except OSError as ex:
                if ex.errno == errno.EAGAIN:
                    # The pipe is drained
                    return
                else:
                    raise

    @property
    def fd(self):
        return self._readable_pipe

    @staticmethod
    def _set_nonblocking(fd):
        """Sets a file descriptor to non-blocking IO mode."""
        import fcntl     # deferred import; not available on Win32
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def _prepare_pipes(self):
        """Prepares the input and output pipes."""
        rd, wr = os.pipe()
        self._set_nonblocking(rd)
        self._set_nonblocking(wr)
        return rd, wr

    def close(self):
        if self._readable_pipe is not None:
            pipe, self._readable_pipe = self._readable_pipe, None
            os.close(pipe)
        if self._writable_pipe is not None:
            pipe, self._writable_pipe = self._writable_pipe, None
            os.close(pipe)

    def notify(self):
        os.write(self._writable_pipe, b'x')


FDNotifier = _PosixFDNotifier
