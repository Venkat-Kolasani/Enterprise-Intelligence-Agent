from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from metricthread.api import AgentRuntime, create_app
from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import generate_dataset
from metricthread.insights import InMemoryInsightStore, InsightRecord, RecommendationRecord
from metricthread.live_pipeline import InMemoryColdStore, LivePipeline
from metricthread.signals import InMemorySignalRepository, observations_from_metric_events
from metricthread.streams import InMemoryStream


class ReadOnlyEvidenceRepository:
    def __init__(self, signals, observations) -> None:
        self._signals = signals
        self._observations = observations

    def list_accepted(self):
        return list(self._signals)

    def list_metric_observations(self):
        return list(self._observations)

    def run_analysis(self):
        raise AssertionError("A casefile GET must not persist or rerun repository analysis")


def test_casefile_replays_evidence_and_validates_the_model_boundary_without_writing() -> None:
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    observations = observations_from_metric_events(dataset.events)
    source_repository = InMemorySignalRepository(observations)
    report = source_repository.run_analysis()
    primary = next(
        signal
        for signal in report.accepted
        if signal.metric_a == "partner_referral_quality" and signal.metric_b == "client_acquisition_cost"
    )
    insight_store = InMemoryInsightStore()
    insight_id = uuid4()
    insight_store.persist_generated(
        InsightRecord(
            id=insight_id,
            title="Stored predictive narrative",
            narrative_text="Synthetic predictive evidence only.",
            related_signal_ids=(str(primary.id),),
            confidence_score=primary.confidence_score,
            domains=(primary.domain_a, primary.domain_b),
            status="active",
            generated_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
        ),
        RecommendationRecord(
            id=uuid4(),
            insight_id=insight_id,
            recommendation_text="Review the partner program with a human owner.",
            predicted_impact={"statement": "Predictive only."},
            confidence_score=primary.confidence_score,
            status="proposed",
            created_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
        ),
    )
    pipeline = LivePipeline(InMemoryStream(), InMemoryColdStore(), consumer_name="casefile-api-test")
    app = create_app(
        AgentRuntime(pipeline, interval_seconds=60),
        ReadOnlyEvidenceRepository(report.accepted, observations),
        insight_store,
    )

    with TestClient(app) as client:
        response = client.get(f"/signals/{primary.id}/casefile")
        missing = client.get(f"/signals/{uuid4()}/casefile")

    assert response.status_code == 200
    assert missing.status_code == 404
    payload = response.json()["casefile"]
    assert payload["recomputation"]["state"] == "matches_persisted_evidence"
    assert payload["replay"]["source"]["metric"] == "partner_referral_quality"
    assert len(payload["replay"]["source"]["points"]) == 180
    assert len(payload["replay"]["target"]["points"]) == 180
    assert payload["test_family"]["candidate_count"] == 54
    assert payload["test_family"]["retained_count"] == 4
    assert payload["test_family"]["rejected_count"] == 50
    assert all(control["status"] == "rejected" for control in payload["test_family"]["declared_negative_controls"])
    assert payload["signal"]["test_metadata"]["source_preparation"]["transformation"] == "first_difference"
    assert payload["signal"]["test_metadata"]["target_preparation"]["transformation"] == "first_difference"
    assert len(payload["signal"]["test_metadata"]["input_data_digest"]) == 64
    assert payload["model_evidence_packet"]["signal_id"] == str(primary.id)
    assert payload["claim_audit"]["confidence"]["matches_deterministic_formula"] is True
    assert payload["claim_audit"]["confidence"]["model_may_change_score"] is False
    citation_check = payload["claim_audit"]["citation_checks"][0]
    assert citation_check["cites_casefile_signal"] is True
    assert citation_check["unknown_cited_signal_ids"] == []
    assert citation_check["confidence_matches_casefile"] is True
    assert "caused" in payload["claim_audit"]["causal_language_guard"]["forbidden_terms"]
