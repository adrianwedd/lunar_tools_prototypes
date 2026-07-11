"""Optional LangSmith tracing: no-op decorator when langsmith is absent."""

try:
    from langsmith import traceable  # type: ignore
except ImportError:  # pragma: no cover - exercised via test monkeypatch

    def traceable(*dargs, **dkwargs):
        def deco(fn):
            return fn

        return deco
