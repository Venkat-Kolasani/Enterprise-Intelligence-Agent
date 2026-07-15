from __future__ import annotations

import argparse
import time
from typing import Any

import httpx


def request_json(client: httpx.Client, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise AssertionError(f"{method} {path} did not return an object")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the deployed MetricThread judge-demo API")
    parser.add_argument("--base-url", required=True, help="Render API origin, for example https://metricthread-api.onrender.com")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        health = request_json(client, "GET", "/health")
        if health != {"status": "ok", "demo_access": "read_only"}:
            raise AssertionError(f"unexpected health response: {health}")

        status = request_json(client, "GET", "/agent/status")
        if status.get("simulation_label") != "synthetic live simulation":
            raise AssertionError("agent status is missing the synthetic-data label")
        if status.get("demo_access") != "read_only":
            raise AssertionError("deployed judge demo is not read-only")

        signals = request_json(client, "GET", "/signals").get("signals", [])
        if not signals:
            raise AssertionError("no accepted signals are available to a judge")
        if any(signal.get("adjusted_q_value", 1) > 0.05 for signal in signals):
            raise AssertionError("an uncorrected signal appeared in the judge demo")

        insights = request_json(client, "GET", "/insights").get("insights", [])
        if not insights:
            raise AssertionError("no persisted grounded insight is available to a judge")

        answer = request_json(
            client,
            "POST",
            "/chat",
            json={"question": "Why is CAC rising?", "prior_insight_ids": []},
        )
        if answer.get("status") != "grounded" or not answer.get("signal_ids"):
            raise AssertionError(f"CAC chat response was not grounded: {answer}")

        refusal = request_json(
            client,
            "POST",
            "/chat",
            json={"question": "What did a competitor change?", "prior_insight_ids": []},
        )
        if refusal.get("status") != "no_evidence":
            raise AssertionError(f"unsupported chat did not refuse: {refusal}")

        forecast = request_json(
            client,
            "POST",
            "/scenarios/forecast",
            json={"input_metric": "marketing_spend", "input_change_percent": 10, "horizon_days": 7},
        ).get("forecast", {})
        if forecast.get("input_metric") != "marketing_spend" or not forecast.get("supporting_signal_ids"):
            raise AssertionError(f"forecast is not evidence-linked: {forecast}")

        request_json(client, "POST", "/simulation/start")
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            metrics = request_json(client, "GET", "/metrics/live").get("metrics", [])
            if metrics:
                break
            time.sleep(1)
        else:
            raise AssertionError("the live simulation did not reach the hot path within 15 seconds")

        blocked = client.post("/signals/run")
        if blocked.status_code != 403:
            raise AssertionError(f"read-only signal analysis was not blocked: {blocked.status_code}")

    print("Phase 6 deployed rehearsal passed: read-only, grounded, evidence-linked, and live paths verified.")


if __name__ == "__main__":
    main()
