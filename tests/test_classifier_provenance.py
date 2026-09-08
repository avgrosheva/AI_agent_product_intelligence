"""Classifier provenance: verifies the API-facing provider/model parsing
(Stage "real LLM classification" release requirement, UI/API section) —
that when a real-LLM classifier is (or isn't) the one that produced
failure_labels, ClassifierProvenance reports classifier_type/provider/
model/is_mock correctly. This is fully offline: it writes a temporary
classifier_metadata.json and reads it back through the same function the
API routers call, so it exercises the exact code path the UI depends on
without needing a live server or an OPENROUTER_API_KEY.
"""

from __future__ import annotations

from backend.app.schemas.common import ClassifierProvenance
from backend.llm import provenance as provenance_module
from backend.llm.provenance import (
    MOCK_CLASSIFIER_VERSION,
    current_classifier_provenance_fields,
    parse_real_llm_version,
    real_llm_classifier_version,
    write_classifier_metadata,
)


def test_real_llm_classifier_version_roundtrip():
    version = real_llm_classifier_version("openrouter", "anthropic/claude-sonnet-5")
    assert version == "openrouter:anthropic/claude-sonnet-5"
    assert parse_real_llm_version(version) == ("openrouter", "anthropic/claude-sonnet-5")


def test_parse_real_llm_version_returns_none_for_mock_version_string():
    assert parse_real_llm_version(MOCK_CLASSIFIER_VERSION) is None


def test_mock_provenance_has_null_provider_and_model(tmp_path, monkeypatch):
    metadata_path = tmp_path / "classifier_metadata.json"
    monkeypatch.setattr(provenance_module, "METADATA_PATH", metadata_path)
    write_classifier_metadata("rule_based_mock", MOCK_CLASSIFIER_VERSION, True, 32299)

    fields = current_classifier_provenance_fields()
    assert fields["classifier_type"] == "rule_based_mock"
    assert fields["is_mock"] is True
    assert fields["provider"] is None
    assert fields["model"] is None

    provenance = ClassifierProvenance(evaluation_status="not_evaluated", **fields)
    assert provenance.is_mock is True
    assert provenance.provider is None


def test_real_llm_provenance_exposes_provider_and_model(tmp_path, monkeypatch):
    metadata_path = tmp_path / "classifier_metadata.json"
    monkeypatch.setattr(provenance_module, "METADATA_PATH", metadata_path)
    version = real_llm_classifier_version("openrouter", "anthropic/claude-sonnet-5")
    write_classifier_metadata("real_llm", version, False, 460)

    fields = current_classifier_provenance_fields()
    assert fields["classifier_type"] == "real_llm"
    assert fields["is_mock"] is False
    assert fields["provider"] == "openrouter"
    assert fields["model"] == "anthropic/claude-sonnet-5"

    provenance = ClassifierProvenance(evaluation_status="not_evaluated", **fields)
    assert provenance.is_mock is False
    assert provenance.classifier_type == "real_llm"
    assert provenance.provider == "openrouter"
    assert provenance.model == "anthropic/claude-sonnet-5"


def test_not_classified_state_has_null_provider_and_model(tmp_path, monkeypatch):
    metadata_path = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(provenance_module, "METADATA_PATH", metadata_path)

    fields = current_classifier_provenance_fields()
    assert fields == {"classifier_type": "not_classified", "is_mock": False}
    provenance = ClassifierProvenance(evaluation_status="not_classified", **fields)
    assert provenance.provider is None
    assert provenance.model is None


def test_mock_and_real_evaluation_summaries_are_stored_separately():
    from backend.llm.provenance import EVALUATION_SUMMARY_PATH, REAL_LLM_EVALUATION_SUMMARY_PATH

    assert EVALUATION_SUMMARY_PATH != REAL_LLM_EVALUATION_SUMMARY_PATH
