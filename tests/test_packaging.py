import builtins
import sys


def test_import_without_langsmith(monkeypatch):
    real_import = builtins.__import__

    def block(name, *a, **k):
        if name.startswith("langsmith"):
            raise ImportError("blocked")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", block)
    for mod in [m for m in list(sys.modules) if m.startswith("lunar_tools_art")]:
        del sys.modules[mod]
    import lunar_tools_art.manager  # must not raise

    assert lunar_tools_art.manager is not None


def test_traceable_noop_preserves_function():
    from lunar_tools_art.tracing import traceable

    @traceable(name="x")
    def f(a):
        return a + 1

    assert f(1) == 2
