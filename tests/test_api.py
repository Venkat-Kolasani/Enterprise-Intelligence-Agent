from __future__ import annotations

from fastapi.testclient import TestClient

from metricthread.api import AgentRuntime, create_app
from metricthread.live_pipeline import InMemoryColdStore, LivePipeline
from metricthread.streams import InMemoryStream


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
