from lunar_tools_art.prototype_base import PrototypeBase


class _FakeManager:
    renderer = None
    keyboard_input = None
    main_queue = None


class Exploding(PrototypeBase):
    def setup(self):
        raise RuntimeError("boom at setup")

    def update(self):
        pass

    def cleanup(self):
        pass


class Clean(PrototypeBase):
    def setup(self):
        pass

    def update(self):
        self._running = False

    def cleanup(self):
        pass


def test_fatal_exception_recorded():
    p = Exploding(_FakeManager())
    p.run()
    assert isinstance(p.last_fatal_error, RuntimeError)
    assert "boom at setup" in str(p.last_fatal_error)


def test_clean_exit_leaves_no_error():
    p = Clean(_FakeManager())
    p.run()
    assert p.last_fatal_error is None
