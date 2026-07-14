from __future__ import annotations

from metricthread.live_pipeline import InMemoryColdStore, LivePipeline
from metricthread.streams import InMemoryStream


def test_each_simulated_day_reaches_independent_hot_and_cold_paths() -> None:
    stream = InMemoryStream()
    cold_store = InMemoryColdStore()
    pipeline = LivePipeline(stream, cold_store, consumer_name="test-worker")

    pipeline.start()
    assert pipeline.emit_next_day() == 9
    pipeline.process_once()

    status = pipeline.status()
    assert status.hot_events_processed == 9
    assert status.cold_events_persisted == 9
    assert status.hot_pending == 0
    assert status.cold_pending == 0
    assert len(cold_store.events) == 9
    assert len(pipeline.latest_metrics()) == 9


def test_cold_path_leaves_events_recoverable_when_durable_write_fails() -> None:
    class FailingStore:
        def persist(self, events: list[dict[str, object]]) -> None:
            raise RuntimeError("durable store unavailable")

    stream = InMemoryStream()
    pipeline = LivePipeline(stream, FailingStore(), consumer_name="test-worker")

    pipeline.start()
    pipeline.emit_next_day()
    pipeline.process_once()

    status = pipeline.status()
    assert status.hot_pending == 0
    assert status.cold_pending == 9
    assert status.last_cold_error == "durable store unavailable"
