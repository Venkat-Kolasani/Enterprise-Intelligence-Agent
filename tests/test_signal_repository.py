from __future__ import annotations

from metricthread.entities import foundation_source_records, resolve_exact_keys
from metricthread.generator import generate_dataset
from metricthread.signal_repository import SupabaseSignalRepository
from metricthread.signals import TEST_CONFIG_VERSION, observations_from_metric_events


def test_signal_repository_reconciles_prior_evidence_before_persisting_current_run(monkeypatch) -> None:
    requests: list[tuple[str, object]] = []

    class SuccessfulResponse:
        def raise_for_status(self) -> None:
            return None

    def delete(*_: object, **kwargs: object) -> SuccessfulResponse:
        requests.append(("delete", kwargs))
        return SuccessfulResponse()

    def post(*_: object, **kwargs: object) -> SuccessfulResponse:
        requests.append(("post", kwargs))
        return SuccessfulResponse()

    repository = SupabaseSignalRepository("https://example.supabase.co", "test-secret")
    dataset = generate_dataset(resolve_exact_keys(foundation_source_records()))
    monkeypatch.setattr(repository, "_metric_observations", lambda: observations_from_metric_events(dataset.events))
    monkeypatch.setattr("metricthread.signal_repository.httpx.delete", delete)
    monkeypatch.setattr("metricthread.signal_repository.httpx.post", post)

    report = repository.run_analysis()

    assert len(report.accepted) == 4
    assert requests[0][0] == "delete"
    assert requests[0][1]["params"] == {"test_config_version": f"eq.{TEST_CONFIG_VERSION}"}
    assert requests[1][0] == "post"
    assert len(requests[1][1]["json"]) == 4
