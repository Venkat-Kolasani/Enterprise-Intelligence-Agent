from __future__ import annotations

import json

import pytest

from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import generate_dataset
from metricthread.insights import (
    GroundedInsightService,
    GroundedNarrative,
    InMemoryInsightStore,
    OpenAIResponsesNarrativeGenerator,
)
from metricthread.signals import DeterministicSignalEngine, observations_from_metric_events


def _primary_signal():
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    report = DeterministicSignalEngine().analyze(observations_from_metric_events(dataset.events))
    return next(
        signal
        for signal in report.accepted
        if (signal.metric_a, signal.metric_b) == ("partner_referral_quality", "client_acquisition_cost")
    )


class FixedSignalRepository:
    def __init__(self, signals):
        self._signals = signals

    def list_accepted(self):
        return list(self._signals)

    def run_analysis(self):
        raise AssertionError("not used by grounded-insight tests")


class GroundedNarrator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, signal):
        self.calls += 1
        signal_id = str(signal.id)
        return GroundedNarrative(
            signal_id=signal_id,
            title="Partner referral quality predicts higher acquisition cost",
            narrative="This predictive lead-lag evidence is consistent with a negative relationship in the synthetic live simulation.",
            recommendation="Propose a human review of partner referral quality and acquisition-cost monitoring.",
            predicted_impact="Any observed impact requires measurement after a human-controlled action.",
            evidence_signal_ids=(signal_id,),
        )


def test_grounded_service_generates_once_for_a_new_signal_and_tracks_human_lifecycle() -> None:
    primary = _primary_signal()
    store = InMemoryInsightStore()
    narrator = GroundedNarrator()
    service = GroundedInsightService(FixedSignalRepository([primary]), store, narrator)

    generated = service.generate_next()

    assert generated is not None
    assert narrator.calls == 1
    assert generated.insight.related_signal_ids == (str(primary.id),)
    assert generated.recommendation.status == "proposed"
    assert generated.recommendation.confidence_score == primary.confidence_score
    assert generated.recommendation.predicted_impact["human_review_required"] is True
    assert service.generate_next() is None
    assert narrator.calls == 1

    with pytest.raises(ValueError, match="cannot transition"):
        store.update_recommendation_status(generated.recommendation.id, "implemented")
    planned = store.update_recommendation_status(generated.recommendation.id, "planned")
    implemented = store.update_recommendation_status(planned.id, "implemented")
    with pytest.raises(ValueError, match="cannot transition"):
        store.update_recommendation_status(implemented.id, "planned")
    outcome = store.record_outcome(
        implemented.id,
        implemented_at=implemented.created_at,
        outcome_metric="client_acquisition_cost",
        outcome_value=121.4,
        measured_at=implemented.created_at,
        notes="Synthetic outcome recorded for lifecycle verification.",
    )
    assert outcome.outcome is not None
    assert outcome.outcome["outcome_metric"] == "client_acquisition_cost"


def test_openai_generator_uses_a_strict_low_cost_grounded_request(monkeypatch) -> None:
    primary = _primary_signal()
    captured: dict[str, object] = {}

    class Response:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self._payload

    def get(*_: object, **__: object) -> Response:
        return Response({"id": "gpt-5.6-luna"})

    def post(*_: object, **kwargs: object) -> Response:
        captured.update(kwargs)
        return Response(
            {
                "output_text": json.dumps(
                    {
                        "signal_id": str(primary.id),
                        "title": "Quality signal requires review",
                        "narrative": "This predictive lead-lag evidence is consistent with a negative synthetic relationship.",
                        "recommendation": "Propose a human review before any action.",
                        "predicted_impact": "Any impact remains predictive and requires measurement.",
                        "evidence_signal_ids": [str(primary.id)],
                    }
                )
            }
        )

    monkeypatch.setattr("metricthread.insights.httpx.get", get)
    monkeypatch.setattr("metricthread.insights.httpx.post", post)
    narrative = OpenAIResponsesNarrativeGenerator("test-key", "gpt-5.6-luna").generate(primary)

    assert narrative.signal_id == str(primary.id)
    request = captured["json"]
    assert request["model"] == "gpt-5.6-luna"
    assert request["store"] is False
    assert request["reasoning"] == {"effort": "low"}
    assert request["text"]["format"]["strict"] is True


def test_openai_generator_rejects_causal_language_even_in_schema_valid_output(monkeypatch) -> None:
    primary = _primary_signal()

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "output_text": json.dumps(
                    {
                        "signal_id": str(primary.id),
                        "title": "Quality causes CAC movement",
                        "narrative": "This predictive lead-lag evidence proves the relationship.",
                        "recommendation": "Propose a human review.",
                        "predicted_impact": "Any impact remains predictive.",
                        "evidence_signal_ids": [str(primary.id)],
                    }
                )
            }

    monkeypatch.setattr("metricthread.insights.httpx.get", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr("metricthread.insights.httpx.post", lambda *_args, **_kwargs: Response())

    with pytest.raises(RuntimeError, match="evidence language"):
        OpenAIResponsesNarrativeGenerator("test-key", "gpt-5.6-luna").generate(primary)
