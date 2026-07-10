import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(scope="session")
def headless_manager(request):
    """Session-scoped Manager wired against the headless fake tools layer.

    Sets LUNAR_HEADLESS=1 for the whole test session so `tools.resolve()`
    returns deterministic fakes, then constructs a single shared Manager
    instance for smoke tests to instantiate prototypes against.
    """
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("LUNAR_HEADLESS", "1")
    request.addfinalizer(monkeypatch.undo)

    from src.lunar_tools_art import Manager

    manager = Manager()
    # ZMQPairEndpoint has no headless fake (it's a real, lazily-imported
    # pyzmq PAIR socket bound to tcp://127.0.0.1:5871 by default). Close it
    # immediately — none of the smoke tests exercise send/receive on it,
    # they only touch .ip/.port — so it doesn't hold that port for the rest
    # of the session and collide with tests/test_tools_net.py, which binds
    # the same default address.
    if getattr(manager, "zmq_pair_endpoint", None) is not None:
        manager.zmq_pair_endpoint.close()
    return manager
