"""Variant of the application class with a pre-configured asynchronous
event loop based on Trio.
"""

from .app import Application

__all__ = ("AsyncApplication",)


class AsyncApplication(Application):
    """Asynchronous application class that provides a ``run_async()`` method
    to run the application in an already existing event loop.
    """

    def create_event_loop(self):
        from urwid import TrioEventLoop

        return TrioEventLoop()

    async def run_async(self):
        """Runs the application and blocks execution until the application
        exits, allowing other asynchronous task to run in the background.
        """
        if not hasattr(self.loop.event_loop, "run_async"):
            raise RuntimeError("event loop needs a run_async() method")

        with self.loop.start():
            await self.loop.event_loop.run_async()
