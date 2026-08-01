"""Phase 9B: role dispatch, env overrides and the internal contracts (fast)."""
from __future__ import annotations

import pytest

from app.config import _apply_env_overrides, _coerce
from app.models.internal import ChunkOut, RetrieveResponse
from app.modules.retrieval.dense import RetrievedChunk
from app.services import role


@pytest.fixture
def as_role(monkeypatch):
    """Run the body as a given service role and services.mode."""

    def _set(service_role: str, mode: str = "distributed"):
        from app.config import get_config

        monkeypatch.setenv(role.ROLE_ENV, service_role)
        monkeypatch.setattr(get_config().services, "mode", mode)

    return _set


# --- role dispatch ------------------------------------------------------------


def test_monolith_runs_everything_locally(as_role):
    """The default must keep working with no services and no infrastructure."""
    as_role("api", mode="monolith")
    assert role.runs_locally(role.RETRIEVAL) is True
    assert role.runs_locally(role.INGESTION) is True


def test_api_delegates_both_components(as_role):
    as_role("api")
    assert role.runs_locally(role.RETRIEVAL) is False
    assert role.runs_locally(role.INGESTION) is False


def test_retrieval_service_runs_retrieval_itself(as_role):
    """Without this the retrieval service would call itself over HTTP forever."""
    as_role("retrieval")
    assert role.runs_locally(role.RETRIEVAL) is True
    assert role.runs_locally(role.INGESTION) is False


def test_ingestion_service_runs_ingestion_itself(as_role):
    as_role("ingestion")
    assert role.runs_locally(role.INGESTION) is True
    # ...and asks retrieval to rebuild BM25 rather than doing it locally.
    assert role.runs_locally(role.RETRIEVAL) is False


def test_unknown_role_falls_back_to_monolith(monkeypatch):
    monkeypatch.setenv(role.ROLE_ENV, "not-a-role")
    assert role.current_role() == role.MONOLITH


# --- environment overrides ----------------------------------------------------


def test_env_overrides_nested_yaml_keys(monkeypatch):
    monkeypatch.setenv("RAG_STORES__VECTOR", "pgvector")
    monkeypatch.setenv("RAG_SERVICES__RETRIEVAL_URL", "http://retrieval:8011")
    data = _apply_env_overrides({"stores": {"vector": "chroma", "relational": "sqlite"}})
    assert data["stores"]["vector"] == "pgvector"
    assert data["stores"]["relational"] == "sqlite"  # untouched keys survive
    assert data["services"]["retrieval_url"] == "http://retrieval:8011"


def test_env_values_get_real_types():
    assert _coerce("true") is True
    assert _coerce("false") is False
    assert _coerce("5") == 5
    assert _coerce("0.45") == 0.45
    assert _coerce("pgvector") == "pgvector"


def test_unprefixed_environment_is_ignored(monkeypatch):
    monkeypatch.setenv("PATH_LIKE_THING", "x")
    assert _apply_env_overrides({"a": 1}) == {"a": 1}


# --- wire contract ------------------------------------------------------------


def test_chunk_survives_the_round_trip():
    """A chunk must arrive from the retrieval service exactly as it left."""
    original = RetrievedChunk(
        chunk_id="c1", text="Metformin is first-line.", source="guideline.pdf",
        section_path="Treatment > Adults", score=0.87, file_type="pdf", title="Guideline",
        page_number=14, locator=None, content_type="text",
    )
    restored = ChunkOut.of(original).to_chunk()
    assert restored == original


def test_retrieve_response_round_trips_through_json():
    payload = RetrieveResponse(
        chunks=[
            ChunkOut.of(
                RetrievedChunk(chunk_id="c1", text="t", source="s", section_path="", score=0.5)
            )
        ],
        confidence=0.91,
        mode="hybrid",
    )
    back = RetrieveResponse.model_validate_json(payload.model_dump_json())
    assert back.confidence == 0.91 and back.chunks[0].chunk_id == "c1"
