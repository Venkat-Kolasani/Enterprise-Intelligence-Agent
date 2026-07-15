from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from metricthread.api import AgentRuntime, create_app
from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.executive import (
    BriefingService,
    GroundedChatService,
    InMemoryExecutiveStore,
    ScenarioForecastService,
)
from metricthread.generator import generate_dataset
from metricthread.insights import InMemoryInsightStore, InsightRecord, RecommendationRecord
from metricthread.live_pipeline import InMemoryColdStore, LivePipeline
from metricthread.signals import InMemorySignalRepository, observations_from_metric_events
from metricthread.streams import InMemoryStream


def _signal_repository() -> InMemorySignalRepository:
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    repository = InMemorySignalRepository(observations_from_metric_events(dataset.events))
    repository.run_analysis()
    return repository


def _insight_store(signal_id: str) -> InMemoryInsightStore:
    now = datetime(2026, 6, 30, tzinfo=timezone.utc)
    insight = InsightRecord(
        id=uuid4(),
        title="Partner referral quality and client acquisition cost",
        narrative_text="This predictive lead-lag evidence is consistent with a relationship between partner referral quality and client acquisition cost.",
        related_signal_ids=(signal_id,),
        confidence_score=99.33,
        domains=("partner", "client"),
        status="active",
        generated_at=now,
    )
    recommendation = RecommendationRecord(
        id=uuid4(),
        insight_id=insight.id,
        recommendation_text="Conduct a human-led review of partner referral qualification criteria.",
        predicted_impact={"human_review_required": True},
        confidence_score=99.33,
        status="proposed",
        created_at=now,
    )
    store = InMemoryInsightStore()
    store.persist_generated(insight, recommendation)
    return store


def test_briefing_and_chat_only_return_stored_evidence() -> None:
    repository = _signal_repository()
    primary = next(
        signal
        for signal in repository.list_accepted()
        if signal.metric_a == "partner_referral_quality" and signal.metric_b == "client_acquisition_cost"
    )
    insight_store = _insight_store(str(primary.id))
    executive_store = InMemoryExecutiveStore()

    briefing = BriefingService(insight_store, executive_store, repository).generate()
    chat = GroundedChatService(insight_store, repository).answer("Why is CAC rising?")
    follow_up = GroundedChatService(insight_store, repository).answer(
        "What action is proposed?", prior_insight_ids=chat.insight_ids
    )
    unsupported = GroundedChatService(insight_store, repository).answer(
        "What is the competitor pricing strategy?"
    )
    stale_evidence = GroundedChatService(
        insight_store, InMemorySignalRepository([])
    ).answer("Why is CAC rising?")

    assert briefing is not None
    assert str(primary.id) in briefing.summary_text
    assert BriefingService(insight_store, executive_store, repository).generate() is None
    assert BriefingService(insight_store, InMemoryExecutiveStore(), InMemorySignalRepository([])).generate() is None
    assert chat.result == "answer"
    assert chat.signal_ids == (str(primary.id),)
    assert chat.insight_ids == (str(insight_store.list_insights()[0].id),)
    assert follow_up.result == "answer"
    assert follow_up.insight_ids == chat.insight_ids
    assert follow_up.signal_ids == chat.signal_ids
    assert unsupported.result == "no_evidence"
    assert unsupported.insight_ids == ()
    assert stale_evidence.result == "no_evidence"


def test_marketing_scenario_is_persisted_with_expected_forecast_direction_and_intervals() -> None:
    repository = _signal_repository()
    executive_store = InMemoryExecutiveStore()

    forecast = ScenarioForecastService(repository, executive_store).forecast(
        input_change_percent=10,
        horizon_days=7,
    )

    assert forecast.forecast_values["recognized_revenue"][4] > forecast.baseline_values["recognized_revenue"][4]
    assert forecast.forecast_values["client_acquisition_cost"][0] > forecast.baseline_values["client_acquisition_cost"][0]
    assert forecast.prediction_intervals["recognized_revenue"][4]["lower"] < forecast.forecast_values["recognized_revenue"][4]
    assert forecast.prediction_intervals["recognized_revenue"][4]["upper"] > forecast.forecast_values["recognized_revenue"][4]
    assert 0 <= forecast.reliability_score <= 100
    assert executive_store.list_forecasts() == [forecast]


def test_phase_five_api_returns_citations_refuses_unsupported_questions_and_bounds_scenarios() -> None:
    repository = _signal_repository()
    primary = next(
        signal
        for signal in repository.list_accepted()
        if signal.metric_a == "partner_referral_quality" and signal.metric_b == "client_acquisition_cost"
    )
    insight_store = _insight_store(str(primary.id))
    app = create_app(
        AgentRuntime(LivePipeline(InMemoryStream(), InMemoryColdStore(), consumer_name="executive-api-test")),
        repository,
        insight_store,
        executive_store=InMemoryExecutiveStore(),
    )

    with TestClient(app) as client:
        briefing = client.post("/briefings/generate")
        answer = client.post("/chat", json={"question": "Why is CAC rising?"})
        follow_up = client.post(
            "/chat",
            json={"question": "What action is proposed?", "prior_insight_ids": answer.json()["insight_ids"]},
        )
        unsupported = client.post("/chat", json={"question": "What is the competitor pricing strategy?"})
        scenario = client.post(
            "/scenarios/forecast",
            json={"input_metric": "marketing_spend", "input_change_percent": 10, "horizon_days": 7},
        )
        out_of_scope = client.post(
            "/scenarios/forecast",
            json={"input_metric": "marketing_spend", "input_change_percent": 21, "horizon_days": 7},
        )

    assert briefing.status_code == 200
    assert briefing.json()["generated"] is True
    assert answer.json()["result"] == "answer"
    assert answer.json()["signal_ids"] == [str(primary.id)]
    assert follow_up.json()["result"] == "answer"
    assert follow_up.json()["insight_ids"] == answer.json()["insight_ids"]
    assert unsupported.json()["result"] == "no_evidence"
    assert scenario.status_code == 200
    assert scenario.json()["forecast"]["supporting_signal_ids"]
    assert out_of_scope.status_code == 422
