from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import generate_dataset
from metricthread.insights import GroundedInsightService, GroundedNarrative, InMemoryInsightStore
from metricthread.resilience import InMemoryResilienceStore, assess_signal_resilience
from metricthread.signals import InMemorySignalRepository, observations_from_metric_events


def _primary_signal_and_observations():
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    observations = observations_from_metric_events(dataset.events)
    repository = InMemorySignalRepository(observations)
    report = repository.run_analysis()
    primary = next(
        signal
        for signal in report.accepted
        if signal.metric_a == "partner_referral_quality"
        and signal.metric_b == "client_acquisition_cost"
    )
    return primary, observations


def test_rolling_origin_resilience_requires_stability_baseline_wins_and_rejected_controls() -> None:
    primary, observations = _primary_signal_and_observations()

    assessment = assess_signal_resilience(
        primary,
        observations,
        evaluated_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
    )

    assert assessment.recommendation_eligible is True
    summary = assessment.result["summary"]
    assert summary["origin_count"] == 4
    assert summary["signal_retained_windows"] == 4
    assert summary["baseline_wins"] == 3
    assert summary["negative_controls_rejected_windows"] == 4
    assert summary["suppression_reasons"] == []
    assert all(origin["negative_controls_rejected"] for origin in assessment.result["origins"])
    assert all(
        control["status"] == "rejected"
        for origin in assessment.result["origins"]
        for control in origin["negative_controls"]
    )
    assert assessment.evaluation_config["baseline_model_version"] == "target_history_ols_v1"
    assert assessment.evaluation_config["origin_count"] == 4
    assert json.loads(json.dumps(assessment.as_public_dict()))["recommendation_eligible"] is True


def test_resilience_suppresses_recommendations_when_the_signal_fails_stability() -> None:
    primary, observations = _primary_signal_and_observations()
    altered_observations = [
        replace(
            observation,
            value=(observation.event_time.date().toordinal() % 7) * 10 + 50,
        )
        if observation.metric_name == "partner_referral_quality"
        else observation
        for observation in observations
    ]

    assessment = assess_signal_resilience(primary, altered_observations)
    resilience_store = InMemoryResilienceStore()
    resilience_store.persist(assessment)

    class FixedRepository:
        def list_accepted(self):
            return [primary]

    class Narrator:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, signal):
            self.calls += 1
            return GroundedNarrative(
                signal_id=str(signal.id),
                title="Should never be produced",
                narrative="This predictive lead-lag evidence is consistent with synthetic data.",
                recommendation="Do not use this response.",
                predicted_impact="Predictive only.",
                evidence_signal_ids=(str(signal.id),),
            )

    narrator = Narrator()
    service = GroundedInsightService(
        FixedRepository(), InMemoryInsightStore(), narrator, resilience_store
    )

    assert assessment.recommendation_eligible is False
    assert "signal_not_retained_in_enough_origins" in assessment.result["summary"]["suppression_reasons"]
    assert service.generate_next() is None
    assert narrator.calls == 0
