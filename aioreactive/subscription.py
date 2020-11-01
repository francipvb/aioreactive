import asyncio
import logging
from collections.abc import Awaitable
from types import TracebackType
from typing import Any, Callable, Generator, Optional, Type, TypeVar

from fslash.system import AsyncDisposable

from .observers import AsyncAwaitableObserver
from .types import AsyncObservable, AsyncObserver

log = logging.getLogger(__name__)

TSource = TypeVar("TSource")


class AsyncSubscription(Awaitable[TSource], AsyncDisposable):
    """Async stream factory.

    A helper class that makes it possible to subscribe both
    using await and async-with. You will most likely not use this class
    directly, but it will created when using subscribe_async()."""

    def __init__(
        self,
        subscribe: Callable[[AsyncObserver[TSource]], Awaitable[AsyncDisposable]],
        observer: AsyncObserver[TSource],
    ):
        self._subscribe = subscribe
        self._observer = observer

        self._subscription: Optional[AsyncDisposable] = None

    async def run(self) -> AsyncDisposable:
        """Awaits stream creation.

        Awaits until stream has been created, and returns the new
        stream."""

        log.debug("AsyncSubscription:run()")
        self._subscription = await self._subscribe(self._observer)
        return self._subscription

    async def dispose_async(self) -> None:
        """Closes stream."""
        if self._subscription is not None:
            await self._subscription.dispose_async()

    async def __aenter__(self) -> AsyncDisposable:
        """Awaits subscription creation."""
        return await self.run()

    async def __aexit__(
        self, exctype: Optional[Type[BaseException]], excinst: Optional[BaseException], exctb: Optional[TracebackType]
    ):
        """Awaits unsubscription."""
        if self._subscription is not None:
            await self._subscription.dispose_async()

    def __await__(self) -> Generator[Any, None, AsyncDisposable]:
        """Await stream creation."""

        log.debug("AsyncSubscription:__await__()")
        return self.run().__await__()


async def chain(source: AsyncObservable[TSource], observer: AsyncObserver[TSource]) -> AsyncDisposable:
    """Chains an async observer with an async observable.

    Performs the chaining done internally by most operators. A much
    more light-weight version of subscribe()."""

    log.debug("AsyncSubscription:chain()")
    return await source.subscribe_async(observer)


def subscription(
    subscribe: Callable[[AsyncObserver[TSource]], Awaitable[AsyncDisposable]], observer: AsyncObserver[TSource]
) -> AsyncSubscription:
    """Start streaming source into observer.

    Returns an AsyncSubscription that is lazy in the sense that it will
    not start the source before it's either awaited or entered using
    async-with.

    Examples:

    1. Awaiting stream with explicit cancel:

    stream = await subscribe(source, observer)
    async for x in stream:
        print(x)

    stream.cancel()

    2. Start streaming with a context manager:

    async with subscribe(source, observer) as stream:
        async for x in stream:
            print(x)

    3. Start streaming without a specific observer

    async with subscribe(source) as stream:
        async for x in stream:
            print(x)

    Keyword arguments:
    observer -- Optional AsyncObserver that will receive all events sent through
        the stream.

    Returns AsyncStreamFactory that may either be awaited or entered
    using async-for.
    """
    return AsyncSubscription(subscribe, observer)


async def run(
    source: AsyncObservable[TSource], observer: Optional[AsyncAwaitableObserver[TSource]] = None, timeout: int = 2
) -> TSource:
    """Run the source with the given observer.

    Similar to subscribe() but also awaits until the stream closes and
    returns the final value.

    Keyword arguments:
    timeout -- Seconds before timing out in case source never closes.

    Returns last event sent through the stream. If any values have been
    sent through the stream it will return the last value. If the stream
    is closed without any previous values it will throw
    StopAsyncIteration. For any other errors it will throw the
    exception.
    """

    # For run we need a noopobserver if no observer is specified to avoid
    # blocking the last single stream in the chain.
    observer_: AsyncObserver[TSource] = observer or AsyncAwaitableObserver()
    await subscription(source.subscribe_async, observer_)
    return await asyncio.wait_for(observer_, timeout)
