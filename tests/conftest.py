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
    # ZMQPairEndpoint resolves to FakeZMQPairEndpoint in headless mode (no
    # socket, no pyzmq). close() is kept as belt-and-braces for anyone
    # running this fixture without LUNAR_HEADLESS.
    if getattr(manager, "zmq_pair_endpoint", None) is not None:
        manager.zmq_pair_endpoint.close()
    return manager
