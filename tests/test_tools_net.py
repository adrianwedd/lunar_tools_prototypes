import numpy as np
import pytest

# pyzmq lives in the "hw" extra (not installed by CI's "dev" extra). Without
# it, ZMQPairEndpoint degrades gracefully (logs a warning, all sends/receives
# become no-ops), which would otherwise make these tests fail with confusing
# assertion errors rather than a clear skip.
pytest.importorskip("zmq")

# Manager() (constructed directly, without going through the closed
# `headless_manager` fixture, by many tests in test_lunar_tools_art.py) binds
# a ZMQPairEndpoint on the tools' default address tcp://127.0.0.1:5871 and
# never closes it, so when the whole suite runs together that port is
# frequently already taken. Use dedicated high ports here, well away from the
# default, so these tests don't race with those manager instances.
_ROUNDTRIP_PORT = 58711
_IMG_PORT = 58712
_TIMEOUT_PORT = 58713


def test_pair_endpoint_send_receive_roundtrip():
    from lunar_tools_art.tools.net import ZMQPairEndpoint

    server = ZMQPairEndpoint(bind=True, address=f"tcp://127.0.0.1:{_ROUNDTRIP_PORT}")
    client = ZMQPairEndpoint(bind=False, address=f"tcp://127.0.0.1:{_ROUNDTRIP_PORT}")
    try:
        assert server.port == _ROUNDTRIP_PORT
        assert server.ip == "127.0.0.1"

        server.send("ping")
        assert client.receive(timeout_ms=1000) == "ping"
    finally:
        server.close()
        client.close()


def test_pair_endpoint_get_messages_and_send_img():
    from lunar_tools_art.tools.net import ZMQPairEndpoint

    server = ZMQPairEndpoint(bind=True, address=f"tcp://127.0.0.1:{_IMG_PORT}")
    client = ZMQPairEndpoint(bind=False, address=f"tcp://127.0.0.1:{_IMG_PORT}")
    try:
        img = np.arange(2 * 2 * 3, dtype=np.uint8).reshape(2, 2, 3)
        client.send_img(img)

        received = server.receive_img(timeout_ms=1000)
        assert received is not None
        assert received.shape == img.shape
        assert received.dtype == img.dtype
        assert np.array_equal(received, img)

        # get_messages() must not surface image frames as text messages,
        # and must not swallow images without a way to observe them.
        msgs = server.get_messages()
        assert isinstance(msgs, list)
        assert msgs == []
    finally:
        server.close()
        client.close()


def test_receive_timeout_returns_none():
    from lunar_tools_art.tools.net import ZMQPairEndpoint

    server = ZMQPairEndpoint(bind=True, address=f"tcp://127.0.0.1:{_TIMEOUT_PORT}")
    try:
        assert server.receive(timeout_ms=50) is None
    finally:
        server.close()
