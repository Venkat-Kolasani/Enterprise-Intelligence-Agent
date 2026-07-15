from __future__ import annotations

from fastapi.testclient import TestClient

from metricthread.api import AgentRuntime, create_app
from metricthread.executive import InMemoryExecutiveStore
from metricthread.insights import GroundedNarrative, InMemoryInsightStore
from metricthread.live_pipeline import InMemoryColdStore, LivePipeline
from metricthread.resilience import InMemoryResilienceStore, assess_signal_resilience
from metricthread.signals import InMemorySignalRepository, observations_from_metric_events
from metricthread.streams import InMemoryStream
from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import generate_dataset


def test_agent_status_and_simulation_endpoints_expose_live_pipeline_state() -> None:
    pipeline = LivePipeline(InMemoryStream(), InMemoryColdStore(), consumer_name="api-test")
    app = create_app(AgentRuntime(pipeline, interval_seconds=60))

    with TestClient(app) as client:
        before_start = client.get("/agent/status")
        started = client.post("/simulation/start")
        live_metrics = client.get("/metrics/live")

    assert before_start.status_code == 200
    assert before_start.json()["simulation_state"] == "idle"
    assert started.status_code == 200
    assert started.json()["started"] is True
    assert started.json()["simulation_label"] == "synthetic live simulation"
    assert live_metrics.status_code == 200
    assert live_metrics.json()["simulation_label"] == "synthetic live simulation"


def test_signal_endpoints_return_only_persisted_deterministic_evidence() -> None:
    pipeline = LivePipeline(InMemoryStream(), InMemoryColdStore(), consumer_name="signal-api-test")
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    repository = InMemorySignalRepository(observations_from_metric_events(dataset.events))
    app = create_app(AgentRuntime(pipeline, interval_seconds=60), repository)

    with TestClient(app) as client:
        before_run = client.get("/signals")
        run = client.post("/signals/run")
        after_run = client.get("/signals")

    assert before_run.status_code == 200
    assert before_run.json()["signals"] == []
    assert run.status_code == 200
    assert run.json()["accepted_count"] == 4
    assert after_run.status_code == 200
    primary = next(
        signal
        for signal in after_run.json()["signals"]
        if signal["source"]["metric"] == "partner_referral_quality"
        and signal["target"]["metric"] == "client_acquisition_cost"
    )
    assert primary["adjusted_q_value"] <= 0.05
    assert primary["test_metadata"]["lag_interpretation"] == "BIC-selected model history, not a causal delay claim"


def test_grounded_insight_and_recommendation_lifecycle_endpoints() -> None:
    class SingleSignalRepository:
        def __init__(self, signal):
            self._signal = signal

        def list_accepted(self):
            return [self._signal]

        def run_analysis(self):
            raise AssertionError("not used by this test")

    class Narrator:
        def generate(self, signal):
            signal_id = str(signal.id)
            return GroundedNarrative(
                signal_id=signal_id,
                title="Predictive partner-quality signal",
                narrative="This predictive lead-lag evidence is consistent with higher acquisition cost in the synthetic live simulation.",
                recommendation="Propose a human review before any partner-program action.",
                predicted_impact="Any impact remains predictive and must be measured after implementation.",
                evidence_signal_ids=(signal_id,),
            )

    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    observations = observations_from_metric_events(dataset.events)
    signal = next(
        item for item in InMemorySignalRepository(observations).run_analysis().accepted
        if item.metric_a == "partner_referral_quality" and item.metric_b == "client_acquisition_cost"
    )
    resilience_store = InMemoryResilienceStore()
    resilience_store.persist(assess_signal_resilience(signal, observations))
    pipeline = LivePipeline(InMemoryStream(), InMemoryColdStore(), consumer_name="insight-api-test")
    app = create_app(
        AgentRuntime(pipeline, interval_seconds=60),
        SingleSignalRepository(signal),
        InMemoryInsightStore(),
        Narrator(),
        resilience_store=resilience_store,
    )

    with TestClient(app) as client:
        generated = client.post("/insights/generate")
        insight = generated.json()["insight"]
        recommendation_id = insight["recommendations"][0]["id"]
        skipped = client.post(f"/recommendations/{recommendation_id}/status", json={"status": "implemented"})
        planned = client.post(f"/recommendations/{recommendation_id}/status", json={"status": "planned"})
        implemented = client.post(f"/recommendations/{recommendation_id}/status", json={"status": "implemented"})
        backward = client.post(f"/recommendations/{recommendation_id}/status", json={"status": "planned"})
        outcome = client.post(
            f"/recommendations/{recommendation_id}/outcomes",
            json={
                "implemented_at": "2026-06-30T00:00:00Z",
                "outcome_metric": "client_acquisition_cost",
                "outcome_value": 121.4,
                "measured_at": "2026-07-07T00:00:00Z",
                "notes": "Synthetic lifecycle test.",
            },
        )
        listed = client.get("/insights")

    assert generated.status_code == 200
    assert generated.json()["generated"] is True
    assert skipped.status_code == 409
    assert planned.json()["recommendation"]["status"] == "planned"
    assert implemented.json()["recommendation"]["status"] == "implemented"
    assert backward.status_code == 409
    assert outcome.status_code == 200
    assert outcome.json()["recommendation"]["outcome"]["outcome_metric"] == "client_acquisition_cost"
    assert listed.json()["insights"][0]["recommendations"][0]["outcome"] is not None


def test_resilience_endpoint_persists_a_versioned_assessment() -> None:
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    repository = InMemorySignalRepository(observations_from_metric_events(dataset.events))
    report = repository.run_analysis()
    primary = next(
        signal
        for signal in report.accepted
        if signal.metric_a == "partner_referral_quality" and signal.metric_b == "client_acquisition_cost"
    )
    app = create_app(
        AgentRuntime(LivePipeline(InMemoryStream(), InMemoryColdStore(), consumer_name="resilience-api-test")),
        repository,
        resilience_store=InMemoryResilienceStore(),
    )

    with TestClient(app) as client:
        before = client.get(f"/signals/{primary.id}/resilience")
        run = client.post(f"/signals/{primary.id}/resilience/run")
        after = client.get(f"/signals/{primary.id}/resilience")

    assert before.json()["resilience"] is None
    assert run.status_code == 200
    assert run.json()["resilience"]["recommendation_eligible"] is True
    assert after.json()["resilience"]["summary"]["origin_count"] == 4


def test_read_only_judge_demo_blocks_persistence_but_keeps_forecasts_and_cors_available() -> None:
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    repository = InMemorySignalRepository(observations_from_metric_events(dataset.events))
    repository.run_analysis()
    executive_store = InMemoryExecutiveStore()
    app = create_app(
        AgentRuntime(LivePipeline(InMemoryStream(), InMemoryColdStore(), consumer_name="judge-demo-test")),
        repository,
        InMemoryInsightStore(),
        executive_store=executive_store,
        demo_read_only=True,
        cors_origins=["https://metricthread.example"],
    )

    with TestClient(app) as client:
        status = client.get("/agent/status")
        health = client.get("/health")
        blocked_signals = client.post("/signals/run")
        blocked_insight = client.post("/insights/generate")
        blocked_resilience = client.post("/signals/00000000-0000-0000-0000-000000000000/resilience/run")
        blocked_briefing = client.post("/briefings/generate")
        forecast = client.post(
            "/scenarios/forecast",
            json={"input_metric": "marketing_spend", "input_change_percent": 10, "horizon_days": 7},
        )
        preflight = client.options(
            "/agent/status",
            headers={
                "Origin": "https://metricthread.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert status.json()["demo_access"] == "read_only"
    assert health.json()["status"] == "ok"
    assert blocked_signals.status_code == 403
    assert blocked_insight.status_code == 403
    assert blocked_resilience.status_code == 403
    assert blocked_briefing.status_code == 403
    assert forecast.status_code == 200
    assert executive_store.list_forecasts() == []
    assert preflight.headers["access-control-allow-origin"] == "https://metricthread.example"
