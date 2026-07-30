"""Phase 8: ChatGPT-style conversation titling (fast — the model is never called)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_config
from app.main import create_app
from app.modules.generation import generator
from app.modules.generation.prompt import build_title_prompt

client = TestClient(create_app())

LONG_QUESTION = "Why am I getting a ModuleNotFoundError when importing LangChain on Windows 11"


def _boom():
    raise RuntimeError("the title path must not need a live model")


@pytest.fixture
def title_cfg():
    return get_config().models.title


def test_clean_title_strips_quotes_and_trailing_punctuation():
    assert generator._clean_title('  "Fixing LangChain Import Errors."  ') == (
        "Fixing LangChain Import Errors"
    )
    assert generator._clean_title("`Understanding RAG`?") == "Understanding RAG"
    assert generator._clean_title("BM25  vs\n Vector Search") == "BM25 vs Vector Search"


def test_fallback_title_trims_on_a_word_boundary(title_cfg):
    got = generator.fallback_title(LONG_QUESTION)
    assert got.endswith("…")
    assert len(got) <= title_cfg.max_chars + 1  # the ellipsis is added after the cut
    assert LONG_QUESTION.startswith(got.rstrip("…"))  # never mid-word


def test_disabled_titling_skips_the_model(monkeypatch, title_cfg):
    monkeypatch.setattr(title_cfg, "enabled", False)
    monkeypatch.setattr(generator, "get_instructor_client", _boom)
    assert generator.generate_title("What is RAG?") == "What is RAG?"


def test_model_failure_degrades_to_the_question(monkeypatch, title_cfg):
    """A title is cosmetic — a broken model must not surface as an error."""
    monkeypatch.setattr(title_cfg, "enabled", True)
    monkeypatch.setattr(generator, "get_instructor_client", _boom)
    assert generator.generate_title("What is RAG?") == "What is RAG?"


def test_title_prompt_is_formatted_with_the_configured_word_cap():
    prompt = build_title_prompt(5)
    assert "At most 5 significant words" in prompt
    assert "{max_words}" not in prompt


def test_endpoint_flags_a_fallback_as_not_generated(monkeypatch, title_cfg):
    monkeypatch.setattr(title_cfg, "enabled", False)
    res = client.post("/v1/title", json={"question": "How do I install FastAPI on Windows?"})
    assert res.status_code == 200
    assert res.json() == {
        "title": "How do I install FastAPI on Windows?",
        "generated": False,
    }


def test_endpoint_rejects_a_too_short_question():
    assert client.post("/v1/title", json={"question": "hi"}).status_code == 422
