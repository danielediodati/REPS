"""The guarantees `conftest.py` makes to every other test in the suite."""

from __future__ import annotations

import asyncio
import socket
import threading

import pytest


def test_opening_a_socket_still_fails_loudly() -> None:
    """What the guard is for: a test that grows a dependency on the network
    fails instead of passing on a laptop that happens to be online."""
    with pytest.raises(AssertionError, match="must not touch the network"):
        socket.socket()

    with pytest.raises(AssertionError, match="must not touch the network"):
        socket.create_connection(("example.com", 80))


def test_a_real_socket_is_still_recognised_as_one() -> None:
    """Windows' event loop wakes itself from another thread through a socket
    pair and reads it with `isinstance(conn, socket.socket)`. With a function
    standing in for the class that check raises, the wake-up is lost, and
    anything waiting on a thread hangs until it is killed."""
    one, other = socket.socketpair()
    try:
        assert isinstance(one, socket.socket)
    finally:
        one.close()
        other.close()


def test_a_thread_can_still_wake_the_loop() -> None:
    """`asyncio.to_thread` is how the bot keeps a run off the loop, and it is
    the thing the lost wake-up broke."""

    async def scenario() -> str:
        done = threading.Event()

        def working() -> str:
            assert done.wait(5), "the loop never ran while the thread worked"
            return "worked"

        running = asyncio.create_task(asyncio.to_thread(working))
        await asyncio.sleep(0.05)
        done.set()
        return await running

    assert asyncio.run(scenario()) == "worked"
