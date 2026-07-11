"""Real pyzmq PAIR-socket endpoint used by networked prototypes.

``zmq`` is imported lazily inside methods/constructor so importing this
module never opens a socket, and so tests can monkeypatch it if needed.
"""

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_IMG_TAG = b"__lunar_img__"


class ZMQPairEndpoint:
    """A ZeroMQ PAIR socket wrapper with text and image message helpers.

    ``.ip``/``.port`` are parsed from ``address`` and are also assignable —
    a legacy prototype (``collaborative-canvas.py``) reads/writes them
    directly.
    """

    def __init__(self, bind: bool = True, address: str = "tcp://127.0.0.1:5871"):
        self.address = address
        parsed = urlparse(address)
        self.ip = parsed.hostname
        self.port = parsed.port

        self._degraded = False
        self._socket = None
        self._context = None

        try:
            import zmq

            self._context = zmq.Context.instance()
            self._socket = self._context.socket(zmq.PAIR)
            if bind:
                self._socket.bind(address)
            else:
                self._socket.connect(address)
                # ZMQ's "slow joiner" behavior: give the transport handshake
                # a moment to complete so an immediate send() isn't dropped.
                import time

                time.sleep(0.1)
        except Exception as e:
            if self._socket is not None:
                self._socket.close(linger=0)
                self._socket = None
            self._degraded = True
            logger.warning(f"ZMQ endpoint unavailable ({address}); degraded: {e}")

    def send(self, message: str) -> None:
        if self._degraded:
            return
        self._socket.send_string(message)

    def send_img(self, img) -> None:
        if self._degraded:
            return
        import json

        meta = json.dumps({"shape": list(img.shape), "dtype": str(img.dtype)}).encode()
        self._socket.send_multipart([_IMG_TAG, meta, img.tobytes()])

    @staticmethod
    def _decode_img(frames):
        """Reconstruct a numpy array from an image frame triple."""
        import json

        import numpy as np

        meta = json.loads(frames[1].decode("utf-8"))
        return np.frombuffer(frames[2], dtype=meta["dtype"]).reshape(meta["shape"])

    def receive(self, timeout_ms: int = 0):
        """Return the next text message, or ``None`` if none within timeout.

        Image frames sent via :meth:`send_img` are skipped here — use
        :meth:`receive_img` to consume those.
        """
        if self._degraded:
            return None

        import zmq

        if self._socket.poll(timeout_ms, zmq.POLLIN) == 0:
            return None

        frames = self._socket.recv_multipart()
        if frames and frames[0] == _IMG_TAG:
            return None
        return frames[0].decode("utf-8")

    def receive_img(self, timeout_ms: int = 0):
        """Return the next image sent via :meth:`send_img`, or ``None``.

        Non-image (text) frames encountered while waiting are skipped.
        """
        if self._degraded:
            return None

        import zmq

        if self._socket.poll(timeout_ms, zmq.POLLIN) == 0:
            return None

        frames = self._socket.recv_multipart()
        if not frames or frames[0] != _IMG_TAG:
            return None
        return self._decode_img(frames)

    def get_messages(self) -> list:
        """Drain all currently pending text messages (non-blocking)."""
        messages = []
        if self._degraded:
            return messages

        import zmq

        while self._socket.poll(0, zmq.POLLIN):
            frames = self._socket.recv_multipart()
            if frames and frames[0] == _IMG_TAG:
                continue
            messages.append(frames[0].decode("utf-8"))
        return messages

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close(linger=0)
            self._socket = None
