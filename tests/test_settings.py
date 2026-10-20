import importlib
import os

import pytest


def test_missing_model_name_raises(monkeypatch):
    # clear cached settings
    from backend.config import settings as s
    s.get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.setenv("MODEL_BASE_URL", "http://localhost:9/v1")
    monkeypatch.setenv("MODEL_API_KEY", "x")
    with pytest.raises(RuntimeError) as e:
        s.get_settings()
    assert "MODEL_NAME" in str(e.value)


def test_model_name_env_driven(monkeypatch):
    from backend.config import settings as s
    s.get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setenv("MODEL_NAME", "my/model-7b")
    monkeypatch.setenv("MODEL_BASE_URL", "http://localhost:9/v1")
    monkeypatch.setenv("MODEL_API_KEY", "x")
    cfg = s.get_settings()
    assert cfg.model.name == "my/model-7b"
    # also make sure it's not hardcoded in any imported module
    import pkgutil, backend
    for finder, name, ispkg in pkgutil.walk_packages(backend.__path__, backend.__name__ + "."):
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue
        src = getattr(mod, "__file__", None)
        if not src or not src.endswith(".py"):
            continue
        with open(src, "r", encoding="utf-8") as f:
            text = f.read().lower()
        # None of the following common hardcoded names should appear.
        for forbidden in ("gpt-4", "gpt-3.5", "claude-", "llama-3", "mistral-", "nvidia/"):
            assert forbidden not in text, f"forbidden hardcoded model {forbidden} in {src}"
