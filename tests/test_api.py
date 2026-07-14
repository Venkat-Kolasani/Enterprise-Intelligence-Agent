from __future__ import annotations

from fastapi.testclient import TestClient

from metricthread.api import AgentRuntime, create_app
from metricthread.live_pipeline import InMemoryColdStore, LivePipeline
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
