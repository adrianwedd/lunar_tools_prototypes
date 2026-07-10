import numpy as np


def test_pair_endpoint_send_receive_roundtrip():
    from lunar_tools_art.tools.net import ZMQPairEndpoint

    server = ZMQPairEndpoint(bind=True, address="tcp://127.0.0.1:5871")
    client = ZMQPairEndpoint(bind=False, address="tcp://127.0.0.1:5871")
    try:
        assert server.port == 5871
        assert server.ip == "127.0.0.1"

        server.send("ping")
        assert client.receive(timeout_ms=1000) == "ping"
    finally:
        server.close()
        client.close()


def test_pair_endpoint_get_messages_and_send_img():
    from lunar_tools_art.tools.net import ZMQPairEndpoint

    server = ZMQPairEndpoint(bind=True, address="tcp://127.0.0.1:5872")
    client = ZMQPairEndpoint(bind=False, address="tcp://127.0.0.1:5872")
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

    server = ZMQPairEndpoint(bind=True, address="tcp://127.0.0.1:5873")
    try:
        assert server.receive(timeout_ms=50) is None
    finally:
        server.close()
