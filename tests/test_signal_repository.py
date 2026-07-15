from __future__ import annotations

from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import generate_dataset
from metricthread.signal_repository import SupabaseSignalRepository
from metricthread.signals import TEST_CONFIG_VERSION, observations_from_metric_events


def test_signal_repository_upserts_current_evidence_then_archives_only_stale_rows(monkeypatch) -> None:
    requests: list[tuple[str, object]] = []

    class SuccessfulResponse:
        def raise_for_status(self) -> None:
            return None

    def patch(*_: object, **kwargs: object) -> SuccessfulResponse:
        requests.append(("patch", kwargs))
        return SuccessfulResponse()

    def post(*_: object, **kwargs: object) -> SuccessfulResponse:
        requests.append(("post", kwargs))
        return SuccessfulResponse()

    repository = SupabaseSignalRepository("https://example.supabase.co", "test-secret")
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    monkeypatch.setattr(repository, "_metric_observations", lambda: observations_from_metric_events(dataset.events))
    monkeypatch.setattr("metricthread.signal_repository.httpx.patch", patch)
    monkeypatch.setattr("metricthread.signal_repository.httpx.post", post)

    report = repository.run_analysis()

    assert len(report.accepted) == 4
    assert requests[0][0] == "post"
    assert len(requests[0][1]["json"]) == 4
    assert all(row["state"] == "active" and row["superseded_at"] is None for row in requests[0][1]["json"])
    assert requests[1][0] == "patch"
    assert requests[1][1]["params"]["test_config_version"] == f"eq.{TEST_CONFIG_VERSION}"
    assert requests[1][1]["params"]["state"] == "eq.active"
    assert requests[1][1]["params"]["evidence_fingerprint"].startswith("not.in.(")
    assert requests[1][1]["json"]["state"] == "superseded"


def test_signal_repository_reads_only_current_corrected_evidence(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class SuccessfulResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[object]:
            return []

    def get(*_: object, **kwargs: object) -> SuccessfulResponse:
        captured.update(kwargs)
        return SuccessfulResponse()

    monkeypatch.setattr("metricthread.signal_repository.httpx.get", get)
    assert SupabaseSignalRepository("https://example.supabase.co", "test-secret").list_accepted() == []
    assert captured["params"] == {
        "select": "*",
        "test_config_version": f"eq.{TEST_CONFIG_VERSION}",
        "state": "eq.active",
        "adjusted_q_value": "lte.0.05",
        "order": "confidence_score.desc",
    }
